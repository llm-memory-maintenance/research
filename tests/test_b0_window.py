"""Offline B0 window tests with a toy chat-template tokenizer and synthetic text only."""

import hashlib
import importlib.util
from pathlib import Path
import re
import socket

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('b0_window', ROOT / 'experiments/b0_window.py')
b0 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b0)
STAGED_READER = Path('/tmp/retrieval-implementation-identity/reader')


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


TOKENIZER = ToyTokenizer()
SYSTEM = 'Answer from the conversation.'


def texts(sizes=None):
    sizes = sizes or {}
    return {label: ' '.join([f'{label.lower()}word'] * sizes.get(label, 3)) for label in b0.EVENT_ORDER}


def exchanges(sizes=None):
    return b0.build_exchanges(texts(sizes))


def count(items, system=SYSTEM):
    return b0.history_tokens(system, items, TOKENIZER)


def test_exchange_is_one_complete_user_message_plus_the_fixed_acknowledgement():
    built = exchanges()
    assert [e['event'] for e in built] == list(b0.EVENT_ORDER) and len(built) == 16
    for exchange in built:
        assert [m['role'] for m in exchange['messages']] == ['user', 'assistant']
        assert exchange['messages'][1]['content'] == 'Noted.'
    assert built[-2]['event'] == 'U7' and built[-1]['event'] == 'N2'


def test_exchange_construction_rejects_missing_extra_or_empty_events():
    for mutate in (lambda t: t.pop('N2'), lambda t: t.update(Q='question'), lambda t: t.update(U7='')):
        broken = texts()
        mutate(broken)
        with pytest.raises(ValueError):
            b0.build_exchanges(broken)


def test_history_count_is_the_marginal_chat_template_difference():
    built = exchanges()
    two = built[-2:]
    flat = [m for e in two for m in e['messages']]
    base = [{'role': 'system', 'content': SYSTEM}]
    assert count(two) == b0.chat_tokens(base + flat, TOKENIZER) - b0.chat_tokens(base, TOKENIZER)
    # 8 role/terminator tokens per exchange pair of messages plus content: not a raw-text token sum.
    raw = sum(len(TOKENIZER.encode(m['content'], False)) for m in flat)
    assert count(two) > raw and count([]) == 0


def test_marginal_count_excludes_the_system_prompt_and_the_generation_prefix():
    built = exchanges()
    assert count(built) == count(built, system='A much longer fixed system prompt with many extra words in it.')
    rendered = TOKENIZER.apply_chat_template([{'role': 'user', 'content': 'x'}], False, False)
    assert not rendered.endswith('assistant<|/head|>\n\n')


def test_selection_admits_a_contiguous_newest_suffix_in_chronological_order():
    built = exchanges()
    for size in range(1, 16):
        budget = count(built[-size:])
        chosen = b0.select_window(built, budget, SYSTEM, TOKENIZER)
        assert chosen['exchanges'] == built[-size:]
        assert chosen['history_tokens'] == budget and not chosen['history_unit_overflow']
    assert b0.select_window(built, count(built) + 1000, SYSTEM, TOKENIZER)['exchanges'] == built


def test_selection_never_skips_a_large_exchange_to_reach_an_older_one():
    built = exchanges({'N1': 40})
    budget = count(built[-2:]) + 5  # Room for small older exchanges, but not for the large N1.
    assert budget < count(built[-3:])
    chosen = b0.select_window(built, budget, SYSTEM, TOKENIZER)
    assert [e['event'] for e in chosen['exchanges']] == ['U7', 'N2']
    assert all(e['event'] != 'U6' for e in chosen['exchanges'])


def test_selection_never_partially_retains_an_exchange():
    built = exchanges()
    for budget in range(0, count(built) + 1):
        chosen = b0.select_window(built, budget, SYSTEM, TOKENIZER)
        messages = [m for e in chosen['exchanges'] for m in e['messages']]
        assert [m['role'] for m in messages] == ['user', 'assistant'] * len(chosen['exchanges'])
        assert chosen['history_tokens'] <= budget


def test_newest_exchange_larger_than_the_budget_is_an_overflow_with_empty_history():
    built = exchanges()
    chosen = b0.select_window(built, count(built[-1:]) - 1, SYSTEM, TOKENIZER)
    assert chosen['exchanges'] == [] and chosen['history_unit_overflow'] and chosen['history_tokens'] == 0
    assert not b0.retains(chosen)


def test_selection_is_blind_to_event_identity():
    built = exchanges({'U7': 12, 'N2': 9})
    anonymous = [{'event': 'x', 'messages': e['messages']} for e in built]
    for budget in range(0, count(built) + 1, 3):
        named = b0.select_window(built, budget, SYSTEM, TOKENIZER)
        blind = b0.select_window(anonymous, budget, SYSTEM, TOKENIZER)
        assert [e['messages'] for e in named['exchanges']] == [e['messages'] for e in blind['exchanges']]


def test_required_suffix_is_u7_and_n2_and_excludes_n1():
    built = exchanges()
    suffix = b0.required_suffix(built)
    assert [e['event'] for e in suffix] == ['U7', 'N2']
    assert suffix == built[-2:]


def test_threshold_retains_u7_and_n2_exactly_and_one_token_less_does_not():
    for sizes in ({}, {'U7': 15, 'N2': 4}, {'U7': 2, 'N2': 30}, {'N1': 50, 'U6': 1}):
        built = exchanges(sizes)
        threshold = count(b0.required_suffix(built))
        at = b0.select_window(built, threshold, SYSTEM, TOKENIZER)
        assert b0.retains(at) and at['exchanges'] == built[-2:] and at['history_tokens'] == threshold
        below = b0.select_window(built, threshold - 1, SYSTEM, TOKENIZER)
        assert not b0.retains(below)
        assert [e['event'] for e in below['exchanges']] in ([], ['N2'])


def brute_force_budget(built, tokenizer):
    for budget in range(0, 2000):
        if b0.retains(b0.select_window(built, budget, SYSTEM, tokenizer)):
            return budget
    raise AssertionError('No budget retains the required suffix')


def test_required_budget_is_the_smallest_budget_that_retains_u7_and_n2():
    for sizes in ({}, {'U7': 15, 'N2': 4}, {'U7': 2, 'N2': 30}, {'N1': 50}):
        built = exchanges(sizes)
        budget = b0.required_budget(built, SYSTEM, TOKENIZER)
        assert budget == count(b0.required_suffix(built)) == brute_force_budget(built, TOKENIZER)
        assert b0.retains(b0.select_window(built, budget, SYSTEM, TOKENIZER))
        assert not b0.retains(b0.select_window(built, budget - 1, SYSTEM, TOKENIZER))


class QuirkyTokenizer(ToyTokenizer):
    """Counts are not monotone in suffix length: a long N2 makes the two-exchange suffix cheaper."""

    def encode(self, text, add_special_tokens):
        tokens = super().encode(text, add_special_tokens)
        return tokens[:-30] if text.count('n2word') >= 40 and 'u7word' in text else tokens


def test_required_budget_matches_brute_force_when_suffix_counts_are_not_monotone():
    built = exchanges({'N2': 40, 'U7': 3})
    quirky = QuirkyTokenizer()
    assert b0.history_tokens(SYSTEM, built[-2:], quirky) < b0.history_tokens(SYSTEM, built[-1:], quirky)
    budget = b0.required_budget(built, SYSTEM, quirky)
    assert budget == b0.history_tokens(SYSTEM, built[-1:], quirky) == brute_force_budget(built, quirky)


def test_question_is_appended_after_selection_and_outside_the_history_budget():
    built = exchanges()
    threshold = count(b0.required_suffix(built))
    for question in ('Short?', 'A far longer final question ' * 30):
        chosen = b0.select_window(built, threshold, SYSTEM, TOKENIZER)
        assert b0.retains(chosen) and chosen['history_tokens'] == threshold
        messages = b0.assemble(SYSTEM, chosen, question)
        assert messages[0]['role'] == 'system' and messages[-1] == {'role': 'user', 'content': question}
        assert messages[1:-1] == [m for e in chosen['exchanges'] for m in e['messages']]
        assert count(chosen['exchanges']) == threshold


def test_selection_is_deterministic_across_repeated_runs():
    built = exchanges({'U7': 7, 'N2': 5})
    runs = [b0.select_window(built, 60, SYSTEM, TOKENIZER) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_pinned_reader_tokenizer_marginal_count_is_independent_of_the_system_prompt():
    config = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']
    files = config['artifact_sha256']
    if not STAGED_READER.is_dir() or not all((STAGED_READER / name).is_file() for name in files):
        pytest.skip('Pinned reader tokenizer files are not staged locally')
    for name, digest in files.items():
        if hashlib.sha256((STAGED_READER / name).read_bytes()).hexdigest() != digest:
            pytest.skip(f'Staged {name} does not match the pinned artifact hash')
    import os
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from transformers import AutoTokenizer
    real = AutoTokenizer.from_pretrained(str(STAGED_READER), use_fast=True, local_files_only=True,
                                         trust_remote_code=False)
    built = exchanges({'U7': 11, 'N2': 8})
    suffix = b0.required_suffix(built)
    counts = {b0.history_tokens(system, suffix, real)
              for system in ('S', SYSTEM, 'A considerably longer system prompt. ' * 12)}
    assert len(counts) == 1 and counts.pop() > 0
    threshold = b0.history_tokens(SYSTEM, suffix, real)
    assert b0.retains(b0.select_window(built, threshold, SYSTEM, real))
    assert not b0.retains(b0.select_window(built, threshold - 1, SYSTEM, real))
