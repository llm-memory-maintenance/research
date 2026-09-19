"""Offline tests of the whole-value CRST answer parser and scorer."""
import json

import pytest

from crst_common import no_network  # noqa: F401
import crst_scoring as s

CURRENT, OLD = 'Gate Hazelgrave', ['Gate Amberlyn', 'Gate Dunmere']


def answer(value):
    return json.dumps({'answer': value})


def label(raw):
    return s.classify(raw, CURRENT, OLD)['class']


def test_normalization_is_representation_only():
    assert s.normalize('  Gate  Hazel\tgrave ') == 'gate hazel grave'
    assert s.normalize('Café') == s.normalize('Café')
    assert s.NORMALIZATION == ('Unicode NFC', 'trim', 'collapse internal whitespace', 'casefold')
    assert s.TYPE_SPECIFIC_CANONICALIZATION == 'none'
    assert s.normalize('07:35') != s.normalize('7:35') and s.normalize('12 minutes') != s.normalize('12')


@pytest.mark.parametrize('raw,expected', [
    (answer('Gate Hazelgrave'), s.CURRENT_CORRECT), (answer('  gate   HAZELGRAVE '), s.CURRENT_CORRECT),
    (answer('Gate Amberlyn'), s.STALE_ERROR), (answer('gate dunmere'), s.STALE_ERROR),
    (answer('Gate Ivorlea'), s.OTHER_ERROR),
    (answer('The gate is Gate Hazelgrave'), s.OTHER_ERROR), (answer('Gate Hazelgrave.'), s.OTHER_ERROR),
    (answer('Hazelgrave'), s.OTHER_ERROR), (answer('Gate Hazelgrave or Gate Amberlyn'), s.OTHER_ERROR),
    (answer('Gate Amberlyn, Gate Hazelgrave'), s.OTHER_ERROR), (answer('Gate Hazelgrave\nGate Amberlyn'), s.OTHER_ERROR),
    (answer('Gate Hazelgrave (Gate Amberlyn before)'), s.OTHER_ERROR),
    (answer(''), s.OTHER_ERROR), (answer('   '), s.OTHER_ERROR),
    ('Gate Hazelgrave', s.OTHER_ERROR), ('', s.OTHER_ERROR), (None, s.OTHER_ERROR),
    (json.dumps({'answer': 'Gate Hazelgrave', 'reason': 'x'}), s.OTHER_ERROR),
    (json.dumps({'Answer': 'Gate Hazelgrave'}), s.OTHER_ERROR), (json.dumps({}), s.OTHER_ERROR),
    (json.dumps([CURRENT]), s.OTHER_ERROR), (json.dumps({'answer': ['Gate Hazelgrave']}), s.OTHER_ERROR),
    (json.dumps({'answer': None}), s.OTHER_ERROR), (json.dumps({'answer': 5}), s.OTHER_ERROR),
    ('{"answer": "Gate Hazelgrave", "answer": "Gate Hazelgrave"}', s.OTHER_ERROR),
    ('{"answer": NaN}', s.OTHER_ERROR), ('```json\n{"answer": "Gate Hazelgrave"}\n```', s.OTHER_ERROR)])
def test_whole_value_classification(raw, expected):
    assert label(raw) == expected


def test_no_containment_or_fuzzy_matching_of_any_kind():
    for near in ('Gate Hazelgrav', 'Gate Hazlegrave', 'gatehazelgrave', 'Gate-Hazelgrave', 'Hazelgrave Gate'):
        assert label(answer(near)) == s.OTHER_ERROR


def test_current_is_checked_before_stale_and_reasons_are_explicit():
    assert s.classify(answer('Gate Hazelgrave'), CURRENT, OLD)['reason'] == 'equals_current_target'
    assert s.classify(answer('Gate Amberlyn'), CURRENT, OLD)['reason'] == 'equals_superseded_target'
    assert s.classify(answer('nope'), CURRENT, OLD)['reason'] == 'not_a_target_value'
    assert s.classify('nope', CURRENT, OLD)['reason'] == 'not_json'
    assert s.classify(answer('  '), CURRENT, OLD)['reason'] == 'blank_or_non_string_answer'


def test_raw_exact_equality_is_a_diagnostic_only():
    exact = s.classify(answer('Gate Hazelgrave'), CURRENT, OLD)
    loose = s.classify(answer('gate hazelgrave'), CURRENT, OLD)
    assert exact['raw_exact_match'] is True and loose['raw_exact_match'] is False
    assert exact['class'] == loose['class'] == s.CURRENT_CORRECT


def test_indistinguishable_targets_are_refused_before_scoring():
    with pytest.raises(ValueError):
        s.classify(answer('x'), 'Gate  Amber', ['gate amber'])
    with pytest.raises(ValueError):
        s.classify(answer('x'), 'a', ['b', 'B '])


def test_contributions_are_per_run_only():
    assert s.run_contributions(s.classify(answer(CURRENT), CURRENT, OLD)) == {'csa': 1, 'srr': 0}
    assert s.run_contributions(s.classify(answer(OLD[0]), CURRENT, OLD)) == {'csa': 0, 'srr': 1}
    assert s.run_contributions(s.classify(answer('zzz'), CURRENT, OLD)) == {'csa': 0, 'srr': 0}
    assert not hasattr(s, 'aggregate') and not hasattr(s, 'rank')


def test_local_answer_schema_is_enforced_exactly():
    import crst_prompts as prompts
    schema = prompts.answer_schema()
    assert schema['required'] == ['answer'] and schema['additionalProperties'] is False
    assert schema['properties']['answer']['minLength'] == 1 and set(schema['properties']) == {'answer'}
    for raw, reason in ((json.dumps({}), 'wrong_fields'), (json.dumps({'answer': 'x', 'note': 1}), 'wrong_fields'),
                        (json.dumps({'answer': ''}), 'blank_or_non_string_answer'),
                        (json.dumps({'answer': ' \t\n'}), 'blank_or_non_string_answer'),
                        (json.dumps({'answer': 7}), 'blank_or_non_string_answer'),
                        ('answer: x', 'not_json'), (None, 'no_content')):
        result = s.classify(raw, CURRENT, OLD)
        assert result['class'] == s.OTHER_ERROR and result['reason'] == reason
    assert s.parse_answer(json.dumps({'answer': 'x'})) == ('x', None)
