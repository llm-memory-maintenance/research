"""Offline tests of the backbone transport with a mock HTTP transport; no network."""
import json

import httpx
import pytest
import yaml

from crst_common import ROOT, chat_envelope, no_network  # noqa: F401
import crst_transport as tr
import run_crst_pilot as run

MODEL = yaml.safe_load((ROOT / 'configs/model.yaml').read_text())
BODY = run.request_body(MODEL, {'schema': 'answer', 'messages': [{'role': 'system', 'content': 's'},
                                                                  {'role': 'user', 'content': 'u'}]})


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def call(handler, body=BODY):
    sleeps = []
    result = tr.call_backbone(client(handler), MODEL, body, sleep=sleeps.append)
    return result, sleeps


def test_success_records_content_usage_cost_latency_and_routing():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=chat_envelope(BODY, '{"answer":"x"}'), headers={'x-request-id': 'r1'})
    result, sleeps = call(handler)
    assert result['request_status'] == 'success' and result['content'] == '{"answer":"x"}' and sleeps == []
    assert result['usage'] == {'prompt_tokens': 100, 'completion_tokens': 5, 'total_tokens': 105, 'cost': 0.0001,
                               'cached_tokens': 0}
    assert result['cost'] == 0.0001 and result['routing_ok'] is True and result['accounting_ok'] is True
    assert result['finish_reason'] == 'stop' and result['latency_seconds'] >= 0
    [attempt] = result['attempts']
    assert attempt['request_id'] == 'r1' and attempt['http_status'] == 200 and attempt['raw_response']
    assert attempt['response_sha256'] and attempt['returned_model'] == BODY['model']
    assert json.loads(seen[0].content) == BODY and seen[0].headers['x-openrouter-metadata'] == 'enabled'
    assert result['request_sha256'] == tr.sha256(tr.canonical(BODY))


def test_transport_adds_no_conversation_state_and_sends_exactly_the_request():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=chat_envelope(BODY, '{}'))
    for _ in range(2):
        call(handler)
    assert bodies == [BODY, BODY]
    assert not {'conversation', 'session', 'previous_response_id', 'user', 'tools', 'models', 'route'} & BODY.keys()


@pytest.mark.parametrize('status', [408, 429, 500, 502, 503, 504])
def test_retryable_status_retries_inside_one_logical_request(status):
    responses = iter([httpx.Response(status, text='busy'), httpx.Response(200, json=chat_envelope(BODY, '{}'))])
    result, sleeps = call(lambda request: next(responses))
    assert [a['http_status'] for a in result['attempts']] == [status, 200] and sleeps == [1]
    assert [a['will_retry'] for a in result['attempts']] == [True, False] and result['request_status'] == 'success'
    assert result['attempts'][0]['usage'] is None and result['usage']['prompt_tokens'] == 100


def test_network_error_is_retried_and_recorded():
    state = {'n': 0}

    def handler(request):
        state['n'] += 1
        if state['n'] == 1:
            raise httpx.ConnectError('boom')
        return httpx.Response(200, json=chat_envelope(BODY, '{}'))
    result, sleeps = call(handler)
    assert result['attempts'][0]['error_type'] == 'ConnectError' and result['attempts'][0]['http_status'] is None
    assert len(result['attempts']) == 2 and sleeps == [1]


def test_three_failed_attempts_raise_with_all_evidence_and_backoff_1_then_2():
    with pytest.raises(tr.InfrastructureFailure) as failure:
        call(lambda request: httpx.Response(503, text='down'))
    record = failure.value.record
    assert len(record['attempts']) == 3 and record['request_status'] == 'failed' and record['content'] is None
    assert [a['will_retry'] for a in record['attempts']] == [True, True, False]
    assert all(a['raw_response'] == 'down' for a in record['attempts'])


def test_backoff_schedule_is_the_frozen_one():
    sleeps = []
    with pytest.raises(tr.InfrastructureFailure):
        tr.call_backbone(client(lambda request: httpx.Response(503)), MODEL, BODY, sleep=sleeps.append)
    assert sleeps == [1, 2]


def test_non_retryable_status_is_terminal_after_one_attempt():
    with pytest.raises(tr.InfrastructureFailure) as failure:
        call(lambda request: httpx.Response(400, json={'error': 'bad'}))
    assert len(failure.value.record['attempts']) == 1


def test_provider_or_model_mismatch_is_a_routing_violation_with_evidence():
    for kwargs in ({'provider': 'Other'}, {'model': 'meta-llama/other'}):
        with pytest.raises(tr.RoutingViolation) as violation:
            call(lambda request: httpx.Response(200, json=chat_envelope(BODY, '{}', **kwargs)))
        assert violation.value.record['routing_ok'] is False and violation.value.record['attempts']


def test_missing_usage_is_flagged_not_guessed():
    result, _ = call(lambda request: httpx.Response(200, json=chat_envelope(BODY, '{}', usage=False)))
    assert result['accounting_ok'] is False and result['cost'] is None
    assert result['usage']['prompt_tokens'] is None


def test_non_text_content_is_no_content_not_a_repair():
    envelope = chat_envelope(BODY, None)
    result, _ = call(lambda request: httpx.Response(200, json=envelope))
    assert result['content'] is None and result['request_status'] == 'success'
    result, _ = call(lambda request: httpx.Response(200, json={**envelope, 'choices': []}))
    assert result['content'] is None


def test_make_ask_archives_success_and_failure_records():
    archived = []

    def on_record(request, body, response):
        archived.append((request['logical_id'], response['request_status']))
    ok = tr.make_ask(client(lambda r: httpx.Response(200, json=chat_envelope(BODY, '{}'))), MODEL,
                     lambda request: BODY, on_record)
    assert ok({'logical_id': 'a'})['request_status'] == 'success'
    bad = tr.make_ask(client(lambda r: httpx.Response(400)), MODEL, lambda request: BODY, on_record)
    with pytest.raises(tr.InfrastructureFailure):
        bad({'logical_id': 'b'})
    assert archived == [('a', 'success'), ('b', 'failed')]


def test_transport_reuses_the_qualified_model_transport_rules():
    import qualify_model as qm
    assert tr.qm is qm and MODEL['transport']['max_retries'] == 2
    assert MODEL['transport']['retry_status_codes'] == [408, 429, 500, 502, 503, 504]
    assert MODEL['provider']['upstream'] == qm.PROVIDER and MODEL['model']['id'] == qm.MODEL


def test_retry_usage_is_separate_from_logical_usage_in_accounting():
    responses = iter([httpx.Response(503), httpx.Response(200, json=chat_envelope(BODY, '{}'))])
    result, _ = call(lambda request: next(responses))
    record = run.logical_record({'logical_id': 'a'}, BODY, result, policy='M2', scenario='s', variant='low',
                                event='U1', model_config=MODEL)
    assert run.validate_record(record)
    totals = run.account_run([record])
    assert totals['logical_calls'] == 1 and totals['physical_attempts'] == 2
    assert totals['logical_token_usage'] == {'prompt_tokens': 100, 'completion_tokens': 5}
    assert totals['retry_token_usage'] == {'prompt_tokens': 0, 'completion_tokens': 0}
    assert totals['retry_attempts_without_usage'] == 1
