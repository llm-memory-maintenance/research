"""CRST Small Pilot naturalization: gated live construction (step B) and offline audit (step C).

The default invocation is an offline preview. Live construction needs --execute, --confirm-spend, the frozen
--output-directory and OPENROUTER_API_KEY. --audit is offline. Each unit is one Low/Medium/High triplet under its
preassigned generator, with at most three logical attempts; every attempt is archived separately.
"""
import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path

import httpx

import crst_policies as pol
import probe_generators as probe
import qualify_generators as q
import run_crst_pilot as run
import validate_crst_pilot_material as material
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
CONFIG = run.CONFIG_PATH
COLLECTION = 'crst-pilot-naturalization/1.0.0'
AUDIT = 'crst-pilot-naturalization-audit/1.0.0'
REVIEW = 'crst-pilot-naturalization-review/1.0.0'
NAMESPACE = 'results/crst-small-pilot'
IMPLEMENTATION = ('experiments/naturalize_crst_pilot.py', 'experiments/run_crst_pilot.py',
                  'experiments/crst_policies.py', 'experiments/crst_prompts.py', 'experiments/crst_scoring.py',
                  'experiments/validate_crst_pilot_material.py', 'configs/crst-small-pilot.yaml')
STOP = 'NATURALIZATION STOPPED; STOP FOR RESEARCHER DECISION'
require = gq.require


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, check=True).stdout


def load_inputs(path=CONFIG, *, full_separation=False):
    config = run.load_config(path)
    run.verify_config(config)
    manifest, fixtures = material.validate_directory(longmemeval=full_separation)
    nat = config['naturalization']
    require(probe.file_hash(ROOT / nat['contract_path']) == nat['contract_sha256'] == q.CONTRACT_HASH
            and nat['prompt_sha256'] == q.PROMPT_HASH and nat['output_schema_sha256'] == q.SCHEMA_HASH
            and {k: nat[k] for k in probe.VERSIONS} == probe.VERSIONS, 'Naturalization contract drift')
    by_scenario = {f['fixture_id']: f for f in fixtures}
    generators = []
    for entry in nat['generators']:
        profile = probe.PROFILES[entry['execution_profile']]
        package = ROOT / entry['execution_package_path']
        require(Path(profile['config_path']) == package and probe.file_hash(package)
                == entry['execution_package_sha256'] == q.PACKAGE_HASHES[entry['execution_profile']],
                'Execution package drift')
        slot = next((s for s in profile['slots'] if s['logical_call_id'] == entry['logical_call_id']
                     and s['model'] == entry['model'] and s['provider_order'] == entry['provider_order']), None)
        require(slot is not None, 'Planned generator is not a declared execution slot')
        q.slot_capability_gate(entry['execution_profile'], slot)
        evidence = ROOT / entry['qualification_evidence_path']
        require(probe.file_hash(evidence) == entry['qualification_evidence_sha256']
                and gq.read(evidence)['candidates'].get(entry['logical_call_id']) == 'QUALIFIED',
                'Generator qualification evidence mismatch')
        bundle = probe.load_bundle(profile['config_path'], slots=profile['slots'], status=profile['status'],
                                   capability_result=profile['capability_result'],
                                   successful_attempt=profile['successful_attempt'],
                                   execution_package=profile['execution_package'],
                                   execution_compatibility=profile['execution_compatibility'])
        require(bundle['provenance']['prompt_sha256'] == nat['prompt_sha256']
                and bundle['provenance']['output_schema_sha256'] == nat['output_schema_sha256'], 'Prompt drift')
        generators.append({'entry': entry, 'slot': slot, 'bundle': bundle,
                           'fixture': by_scenario[entry['scenario_id']]})
    require(len(generators) == len(fixtures) == 2, 'Planned unit count drift')
    return {'config': config, 'path': Path(path), 'manifest': manifest, 'fixtures': fixtures,
            'generators': generators}


def request(generator):
    payload = gq.project(generator['fixture'])
    return probe.request_body(dict(generator['bundle'], input=payload), generator['slot'],
                              input_validator=gq.validate_input)


def request_sha(generator):
    return probe.digest(probe.canonical(request(generator)).encode())


def relative_attempt(generator, number):
    return f'{generator["entry"]["scenario_id"]}/attempt-{number:02d}.json'


def relative_unit(generator):
    return f'{generator["entry"]["scenario_id"]}/unit.json'


def result_directory(config):
    return ROOT / config['naturalization']['result_directory']


def preview(inputs):
    nat, cap = inputs['config']['naturalization'], inputs['config']['naturalization']['max_logical_attempts_per_unit']
    units = []
    for index, g in enumerate(inputs['generators'], 1):
        entry = g['entry']
        projection = gq.sha(gq.canonical(gq.project(g['fixture'])))
        units.append({'unit_index': index, 'unit': f'naturalize/{entry["scenario_id"]}',
                      'scenario_id': entry['scenario_id'], 'generator': entry['logical_call_id'],
                      'model': entry['model'], 'provider_order': entry['provider_order'],
                      'allow_fallbacks': False, 'max_logical_attempts': cap,
                      'input_sha256': projection, 'request_sha256': request_sha(g),
                      'attempt_paths': [f'{nat["result_directory"]}/{relative_attempt(g, n)}'
                                        for n in range(1, cap + 1)]})
    return {'status': 'NETWORK_DISABLED', 'credits': 'CREDITS_NOT_SPENT', 'step': 'B live naturalization',
            'planned_units': len(units), 'max_logical_calls': len(units) * cap,
            'result_directory': nat['result_directory'], 'audit_directory': nat['audit_directory'],
            'contract_sha256': nat['contract_sha256'], 'prompt_sha256': nat['prompt_sha256'],
            'output_schema_sha256': nat['output_schema_sha256'],
            'material_manifest_sha256': inputs['config']['material']['manifest_sha256'],
            'order': nat['execution']['order'], 'units': units,
            'stop_rules': {'terminal_failure': 'retry the same unit up to the cap, then UNBUILDABLE',
                           'level_1_semantic_failure': 'stop; no automatic regeneration',
                           'fluency_only': 'no regeneration'}}


def guard_output(output, config, root=ROOT):
    """Inside results/crst-small-pilot only the planned naturalization directory may be written."""
    target, official = Path(output).resolve(), (root / NAMESPACE).resolve()
    if target == official or official in target.parents:
        require(target == result_directory(config).resolve(),
                'Only the planned naturalization directory may be written; existing evidence is immutable')


def provenance(inputs):
    config, nat = inputs['config'], inputs['config']['naturalization']
    return {'source_commit': git('rev-parse', 'HEAD').decode().strip(),
            'config_sha256': probe.file_hash(inputs['path']),
            'material_manifest_sha256': config['material']['manifest_sha256'],
            'contract_sha256': nat['contract_sha256'], 'prompt_sha256': nat['prompt_sha256'],
            'output_schema_sha256': nat['output_schema_sha256'], **{k: nat[k] for k in probe.VERSIONS},
            'generators': [{k: g['entry'][k] for k in ('logical_call_id', 'scenario_id', 'model', 'provider_order',
                                                       'execution_package_sha256')} for g in inputs['generators']],
            'request_sha256': [request_sha(g) for g in inputs['generators']],
            'implementation': {path: probe.file_hash(ROOT / path) for path in IMPLEMENTATION},
            'qualification_implementation': q.implementation('v2'), 'python': platform.python_version(),
            'packages': {n: importlib.metadata.version(n) for n in ('httpx', 'pydantic', 'pyyaml')}}


def attempt_outcome(call, fixture):
    """Terminal non-evaluable failure, or an evaluable output judged by the frozen deterministic check."""
    if call['status'] != 'PASS':
        return 'TERMINAL_FAILURE', None
    try:
        audit = run.naturalization_audit(fixture, call['attempts'][-1]['parsed_structured_response'])
    except ValueError:
        return 'TERMINAL_FAILURE', None
    return ('EVALUABLE_LEVEL1_FAILURE' if audit['status'] == 'FAIL' else 'EVALUABLE_PASS'), audit


async def collect(inputs, key, output, *, client_factory=httpx.AsyncClient, sleep=asyncio.sleep):
    """One naturalization collection. Units run in plan order; only a terminal non-evaluable failure retries."""
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    require(not git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=none'),
            'Execution requires a clean worktree')
    git('ls-files', '--error-unmatch', *IMPLEMENTATION, 'data/crst-small-pilot/manifest.json')
    guard_output(output, inputs['config'])
    fresh = load_inputs(inputs['path'], full_separation=True)
    fresh_provenance = provenance(fresh)
    require(fresh_provenance == provenance(inputs), 'Source/input changed since preflight')
    require(fresh_provenance['qualification_implementation']['status'] == q.FROZEN,
            f'Qualification implementation {q.NOT_FROZEN}; live execution refused')
    inputs = fresh
    cap = inputs['config']['naturalization']['max_logical_attempts_per_unit']
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    result = {'procedure_version': COLLECTION, 'status': 'STOPPED', 'provenance': fresh_provenance,
              'planned_units': len(inputs['generators']), 'max_logical_attempts_per_unit': cap,
              'failure_reason': None, 'units': []}
    hashes = {}
    try:
        async with client_factory(trust_env=False, follow_redirects=False) as client:
            for generator in inputs['generators']:
                outcomes, accepted = [], None
                while True:
                    decision = run.naturalization_next(outcomes, cap)
                    if decision not in ('ATTEMPT', 'RETRY_SAME_UNIT'):
                        break
                    number = len(outcomes) + 1
                    body = request(generator)
                    call = await probe.probe_call(client, generator['bundle'], generator['slot'], key, sleep=sleep,
                                                  request_factory=lambda *_, body=body: body)
                    outcome, audit = attempt_outcome(call, generator['fixture'])
                    call.pop('semantic_qualification', None)
                    call.update(scenario_id=generator['entry']['scenario_id'], unit_attempt=number,
                                outcome=outcome, semantic_check=audit)
                    if call['status'] == 'PASS':
                        call['output_sha256'] = probe.digest(probe.canonical(
                            call['attempts'][-1]['parsed_structured_response']).encode())
                    relative = relative_attempt(generator, number)
                    (directory / relative).parent.mkdir(parents=True, exist_ok=True)
                    hashes[relative] = q.publish(directory / relative, call, key)
                    outcomes.append(outcome)
                    if outcome == 'EVALUABLE_PASS':
                        accepted = number
                unit = {'scenario_id': generator['entry']['scenario_id'], 'generator': generator['entry']['model'],
                        'outcomes': outcomes, 'decision': decision, 'accepted_attempt': accepted
                        if decision.startswith('ACCEPT') else None, 'logical_attempts': len(outcomes)}
                hashes[relative_unit(generator)] = q.publish(directory / relative_unit(generator), unit, key)
                result['units'].append(unit)
                if not decision.startswith('ACCEPT'):
                    result['failure_reason'] = f'{unit["scenario_id"]}: {decision}; {STOP}'
                    break
            else:
                result['status'] = 'COMPLETE'
    except Exception as exc:
        result['failure_reason'] = f'Execution/runner defect: {type(exc).__name__}: {exc}; {STOP}'
    hashes['collection.json'] = q.publish(directory / 'collection.json', result, key)
    with (directory / 'SHA256SUMS').open('x', encoding='utf-8') as stream:
        for name, checksum in sorted(hashes.items()):
            stream.write(f'{checksum}  {name}\n')
    return result


def verified_collection(directory):
    """Checksum-verified collection.json of an archived naturalization directory."""
    directory = Path(directory)
    sums = q.read_sums(directory)
    for name, checksum in sums.items():
        require(probe.file_hash(directory / name) == checksum, f'Archived file drifted: {name}')
    require('collection.json' in sums, 'Missing collection record')
    return json.loads((directory / 'collection.json').read_text(encoding='utf-8')), sums


def accepted_outputs(directory, inputs):
    """{scenario_id: (attempt record, parsed triplet)} of the accepted attempt of each unit; verified."""
    collection, sums = verified_collection(directory)
    require(collection['status'] == 'COMPLETE' and [u['scenario_id'] for u in collection['units']]
            == [g['entry']['scenario_id'] for g in inputs['generators']], 'Naturalization is not complete')
    out = {}
    for generator, unit in zip(inputs['generators'], collection['units']):
        require(unit['decision'].startswith('ACCEPT') and 1 <= unit['logical_attempts'] <= 3
                and unit['accepted_attempt'] == unit['logical_attempts'], 'Unit was not accepted')
        record = json.loads((Path(directory) / relative_attempt(generator, unit['accepted_attempt'])).read_text(
            encoding='utf-8'))
        require(record['status'] == 'PASS' and record['scenario_id'] == generator['entry']['scenario_id']
                and record['logical_call_id'] == generator['entry']['logical_call_id'],
                'Accepted attempt identity mismatch')
        parsed = record['attempts'][-1]['parsed_structured_response']
        probe.validate_output(parsed)
        out[generator['entry']['scenario_id']] = (record, parsed)
    return out


def naturalized_texts(outputs):
    """{scenario_id: {variant: {event: text, 'Q': text}}} from verified accepted outputs."""
    return {scenario: {variant: dict(parsed[variant]) for variant in gq.VARIANTS}
            for scenario, (_, parsed) in outputs.items()}


def audit(directory, inputs, tokenizer, review=None):
    """Step C: structural and deterministic semantic audit, B0 coverage, and researcher-review binding."""
    directory = Path(directory)
    collection, sums = verified_collection(directory)
    outputs = accepted_outputs(directory, inputs)
    units, findings = [], {}
    eligible_coverage = True
    for generator in inputs['generators']:
        scenario = generator['entry']['scenario_id']
        record, parsed = outputs[scenario]
        semantic = run.naturalization_audit(generator['fixture'], parsed)
        coverage = {}
        for variant in gq.VARIANTS:
            texts = {label: parsed[variant][label] for label in pol.EVENT_ORDER}
            try:
                coverage[variant] = {'status': 'RETAINED', **run.b0_coverage_report(texts, tokenizer)}
            except pol.CoverageFailure:
                coverage[variant] = {'status': 'COVERAGE_FAILURE', 'budget': pol.B0_CONTEXT_TOKENS}
                eligible_coverage = False
        for finding in semantic['findings']:
            findings[f'{scenario}/{finding["id"]}'] = finding
        units.append({'scenario_id': scenario, 'generator': generator['entry']['model'],
                      'accepted_attempt': next(u for u in collection['units']
                                               if u['scenario_id'] == scenario)['accepted_attempt'],
                      'output_sha256': record['output_sha256'], 'semantic_status': semantic['status'],
                      'finding_ids': [f'{scenario}/{f["id"]}' for f in semantic['findings']],
                      'b0_coverage': coverage})
    semantic_status = ('FAIL' if any(u['semantic_status'] == 'FAIL' for u in units) else
                       'MANUAL_REVIEW_REQUIRED' if findings else 'PASS')
    review_sha, decisions = None, None
    if review is not None:
        review_path = Path(review)
        payload = json.loads(review_path.read_text(encoding='utf-8'))
        require(set(payload) == {'schema_version', 'collection_sha256', 'finding_decisions'}
                and payload['schema_version'] == REVIEW
                and payload['collection_sha256'] == probe.file_hash(directory / 'collection.json')
                and set(payload['finding_decisions']) == set(findings)
                and set(payload['finding_decisions'].values()) <= {'ACCEPT', 'REJECT'},
                'The review must cover exactly the audited findings for this collection')
        review_sha, decisions = probe.file_hash(review_path), payload['finding_decisions']
    if semantic_status == 'FAIL' or not eligible_coverage:
        status = 'NOT_ELIGIBLE'
    elif semantic_status == 'PASS':
        status = 'ELIGIBLE'
    elif decisions is None:
        status = 'PENDING_RESEARCHER_REVIEW'
    else:
        status = 'ELIGIBLE' if set(decisions.values()) == {'ACCEPT'} else 'NOT_ELIGIBLE'
    return {'schema_version': AUDIT, 'collection_sha256': probe.file_hash(directory / 'collection.json'),
            'sha256sums_sha256': probe.file_hash(directory / 'SHA256SUMS'), 'files': sums, 'status': status,
            'semantic_status': semantic_status, 'b0_budget': pol.B0_CONTEXT_TOKENS, 'units': units,
            'findings': findings, 'review_sha256': review_sha, 'finding_decisions': decisions,
            'source_commit': collection['provenance']['source_commit'],
            'note': 'Deterministic checks are not semantic qualification; fluency-only findings never regenerate.'}


def load_eligible(audit_path, directory, inputs):
    """Texts of an ELIGIBLE audit bound to the current, checksum-verified collection; otherwise refuse."""
    record = json.loads(Path(audit_path).read_text(encoding='utf-8'))
    require(record.get('schema_version') == AUDIT and record['status'] == 'ELIGIBLE',
            'The naturalization audit is not ELIGIBLE')
    collection, _ = verified_collection(directory)
    require(record['collection_sha256'] == probe.file_hash(Path(directory) / 'collection.json')
            and record['sha256sums_sha256'] == probe.file_hash(Path(directory) / 'SHA256SUMS'),
            'The audit does not belong to this collection')
    outputs = accepted_outputs(directory, inputs)
    for unit in record['units']:
        require(outputs[unit['scenario_id']][0]['output_sha256'] == unit['output_sha256'], 'Audited output drifted')
    return naturalized_texts(outputs), record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-spend', action='store_true')
    parser.add_argument('--output-directory', type=Path, default=None)
    parser.add_argument('--audit', type=Path, help='Offline audit of a naturalization directory')
    parser.add_argument('--audit-output', type=Path, help='New immutable audit record for --audit')
    parser.add_argument('--review', type=Path, help='Researcher review of audited findings')
    parser.add_argument('--tokenizer-directory', type=Path, default=None)
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    if args.audit or args.audit_output:
        if not (args.audit and args.audit_output) or args.execute or args.output_directory:
            parser.error('Audit requires --audit and --audit-output and no execution flags')
        import calibrate_b0_suffix as suffix
        tokenizer, _ = suffix.load_reader_tokenizer(args.tokenizer_directory)
        record = audit(args.audit, load_inputs(args.config, full_separation=True), tokenizer, args.review)
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        checksum = q.publish(args.audit_output, record)
        print(f'{record["status"]}: semantic {record["semantic_status"]}; audit SHA-256: {checksum}')
        return 0 if record['status'] == 'ELIGIBLE' else 1
    inputs = load_inputs(args.config)
    if not args.execute:
        if args.output_directory is not None:
            parser.error('--output-directory is used only with --execute')
        print(json.dumps(preview(inputs), indent=2, ensure_ascii=False))
        return 0
    if args.output_directory is None:
        parser.error('Execution requires an explicit --output-directory')
    require(args.output_directory.resolve() == result_directory(inputs['config']).resolve(),
            'Execution writes only to the frozen result directory')
    result = asyncio.run(collect(inputs, os.environ.get('OPENROUTER_API_KEY', ''), args.output_directory))
    print(f'{result["status"]}: {len(result["units"])} of {result["planned_units"]} units recorded')
    return 0 if result['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
