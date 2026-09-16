"""Offline structural and semantic validator for the template-built corpus.

Uses standard-library checks corresponding to the frozen schema, not a full
JSON Schema Draft 2020-12 implementation. Text/annotation consistency and
semantic distractor roles are checked against the independently authored
lexicon. No external validation content is read or compared.
"""

import argparse
from collections import Counter
from datetime import datetime, timedelta
from itertools import product
import json
from pathlib import Path
import re

if __package__:
    from . import build_retrieval_calibration as build
else:
    import build_retrieval_calibration as build

TAGS = {'oracle_current', 'oracle_existing_target', 'stale_competing_version',
        'same_entity_different_attribute', 'different_entity_similar_attribute',
        'semantically_related_different_key', 'other'}
HARD_TAGS = {'same_entity_different_attribute', 'different_entity_similar_attribute',
             'semantically_related_different_key'}
FORBIDDEN = ('mira', 'locker', 'locker_color', 'cobalt', 'amber', 'mem-1')
COMMON_FIELDS = {'case_id', 'task', 'active_memory', 'active_memory_size'}
MAINT_FIELDS = {'maintenance_case_type', 'candidate', 'oracle_target_entry_id'}
ANSWER_FIELDS = {'query_wording', 'stale_competing_version', 'question', 'oracle_entry_ids'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), 'Expected an object')
    require(required <= value.keys() and value.keys() <= required | set(optional),
            f'Invalid fields: required {sorted(required)}, observed {sorted(value)}')


def nonempty(value):
    require(isinstance(value, str) and bool(value.strip()), 'Expected nonempty string')


def parse_time(value):
    nonempty(value)
    require(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)', value)),
            'Expected UTC RFC3339 timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.utcoffset() == timedelta(0), 'Timestamp must be UTC')
    return result


def key(annotation):
    return annotation['entity'], annotation['attribute']


def tags(entry):
    return set(entry['annotation'].get('diagnostic_tags', []))


def validate_fact(item):
    annotation = item['annotation']
    fields(annotation, {'entity', 'attribute', 'value'}, {'diagnostic_tags'})
    for name in ('entity', 'attribute', 'value'):
        nonempty(annotation[name])
    require(annotation['entity'] in build.ENTITIES, 'Entity outside independent synthetic lexicon')
    require(annotation['attribute'] in build.ATTRIBUTES, 'Unsupported canonical attribute')
    spec = build.ATTRIBUTES[annotation['attribute']]
    require(annotation['value'] in spec[1], 'Value outside attribute inventory')
    diagnostic = annotation.get('diagnostic_tags', [])
    require(isinstance(diagnostic, list) and all(isinstance(t, str) for t in diagnostic), 'Invalid tags')
    require(len(diagnostic) == len(set(diagnostic)) and set(diagnostic) <= TAGS, 'Invalid diagnostic tags')
    nonempty(item['text'])
    require(item['text'] in build.fact_forms(annotation['entity'], annotation['attribute'], annotation['value']),
            'Text does not render the annotated fact')


def validate_roles(entries, reference, *, distinct_entries=False):
    family = build.ATTRIBUTES[reference['attribute']][0]
    role_ids = {tag: set() for tag in sorted(HARD_TAGS)}
    for entry in entries:
        a = entry['annotation']
        same_entity = a['entity'] == reference['entity']
        same_attribute = a['attribute'] == reference['attribute']
        related = build.ATTRIBUTES[a['attribute']][0] == family
        valid = {
            'same_entity_different_attribute': same_entity and not same_attribute,
            'different_entity_similar_attribute': not same_entity and related,
            'semantically_related_different_key': key(a) != key(reference) and not same_attribute and related,
        }
        for tag in tags(entry) & HARD_TAGS:
            require(valid[tag], f'False distractor relationship: {tag}')
            role_ids[tag].add(entry['entry_id'])
    require(all(role_ids.values()), 'Missing required hard distractor')
    if distinct_entries:
        require(any(len(set(ids)) == 3 for ids in product(*role_ids.values())),
                'Required hard distractor roles need three distinct entry IDs')


def validate_case(case, all_entry_ids):
    require(isinstance(case, dict) and case.get('task') in ('maintenance', 'answer'), 'Invalid task')
    maintenance = case['task'] == 'maintenance'
    fields(case, COMMON_FIELDS | (MAINT_FIELDS if maintenance else ANSWER_FIELDS))
    nonempty(case['case_id'])
    size = case['active_memory_size']
    require(type(size) is int and size in build.SIZES, 'Invalid active-memory size')
    entries = case['active_memory']
    require(isinstance(entries, list) and len(entries) == size, 'Wrong active-memory length')
    by_id, chronology = {}, {}
    for entry in entries:
        fields(entry, {'entry_id', 'text', 'created_time', 'last_updated_time', 'annotation'})
        entry_id = entry['entry_id']
        nonempty(entry_id)
        require(entry_id not in all_entry_ids, 'Duplicate entry ID')
        all_entry_ids.add(entry_id)
        validate_fact(entry)
        created, updated = parse_time(entry['created_time']), parse_time(entry['last_updated_time'])
        require(created <= updated, 'Created time after last update')
        by_id[entry_id] = entry
        chronology[entry_id] = (created, updated)
    tagged = {tag: {entry['entry_id'] for entry in entries if tag in tags(entry)}
              for tag in ('oracle_current', 'oracle_existing_target', 'stale_competing_version')}
    if maintenance:
        kind = case['maintenance_case_type']
        require(kind in ('changed_state', 'same_state', 'new_key'), 'Invalid maintenance type')
        fields(case['candidate'], {'text', 'annotation'})
        validate_fact(case['candidate'])
        require(not tags(case['candidate']), 'Candidate must not carry entry role tags')
        reference = case['candidate']['annotation']
        target_id = case['oracle_target_entry_id']
        matching = [e for e in entries if key(e['annotation']) == key(reference)]
        require(not tagged['oracle_current'] and not tagged['stale_competing_version'],
                'Answer role tag in maintenance memory')
        if kind == 'new_key':
            require(target_id is None and not matching and not tagged['oracle_existing_target'],
                    'New-key candidate already exists or has an oracle')
        else:
            nonempty(target_id)
            require(target_id in by_id, 'Missing oracle reference')
            require(len(matching) == 1 and matching[0]['entry_id'] == target_id, 'Oracle key mismatch or ambiguity')
            require(tagged['oracle_existing_target'] == {target_id}, 'Oracle existing-target tags mismatch')
            same_value = reference['value'] == by_id[target_id]['annotation']['value']
            require(same_value == (kind == 'same_state'), f'Invalid {kind} candidate value')
            if kind == 'same_state':
                require(case['candidate']['text'] != by_id[target_id]['text'],
                        'Same-state candidate text must differ from oracle text')
        validate_roles(entries, reference, distinct_entries=kind != 'new_key')
        allowed_duplicate = None
    else:
        require(case['query_wording'] in ('direct', 'paraphrased'), 'Invalid query wording')
        require(type(case['stale_competing_version']) is bool, 'Stale flag must be boolean')
        oracle_ids = case['oracle_entry_ids']
        require(isinstance(oracle_ids, list) and len(oracle_ids) == 1, 'Answer needs exactly one oracle ID')
        nonempty(oracle_ids[0])
        oracle_id = oracle_ids[0]
        require(oracle_id in by_id, 'Missing oracle reference')
        require(tagged['oracle_current'] == {oracle_id} and not tagged['oracle_existing_target'],
                'Answer oracle tags mismatch')
        reference = by_id[oracle_id]['annotation']
        nonempty(case['question'])
        require(case['question'] in build.question_forms(reference['entity'], reference['attribute'], case['query_wording']),
                'Question does not match oracle or query wording')
        matching = [e for e in entries if key(e['annotation']) == key(reference)]
        if case['stale_competing_version']:
            require(len(tagged['stale_competing_version']) == 1, 'Expected exactly one stale entry')
            stale_id = next(iter(tagged['stale_competing_version']))
            require(stale_id != oracle_id, 'Stale entry cannot be the current oracle')
            old = by_id[stale_id]
            require(len(matching) == 2 and key(old['annotation']) == key(reference), 'Stale key mismatch or ambiguity')
            require(old['annotation']['value'] != reference['value'], 'Stale value equals current value')
            require(chronology[stale_id][0] < chronology[oracle_id][0]
                    and chronology[stale_id][1] < chronology[oracle_id][0], 'Stale chronology is not older')
            allowed_duplicate = key(reference)
        else:
            require(len(matching) == 1 and not tagged['stale_competing_version'], 'Unexpected stale competitor')
            allowed_duplicate = None
        validate_roles(entries, reference)
        require(any(build.ATTRIBUTES[e['annotation']['attribute']][0] != build.ATTRIBUTES[reference['attribute']][0]
                    for e in entries), 'Answer case lacks unrelated filler')
    counts = Counter(key(e['annotation']) for e in entries)
    require(all(n == 1 or (k == allowed_duplicate and n == 2) for k, n in counts.items()),
            'Unexpected duplicate state key')


def validate_dataset(dataset):
    fields(dataset, {'schema_version', 'dataset_id', 'source', 'cases'})
    require(dataset['schema_version'] == '1.0', 'Invalid schema version')
    require(dataset['dataset_id'] == 'retrieval-calibration-v1', 'Invalid dataset ID')
    require(dataset['source'] == 'synthetic_retrieval_calibration', 'Invalid dataset source')
    serialized = json.dumps(dataset, ensure_ascii=False, allow_nan=False).casefold()
    require(not any(term in serialized for term in FORBIDDEN), 'Model Qualification fixture leakage')
    cases = dataset['cases']
    require(isinstance(cases, list) and len(cases) == 140, 'Expected exactly 140 cases')
    case_ids, entry_ids = set(), set()
    composition, balance, cells = Counter(), Counter(), Counter()
    for case in cases:
        validate_case(case, entry_ids)
        require(case['case_id'] not in case_ids, 'Duplicate case ID')
        case_ids.add(case['case_id'])
        kind = case.get('maintenance_case_type', 'answer')
        composition[kind] += 1
        if kind in ('changed_state', 'same_state'):
            balance[kind, case['active_memory_size']] += 1
        if kind == 'answer':
            cells[case['query_wording'], case['active_memory_size'], case['stale_competing_version']] += 1
    require(composition == Counter(changed_state=30, same_state=30, new_key=20, answer=60), 'Wrong task composition')
    require(balance == Counter({(kind, size): 10 for kind in ('changed_state', 'same_state') for size in build.SIZES}),
            'Wrong maintenance size balance')
    require(cells == Counter({(wording, size, stale): 5 for wording in ('direct', 'paraphrased')
                             for size in build.SIZES for stale in (False, True)}), 'Wrong answer cell balance')


def load_dataset(path):
    def unique_fields(pairs):
        result = {}
        for name, value in pairs:
            require(name not in result, 'Duplicate JSON object field')
            result[name] = value
        return result

    def invalid_constant(value):
        raise ValueError(f'Invalid JSON constant: {value}')

    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_fields,
                      parse_constant=invalid_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    args = parser.parse_args(argv)
    dataset = load_dataset(args.dataset)
    validate_dataset(dataset)
    print('VALID: structural, composition, oracle, timestamp, template, and distractor checks passed')
    build.summary(dataset, args.dataset.read_bytes())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
