"""Offline tests of the gated backbone execution, its abort rules, and replay (mock transport only)."""
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from crst_common import (ANSWER_INSTRUCTION, KEY, ROOT, ToyTokenizer, chat_envelope, fake_git, no_network,  # noqa: F401
                         reference_decision, run_naturalization)
import calibrate_b0_suffix as suffix
import crst_policies as pol
import execute_crst_pilot as ex
import naturalize_crst_pilot as nat
import probe_generators as probe
import qualify_generators as q
import run_crst_pilot as run
import validate_generator_qualification_fixtures as gq

CONFIG = run.CONFIG_PATH


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setattr(nat, 'git', fake_git)
    monkeypatch.setattr(nat.material, 'LONGMEMEVAL_RAW', ROOT / 'nonexistent-longmemeval.json')
    monkeypatch.setattr(suffix, 'load_reader_tokenizer', lambda directory=None: (
        ToyTokenizer(), {'repository_id': 'meta-llama/Llama-3.1-8B-Instruct', 'toy': True}))


@pytest.fixture(scope='module')
def ninputs():
    return nat.load_inputs()


@pytest.fixture()
def world(ninputs, tmp_path):
    """A mock-collected, audited, eligible naturalization directory."""
    directory = tmp_path / 'naturalization'
    run_naturalization(ninputs, directory)
    audit = tmp_path / 'audit.json'
    q.publish(audit, nat.audit(directory, ninputs, ToyTokenizer()))
    return {'directory': directory, 'audit': audit, 'out': tmp_path / 'backbone'}


def gates(world, **overrides):
    args = dict(key=KEY, execute=True, confirm=True, full_separation=False)
    args.update(overrides)
    return ex.check_gates(CONFIG, world['audit'], world['directory'], world['out'], **args)


def plan_replies(gate):
    """Content of every planned reply, in plan order, following the reference path."""
    replies = []
    for reference in gate['fixtures']:
        for variant in gq.VARIANTS:
            for policy in ('M1', 'B0', 'M2', 'M3'):
                if policy in ('M2', 'M3'):
                    replies += [reference_decision(e) for e in pol.reference_events(reference, variant, policy)[7:]]
                replies.append(json.dumps({'answer': reference['gold_current_value']}))
    return replies


def mock_client(gate, override=None):
    """Returns (client_factory, bodies). Replies follow the plan, and `override(i, body)` may return a Response.

    `i` counts physical requests. An error-status override is an infrastructure failure of that attempt and does
    not consume the logical reply; a 2xx override replaces the reply of the current logical request.
    """
    replies, bodies, logical = plan_replies(gate), [], []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        response = override(len(bodies) - 1, body) if override else None
        if response is not None and response.status_code >= 400:
            return response
        logical.append(1)
        return response or httpx.Response(200, json=chat_envelope(body, replies[len(logical) - 1]))
    return (lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler), **kwargs)), bodies


def execute(gate, out, override=None):
    factory, bodies = mock_client(gate, override)
    result = ex.execute(gate, KEY, out, client_factory=factory, sleep=lambda s: None)
    return result, bodies


def tree(path):
    return sorted(str(p.relative_to(path)) for p in Path(path).rglob('*') if p.is_file())


# --- Preview --------------------------------------------------------------------------------------------

def test_preview_is_exactly_132_logical_calls_108_maintenance_and_24_answers():
    config = run.load_config()
    shown = ex.preview(config, run.load_fixtures(), ex.load_model(config))
    assert shown['plan_counts'] == {'runs': 24, 'backbone_calls': 132, 'maintenance': 108, 'answering': 24}
    calls = shown['logical_calls']
    assert len(calls) == len({c['logical_id'] for c in calls}) == 132
    assert sum(c['kind'] == 'maintenance' for c in calls) == 108 and sum(c['kind'] == 'answer' for c in calls) == 24
    assert shown['model'] == 'meta-llama/llama-3.1-8b-instruct' and shown['provider_order'] == ['coreweave/bf16']
    assert shown['allow_fallbacks'] is False and shown['provider_response_mode'] == {'type': 'json_object'}
    assert shown['stateless'] is True and shown['credits'] == 'CREDITS_NOT_SPENT'
    assert shown['result_directory'] == 'results/crst-small-pilot/backbone/attempt-01'
    assert 'eligible naturalization audit bound to the archived collection' in shown['gates']


def test_cli_preview_writes_nothing_and_needs_no_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.chdir(tmp_path)
    assert ex.main([]) == 0
    assert json.loads(capsys.readouterr().out)['plan_counts']['backbone_calls'] == 132
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('flags', [['--execute'], ['--confirm-spend'],
                                   ['--execute', '--confirm-spend'],
                                   ['--replay', 'x', '--execute', '--confirm-spend']])
def test_cli_refuses_incomplete_or_mixed_execution_flags(flags):
    with pytest.raises(SystemExit):
        ex.main(flags)


def test_cli_refuses_a_non_frozen_output_directory(world, tmp_path):
    with pytest.raises(ValueError, match='frozen result directory'):
        ex.main(['--execute', '--confirm-spend', '--eligibility', str(world['audit']),
                 '--naturalization-directory', str(world['directory']), '--output-directory', str(tmp_path / 'x')])


# --- Gates ----------------------------------------------------------------------------------------------

def test_all_gates_hold_for_an_eligible_collection(world):
    gate = gates(world)
    assert set(gate['texts']) == {'pilot-scheduling-01', 'pilot-travel-01'}
    assert gate['provenance']['eligibility_status'] == 'ELIGIBLE' and gate['provenance']['source_commit'] == '0' * 40
    assert set(gate['provenance']['implementation']) == set(ex.IMPLEMENTATION)
    assert gate['provenance']['prompt_identities']['provider_response_mode']['response_format'] == {
        'type': 'json_object'}
    assert not world['out'].exists()


def test_gates_refuse_without_both_flags(world):
    for flags in ({'execute': False}, {'confirm': False}):
        with pytest.raises(ValueError, match='BOTH'):
            gates(world, **flags)


def test_gates_refuse_a_blank_key(world):
    with pytest.raises(ValueError, match='OPENROUTER_API_KEY'):
        gates(world, key=' ')


def test_gates_refuse_a_dirty_worktree(world, monkeypatch):
    monkeypatch.setattr(nat, 'git', lambda *a: b' M x\0' if a[0] == 'status' else fake_git(*a))
    with pytest.raises(ValueError, match='clean worktree'):
        gates(world)


def test_gates_refuse_untracked_implementation_files(world, monkeypatch):
    def untracked(*a):
        if a[0] == 'ls-files':
            raise subprocess.CalledProcessError(1, 'git')
        return fake_git(*a)
    monkeypatch.setattr(nat, 'git', untracked)
    with pytest.raises(subprocess.CalledProcessError):
        gates(world)


def test_gates_refuse_an_existing_result_directory(world):
    world['out'].mkdir()
    with pytest.raises(ValueError, match='already exists'):
        gates(world)


def test_gates_refuse_a_non_frozen_directory_inside_the_pilot_namespace(world):
    world['out'] = ROOT / 'results/crst-small-pilot/backbone/attempt-02'
    with pytest.raises(ValueError, match='planned backbone directory'):
        gates(world)


@pytest.mark.parametrize('status', ['NOT_ELIGIBLE', 'PENDING_RESEARCHER_REVIEW'])
def test_gates_refuse_an_audit_that_is_not_eligible(world, status):
    record = json.loads(world['audit'].read_text())
    world['audit'].write_text(json.dumps({**record, 'status': status}))
    with pytest.raises(ValueError, match='not ELIGIBLE'):
        gates(world)


def test_gates_refuse_an_audit_that_belongs_to_another_collection(world):
    record = json.loads(world['audit'].read_text())
    world['audit'].write_text(json.dumps({**record, 'collection_sha256': '0' * 64}))
    with pytest.raises(ValueError, match='does not belong'):
        gates(world)


def test_gates_refuse_a_tampered_or_missing_naturalization(world, tmp_path):
    (world['directory'] / 'pilot-travel-01/unit.json').write_text('{}')
    with pytest.raises(ValueError, match='drifted'):
        gates(world)
    world['directory'] = tmp_path / 'absent'
    with pytest.raises(Exception):
        gates(world)


def test_gates_refuse_an_incomplete_naturalization(ninputs, tmp_path):
    directory = tmp_path / 'stopped'
    run_naturalization(ninputs, directory, replies=['garbage'] * 3)
    with pytest.raises(ValueError, match='not complete'):
        nat.accepted_outputs(directory, ninputs)


def test_gates_refuse_when_source_or_config_identities_differ_from_the_naturalization(world, monkeypatch):
    real = nat.provenance
    for field in ('config_sha256', 'material_manifest_sha256', 'request_sha256', 'prompt_sha256'):
        monkeypatch.setattr(nat, 'provenance', lambda i, field=field: {**real(i), field: 'changed'})
        with pytest.raises(ValueError, match=field):
            gates(world)


def test_gates_refuse_when_the_pilot_material_no_longer_validates(world, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError('material drift')
    monkeypatch.setattr(run.material, 'validate_directory', broken)
    with pytest.raises(ValueError, match='material drift'):
        gates(world)


def test_gates_refuse_when_the_protocol_config_drifts(world, tmp_path):
    import yaml
    config = yaml.safe_load(CONFIG.read_text())
    config['answering']['b0']['b0_context_tokens'] = 72
    changed = tmp_path / 'config.yaml'
    changed.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        ex.check_gates(changed, world['audit'], world['directory'], world['out'], key=KEY, execute=True,
                       confirm=True, full_separation=False)


def test_gates_require_a_loadable_pinned_tokenizer(world, monkeypatch):
    def missing(directory=None):
        raise FileNotFoundError('tokenizer artifacts missing')
    monkeypatch.setattr(suffix, 'load_reader_tokenizer', missing)
    with pytest.raises(FileNotFoundError):
        gates(world)


def test_gates_recheck_b0_coverage_of_the_naturalized_text(world, monkeypatch):
    class Heavy(ToyTokenizer):
        def encode(self, text, add_special_tokens):
            return super().encode(text, add_special_tokens) * 20
    monkeypatch.setattr(suffix, 'load_reader_tokenizer', lambda directory=None: (Heavy(), {}))
    with pytest.raises(pol.CoverageFailure):
        gates(world)


# --- Execution (mock transport only) ---------------------------------------------------------------------

def test_mocked_execution_makes_exactly_132_calls_in_plan_order_and_archives_everything(world):
    gate = gates(world)
    result, bodies = execute(gate, world['out'])
    plan = run.call_plan(gate['fixtures'])
    assert result['status'] == 'COMPLETE' and len(bodies) == 132 and len(result['runs']) == 24
    names = tree(world['out'])
    assert sum(n.startswith('records/') for n in names) == 132 and sum(n.startswith('runs/') for n in names) == 24
    assert {'collection.json', 'SHA256SUMS'} <= set(names)
    for call in plan:
        record = json.loads((world['out'] / ex.record_path({'logical_id': call['logical_id']})).read_text())
        assert run.validate_record(record) and record['logical_id'] == call['logical_id']
    assert [json.loads((world['out'] / ex.record_path({'logical_id': c['logical_id']})).read_text())['request_body']
            for c in plan] == bodies
    for body in bodies:
        assert body['response_format'] == {'type': 'json_object'} and 'json_schema' not in json.dumps(body)
        assert body['model'] == 'meta-llama/llama-3.1-8b-instruct' and body['provider']['allow_fallbacks'] is False
        assert body['provider']['order'] == ['coreweave/bf16']
        assert not {'conversation', 'session', 'previous_response_id', 'tools'} & body.keys()
    assert KEY not in ' '.join((world['out'] / n).read_text() for n in names)


def test_calls_per_policy_and_request_shapes(world):
    gate = gates(world)
    result, bodies = execute(gate, world['out'])
    docs = {r: json.loads((world['out'] / ex.run_path(r)).read_text()) for r in result['runs']}
    for run_id, doc in docs.items():
        policy = run_id.rsplit('/', 1)[1]
        assert doc['summary']['logical_calls'] == {'M1': 1, 'B0': 1, 'M2': 10, 'M3': 10}[policy]
        assert len(doc['logical_ids']) == doc['accounting']['logical_calls']
    by_id = {}
    for call in run.call_plan(gate['fixtures']):
        by_id[call['logical_id']] = bodies[len(by_id)]
    for run_id in docs:
        answer = by_id[f'{run_id}/A']['messages']
        scenario, variant, policy = run_id.split('/')
        question = gate['texts'][scenario][variant]['Q']
        if policy == 'B0':
            assert answer[-1] == {'role': 'user', 'content': f'Question:\n{question}\n\n{ANSWER_INSTRUCTION}'}
            assert answer[0]['role'] == 'system'
            assert all(m['role'] in ('user', 'assistant') for m in answer[1:-1])
            assert docs[run_id]['b0_context']['b0_history_tokens'] <= 71
        else:
            assert [m['role'] for m in answer] == ['system', 'user']
            assert answer[1]['content'] == (f'Context:\n{docs[run_id]["final_active_memory"]}\n\n'
                                            f'Question:\n{question}\n\n{ANSWER_INSTRUCTION}')


def test_no_policy_ranking_or_aggregate_is_written(world):
    gate = gates(world)
    result, _ = execute(gate, world['out'])
    text = ' '.join((world['out'] / n).read_text() for n in tree(world['out']) if n.startswith(('runs/', 'coll')))
    for word in run.FORBIDDEN_RANKING_KEYS:
        assert f'"{word}"' not in text


def test_infrastructure_retries_stay_inside_one_logical_request(world):
    gate = gates(world)
    result, bodies = execute(gate, world['out'], override=lambda i, b: httpx.Response(503) if i in (0, 7) else None)
    assert result['status'] == 'COMPLETE' and len(bodies) == 134
    doc = json.loads((world['out'] / ex.run_path('pilot-scheduling-01/low/M1')).read_text())
    assert doc['accounting']['logical_calls'] == 1 and doc['accounting']['physical_attempts'] == 2
    assert doc['accounting']['retry_attempts_without_usage'] == 1
    record = json.loads((world['out'] / ex.record_path({'logical_id': 'pilot-scheduling-01/low/M1/A'})).read_text())
    assert [a['http_status'] for a in record['attempts']] == [503, 200]


def test_malformed_model_output_is_scored_not_retried_or_repaired(world):
    gate = gates(world)
    extra_field = json.dumps({'answer': 'x', 'extra': 1})

    def override(index, body):
        # Plan order for the first variant: 0 M1 answer, 1 B0 answer, 2-10 M2 decisions U1..N2, 11 M2 answer.
        if index in (0, 2):
            return httpx.Response(200, json=chat_envelope(body, 'not json'))
        if index == 1:
            return httpx.Response(200, json=chat_envelope(body, extra_field))
    result, bodies = execute(gate, world['out'], override)
    assert result['status'] == 'COMPLETE' and len(bodies) == 132
    m1 = json.loads((world['out'] / ex.run_path('pilot-scheduling-01/low/M1')).read_text())
    assert m1['classification']['class'] == 'OTHER_ERROR' and m1['classification']['reason'] == 'not_json'
    b0 = json.loads((world['out'] / ex.run_path('pilot-scheduling-01/low/B0')).read_text())
    assert b0['classification']['class'] == 'OTHER_ERROR' and b0['classification']['reason'] == 'wrong_fields'
    m2 = json.loads((world['out'] / ex.run_path('pilot-scheduling-01/low/M2')).read_text())
    invalid = [j for j in m2['journal'] if j['status'] == 'INVALID_DECISION']
    assert [j['event'] for j in invalid] == ['U1'] and invalid[0]['post_state'] == invalid[0]['pre_state']
    assert m2['maintenance']['invalid_decisions'] == 1 and m2['summary']['logical_calls'] == 10


def test_infrastructure_terminal_failure_aborts_and_preserves_evidence(world):
    gate = gates(world)
    result, bodies = execute(gate, world['out'], override=lambda i, b: httpx.Response(400) if i == 29 else None)
    assert result['status'] == 'ABORTED' and len(bodies) == 30 and 'STOP FOR RESEARCHER DECISION' in result['failure_reason']
    assert 'InfrastructureFailure' in result['failure_reason'] and len(result['runs']) < 24
    names = tree(world['out'])
    assert sum(n.startswith('records/') for n in names) == 30 and 'SHA256SUMS' in names
    failed = [json.loads((world['out'] / n).read_text()) for n in names if n.startswith('records/')]
    assert sum(r['request_status'] == 'failed' for r in failed) == 1 and sum(1 for r in failed if r['content']) == 29


def test_routing_violation_aborts(world):
    gate = gates(world)
    result, bodies = execute(gate, world['out'], override=lambda i, b: httpx.Response(
        200, json=chat_envelope(b, '{}', provider='Other')) if i == 3 else None)
    assert result['status'] == 'ABORTED' and len(bodies) == 4 and 'RoutingViolation' in result['failure_reason']


def test_an_existing_result_directory_is_never_overwritten(world):
    gate = gates(world)
    execute(gate, world['out'])
    before = {n: (world['out'] / n).read_bytes() for n in tree(world['out'])}
    factory, bodies = mock_client(gate)
    with pytest.raises(FileExistsError):
        ex.execute(gate, KEY, world['out'], client_factory=factory, sleep=lambda s: None)
    assert bodies == [] and {n: (world['out'] / n).read_bytes() for n in tree(world['out'])} == before


def test_no_test_ever_writes_under_the_real_results_namespace(world):
    gate = gates(world)
    execute(gate, world['out'])


# --- Replay (offline) -------------------------------------------------------------------------------------

def replay_gate(gate):
    return {k: gate[k] for k in ('config', 'model', 'fixtures', 'texts', 'tokenizer')}


def test_replay_reproduces_all_24_runs_and_reports_post_run_checks(world):
    gate = gates(world)
    execute(gate, world['out'])
    report = ex.replay(world['out'], replay_gate(gate))
    assert len(report['rows']) == 24 and {r['replay'] for r in report['rows']} == {'MATCH'}
    assert report['post_run_checks'] == {'ACC-01': 'PASS_POST_RUN', 'ACC-02': 'PASS_POST_RUN',
                                         'ACC-04': 'PASS_POST_RUN', 'ACC-05': 'PASS_POST_RUN',
                                         'ANS-02': 'PASS_POST_RUN', 'DATA-10': 'PASS_POST_RUN',
                                         'SCR-03': 'PENDING_RESEARCHER_REVIEW'}
    assert all(r['classification'] == 'CURRENT_CORRECT' for r in report['rows'])
    assert not any(k in report for k in run.FORBIDDEN_RANKING_KEYS) and 'aggregate' not in json.dumps(report)


def test_replay_is_offline_and_deterministic(world, monkeypatch):
    gate = gates(world)
    execute(gate, world['out'])
    monkeypatch.setattr(httpx.Client, 'post', lambda *a, **k: pytest.fail('replay must not call a provider'))
    assert ex.replay(world['out'], replay_gate(gate)) == ex.replay(world['out'], replay_gate(gate))


def test_replay_detects_tampered_evidence(world):
    gate = gates(world)
    execute(gate, world['out'])
    record = world['out'] / ex.record_path({'logical_id': 'pilot-travel-01/high/M3/A'})
    record.write_text(record.read_text().replace('CoreWeave', 'Other'))
    with pytest.raises(ValueError, match='drifted'):
        ex.replay(world['out'], replay_gate(gate))


def test_replay_flags_a_run_document_that_no_longer_matches_its_raw_responses(world):
    gate = gates(world)
    execute(gate, world['out'])
    path = world['out'] / ex.run_path('pilot-scheduling-01/low/M2')
    document = json.loads(path.read_text())
    document['classification']['class'] = 'STALE_ERROR'
    path.write_text(json.dumps(document))
    sums = (world['out'] / 'SHA256SUMS').read_text().splitlines()
    name = ex.run_path('pilot-scheduling-01/low/M2')
    (world['out'] / 'SHA256SUMS').write_text('\n'.join(
        f'{probe.file_hash(path)}  {name}' if line.endswith(name) else line for line in sums) + '\n')
    report = ex.replay(world['out'], replay_gate(gate))
    assert [r['run_id'] for r in report['rows'] if r['replay'] == 'MISMATCH'] == ['pilot-scheduling-01/low/M2']
    assert report['post_run_checks']['ACC-05'] == 'FAIL'


def test_replay_refuses_an_aborted_execution(world):
    gate = gates(world)
    execute(gate, world['out'], override=lambda i, b: httpx.Response(400) if i == 5 else None)
    with pytest.raises(ValueError, match='complete'):
        ex.replay(world['out'], replay_gate(gate))


def test_replay_detects_a_changed_request(world):
    gate = gates(world)
    execute(gate, world['out'])
    changed = dict(gate['model'], generation={**gate['model']['generation'], 'temperature': 0.5})
    with pytest.raises(ValueError, match='differs from the archive'):
        ex.replay(world['out'], {**replay_gate(gate), 'model': changed})


def test_gates_refuse_a_naturalization_from_a_commit_outside_the_current_history(world, monkeypatch):
    def unreachable(*a):
        if a[0] == 'merge-base':
            raise subprocess.CalledProcessError(1, 'git')
        return fake_git(*a)
    monkeypatch.setattr(nat, 'git', unreachable)
    with pytest.raises(subprocess.CalledProcessError):
        gates(world)


def test_post_run_check_fails_when_a_b0_history_exceeds_the_frozen_budget(world):
    gate = gates(world)
    execute(gate, world['out'])
    name = ex.run_path('pilot-scheduling-01/low/B0')
    path = world['out'] / name
    document = json.loads(path.read_text())
    document['b0_context']['b0_history_tokens'] = 999
    path.write_text(json.dumps(document))
    sums = (world['out'] / 'SHA256SUMS').read_text().splitlines()
    (world['out'] / 'SHA256SUMS').write_text('\n'.join(
        f'{probe.file_hash(path)}  {name}' if line.endswith(name) else line for line in sums) + '\n')
    assert ex.replay(world['out'], replay_gate(gate))['post_run_checks']['ANS-02'] == 'FAIL'


@pytest.mark.parametrize('kind', ['infrastructure', 'routing'])
def test_abort_is_never_scored_or_interpreted(world, kind):
    """Approved abort rule: after exhausted retries, no model-decision scoring and no partial interpretation."""
    overrides = {'infrastructure': lambda i, b: httpx.Response(503) if i >= 40 else None,
                 'routing': lambda i, b: httpx.Response(200, json=chat_envelope(b, '{}', provider='Other'))
                 if i == 40 else None}
    gate = gates(world)
    result, bodies = execute(gate, world['out'], overrides[kind])
    assert result['status'] == 'ABORTED' and result['interpretation'] == 'PROHIBITED'
    assert 'STOP FOR RESEARCHER DECISION' in result['failure_reason']
    names = tree(world['out'])
    documents = [n for n in names if n.startswith('runs/')]
    assert len(documents) == len(result['runs']) and 0 < len(documents) < 24
    planned = [r['run_id'] for r in run.call_plan(gate['fixtures'])]
    in_progress = next(r for r in dict.fromkeys(planned) if r not in result['runs'])
    assert not (world['out'] / ex.run_path(in_progress)).exists()
    collection = (world['out'] / 'collection.json').read_text()
    assert 'OTHER_ERROR' not in collection and 'CURRENT_CORRECT' not in collection
    records = [json.loads((world['out'] / n).read_text()) for n in names if n.startswith('records/')]
    assert sum(r['request_status'] == 'failed' or r['routing_ok'] is False for r in records) == 1
    assert not any(r['logical_id'].startswith(in_progress + '/') and r['request_status'] == 'success'
                   and r['logical_id'].endswith('/A') for r in records)
    with pytest.raises(ValueError, match='complete'):
        ex.replay(world['out'], replay_gate(gate))


def test_complete_execution_is_marked_for_replay_then_review_only(world):
    gate = gates(world)
    result, _ = execute(gate, world['out'])
    assert result['interpretation'] == 'OFFLINE_REPLAY_THEN_RESEARCHER_REVIEW'


def test_config_records_the_approved_abort_rule():
    backbone = run.load_config()['backbone']
    assert 'never scored as a model decision or OTHER_ERROR' in backbone['infrastructure_terminal_failure']
    assert 'never scored as a model decision or OTHER_ERROR' in backbone['routing_violation']
    assert backbone['partial_execution'].startswith('never continued and never interpreted')
