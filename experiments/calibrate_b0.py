"""B0 calibration: design validation, naturalization plan, gated collection and exact-maximum budget derivation.

The default invocation is an offline preview. Live collection needs --execute, --confirm-spend, the frozen
--output-directory and OPENROUTER_API_KEY.
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
    directory = Path(design['naturalization']['result_directory'])
    require(not directory.is_absolute() and '..' not in directory.parts
            and directory.parts[:2] == ('results', 'b0-calibration'), 'Unexpected official result directory')
    return design


def require_official(design):
    """Live execution needs every design decision frozen and the calibration not yet run."""
    require(design['status'] == 'DESIGN_FROZEN' and design['system_prompt']['status'] == 'FROZEN'
            and design['calibration']['coverage_failure']['status'] == 'FROZEN'
            and design['budget_status'] == 'OPEN' and design['b0_context_tokens'] is None
            and design['naturalization']['status'] == 'PLANNED_NOT_EXECUTED',
            'B0 calibration design is not fully frozen; live execution refused')


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


def preview(inputs):
    design, nat = inputs['design'], inputs['design']['naturalization']
    calls = plan(inputs)
    bodies = [request(g, f) for g, f, _ in calls]
    for (_, fixture, entry), body in zip(calls, bodies):
        require(probe.digest(probe.canonical(gq.project(fixture)).encode()) == entry['projection_sha256']
                and json.loads(body['messages'][1]['content']) == gq.project(fixture), 'Input hash drift')
    return {'status': 'NETWORK_DISABLED', 'credits': 'CREDITS_NOT_SPENT', 'naturalization_status': 'NOT EXECUTED',
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
            'allow_fallbacks': False, 'require_parameters': True, 'result_directory': nat['result_directory'],
            'system_prompt_sha256': design['system_prompt']['composed_sha256'],
            'request_hashes': [probe.digest(probe.canonical(body).encode()) for body in bodies],
            'calls': [{'index': i, 'logical_call_id': g['entry']['logical_call_id'], 'model': g['entry']['model'],
                       'provider_order': g['entry']['provider_order'], 'scenario_id': e['fixture_id'],
                       'input_sha256': e['projection_sha256'],
                       'request_sha256': probe.digest(probe.canonical(body).encode()),
                       'output_path': f'{nat["result_directory"]}/{output_path(g, e)}'}
                      for i, ((g, _, e), body) in enumerate(zip(calls, bodies), 1)]}


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
    fresh = load_inputs(inputs['path'])
    fresh_provenance = provenance(fresh)
    require(fresh_provenance == provenance(inputs), 'Source/input changed since preflight')
    require(fresh_provenance['qualification_implementation']['status'] == q.FROZEN,
            f'Qualification implementation {q.NOT_FROZEN}; live execution refused')
    inputs = fresh
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    result = {'procedure_version': COLLECTION, 'status': 'INCOMPLETE', 'provenance': fresh_provenance,
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
                            projection_sha256=entry['projection_sha256'], logical_call_index=index)
                if call['status'] == 'PASS':
                    call['output_sha256'] = probe.digest(probe.canonical(
                        call['attempts'][-1]['parsed_structured_response']).encode())
                relative = output_path(generator, entry)
                (directory / relative).parent.mkdir(parents=True, exist_ok=True)
                hashes[relative] = q.publish(directory / relative, call, key)
                result['calls'].append(probe.redact(call, key))
                if call['status'] != 'PASS':
                    result['failure_reason'] = (f'{generator["entry"]["logical_call_id"]}/{entry["fixture_id"]}: '
                                                f'{call["failure_reason"]}; STOP FOR ADJUDICATION')
                    break
            else:
                result['status'] = 'COMPLETE'
    except Exception as exc:
        result['failure_reason'] = f'Execution/runner defect: {type(exc).__name__}: {exc}'
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


def histories_from_calls(calls, inputs):
    """Validate the official call records and return one calibration history per generator, scenario and variant."""
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
        messages = window.assemble(system, selection, h['question'])
        require(messages[-1] == {'role': 'user', 'content': h['question']}
                and window.history_tokens(system, selection['exchanges'], tokenizer) <= maximum, 'Question boundary')
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
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    inputs = load_inputs(args.design)
    if not args.execute:
        if args.output_directory is not None:
            parser.error('--output-directory is used only with --execute')
        print(json.dumps(preview(inputs), indent=2, ensure_ascii=False))
        return 0
    if args.output_directory is None:
        parser.error('Execution requires an explicit --output-directory')
    require_official(inputs['design'])
    official = ROOT / inputs['design']['naturalization']['result_directory']
    require(args.output_directory.resolve() == official.resolve(),
            'Official execution writes only to the frozen result directory')
    result = asyncio.run(collect(inputs, os.environ.get('OPENROUTER_API_KEY', ''), args.output_directory))
    print(f'{result["status"]}: {len(result["calls"])} of {result["planned_logical_calls"]} calls recorded; '
          'no budget derived')
    return 0 if result['status'] == 'COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
