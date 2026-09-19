"""Deterministic whole-value CRST answer parsing and scoring; no containment, fuzzy, embedding or LLM matching."""
import json
import re
import unicodedata

CURRENT_CORRECT, STALE_ERROR, OTHER_ERROR = 'CURRENT_CORRECT', 'STALE_ERROR', 'OTHER_ERROR'
CLASSES = (CURRENT_CORRECT, STALE_ERROR, OTHER_ERROR)
TYPE_SPECIFIC_CANONICALIZATION = 'none'
NORMALIZATION = ('Unicode NFC', 'trim', 'collapse internal whitespace', 'casefold')


def normalize(text):
    """Representation-only normalization; never a semantic equivalence rule."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text).strip()).casefold()


def strict_pairs(items):
    keys = [key for key, _ in items]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate key')
    return dict(items)


def reject_constant(name):
    raise ValueError(f'non-finite constant {name}')


def parse_answer(raw):
    """Strict {"answer": <nonblank string>} with no other field. Returns (answer, error)."""
    if not isinstance(raw, str):
        return None, 'no_content'
    try:
        value = json.loads(raw, object_pairs_hook=strict_pairs, parse_constant=reject_constant)
    except ValueError:
        return None, 'not_json'
    if type(value) is not dict or set(value) != {'answer'}:
        return None, 'wrong_fields'
    if type(value['answer']) is not str or not normalize(value['answer']):
        return None, 'blank_or_non_string_answer'
    return value['answer'], None


def assert_distinct(current, superseded):
    """Material precondition: normalized current and superseded values stay pairwise distinct."""
    values = [normalize(current), *[normalize(v) for v in superseded]]
    if len(set(values)) != len(values):
        raise ValueError('Normalized current/superseded target values are not distinct')


def classify(raw, current, superseded):
    """Whole-value normalized equality only. Raw exact equality is reported as a diagnostic."""
    assert_distinct(current, superseded)
    answer, error = parse_answer(raw)
    if error:
        return {'class': OTHER_ERROR, 'reason': error, 'answer': None, 'normalized_answer': None,
                'raw_exact_match': False}
    normalized = normalize(answer)
    if normalized == normalize(current):
        label, reason = CURRENT_CORRECT, 'equals_current_target'
    elif normalized in {normalize(v) for v in superseded}:
        label, reason = STALE_ERROR, 'equals_superseded_target'
    else:
        label, reason = OTHER_ERROR, 'not_a_target_value'
    return {'class': label, 'reason': reason, 'answer': answer, 'normalized_answer': normalized,
            'raw_exact_match': answer == current}


def run_contributions(classification):
    """Per-run contributions only; no policy-level aggregation in the pilot."""
    label = classification['class']
    return {'csa': int(label == CURRENT_CORRECT), 'srr': int(label == STALE_ERROR)}
