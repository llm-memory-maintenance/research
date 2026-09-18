"""Guarded two-model capability probe. Default invocation is offline preview only."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/generator-capability-probe.yaml'
URL = 'https://openrouter.ai/api/v1/chat/completions'
EVENTS = tuple([f'I{i}' for i in range(1, 8)] + [f'U{i}' for i in range(1, 7)] + ['N1', 'U7', 'N2'])
VARIANTS = ('low', 'medium', 'high')
SCHEDULES = {'low': {7}, 'medium': {1, 3, 5, 7}, 'high': set(range(1, 8))}
SLOTS = [dict(logical_call_id='G1', model='openai/gpt-5.6-sol', provider_order=['openai']),
         dict(logical_call_id='G2', model='anthropic/claude-sonnet-5', provider_order=['anthropic'])]
VERSIONS = {'prompt_version': 'crst-naturalization-prompt/1.1.0',
            'input_contract_version': 'crst-naturalization-input/1.1.0',
            'output_schema_version': 'crst-naturalization-triplet/1.0.0'}
MAPPING = {'max_output_tokens': 'max_tokens', 'reasoning_effort': 'reasoning.effort',
           'output_schema': 'response_format.json_schema.schema', 'strict': 'response_format.json_schema.strict'}
GENERATION = {'reasoning_effort': 'low', 'max_output_tokens': 16384}
TRANSPORT = {'per_attempt_deadline_seconds': 300, 'max_infrastructure_retries': 2,
             'backoff_seconds': [1, 2], 'retryable_http_statuses': [408, 429, 500, 502, 503, 504]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    return digest(Path(path).read_bytes())


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate object key')
        result[key] = value
    return result


def parse_json(text):
    def invalid(_):
        raise ValueError('Nonfinite JSON value')
    return json.loads(text, object_pairs_hook=unique_pairs, parse_constant=invalid)


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected), 'Unexpected/missing object fields')


def nonempty(value):
    require(type(value) is str and bool(value.strip()), 'Expected nonempty string')


def validate_input(data):
    """Exact probe serialization and trajectory checks, not a CRST generator."""
    fields(data, ['domain', 'entities', 'attributes', 'state_keys', 'initial_order', 'question_intent', 'variants'])
    require(data['domain'] == 'Software Configuration', 'Unexpected probe domain')
    entities, attributes = {}, {}
    for name, target, identity, shape in [
        ('entities', entities, 'entity_id', ['entity_id', 'name']),
        ('attributes', attributes, 'attribute_id', ['attribute_id', 'meaning', 'units_or_interpretation'])]:
        require(type(data[name]) is list and bool(data[name]), 'Expected identity list')
        for item in data[name]:
            fields(item, shape)
            for value in item.values():
                nonempty(value)
            require(item[identity] not in target, 'Duplicate identity')
            target[item[identity]] = item
    require(type(data['state_keys']) is list and len(data['state_keys']) == 7, 'Expected seven keys')
    keys, pairs, roles = {}, set(), Counter()
    for item in data['state_keys']:
        fields(item, ['state_key', 'entity_id', 'attribute_id', 'initial_value', 'role'])
        for value in item.values():
            nonempty(value)
        key, pair = item['state_key'], (item['entity_id'], item['attribute_id'])
        require(key not in keys and pair not in pairs, 'Duplicate state key')
        require(pair[0] in entities and pair[1] in attributes, 'Unresolved identity')
        keys[key] = item
        pairs.add(pair)
        roles[item['role']] += 1
    require(roles == Counter(target=1, hard_distractor=1, dedicated_n2_secondary=1,
                             updateable_secondary=4), 'Incorrect roles')
    target = next(k for k, v in keys.items() if v['role'] == 'target')
    n2 = next(k for k, v in keys.items() if v['role'] == 'dedicated_n2_secondary')
    fields(data['initial_order'], EVENTS[:7])
    require(set(data['initial_order'].values()) == set(keys), 'Initial order must cover every key')
    fields(data['question_intent'], ['entity_id', 'attribute_id', 'intent'])
    question = data['question_intent']
    nonempty(question['intent'])
    require((question['entity_id'], question['attribute_id']) ==
            (keys[target]['entity_id'], keys[target]['attribute_id']), 'Wrong Q target')
    fields(data['variants'], VARIANTS)
    final_values = []
    for variant in VARIANTS:
        trajectory = data['variants'][variant]
        require(type(trajectory) is list and len(trajectory) == 16, 'Expected sixteen events')
        state, target_seen, target_updates = {}, set(), set()
        for label, event in zip(EVENTS, trajectory):
            fields(event, ['event', 'state_key', 'current_value', 'semantics'])
            key, value = event['state_key'], event['current_value']
            require(event['event'] == label and key in keys, 'Wrong event order/key')
            nonempty(value)
            if label.startswith('I'):
                require(event['semantics'] == 'initial' and key == data['initial_order'][label]
                        and value == keys[key]['initial_value'], 'Initial-state mismatch')
            elif label.startswith('U'):
                require(event['semantics'] == 'changed_state' and value != state[key], 'Update must change value')
                if key == target:
                    require(value not in target_seen, 'Target value returned')
                    target_updates.add(int(label[1:]))
                else:
                    require(keys[key]['role'] == 'updateable_secondary', 'Protected secondary updated')
            else:
                require(event['semantics'] == 'same_state' and key == (target if label == 'N1' else n2)
                        and value == state[key], 'Incorrect reaffirmation')
            state[key] = value
            if key == target:
                target_seen.add(value)
        require(target_updates == SCHEDULES[variant], 'Wrong target revision schedule')
        final_values.append(state[target])
    require(len(set(final_values)) == 1, 'Final target states differ')


def validate_output(output):
    """Validate this fixed schema's complete shape and nonempty strings locally.

    This is not a general Draft 2020-12 engine or semantic/fidelity validator.
    """
    fields(output, VARIANTS)
    for variant in VARIANTS:
        fields(output[variant], (*EVENTS, 'Q'))
        for value in output[variant].values():
            nonempty(value)


def source_commit(clean=False):
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    if clean:
        # Explicit format and scope: staged, unstaged, untracked, and submodule
        # changes count; ordinary ignored build/cache files do not.
        require(not git('status', '--porcelain=v1', '-z', '--untracked-files=all',
                        '--ignore-submodules=none'), 'Official execution requires a clean worktree')
        git('ls-files', '--error-unmatch', 'experiments/probe_generators.py')
    return git('rev-parse', 'HEAD')


def load_bundle(config_path=CONFIG):
    config_path = Path(config_path)
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    require(type(config) is dict, 'Expected config object')
    expected = dict(execution_mode='standard', logical_calls=SLOTS, allow_fallbacks=False,
                    require_parameters=True, generation=GENERATION, transport=TRANSPORT,
                    wire_mapping=MAPPING, status='CLOSED', capability_result='PASS',
                    successful_attempt='attempt-02', execution_package='FROZEN',
                    execution_compatibility='VERIFIED', output_directory=None, generator_status='CANDIDATE',
                    parameter_semantics='HIDDEN_REASONING_EQUIVALENCE_NOT_CLAIMED', input_purpose='CAPABILITY-PROBE-ONLY',
                    input_domain='Software Configuration', **VERSIONS)
    for key, value in expected.items():
        require(canonical(config.get(key)) == canonical(value), f'Unexpected probe setting: {key}')
    for stem in ('contract', 'contract_document', 'input'):
        require(file_hash(ROOT / config[stem + '_path']) == config[stem + '_sha256'], f'{stem} checksum mismatch')
    contract = parse_json((ROOT / config['contract_path']).read_text(encoding='utf-8'))
    fields(contract, [*VERSIONS, 'prompt', 'output_schema'])
    for key, value in VERSIONS.items():
        require(contract[key] == value, 'Contract version mismatch')
    require(digest(contract['prompt'].encode('utf-8')) == config['prompt_sha256'], 'Prompt checksum mismatch')
    require(digest(canonical(contract['output_schema']).encode('utf-8')) == config['output_schema_sha256'],
            'Schema checksum mismatch')
    # Ensure the local validator exactly implements the immutable schema in use.
    variant = dict(type='object', additionalProperties=False, required=[*EVENTS, 'Q'],
                   properties={key: dict(type='string', minLength=1) for key in (*EVENTS, 'Q')})
    expected_schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                       'type': 'object', 'additionalProperties': False, 'required': list(VARIANTS),
                       'properties': {v: {'$ref': '#/$defs/variant'} for v in VARIANTS},
                       '$defs': {'variant': variant}}
    require(contract['output_schema'] == expected_schema, 'Schema/local-validator mismatch')
    payload = parse_json((ROOT / config['input_path']).read_text(encoding='utf-8'))
    validate_input(payload)
    provenance = {'source_commit': source_commit(), 'config_path': str(config_path),
                  'config_sha256': file_hash(config_path), 'contract_sha256': config['contract_sha256'],
                  'contract_document_sha256': config['contract_document_sha256'], **VERSIONS,
                  'prompt_sha256': config['prompt_sha256'], 'output_schema_sha256': config['output_schema_sha256'],
                  'probe_input_sha256': config['input_sha256'],
                  'model_facing_input_sha256': digest(canonical(payload).encode('utf-8')),
                  'probe_input_identity': config['input_identity'], 'input_purpose': config['input_purpose'],
                  'input_domain': payload['domain'], 'input_origin': config['input_origin'],
                  'input_allocation_scope': config['input_allocation_scope']}
    return {'config': config, 'contract': contract, 'input': payload, 'provenance': provenance}


def request_body(bundle, slot):
    validate_input(bundle['input'])  # Also enforce at the public construction boundary.
    require(slot in SLOTS, 'Unknown probe slot')
    return {'model': slot['model'],
            'provider': {'order': slot['provider_order'], 'allow_fallbacks': False, 'require_parameters': True},
            'messages': [{'role': 'system', 'content': bundle['contract']['prompt']},
                         {'role': 'user', 'content': canonical(bundle['input'])}],
            'reasoning': {'effort': 'low'}, 'max_tokens': 16384,
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'crst_naturalization_triplet_v1', 'strict': True,
                'schema': bundle['contract']['output_schema']}}}


def preview(bundle):
    bodies = [request_body(bundle, slot) for slot in SLOTS]
    return {'status': 'CAPABILITY_PROBE_CLOSED_PASS', **bundle['provenance'],
            'execution_mode': 'standard', 'parameter_semantics': bundle['config']['parameter_semantics'],
            'execution_package': 'FROZEN', 'execution_compatibility': 'VERIFIED',
            'generator_status': 'CANDIDATE', 'successful_attempt': 'attempt-02',
            'output_directory': bundle['config']['output_directory'],
            'generation': bundle['config']['generation'], 'wire_mapping_under_test': MAPPING,
            'transport': bundle['config']['transport'],
            'expected_logical_calls': 2, 'maximum_physical_inference_attempts': 6,
            'requests': [{'logical_call_id': slot['logical_call_id'], 'requested_model': body['model'],
                          'requested_provider_order': body['provider']['order'],
                          'wire_request_sha256': digest(canonical(body).encode('utf-8'))}
                         for slot, body in zip(SLOTS, bodies)]}


def selected_provider(metadata):
    require(type(metadata) is dict and type(metadata.get('endpoints')) is dict, 'Missing routing metadata')
    available = metadata['endpoints'].get('available')
    require(type(available) is list and bool(available), 'Missing endpoint evidence')
    selected = []
    for entry in available:
        require(type(entry) is dict and type(entry.get('selected')) is bool, 'Malformed routing metadata')
        nonempty(entry.get('provider'))
        if entry['selected']:
            selected.append(entry['provider'])
    require(bool(selected), 'No selected provider')
    require(len({p.strip().casefold() for p in selected}) == 1, 'Ambiguous selected providers')
    return selected[0]


def retryable(status=None, error=None):
    return status in TRANSPORT['retryable_http_statuses'] or isinstance(
        error, (httpx.NetworkError, httpx.ReadTimeout, httpx.WriteTimeout,
                httpx.ConnectTimeout, httpx.PoolTimeout, asyncio.TimeoutError))


def terminal_error(envelope):
    if type(envelope) is not dict or not envelope.get('error'):
        return False
    error = envelope['error']
    if type(error) is not dict:
        return False
    code = error.get('code')
    return code in (400, 401, 403, 404, 422, 'unsupported_parameter', 'invalid_parameter',
                    'invalid_request_error', 'invalid_json_schema', 'authentication_error',
                    'permission_error', 'refusal', 'semantic_failure')


def inspect_response(attempt, envelope, body):
    require(type(envelope) is dict, 'Malformed response envelope')
    require(not envelope.get('error'), 'API error response')
    provider = selected_provider(envelope.get('openrouter_metadata'))
    attempt['observed_selected_provider'] = provider
    require(provider.strip().casefold() == body['provider']['order'][0], 'Provider route mismatch')
    require(envelope.get('model') == body['model'], 'Returned model mismatch')
    choices = envelope.get('choices')
    require(type(choices) is list and len(choices) == 1, 'Missing/ambiguous completion')
    choice = choices[0]
    require(type(choice) is dict, 'Malformed choice')
    message = choice.get('message')
    require(type(message) is dict, 'Missing assistant message')
    require(not attempt['refusal'], 'Refusal')
    require(not attempt['incomplete_or_truncated'], 'Incomplete/truncated response')
    require(choice.get('finish_reason') == 'stop', 'Missing/unexpected finish reason')
    require(message.get('role') == 'assistant' and not message.get('tool_calls'), 'Unexpected response role/tools')
    content = message.get('content')
    nonempty(content)
    try:
        attempt['parsed_structured_response'] = parse_json(content)  # One parse; no repairs.
    except ValueError:
        attempt['parse_status'] = 'failed'
        raise
    attempt['parse_status'] = 'passed'
    try:
        validate_output(attempt['parsed_structured_response'])
    except ValueError:
        attempt['schema_status'] = 'failed'
        raise
    attempt['schema_status'] = 'passed'
    exposed = envelope.get('usage')
    require(exposed is None or type(exposed) is dict, 'Malformed usage object')
    if exposed is not None:
        for detail in ('completion_tokens_details', 'prompt_tokens_details'):
            nested = exposed.get(detail)
            require(nested is None or type(nested) is dict, f'Malformed usage {detail}')
    for field, value in attempt['usage'].items():
        if value is None:  # Unexposed/null optional accounting remains unknown.
            continue
        if field == 'cost':
            require(type(value) in (int, float) and value >= 0
                    and (type(value) is int or math.isfinite(value)), 'Malformed usage cost')
        else:
            require(type(value) is int and value >= 0, f'Malformed usage {field}')


def response_evidence(attempt, envelope):
    """Preserve available evidence before any routing/schema gate can fail."""
    if type(envelope) is not dict:
        return
    attempt.update(returned_model=envelope.get('model'), response_id=envelope.get('id'),
                   openrouter_metadata=envelope.get('openrouter_metadata'),
                   service_tier=envelope.get('service_tier'))
    usage = envelope.get('usage')
    if type(usage) is dict:
        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'cost'):
            attempt['usage'][key] = usage.get(key)
        for field, detail, subfield in [('reasoning_tokens', 'completion_tokens_details', 'reasoning_tokens'),
                                       ('cached_tokens', 'prompt_tokens_details', 'cached_tokens')]:
            nested = usage.get(detail)
            attempt['usage'][field] = nested.get(subfield) if type(nested) is dict else None
    choices = envelope.get('choices')
    if type(choices) is list and choices and type(choices[0]) is dict:
        choice = choices[0]
        attempt['finish_reason'] = choice.get('finish_reason')
        attempt['native_finish_reason'] = choice.get('native_finish_reason')
        message = choice.get('message')
        attempt['incomplete_or_truncated'] = (choice.get('finish_reason') in ('length', 'max_tokens')
                                             or choice.get('native_finish_reason') in ('max_tokens', 'length')
                                             or bool(envelope.get('incomplete_details')))
        attempt['refusal'] = bool(choice.get('finish_reason') == 'content_filter'
                                  or envelope.get('refusal') or (type(message) is dict and message.get('refusal')))


async def post_with_deadline(client, wire, headers, seconds):
    # AsyncClient.post reads the complete body. wait_for bounds the whole operation,
    # including connection, upload, and body receipt, not just an inactivity window.
    return await asyncio.wait_for(client.post(URL, content=wire, headers=headers, timeout=seconds), timeout=seconds)


async def probe_call(client, bundle, slot, key, *, sleep=asyncio.sleep):
    body = request_body(bundle, slot)
    wire = canonical(body).encode('utf-8')
    result = {'logical_call_id': slot['logical_call_id'], 'status': 'FAIL', 'failure_reason': None,
              'wire_request': wire.decode('utf-8'), 'wire_request_sha256': digest(wire),
              'request_body': body, 'attempts': [], 'semantic_qualification': 'NOT_ASSESSED'}
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
               'X-OpenRouter-Metadata': 'enabled'}
    for number in range(1, 4):
        started = time.monotonic()
        attempt = {'logical_call_id': slot['logical_call_id'], 'physical_attempt': number,
                   'started_at': datetime.now(timezone.utc).isoformat(),
                   'requested_model': slot['model'], 'requested_provider_order': slot['provider_order'],
                   'returned_model': None, 'observed_selected_provider': None,
                   'request_id': None, 'response_id': None, 'http_status': None, 'raw_response': None,
                   'response_sha256_before_redaction': None, 'response_envelope': None,
                   'envelope_parse_status': 'not_run',
                   'openrouter_metadata': None, 'service_tier': None, 'finish_reason': None,
                   'native_finish_reason': None, 'refusal': None, 'incomplete_or_truncated': None,
                   'parsed_structured_response': None, 'parse_status': 'not_run', 'schema_status': 'not_run',
                   'usage': {k: None for k in ('prompt_tokens', 'completion_tokens', 'total_tokens',
                                             'reasoning_tokens', 'cached_tokens', 'cost')},
                   'latency_seconds': None, 'retry_reason': None, 'will_retry': False,
                   'processing_or_charge_uncertain': False, 'error_type': None, 'failure_reason': None}
        result['attempts'].append(attempt)
        envelope, response, error = None, None, None
        try:
            response = await post_with_deadline(client, wire, headers, TRANSPORT['per_attempt_deadline_seconds'])
            attempt.update(http_status=response.status_code, request_id=response.headers.get('x-request-id'),
                           raw_response=response.text,
                           response_sha256_before_redaction=digest(response.content))
            try:
                envelope = parse_json(response.text)
                attempt['response_envelope'] = envelope
                attempt['envelope_parse_status'] = 'passed'
            except ValueError:
                attempt['envelope_parse_status'] = 'failed'
            response_evidence(attempt, envelope)
        except Exception as exc:
            error = exc
            attempt.update(error_type=type(exc).__name__, processing_or_charge_uncertain=True)
        attempt['latency_seconds'] = time.monotonic() - started
        again = retryable(attempt['http_status'], error) and not terminal_error(envelope)
        if again:
            attempt['retry_reason'] = (f'HTTP {attempt["http_status"]}' if response is not None else type(error).__name__)
            attempt['will_retry'] = number < 3
            if attempt['will_retry']:
                await sleep(TRANSPORT['backoff_seconds'][number - 1])
                continue
        try:
            require(error is None, 'Transport failure; processing/charge may be uncertain')
            require(response is not None and response.is_success, f'HTTP request failed: {attempt["http_status"]}')
            inspect_response(attempt, envelope, body)
        except (ValueError, TypeError, KeyError) as exc:
            if attempt['parse_status'] == 'not_run' and isinstance(exc, json.JSONDecodeError):
                attempt['parse_status'] = 'failed'
            attempt['failure_reason'] = str(exc)
            result['failure_reason'] = str(exc)
            break
        result['status'] = 'PASS'
        break
    return result


def redact(value, key):
    """Never archive credentials, including credentials echoed in response bodies."""
    if isinstance(value, dict):
        return {redact(str(k), key): redact(v, key) for k, v in value.items()
                if str(k).casefold() not in {'authorization', 'proxy-authorization', 'api_key', 'openrouter_api_key'}}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        value = value.replace(key, '[REDACTED]') if key else value
        return re.sub(r'(?i)[\"\']?(?:proxy-)?authorization[\"\']?\s*[:=]\s*[^\r\n]*',
                      '[REDACTED HEADER]', value)
    return value


def archive(directory, result, key):
    payload = (json.dumps(redact(result, key), ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.evidence-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        target = Path(directory) / 'probe.json'
        os.link(temporary, target)  # Atomic no-overwrite publication.
        with (Path(directory) / 'SHA256SUMS').open('x', encoding='utf-8') as manifest:
            manifest.write(f'{digest(payload)}  probe.json\n')
    finally:
        if temporary is not None:
            temporary.unlink()
    return digest(payload)


async def execute_probe(bundle, key, output_directory, *, client_factory=httpx.AsyncClient):
    require(bundle['config']['status'] != 'CLOSED', 'Capability probe CLOSED/PASS; reopening requires adjudication')
    require(bool(key.strip()), 'Execution requires OPENROUTER_API_KEY')
    require(source_commit(clean=True) == bundle['provenance']['source_commit'], 'Source changed since preflight')
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=False)  # Reserve once; never overwrite an attempt.
    result = {'status': 'FAIL', 'purpose': 'CAPABILITY-PROBE-ONLY', 'failure_reason': None,
              'parameter_semantics': 'UNOBSERVABLE_SEMANTICS_REMAIN_VERIFY', 'generator_status': 'CANDIDATE',
              'provenance': bundle['provenance'], 'config': bundle['config'],
              'wire_mapping_under_test': MAPPING, 'probe_input': bundle['input'],
              'expected_logical_calls': 2, 'logical_calls': [
                  {'logical_call_id': s['logical_call_id'], 'status': 'BLOCKED',
                   'failure_reason': 'Not executed', 'attempts': []} for s in SLOTS]}
    try:
        async with client_factory(trust_env=False, follow_redirects=False) as client:
            for index, slot in enumerate(SLOTS):
                call = await probe_call(client, bundle, slot, key)
                result['logical_calls'][index] = call
                if call['status'] != 'PASS':
                    result['failure_reason'] = f'{slot["logical_call_id"]}: {call["failure_reason"]}; STOP FOR ADJUDICATION'
                    break
            else:
                result['status'] = 'PASS'
    except Exception as exc:
        result['failure_reason'] = f'Execution exception: {type(exc).__name__}; STOP FOR ADJUDICATION'
    checksum = archive(directory, result, key)
    print(f'{result["status"]}: capability compatibility only; generators remain CANDIDATE. Artifact SHA-256: {checksum}')
    return redact(result, key)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Permit execution only together with --confirm-spend')
    parser.add_argument('--confirm-spend', action='store_true', help='Acknowledge model charges; also requires --execute')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--output-directory', type=Path, help='New immutable attempt directory (execution only)')
    args = parser.parse_args(argv)
    if args.execute != args.confirm_spend:
        parser.error('Execution requires BOTH --execute AND --confirm-spend')
    bundle = load_bundle(args.config)
    if not args.execute:
        print(json.dumps(preview(bundle), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    if bundle['config']['status'] == 'CLOSED':
        parser.error('Capability probe CLOSED/PASS; reopening requires adjudication')
    key = os.environ.get('OPENROUTER_API_KEY', '')  # Only read in explicitly gated execution.
    if not key.strip():
        parser.error('Execution requires OPENROUTER_API_KEY')
    output = args.output_directory or ROOT / bundle['config']['output_directory']
    result = asyncio.run(execute_probe(bundle, key, output))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
