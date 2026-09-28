"""Offline regression checks for deterministic dataset construction, not retrieval."""

from collections import Counter
import copy
import json
from pathlib import Path
import random
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
import build_retrieval_calibration as build
import validate_retrieval_calibration as validator


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network access forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


@pytest.fixture(scope='module')
def corpus():
    return build.build_dataset()


@pytest.fixture
def changed(corpus):
    return copy.deepcopy(corpus)


def select(dataset, kind):
    if kind in ('changed_state', 'same_state', 'new_key'):
        return next(c for c in dataset['cases'] if c.get('maintenance_case_type') == kind)
    return next(c for c in dataset['cases'] if c['task'] == 'answer'
                and c['stale_competing_version'] == (kind == 'stale'))


def oracle(case):
    target = case.get('oracle_target_entry_id') or case['oracle_entry_ids'][0]
    return next(e for e in case['active_memory'] if e['entry_id'] == target)


def stale(case):
    return next(e for e in case['active_memory'] if 'stale_competing_version' in validator.tags(e))


def render(item):
    a = item['annotation']
    item['text'] = build.fact_forms(a['entity'], a['attribute'], a['value'])[0]


def test_composition_and_balances(corpus):
    cases = corpus['cases']
    assert len(cases) == 140
    assert Counter(c.get('maintenance_case_type', 'answer') for c in cases) == {
        'changed_state': 30, 'same_state': 30, 'new_key': 20, 'answer': 60}
    for kind in ('changed_state', 'same_state'):
        assert Counter(c['active_memory_size'] for c in cases if c.get('maintenance_case_type') == kind) == {
            16: 10, 64: 10, 128: 10}
    assert Counter(c['active_memory_size'] for c in cases if c.get('maintenance_case_type') == 'new_key') == {
        16: 7, 64: 7, 128: 6}
    cells = Counter((c['query_wording'], c['active_memory_size'], c['stale_competing_version'])
                    for c in cases if c['task'] == 'answer')
    assert cells == {(wording, size, old): 5 for wording in ('direct', 'paraphrased')
                     for size in (16, 64, 128) for old in (False, True)}


def test_fixed_seed_deterministic_bytes(corpus):
    random.seed(23)
    first = build.dataset_bytes(build.build_dataset(20260917))
    random.seed(987)
    second = build.dataset_bytes(build.build_dataset())
    assert first == second == build.dataset_bytes(corpus)
    assert first.endswith(b'\n')
    assert first == (json.dumps(corpus, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


@pytest.mark.parametrize('seed', [None, 0, 20260918, '20260917', 20260917.0, True])
def test_refuse_other_seeds(seed):
    with pytest.raises(ValueError, match='frozen seed'):
        build.build_dataset(seed)


def test_official_corpus_valid_and_byte_identical(corpus):
    validator.validate_dataset(corpus)
    official = validator.load_dataset(build.OUTPUT)
    validator.validate_dataset(official)
    assert build.OUTPUT.read_bytes() == build.dataset_bytes(corpus)


def test_templates_and_source_diversity(corpus):
    targets = [c['candidate']['annotation'] if c['task'] == 'maintenance' else oracle(c)['annotation']
               for c in corpus['cases']]
    assert {a['attribute'] for a in targets} == set(build.ATTRIBUTE_NAMES)
    assert len({a['entity'] for a in targets}) == 140
    assert all(len(set(spec[2])) == 3 and len(spec[3]) == len(spec[4]) == 2
               for spec in build.ATTRIBUTES.values())
    assert not any(term in build.dataset_bytes(corpus).decode().casefold() for term in validator.FORBIDDEN)
    entries = [e for c in corpus['cases'] for e in c['active_memory']]
    assert len({e['entry_id'] for e in entries}) == len(entries)


def test_same_state_surface_distinct_semantics_equal(corpus):
    cases = [c for c in corpus['cases'] if c.get('maintenance_case_type') == 'same_state']
    assert len(cases) == 30
    for case in cases:
        candidate, target = case['candidate'], oracle(case)
        assert all(candidate['annotation'][k] == target['annotation'][k]
                   for k in ('entity', 'attribute', 'value'))
        assert candidate['text'] != target['text']
        validator.validate_fact(candidate)
        validator.validate_fact(target)


def test_reject_same_state_identical_text(changed):
    case = select(changed, 'same_state')
    case['candidate']['text'] = oracle(case)['text']
    with pytest.raises(ValueError, match='Same-state candidate text must differ'):
        validator.validate_dataset(changed)


@pytest.mark.parametrize('kind', ['changed_state', 'same_state'])
def test_reject_collapsed_hard_distractor_roles(changed, kind):
    case = select(changed, kind)
    entries = case['active_memory']
    same_entity = next(e for e in entries if 'same_entity_different_attribute' in validator.tags(e))
    related = next(e for e in entries if 'semantically_related_different_key' in validator.tags(e))
    related['annotation']['diagnostic_tags'] = ['other']
    # This paired attribute is semantically related, so both tags are true;
    # the rejection concerns distinct entry IDs, not incorrect semantics.
    same_entity['annotation']['diagnostic_tags'].append('semantically_related_different_key')
    with pytest.raises(ValueError, match='three distinct entry IDs'):
        validator.validate_dataset(changed)


def test_overlapping_roles_with_distinct_representatives_pass(changed):
    case = select(changed, 'changed_state')
    entry = next(e for e in case['active_memory'] if 'same_entity_different_attribute' in validator.tags(e))
    entry['annotation']['diagnostic_tags'].append('semantically_related_different_key')
    validator.validate_dataset(changed)


@pytest.mark.parametrize('mutation', [
    'duplicate_case', 'duplicate_entry', 'missing_oracle', 'changed_same_value',
    'same_changed_value', 'new_existing_key', 'missing_distractor', 'false_distractor',
    'stale_missing', 'stale_same_value', 'stale_newer', 'stale_wrong_key',
    'stale_is_oracle', 'false_stale_flag', 'wrong_cell', 'wrong_length',
    'wrong_text', 'wrong_question', 'wrong_oracle_tag', 'extra_oracle',
    'timestamp_invalid', 'timestamp_non_utc', 'timestamp_reversed',
    'wrong_composition', 'wrong_total', 'extra_field', 'answer_only_field',
    'maintenance_only_field', 'empty_annotation', 'invalid_tag', 'duplicate_tag',
    'candidate_role_tag', 'multiple_answer_oracles', 'wrong_source', 'wrong_version', 'wrong_dataset_id',
])
def test_reject_invalid_corpus(changed, mutation):
    c = select(changed, 'changed_state')
    if mutation == 'duplicate_case':
        changed['cases'][1]['case_id'] = c['case_id']
    elif mutation == 'duplicate_entry':
        c['active_memory'][1]['entry_id'] = c['active_memory'][0]['entry_id']
    elif mutation == 'missing_oracle':
        c['oracle_target_entry_id'] = 'not-present'
    elif mutation == 'changed_same_value':
        c['candidate']['annotation']['value'] = oracle(c)['annotation']['value']
        render(c['candidate'])
    elif mutation == 'same_changed_value':
        c = select(changed, 'same_state')
        a = c['candidate']['annotation']
        a['value'] = next(v for v in build.ATTRIBUTES[a['attribute']][1] if v != a['value'])
        render(c['candidate'])
    elif mutation == 'new_existing_key':
        c = select(changed, 'new_key')
        c['candidate'] = copy.deepcopy({k: c['active_memory'][0][k] for k in ('text', 'annotation')})
        c['candidate']['annotation']['diagnostic_tags'] = []
    elif mutation == 'missing_distractor':
        for e in c['active_memory']:
            e['annotation']['diagnostic_tags'] = [t for t in validator.tags(e) if t != 'same_entity_different_attribute']
    elif mutation == 'false_distractor':
        e = next(e for e in c['active_memory'] if 'same_entity_different_attribute' in validator.tags(e))
        e['annotation']['entity'] = build.ENTITIES[-1]
        render(e)
    elif mutation.startswith('stale_'):
        c = select(changed, 'stale')
        old, current = stale(c), oracle(c)
        if mutation == 'stale_missing':
            old['annotation']['diagnostic_tags'] = ['other']
        elif mutation == 'stale_same_value':
            old['annotation']['value'] = current['annotation']['value']
            render(old)
        elif mutation == 'stale_newer':
            old['created_time'] = old['last_updated_time'] = '2090-01-01T00:00:00Z'
        elif mutation == 'stale_wrong_key':
            old['annotation']['entity'] = build.ENTITIES[-1]
            render(old)
        else:
            old['annotation']['diagnostic_tags'].append('oracle_current')
    elif mutation == 'false_stale_flag':
        select(changed, 'stale')['stale_competing_version'] = False
    elif mutation == 'wrong_cell':
        c = select(changed, 'plain')
        c['query_wording'] = 'paraphrased'
        a = oracle(c)['annotation']
        c['question'] = build.question_forms(a['entity'], a['attribute'], 'paraphrased')[0]
    elif mutation == 'wrong_length':
        c['active_memory'].pop()
    elif mutation == 'wrong_text':
        c['active_memory'][0]['text'] = 'This text does not express the annotated fact.'
    elif mutation == 'wrong_question':
        select(changed, 'plain')['question'] = 'Which of several properties is relevant?'
    elif mutation == 'wrong_oracle_tag':
        oracle(c)['annotation']['diagnostic_tags'] = ['other']
    elif mutation == 'extra_oracle':
        c = select(changed, 'plain')
        next(e for e in c['active_memory'] if e is not oracle(c))['annotation']['diagnostic_tags'].append('oracle_current')
    elif mutation == 'timestamp_invalid':
        c['active_memory'][0]['created_time'] = '2020-02-30T00:00:00Z'
    elif mutation == 'timestamp_non_utc':
        c['active_memory'][0]['created_time'] = '2020-01-01T00:00:00+07:00'
    elif mutation == 'timestamp_reversed':
        c['active_memory'][0]['created_time'] = '2090-01-01T00:00:00Z'
    elif mutation == 'wrong_composition':
        c['maintenance_case_type'] = 'same_state'
        c['candidate']['annotation']['value'] = oracle(c)['annotation']['value']
        render(c['candidate'])
    elif mutation == 'wrong_total':
        changed['cases'].pop()
    elif mutation == 'extra_field':
        c['unrecognized'] = True
    elif mutation == 'answer_only_field':
        c['question'] = 'Not allowed here'
    elif mutation == 'maintenance_only_field':
        select(changed, 'plain')['candidate'] = c['candidate']
    elif mutation == 'empty_annotation':
        c['candidate']['annotation']['entity'] = ' '
    elif mutation == 'invalid_tag':
        c['active_memory'][0]['annotation']['diagnostic_tags'] = ['invented']
    elif mutation == 'duplicate_tag':
        c['active_memory'][0]['annotation']['diagnostic_tags'] = ['other', 'other']
    elif mutation == 'candidate_role_tag':
        c['candidate']['annotation']['diagnostic_tags'] = ['oracle_existing_target']
    elif mutation == 'multiple_answer_oracles':
        c = select(changed, 'plain')
        c['oracle_entry_ids'].append(c['oracle_entry_ids'][0])
    elif mutation == 'wrong_source':
        changed['source'] = 'external'
    elif mutation == 'wrong_version':
        changed['schema_version'] = '2.0'
    elif mutation == 'wrong_dataset_id':
        changed['dataset_id'] = 'other'
    else:
        raise AssertionError('Unhandled mutation')
    with pytest.raises(ValueError):
        validator.validate_dataset(changed)


@pytest.mark.parametrize('term', validator.FORBIDDEN)
def test_reject_fixture_leakage(changed, term):
    changed['cases'][0]['active_memory'][0]['text'] = term.upper()
    with pytest.raises(ValueError, match='fixture leakage'):
        validator.validate_dataset(changed)


def test_check_mode_does_not_write(corpus, tmp_path, monkeypatch, capsys):
    output = tmp_path / 'calibration.json'
    output.write_bytes(build.dataset_bytes(corpus))
    monkeypatch.setattr(build, 'OUTPUT', output)
    before = output.stat().st_mtime_ns
    assert build.main(['--check']) == 0
    assert 'CHECK PASSED' in capsys.readouterr().out
    assert output.stat().st_mtime_ns == before
    output.write_bytes(output.read_bytes() + b' ')
    with pytest.raises(ValueError, match='differs'):
        build.main(['--check'])


def test_check_mode_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(build, 'OUTPUT', tmp_path / 'missing.json')
    with pytest.raises(FileNotFoundError):
        build.main(['--check'])


def test_invalid_generation_cannot_overwrite(corpus, tmp_path, monkeypatch):
    output = tmp_path / 'calibration.json'
    output.write_bytes(b'preserve-existing')
    monkeypatch.setattr(build, 'OUTPUT', output)
    bad = copy.deepcopy(corpus)
    bad['cases'].pop()
    monkeypatch.setattr(build, 'build_dataset', lambda: bad)
    with pytest.raises(ValueError):
        build.main([])
    assert output.read_bytes() == b'preserve-existing'


def test_nondeterminism_cannot_overwrite(corpus, tmp_path, monkeypatch):
    output = tmp_path / 'calibration.json'
    output.write_bytes(b'preserve-existing')
    monkeypatch.setattr(build, 'OUTPUT', output)
    other = copy.deepcopy(corpus)
    other['cases'].reverse()
    calls = iter((corpus, other))
    monkeypatch.setattr(build, 'build_dataset', lambda: next(calls))
    with pytest.raises(ValueError, match='Nondeterministic'):
        build.main([])
    assert output.read_bytes() == b'preserve-existing'


def test_atomic_generation(corpus, tmp_path, monkeypatch, capsys):
    output = tmp_path / 'calibration.json'
    monkeypatch.setattr(build, 'OUTPUT', output)
    assert build.main([]) == 0
    assert output.read_bytes() == build.dataset_bytes(corpus)
    assert list(tmp_path.iterdir()) == [output]
    assert 'SHA-256:' in capsys.readouterr().out


@pytest.mark.parametrize('content', ['{"source": "x", "source": "y"}', '{"value": NaN}'])
def test_reject_invalid_json_fields(tmp_path, content):
    path = tmp_path / 'bad.json'
    path.write_text(content)
    with pytest.raises(ValueError):
        validator.load_dataset(path)
