"""Offline capability machinery tests; synthetic responses never qualify a model."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess

import httpx
import pytest
import yaml

SPEC = importlib.util.spec_from_file_location('probe', Path(__file__).resolve().parents[1] / 'experiments/probe_generators.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('External network access forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


@pytest.fixture
def bundle():
    return p.load_bundle()


def envelope(slot=None):
    slot = slot or p.SLOTS[0]
    output = {v: {e: 'Synthetic mock output.' for e in (*p.EVENTS, 'Q')} for v in p.VARIANTS}
    return {'id': 'completion-mock', 'model': slot['model'],
            'openrouter_metadata': {'endpoints': {'available': [
                {'provider': slot['provider_order'][0], 'selected': True}]}},
            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(output)}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 51}}


def call(bundle, handler):
    waits, requests = [], []
    def wrapped(request):
        requests.append(request)
        return handler(request)
    async def sleep(seconds):
        waits.append(seconds)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(wrapped)) as client:
            return await p.probe_call(client, bundle, p.SLOTS[0], 'mock-secret', sleep=sleep)
    return asyncio.run(run()), requests, waits


def test_document_contract_and_hashes(bundle):
    doc = (p.ROOT / bundle['config']['contract_document_path']).read_text()
    assert doc.split('```text\n', 1)[1].split('\n```', 1)[0] == bundle['contract']['prompt']
    assert json.loads(doc.split('```json\n', 1)[1].split('\n```', 1)[0]) == bundle['contract']['output_schema']
    assert bundle['provenance'] == p.load_bundle()['provenance']
    assert bundle['provenance']['config_sha256'] == p.file_hash(p.CONFIG)
    assert bundle['provenance']['prompt_sha256'] == 'a7b7013488d27b95962d1131d4d635eb065238b92e87f2b654d817a01d99d279'
    assert bundle['provenance']['output_schema_sha256'] == 'c0970e798666467520b3b33fc2657424c52ecf8be3a97d502f056156257cb917'


def test_requests_and_schema(bundle):
    a, b = [p.request_body(bundle, slot) for slot in p.SLOTS]
    assert a['messages'] == b['messages']
    assert a['response_format'] == b['response_format']
    for body, slot in zip((a, b), p.SLOTS):
        assert body['model'] == slot['model'] and ':batch' not in body['model']
        assert body['provider'] == {'order': slot['provider_order'], 'allow_fallbacks': False, 'require_parameters': True}
        assert [m['role'] for m in body['messages']] == ['system', 'user']
        assert body['messages'][1]['content'] == p.canonical(bundle['input'])
        assert body['reasoning'] == {'effort': 'low'}
        assert 'temperature' not in body and 'top_p' not in body
        assert body['max_tokens'] == 16384
        assert not {'tools', 'plugins', 'search', 'max_output_tokens'} & body.keys()
    schema = a['response_format']['json_schema']['schema']
    assert a['response_format']['json_schema']['strict'] is True
    assert schema['required'] == list(p.VARIANTS) and schema['additionalProperties'] is False
    variant = schema['$defs']['variant']
    assert variant['additionalProperties'] is False
    assert variant['required'] == [*p.EVENTS, 'Q']
    assert len(schema['required']) * len(variant['required']) == 51
    assert all(v == {'type': 'string', 'minLength': 1} for v in variant['properties'].values())


def test_input_invariants_and_serialization(bundle):
    data = bundle['input']
    p.validate_input(data)
    assert p.canonical(data) == p.canonical(dict(reversed(list(data.items()))))
    assert '\n' not in p.canonical(data)
    assert p.canonical({'z': 'é', 'a': 1}) == '{"a":1,"z":"é"}'
    def walk(value):
        if isinstance(value, dict):
            assert not {'previous_value', 'gold_answer', 'superseded_values', 'reference_operation',
                        'timestamp', 'memory_id', 'evaluator_labels'} & value.keys()
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(data)
    for variant, positions in p.SCHEDULES.items():
        events = data['variants'][variant]
        assert [e['event'] for e in events] == list(p.EVENTS)
        assert {int(e['event'][1:]) for e in events if e['event'].startswith('U') and e['state_key'] == 'key_01'} == positions
        assert events[-3]['event'] == 'N1' and events[-3]['semantics'] == 'same_state'
        assert events[-2]['event'] == 'U7' and events[-1]['event'] == 'N2'


@pytest.mark.parametrize('mutation', ['extra', 'missing', 'schedule', 'n1', 'n2', 'return', 'final', 'order'])
def test_invalid_input_rejected_before_request(bundle, mutation):
    data = bundle['input']
    if mutation == 'extra':
        data['previous_value'] = 'forbidden'
    elif mutation == 'missing':
        del data['question_intent']
    elif mutation == 'schedule':
        data['variants']['low'][7]['state_key'] = 'key_01'
    elif mutation in ('n1', 'n2'):
        data['variants']['low'][-3 if mutation == 'n1' else -1]['current_value'] = 'wrong'
    elif mutation == 'return':
        data['variants']['high'][-2]['current_value'] = data['state_keys'][0]['initial_value']
    elif mutation == 'final':
        data['variants']['low'][-2]['current_value'] = '19999'
    else:
        data['variants']['low'].reverse()
    with pytest.raises(ValueError):
        p.request_body(bundle, p.SLOTS[0])


@pytest.mark.parametrize('field,value', [('allow_fallbacks', True), ('require_parameters', False),
                                        ('execution_mode', 'batch'), ('prompt_sha256', 'bad'),
                                        ('input_sha256', 'bad'), ('contract_sha256', 'bad')])
def test_config_fail_closed(bundle, tmp_path, field, value):
    bundle['config'][field] = value
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(bundle['config']))
    with pytest.raises(ValueError):
        p.load_bundle(path)


def test_default_preview_no_client_no_key_no_artifact(monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('Execution entered by preview')
    monkeypatch.setattr(p, 'execute_probe', forbidden)
    class Environment(dict):
        def get(self, key, default=None):
            if key == 'OPENROUTER_API_KEY':
                pytest.fail('Preview read API key')
            return super().get(key, default)
    monkeypatch.setattr(p.os, 'environ', Environment(p.os.environ))
    output = tmp_path / 'must-not-exist'
    assert p.main(['--output-directory', str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'CAPABILITY_PROBE_CLOSED_PASS'
    assert result['output_directory'] is None
    assert result['successful_attempt'] == 'attempt-02'
    assert result['execution_package'] == 'FROZEN'
    assert result['generation'] == {'reasoning_effort': 'low', 'max_output_tokens': 16384}
    assert result['expected_logical_calls'] == 2 and result['maximum_physical_inference_attempts'] == 6
    assert not output.exists()


@pytest.mark.parametrize('args', [['--execute'], ['--confirm-spend'], ['--execute', '--confirm-spend']])
def test_execution_gates_and_missing_key(monkeypatch, args):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setattr(p, 'execute_probe', lambda *args: pytest.fail('Execution entered'))
    with pytest.raises(SystemExit) as exc:
        p.main(args)
    assert exc.value.code == 2


@pytest.mark.parametrize('status', [408, 429, 500, 502, 503, 504])
def test_retryable_http(bundle, status):
    result, requests, waits = call(bundle, lambda _: httpx.Response(status, json={'error': {'code': status}}))
    assert result['status'] == 'FAIL' and len(requests) == 3 and waits == [1, 2]
    assert [a['will_retry'] for a in result['attempts']] == [True, True, False]


@pytest.mark.parametrize('error', [httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.CloseError,
                                  httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
def test_transport_retry_classes(bundle, error):
    def handler(_):
        raise error('mock')
    result, requests, waits = call(bundle, handler)
    assert len(requests) == 3 and waits == [1, 2]
    assert all(a['processing_or_charge_uncertain'] for a in result['attempts'])
    assert not p.retryable(error=ValueError('schema or semantic failure'))


@pytest.mark.parametrize('status', [400, 401, 403, 404, 422])
def test_nonretryable_http(bundle, status):
    result, requests, waits = call(bundle, lambda _: httpx.Response(status, json={'error': {'code': status}}))
    assert result['status'] == 'FAIL' and len(requests) == 1 and not waits


def test_parameter_error_overrides_retry_status(bundle):
    result, requests, waits = call(bundle, lambda _: httpx.Response(429, json={'error': {'code': 'unsupported_parameter'}}))
    assert result['status'] == 'FAIL' and len(requests) == 1 and not waits


@pytest.mark.parametrize('failure', ['metadata', 'wrong_provider', 'not_selected', 'malformed_metadata', 'model',
                                    'refusal', 'truncation', 'finish', 'json', 'duplicate', 'schema', 'usage', 'envelope'])
def test_response_contract_failure_not_retried(bundle, failure):
    data = envelope()
    message = data['choices'][0]['message']
    if failure == 'metadata':
        del data['openrouter_metadata']
    elif failure == 'wrong_provider':
        data['openrouter_metadata']['endpoints']['available'][0]['provider'] = 'other'
    elif failure == 'not_selected':
        data['openrouter_metadata']['endpoints']['available'][0]['selected'] = False
    elif failure == 'malformed_metadata':
        data['openrouter_metadata'] = []
    elif failure == 'model':
        data['model'] = 'different'
    elif failure == 'refusal':
        message['refusal'] = 'mock refusal'
    elif failure == 'truncation':
        data['choices'][0]['finish_reason'] = 'length'
    elif failure == 'finish':
        del data['choices'][0]['finish_reason']
    elif failure in ('json', 'duplicate', 'schema'):
        message['content'] = {'json': '{', 'duplicate': '{"low":{},"low":{}}', 'schema': '{}'}[failure]
    elif failure == 'usage':
        data['usage']['prompt_tokens'] = -1
    response = httpx.Response(200, text='not JSON') if failure == 'envelope' else httpx.Response(200, json=data)
    result, requests, waits = call(bundle, lambda _: response)
    assert result['status'] == 'FAIL' and len(requests) == 1 and not waits
    attempt = result['attempts'][0]
    assert attempt['raw_response'] and attempt['failure_reason']
    if failure in ('json', 'duplicate'):
        assert attempt['parse_status'] == 'failed'
    if failure == 'schema':
        assert attempt['schema_status'] == 'failed'


def test_success_preserves_provenance_optional_nulls(bundle):
    result, requests, waits = call(bundle, lambda _: httpx.Response(200, json=envelope(), headers={'x-request-id': 'request-mock'}))
    assert result['status'] == 'PASS' and len(requests) == 1 and not waits
    attempt = result['attempts'][0]
    assert attempt['request_id'] == 'request-mock' and attempt['response_id'] == 'completion-mock'
    assert attempt['observed_selected_provider'] == 'openai'
    assert attempt['usage'] == dict(prompt_tokens=12, completion_tokens=51, total_tokens=None,
                                   reasoning_tokens=None, cached_tokens=None, cost=None)
    assert attempt['parse_status'] == attempt['schema_status'] == 'passed'
    assert requests[0].headers['x-openrouter-metadata'] == 'enabled'
    assert result['semantic_qualification'] == 'NOT_ASSESSED'
    assert result['wire_request_sha256'] == p.digest(requests[0].content)


def test_optional_usage_and_response_id_not_request_id(bundle):
    data = envelope()
    data['usage'].update(cost=0.1, total_tokens=63, completion_tokens_details={'reasoning_tokens': 7},
                         prompt_tokens_details={'cached_tokens': 4})
    result, _, _ = call(bundle, lambda _: httpx.Response(200, json=data))
    attempt = result['attempts'][0]
    assert attempt['request_id'] is None
    assert attempt['usage']['reasoning_tokens'] == 7 and attempt['usage']['cached_tokens'] == 4
    assert attempt['usage']['cost'] == 0.1


def test_deadline_bounds_whole_attempt():
    cancelled = []
    class SlowClient:
        async def post(self, *args, **kwargs):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(p.post_with_deadline(SlowClient(), b'{}', {}, 0.005))
    assert cancelled == [True]


def test_deadline_retries_are_auditable(bundle, monkeypatch):
    deadlines = []
    async def expired(client, wire, headers, seconds):
        deadlines.append(seconds)
        raise asyncio.TimeoutError()
    monkeypatch.setattr(p, 'post_with_deadline', expired)
    result, requests, waits = call(bundle, lambda _: pytest.fail('Unexpected send'))
    assert deadlines == [300, 300, 300] and waits == [1, 2] and requests == []
    assert all(a['processing_or_charge_uncertain'] for a in result['attempts'])


@pytest.mark.parametrize('fail_first', [False, True])
def test_mock_run_sequential_stop_and_archive(bundle, monkeypatch, tmp_path, fail_first):
    monkeypatch.setattr(p, 'source_commit', lambda clean=False: bundle['provenance']['source_commit'])
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body['model'])
        slot = next(s for s in p.SLOTS if s['model'] == body['model'])
        return httpx.Response(400, json={'error': 'unsupported'}) if fail_first else httpx.Response(200, json=envelope(slot))
    def factory(**kwargs):
        assert kwargs == {'trust_env': False, 'follow_redirects': False}
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = tmp_path / 'mock-attempt'
    result = asyncio.run(p.execute_probe(mock_open_bundle(bundle), 'mock-secret', out, client_factory=factory))
    assert seen == [s['model'] for s in p.SLOTS[:1 if fail_first else 2]]
    assert result['status'] == ('FAIL' if fail_first else 'PASS')
    assert result['logical_calls'][1]['status'] == ('BLOCKED' if fail_first else 'PASS')
    raw = (out / 'probe.json').read_bytes()
    assert b'mock-secret' not in raw and b'Authorization' not in raw
    assert (out / 'SHA256SUMS').read_text().split()[0] == p.digest(raw)
    assert json.loads(raw)['provenance'] == bundle['provenance']
    with pytest.raises(FileExistsError):
        asyncio.run(p.execute_probe(mock_open_bundle(bundle), 'mock-secret', out, client_factory=lambda **kwargs: pytest.fail('Overwrite sent request')))


def test_maximum_six_attempts(bundle, monkeypatch, tmp_path):
    monkeypatch.setattr(p, 'source_commit', lambda clean=False: bundle['provenance']['source_commit'])
    original = p.probe_call
    waits = []
    async def sleep(delay):
        waits.append(delay)
    async def wrapped(*args):
        return await original(*args, sleep=sleep)
    monkeypatch.setattr(p, 'probe_call', wrapped)
    seen = []
    def handler(request):
        seen.append(json.loads(request.content)['model'])
        slot = next(s for s in p.SLOTS if s['model'] == seen[-1])
        return httpx.Response(200, json=envelope(slot)) if len(seen) % 3 == 0 else httpx.Response(503)
    result = asyncio.run(p.execute_probe(mock_open_bundle(bundle), 'mock-secret', tmp_path / 'attempt',
                        client_factory=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler))))
    assert result['status'] == 'PASS' and len(seen) == 6 and waits == [1, 2, 1, 2]


def test_secret_redaction_and_no_overwrite(tmp_path):
    result = {'Authorization': 'Bearer secret-value', 'nested': {'api_key': 'secret-value'},
              'raw_response': 'echo secret-value\nAuthorization: Bearer another-value\nend'}
    p.archive(tmp_path, result, 'secret-value')
    text = (tmp_path / 'probe.json').read_text()
    assert 'secret-value' not in text and 'another-value' not in text and 'Authorization' not in text
    with pytest.raises(FileExistsError):
        p.archive(tmp_path, result, 'secret-value')


def test_dirty_worktree_refused_before_output(bundle, monkeypatch, tmp_path):
    def git(args, **kwargs):
        class Result:
            stdout = ' M dirty-file\n'
        assert 'status' in args
        return Result()
    monkeypatch.setattr(p.subprocess, 'run', git)
    with pytest.raises(ValueError, match='clean worktree'):
        asyncio.run(p.execute_probe(mock_open_bundle(bundle), 'mock-secret', tmp_path / 'attempt'))
    assert not (tmp_path / 'attempt').exists()


def test_unexpected_transport_exception_preserves_attempt(bundle):
    def broken(_):
        raise RuntimeError('unexpected mock failure')
    result, requests, waits = call(bundle, broken)
    assert result['status'] == 'FAIL' and len(requests) == 1 and not waits
    assert result['attempts'][0]['error_type'] == 'RuntimeError'


@pytest.mark.parametrize('usage', [None, {}, {'prompt_tokens': 12},
                                  {'completion_tokens': 51, 'cost': None},
                                  {'prompt_tokens': None, 'completion_tokens_details': None}])
def test_missing_or_partial_usage_remains_unknown(bundle, usage):
    data = envelope()
    if usage is None:
        del data['usage']
    else:
        data['usage'] = usage
    result, requests, waits = call(bundle, lambda _: httpx.Response(200, json=data))
    assert result['status'] == 'PASS' and len(requests) == 1 and not waits
    recorded = result['attempts'][0]['usage']
    assert recorded == {key: (usage or {}).get(key) for key in recorded}
    assert all(value is None for key, value in recorded.items() if key not in (usage or {}))


@pytest.mark.parametrize('field', ['prompt_tokens', 'completion_tokens', 'total_tokens',
                                  'reasoning_tokens', 'cached_tokens', 'cost'])
@pytest.mark.parametrize('bad', [-1, True, '12', [], {}])
def test_malformed_present_usage_fails_without_retry(bundle, field, bad):
    data = envelope()
    if field == 'reasoning_tokens':
        data['usage']['completion_tokens_details'] = {field: bad}
    elif field == 'cached_tokens':
        data['usage']['prompt_tokens_details'] = {field: bad}
    else:
        data['usage'][field] = bad
    result, requests, waits = call(bundle, lambda _: httpx.Response(200, json=data))
    assert result['status'] == 'FAIL' and len(requests) == 1 and not waits
    assert 'Malformed usage' in result['failure_reason']
    assert result['attempts'][0]['usage'][field] == bad


@pytest.mark.parametrize('usage', [[], 'wrong', {'completion_tokens_details': []},
                                  {'prompt_tokens_details': 'wrong'}, {'total_tokens': 1.5}])
def test_malformed_usage_containers_and_fractional_count(bundle, usage):
    data = envelope()
    data['usage'] = usage
    result, requests, waits = call(bundle, lambda _: httpx.Response(200, json=data))
    assert result['status'] == 'FAIL' and len(requests) == 1 and not waits


def test_nonfinite_cost_fails_provenance_validation(bundle):
    data = envelope()
    data['usage']['cost'] = float('inf')
    attempt = {'usage': {k: None for k in ('prompt_tokens', 'completion_tokens', 'total_tokens',
                                          'reasoning_tokens', 'cached_tokens', 'cost')}}
    p.response_evidence(attempt, data)
    with pytest.raises(ValueError, match='Malformed usage cost'):
        p.inspect_response(attempt, data, p.request_body(bundle, p.SLOTS[0]))


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    repo = tmp_path / 'repository'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null',
                               '-c', 'commit.gpgsign=false', '-c', 'user.name=Offline Test',
                               '-c', 'user.email=offline@example.invalid', *args],
                              check=True, capture_output=True, text=True).stdout.strip()
    git('init')
    (repo / 'experiments').mkdir()
    (repo / 'experiments/probe_generators.py').write_text('# Tracked test placeholder\n')
    (repo / 'tracked.txt').write_text('initial\n')
    (repo / '.gitignore').write_text('cache/\n')
    git('add', '.')
    git('commit', '-m', 'Temporary offline fixture')
    monkeypatch.setattr(p, 'ROOT', repo)
    return repo, git


@pytest.mark.parametrize('state', ['clean', 'ignored', 'modified', 'staged', 'untracked'])
def test_real_git_cleanliness_before_directory_or_client(bundle, git_repo, tmp_path, state):
    repo, git = git_repo
    bundle['provenance']['source_commit'] = git('rev-parse', 'HEAD')
    if state in ('modified', 'staged'):
        (repo / 'tracked.txt').write_text('changed\n')
        if state == 'staged':
            git('add', 'tracked.txt')
    elif state == 'untracked':
        (repo / 'new-input.json').write_text('{}\n')
    elif state == 'ignored':
        (repo / 'cache').mkdir()
        (repo / 'cache/harmless').write_text('cache\n')
    opened, requests = [], []
    def handler(request):
        requests.append(request)
        slot = next(s for s in p.SLOTS if s['model'] == json.loads(request.content)['model'])
        return httpx.Response(200, json=envelope(slot))
    def factory(**kwargs):
        opened.append(True)
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))
    output = tmp_path / 'mock-result'
    if state in ('clean', 'ignored'):
        result = asyncio.run(p.execute_probe(mock_open_bundle(bundle), 'mock-secret', output, client_factory=factory))
        assert result['status'] == 'PASS' and opened == [True] and len(requests) == 2
        assert result['provenance']['source_commit'] == git('rev-parse', 'HEAD')
    else:
        with pytest.raises(ValueError, match='clean worktree'):
            asyncio.run(p.execute_probe(mock_open_bundle(bundle), 'mock-secret', output, client_factory=factory))
        assert not output.exists() and not opened and not requests


def test_runner_must_be_tracked_even_with_clean_tree(git_repo):
    repo, git = git_repo
    git('rm', 'experiments/probe_generators.py')
    git('commit', '-m', 'Temporary fixture without tracked runner')
    assert git('status', '--porcelain') == ''
    with pytest.raises(subprocess.CalledProcessError):
        p.source_commit(clean=True)


@pytest.mark.parametrize('removed_control,value', [('temperature', 0), ('top_p', 1)])
def test_removed_sampling_controls_rejected_in_config(bundle, tmp_path, removed_control, value):
    bundle['config']['generation'][removed_control] = value
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(bundle['config']))
    with pytest.raises(ValueError, match='Unexpected probe setting: generation'):
        p.load_bundle(path)


def mock_open_bundle(bundle):
    """Exercise preserved execution machinery with mocks, never reopen the config."""
    opened = deepcopy(bundle)
    opened['config']['status'] = 'MOCK_ONLY'
    return opened


def test_closed_config_refuses_execution_before_side_effects(bundle, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('Closed execution crossed boundary')
    monkeypatch.setattr(p, 'source_commit', forbidden)
    out = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match='CLOSED/PASS'):
        asyncio.run(p.execute_probe(bundle, 'mock-secret', out, client_factory=forbidden))
    assert not out.exists()


def test_closed_cli_does_not_read_key_or_execute(monkeypatch, capsys):
    class Environment(dict):
        def get(self, key, default=None):
            if key == 'OPENROUTER_API_KEY':
                pytest.fail('Closed CLI read key')
            return super().get(key, default)
    monkeypatch.setattr(p.os, 'environ', Environment(p.os.environ))
    with pytest.raises(SystemExit) as exc:
        p.main(['--execute', '--confirm-spend'])
    assert exc.value.code == 2
    assert 'CLOSED/PASS' in capsys.readouterr().err
