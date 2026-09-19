"""Offline preview, guarded qualification collection, and offline manual adjudication."""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import unicodedata

import httpx
import yaml

import probe_generators as probe
import validate_generator_qualification_fixtures as fixtures

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_COMMIT = '683c0416c5bf47c83021408f26bc7a7ab5e8becc'
MANIFEST_HASH = 'ecce7e579f02f64bb5578d8b18b9164483da1c5438544f21a89e17d7a2aaa1f9'
PACKAGE_HASH = '848ca0219ff1d24adcf2f12d0789ebeb8e7a86427336672173b91e034dca6b62'
CONTRACT_HASH = '3ac8a05ac25a0d7473887979392a825da2f6ee84b1a5b77f1b6e6d6b465b86ee'
PROMPT_HASH = 'a7b7013488d27b95962d1131d4d635eb065238b92e87f2b654d817a01d99d279'
SCHEMA_HASH = 'c0970e798666467520b3b33fc2657424c52ecf8be3a97d502f056156257cb917'
# Fallback capability-probe execution-package identity (Sec. 1); UNDER_DEVELOPMENT, never CLOSED here.
FALLBACK_PACKAGE_HASH = '1316b2b1f3a7f5f15f64d5b3b2ef379c60f96edddff8b5f62bf0e712d7099e1b'
# Execution package hash for the second-level G2 profile.
SECOND_LEVEL_G2_PACKAGE_HASH = 'fb2c74eec9fea2ab49cee00e76cbe84ec7ce0fe2464e80bf84d157e82ec56180'
PACKAGE_HASHES = {'primary': PACKAGE_HASH, 'fallback': FALLBACK_PACKAGE_HASH,
                  'second_level_g2': SECOND_LEVEL_G2_PACKAGE_HASH}
DEFAULT_OUTPUT = ROOT / 'results/generator-qualification/attempt-01'
FALLBACK_DEFAULT_OUTPUT = ROOT / 'results/generator-qualification/attempt-02'
PROCEDURE = 'generator-qualification-procedure/1.0.0'
AUDIT_SCHEMA = 'generator-manual-audit/1.0.0'
# Execution-critical sources. Hashed at run time (never a hardcoded self-hash) and,
# for live execution, pinned by a separate freeze record committed after review.
SOURCES = ('experiments/qualify_generators.py', 'experiments/probe_generators.py',
           'experiments/validate_generator_qualification_fixtures.py')
FREEZE_RECORD = ROOT / 'configs/generator-qualification-implementation-freeze.json'
# Implementation freeze records pin a commit and the SHA-256 of each file in SOURCES. FREEZE_RECORD covers
# protocol v1. Protocol v2 uses revisioned records (-v2, -v2-r2, ..., -v2-r5): only the current revision,
# V2_FREEZE_RECORD, is consulted, and earlier revisions are kept as historical provenance. The revision
# suffix is independent of the protocol version. implementation('v2') reports NOT_FROZEN until it exists.
V2_FREEZE_RECORD = ROOT / 'configs/generator-qualification-implementation-freeze-v2-r5.json'
FREEZE_SCHEMA = 'generator-qualification-implementation-freeze/1.0.0'
NOT_FROZEN = 'NOT YET FROZEN FOR LIVE EXECUTION'
FROZEN = 'FROZEN FOR LIVE EXECUTION'
EVENTS = (*fixtures.EVENTS, 'Q')
INITIAL = tuple(e for e in EVENTS if e.startswith('I'))
UPDATES = tuple(e for e in EVENTS if e.startswith('U'))
# Fixed semantic applicability; every other (check, event) pair is NA in the template.
APPLICABILITY = {
    'natural_english': EVENTS,
    'entity_fidelity': EVENTS,
    'attribute_fidelity': EVENTS,
    'current_value_fidelity': fixtures.EVENTS,  # Q states no value.
    'changed_vs_hypothetical_wording': UPDATES,
    'same_state_fidelity': ('N1', 'N2'),
    'superseded_value_leakage': tuple(e for e in EVENTS if e not in INITIAL),  # Nothing superseded yet.
    'invented_information_or_state_change': EVENTS,
    'merged_or_omitted_event': EVENTS,
    'output_boundary': EVENTS,
    'q_intent_fidelity': ('Q',),
    'answer_leakage': ('Q',),
}
CHECKS = tuple(APPLICABILITY)
PROCEDURE_V1 = PROCEDURE
AUDIT_SCHEMA_V1 = AUDIT_SCHEMA
PROCEDURE_V2 = 'generator-qualification-procedure/2.0.0'
AUDIT_SCHEMA_V2 = 'generator-manual-audit/2.0.0'
# Protocol v2 (docs/generator-qualification.md Sec. 14, "Two-Level Quality Model", FROZEN): the single
# v1 natural_english cell splits into comprehensibility (Level 1, hard gate; same applicability as
# v1 natural_english -- every event) and fluency (Level 2, descriptive only; never disqualifying).
# Every other v1 check is unchanged and stays Level 1. No score, ranking, or threshold is implemented.
APPLICABILITY_V2 = {**{c: e for c, e in APPLICABILITY.items() if c != 'natural_english'},
                     'comprehensibility': EVENTS, 'fluency': EVENTS}
CHECKS_V2 = tuple(APPLICABILITY_V2)
PROTOCOLS = {
    'v1': {'procedure': PROCEDURE_V1, 'audit_schema': AUDIT_SCHEMA_V1,
           'applicability': APPLICABILITY, 'checks': CHECKS, 'level2': frozenset(), 'derived_summaries': False},
    'v2': {'procedure': PROCEDURE_V2, 'audit_schema': AUDIT_SCHEMA_V2,
           'applicability': APPLICABILITY_V2, 'checks': CHECKS_V2, 'level2': frozenset({'fluency'}),
           'derived_summaries': True},
}


def archive_protocol(procedure_version):
    """Protocol key ('v1' or 'v2') for a recorded qualification procedure version."""
    for key, spec in PROTOCOLS.items():
        if spec['procedure'] == procedure_version:
            return key
    raise ValueError(f'Unknown attempt procedure: {procedure_version}')


def archived_protocol(directory):
    """Protocol under which the attempt in `directory` was collected, from its own qualification.json."""
    return archive_protocol(fixtures.read(Path(directory) / 'qualification.json')['procedure_version'])


TERMINAL_AUTOMATED = {'status': 'FAIL', 'findings': [], 'reason': 'Execution/parse/schema failed'}
SUMS_LINE = re.compile(r'([0-9a-f]{64})  (\S.*)')
# RFC 3339 with an explicit offset, e.g. 2026-09-18T21:30:00+07:00.
TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})')
EXHAUSTED = 'INFRASTRUCTURE_RETRY_EXHAUSTED'
CONTRACT = 'EXECUTION_CONTRACT_FAILURE'
RUNNER = 'RUNNER_EXCEPTION'
require = probe.require


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def implementation(protocol='v1'):
    """Technical source identity; live execution is permitted only under a valid, CURRENT freeze
    record FOR THE GIVEN PROTOCOL. protocol='v1' reads the historical FREEZE_RECORD; protocol='v2'
    reads the separate V2_FREEZE_RECORD -- exactly the same reproducibility principles apply to
    either (a real, reachable, authentic commit whose git-archived bytes match the pinned hashes
    exactly), and neither record is ever substituted for the other. Defaults to 'v1', so every
    existing call site is unaffected.

    A well-formed freeze record whose pinned hashes no longer match current bytes means development has
    continued past the last freeze -- an expected, normal state (NOT_FROZEN), not a fatal error. Only a
    malformed record, or one whose claimed hashes don't match its own cited commit's real git history
    (an authenticity problem), raises.
    """
    require(protocol in ('v1', 'v2'), f'Unknown protocol: {protocol}')
    record_path = FREEZE_RECORD if protocol == 'v1' else V2_FREEZE_RECORD  # Live lookup: respects monkeypatching.
    sources = {path: probe.file_hash(ROOT / path) for path in SOURCES}
    if not record_path.exists():
        return {'status': NOT_FROZEN, 'freeze_commit': None, 'source_sha256': sources}
    record = fixtures.read(record_path)
    probe.fields(record, ['schema_version', 'implementation_commit', 'source_sha256'])
    commit = record['implementation_commit']
    require(record['schema_version'] == FREEZE_SCHEMA and type(commit) is str
            and re.fullmatch(r'[0-9a-f]{40}', commit) is not None
            and type(record['source_sha256']) is dict and set(record['source_sha256']) == set(SOURCES),
            'Malformed implementation freeze record')
    git('merge-base', '--is-ancestor', commit, 'HEAD')  # The cited commit must be real and reachable.
    for path in SOURCES:
        require(probe.digest(git('show', f'{commit}:{path}')) == record['source_sha256'][path],
                'Implementation differs from frozen commit')  # The record must match its own cited commit.
    if record['source_sha256'] != sources:
        # The record is authentic, but development has continued past it: NOT_FROZEN, not a fatal error.
        return {'status': NOT_FROZEN, 'freeze_commit': None, 'source_sha256': sources}
    return {'status': FROZEN, 'freeze_commit': commit, 'source_sha256': sources}


def verify_archived_implementation(record):
    """Independently re-verify an archived attempt's implementation identity against git history,
    not against the current (possibly mid-development, uncommitted) working tree. A later,
    legitimately re-frozen implementation must not break replay of an attempt collected under an
    earlier freeze: this checks the archive's own claim is authentic, not that it matches right now.
    """
    probe.fields(record, ['status', 'freeze_commit', 'source_sha256'])
    require(record['status'] == FROZEN, 'Archived attempt implementation not FROZEN')
    commit = record['freeze_commit']
    require(type(commit) is str and re.fullmatch(r'[0-9a-f]{40}', commit) is not None,
            'Malformed archived implementation commit')
    require(type(record['source_sha256']) is dict and set(record['source_sha256']) == set(SOURCES),
            'Malformed archived source hash set')
    git('merge-base', '--is-ancestor', commit, 'HEAD')
    for path, expected_hash in record['source_sha256'].items():
        require(probe.digest(git('show', f'{commit}:{path}')) == expected_hash,
                "Archived implementation hash does not match its own frozen commit")


def load_inputs(profile='primary', slot=None, protocol='v1'):
    """Pin current bytes to the reviewed committed fixture set and execution contract.

    profile selects the PRIMARY (CLOSED) or predeclared FALLBACK (Terra/Opus) candidate pair. The
    frozen fixture set, naturalization contract, prompt, and output schema are shared and unchanged
    by profile; only candidate identity and the execution-package file/hash under test differ.

    protocol selects which qualification-procedure identity (docs/generator-qualification.md Sec. 14)
    a FUTURE collection under these inputs would be recorded under; it never changes the generation
    task itself (fixtures, prompt, input/output contract, execution package are all shared and
    unchanged by protocol). Defaults to 'v1', so every existing call site is unaffected.

    slot, if given (e.g. 'G1'), restricts the returned plan to that one logical call from the
    profile; the config itself is still validated against the FULL predeclared pair (it always
    declares both), only the planned/active slots are filtered. Omit slot for the full profile --
    the historical, unchanged two-slot behavior.
    """
    require(profile in probe.PROFILES, f'Unknown candidate profile: {profile}')
    package_hash = PACKAGE_HASHES[profile]
    selected = probe.PROFILES[profile]
    require(probe.file_hash(selected['config_path']) == package_hash, 'Execution package drift')
    require(probe.file_hash(ROOT / 'configs/generator-naturalization-contract.json') == CONTRACT_HASH,
            'Semantic contract drift')
    bundle = probe.load_bundle(selected['config_path'], slots=selected['slots'], status=selected['status'],
                               capability_result=selected['capability_result'],
                               successful_attempt=selected['successful_attempt'],
                               execution_package=selected['execution_package'],
                               execution_compatibility=selected['execution_compatibility'])
    require(bundle['provenance']['prompt_sha256'] == PROMPT_HASH, 'Prompt drift')
    require(bundle['provenance']['output_schema_sha256'] == SCHEMA_HASH, 'Output schema drift')
    manifest_path = fixtures.DIRECTORY / 'manifest.json'
    require(probe.file_hash(manifest_path) == MANIFEST_HASH, 'Frozen manifest drift')
    manifest, truth = fixtures.validate_directory()
    git('merge-base', '--is-ancestor', FIXTURE_COMMIT, 'HEAD')
    for path in [manifest_path, fixtures.DIRECTORY / 'reference-schema.json',
                 *[fixtures.DIRECTORY / e['fixture_path'] for e in manifest['fixtures']]]:
        committed = git('show', f'{FIXTURE_COMMIT}:{path.relative_to(ROOT).as_posix()}')
        require(committed == path.read_bytes(), 'Frozen fixture-set provenance mismatch')
    active_slots = selected['slots'] if slot is None else [
        s for s in selected['slots'] if s['logical_call_id'] == slot]
    require(active_slots, f'Unknown slot for profile {profile}: {slot}')
    return {'bundle': bundle, 'manifest': manifest, 'fixtures': truth, 'slots': active_slots,
            'profile': profile, 'selected_slot': slot,
            'provenance': {'source_commit': git('rev-parse', 'HEAD').decode().strip(),
                'candidate_profile': profile.upper(), 'selected_slot': slot,
                'fixture_set_commit': FIXTURE_COMMIT, 'fixture_manifest_sha256': MANIFEST_HASH,
                'execution_config_sha256': package_hash, 'contract_sha256': CONTRACT_HASH,
                'prompt_sha256': PROMPT_HASH, 'output_schema_sha256': SCHEMA_HASH,
                **probe.VERSIONS, 'procedure_version': PROTOCOLS[protocol]['procedure'], 'implementation': implementation(protocol),
                'python': platform.python_version(),
                'packages': {n: importlib.metadata.version(n) for n in ('httpx', 'pydantic', 'pyyaml')}}}


def slot_capability_gate(profile_name, slot):
    """Live Generator Qualification for one slot requires CLOSED/PASS capability evidence for the
    EXACT candidate occupying that slot. Generic: reads probe.slot_capability(), never a
    hardcoded Terra/Opus check. One slot's PASS never authorizes another slot; stale evidence for a
    replaced candidate (model mismatch) never authorizes the new one; the primary profile's own
    CLOSED/PASS evidence is read from ITS OWN config and cannot satisfy a different profile's slot.
    """
    capability = probe.slot_capability(profile_name, slot)
    require(capability['model'] == slot['model'] and capability['status'] == 'CLOSED'
            and capability['capability_result'] == 'PASS',
            f'Generator Qualification for {slot["logical_call_id"]} ({slot["model"]}) requires '
            f'CLOSED/PASS capability evidence for this exact candidate; current status: '
            f'{capability["status"]}/{capability["capability_result"]}'
            + (f' ({capability["reason"]})' if capability.get('reason') else ''))


def plan(inputs):
    return [(slot, truth, entry) for slot in inputs['slots']
            for truth, entry in zip(inputs['fixtures'], inputs['manifest']['fixtures'])]


def request(inputs, slot, truth):
    bundle = dict(inputs['bundle'], input=fixtures.validate_fixture(truth))
    return probe.request_body(bundle, slot, input_validator=fixtures.validate_input)


def preview(inputs, output):
    per_candidate = len(inputs['fixtures'])
    planned = len(inputs['slots']) * per_candidate
    return {'status': 'NETWORK_DISABLED', 'credits': 'CREDITS_NOT_SPENT',
            'qualification_status': 'NOT EXECUTED', 'generator_status': 'CANDIDATE',
            'qualification_implementation_status': inputs['provenance']['implementation']['status'],
            **inputs['provenance'],
            'planned_logical_calls': planned, 'per_candidate': per_candidate,
            'maximum_physical_attempts': planned * 3,
            'order': ', then '.join(f"{s['logical_call_id']} all fixtures" for s in inputs['slots'])
                    + '; frozen manifest order',
            'fixture_ids': [e['fixture_id'] for e in inputs['manifest']['fixtures']],
            'planned_calls': [f'{i}:{s["logical_call_id"]}:{e["fixture_id"]}'
                              for i, (s, _, e) in enumerate(plan(inputs), 1)],
            'candidates': inputs['slots'], 'generation': probe.GENERATION, 'transport': probe.TRANSPORT,
            'execution_mode': 'standard', 'allow_fallbacks': False, 'require_parameters': True,
            'wire_mapping': probe.MAPPING, 'result_directory': str(output),
            'request_hashes': [probe.digest(probe.canonical(request(inputs, s, f)).encode())
                               for s, f, _ in plan(inputs)]}


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def contains(text, expression):
    """Literal normalized full expression, with word boundaries; no substring gate."""
    return re.search(r'(?<!\w)' + re.escape(normalize(expression)) + r'(?!\w)', normalize(text)) is not None


def overlaps(a, b):
    return contains(a, b) or contains(b, a)


def semantic_check(truth, output):
    probe.validate_output(output)
    r = truth['reference']
    keys = {k['state_key']: k for k in r['state_keys']}
    names = {e['entity_id']: e['name'] for e in r['entities']}
    attrs = {a['attribute_id']: a for a in r['attributes']}
    findings = []
    def flag(variant, event, status, code, expression=None):
        findings.append(dict(id=f'{variant}/{event}/{len(findings) + 1}', variant=variant,
                             event=event, status=status, code=code, expression=expression))
    for variant in fixtures.VARIANTS:
        for event in r['variants'][variant]['events']:
            label = event['event']
            text = output[variant][label]
            key = keys[event['state_key']]
            name, value = names[key['entity_id']], event['current_value']
            if not contains(text, name):
                flag(variant, label, 'MANUAL_REVIEW_REQUIRED', 'entity_not_literal', name)
            if not contains(text, value):
                flag(variant, label, 'MANUAL_REVIEW_REQUIRED', 'current_value_not_literal', value)
            for other in sorted({v for k in keys.values() for v in k['value_inventory']} - {value}):
                if contains(text, other):
                    ambiguous = overlaps(other, value) or overlaps(other, name)
                    flag(variant, label, 'MANUAL_REVIEW_REQUIRED' if ambiguous else 'FAIL',
                         'superseded_value' if other in event['superseded_values'] else 'wrong_known_value', other)
            for foreign in names.values():
                if foreign != name and contains(text, foreign):
                    flag(variant, label, 'MANUAL_REVIEW_REQUIRED' if overlaps(foreign, name) else 'FAIL',
                         'foreign_entity', foreign)
        q = output[variant]['Q']
        target = keys[r['target_state_key']]
        name = names[target['entity_id']]
        if not contains(q, name):
            foreign = any(contains(q, n) for n in names.values() if n != name)
            flag(variant, 'Q', 'FAIL' if foreign else 'MANUAL_REVIEW_REQUIRED', 'q_entity', name)
        attribute = attrs[target['attribute_id']]
        # An absent literal attribute may be a faithful paraphrase; do not fail synonyms.
        if not (contains(q, attribute['meaning']) or contains(q, target['attribute_id'].replace('_', ' '))):
            wrong = [a['meaning'] for a in attrs.values() if a is not attribute and contains(q, a['meaning'])]
            flag(variant, 'Q', 'FAIL' if wrong else 'MANUAL_REVIEW_REQUIRED', 'q_attribute', attribute['meaning'])
        for value in target['value_inventory']:
            if contains(q, value):
                flag(variant, 'Q', 'MANUAL_REVIEW_REQUIRED' if overlaps(value, name) else 'FAIL',
                     'q_answer_leakage', value)
    if len({output[v]['Q'] for v in fixtures.VARIANTS}) != 1:
        flag('all', 'Q', 'FAIL', 'q_wording_not_identical')
    status = 'FAIL' if any(f['status'] == 'FAIL' for f in findings) else (
        'MANUAL_REVIEW_REQUIRED' if findings else 'PASS')
    return {'status': status, 'meaning': 'No deterministic violation detected is not semantic qualification.',
            'findings': findings}


def applicable(check, event, applicability=APPLICABILITY):
    return event in applicability[check]


def terminal(call):
    """Machine-detectable terminal failure; no manual record can reverse it."""
    if call['status'] != 'PASS':
        return f'{call["fixture_id"]}: terminal logical-call failure: {call["failure_reason"]}'
    if call['automated']['status'] == 'FAIL':
        return f'{call["fixture_id"]}: deterministic automated semantic FAIL'
    return None


def audit_template(result, result_hash, slots=None, protocol='v1'):
    """No invented review: null means unreviewed; NA only by the fixed applicability table.

    Terminally failed calls have no parsed output to review, so they carry no event records.
    slots defaults to the primary pair; a fallback attempt passes its own candidate identity.
    protocol selects the manual-audit schema/check set (docs/generator-qualification.md Sec. 14);
    it defaults to 'v1', so every existing call site keeps producing byte-identical v1 output.
    """
    slots = slots if slots is not None else probe.SLOTS
    spec = PROTOCOLS[protocol]
    checks, applicability = spec['checks'], spec['applicability']
    candidates = {}
    for slot in slots:
        records = {}
        for call in result['calls']:
            if call['candidate'] != slot['logical_call_id']:
                continue
            reviewable = call['status'] == 'PASS'
            records[call['fixture_id']] = {'disposition': None, 'notes': '',
                'call_status': call['status'], 'automated_status': call['automated']['status'],
                'output_sha256': call.get('output_sha256'),
                'ambiguities': {f['id']: {'disposition': None, 'notes': ''}
                    for f in call['automated']['findings'] if f['status'] == 'MANUAL_REVIEW_REQUIRED'},
                'variants': {v: {'disposition': None, 'notes': '', 'events': {
                    e: {**{c: None if applicable(c, e, applicability) else 'NA' for c in checks}, 'notes': ''}
                    for e in EVENTS}} for v in fixtures.VARIANTS} if reviewable else {}}
        candidates[slot['logical_call_id']] = {'model': slot['model'], 'disposition': None, 'fixtures': records}
    return {'schema_version': spec['audit_schema'], 'qualification_sha256': result_hash,
            'check_applicability': {c: list(e) for c, e in applicability.items()},
            'reviewer': '', 'reviewed_at': '', 'notes': '', 'candidates': candidates}


def valid_timestamp(text):
    if TIMESTAMP.fullmatch(text) is None:
        return False
    try:
        # Calendar/offset validity; the fraction's form is already checked by the pattern.
        datetime.fromisoformat(re.sub(r'\.\d+', '', text).replace('Z', '+00:00'))
    except ValueError:
        return False
    return True


def adjudicate(result, audit, result_hash, slots=None, protocol='v1'):
    """Terminal failure resolves FAIL at once; otherwise every applicable Level-1 manual item must
    PASS. Under protocol 'v2' the fluency check is Level 2 (docs/generator-qualification.md Sec. 14):
    a Level-2 FAIL is recorded in basis[slot]['level2_findings'] and still requires evidence notes and
    counts toward pending completeness, but never sets a variant/fixture/candidate FAIL by itself.
    protocol defaults to 'v1', so every existing call site keeps producing byte-identical v1 output.

    Historical v1 requires the reviewer to mark variant/fixture/candidate dispositions by hand. Under
    v2 the human decides only applicable manual CHECKS and ambiguity resolutions: variant, fixture and
    candidate outcomes are deterministic derived results (variant FAIL iff a Level-1 check FAILs in it;
    fixture FAIL iff a terminal failure, ambiguity FAIL or failed variant; PASS once every required cell
    in scope is complete; candidate FAIL iff any Level-1 failure, QUALIFIED iff none and nothing
    pending), reported in basis[slot]['derived_dispositions']. A manually supplied v2 summary
    disposition is rejected rather than silently ignored or allowed to override derived evidence.
    """
    slots = slots if slots is not None else probe.SLOTS
    spec = PROTOCOLS[protocol]
    checks, applicability, level2 = spec['checks'], spec['applicability'], spec['level2']
    derived = spec['derived_summaries']
    expected = audit_template(result, result_hash, slots, protocol)
    probe.fields(audit, expected)
    for field in ('schema_version', 'qualification_sha256', 'check_applicability'):
        require(audit[field] == expected[field], 'Audit provenance mismatch')
    for field in ('reviewer', 'reviewed_at', 'notes'):
        require(type(audit[field]) is str, 'Audit text field')
    require(not audit['reviewed_at'] or valid_timestamp(audit['reviewed_at']),
            'reviewed_at must be an RFC 3339 timestamp with offset, e.g. 2026-09-18T21:30:00+07:00')
    # reviewer names the human reviewer chosen by the researcher; the template never fills it.
    identified = bool(audit['reviewer'].strip() and audit['reviewed_at'])
    if result['status'] == 'INVALIDATED':  # Not model-capability evidence: no candidate becomes FAIL.
        return {'procedure_version': spec['procedure'], 'qualification_sha256': result_hash,
                'manual_audit_sha256': probe.digest(probe.canonical(audit).encode()),
                'candidates': {s['logical_call_id']: 'INVALIDATED' for s in slots},
                'basis': {'invalidation': result['invalidation']}}

    def manual(value, notes, level):
        require(value in (None, 'PASS', 'FAIL') and type(notes) is str, f'Invalid {level} value')
        require(value is None or identified, 'Manual values require reviewer and reviewed_at')
        require(value != 'FAIL' or bool(notes.strip()), f'Manual {level} FAIL requires evidence notes')
        return value

    probe.fields(audit['candidates'], expected['candidates'])
    verdicts, basis = {}, {}
    for slot, template in expected['candidates'].items():
        reviewed = audit['candidates'][slot]
        probe.fields(reviewed, template)
        require(reviewed['model'] == template['model'], 'Audit model mismatch')
        calls = [c for c in result['calls'] if c['candidate'] == slot]
        require(len(calls) == 12, 'Incomplete candidate evidence')
        probe.fields(reviewed['fixtures'], template['fixtures'])
        terminals, failures, level2_findings, pending = [], [], [], 0
        derived_fixtures = {}
        for call in calls:
            fid = call['fixture_id']
            record, blank = reviewed['fixtures'][fid], template['fixtures'][fid]
            probe.fields(record, blank)
            for field in ('call_status', 'automated_status', 'output_sha256'):
                require(record[field] == blank[field], 'Audit evidence mismatch')
            reason = terminal(call)
            fixture_failed = reason is not None
            fixture_pending = 0
            derived_variants = {}
            if reason:
                terminals.append(reason)
            probe.fields(record['ambiguities'], blank['ambiguities'])
            for finding, resolution in record['ambiguities'].items():
                probe.fields(resolution, ['disposition', 'notes'])
                value = manual(resolution['disposition'], resolution['notes'], 'ambiguity')
                require(value is None or bool(resolution['notes'].strip()), 'Ambiguity resolution requires notes')
                pending += value is None
                fixture_pending += value is None
                if value == 'FAIL':
                    failures.append(f'{fid}: ambiguity {finding} resolved FAIL')
                    fixture_failed = True
            probe.fields(record['variants'], blank['variants'])
            for variant, vr in record['variants'].items():
                probe.fields(vr, ['disposition', 'notes', 'events'])
                variant_failed, variant_pending = False, 0
                probe.fields(vr['events'], EVENTS)
                for event, event_checks in vr['events'].items():
                    probe.fields(event_checks, [*checks, 'notes'])
                    require(type(event_checks['notes']) is str, 'Event notes')
                    for check in checks:
                        if not applicable(check, event, applicability):
                            require(event_checks[check] == 'NA', 'Invalid applicability')
                            continue
                        value = manual(event_checks[check], event_checks['notes'], 'check')
                        pending += value is None
                        variant_pending += value is None
                        if value == 'FAIL':
                            entry = f'{fid}/{variant}/{event}: {check} FAIL'
                            if check in level2:
                                level2_findings.append(entry)
                            else:
                                failures.append(entry)
                                variant_failed = True
                if derived:
                    require(vr['disposition'] is None and type(vr['notes']) is str,
                            'Protocol v2 variant disposition is derived; a manual value was supplied')
                    derived_variants[variant] = 'FAIL' if variant_failed else None if variant_pending else 'PASS'
                    fixture_failed |= variant_failed
                    fixture_pending += variant_pending
                    continue
                value = manual(vr['disposition'], vr['notes'], 'variant')
                require(not (value == 'PASS' and variant_failed), 'Variant PASS contradicts recorded FAIL')
                pending += value is None
                if value == 'FAIL':
                    failures.append(f'{fid}/{variant}: variant FAIL')
                fixture_failed |= variant_failed or value == 'FAIL'
            if derived:
                require(record['disposition'] is None and type(record['notes']) is str,
                        'Protocol v2 fixture disposition is derived; a manual value was supplied')
                derived_fixtures[fid] = {'disposition': 'FAIL' if fixture_failed else None if fixture_pending else 'PASS',
                                         'variants': derived_variants}
                continue
            value = manual(record['disposition'], record['notes'], 'fixture')
            require(not (value == 'PASS' and fixture_failed), 'Fixture PASS contradicts recorded FAIL')
            pending += value is None
            if value == 'FAIL':
                failures.append(f'{fid}: fixture FAIL')
        failed = bool(terminals or failures)
        value = reviewed['disposition']  # v1: a manual summary; v2: must be unset (derived below).
        if derived:
            require(value is None, 'Protocol v2 candidate disposition is derived; a manual value was supplied')
        else:
            require(value in (None, 'PASS', 'FAIL'), 'Invalid candidate value')
            require(value is None or identified, 'Manual values require reviewer and reviewed_at')
            require(not (value == 'PASS' and failed), 'Candidate PASS contradicts recorded FAIL')
            require(not (value == 'FAIL' and not failed), 'Candidate FAIL without recorded failure')
            pending += value is None
        verdicts[slot] = 'FAIL' if failed else 'PENDING_MANUAL_AUDIT' if pending else 'QUALIFIED'
        basis[slot] = {'terminal_failures': terminals, 'manual_failures': failures, 'pending_manual_items': pending}
        if level2:  # Only present for a protocol that defines a Level-2 check (v2: fluency); v1 basis
            basis[slot]['level2_findings'] = level2_findings  # shape stays byte-identical to before.
        if derived:
            basis[slot]['derived_dispositions'] = derived_fixtures
    return {'procedure_version': spec['procedure'], 'qualification_sha256': result_hash,
            'manual_audit_sha256': probe.digest(probe.canonical(audit).encode()),
            'candidates': verdicts, 'basis': basis}


def derive_v2_audit_template(result, result_hash, v1_audit, slots=None):
    """Offline v1 -> v2 audit mapping for HISTORICAL Protocol-v1 evidence only (docs/generator-
    qualification.md Sec. 14, "Historical v1 -> v2 mapping"; FROZEN) -- i.e. `result` was collected
    under PROCEDURE_V1. It is not the construction path for a newly qualified Protocol-v2 candidate:
    a candidate qualified for the first time AFTER Protocol v2 is active is executed natively under
    v2 (audit_template(..., protocol='v2') from the start, via collect(..., protocol='v2')), and never
    passes through this mapping function at all. Starts from a blank Protocol-v2 template derived from
    the SAME archived result the v1_audit was itself completed against, then carries every v1 manual
    judgment other than natural_english forward unchanged, including ambiguity resolutions.

    natural_english = PASS maps mechanically to comprehensibility = PASS, fluency = PASS.
    natural_english = FAIL is never auto-classified: comprehensibility and fluency are left None
    (pending an explicit reviewer decision), and the (fixture, variant, event) plus the historical v1
    note are returned separately in pending_reclassification -- never copied into the v2 event's own
    notes field, so a stale v1 note can never be mistaken for an already-made v2 judgment.

    Variant/fixture/candidate-level disposition and notes are always left blank (None/''): they are
    derived summaries, not the per-check manual "cells" the frozen rule carries forward. Under v2 they
    are never manual inputs at all: adjudicate(protocol='v2') derives them deterministically from the
    cell-level evidence and rejects a manually supplied one.

    No candidate identity is inspected anywhere in this function.
    """
    slots = slots if slots is not None else probe.SLOTS
    require(result['procedure_version'] == PROCEDURE_V1, 'Source evidence is not a Protocol-v1 collection')
    require(v1_audit['schema_version'] == AUDIT_SCHEMA_V1, 'Source audit is not a Protocol-v1 audit')
    require(v1_audit['qualification_sha256'] == result_hash, 'Source v1 audit does not match this result')
    v2_template = audit_template(result, result_hash, slots, protocol='v2')
    pending_reclassification = []
    for slot_id, v2_candidate in v2_template['candidates'].items():
        v1_candidate = v1_audit['candidates'][slot_id]
        for fixture_id, v2_fixture in v2_candidate['fixtures'].items():
            v1_fixture = v1_candidate['fixtures'][fixture_id]
            for finding_id, v2_resolution in v2_fixture['ambiguities'].items():
                v1_resolution = v1_fixture['ambiguities'][finding_id]
                v2_resolution['disposition'] = v1_resolution['disposition']
                v2_resolution['notes'] = v1_resolution['notes']
            for variant, v2_variant in v2_fixture['variants'].items():
                v1_variant = v1_fixture['variants'][variant]
                for event, v2_checks in v2_variant['events'].items():
                    v1_checks = v1_variant['events'][event]
                    for check in CHECKS:
                        if check == 'natural_english' or v2_checks.get(check) == 'NA':
                            continue
                        v2_checks[check] = v1_checks[check]
                    v1_value = v1_checks['natural_english']
                    if v1_value == 'PASS':
                        v2_checks['comprehensibility'] = 'PASS'
                        v2_checks['fluency'] = 'PASS'
                    elif v1_value == 'FAIL':
                        pending_reclassification.append({'fixture_id': fixture_id, 'variant': variant,
                            'event': event, 'v1_natural_english_note': v1_checks['notes']})
                    # v1_value is None (v1 review incomplete): the v2 cells stay unreviewed, as blank.
    return v2_template, pending_reclassification


def resolve_primary_precedence(primary_qualified, fallback_qualified):
    """docs/generator-qualification.md Sec. 14, "Primary precedence" (FROZEN) -- a pure, offline G1
    slot-resolution rule applied only AFTER both candidates' Protocol-v2 QUALIFIED/not-QUALIFIED
    dispositions are already known. Never used inside per-candidate qualification adjudication itself,
    and never decided from fluency counts, subjective quality, or any other outcome.

    Returns 'primary' (Sol occupies G1), 'fallback' (Terra occupies G1), or None (unresolved).
    """
    if primary_qualified:
        return 'primary'
    if fallback_qualified:
        return 'fallback'
    return None


def publish(path, value, secret=''):
    path = Path(path)
    data = (json.dumps(probe.redact(value, secret), ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink()
    return probe.digest(data)


def invalidation(call, slot):
    """Attempt-level invalidation, not candidate evidence; None for a completed or candidate-level outcome.

    Retry exhaustion is checked first: infrastructure failure is not evidence of model capability.
    """
    if call['status'] == 'PASS':
        return None
    attempts, last = call['attempts'], call['attempts'][-1]
    where = f'{call["candidate"]}/{call["fixture_id"]} (logical call {call["logical_call_index"]})'
    if len(attempts) == 1 + probe.TRANSPORT['max_infrastructure_retries'] and all(a['retry_reason'] for a in attempts):
        return {'kind': EXHAUSTED, 'logical_call_index': call['logical_call_index'],
                'reason': f'{where}: {len(attempts)} physical attempts exhausted; last {last["retry_reason"]}'}
    if (last['http_status'] != 200 or last['returned_model'] != slot['model'] or
            (last['observed_selected_provider'] or '').strip().casefold() != slot['provider_order'][0] or
            (call['failure_reason'] or '').startswith(('Malformed usage', 'Missing routing', 'API error'))):
        return {'kind': CONTRACT, 'logical_call_index': call['logical_call_index'],
                'reason': f'{where}: {call["failure_reason"]}'}
    return None


async def collect(inputs, key, output, *, client_factory=httpx.AsyncClient, sleep=asyncio.sleep, protocol='v1'):
    """protocol selects the qualification procedure this NEW collection is recorded under (native
    Protocol-v1 or Protocol-v2 execution of a candidate not previously qualified under any protocol);
    it must match the protocol `inputs` was itself loaded under. It never changes the generation task:
    the same frozen fixtures, prompt, input/output contract and execution package are used either way
    (docs/generator-qualification.md Sec. 14). Defaults to 'v1', so every existing call site producing
    historical evidence is unaffected.
    """
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    require(not git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=none'),
            'Official execution requires a clean worktree')
    git('ls-files', '--error-unmatch', *SOURCES)
    for slot in inputs['slots']:
        slot_capability_gate(inputs['profile'], slot)
    # Recheck frozen bytes immediately before any side effect, under the same protocol as `inputs`.
    fresh = load_inputs(profile=inputs['profile'], slot=inputs.get('selected_slot'), protocol=protocol)
    require(fresh['provenance'] == inputs['provenance'], 'Source/input changed since preflight')
    require(fresh['provenance']['implementation']['status'] == FROZEN,
            f'Qualification implementation {NOT_FROZEN}; live execution refused')
    inputs = fresh
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    result = {'procedure_version': PROTOCOLS[protocol]['procedure'], 'status': 'PENDING_MANUAL_AUDIT',
              'provenance': inputs['provenance'],
              'planned_logical_calls': len(inputs['slots']) * len(inputs['fixtures']),
              'candidates': {s['logical_call_id']: 'CANDIDATE' for s in inputs['slots']},
              'failure_reason': None, 'invalidation': None, 'calls': []}
    hashes = {}
    try:
        async with client_factory(trust_env=False, follow_redirects=False) as client:
            for index, (slot, truth, entry) in enumerate(plan(inputs), 1):
                body = request(inputs, slot, truth)
                call = await probe.probe_call(client, inputs['bundle'], slot, key, sleep=sleep,
                    request_factory=lambda *_: body)
                call.pop('semantic_qualification', None)
                call.update(candidate=slot['logical_call_id'], fixture_id=entry['fixture_id'],
                            fixture_sha256=entry['sha256'], projection_sha256=entry['projection_sha256'],
                            logical_call_index=index, provenance=inputs['provenance'])
                call['automated'] = deepcopy(TERMINAL_AUTOMATED)
                if call['status'] == 'PASS':
                    output_text = call['attempts'][-1]['parsed_structured_response']
                    call['automated'] = semantic_check(truth, output_text)
                    call['output_sha256'] = probe.digest(probe.canonical(output_text).encode())
                relative = evidence_path(slot, entry)
                path = directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                hashes[relative] = publish(path, call, key)
                result['calls'].append(probe.redact(call, key))
                # Candidate output/semantic failures are evidence and continue. Infrastructure retry
                # exhaustion or an execution-contract defect invalidates the whole attempt: stop here,
                # keep collected evidence, mark no candidate FAIL, and never rerun automatically.
                invalid = invalidation(call, slot)
                if invalid:
                    result.update(status='INVALIDATED', failure_reason=invalid['reason'], invalidation=invalid)
                    break
    except Exception as exc:
        reason = f'Execution/runner defect: {type(exc).__name__}: {exc}'
        result.update(status='INVALIDATED', failure_reason=reason,
                      invalidation={'kind': RUNNER, 'logical_call_index': None, 'reason': reason})
    hashes['qualification.json'] = publish(directory / 'qualification.json', result, key)
    hashes['manual-audit.json'] = publish(directory / 'manual-audit.json',
        audit_template(result, hashes['qualification.json'], inputs['slots'], protocol), key)
    with (directory / 'SHA256SUMS').open('x', encoding='utf-8') as stream:
        for name, checksum in sorted(hashes.items()):
            stream.write(f'{checksum}  {name}\n')
    return result


def evidence_path(slot, entry):
    return f'outputs/{slot["logical_call_id"].lower()}/{entry["fixture_id"]}.json'


def read_sums(directory):
    sums = {}
    for line in (directory / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        match = SUMS_LINE.fullmatch(line)
        require(match is not None, 'Malformed checksum line')
        checksum, name = match.groups()
        parts = Path(name).parts
        require(not Path(name).is_absolute() and '..' not in parts and '\\' not in name
                and parts[0] != 'SHA256SUMS', 'Unsafe checksum path')
        require(name not in sums, 'Duplicate checksum path')
        sums[name] = checksum
    return sums


def replay(directory, inputs):
    """Validate archived evidence, then reproduce execution and semantic gates offline."""
    directory = Path(directory)
    sums = read_sums(directory)
    present = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    require(present == {*sums, 'SHA256SUMS'}, 'Unlisted or missing evidence files')
    for name, checksum in sums.items():
        require(probe.file_hash(directory / name) == checksum, 'Evidence checksum mismatch')
    result = fixtures.read(directory / 'qualification.json')
    probe.fields(result, ['procedure_version', 'status', 'provenance', 'planned_logical_calls',
                          'candidates', 'failure_reason', 'invalidation', 'calls'])
    # Either a native Protocol-v1 or Protocol-v2 collection (Sec. 14); the provenance-drift check
    # below ties this to whichever protocol the caller's `inputs` was itself loaded under.
    require(result['procedure_version'] in (PROCEDURE_V1, PROCEDURE_V2)
            and result['status'] in ('PENDING_MANUAL_AUDIT', 'INVALIDATED'), 'Unknown attempt procedure/status')
    implied = [invalidation(c, s) for c, (s, _, _) in zip(result['calls'], plan(inputs))]
    if result['status'] == 'INVALIDATED':
        invalid = result['invalidation']
        require(type(invalid) is dict and invalid.get('reason') == result['failure_reason'], 'Invalidation record')
        if invalid['kind'] == RUNNER:
            consistent = invalid['logical_call_index'] is None and not any(implied)
        else:  # A call-level invalidation is the final archived call: nothing ran after it.
            consistent = bool(implied) and invalid == implied[-1] and not any(implied[:-1])
        require(consistent, 'Invalidation inconsistent with archived calls')
    else:
        require(result['invalidation'] is None and result['failure_reason'] is None
                and not any(implied), 'Attempt should have been invalidated')
    expected_calls = len(inputs['slots']) * len(inputs['fixtures'])
    require(result['planned_logical_calls'] == expected_calls and
            result['candidates'] == {s['logical_call_id']: 'CANDIDATE' for s in inputs['slots']}, 'Attempt header drift')
    for key in ('fixture_set_commit', 'fixture_manifest_sha256', 'execution_config_sha256', 'contract_sha256',
                'prompt_sha256', 'output_schema_sha256', 'procedure_version', *probe.VERSIONS):
        require(result['provenance'][key] == inputs['provenance'][key], 'Archived provenance drift')
    # The implementation may legitimately be re-frozen after this attempt; verify the archive's own
    # claim against git history rather than requiring it to match the current live computation.
    require(result['provenance']['implementation']['status'] == FROZEN, 'Attempt ran without implementation freeze')
    verify_archived_implementation(result['provenance']['implementation'])
    require(len(result['calls']) <= expected_calls, 'Unexpected calls')
    if result['status'] != 'INVALIDATED':
        require(len(result['calls']) == expected_calls, 'Incomplete attempt')
    planned = plan(inputs)
    require(sums.keys() == {'qualification.json', 'manual-audit.json',
                            *(evidence_path(s, e) for s, _, e in planned[:len(result['calls'])])},
            'Unexpected or missing evidence checksums')
    for index, (call, (slot, truth, entry)) in enumerate(zip(result['calls'], planned), 1):
        require(call['candidate'] == slot['logical_call_id'] and call['fixture_id'] == entry['fixture_id']
                and call['logical_call_index'] == index and call['fixture_sha256'] == entry['sha256']
                and call['projection_sha256'] == entry['projection_sha256']
                and call['provenance'] == result['provenance'], 'Call provenance/order mismatch')
        require(fixtures.read(directory / evidence_path(slot, entry)) == call, 'Call archive mismatch')
        body = request(inputs, slot, truth)
        require(call['request_body'] == body and call['wire_request'] == probe.canonical(body)
                and call['wire_request_sha256'] == probe.digest(probe.canonical(body).encode()), 'Request drift')
        require(1 <= len(call['attempts']) <= 3, 'Physical attempt count')
        require(call['status'] in ('PASS', 'FAIL'), 'Unknown call status')
        last = deepcopy(call['attempts'][-1])
        if call['status'] == 'PASS':
            require(last['http_status'] == 200, 'HTTP failure')
            envelope = probe.parse_json(last['raw_response'])
            probe.response_evidence(last, envelope)
            probe.inspect_response(last, envelope, body)
            output_text = last['parsed_structured_response']
            require(semantic_check(truth, output_text) == call['automated'], 'Automated findings drift')
            require(probe.digest(probe.canonical(output_text).encode()) == call['output_sha256'], 'Output drift')
            continue
        # A terminal failure stays terminal: fixed failure record, no output identity, and the
        # archived response (when one was received) must still fail the same gates offline.
        require(call['automated'] == TERMINAL_AUTOMATED and 'output_sha256' not in call, 'Terminal failure altered')
        if last['http_status'] == 200 and last['raw_response'] is not None:
            try:
                envelope = probe.parse_json(last['raw_response'])
                probe.response_evidence(last, envelope)
                probe.inspect_response(last, envelope, body)
            except (ValueError, TypeError, KeyError):
                pass
            else:
                raise ValueError('Archived terminal failure now passes; evidence altered')
    require(fixtures.read(directory / 'manual-audit.json')
            == audit_template(result, sums['qualification.json'], inputs['slots'],
                              archive_protocol(result['procedure_version'])),
            'Archived blank audit template drift')
    return result, sums['qualification.json']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-spend', action='store_true')
    parser.add_argument('--profile', choices=sorted(probe.PROFILES), default='primary',
                        help='primary (CLOSED Attempt-01, FAIL/FAIL), the predeclared fallback (Terra/Opus), '
                             'or the frozen second-level G2 candidate (second_level_g2, one G2 slot)')
    parser.add_argument('--slot', choices=['G1', 'G2'], default=None,
                        help='Restrict Generator Qualification to one candidate slot (12 calls); '
                             'omit for the full profile (historical 24-call behavior, unchanged default)')
    parser.add_argument('--output-directory', type=Path, default=None)
    parser.add_argument('--attempt', type=Path, help='Offline replay/adjudication of archived attempt')
    parser.add_argument('--audit', type=Path, help='Completed copy of generated manual-audit.json '
                        '(a v1 audit for --v2-mapping-output; v1 or v2 per --protocol-version otherwise)')
    parser.add_argument('--adjudication-output', type=Path, help='New immutable offline adjudication JSON')
    parser.add_argument('--protocol-version', choices=['v1', 'v2'], default=None,
                        help='For --execute/preview: the qualification procedure a NEW collection is recorded '
                             'under (default v1; same generation task either way). For --audit/'
                             '--adjudication-output: the manual-audit schema and adjudication rules for --audit '
                             '(default: the protocol recorded in the archived attempt).')
    parser.add_argument('--v2-mapping-output', type=Path,
                        help='Derive an offline Protocol-v2 audit template from a COMPLETED v1 --audit '
                             '(docs/generator-qualification.md Sec. 14); writes here instead of adjudicating')
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    if any((args.attempt, args.audit, args.adjudication_output, args.v2_mapping_output)):
        if args.adjudication_output and args.v2_mapping_output:
            parser.error('--adjudication-output and --v2-mapping-output are separate offline modes; use only one')
        if args.execute:
            parser.error('Offline operations require no execution flags')
        if args.adjudication_output and not (args.attempt and args.audit):
            parser.error('Offline adjudication requires --attempt, --audit, --adjudication-output')
        if args.v2_mapping_output and not (args.attempt and args.audit):
            parser.error('Offline v1->v2 mapping requires --attempt, --audit, --v2-mapping-output')
        if not args.adjudication_output and not args.v2_mapping_output:
            parser.error('--attempt/--audit alone requires either --adjudication-output or --v2-mapping-output')
    output_directory = args.output_directory
    if output_directory is None:
        if args.slot is not None or args.profile == 'second_level_g2':
            # Single-slot runs have no default result path, so execution needs an explicit
            # --output-directory. second_level_g2 has a single slot.
            if args.execute:
                parser.error('Single-slot execution requires an explicit --output-directory; no '
                             'official single-slot result-path convention exists yet')
            output_directory = 'OPEN: official single-slot result-path identity not yet decided'
        else:
            output_directory = DEFAULT_OUTPUT if args.profile == 'primary' else FALLBACK_DEFAULT_OUTPUT
    if args.attempt and args.v2_mapping_output:
        # The mapping source must be a v1 collection; a v2 archive is rejected by derive_v2_audit_template.
        attempt = args.attempt.resolve()
        inputs = load_inputs(profile=args.profile, slot=args.slot, protocol=archived_protocol(attempt))
        for path in (args.audit, args.v2_mapping_output):
            require(not path.resolve().is_relative_to(attempt),
                    'Completed v1 audit and v2 mapping output must be separate copies outside the archived attempt')
        result, checksum = replay(attempt, inputs)
        v2_template, pending = derive_v2_audit_template(result, checksum, fixtures.read(args.audit), inputs['slots'])
        output = {'v2_audit_template': v2_template, 'pending_reclassification': pending}
        publish(args.v2_mapping_output, output)
        print(json.dumps(output, indent=2))
        return 0
    if args.attempt and args.adjudication_output:
        # Inputs load under the protocol the attempt was collected with. The audit rules default to that
        # protocol; --protocol-version overrides them (a v1 archive adjudicated with a mapped v2 audit).
        attempt = args.attempt.resolve()
        archive = archived_protocol(attempt)
        inputs = load_inputs(profile=args.profile, slot=args.slot, protocol=archive)
        for path in (args.audit, args.adjudication_output):
            require(not path.resolve().is_relative_to(attempt),
                    'Completed audit and adjudication must be separate copies outside the archived attempt')
        result, checksum = replay(attempt, inputs)
        verdict = adjudicate(result, fixtures.read(args.audit), checksum, inputs['slots'],
                             protocol=args.protocol_version or archive)
        verdict['manual_audit_file_sha256'] = probe.file_hash(args.audit)
        publish(args.adjudication_output, verdict)
        print(json.dumps(verdict, indent=2))
        return 0
    # Preview and collection: the protocol a new collection is recorded under. It does not change
    # the generation task (same fixtures, prompt, contract and execution package).
    protocol = args.protocol_version or 'v1'
    inputs = load_inputs(profile=args.profile, slot=args.slot, protocol=protocol)
    if not args.execute:
        print(json.dumps(preview(inputs, output_directory), indent=2))
        return 0
    key = os.environ.get('OPENROUTER_API_KEY', '')
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    require(inputs['provenance']['implementation']['status'] == FROZEN,
            f'Qualification implementation {NOT_FROZEN}; live execution refused')
    result = asyncio.run(collect(inputs, key, output_directory, protocol=protocol))
    print(result['status'] + ': qualification requires completed manual adjudication')
    return 1 if result['status'] == 'INVALIDATED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
