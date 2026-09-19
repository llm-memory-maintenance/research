"""Shared offline helpers for the CRST Small Pilot tests."""
from pathlib import Path
import json
import re
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import build_crst_pilot_material as builder  # noqa: E402
import crst_policies as pol  # noqa: E402
import validate_crst_pilot_material as v  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)


class ToyTokenizer:
    """Role headers and terminators are tokens, so message structure contributes to the count."""

    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize is False and add_generation_prompt is False
        return '<|bos|>' + ''.join(f'<|head|>{m["role"]}<|/head|>\n\n{m["content"]}<|eot|>' for m in messages)

    def encode(self, text, add_special_tokens):
        assert add_special_tokens is False
        return re.findall(r'<\|/?\w+\|>|\w+|[^\w\s]', text)


@pytest.fixture(scope='module')
def material():
    return v.validate_directory(longmemeval=False)


@pytest.fixture(scope='module')
def references(material):
    return [v.with_scenario_id(f) for f in material[1]]


@pytest.fixture()
def built():
    """Fresh, mutable structured fixtures reproduced offline."""
    return builder.build_fixtures()


def reference_decision(event):
    operation = event['reference_operation']
    return json.dumps({'operation': operation,
                       'target_id': event['canonical_target_id'] if operation == 'Update' else None})


def follow_reference(reference, variant, policy, overrides=None, answer=None):
    """`ask` that follows the reference path, with per-event raw-response overrides."""
    events = {f'{reference["scenario_id"]}/{variant}/{policy}/{e["event"]}': e
              for e in pol.reference_events(reference, variant, policy)}
    overrides = overrides or {}

    def ask(request):
        if request['kind'] == 'answer':
            return {'content': answer}
        event = events[request['logical_id']]
        return {'content': overrides.get(event['event'], reference_decision(event))}
    return ask


def fake_git(*args):
    return b'0' * 40 + b'\n' if args[:1] == ('rev-parse',) else b''


def good_output(fixture):
    """A schema-valid triplet that the frozen deterministic check passes; synthetic text only."""
    import validate_generator_qualification_fixtures as gq
    r = fixture['reference']
    names = {e['entity_id']: e['name'] for e in r['entities']}
    keys = {k['state_key']: k for k in r['state_keys']}
    meaning = {a['attribute_id']: a['meaning'] for a in r['attributes']}
    out = {}
    for variant in gq.VARIANTS:
        out[variant] = {e['event']: f'{names[keys[e["state_key"]]["entity_id"]]} is set to {e["current_value"]} today.'
                        for e in r['variants'][variant]['events']}
        primary = names[r['question_intent']['entity_id']]
        out[variant]['Q'] = f'What is the {meaning[r["question_intent"]["attribute_id"]]} of {primary}?'
    return out


def chat_envelope(body, content, *, usage=True, provider='CoreWeave', model=None):
    envelope = {'model': model or body['model'], 'id': 'mock-response',
                'openrouter_metadata': {'endpoints': {'available': [{'provider': provider, 'selected': True}]}},
                'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': content}}]}
    if usage:
        envelope['usage'] = {'prompt_tokens': 100, 'completion_tokens': 5, 'total_tokens': 105, 'cost': 0.0001,
                             'prompt_tokens_details': {'cached_tokens': 0}}
    return envelope


KEY = 'test-secret'

# Literal, independent of the module under test.
ANSWER_INSTRUCTION = ('Return exactly one JSON object with exactly one key named "answer".\n'
                      'The value of "answer" must contain only the answer to the question, with no explanation or '
                      'additional text.\n'
                      'Do not return any other keys.')


def content_for(body, inputs, override=None):
    """The mock generator reply: a good triplet for the scenario whose projection is in the request."""
    import validate_generator_qualification_fixtures as gq
    payload = json.loads(body['messages'][1]['content'])
    for generator in inputs['generators']:
        if gq.project(generator['fixture']) == payload:
            output = good_output(generator['fixture'])
            return json.dumps(override(output) if override else output)
    raise AssertionError('Unknown scenario in request')


def run_naturalization(inputs, path, replies=None, key=KEY, override=None):
    """Mock live naturalization. `replies[i]` is None (good output), a callable(body)->Response, or 'garbage'."""
    import asyncio
    import httpx
    import naturalize_crst_pilot as nat
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        index = len(bodies)
        bodies.append(body)
        reply = replies[index] if replies and index < len(replies) else None
        provider = body['provider']['order'][0]
        if callable(reply):
            return reply(body)
        if reply == 'garbage':
            return httpx.Response(200, json=chat_envelope(body, 'not json', provider=provider))
        return httpx.Response(200, json=chat_envelope(body, content_for(body, inputs, override), provider=provider))

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    async def no_wait(seconds):
        pass
    result = asyncio.run(nat.collect(inputs, key, path, client_factory=factory, sleep=no_wait))
    return result, bodies
