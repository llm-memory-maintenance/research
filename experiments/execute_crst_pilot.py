"""CRST Small Pilot backbone execution (step D) and offline replay (step E).

The default invocation is an offline preview. Live execution needs --execute, --confirm-spend, --eligibility, the
naturalization directory, the frozen --output-directory and OPENROUTER_API_KEY, and refuses unless every gate holds.
--replay is offline and never contacts a provider.
"""
import argparse
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path

import httpx
import yaml

import crst_policies as pol
import crst_prompts as prompts
import crst_scoring as scoring
import crst_transport as transport
import naturalize_crst_pilot as nat
import probe_generators as probe
import qualify_generators as q
import run_crst_pilot as run
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
COLLECTION = 'crst-pilot-backbone-collection/1.0.0'
IMPLEMENTATION = (*nat.IMPLEMENTATION, 'experiments/execute_crst_pilot.py', 'experiments/crst_transport.py',
                  'configs/model.yaml')
STOP = 'EXECUTION ABORTED; STOP FOR RESEARCHER DECISION'
require = gq.require


def result_directory(config):
    return ROOT / config['backbone_execution']['result_directory']


def guard_output(output, config, root=ROOT):
    """Inside results/crst-small-pilot only the planned backbone directory may be written."""
    target, official = Path(output).resolve(), (root / nat.NAMESPACE).resolve()
    if target == official or official in target.parents:
        require(target == result_directory(config).resolve(),
                'Only the planned backbone directory may be written; existing evidence is immutable')


def load_model(config):
    return yaml.safe_load((ROOT / config['backbone']['parameters_config']).read_text(encoding='utf-8'))


def logical_ids(fixtures):
    return [p['logical_id'] for p in run.call_plan(fixtures)]


def preview(config, fixtures, model, directory=None):
    """Offline description of step D: exactly the planned logical calls and the gates that must hold."""
    plan = run.call_plan(fixtures)
    target = Path(directory) if directory else result_directory(config)
    return {'status': 'NETWORK_DISABLED', 'credits': 'CREDITS_NOT_SPENT', 'step': 'D backbone execution',
            'plan_counts': run.plan_counts(plan), 'logical_calls': [
                {k: p[k] for k in ('logical_id', 'run_id', 'kind', 'policy', 'event')} for p in plan],
            'model': model['model']['id'], 'provider_order': [model['provider']['upstream']],
            'allow_fallbacks': model['provider']['allow_fallbacks'],
            'provider_response_mode': prompts.response_format(), 'stateless': True,
            'result_directory': config['backbone_execution']['result_directory'],
            'result_directory_exists': target.exists(),
            'gates': config['backbone_execution']['requires'],
            'requires_flags': config['backbone_execution']['flags'],
            'b0_requests': 'require the eligible naturalized text'}


def implementation_hashes():
    return {path: probe.file_hash(ROOT / path) for path in IMPLEMENTATION}


def provenance(config_path, config, eligibility, collection_path, audit_record, tokenizer_identity):
    return {'source_commit': nat.git('rev-parse', 'HEAD').decode().strip(),
            'config_sha256': probe.file_hash(config_path),
            'model_config_sha256': config['backbone']['parameters_sha256'],
            'material_manifest_sha256': config['material']['manifest_sha256'],
            'prompt_identities': prompts.identities(), 'eligibility_status': audit_record['status'],
            'naturalization_audit_sha256': probe.file_hash(eligibility),
            'naturalization_collection_sha256': probe.file_hash(collection_path),
            'implementation': implementation_hashes(), 'tokenizer': tokenizer_identity,
            'python': platform.python_version(),
            'packages': {n: importlib.metadata.version(n) for n in ('httpx', 'pydantic', 'pyyaml')},
            'planned': {'runs': 24, 'backbone_calls': 132}}


def check_gates(config_path, eligibility, naturalization_directory, output, *, key, execute, confirm,
                tokenizer_directory=None, full_separation=True):
    """Every gate of step D. Returns the verified inputs; raises before any side effect otherwise."""
    require(execute and confirm, 'Execution requires BOTH --execute AND --confirm-spend')
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    config = run.load_config(config_path)
    run.verify_config(config)
    fixtures = run.load_fixtures(longmemeval=full_separation)
    require(not nat.git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=none'),
            'Execution requires a clean worktree')
    nat.git('ls-files', '--error-unmatch', *IMPLEMENTATION, 'data/crst-small-pilot/manifest.json')
    guard_output(output, config)
    require(not Path(output).exists(), 'The result directory already exists; evidence is immutable')
    ninputs = nat.load_inputs(config_path, full_separation=full_separation)
    texts, audit_record = nat.load_eligible(eligibility, naturalization_directory, ninputs)
    collection, _ = nat.verified_collection(naturalization_directory)
    recorded, current = collection['provenance'], nat.provenance(ninputs)
    for field in ('config_sha256', 'material_manifest_sha256', 'contract_sha256', 'prompt_sha256',
                  'output_schema_sha256', 'generators', 'request_sha256'):
        require(recorded[field] == current[field], f'Naturalization provenance differs from current: {field}')
    nat.git('merge-base', '--is-ancestor', recorded['source_commit'], 'HEAD')
    import calibrate_b0_suffix as suffix
    tokenizer, identity = suffix.load_reader_tokenizer(tokenizer_directory)
    for scenario, variants in texts.items():
        for variant, block in variants.items():
            run.b0_coverage_report({label: block[label] for label in pol.EVENT_ORDER}, tokenizer)
    model = load_model(config)
    gate_provenance = provenance(config_path, config, eligibility,
                                 Path(naturalization_directory) / 'collection.json', audit_record, identity)
    return {'config': config, 'model': model, 'fixtures': fixtures, 'texts': texts, 'tokenizer': tokenizer,
            'provenance': gate_provenance, 'path': Path(config_path)}


def record_path(request):
    return '/'.join(['records', *request['logical_id'].split('/')]) + '.json'


def run_path(run_id):
    return '/'.join(['runs', *run_id.split('/')]) + '.json'


def event_texts(gate, scenario, variant):
    block = gate['texts'][scenario][variant]
    return {label: block[label] for label in pol.EVENT_ORDER}


def run_document(result, records, model):
    """Everything needed to compare a later replay; raw responses live in the per-request records."""
    return {'run_id': result['run_id'], 'scenario_id': result['scenario_id'], 'variant': result['variant'],
            'policy': result['policy'], 'logical_ids': [r['logical_id'] for r in result['requests']],
            'journal': result['journal'], 'trajectory': result['trajectory'], 'raw_answer': result['raw_answer'],
            'classification': result['classification'], 'csa_contribution': result['csa'],
            'srr_contribution': result['srr'], 'maintenance': result['maintenance'],
            'memory_size': result['memory_size'], 'b0_context': result['b0_context'],
            'final_active_memory': result['final_active_memory'], 'summary': run.summarize_run(result),
            'accounting': run.account_run(records), 'end_to_end_seconds': result['end_to_end_seconds']}


def execute(gate, key, output, *, client_factory=httpx.Client, sleep=time.sleep, clock=time.monotonic):
    """One live execution. Any infrastructure or routing failure aborts; evidence so far is kept."""
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=False)
    model, hashes, run_ids = gate['model'], {}, []
    result = {'procedure_version': COLLECTION, 'status': 'ABORTED', 'provenance': gate['provenance'],
              'planned_runs': 24, 'planned_backbone_calls': 132, 'failure_reason': None, 'runs': [],
              'interpretation': 'PROHIBITED'}

    def publish(relative, value):
        (directory / relative).parent.mkdir(parents=True, exist_ok=True)
        hashes[relative] = q.publish(directory / relative, value, key)

    try:
        with client_factory(headers={'Authorization': f'Bearer {key}'}, follow_redirects=False,
                            trust_env=False) as client:
            for reference in gate['fixtures']:
                scenario = reference['scenario_id']
                for variant in gq.VARIANTS:
                    for policy in ('M1', 'B0', 'M2', 'M3'):
                        records = []

                        def on_record(request, body, response, policy=policy, scenario=scenario, variant=variant):
                            event = request['logical_id'].split('/')[-1]
                            record = run.logical_record(request, body, response, policy=policy, scenario=scenario,
                                                        variant=variant, event='Q' if event == 'A' else event,
                                                        model_config=model)
                            records.append(record)
                            publish(record_path(request), record)
                        ask = transport.make_ask(client, model, lambda r: run.request_body(model, r), on_record,
                                                 sleep=sleep, clock=clock)
                        outcome = pol.run_policy(
                            policy, reference, variant, ask=ask, question=gate['texts'][scenario][variant]['Q'],
                            texts=event_texts(gate, scenario, variant) if policy == 'B0' else None,
                            tokenizer=gate['tokenizer'], clock=clock)
                        publish(run_path(outcome['run_id']), run_document(outcome, records, model))
                        result['runs'].append(outcome['run_id'])
            result['status'] = 'COMPLETE'
            result['interpretation'] = 'OFFLINE_REPLAY_THEN_RESEARCHER_REVIEW'
    except (transport.InfrastructureFailure, transport.RoutingViolation) as exc:
        result['failure_reason'] = f'{type(exc).__name__}: {exc}; {STOP}'
    except Exception as exc:
        result['failure_reason'] = f'Execution/runner defect: {type(exc).__name__}: {exc}; {STOP}'
    publish('collection.json', result)
    with (directory / 'SHA256SUMS').open('x', encoding='utf-8') as stream:
        for name, checksum in sorted(hashes.items()):
            stream.write(f'{checksum}  {name}\n')
    return result


def replay(directory, gate):
    """Step E: rebuild every run from archived raw responses and compare it with the archived run document."""
    directory = Path(directory)
    sums = q.read_sums(directory)
    for name, checksum in sums.items():
        require(probe.file_hash(directory / name) == checksum, f'Archived file drifted: {name}')
    collection = json.loads((directory / 'collection.json').read_text(encoding='utf-8'))
    require(collection['status'] == 'COMPLETE', 'Only a complete execution is replayed')
    model, rows, records = gate['model'], [], {}
    for name in sums:
        if name.startswith('records/'):
            record = json.loads((directory / name).read_text(encoding='utf-8'))
            run.validate_record(record)
            records[record['logical_id']] = record
    for reference in gate['fixtures']:
        scenario = reference['scenario_id']
        for variant in gq.VARIANTS:
            for policy in ('M1', 'B0', 'M2', 'M3'):
                run_id = f'{scenario}/{variant}/{policy}'

                def ask(request):
                    record = records[request['logical_id']]
                    body = run.request_body(model, request)
                    require(run.request_sha(body) == record['request_sha256'],
                            f'Replayed request differs from the archive: {request["logical_id"]}')
                    return {'content': record['content']}
                again = pol.run_policy(
                    policy, reference, variant, ask=ask, question=gate['texts'][scenario][variant]['Q'],
                    texts=event_texts(gate, scenario, variant) if policy == 'B0' else None,
                    tokenizer=gate['tokenizer'])
                archived = json.loads((directory / run_path(run_id)).read_text(encoding='utf-8'))
                same = all(archived[k] == v for k, v in (
                    ('journal', again['journal']), ('classification', again['classification']),
                    ('raw_answer', again['raw_answer']), ('final_active_memory', again['final_active_memory']),
                    ('maintenance', again['maintenance']), ('memory_size', again['memory_size']),
                    ('b0_context', again['b0_context']), ('trajectory', again['trajectory'])))
                target = pol.target_answer(reference, variant)
                rows.append({'run_id': run_id, 'replay': 'MATCH' if same else 'MISMATCH',
                             'final_answer_raw': again['raw_answer'], 'classification': again['classification']['class'],
                             'reason': again['classification']['reason'], 'current_target': target['current'],
                             'superseded_targets': target['superseded']})
    return {'collection_sha256': probe.file_hash(directory / 'collection.json'), 'rows': rows,
            'post_run_checks': post_run_checks(directory, sums, records, collection, rows, gate),
            'review': 'Step F: the researcher cross-checks each row against the scorer; no ranking is computed.'}


def post_run_checks(directory, sums, records, collection, rows, gate):
    """Binary post-run checklist items. SCR-03 stays a researcher review item."""
    plan = logical_ids(gate['fixtures'])
    fields = all(run.validate_record(r) for r in records.values())
    ids = sorted(records) == sorted(plan) and len(plan) == 132
    accounted = all(isinstance(r['attempts'], list) and r['attempts'] and r['request_status'] == 'success'
                    and r['routing_ok'] is True for r in records.values())
    b0 = []
    for row in rows:
        if row['run_id'].endswith('/B0'):
            doc = json.loads((directory / run_path(row['run_id'])).read_text(encoding='utf-8'))
            b0.append(doc['b0_context']['b0_history_tokens'] <= pol.B0_CONTEXT_TOKENS
                      and doc['b0_context']['b0_selected_events'][-2:] == ['U7', 'N2'])
    provenance = collection['provenance']
    return {'ACC-01': 'PASS_POST_RUN' if fields and ids and accounted and len(rows) == 24 else 'FAIL',
            'ACC-02': 'PASS_POST_RUN' if all('attempts' in r for r in records.values()) else 'FAIL',
            'ACC-04': 'PASS_POST_RUN' if provenance['source_commit'] and provenance['python']
            and provenance['packages'] and provenance['implementation'] else 'FAIL',
            'ACC-05': 'PASS_POST_RUN' if all(r['replay'] == 'MATCH' for r in rows) else 'FAIL',
            'ANS-02': 'PASS_POST_RUN' if len(b0) == 6 and all(b0) else 'FAIL',
            'DATA-10': 'PASS_POST_RUN' if provenance['eligibility_status'] == 'ELIGIBLE' else 'FAIL',
            'SCR-03': 'PENDING_RESEARCHER_REVIEW'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=run.CONFIG_PATH)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-spend', action='store_true')
    parser.add_argument('--eligibility', type=Path)
    parser.add_argument('--naturalization-directory', type=Path)
    parser.add_argument('--output-directory', type=Path)
    parser.add_argument('--replay', type=Path, help='Offline replay of an archived backbone execution')
    parser.add_argument('--tokenizer-directory', type=Path, default=None)
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    config = run.load_config(args.config)
    run.verify_config(config)
    if args.replay:
        if args.execute or args.output_directory or not (args.eligibility and args.naturalization_directory):
            parser.error('Replay is offline: use --replay with --eligibility and --naturalization-directory only')
        gate = replay_inputs(args)
        print(json.dumps(replay(args.replay, gate), indent=2, ensure_ascii=False))
        return 0
    if not args.execute:
        if args.output_directory is not None:
            parser.error('--output-directory is used only with --execute')
        print(json.dumps(preview(config, run.load_fixtures(), load_model(config)), indent=2))
        return 0
    if not (args.eligibility and args.naturalization_directory and args.output_directory):
        parser.error('Execution requires --eligibility, --naturalization-directory and --output-directory')
    require(args.output_directory.resolve() == result_directory(config).resolve(),
            'Execution writes only to the frozen result directory')
    key = os.environ.get('OPENROUTER_API_KEY', '')
    gate = check_gates(args.config, args.eligibility, args.naturalization_directory, args.output_directory,
                       key=key, execute=args.execute, confirm=args.confirm_spend,
                       tokenizer_directory=args.tokenizer_directory)
    result = execute(gate, key, args.output_directory)
    print(f'{result["status"]}: {len(result["runs"])} of {result["planned_runs"]} runs recorded; no ranking computed')
    return 0 if result['status'] == 'COMPLETE' else 1


def replay_inputs(args):
    ninputs = nat.load_inputs(args.config, full_separation=False)
    texts, _ = nat.load_eligible(args.eligibility, args.naturalization_directory, ninputs)
    import calibrate_b0_suffix as suffix
    tokenizer, _ = suffix.load_reader_tokenizer(args.tokenizer_directory)
    config = run.load_config(args.config)
    return {'config': config, 'model': load_model(config), 'fixtures': run.load_fixtures(), 'texts': texts,
            'tokenizer': tokenizer}


if __name__ == '__main__':
    raise SystemExit(main())
