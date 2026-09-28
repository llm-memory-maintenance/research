"""B0 suffix-only calibration: naturalize only U7 and N2, audit them, then derive the exact-maximum budget.

The default invocation is an offline preview. Live collection needs --execute, --confirm-spend, the planned
--output-directory and OPENROUTER_API_KEY. --audit-template, --adjudicate and --derive-budget are the offline
post-collection steps, in that order. The full-history procedure (calibrate_b0.py) is closed.
"""
import argparse
import asyncio
import contextlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
from typing import Literal
from unittest import mock

import httpx
import yaml

import b0_window as window
import calibrate_b0 as cal
import calibrate_retrieval as retrieval
import probe_generators as probe
import qualify_generators as q
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
CONFIG = ROOT / 'configs/b0-suffix-calibration.yaml'
SCHEMA = 'b0-suffix-calibration/1.0.0'
COLLECTION = 'b0-suffix-collection/1.0.0'
AUDIT = 'b0-suffix-audit/1.0.0'
ADJUDICATION = 'b0-suffix-adjudication/1.0.0'
DERIVATION = 'b0-suffix-budget-derivation/1.0.0'
ELIGIBILITY_FIELDS = ('schema_version', 'attempt', 'collection_sha256', 'items_audited', 'status',
                      'level1_failure_count', 'level1_failures', 'budget_derivation', 'b0_context_tokens')
LEVEL1 = {
    'U7': {'entity_fidelity': 'automated', 'attribute_fidelity': 'manual', 'current_value_fidelity': 'automated',
           'changed_state_semantics': 'manual', 'no_superseded_value': 'automated',
           'no_invented_value_or_change': 'manual', 'comprehensibility': 'manual'},
    'N2': {'entity_fidelity': 'automated', 'attribute_fidelity': 'manual', 'current_value_fidelity': 'automated',
           'same_state_semantics': 'manual', 'no_invented_change': 'manual',
           'no_historical_or_superseded_value': 'automated', 'comprehensibility': 'manual'},
}
EVENTS = ('U7', 'N2')
OLD_NAMESPACE = 'results/b0-calibration'
NAMESPACE = 'results/b0-suffix-calibration'
IMPLEMENTATION = ('experiments/calibrate_b0_suffix.py', 'experiments/calibrate_b0.py', 'experiments/b0_window.py',
                  'experiments/validate_b0_calibration_material.py')
POLICY_STATUSES = ('PROPOSED_PENDING_RESEARCHER_APPROVAL', 'FROZEN')
ATTEMPT_STATUSES = ('PLANNED_NOT_EXECUTED', 'CLOSED_INCOMPLETE', 'COMPLETE')
CLOSED = 'B0 suffix calibration is closed and its budget is frozen; no further attempt or derivation is allowed'
STOP = 'ATTEMPT CLOSED INCOMPLETE; STOP FOR RESEARCHER DECISION'
require = gq.require


class Fact(gq.Strict):
    entity_id: gq.Text
    attribute_id: gq.Text
    current_value: gq.Text
    semantics: Literal['changed_state', 'same_state']


class SuffixVariant(gq.Strict):
    U7: Fact
    N2: Fact


class SuffixVariants(gq.Strict):
    low: SuffixVariant
    medium: SuffixVariant
    high: SuffixVariant


class SuffixInput(gq.Strict):
    scenario_id: gq.Text
    domain: Literal[gq.DOMAINS]
    entities: list[gq.Entity]
    attributes: list[gq.Attribute]
    variants: SuffixVariants


# --- Input projection ------------------------------------------------------------------------------

def facts(fixture):
    """The U7 and N2 facts of each variant, read from the reference events (entity and attribute by state key)."""
    r = fixture['reference']
    keys = {k['state_key']: k for k in r['state_keys']}
    result = {}
    for variant in gq.VARIANTS:
        events = {e['event']: e for e in r['variants'][variant]['events']}
        result[variant] = {label: {'entity_id': keys[events[label]['state_key']]['entity_id'],
                                   'attribute_id': keys[events[label]['state_key']]['attribute_id'],
                                   'current_value': events[label]['current_value'],
                                   'semantics': events[label]['semantics']} for label in EVENTS}
    return result


def projection(fixture):
    """Only what is needed to realize U7 and N2; no other event, state, previous value or answer."""
    r, variants = fixture['reference'], facts(fixture)
    used = [f for variant in variants.values() for f in variant.values()]
    entities = {f['entity_id'] for f in used}
    attributes = {f['attribute_id'] for f in used}
    return json.loads(gq.canonical({
        'scenario_id': fixture['fixture_id'], 'domain': r['domain'],
        'entities': [e for e in r['entities'] if e['entity_id'] in entities],
        'attributes': [a for a in r['attributes'] if a['attribute_id'] in attributes],
        'variants': variants}))


def validate_input(payload):
    SuffixInput.model_validate(payload)
    entities = {e['entity_id'] for e in payload['entities']}
    attributes = {a['attribute_id'] for a in payload['attributes']}
    require(len(entities) == len(payload['entities']) and len(attributes) == len(payload['attributes']),
            'Duplicate identity')
    used_entities, used_attributes = set(), set()
    for variant in gq.VARIANTS:
        u7, n2 = payload['variants'][variant]['U7'], payload['variants'][variant]['N2']
        require(u7['semantics'] == 'changed_state' and n2['semantics'] == 'same_state', 'Event semantics')
        require((u7['entity_id'], u7['attribute_id']) != (n2['entity_id'], n2['attribute_id']),
                'U7 and N2 name the same entity and attribute')
        for fact in (u7, n2):
            require(fact['entity_id'] in entities and fact['attribute_id'] in attributes, 'Unresolved identity')
            used_entities.add(fact['entity_id'])
            used_attributes.add(fact['attribute_id'])
    require(used_entities == entities and used_attributes == attributes, 'Irrelevant projected content')
    require(payload['variants']['low'] == payload['variants']['medium'] == payload['variants']['high'],
            'U7 and N2 facts differ across variants')


def verify_projection(fixture, payload):
    """The projection is deterministic and losslessly carries exactly the fixture's U7 and N2 facts.

    The fixture side is read directly from the reference events, independently of facts().
    """
    require(payload == projection(fixture) and gq.canonical(payload) == gq.canonical(projection(fixture)),
            'Projection is not the deterministic projection of the scenario')
    validate_input(payload)
    r = fixture['reference']
    entities = {e['entity_id']: e['name'] for e in r['entities']}
    attributes = {a['attribute_id']: a['meaning'] for a in r['attributes']}
    keys = {k['state_key']: k for k in r['state_keys']}
    from_fixture = {(variant, event['event'], entities[keys[event['state_key']]['entity_id']],
                     attributes[keys[event['state_key']]['attribute_id']], event['current_value'], event['semantics'])
                    for variant in gq.VARIANTS for event in r['variants'][variant]['events']
                    if event['event'] in EVENTS}
    names = {e['entity_id']: e['name'] for e in payload['entities']}
    meanings = {a['attribute_id']: a['meaning'] for a in payload['attributes']}
    from_payload = {(variant, label, names[f['entity_id']], meanings[f['attribute_id']], f['current_value'],
                     f['semantics']) for variant, events in payload['variants'].items() for label, f in events.items()}
    require(from_fixture == from_payload and len(from_payload) == 6, 'Projection loses or adds U7/N2 facts')


# --- Output contract -------------------------------------------------------------------------------

def validate_output(output):
    """Exactly low/medium/high, each exactly U7 and N2, both nonblank strings."""
    probe.fields(output, gq.VARIANTS)
    for variant in gq.VARIANTS:
        probe.fields(output[variant], EVENTS)
        for value in output[variant].values():
            probe.nonempty(value)


@contextlib.contextmanager
def suffix_output_contract():
    """The frozen transport validates every response with probe.validate_output; swap in this procedure's."""
    with mock.patch.object(probe, 'validate_output', validate_output):
        yield


def automated_checks(fixture, output):
    """Deterministic Level-1 checks per variant and event; they never stop collection and are never repaired."""
    r = fixture['reference']
    keys = {k['state_key']: k for k in r['state_keys']}
    name = next(e['name'] for e in r['entities'] if e['entity_id'] == keys['k_target']['entity_id'])
    target, hard = keys['k_target']['value_inventory'], keys['k_hard']['value_inventory']
    expected = {'U7': r['gold_current_value'], 'N2': keys['k_n2']['initial_value']}
    forbidden = {'U7': [*target[:-1], *hard], 'N2': [*target, *hard]}
    absence = {'U7': 'no_superseded_value', 'N2': 'no_historical_or_superseded_value'}
    result = {}
    for variant in gq.VARIANTS:
        result[variant] = {}
        for event in EVENTS:
            text = output[variant][event]
            checks = {'entity_fidelity': q.contains(text, name),
                      'current_value_fidelity': q.contains(text, expected[event]),
                      absence[event]: not any(q.contains(text, value) for value in forbidden[event])}
            result[variant][event] = {check: 'PASS' if ok else 'FAIL' for check, ok in checks.items()}
    return result


def summarize_checks(checks):
    failed = any(v == 'FAIL' for events in checks.values() for event in events.values() for v in event.values())
    return {'status': 'LEVEL1_FINDINGS' if failed else 'PASS', 'checks': checks,
            'meaning': 'Deterministic Level-1 checks; they never stop collection and are not semantic qualification.'}


# --- Configuration and inputs ----------------------------------------------------------------------

def load_config(path=CONFIG):
    config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    require(type(config) is dict and config.get('schema_version') == SCHEMA and config['status'] == 'PROCEDURE_FROZEN',
            'Unexpected B0 suffix calibration config')
    require(config['collection_rule']['status'] in POLICY_STATUSES
            and config['attempt_policy']['status'] in POLICY_STATUSES
            and config['semantic_eligibility']['status'] in POLICY_STATUSES, 'Policy status')
    require(config['semantic_eligibility']['level1_checks'] == LEVEL1, 'Level-1 check registry drift')
    attempts = config['results']['attempts']
    require(config['attempt_policy']['cap'] == 1 and [a['id'] for a in attempts] == ['attempt-01'],
            'Unexpected attempt list: exactly one attempt is allowed')
    for attempt in attempts:
        require(attempt['status'] in ATTEMPT_STATUSES
                and attempt['result_directory'] == f'{NAMESPACE}/{attempt["id"]}', 'Unexpected attempt entry')
    tokens = config['b0_context_tokens']
    if config['budget_status'] == 'FROZEN':
        require(config['calibration_status'] == 'CLOSED' and type(tokens) is int and tokens > 0
                and attempts[0]['status'] == 'COMPLETE' and attempts[0]['derivation_status'] == 'DERIVED'
                and config['budget_derivation']['attempt'] == attempts[0]['id'],
                'A frozen budget needs a closed calibration with a completed, derived attempt')
    else:
        require(config['budget_status'] == 'OPEN' and config['calibration_status'] == 'OPEN' and tokens is None
                and 'budget_derivation' not in config and attempts[0]['status'] != 'COMPLETE',
                'The budget is set only by the official calibration run')
    return config


def verify_frozen_budget(config, design):
    """A frozen budget must equal the immutable derivation artifact, which must match its archived sources."""
    if config['budget_status'] != 'FROZEN':
        return None
    binding, attempt = config['budget_derivation'], config['results']['attempts'][0]
    path = ROOT / binding['artifact']
    require(probe.file_hash(path) == binding['sha256'], 'Budget derivation artifact drifted')
    artifact = json.loads(path.read_text(encoding='utf-8'))
    evidence = {'collection_sha256': ROOT / attempt['result_directory'] / 'collection.json',
                'audit_sha256': ROOT / attempt['audit']['path'],
                'adjudication_sha256': ROOT / attempt['adjudication']['path']}
    recorded = {'collection_sha256': attempt['collection_sha256'], 'audit_sha256': attempt['audit']['sha256'],
                'adjudication_sha256': attempt['adjudication']['sha256']}
    require(all(probe.file_hash(evidence[k]) == recorded[k] for k in recorded), 'Archived evidence drifted')
    rows = artifact['per_history']
    require(artifact['schema_version'] == DERIVATION and artifact['status'] == 'DERIVED'
            and artifact['procedure_version'] == COLLECTION and artifact['attempt'] == attempt['id']
            and artifact['source'] == {**recorded, 'adjudication_status': 'ELIGIBLE'}
            and artifact['b0_context_tokens'] == config['b0_context_tokens']
            == max(r['required_tokens'] for r in rows) and len(rows) == attempt['histories']
            and artifact['histories'] == {'eligible': attempt['histories'], 'retained_at_maximum': attempt['histories']}
            and artifact['determined_by'] == [r for r in rows if r['required_tokens'] == config['b0_context_tokens']],
            'The frozen budget disagrees with its derivation artifact')
    budget, retention = design['design']['calibration']['budget'], design['design']['calibration']['retention']
    require(artifact['rule'] == {'name': budget['rule'], 'statistic': budget['statistic'], 'percentile_rule': 'none',
                                 'candidate_grid': budget['candidate_grid'],
                                 'headroom_tokens': budget['headroom_tokens'],
                                 'required_retention_fraction': retention['fraction']},
            'The derivation rule differs from the frozen design')
    require({k: artifact['tokenizer'][k] for k in ('repository_id', 'revision')} == {
        k: design['design']['tokenizer'][k] for k in ('repository_id', 'revision')},
            'The derivation tokenizer differs from the frozen design')
    return artifact


def official_attempt(config):
    """The single attempt that may run: the last one, planned, with every earlier attempt closed incomplete."""
    attempts = config['results']['attempts']
    require(config['budget_status'] != 'FROZEN' and attempts[-1]['status'] != 'COMPLETE', CLOSED)
    require(attempts[-1]['status'] == 'PLANNED_NOT_EXECUTED'
            and all(a['status'] == 'CLOSED_INCOMPLETE' for a in attempts[:-1]),
            'No official suffix attempt is available; STOP FOR RESEARCHER DECISION')
    return attempts[-1]


def require_official(config):
    """Live execution needs the procedure, failure handling and attempt policy all frozen, and no closed budget."""
    require(config['budget_status'] != 'FROZEN', CLOSED)
    require(config['status'] == 'PROCEDURE_FROZEN' and config['collection_rule']['status'] == 'FROZEN'
            and config['semantic_eligibility']['status'] == 'FROZEN'
            and config['attempt_policy']['status'] == 'FROZEN' and config['budget_status'] == 'OPEN'
            and config['b0_context_tokens'] is None,
            'B0 suffix procedure is not fully approved; live execution refused')
    official_attempt(config)


def load_contract(config):
    spec = config['contract']
    path = ROOT / spec['path']
    contract = json.loads(path.read_text(encoding='utf-8'))
    require(set(contract) == {'prompt_version', 'input_contract_version', 'output_schema_version', 'prompt',
                              'input_schema', 'output_schema'}, 'Unexpected contract fields')
    require(probe.file_hash(path) == spec['sha256']
            and probe.digest(contract['prompt'].encode('utf-8')) == spec['prompt_sha256']
            and probe.digest(probe.canonical(contract['input_schema']).encode('utf-8')) == spec['input_schema_sha256']
            and probe.digest(probe.canonical(contract['output_schema']).encode('utf-8')) == spec['output_schema_sha256']
            and (contract['prompt_version'], contract['input_contract_version'], contract['output_schema_version'])
            == (spec['prompt_version'], spec['input_contract_version'], spec['output_schema_version']),
            'Suffix contract drift')
    variant = contract['output_schema']['$defs']['variant']
    require(contract['output_schema']['required'] == list(gq.VARIANTS)
            and contract['output_schema']['additionalProperties'] is False
            and set(contract['output_schema']['properties']) == set(gq.VARIANTS)
            and variant['additionalProperties'] is False and variant['required'] == list(EVENTS)
            and set(variant['properties']) == set(EVENTS)
            and all(p == {'type': 'string', 'minLength': 1} for p in variant['properties'].values()),
            'Suffix output schema must require exactly nonempty U7 and N2 per variant')
    return contract


def load_inputs(path=CONFIG):
    config = load_config(path)
    design = cal.load_inputs(ROOT / config['design_config'])
    contract = load_contract(config)
    require(len(design['fixtures']) * len(design['generators']) == config['plan']['planned_logical_calls'],
            'Planned call count drift')
    require([{k: g['entry'][k] for k in ('logical_call_id', 'model', 'provider_order')}
             for g in design['generators']] == config['generators'], 'Generator identity drift')
    projections = [projection(f) for f in design['fixtures']]
    for fixture, payload in zip(design['fixtures'], projections):
        verify_projection(fixture, payload)
    inputs = {'config': config, 'contract': contract, 'design': design, 'fixtures': design['fixtures'],
              'manifest': design['manifest'], 'generators': design['generators'], 'projections': projections,
              'path': Path(path)}
    require(gq.sha(gq.canonical([gq.sha(gq.canonical(p)) for p in projections]))
            == config['input_projection']['set_sha256'], 'Input projection set drift')
    require(gq.sha(gq.canonical(plan_identity(inputs))) == config['plan']['plan_sha256'], 'Execution plan drift')
    verify_frozen_budget(config, design)
    return inputs


# --- Plan ------------------------------------------------------------------------------------------

def plan(inputs):
    return [(g, fixture, entry, payload) for g in inputs['generators']
            for fixture, entry, payload in zip(inputs['fixtures'], inputs['manifest']['scenarios'],
                                               inputs['projections'])]


def request(inputs, generator, payload):
    slot = generator['slot']
    return {'model': slot['model'],
            'provider': {'order': slot['provider_order'], 'allow_fallbacks': False, 'require_parameters': True},
            'messages': [{'role': 'system', 'content': inputs['contract']['prompt']},
                         {'role': 'user', 'content': probe.canonical(payload)}],
            'reasoning': {'effort': probe.GENERATION['reasoning_effort']},
            'max_tokens': probe.GENERATION['max_output_tokens'],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'b0_suffix_naturalization_v1', 'strict': True,
                'schema': inputs['contract']['output_schema']}}}


def plan_identity(inputs):
    config = inputs['config']
    return {'procedure_version': COLLECTION, **{k: config['contract'][k] for k in (
                'prompt_version', 'input_contract_version', 'output_schema_version', 'prompt_sha256',
                'input_schema_sha256', 'output_schema_sha256')},
            'material_manifest_sha256': inputs['design']['design']['calibration']['material']['manifest_sha256'],
            'order': config['plan']['order'], 'generators': config['generators'],
            'scenario_ids': [e['fixture_id'] for e in inputs['manifest']['scenarios']],
            'projection_sha256': [gq.sha(gq.canonical(p)) for p in inputs['projections']],
            'request_sha256': [probe.digest(probe.canonical(request(inputs, g, p)).encode())
                               for g, _, _, p in plan(inputs)]}


def output_path(generator, entry):
    return f'outputs/{generator["entry"]["logical_call_id"].lower()}/{entry["fixture_id"]}.json'


def verify_old_procedure_closed(inputs):
    """The full-history procedure must be closed with authentic closures for both of its attempts."""
    design = inputs['design']['design']['naturalization']
    require(design['status'] == 'CLOSED_NO_ELIGIBLE_SET'
            and [a['status'] for a in design['attempts']] == ['CLOSED_INCOMPLETE'] * 2,
            'The full-history B0 procedure must be closed')
    return cal.verify_predecessors(inputs['design'])


def preview(inputs):
    config = inputs['config']
    calls = plan(inputs)
    attempt = config['results']['attempts'][-1]
    bodies = [request(inputs, g, p) for g, _, _, p in calls]
    return {'status': 'NETWORK_DISABLED', 'credits': 'CREDITS_NOT_SPENT',
            'suffix_collection_status': 'NOT EXECUTED' if attempt['status'] == 'PLANNED_NOT_EXECUTED'
            else attempt['status'],
            'procedure_version': COLLECTION, 'calibration_status': config['calibration_status'],
            'budget_status': config['budget_status'], 'b0_context_tokens': config['b0_context_tokens'],
            'attempt_policy_status': config['attempt_policy']['status'], 'attempt_cap': config['attempt_policy']['cap'],
            'attempt': attempt['id'], 'attempt_status': attempt['status'],
            'result_directory': attempt['result_directory'],
            'old_procedure_closures': verify_old_procedure_closed(inputs),
            'contract': config['contract'], 'input_projection_set_sha256': config['input_projection']['set_sha256'],
            'plan_sha256': config['plan']['plan_sha256'],
            'planned_logical_calls': len(calls),
            'per_generator': {g['entry']['logical_call_id']: len(inputs['fixtures']) for g in inputs['generators']},
            'generators': config['generators'], 'suffix_events': list(EVENTS),
            'expected_histories': len(calls) * len(gq.VARIANTS),
            'maximum_physical_attempts': len(calls) * (probe.TRANSPORT['max_infrastructure_retries'] + 1),
            'order': config['plan']['order'], 'scenario_ids': [e['fixture_id'] for e in inputs['manifest']['scenarios']],
            'planned_calls': [f'{i}:{g["entry"]["logical_call_id"]}:{e["fixture_id"]}'
                              for i, (g, _, e, _) in enumerate(calls, 1)],
            'execution_mode': 'standard', 'generation': probe.GENERATION, 'transport': probe.TRANSPORT,
            'allow_fallbacks': False, 'require_parameters': True,
            'request_hashes': [probe.digest(probe.canonical(b).encode()) for b in bodies],
            'calls': [{'index': i, 'logical_call_id': g['entry']['logical_call_id'], 'model': g['entry']['model'],
                       'provider_order': g['entry']['provider_order'], 'scenario_id': e['fixture_id'],
                       'input_sha256': gq.sha(gq.canonical(p)),
                       'request_sha256': probe.digest(probe.canonical(b).encode()),
                       'output_path': f'{attempt["result_directory"]}/{output_path(g, e)}'}
                      for i, ((g, _, e, p), b) in enumerate(zip(calls, bodies), 1)]}


# --- Live collection -------------------------------------------------------------------------------

def guard_output(output, config, root=ROOT):
    """The closed full-history namespace is immutable; inside the suffix namespace only the planned attempt."""
    target = Path(output).resolve()
    old, new = (root / OLD_NAMESPACE).resolve(), (root / NAMESPACE).resolve()
    require(target != old and old not in target.parents, 'The closed full-history B0 result namespace is immutable')
    if target == new or new in target.parents:
        require(target == (root / official_attempt(config)['result_directory']).resolve(),
                'Only the planned attempt directory may be written; existing attempts are immutable')


def provenance(inputs):
    config = inputs['config']
    return {'source_commit': cal.git('rev-parse', 'HEAD').decode().strip(),
            'config_sha256': probe.file_hash(inputs['path']), 'procedure_version': COLLECTION,
            'design_sha256': probe.file_hash(inputs['design']['path']),
            'contract': config['contract'], 'plan_sha256': config['plan']['plan_sha256'],
            'input_projection_set_sha256': config['input_projection']['set_sha256'],
            'material_manifest_sha256': plan_identity(inputs)['material_manifest_sha256'],
            'system_prompt_sha256': inputs['design']['design']['system_prompt']['composed_sha256'],
            'generators': [{k: g['entry'][k] for k in ('logical_call_id', 'model', 'provider_order',
                                                       'execution_package_sha256')} for g in inputs['generators']],
            'implementation': {path: probe.file_hash(ROOT / path) for path in IMPLEMENTATION},
            'qualification_implementation': q.implementation('v2'),
            'attempt': official_attempt(config)['id'], 'old_procedure_closures': verify_old_procedure_closed(inputs),
            'python': platform.python_version(),
            'packages': {n: importlib.metadata.version(n) for n in ('httpx', 'pydantic', 'pyyaml')}}


async def collect(inputs, key, output, *, client_factory=httpx.AsyncClient, sleep=asyncio.sleep):
    """One official suffix collection. Any non-PASS call ends the attempt: evidence so far is kept, nothing is
    rerun, and only the frozen infrastructure retries inside probe_call repeat a request."""
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    require(not cal.git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=none'),
            'Official execution requires a clean worktree')
    cal.git('ls-files', '--error-unmatch', str(CONFIG.relative_to(ROOT)), 'configs/b0-calibration.yaml',
            inputs['config']['contract']['path'], *IMPLEMENTATION)
    require_official(inputs['config'])
    guard_output(output, inputs['config'])
    fresh = load_inputs(inputs['path'])
    fresh_provenance = provenance(fresh)
    require(fresh_provenance == provenance(inputs), 'Source/input changed since preflight')
    require(fresh_provenance['qualification_implementation']['status'] == q.FROZEN,
            f'Qualification implementation {q.NOT_FROZEN}; live execution refused')
    inputs = fresh
    attempt = official_attempt(inputs['config'])
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    stop = STOP + '; the attempt cap is reached and no further B0 suffix attempt is allowed'
    calls = plan(inputs)
    result = {'procedure_version': COLLECTION, 'status': 'INCOMPLETE', 'attempt': attempt['id'],
              'provenance': fresh_provenance, 'planned_logical_calls': len(calls),
              'expected_histories': len(calls) * len(gq.VARIANTS), 'failure_reason': None, 'calls': []}
    hashes = {}
    try:
        with suffix_output_contract():
            async with client_factory(trust_env=False, follow_redirects=False) as client:
                for index, (generator, fixture, entry, payload) in enumerate(calls, 1):
                    body = request(inputs, generator, payload)
                    call = await probe.probe_call(client, generator['bundle'], generator['slot'], key, sleep=sleep,
                                                  request_factory=lambda *_, body=body: body)
                    call.pop('semantic_qualification', None)
                    call.update(candidate=generator['entry']['logical_call_id'], fixture_id=entry['fixture_id'],
                                projection_sha256=gq.sha(gq.canonical(payload)), logical_call_index=index,
                                attempt=attempt['id'], procedure_version=COLLECTION)
                    if call['status'] == 'PASS':
                        parsed = call['attempts'][-1]['parsed_structured_response']
                        call['output_sha256'] = probe.digest(probe.canonical(parsed).encode())
                        call['automated'] = summarize_checks(automated_checks(fixture, parsed))
                    relative = output_path(generator, entry)
                    (directory / relative).parent.mkdir(parents=True, exist_ok=True)
                    hashes[relative] = q.publish(directory / relative, call, key)
                    result['calls'].append(probe.redact(call, key))
                    if call['status'] != 'PASS':
                        result['failure_kind'] = cal.failure_kind(call)
                        result['failure_reason'] = (f'{generator["entry"]["logical_call_id"]}/{entry["fixture_id"]}: '
                                                    f'{call["failure_reason"]}; {stop}')
                        break
                else:
                    result['status'] = 'COMPLETE'
    except Exception as exc:
        result['failure_reason'] = f'Execution/runner defect: {type(exc).__name__}: {exc}; {stop}'
    hashes['collection.json'] = q.publish(directory / 'collection.json', result, key)
    with (directory / 'SHA256SUMS').open('x', encoding='utf-8') as stream:
        for name, checksum in sorted(hashes.items()):
            stream.write(f'{checksum}  {name}\n')
    return result


# --- Ingestion and derivation ----------------------------------------------------------------------

def official_calls(directory):
    """Call records of a COMPLETE suffix attempt only."""
    directory = Path(directory)
    calls = cal.read_calls(directory)
    collection = json.loads((directory / 'collection.json').read_text(encoding='utf-8'))
    require(collection['procedure_version'] == COLLECTION and collection['status'] == 'COMPLETE'
            and len(calls) == collection['planned_logical_calls'],
            'Only a complete suffix attempt can supply calibration histories')
    return calls


def suffix_exchanges(u7, n2):
    """Exactly U7 user message, Noted., N2 user message, Noted."""
    return [{'event': label, 'messages': [{'role': 'user', 'content': text},
                                          {'role': 'assistant', 'content': window.ACKNOWLEDGEMENT}]}
            for label, text in (('U7', u7), ('N2', n2))]


def histories_from_calls(calls, inputs):
    """One suffix history per generator, scenario and variant; every record must come from one suffix attempt."""
    require(len({c.get('attempt') for c in calls}) == 1 and all(c.get('attempt') for c in calls)
            and {c.get('procedure_version') for c in calls} == {COLLECTION},
            'Call records must all belong to one suffix attempt')
    generators, scenarios = inputs['generators'], inputs['manifest']['scenarios']
    expected = {(g['entry']['logical_call_id'], e['fixture_id']) for g in generators for e in scenarios}
    keys = [(c.get('logical_call_id'), c.get('fixture_id')) for c in calls]
    require(len(keys) == len(set(keys)) and set(keys) == expected, 'Expected exactly one call per generator and scenario')
    by_key = dict(zip(keys, calls))
    histories = []
    for g in generators:
        for e in scenarios:
            call = by_key[(g['entry']['logical_call_id'], e['fixture_id'])]
            last = call['attempts'][-1]
            require(call['status'] == 'PASS' and last['parse_status'] == 'passed' and last['schema_status'] == 'passed'
                    and last['returned_model'] == g['entry']['model'], 'Call record is not a passed planned call')
            output = last['parsed_structured_response']
            validate_output(output)
            for variant in gq.VARIANTS:
                histories.append({'generator': g['entry']['logical_call_id'], 'model': g['entry']['model'],
                                  'scenario': e['fixture_id'], 'variant': variant,
                                  'exchanges': suffix_exchanges(output[variant]['U7'], output[variant]['N2'])})
    require(len(histories) == inputs['config']['plan']['expected_histories'], 'History count mismatch')
    return histories


def audit_template(directory, inputs):
    """Blank human audit for a COMPLETE attempt, derived only from its archived evidence."""
    directory = Path(directory)
    calls = official_calls(directory)
    histories_from_calls(calls, inputs)
    by_key = {(c['logical_call_id'], c['fixture_id']): c for c in calls}
    items = {}
    for generator in inputs['generators']:
        for fixture, entry in zip(inputs['fixtures'], inputs['manifest']['scenarios']):
            call = by_key[(generator['entry']['logical_call_id'], entry['fixture_id'])]
            output = call['attempts'][-1]['parsed_structured_response']
            automated = automated_checks(fixture, output)
            for variant in gq.VARIANTS:
                for event in EVENTS:
                    text = output[variant][event]
                    items[f'{generator["entry"]["logical_call_id"]}/{entry["fixture_id"]}/{variant}/{event}'] = {
                        'text': text, 'text_sha256': probe.digest(text.encode('utf-8')),
                        'automated': automated[variant][event],
                        'manual': {check: None for check, kind in LEVEL1[event].items() if kind == 'manual'},
                        'fluency': None}
    collection = json.loads((directory / 'collection.json').read_text(encoding='utf-8'))
    return {'schema_version': AUDIT, 'attempt': collection['attempt'], 'procedure_version': COLLECTION,
            'collection_sha256': probe.file_hash(directory / 'collection.json'), 'reviewer': '',
            'reviewed_at': '', 'notes': '', 'items': items}


def adjudicate(directory, audit, inputs):
    """Level-1 eligibility of a complete collection from its deterministic checks and a completed human audit.

    The audit must match the archived evidence exactly; only manual cells, optional fluency marks, the reviewer,
    the timestamp and notes are the reviewer's. Fluency never affects eligibility.
    """
    template = audit_template(directory, inputs)
    require(type(audit) is dict and set(audit) == set(template), 'Audit fields')
    for field in ('schema_version', 'attempt', 'procedure_version', 'collection_sha256'):
        require(audit[field] == template[field], f'Audit does not match the archived collection: {field}')
    require(type(audit['reviewer']) is str and audit['reviewer'].strip() and type(audit['notes']) is str
            and type(audit['reviewed_at']) is str and q.valid_timestamp(audit['reviewed_at']),
            'Audit incomplete: reviewer and reviewed_at are required')
    require(type(audit['items']) is dict and list(audit['items']) == list(template['items']), 'Audit items')
    failures, fluency = [], 0
    for item, expected in template['items'].items():
        got = audit['items'][item]
        require(type(got) is dict and set(got) == set(expected) and got['text'] == expected['text']
                and got['text_sha256'] == expected['text_sha256'] and got['automated'] == expected['automated']
                and type(got['manual']) is dict and set(got['manual']) == set(expected['manual']),
                f'Audit item does not match the archived evidence: {item}')
        require(all(v in ('PASS', 'FAIL') for v in got['manual'].values()),
                f'Audit incomplete: every manual check needs PASS or FAIL ({item})')
        require(got['fluency'] in (None, 'PASS', 'FAIL'), f'Audit fluency mark: {item}')
        failures += [{'item': item, 'check': check, 'source': 'automated'}
                     for check, v in expected['automated'].items() if v == 'FAIL']
        failures += [{'item': item, 'check': check, 'source': 'manual'}
                     for check, v in got['manual'].items() if v == 'FAIL']
        fluency += got['fluency'] == 'FAIL'
    eligible = not failures
    return {'schema_version': ADJUDICATION, 'attempt': template['attempt'],
            'collection_sha256': template['collection_sha256'], 'items_audited': len(template['items']),
            'status': 'ELIGIBLE' if eligible else 'COMPLETE_BUT_INELIGIBLE',
            'level1_failure_count': len(failures), 'level1_failures': failures,
            'fluency_findings': fluency, 'fluency_use': 'descriptive only; not used for eligibility or ranking',
            'budget_derivation': 'ALLOWED' if eligible else 'PROHIBITED', 'b0_context_tokens': None}


def eligible_histories(directory, audit, inputs):
    """The 72 suffix histories, only if the collection is complete and every Level-1 check passes."""
    verdict = adjudicate(directory, audit, inputs)
    require(verdict['status'] == 'ELIGIBLE',
            'Budget derivation refused: the completed collection is COMPLETE_BUT_INELIGIBLE')
    return histories_from_calls(official_calls(directory), inputs)


def derive_budget(directory, audit, tokenizer, inputs, system=None):
    """Exact-maximum derivation; refuses unless the collection is complete, audited, and Level-1 clean."""
    system = system if system is not None else cal.official_system(inputs['design']['design'])
    return cal.derive(eligible_histories(directory, audit, inputs), system, tokenizer)


def separate(path, directory):
    require(Path(directory).resolve() not in Path(path).resolve().parents, 'Outputs must be outside the attempt')


def verify_adjudication(directory, audit_path, adjudication, audit, inputs):
    """The immutable adjudication must be authentic for this collection and audit; no override is possible."""
    directory = Path(directory)
    verdict = adjudicate(directory, audit, inputs)
    require(type(adjudication) is dict and set(adjudication) == {*verdict, 'audit_file_sha256'},
            'Adjudication fields')
    require(adjudication['schema_version'] == ADJUDICATION
            and adjudication['attempt'] == verdict['attempt']
            and adjudication['collection_sha256'] == probe.file_hash(directory / 'collection.json'),
            'Adjudication does not belong to this collection')
    require(adjudication['audit_file_sha256'] == probe.file_hash(audit_path),
            'Adjudication does not belong to this completed audit')
    require(adjudication['status'] == 'ELIGIBLE' and adjudication['level1_failure_count'] == 0
            and adjudication['level1_failures'] == [] and adjudication['budget_derivation'] == 'ALLOWED'
            and adjudication['b0_context_tokens'] is None, 'Adjudication is not an ELIGIBLE result')
    require({k: adjudication[k] for k in ELIGIBILITY_FIELDS} == {k: verdict[k] for k in ELIGIBILITY_FIELDS},
            'Adjudication disagrees with the recomputed eligibility')
    return verdict


def load_reader_tokenizer(directory=None):
    """The frozen reader tokenizer: local artifacts verified against the pinned hashes, then loaded offline."""
    config = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))
    reader = config['reader_tokenizer']
    directory = Path(directory) if directory else Path(
        config['artifact_provenance']['verification_staging_directory']) / 'reader'
    checksums = retrieval.verify_artifacts(directory, reader['artifact_sha256'])
    metadata = directory / 'repository-metadata.json'
    if metadata.is_file():
        recorded = json.loads(metadata.read_text(encoding='utf-8'))
        require(recorded.get('id') == reader['repository_id'] and recorded.get('sha') == reader['revision'],
                'Local tokenizer metadata does not name the frozen repository and revision')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(directory), use_fast=reader['use_fast'], local_files_only=True,
                                              trust_remote_code=reader['trust_remote_code'])
    require(type(tokenizer).__name__ == reader['tokenizer_class'], 'Unexpected frozen tokenizer class')
    return tokenizer, {'repository_id': reader['repository_id'], 'revision': reader['revision'],
                       'source': 'configs/retrieval.yaml reader_tokenizer', 'artifact_sha256': checksums,
                       'tokenizer_class': reader['tokenizer_class'], 'use_fast': reader['use_fast'],
                       'add_special_tokens': reader['add_special_tokens'],
                       'directory_is_portable_identity': False}


def derive_final_budget(directory, audit_path, adjudication_path, output, inputs, tokenizer_directory=None):
    """The one offline derivation: verify provenance, call derive_budget(), and publish an immutable artifact."""
    require(inputs['config']['budget_status'] != 'FROZEN', CLOSED)
    directory, output = Path(directory), Path(output)
    separate(output, directory)
    require(not output.exists(), 'The budget derivation output already exists')
    require(directory.is_dir() and Path(audit_path).is_file() and Path(adjudication_path).is_file(),
            'The collection, completed audit and adjudication must all exist')
    audit = gq.read(audit_path)
    verify_adjudication(directory, audit_path, gq.read(adjudication_path), audit, inputs)
    tokenizer, identity = load_reader_tokenizer(tokenizer_directory)
    design = inputs['design']['design']
    require({k: identity[k] for k in ('repository_id', 'revision')} == {
        k: design['tokenizer'][k] for k in ('repository_id', 'revision')}, 'Tokenizer differs from the frozen design')
    result = derive_budget(directory, audit, tokenizer, inputs)
    config = inputs['config']
    artifact = {
        'schema_version': DERIVATION, 'status': 'DERIVED', 'procedure_version': COLLECTION,
        'attempt': json.loads((directory / 'collection.json').read_text(encoding='utf-8'))['attempt'],
        'source': {'collection_sha256': probe.file_hash(directory / 'collection.json'),
                   'audit_sha256': probe.file_hash(audit_path),
                   'adjudication_sha256': probe.file_hash(adjudication_path), 'adjudication_status': 'ELIGIBLE'},
        'tokenizer': identity,
        'design': {'system_prompt_sha256': design['system_prompt']['composed_sha256'],
                   'window_contract': design['window_contract'], 'suffix_config_sha256': probe.file_hash(inputs['path']),
                   'design_config_sha256': probe.file_hash(inputs['design']['path']),
                   'plan_sha256': config['plan']['plan_sha256'], 'contract': config['contract'],
                   'source_commit': cal.git('rev-parse', 'HEAD').decode().strip(),
                   'implementation': {path: probe.file_hash(ROOT / path) for path in IMPLEMENTATION},
                   'python': platform.python_version(),
                   'packages': {n: importlib.metadata.version(n) for n in ('transformers', 'tokenizers')}},
        'rule': {'name': design['calibration']['budget']['rule'],
                 'statistic': design['calibration']['budget']['statistic'], 'percentile_rule': 'none',
                 'candidate_grid': design['calibration']['budget']['candidate_grid'],
                 'headroom_tokens': design['calibration']['budget']['headroom_tokens'],
                 'required_retention_fraction': design['calibration']['retention']['fraction']},
        'histories': {'eligible': result['histories'], 'retained_at_maximum': result['retention']['retained']},
        'b0_context_tokens': result['b0_context_tokens'], 'determined_by': result['determined_by'],
        'retention': result['retention'], 'per_history': result['per_history']}
    require(artifact['histories']['eligible'] == config['plan']['expected_histories']
            and artifact['b0_context_tokens'] == max(r['required_tokens'] for r in result['per_history']),
            'Derivation result is inconsistent')
    output.parent.mkdir(parents=True, exist_ok=True)
    return artifact, q.publish(output, artifact)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, allow_abbrev=False, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Offline budget derivation (after an ELIGIBLE adjudication; never combined with other modes):\n'
               '  calibrate_b0_suffix.py --derive-budget ATTEMPT_DIRECTORY --audit COMPLETED_AUDIT \\\n'
               '      --adjudication ADJUDICATION_FILE --budget-output NEW_ARTIFACT_FILE')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-spend', action='store_true')
    parser.add_argument('--output-directory', type=Path, default=None)
    parser.add_argument('--audit-template', type=Path, help='Offline blank audit for a complete attempt directory')
    parser.add_argument('--template-output', type=Path, help='New immutable blank audit file')
    parser.add_argument('--adjudicate', type=Path, help='Offline adjudication of a complete attempt directory')
    parser.add_argument('--audit', type=Path, help='Completed copy of the audit for --adjudicate or --derive-budget')
    parser.add_argument('--adjudication-output', type=Path, help='New immutable adjudication file')
    parser.add_argument('--derive-budget', type=Path, metavar='ATTEMPT_DIRECTORY',
                        help='Offline final derivation of B0_CONTEXT_TOKENS from a complete, ELIGIBLE collection; '
                             'requires --audit, --adjudication and --budget-output')
    parser.add_argument('--adjudication', type=Path, help='The immutable ELIGIBLE adjudication for --derive-budget')
    parser.add_argument('--budget-output', type=Path, help='New immutable budget-derivation artifact')
    parser.add_argument('--reader-tokenizer-dir', type=Path,
                        help='Local frozen reader tokenizer files for --derive-budget (verified against the pinned '
                             'hashes; default: the staging directory named in configs/retrieval.yaml)')
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    if args.derive_budget or args.adjudication or args.budget_output or args.reader_tokenizer_dir:
        if not (args.derive_budget and args.audit and args.adjudication and args.budget_output):
            parser.error('--derive-budget requires --audit, --adjudication and --budget-output')
        if (args.execute or args.output_directory or args.audit_template or args.template_output
                or args.adjudicate or args.adjudication_output):
            parser.error('--derive-budget is exclusive: use it without execution, --audit-template or --adjudicate')
        artifact, checksum = derive_final_budget(args.derive_budget, args.audit, args.adjudication,
                                                 args.budget_output, load_inputs(args.config),
                                                 args.reader_tokenizer_dir)
        print(f'{artifact["status"]}: B0_CONTEXT_TOKENS = {artifact["b0_context_tokens"]} from '
              f'{artifact["histories"]["eligible"]} eligible suffix histories. Artifact SHA-256: {checksum}')
        return 0
    offline = (args.audit_template, args.template_output, args.adjudicate, args.audit, args.adjudication_output)
    if any(offline):
        if args.execute or args.output_directory:
            parser.error('Audit operations are offline; use no execution flags')
        if bool(args.audit_template) != bool(args.template_output) or bool(args.adjudicate) != bool(
                args.audit and args.adjudication_output) or (args.audit_template and args.adjudicate):
            parser.error('Use either --audit-template with --template-output, or --adjudicate with --audit and '
                         '--adjudication-output')
        inputs = load_inputs(args.config)
        if args.audit_template:
            separate(args.template_output, args.audit_template)
            template = audit_template(args.audit_template, inputs)
            args.template_output.parent.mkdir(parents=True, exist_ok=True)
            print(f'Blank audit for {template["attempt"]}: {len(template["items"])} items. '
                  f'SHA-256: {q.publish(args.template_output, template)}')
            return 0
        for path in (args.audit, args.adjudication_output):
            separate(path, args.adjudicate)
        verdict = adjudicate(args.adjudicate, gq.read(args.audit), inputs)
        verdict['audit_file_sha256'] = probe.file_hash(args.audit)
        args.adjudication_output.parent.mkdir(parents=True, exist_ok=True)
        checksum = q.publish(args.adjudication_output, verdict)
        print(f'{verdict["status"]}: {verdict["level1_failure_count"]} Level-1 failures; budget derivation '
              f'{verdict["budget_derivation"].lower()}. Adjudication SHA-256: {checksum}')
        return 0
    inputs = load_inputs(args.config)
    if not args.execute:
        if args.output_directory is not None:
            parser.error('--output-directory is used only with --execute')
        print(json.dumps(preview(inputs), indent=2, ensure_ascii=False))
        return 0
    if args.output_directory is None:
        parser.error('Execution requires an explicit --output-directory')
    require_official(inputs['config'])
    official = ROOT / official_attempt(inputs['config'])['result_directory']
    require(args.output_directory.resolve() == official.resolve(),
            'Official execution writes only to the planned result directory')
    result = asyncio.run(collect(inputs, os.environ.get('OPENROUTER_API_KEY', ''), args.output_directory))
    print(f'{result["status"]}: {len(result["calls"])} of {result["planned_logical_calls"]} calls recorded; '
          'no budget derived')
    return 0 if result['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
