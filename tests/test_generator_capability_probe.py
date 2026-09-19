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


# --- Predeclared fallback candidate profile (Terra/Opus) ---

def test_primary_profile_unchanged_by_default(bundle):
    """The PRIMARY profile constant and its default load_bundle()/preview() behavior are untouched."""
    assert p.SLOTS == [dict(logical_call_id='G1', model='openai/gpt-5.6-sol', provider_order=['openai']),
                       dict(logical_call_id='G2', model='anthropic/claude-sonnet-5', provider_order=['anthropic'])]
    assert p.load_bundle()['config'] == bundle['config']
    prev = p.preview(bundle)
    assert prev['status'] == 'CAPABILITY_PROBE_CLOSED_PASS' and prev['candidate_profile'] == 'PRIMARY'
    assert prev['execution_package'] == 'FROZEN' and prev['successful_attempt'] == 'attempt-02'
    assert [r['requested_model'] for r in prev['requests']] == ['openai/gpt-5.6-sol', 'anthropic/claude-sonnet-5']


def test_fallback_profile_identities_and_package():
    slots = p.FALLBACK_SLOTS
    assert [(s['logical_call_id'], s['model'], s['provider_order']) for s in slots] == [
        ('G1', 'openai/gpt-5.6-terra', ['openai']), ('G2', 'anthropic/claude-opus-5', ['anthropic'])]
    profile = p.PROFILES['fallback']
    assert profile['slots'] == slots and profile['config_path'] == p.FALLBACK_CONFIG
    assert profile['status'] != 'CLOSED' and profile['capability_result'] != 'PASS'  # Capability is recorded per slot.
    bundle = p.load_bundle(profile['config_path'], slots=slots, status=profile['status'],
                           capability_result=profile['capability_result'],
                           successful_attempt=profile['successful_attempt'],
                           execution_package=profile['execution_package'],
                           execution_compatibility=profile['execution_compatibility'])
    for slot in slots:
        body = p.request_body(bundle, slot)
        assert body['model'] == slot['model'] and body['provider']['order'] == slot['provider_order']
        assert body['provider']['allow_fallbacks'] is False and body['provider']['require_parameters'] is True
        assert not {'temperature', 'top_p', 'tools'} & body.keys()
        assert body['reasoning'] == {'effort': 'low'} and body['max_tokens'] == 16384
        assert body['response_format']['json_schema']['strict'] is True


def test_fallback_capability_preview_offline_two_calls_terra_then_opus(monkeypatch, tmp_path, capsys):
    """Fallback preview: no network, no output directory, exactly 2 calls, Terra then Opus, no key read."""
    def forbidden(*args, **kwargs):
        pytest.fail('Execution entered by fallback preview')
    monkeypatch.setattr(p, 'execute_probe', forbidden)
    class Environment(dict):
        def get(self, key, default=None):
            if key == 'OPENROUTER_API_KEY':
                pytest.fail('Fallback preview read API key')
            return super().get(key, default)
    monkeypatch.setattr(p.os, 'environ', Environment(p.os.environ))
    output = tmp_path / 'must-not-exist'
    assert p.main(['--profile', 'fallback', '--output-directory', str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['candidate_profile'] == 'FALLBACK'
    assert result['status'] == 'CAPABILITY_PROBE_FALLBACK_NOT_EXECUTED'
    assert result['execution_package'] == 'UNDER_DEVELOPMENT' and result['successful_attempt'] is None
    assert result['expected_logical_calls'] == 2 and result['maximum_physical_inference_attempts'] == 6
    assert [r['logical_call_id'] for r in result['requests']] == ['G1', 'G2']
    assert [r['requested_model'] for r in result['requests']] == ['openai/gpt-5.6-terra', 'anthropic/claude-opus-5']
    assert [r['requested_provider_order'] for r in result['requests']] == [['openai'], ['anthropic']]
    assert len({r['wire_request_sha256'] for r in result['requests']}) == 2
    assert not output.exists()
    assert p.main([]) == 0  # Default --profile is still primary, unaffected.
    assert json.loads(capsys.readouterr().out)['candidate_profile'] == 'PRIMARY'


def test_fallback_probe_never_reopens_or_mutates_primary_evidence():
    """Building/previewing the fallback profile does not touch the CLOSED primary config or its slots."""
    before = p.CONFIG.read_bytes()
    primary_bundle = p.load_bundle()
    assert primary_bundle['config']['status'] == 'CLOSED' and primary_bundle['config']['capability_result'] == 'PASS'
    fallback_profile = p.PROFILES['fallback']
    p.load_bundle(fallback_profile['config_path'], slots=fallback_profile['slots'],
                  status=fallback_profile['status'], capability_result=fallback_profile['capability_result'],
                  successful_attempt=fallback_profile['successful_attempt'],
                  execution_package=fallback_profile['execution_package'],
                  execution_compatibility=fallback_profile['execution_compatibility'])
    assert p.CONFIG.read_bytes() == before  # The CLOSED primary config file is untouched.
    assert p.SLOTS == [dict(logical_call_id='G1', model='openai/gpt-5.6-sol', provider_order=['openai']),
                       dict(logical_call_id='G2', model='anthropic/claude-sonnet-5', provider_order=['anthropic'])]


def test_single_slot_capability_preview_g1_only_terra(monkeypatch, tmp_path, capsys):
    """--profile fallback --slot G1: exactly 1 Terra logical call, offline, no key, no directory."""
    def forbidden(*args, **kwargs):
        pytest.fail('Execution entered by single-slot preview')
    monkeypatch.setattr(p, 'execute_probe', forbidden)
    class Environment(dict):
        def get(self, key, default=None):
            if key == 'OPENROUTER_API_KEY':
                pytest.fail('Single-slot preview read API key')
            return super().get(key, default)
    monkeypatch.setattr(p.os, 'environ', Environment(p.os.environ))
    output = tmp_path / 'must-not-exist'
    assert p.main(['--profile', 'fallback', '--slot', 'G1', '--output-directory', str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['candidate_profile'] == 'FALLBACK'
    assert result['expected_logical_calls'] == 1 and result['maximum_physical_inference_attempts'] == 3
    assert [r['logical_call_id'] for r in result['requests']] == ['G1']
    assert [r['requested_model'] for r in result['requests']] == ['openai/gpt-5.6-terra']
    assert [r['requested_provider_order'] for r in result['requests']] == [['openai']]
    assert not output.exists()


def test_single_slot_capability_preview_g2_only_opus(tmp_path, capsys):
    """--profile fallback --slot G2: exactly 1 Opus logical call, symmetric to G1's."""
    output = tmp_path / 'must-not-exist'
    assert p.main(['--profile', 'fallback', '--slot', 'G2', '--output-directory', str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['expected_logical_calls'] == 1
    assert [r['logical_call_id'] for r in result['requests']] == ['G2']
    assert [r['requested_model'] for r in result['requests']] == ['anthropic/claude-opus-5']
    assert [r['requested_provider_order'] for r in result['requests']] == [['anthropic']]
    assert not output.exists()


def test_single_slot_preview_request_package_unchanged(bundle):
    """The single-slot request body is byte-identical to that candidate's entry within the full,
    two-slot preview -- restricting to one slot changes only which calls are planned, not their
    content."""
    fallback_profile = p.PROFILES['fallback']
    fallback_bundle = p.load_bundle(fallback_profile['config_path'], slots=fallback_profile['slots'],
                                    status=fallback_profile['status'],
                                    capability_result=fallback_profile['capability_result'],
                                    successful_attempt=fallback_profile['successful_attempt'],
                                    execution_package=fallback_profile['execution_package'],
                                    execution_compatibility=fallback_profile['execution_compatibility'])
    full = p.preview(fallback_bundle, slots=fallback_profile['slots'], profile_name='FALLBACK')
    g1_only = p.preview(fallback_bundle, slots=[fallback_profile['slots'][0]], profile_name='FALLBACK')
    assert g1_only['requests'][0] == full['requests'][0]
    assert g1_only['expected_logical_calls'] == 1 and full['expected_logical_calls'] == 2


def test_default_two_slot_probe_behavior_unaffected_by_slot_support(monkeypatch, tmp_path, capsys):
    """Omitting --slot still previews the full, historical two-candidate profile unchanged."""
    output = tmp_path / 'must-not-exist'
    assert p.main(['--output-directory', str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'CAPABILITY_PROBE_CLOSED_PASS' and result['candidate_profile'] == 'PRIMARY'
    assert result['expected_logical_calls'] == 2 and result['maximum_physical_inference_attempts'] == 6
    assert [r['requested_model'] for r in result['requests']] == ['openai/gpt-5.6-sol', 'anthropic/claude-sonnet-5']


def test_slot_capability_generic_lookup_for_both_profiles(bundle):
    """slot_capability() works generically: the primary (no `slots:` section) derives uniformly
    from its whole-profile CLOSED/PASS status; the fallback profile reports its real per-slot mix."""
    for slot in p.SLOTS:
        capability = p.slot_capability('primary', slot)
        assert capability['status'] == 'CLOSED' and capability['capability_result'] == 'PASS'
        assert capability['model'] == slot['model']
    terra_capability = p.slot_capability('fallback', p.FALLBACK_SLOTS[0])
    opus_capability = p.slot_capability('fallback', p.FALLBACK_SLOTS[1])
    assert terra_capability['status'] == 'CLOSED' and terra_capability['capability_result'] == 'PASS'
    assert opus_capability['status'] == 'CLOSED' and opus_capability['capability_result'] == 'FAIL'
    assert opus_capability['reason'] == 'provider-policy refusal'


def test_slot_capability_mismatched_candidate_identity_has_no_evidence():
    """A hypothetical future/replaced candidate occupying G2 has no recorded evidence at all -- the
    stale Opus entry is never silently reused for a different model."""
    hypothetical = dict(logical_call_id='G2', model='anthropic/claude-hypothetical-next',
                        provider_order=['anthropic'])
    capability = p.slot_capability('fallback', hypothetical)
    assert capability['status'] == 'OPEN' and capability['capability_result'] == 'NOT_ASSESSED'
    assert capability['evidence_attempt'] is None and capability['evidence_sha256'] is None


def test_execute_probe_refuses_to_reopen_already_closed_slot(monkeypatch, tmp_path):
    """Even with the whole-profile CLOSED guard bypassed (mock_open_bundle), execute_probe still
    refuses to reopen a per-slot CLOSED candidate (Terra CLOSED/PASS) when given its profile_name --
    a no-automatic-reprobe safeguard beyond the whole-profile check."""
    fallback_profile = p.PROFILES['fallback']
    fallback_bundle = p.load_bundle(fallback_profile['config_path'], slots=fallback_profile['slots'],
                                    status=fallback_profile['status'],
                                    capability_result=fallback_profile['capability_result'],
                                    successful_attempt=fallback_profile['successful_attempt'],
                                    execution_package=fallback_profile['execution_package'],
                                    execution_compatibility=fallback_profile['execution_compatibility'])
    def forbidden(*args, **kwargs):
        pytest.fail('Reopen-a-closed-slot execution crossed boundary')
    out = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match=r'G1.*already CLOSED/PASS'):
        asyncio.run(p.execute_probe(fallback_bundle, 'mock-secret', out, slots=[p.FALLBACK_SLOTS[0]],
                                    profile_name='fallback', client_factory=forbidden))
    assert not out.exists()


def test_execute_probe_without_profile_name_skips_per_slot_reopening_check(monkeypatch, tmp_path):
    """Backward compatibility: existing direct callers that never pass profile_name are unaffected
    by the new per-slot reopening guard (it is opt-in via that parameter)."""
    fallback_profile = p.PROFILES['fallback']
    fallback_bundle = p.load_bundle(fallback_profile['config_path'], slots=fallback_profile['slots'],
                                    status=fallback_profile['status'],
                                    capability_result=fallback_profile['capability_result'],
                                    successful_attempt=fallback_profile['successful_attempt'],
                                    execution_package=fallback_profile['execution_package'],
                                    execution_compatibility=fallback_profile['execution_compatibility'])
    monkeypatch.setattr(p, 'source_commit', lambda clean=False: fallback_bundle['provenance']['source_commit'])
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401)), **kwargs)
    out = tmp_path / 'attempt'
    result = asyncio.run(p.execute_probe(fallback_bundle, 'mock-secret', out, slots=[p.FALLBACK_SLOTS[0]],
                                         client_factory=factory))
    assert result['status'] == 'FAIL'  # Reached real per-call execution, not refused up front.
    assert out.exists()


# --- Second-level G2 candidate configuration (docs/generator-qualification.md Sec. 12): identity, route
# and package for anthropic/claude-fable-5.1. These tests read config and build requests offline.

SECOND_LEVEL_G2_CONFIG = p.ROOT / 'configs/generator-capability-probe-second-level-g2.yaml'
SECOND_LEVEL_G2_CONFIG_SHA256 = 'fb2c74eec9fea2ab49cee00e76cbe84ec7ce0fe2464e80bf84d157e82ec56180'
ATTEMPT_04 = p.ROOT / 'results/generator-capability-probe/attempt-04'
ATTEMPT_04_PROBE_SHA256 = '4821739b668e2b5894a28e8f345588dd9869aa92420384cc10120d637fcc9365'
FALLBACK_CONFIG_SHA256 = '1316b2b1f3a7f5f15f64d5b3b2ef379c60f96edddff8b5f62bf0e712d7099e1b'
FABLE_SLOT = dict(logical_call_id='G2', model='anthropic/claude-fable-5.1', provider_order=['anthropic'])


def second_level_bundle():
    return p.load_bundle(SECOND_LEVEL_G2_CONFIG, slots=[FABLE_SLOT], status='OPEN',
                         capability_result='NOT_ASSESSED', successful_attempt=None,
                         execution_package='UNDER_DEVELOPMENT', execution_compatibility='UNVERIFIED')


def test_second_level_g2_candidate_identity_and_first_party_route_frozen():
    config = yaml.safe_load(SECOND_LEVEL_G2_CONFIG.read_text(encoding='utf-8'))
    model = config['candidate_selection']['candidate']
    assert model == config['slots']['G2']['model'] == config['logical_calls'][0]['model'] == 'anthropic/claude-fable-5.1'
    # Exact immutable identifier: no moving alias, no variant suffix.
    assert not model.startswith('~') and ':' not in model and 'latest' not in model and 'batch' not in model
    assert model.startswith('anthropic/') and model not in {'anthropic/claude-sonnet-5', 'anthropic/claude-opus-5'}
    # First-party Anthropic via the repository's existing pinning; no provider fallback or auto-routing.
    assert config['logical_calls'] == [dict(logical_call_id='G2', model=model, provider_order=['anthropic'])]
    assert config['allow_fallbacks'] is False and config['require_parameters'] is True
    selection = config['candidate_selection']
    assert selection['frozen_before_any_output'] is True and selection['frozen_on'] == '2026-09-19'
    assert selection['backup_list'].startswith('none adopted') and 'no retry-until-pass' in selection['on_capability_fail']
    assert 'benchmark' not in selection['basis'].lower() and 'prestige' not in selection['basis'].lower()


def test_second_level_g2_config_is_pinned_and_valid_under_the_frozen_loader():
    assert p.file_hash(SECOND_LEVEL_G2_CONFIG) == SECOND_LEVEL_G2_CONFIG_SHA256
    bundle = second_level_bundle()  # Raises on any deviation from the frozen package/contract/input.
    assert bundle['config']['output_directory'] is None  # No attempt directory scheduled or created.


def test_second_level_g2_package_identical_to_fallback_except_candidate_identity():
    fallback = p.load_bundle(p.FALLBACK_CONFIG, slots=p.FALLBACK_SLOTS, status='OPEN',
                             capability_result='NOT_ASSESSED', successful_attempt=None,
                             execution_package='UNDER_DEVELOPMENT', execution_compatibility='UNVERIFIED')
    for key in ('contract_sha256', 'contract_document_sha256', 'prompt_sha256', 'output_schema_sha256',
                'input_sha256', 'input_identity', 'generation', 'wire_mapping', 'transport', 'allow_fallbacks',
                'require_parameters', 'prompt_version', 'input_contract_version', 'output_schema_version',
                'parameter_semantics', 'execution_mode'):
        assert second_level_bundle()['config'][key] == fallback['config'][key], key
    assert second_level_bundle()['contract'] == fallback['contract'] and second_level_bundle()['input'] == fallback['input']


def test_second_level_g2_profile_resolves_exactly_one_frozen_candidate():
    assert p.SECOND_LEVEL_G2_SLOTS == [FABLE_SLOT] and p.SECOND_LEVEL_G2_CONFIG == SECOND_LEVEL_G2_CONFIG
    profile = p.PROFILES['second_level_g2']
    assert profile['slots'] == [FABLE_SLOT] and profile['config_path'] == SECOND_LEVEL_G2_CONFIG
    assert profile['status'] == 'OPEN' and profile['capability_result'] == 'NOT_ASSESSED'  # Capability is recorded per slot.
    assert profile['successful_attempt'] is None and profile['execution_package'] == 'UNDER_DEVELOPMENT'
    assert sorted(p.PROFILES) == ['fallback', 'primary', 'second_level_g2']
    # Existing profiles are untouched.
    assert [s['model'] for s in p.SLOTS] == ['openai/gpt-5.6-sol', 'anthropic/claude-sonnet-5']
    assert [s['model'] for s in p.FALLBACK_SLOTS] == ['openai/gpt-5.6-terra', 'anthropic/claude-opus-5']


def test_second_level_g2_request_and_offline_capability_preview_identify_only_fable(capsys):
    bundle = second_level_bundle()
    body = p.request_body(bundle, FABLE_SLOT)
    assert body['model'] == 'anthropic/claude-fable-5.1'
    assert body['provider'] == {'order': ['anthropic'], 'allow_fallbacks': False, 'require_parameters': True}
    assert not {'temperature', 'top_p', 'tools'} & body.keys() and body['reasoning'] == {'effort': 'low'}
    assert body['max_tokens'] == 16384 and body['response_format']['json_schema']['strict'] is True
    primary_sonnet_body = p.request_body(p.load_bundle(), p.SLOTS[1])
    assert {**primary_sonnet_body, 'model': body['model']} == body  # Same package; only identity differs.
    for argv in (['--profile', 'second_level_g2'], ['--profile', 'second_level_g2', '--slot', 'G2']):
        assert p.main(argv) == 0  # The official CLI preview: offline (network is blocked by the fixture).
        shown = json.loads(capsys.readouterr().out)
        assert shown['status'] == 'CAPABILITY_PROBE_SECOND_LEVEL_G2_NOT_EXECUTED'
        assert shown['candidate_profile'] == 'SECOND_LEVEL_G2' and shown['expected_logical_calls'] == 1
        assert [(r['logical_call_id'], r['requested_model'], r['requested_provider_order'])
                for r in shown['requests']] == [('G2', 'anthropic/claude-fable-5.1', ['anthropic'])]
        assert shown['execution_package'] == 'UNDER_DEVELOPMENT' and shown['successful_attempt'] is None
        assert shown['output_directory'] is None


def test_second_level_g2_cli_rejects_an_empty_slot_selection_and_ungated_execution(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):  # The profile has no G1: never a silent zero-call selection.
        p.main(['--profile', 'second_level_g2', '--slot', 'G1'])
    with pytest.raises(SystemExit):
        p.main(['--profile', 'second_level_g2', '--execute'])  # Needs BOTH --execute and --confirm-spend.
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    output = tmp_path / 'must-not-be-created'
    with pytest.raises(SystemExit):  # Gated execution still requires a key before any side effect.
        p.main(['--profile', 'second_level_g2', '--execute', '--confirm-spend', '--output-directory', str(output)])
    assert not output.exists()


def test_second_level_g2_capability_is_closed_pass_for_the_exact_candidate_only():
    """The per-slot record (the same convention as the fallback profile) closes capability PASS for exactly
    this model, citing Attempt-04; it does not qualify the generator."""
    recorded = p.slot_capability('second_level_g2', FABLE_SLOT)
    assert recorded == {'model': 'anthropic/claude-fable-5.1', 'status': 'CLOSED', 'capability_result': 'PASS',
                        'reason': None, 'evidence_attempt': 'attempt-04',
                        'evidence_path': 'results/generator-capability-probe/attempt-04',
                        'evidence_sha256': ATTEMPT_04_PROBE_SHA256}
    for other in ('anthropic/claude-sonnet-5', 'anthropic/claude-opus-5', 'anthropic/claude-hypothetical-next'):
        got = p.slot_capability('second_level_g2', dict(FABLE_SLOT, model=other))
        assert got['status'] == 'OPEN' and got['capability_result'] == 'NOT_ASSESSED' and got['evidence_sha256'] is None
    config = yaml.safe_load(SECOND_LEVEL_G2_CONFIG.read_text(encoding='utf-8'))
    assert config['generator_status'] == 'CANDIDATE'  # Capability PASS is not Generator Qualification.
    # Profile-level fields stay as the frozen loader expects; the per-slot record is authoritative.
    assert (config['status'], config['capability_result']) == ('OPEN', 'NOT_ASSESSED')


def test_second_level_g2_recorded_evidence_is_attempt_04_and_execution_fields_are_unchanged():
    """The recorded SHA-256 is that of the archived probe.json, which shows a passed single G2 call to the
    frozen candidate; every non-capability field of the config equals the configuration that produced it."""
    assert p.file_hash(ATTEMPT_04 / 'probe.json') == ATTEMPT_04_PROBE_SHA256
    assert (ATTEMPT_04 / 'SHA256SUMS').read_text(encoding='utf-8').split()[0] == ATTEMPT_04_PROBE_SHA256
    archived = json.loads((ATTEMPT_04 / 'probe.json').read_text(encoding='utf-8'))
    assert archived['status'] == 'PASS' and archived['failure_reason'] is None
    assert [(c['logical_call_id'], c['status']) for c in archived['logical_calls']] == [('G2', 'PASS')]
    current = yaml.safe_load(SECOND_LEVEL_G2_CONFIG.read_text(encoding='utf-8'))
    assert {k for k in {*archived['config'], *current} if archived['config'].get(k) != current.get(k)} == {'slots'}
    assert archived['config']['logical_calls'] == current['logical_calls'] == [
        dict(logical_call_id='G2', model='anthropic/claude-fable-5.1', provider_order=['anthropic'])]


def test_closed_second_level_slot_cannot_be_reprobed(monkeypatch, tmp_path):
    """Re-running the probe for the closed slot is refused before any output directory or network client."""
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-must-never-be-sent')
    output = tmp_path / 'must-not-be-created'
    with pytest.raises(ValueError, match=r'capability already CLOSED/PASS; reopening requires adjudication'):
        p.main(['--profile', 'second_level_g2', '--execute', '--confirm-spend', '--output-directory', str(output)])
    assert not output.exists()


def test_closed_candidates_and_their_configs_untouched_by_second_level_freeze():
    assert p.file_hash(p.FALLBACK_CONFIG) == FALLBACK_CONFIG_SHA256
    opus, terra = p.slot_capability('fallback', p.FALLBACK_SLOTS[1]), p.slot_capability('fallback', p.FALLBACK_SLOTS[0])
    assert (opus['status'], opus['capability_result'], opus['reason']) == ('CLOSED', 'FAIL', 'provider-policy refusal')
    assert (terra['status'], terra['capability_result']) == ('CLOSED', 'PASS')
    assert p.SLOTS[1]['model'] == 'anthropic/claude-sonnet-5' and p.FALLBACK_SLOTS[1]['model'] == 'anthropic/claude-opus-5'


@pytest.mark.parametrize('profile', ['second_level_g2', 'fallback'])
def test_execute_without_output_directory_fails_explicitly_before_network(monkeypatch, capsys, profile):
    """These profiles configure output_directory as null, so execution must require --output-directory
    instead of failing later with a TypeError; the check is generic, not specific to one candidate."""
    assert yaml.safe_load(p.PROFILES[profile]['config_path'].read_text(encoding='utf-8'))['output_directory'] is None
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-must-never-be-sent')
    with pytest.raises(SystemExit) as excinfo:
        p.main(['--profile', profile, '--execute', '--confirm-spend'])
    assert excinfo.value.code == 2
    assert '--output-directory is required for this profile when executing' in capsys.readouterr().err


def test_explicit_output_directory_is_accepted_and_preview_needs_none(monkeypatch, tmp_path, capsys):
    calls = []

    async def fake_execute(bundle, key, output, **kwargs):
        calls.append((Path(output), [s['logical_call_id'] for s in kwargs['slots']]))
        return {'status': 'PASS'}
    monkeypatch.setattr(p, 'execute_probe', fake_execute)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-must-never-be-sent')
    output = tmp_path / 'attempt'
    assert p.main(['--profile', 'second_level_g2', '--execute', '--confirm-spend',
                   '--output-directory', str(output)]) == 0
    assert calls == [(output, ['G2'])]
    assert p.main(['--profile', 'second_level_g2']) == 0  # Preview is unaffected.
    assert json.loads(capsys.readouterr().out)['expected_logical_calls'] == 1
