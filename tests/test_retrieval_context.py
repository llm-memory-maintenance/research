"""Offline rule tests with hand-supplied scores and non-calibration text only."""

import hashlib
import importlib.util
from pathlib import Path
import socket

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('retrieval_context', ROOT / 'experiments/retrieval_context.py')
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network forbidden in deterministic rule tests')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


def entry(identity='smoke-a', day='02', text='A paper crane rests on a shelf.'):
    return {'entry_id': identity, 'created_time': f'2025-01-{day}T00:00:00Z',
            'last_updated_time': f'2025-01-{day}T01:00:00Z', 'text': text,
            'annotation': {'secret_oracle': True}, 'similarity': 0.8, 'policy': 'hidden'}


class CharacterTokenizer:
    """Lengths are a test double, never a substitute for official token budgeting."""
    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return list(text)


def test_exact_serializer_and_field_allowlist():
    first = entry()
    expected = '[memory_id=smoke-a; created=2025-01-02T00:00:00Z; updated=2025-01-02T01:00:00Z] A paper crane rests on a shelf.'
    assert rules.serialize_entry(first) == expected
    assert rules.serialize_context([first, first]) == expected + '\n' + expected
    assert rules.serialize_context([]) == ''
    assert 'hidden' not in rules.serialize_entry(first)
    assert 'oracle' not in rules.serialize_entry(first)


@pytest.mark.parametrize('value', ['', 'trailing ', 'line\nbreak', 'line\rbreak'])
def test_serializer_rejects_invalid_single_line(value):
    sample = entry(text=value)
    with pytest.raises(ValueError):
        rules.serialize_entry(sample)


def test_exact_score_ties_use_hash_not_recency():
    samples = [entry('smoke-a', '03'), entry('smoke-b', '01'), entry('smoke-c', '02')]
    expected = sorted(samples, key=lambda e: hashlib.sha256(e['entry_id'].encode('utf-8')).digest())
    assert rules.rank_entries(samples, [0.5] * 3) == expected
    assert rules.rank_entries(samples[::-1], [0.5] * 3) == expected
    # Distinct float scores must not be rounded into a tie.
    assert rules.rank_entries(samples, [0.5, 0.500000000000001, 0.4])[0] == samples[1]


@pytest.mark.parametrize('scores', [[float('nan')], [float('inf')], []])
def test_invalid_scores_fail(scores):
    with pytest.raises(ValueError):
        rules.rank_entries([entry()], scores)


def test_duplicate_ids_fail():
    with pytest.raises(ValueError):
        rules.rank_entries([entry(), entry()], [0.2, 0.3])


def test_chronological_order_three_keys():
    a = entry('smoke-z', '01')
    a['last_updated_time'] = '2025-01-04T01:00:00Z'
    b = entry('smoke-0', '03')
    c = entry('smoke-b', '02')
    d = entry('smoke-a', '02')
    c['last_updated_time'] = d['last_updated_time'] = b['last_updated_time']
    # Oldest-created a is last because its active content was updated latest.
    # Equal updates put c/d before b by creation time, then d before c by ID.
    assert sorted([b, c, a, d], key=rules.chronological_key) == [d, c, b, a]


def test_prefix_overflow_stops_without_skipping():
    first = entry('smoke-a', text='A folded paper star.')
    oversized = entry('smoke-b', text='A long ribbon circles the empty gift box. ' * 8 + 'End.')
    later = entry('smoke-c', text='A pin.')
    tokenizer = CharacterTokenizer()
    budget = len(rules.serialize_context([first, later]))
    selected, context = rules.select_context([first, oversized, later], 3, budget, tokenizer)
    assert selected == [first]
    assert context == rules.serialize_entry(first)


def test_exact_fit_empty_prefix_and_k_limit():
    first, second = entry('smoke-a'), entry('smoke-b')
    length = len(rules.serialize_entry(first))
    tokenizer = CharacterTokenizer()
    assert rules.select_context([first, second], 2, length, tokenizer)[0] == [first]
    assert rules.select_context([first, second], 2, length - 1, tokenizer) == ([], '')
    assert rules.select_context([first, second], 1, 10000, tokenizer)[0] == [first]


def test_reorder_only_after_admission():
    newest, oldest = entry('smoke-new', '03'), entry('smoke-old', '01')
    tokenizer = CharacterTokenizer()
    budget = len(rules.serialize_entry(newest))
    assert rules.select_context([newest, oldest], 2, budget, tokenizer)[0] == [newest]
    selected, context = rules.select_context([newest, oldest], 2, 10000, tokenizer)
    assert selected == [oldest, newest]
    assert context == rules.serialize_context([oldest, newest])


def test_chronological_recount_fails_closed():
    class OrderSensitiveTokenizer:
        def encode(self, text, *, add_special_tokens):
            assert add_special_tokens is False
            count = 3 if text.startswith('[memory_id=smoke-old') else 1
            return [0] * count

    with pytest.raises(ValueError, match='chronological serialization exceeds'):
        rules.select_context([entry('smoke-new', '03'), entry('smoke-old', '01')],
                             2, 2, OrderSensitiveTokenizer())


def test_configuration_freezes_implementations_not_outcomes():
    config = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text())
    embedding = config['embedding']
    assert embedding['repository_id'] == embedding['tokenizer_repository_id'] == 'facebook/contriever'
    assert embedding['revision'] == embedding['tokenizer_revision'] == '2bd46a25019aeea091fd42d1f0fd4801675cf699'
    assert embedding['pooling'] == 'attention_mask_mean_last_hidden_state'
    assert embedding['dtype'] == 'float32'
    assert embedding['max_length'] == 512
    assert embedding['overlength_behavior'] == 'error_before_truncation'
    assert config['reader_tokenizer']['repository_id'] == 'meta-llama/Llama-3.1-8B-Instruct'
    assert config['reader_tokenizer']['revision'] == '0e9e39f249a16976918f6564b8830bc894c89659'
    assert config['reader_tokenizer']['add_special_tokens'] is False
    retrieval = config['retrieval']
    assert retrieval['maintenance_k_candidates'] == [1, 3, 5, 10]
    assert retrieval['answer_k_candidates'] == [1, 3, 5, 10, 20]
    assert retrieval['context_token_candidates'] == [512, 1024, 2048, 3072]
    assert retrieval['success_threshold'] == 0.95
    assert retrieval['overflow_rule'] == 'stop_at_first_nonfitting_entry_no_skip_no_partial'
    assert retrieval['similarity_tie_break'] == 'sha256_utf8_entry_id_ascending'
    assert retrieval['chronological_order'] == ['last_updated_time_ascending', 'created_time_ascending', 'entry_id_ascending']
    assert all(value is None for value in config['selected'].values())
    assert config['b0']['history_material'] is None and config['b0']['context_tokens'] is None
    assert config['dataset']['sha256'] == 'ce9605fe777febafde20b4675cb6a2fb456b0d12cd649001c25d703e6e4e9079'
    null_paths = []

    def collect_nulls(value, path=()):
        if value is None:
            null_paths.append(path)
        elif isinstance(value, dict):
            for name, item in value.items():
                collect_nulls(item, path + (name,))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                collect_nulls(item, path + (index,))

    collect_nulls(config)
    assert set(null_paths) == {
        ('selected', 'embedding_qualified'), ('selected', 'K_MAINT'),
        ('selected', 'K_ANSWER'), ('selected', 'LME_RETRIEVAL_CONTEXT_TOKENS'),
        ('b0', 'history_material'), ('b0', 'historical_window_serialization'), ('b0', 'context_tokens'),
    }
    for section in ('embedding', 'reader_tokenizer'):
        assert len(config[section]['revision']) == 40
        for checksum in config[section]['artifact_sha256'].values():
            assert len(checksum) == 64 and all(ch in '0123456789abcdef' for ch in checksum)
