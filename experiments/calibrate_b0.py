"""B0 calibration: design validation, naturalization plan, gated collection and exact-maximum budget derivation.

The default invocation is an offline preview. Live collection needs --execute, --confirm-spend, the frozen
--output-directory and OPENROUTER_API_KEY. --close-attempt writes an offline closure for an incomplete attempt.
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
import yaml

import b0_window as window
import probe_generators as probe
import qualify_generators as q
import validate_b0_calibration_material as material
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
DESIGN = ROOT / 'configs/b0-calibration.yaml'
SCHEMA = 'b0-calibration-design/1.0.0'
PROMPT_STATUSES = ('PROPOSED_PENDING_RESEARCHER_APPROVAL', 'FROZEN')
COLLECTION = 'b0-calibration-naturalization/1.0.0'
CLOSURE = 'b0-calibration-closure/1.0.0'
ATTEMPT_STATUSES = ('CLOSED_INCOMPLETE', 'PLANNED_NOT_EXECUTED')
STOP = 'ATTEMPT CLOSED INCOMPLETE; STOP FOR RESEARCHER DECISION'
IMPLEMENTATION = ('experiments/calibrate_b0.py', 'experiments/b0_window.py',
                  'experiments/validate_b0_calibration_material.py')
require = gq.require


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, check=True).stdout


def load_design(path=DESIGN):
    design = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    require(type(design) is dict and design.get('schema_version') == SCHEMA and design['status'] == 'DESIGN_FROZEN',
            'Unexpected B0 calibration design')
    require(design['budget_status'] == 'OPEN' and design['b0_context_tokens'] is None,
            'The budget is set only by the official calibration run')
    contract = design['window_contract']
    require(contract['acknowledgement'] == window.ACKNOWLEDGEMENT
            and contract['required_events'] == list(window.REQUIRED_EVENTS), 'Window contract drift')
    reader = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']
    require({k: design['tokenizer'][k] for k in ('repository_id', 'revision')}
            == {k: reader[k] for k in ('repository_id', 'revision')}, 'Tokenizer identity drift')
    calibration = design['calibration']
    require(calibration['retention'] == {'requirement': 'all_histories', 'fraction': 1.0, 'percentile_rule': 'none'}
            and calibration['budget']['rule'] == 'exact_maximum' and calibration['budget']['headroom_tokens'] == 0
            and calibration['budget']['candidate_grid'] == 'none', 'Calibration rule drift')
    histories = calibration['histories']
    require(histories['total'] == histories['scenarios'] * len(histories['intensities']) * histories['generators'],
            'History count drift')
    prompt = design['system_prompt']
    require(prompt['status'] in PROMPT_STATUSES
            and gq.sha(system_message(design).encode('utf-8')) == prompt['composed_sha256'],
            'System prompt identity drift')
    require(calibration['coverage_failure']['status'] in PROMPT_STATUSES, 'Coverage rule status')
    nat = design['naturalization']
    require(nat['collection_rule']['status'] in PROMPT_STATUSES, 'Collection rule status')
    attempts = nat['attempts']
    require(nat['attempt_cap'] == 2 and 1 <= len(attempts) <= nat['attempt_cap']
            and [a['id'] for a in attempts] == [f'attempt-{i:02d}' for i in range(1, len(attempts) + 1)],
            'Unexpected attempt list')
    for attempt in attempts:
        require(attempt['status'] in ATTEMPT_STATUSES
                and Path(attempt['result_directory']).parts == ('results', 'b0-calibration', attempt['id']),
                'Unexpected attempt entry')
        require(attempt.get('closure') == (f'results/b0-calibration/closure/{attempt["id"]}.json'
                                           if attempt['status'] == 'CLOSED_INCOMPLETE' else None),
                'Unexpected closure reference')
    return design


def official_attempt(design):
    """The single attempt that may run: the last one, planned, with every earlier attempt closed incomplete."""
    attempts = design['naturalization']['attempts']
    require(attempts[-1]['status'] == 'PLANNED_NOT_EXECUTED'
            and all(a['status'] == 'CLOSED_INCOMPLETE' for a in attempts[:-1]),
            'No official attempt is available; STOP FOR RESEARCHER DECISION')
    return attempts[-1]


def require_official(design):
    """Live execution needs every design decision frozen, no completed attempt, and an attempt still allowed."""
    require(design['naturalization']['status'] != 'CLOSED_NO_ELIGIBLE_SET',
            'Full-history B0 naturalization is closed; no further attempt may run under this procedure')
    require(design['status'] == 'DESIGN_FROZEN' and design['system_prompt']['status'] == 'FROZEN'
            and design['calibration']['coverage_failure']['status'] == 'FROZEN'
            and design['naturalization']['collection_rule']['status'] == 'FROZEN'
            and design['budget_status'] == 'OPEN' and design['b0_context_tokens'] is None
            and design['naturalization']['status'] == 'AWAITING_COMPLETE_ATTEMPT',
            'B0 calibration design is not fully frozen; live execution refused')
    official_attempt(design)


def system_message(design):
    return design['system_prompt']['system'] + '\n\n' + design['system_prompt']['answer']


def official_system(design):
    """The fixed system message for official use; refused until the researcher approves the wording."""
    require(design['system_prompt']['status'] == 'FROZEN', 'B0 system/answer prompt wording is not approved')
    return system_message(design)


def load_inputs(path=DESIGN):
    design = load_design(path)
    material_config = design['calibration']['material']
    manifest, fixtures = material.validate_directory()
    require(gq.sha((material.DIRECTORY / 'manifest.json').read_bytes()) == material_config['manifest_sha256']
            and len(fixtures) == material_config['scenarios'], 'Calibration material drift')
    nat = design['naturalization']
    require(probe.file_hash(ROOT / nat['contract_path']) == nat['contract_sha256'] == q.CONTRACT_HASH
            and nat['prompt_sha256'] == q.PROMPT_HASH and nat['output_schema_sha256'] == q.SCHEMA_HASH
            and {k: nat[k] for k in probe.VERSIONS} == probe.VERSIONS, 'Naturalization contract drift')
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
        generators.append({'entry': entry, 'slot': slot, 'bundle': bundle})
    require(len(generators) * len(fixtures) == nat['planned_logical_calls'], 'Planned call count drift')
    return {'design': design, 'manifest': manifest, 'fixtures': fixtures, 'generators': generators,
            'path': Path(path)}


def plan(inputs):
    return [(g, fixture, entry) for g in inputs['generators']
            for fixture, entry in zip(inputs['fixtures'], inputs['manifest']['scenarios'])]


def request(generator, fixture):
    payload = gq.project(fixture)
    return probe.request_body(dict(generator['bundle'], input=payload), generator['slot'],
                              input_validator=gq.validate_input)


def output_path(generator, entry):
    return f'outputs/{generator["entry"]["logical_call_id"].lower()}/{entry["fixture_id"]}.json'


def plan_identity(inputs):
    """Everything that determines the requests; identical for every attempt of the same frozen design."""
    design, nat = inputs['design'], inputs['design']['naturalization']
    return {'material_manifest_sha256': design['calibration']['material']['manifest_sha256'],
            'system_prompt_sha256': design['system_prompt']['composed_sha256'],
            'contract_sha256': nat['contract_sha256'], 'prompt_sha256': nat['prompt_sha256'],
            'output_schema_sha256': nat['output_schema_sha256'], **{k: nat[k] for k in probe.VERSIONS},
            'order': nat['order'],
            'generators': [{k: g['entry'][k] for k in ('logical_call_id', 'model', 'provider_order',
                                                       'execution_package_sha256')} for g in inputs['generators']],
            'scenario_ids': [e['fixture_id'] for e in inputs['manifest']['scenarios']],
            'request_sha256': [probe.digest(probe.canonical(request(g, f)).encode()) for g, f, _ in plan(inputs)]}


def planned_attempt(design):
    """The attempt still allowed to run, or None once the procedure is closed."""
    attempts = design['naturalization']['attempts']
    return attempts[-1] if attempts[-1]['status'] == 'PLANNED_NOT_EXECUTED' else None


def preview(inputs):
    design, nat = inputs['design'], inputs['design']['naturalization']
    attempt = planned_attempt(design)
    calls = plan(inputs)
    bodies = [request(g, f) for g, f, _ in calls]
    for (_, fixture, entry), body in zip(calls, bodies):
        require(probe.digest(probe.canonical(gq.project(fixture)).encode()) == entry['projection_sha256']
                and json.loads(body['messages'][1]['content']) == gq.project(fixture), 'Input hash drift')
    return {'status': 'NETWORK_DISABLED', 'credits': 'CREDITS_NOT_SPENT', 'naturalization_status': nat['status'],
            'design_status': design['status'], 'budget_status': design['budget_status'],
            'b0_context_tokens': design['b0_context_tokens'],
            'system_prompt_status': design['system_prompt']['status'],
            'material_manifest_sha256': design['calibration']['material']['manifest_sha256'],
            'contract_sha256': nat['contract_sha256'], 'prompt_sha256': nat['prompt_sha256'],
            'output_schema_sha256': nat['output_schema_sha256'], **{k: nat[k] for k in probe.VERSIONS},
            'planned_logical_calls': len(calls),
            'per_generator': {g['entry']['logical_call_id']: len(inputs['fixtures']) for g in inputs['generators']},
            'generators': [{k: g['entry'][k] for k in ('logical_call_id', 'model', 'provider_order')}
                           for g in inputs['generators']],
            'expected_histories': len(calls) * len(gq.VARIANTS),
            'maximum_physical_attempts': len(calls) * (probe.TRANSPORT['max_infrastructure_retries'] + 1),
            'order': nat['order'], 'scenario_ids': [e['fixture_id'] for e in inputs['manifest']['scenarios']],
            'planned_calls': [f'{i}:{g["entry"]["logical_call_id"]}:{e["fixture_id"]}'
                              for i, (g, _, e) in enumerate(calls, 1)],
            'execution_mode': nat['execution_mode'], 'generation': probe.GENERATION, 'transport': probe.TRANSPORT,
            'allow_fallbacks': False, 'require_parameters': True,
            'attempt': attempt and attempt['id'], 'attempt_cap': nat['attempt_cap'],
            'predecessor_closures': verify_predecessors(inputs),
            'result_directory': attempt and attempt['result_directory'],
            'system_prompt_sha256': design['system_prompt']['composed_sha256'],
            'request_hashes': [probe.digest(probe.canonical(body).encode()) for body in bodies],
            'calls': [{'index': i, 'logical_call_id': g['entry']['logical_call_id'], 'model': g['entry']['model'],
                       'provider_order': g['entry']['provider_order'], 'scenario_id': e['fixture_id'],
                       'input_sha256': e['projection_sha256'],
                       'request_sha256': probe.digest(probe.canonical(body).encode()),
                       'output_path': attempt and f'{attempt["result_directory"]}/{output_path(g, e)}'}
                      for i, ((g, _, e), body) in enumerate(zip(calls, bodies), 1)]}


def verify_predecessors(inputs, root=ROOT):
    """Each closed attempt must have an authentic incomplete closure for the same frozen plan.

    Only the closure, collection.json and SHA256SUMS are hashed or read; no attempt output is loaded.
    """
    identity, closures = plan_identity(inputs), {}
    for entry in inputs['design']['naturalization']['attempts']:
        if entry['status'] != 'CLOSED_INCOMPLETE':
            continue
        closure_path, directory = root / entry['closure'], root / entry['result_directory']
        require(closure_path.is_file() and directory.is_dir(), f'Missing closure or evidence for {entry["id"]}')
        closure = json.loads(closure_path.read_text(encoding='utf-8'))
        require(closure['schema_version'] == CLOSURE and closure['attempt'] == entry['id']
                and closure['status'] == 'CLOSED_INCOMPLETE' and closure['budget_derivation'] == 'PROHIBITED'
                and closure['b0_context_tokens'] is None, f'{entry["id"]} closure is not CLOSED_INCOMPLETE')
        evidence = closure['evidence']
        require(probe.file_hash(directory / 'collection.json') == evidence['collection_sha256']
                and probe.file_hash(directory / 'SHA256SUMS') == evidence['sha256sums_sha256'],
                f'{entry["id"]} evidence drifted from its closure')
        require(closure['plan_identity'] == identity, f'The frozen plan changed since {entry["id"]}')
        closures[entry['id']] = probe.file_hash(closure_path)
    return closures


def guard_output(output, design, root=ROOT):
    """Inside results/b0-calibration only the planned attempt directory may be written."""
    target, official = Path(output).resolve(), (root / 'results/b0-calibration').resolve()
    if target == official or official in target.parents:
        require(target == (root / official_attempt(design)['result_directory']).resolve(),
                'Only the planned attempt directory may be written; existing attempts are immutable')


def failure_kind(call):
    last = call['attempts'][-1]
    infrastructure = last['retry_reason'] or last['error_type'] or last['http_status'] != 200
    return 'INFRASTRUCTURE_OR_API_ERROR' if infrastructure else 'OUTPUT_CONTRACT_FAILURE'


def terminal_detail(call, empty_fields):
    last = call['attempts'][-1]
    if failure_kind(call) != 'OUTPUT_CONTRACT_FAILURE':
        return 'INFRASTRUCTURE_OR_API_ERROR'
    if last['refusal']:
        return 'REFUSAL'
    if last['incomplete_or_truncated']:
        return 'TRUNCATION'
    if last['parse_status'] == 'failed':
        return 'PARSE_FAILURE'
    if last['schema_status'] == 'failed':
        return 'REQUIRED_EMPTY_FIELD_SCHEMA_FAILURE' if empty_fields else 'SCHEMA_FAILURE'
    return 'OTHER_OUTPUT_CONTRACT_FAILURE'


def classify_attempt(directory, inputs):
    """Offline, deterministic closure of an incomplete attempt, derived only from its archived evidence."""
    directory = Path(directory)
    sums = q.read_sums(directory)
    for name, checksum in sums.items():
        require(probe.file_hash(directory / name) == checksum, f'Archived file drifted: {name}')
    collection = json.loads((directory / 'collection.json').read_text(encoding='utf-8'))
    calls, planned = collection['calls'], plan(inputs)
    hashes = plan_identity(inputs)['request_sha256']
    require(collection['status'] == 'INCOMPLETE' and 0 < len(calls) < len(planned)
            and collection['planned_logical_calls'] == len(planned), 'Not an incomplete collection')
    require([c['logical_call_index'] for c in calls] == list(range(1, len(calls) + 1))
            and all(c['status'] == 'PASS' for c in calls[:-1]) and calls[-1]['status'] != 'PASS',
            'An incomplete attempt has passed calls followed by exactly one terminal call')
    require(set(sums) == {'collection.json', *(output_path(g, e) for (g, _, e), _ in zip(planned, calls))},
            'Unexpected archived files')
    for (generator, _, entry), call, wire in zip(planned, calls, hashes):
        require((call['logical_call_id'], call['fixture_id'], call['wire_request_sha256']) == (
            generator['entry']['logical_call_id'], entry['fixture_id'], wire), 'Recorded call differs from the plan')
        require(json.loads((directory / output_path(generator, entry)).read_text(encoding='utf-8')) == call,
                'Per-call file differs from the collection record')
    terminal = calls[-1]
    last = terminal['attempts'][-1]
    parsed = last['parsed_structured_response']
    empty = {variant: [k for k, v in block.items() if not isinstance(v, str) or not v]
             for variant, block in parsed.items()} if isinstance(parsed, dict) else {}
    empty = {variant: keys for variant, keys in empty.items() if keys}
    try:
        probe.validate_output(parsed)
        recheck = {'result': 'PASSES', 'reason': None}
    except ValueError as exc:
        recheck = {'result': 'FAILS', 'reason': str(exc)}
    schema = json.loads((ROOT / inputs['design']['naturalization']['contract_path']).read_text(
        encoding='utf-8'))['output_schema']['$defs']['variant']['properties']
    recorded = len(calls)
    return {
        'schema_version': CLOSURE, 'attempt': directory.name, 'status': 'CLOSED_INCOMPLETE',
        'terminal_reason': failure_kind(terminal), 'terminal_detail': terminal_detail(terminal, empty),
        'terminal_call': {
            'logical_call_index': terminal['logical_call_index'], 'logical_call_id': terminal['logical_call_id'],
            'model': last['requested_model'], 'scenario_id': terminal['fixture_id'],
            'http_status': last['http_status'], 'finish_reason': last['finish_reason'],
            'refusal': last['refusal'], 'incomplete_or_truncated': last['incomplete_or_truncated'],
            'parse_status': last['parse_status'], 'schema_status': last['schema_status'],
            'processing_or_charge_uncertain': last['processing_or_charge_uncertain'],
            'retry_reason': last['retry_reason'], 'physical_attempts': len(terminal['attempts']),
            'failure_reason': terminal['failure_reason'], 'empty_fields': empty,
            'wire_request_sha256': terminal['wire_request_sha256'],
            'response_sha256_before_redaction': last['response_sha256_before_redaction']},
        'schema_recheck': {'local_validator': recheck,
                           'frozen_schema_nonempty_minimum': sorted({v['minLength'] for v in schema.values()})},
        'calls': {'planned': len(planned), 'recorded': recorded, 'passed': recorded - 1, 'failed': 1,
                  'never_executed': list(range(recorded + 1, len(planned) + 1))},
        'any_processing_or_charge_uncertain': any(
            a['processing_or_charge_uncertain'] for c in calls for a in c['attempts']),
        'evidence': {'collection_sha256': probe.file_hash(directory / 'collection.json'),
                     'sha256sums_sha256': probe.file_hash(directory / 'SHA256SUMS'), 'files': sums,
                     'source_commit': collection['provenance']['source_commit'],
                     'design_sha256': collection['provenance']['design_sha256']},
        'plan_identity': plan_identity(inputs),
        'budget_derivation': 'PROHIBITED', 'b0_context_tokens': None,
        'output_use': 'No output of this attempt may be combined with another attempt or used to construct the '
                      'official calibration histories.'}


def close_attempt(directory, output, inputs):
    directory, output = Path(directory).resolve(), Path(output)
    require(directory not in output.resolve().parents and output.resolve() != directory,
            'The closure must be a separate file outside the attempt')
    closure = classify_attempt(directory, inputs)
    output.parent.mkdir(parents=True, exist_ok=True)
    return closure, q.publish(output, closure)


def provenance(inputs):
    design, nat = inputs['design'], inputs['design']['naturalization']
    return {'source_commit': git('rev-parse', 'HEAD').decode().strip(),
            'design_sha256': probe.file_hash(inputs['path']),
            'material_manifest_sha256': design['calibration']['material']['manifest_sha256'],
            'system_prompt_sha256': design['system_prompt']['composed_sha256'],
            'contract_sha256': nat['contract_sha256'], 'prompt_sha256': nat['prompt_sha256'],
            'output_schema_sha256': nat['output_schema_sha256'], **{k: nat[k] for k in probe.VERSIONS},
            'generators': [{k: g['entry'][k] for k in ('logical_call_id', 'model', 'provider_order',
                                                       'execution_package_sha256')} for g in inputs['generators']],
            'implementation': {path: probe.file_hash(ROOT / path) for path in IMPLEMENTATION},
            'qualification_implementation': q.implementation('v2'),
            'attempt': official_attempt(design)['id'], 'predecessor_closures': verify_predecessors(inputs),
            'python': platform.python_version(),
            'packages': {n: importlib.metadata.version(n) for n in ('httpx', 'pydantic', 'pyyaml')}}


async def collect(inputs, key, output, *, client_factory=httpx.AsyncClient, sleep=asyncio.sleep):
    """One official collection. Any non-PASS call stops the run: evidence so far is kept, nothing is rerun,
    and only the frozen infrastructure retries inside probe_call ever repeat a request."""
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    require(not git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=none'),
            'Official execution requires a clean worktree')
    git('ls-files', '--error-unmatch', 'configs/b0-calibration.yaml', 'data/b0-calibration/manifest.json',
        *IMPLEMENTATION)
    require_official(inputs['design'])
    guard_output(output, inputs['design'])
    fresh = load_inputs(inputs['path'])
    fresh_provenance = provenance(fresh)
    require(fresh_provenance == provenance(inputs), 'Source/input changed since preflight')
    require(fresh_provenance['qualification_implementation']['status'] == q.FROZEN,
            f'Qualification implementation {q.NOT_FROZEN}; live execution refused')
    inputs = fresh
    attempt = official_attempt(inputs['design'])
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    stop = STOP + ('; the attempt cap is reached and no further B0 attempt is allowed' if attempt['id'] == 'attempt-%02d'
                   % inputs['design']['naturalization']['attempt_cap'] else '')
    result = {'procedure_version': COLLECTION, 'status': 'INCOMPLETE', 'attempt': attempt['id'],
              'provenance': fresh_provenance,
              'planned_logical_calls': len(plan(inputs)), 'expected_histories':
              len(plan(inputs)) * len(gq.VARIANTS), 'failure_reason': None, 'calls': []}
    hashes = {}
    try:
        async with client_factory(trust_env=False, follow_redirects=False) as client:
            for index, (generator, fixture, entry) in enumerate(plan(inputs), 1):
                body = request(generator, fixture)
                call = await probe.probe_call(client, generator['bundle'], generator['slot'], key, sleep=sleep,
                                              request_factory=lambda *_, body=body: body)
                call.pop('semantic_qualification', None)
                call.update(candidate=generator['entry']['logical_call_id'], fixture_id=entry['fixture_id'],
                            projection_sha256=entry['projection_sha256'], logical_call_index=index,
                            attempt=attempt['id'])
                if call['status'] == 'PASS':
                    call['output_sha256'] = probe.digest(probe.canonical(
                        call['attempts'][-1]['parsed_structured_response']).encode())
                relative = output_path(generator, entry)
                (directory / relative).parent.mkdir(parents=True, exist_ok=True)
                hashes[relative] = q.publish(directory / relative, call, key)
                result['calls'].append(probe.redact(call, key))
                if call['status'] != 'PASS':
                    result['failure_kind'] = failure_kind(call)
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


def read_calls(directory):
    """Checksum-verified per-call records of an archived collection, in planned order."""
    directory = Path(directory)
    sums = q.read_sums(directory)
    for name, checksum in sums.items():
        require(probe.file_hash(directory / name) == checksum, f'Archived file drifted: {name}')
    calls = [json.loads((directory / name).read_text(encoding='utf-8')) for name in sums if name.startswith('outputs/')]
    return sorted(calls, key=lambda call: call['logical_call_index'])


def official_calls(directory):
    """Call records of a COMPLETE attempt only; an incomplete attempt can never supply calibration histories."""
    directory = Path(directory)
    calls = read_calls(directory)
    collection = json.loads((directory / 'collection.json').read_text(encoding='utf-8'))
    require(collection['status'] == 'COMPLETE' and len(calls) == collection['planned_logical_calls'],
            'Only a complete attempt can supply calibration histories')
    return calls


def histories_from_calls(calls, inputs):
    """Validate the official call records and return one calibration history per generator, scenario and variant.

    All records must come from one attempt; records of different attempts are never combined.
    """
    require(len({c.get('attempt') for c in calls}) == 1 and all(c.get('attempt') for c in calls),
            'Call records must all belong to one attempt')
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
            probe.validate_output(output)
            for variant in gq.VARIANTS:
                block = output[variant]
                histories.append({'generator': g['entry']['logical_call_id'], 'model': g['entry']['model'],
                                  'scenario': e['fixture_id'], 'variant': variant,
                                  'exchanges': window.build_exchanges({k: v for k, v in block.items() if k != 'Q'}),
                                  'question': block['Q']})
    require(len(histories) == inputs['design']['calibration']['histories']['total'], 'History count mismatch')
    return histories


def derive(histories, system, tokenizer):
    """Exact maximum of the per-history minimum budgets, with retention verified for every history."""
    require(len(histories) > 0, 'No calibration histories')
    rows = []
    for h in histories:
        need = window.required_budget(h['exchanges'], system, tokenizer)
        own = window.select_window(h['exchanges'], need, system, tokenizer)
        require(window.retains(own) and not window.retains(
            window.select_window(h['exchanges'], need - 1, system, tokenizer)), 'Per-history budget is not minimal')
        rows.append({'generator': h['generator'], 'scenario': h['scenario'], 'variant': h['variant'],
                     'required_tokens': need})
    maximum = max(row['required_tokens'] for row in rows)
    retained = 0
    for h in histories:
        selection = window.select_window(h['exchanges'], maximum, system, tokenizer)
        require(window.retains(selection) and not selection['history_unit_overflow'], 'Retention failure at maximum')
        if h.get('question') is not None:
            messages = window.assemble(system, selection, h['question'])
            require(messages[-1] == {'role': 'user', 'content': h['question']}, 'Question boundary')
        require(window.history_tokens(system, selection['exchanges'], tokenizer) <= maximum, 'Budget exceeded')
        retained += 1
    determining = [row for row in rows if row['required_tokens'] == maximum]
    key = {(h['generator'], h['scenario'], h['variant']): h for h in histories}
    for row in determining:
        below = window.select_window(key[(row['generator'], row['scenario'], row['variant'])]['exchanges'],
                                     maximum - 1, system, tokenizer)
        require(not window.retains(below), 'Maximum is not minimal')
    return {'histories': len(histories), 'per_history': rows, 'maximum': maximum, 'determined_by': determining,
            'retention': {'histories': len(histories), 'retained': retained, 'fraction': retained / len(histories)},
            'b0_context_tokens': maximum}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--design', type=Path, default=DESIGN)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-spend', action='store_true')
    parser.add_argument('--output-directory', type=Path, default=None)
    parser.add_argument('--close-attempt', type=Path, help='Offline closure of an incomplete attempt directory')
    parser.add_argument('--closure-output', type=Path, help='New immutable closure file for --close-attempt')
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    if args.close_attempt or args.closure_output:
        if not (args.close_attempt and args.closure_output):
            parser.error('Closure requires both --close-attempt and --closure-output')
        if args.execute or args.output_directory:
            parser.error('Closure is an offline operation; use no execution flags')
        closure, checksum = close_attempt(args.close_attempt, args.closure_output, load_inputs(args.design))
        print(f'{closure["status"]}: {closure["attempt"]} ({closure["terminal_detail"]}); '
              f'budget derivation prohibited. Closure SHA-256: {checksum}')
        return 0
    inputs = load_inputs(args.design)
    if not args.execute:
        if args.output_directory is not None:
            parser.error('--output-directory is used only with --execute')
        print(json.dumps(preview(inputs), indent=2, ensure_ascii=False))
        return 0
    if args.output_directory is None:
        parser.error('Execution requires an explicit --output-directory')
    require_official(inputs['design'])
    official = ROOT / official_attempt(inputs['design'])['result_directory']
    require(args.output_directory.resolve() == official.resolve(),
            'Official execution writes only to the frozen result directory')
    result = asyncio.run(collect(inputs, os.environ.get('OPENROUTER_API_KEY', ''), args.output_directory))
    print(f'{result["status"]}: {len(result["calls"])} of {result["planned_logical_calls"]} calls recorded; '
          'no budget derived')
    return 0 if result['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
