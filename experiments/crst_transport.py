"""Backbone transport for the CRST Small Pilot: the qualified Model Qualification behavior, per logical request.

One logical request is one stateless chat call. Infrastructure retries are physical attempts inside it and never
add logical calls. Raw responses, usage, latency and cost are recorded per physical attempt.
"""
import hashlib
import json
import time
from datetime import datetime, timezone

import httpx

import qualify_model as qm

USAGE_KEYS = ('prompt_tokens', 'completion_tokens', 'total_tokens', 'cost')


class InfrastructureFailure(Exception):
    """No usable HTTP response after the frozen retry policy; not a model decision."""


class RoutingViolation(Exception):
    """The observed provider or model differs from the pinned backbone; not a model decision."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def usage_of(envelope):
    usage = envelope.get('usage') if isinstance(envelope, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get('prompt_tokens_details')
    details = details if isinstance(details, dict) else {}
    return {**{key: usage.get(key) for key in USAGE_KEYS}, 'cached_tokens': details.get('cached_tokens')}


def call_backbone(client, config, body, *, sleep=time.sleep, clock=time.monotonic):
    """POST one logical request. Returns the response record, or raises on infrastructure or routing failure.

    The record always carries every physical attempt; a raised exception carries the record as `.record`.
    """
    transport = config['transport']
    record = {'request_sha256': sha256(canonical(body)), 'request_status': 'failed', 'content': None,
              'usage': None, 'cost': None, 'latency_seconds': None, 'finish_reason': None, 'routing_ok': None,
              'accounting_ok': None, 'attempts': []}
    started = clock()
    for number in range(transport['max_retries'] + 1):
        attempt = {'physical_attempt': number + 1, 'started_at': datetime.now(timezone.utc).isoformat(),
                   'http_status': None, 'error_type': None, 'requested_model': body['model'],
                   'requested_provider_endpoint': qm.PROVIDER, 'returned_model': None,
                   'openrouter_metadata': None, 'request_id': None, 'response_id': None, 'service_tier': None,
                   'finish_reason': None, 'raw_response': None, 'response_sha256': None, 'usage': None,
                   'latency_seconds': None, 'will_retry': False}
        record['attempts'].append(attempt)
        attempt_started = clock()
        response, envelope, error = None, None, None
        try:
            response = client.post(qm.URL, json=body, headers={'X-OpenRouter-Metadata': 'enabled'},
                                   timeout=transport['timeout_seconds'])
            attempt.update(http_status=response.status_code, request_id=response.headers.get('x-request-id'),
                           raw_response=response.text,
                           response_sha256=hashlib.sha256(response.content).hexdigest())
            try:
                envelope = response.json()
            except ValueError:
                envelope = None
            if isinstance(envelope, dict):
                attempt.update(returned_model=envelope.get('model'),
                               openrouter_metadata=envelope.get('openrouter_metadata'),
                               response_id=envelope.get('id'), service_tier=envelope.get('service_tier'),
                               usage=usage_of(envelope))
        except httpx.RequestError as exc:
            error = exc
            attempt['error_type'] = type(exc).__name__
        attempt['latency_seconds'] = clock() - attempt_started
        again = qm.retryable(config, status=attempt['http_status'], error=error)
        attempt['will_retry'] = again and number < transport['max_retries']
        if attempt['will_retry']:
            sleep(transport['retry_backoff_seconds'][number])
            continue
        break
    record['latency_seconds'] = clock() - started
    if response is None or not response.is_success or not isinstance(envelope, dict):
        failure = InfrastructureFailure(f'No usable response after {len(record["attempts"])} physical attempts '
                                        f'(last HTTP status {attempt["http_status"]}, {attempt["error_type"]})')
        failure.record = record
        raise failure
    record['request_status'] = 'success'
    record['usage'] = attempt['usage']
    record['cost'] = attempt['usage']['cost']
    record['accounting_ok'] = all(type(attempt['usage'][k]) is int and attempt['usage'][k] >= 0
                                  for k in ('prompt_tokens', 'completion_tokens'))
    record['routing_ok'] = qm.routing_ok(body, attempt['openrouter_metadata'], attempt['returned_model'])
    try:
        choice = envelope['choices'][0]
        record['finish_reason'] = attempt['finish_reason'] = choice.get('finish_reason')
        content = choice['message']['content']
        record['content'] = content if isinstance(content, str) else None
    except (KeyError, IndexError, TypeError, AttributeError):
        record['content'] = None
    if not record['routing_ok']:
        violation = RoutingViolation('Observed provider/model differs from the pinned backbone')
        violation.record = record
        raise violation
    return record


def make_ask(client, config, build_body, on_record, *, sleep=time.sleep, clock=time.monotonic):
    """`ask(request)` for crst_policies.run_policy. `on_record(request, body, response)` archives each request."""
    def ask(request):
        body = build_body(request)
        try:
            response = call_backbone(client, config, body, sleep=sleep, clock=clock)
        except (InfrastructureFailure, RoutingViolation) as exc:
            on_record(request, body, exc.record)
            raise
        on_record(request, body, response)
        return response
    return ask
