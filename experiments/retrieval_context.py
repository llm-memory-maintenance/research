"""Deterministic context rules only; no embedding, retrieval runner, or I/O."""

from datetime import datetime, timedelta
import hashlib
import math


def serialize_entry(entry):
    values = [entry[key] for key in ('entry_id', 'created_time', 'last_updated_time', 'text')]
    if any(not isinstance(value, str) or not value or '\n' in value or '\r' in value
           or value != value.rstrip() for value in values):
        raise ValueError('Context fields must be nonempty single-line strings without trailing whitespace')
    identity, created, updated, text = values
    return f'[memory_id={identity}; created={created}; updated={updated}] {text}'


def serialize_context(entries):
    return '\n'.join(serialize_entry(entry) for entry in entries)


def count_context_tokens(context, tokenizer):
    return len(tokenizer.encode(context, add_special_tokens=False))


def rank_entries(entries, scores):
    """Order entries by precomputed scores, breaking ties by a hash of entry_id.

    The function computes no embeddings and no retrieval quality.
    """
    if len(entries) != len(scores) or len({e['entry_id'] for e in entries}) != len(entries):
        raise ValueError('Scores must align with uniquely identified entries')
    if any(not math.isfinite(score) for score in scores):
        raise ValueError('Cosine scores must be finite')
    return [entry for entry, _ in sorted(zip(entries, scores), key=lambda pair: (
        -pair[1], hashlib.sha256(pair[0]['entry_id'].encode('utf-8')).digest()))]


def chronological_key(entry):
    def utc(value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError('Chronological timestamps must be UTC')
        return parsed

    created, updated = utc(entry['created_time']), utc(entry['last_updated_time'])
    if created > updated:
        raise ValueError('Created time must not exceed last-updated time')
    return updated, created, entry['entry_id']


def select_context(ranked_entries, k, budget, tokenizer):
    """Admit a top-k prefix, then order chronologically and verify the final block."""
    if type(k) is not int or k <= 0 or type(budget) is not int or budget < 0:
        raise ValueError('Expected positive integer k and nonnegative integer budget')
    admitted = []
    for entry in ranked_entries[:k]:
        trial = admitted + [entry]
        if count_context_tokens(serialize_context(trial), tokenizer) > budget:
            break
        admitted.append(entry)
    ordered = sorted(admitted, key=chronological_key)
    context = serialize_context(ordered)
    if count_context_tokens(context, tokenizer) > budget:
        raise ValueError('Final chronological serialization exceeds budget; no repair is attempted')
    return ordered, context
