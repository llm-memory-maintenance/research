"""Offline structural/reference validation; no naturalization or semantic judging."""
import argparse
from collections import Counter
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'data/generator-qualification'
DOMAINS = ('Scheduling', 'Travel', 'Project Planning', 'Task Assignment', 'Software Configuration',
           'Personal Preference', 'Purchase & Order', 'Study Planning', 'Communication',
           'Service & Subscription', 'Location & Logistics', 'Quantitative Planning')
SLUGS = ('scheduling', 'travel', 'project-planning', 'task-assignment', 'software-configuration',
         'personal-preference', 'purchase-order', 'study-planning', 'communication',
         'service-subscription', 'location-logistics', 'quantitative-planning')
EVENTS = tuple([f'I{i}' for i in range(1, 8)] + [f'U{i}' for i in range(1, 7)] + ['N1', 'U7', 'N2'])
VARIANTS = ('low', 'medium', 'high')
SCHEDULES = {'low': ['U7'], 'medium': ['U1', 'U3', 'U5', 'U7'],
             'high': [f'U{i}' for i in range(1, 8)]}
KEYS = ('k_target', 'k_hard', 'k_n2', 'k_a', 'k_b', 'k_c', 'k_d')
PURPOSE = 'GENERATOR-QUALIFICATION-ONLY'
VERSIONS = {'prompt_version': 'crst-naturalization-prompt/1.1.0',
            'input_contract_version': 'crst-naturalization-input/1.1.0',
            'output_schema_version': 'crst-naturalization-triplet/1.0.0'}
ALLOCATION_RULE = ('Zero-based domain index i: rotate [k_a,k_b,k_c,k_d] left by i mod 4. '
                   'Low: rotate [k_hard,*rotated_four,rotated_four[0]] left by i mod 6 '
                   'and assign to U1..U6. Medium: rotate [k_hard,rotated_four[1],rotated_four[2]] '
                   'left by i mod 3 and assign to U2,U4,U6. High: none. '
                   'Qualification-only; not a final CRST allocation decision.')
Text = Annotated[str, StringConstraints(min_length=1, pattern=r'\S')]
Key = Literal['k_target', 'k_hard', 'k_n2', 'k_a', 'k_b', 'k_c', 'k_d']
Initial = Literal['I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7']
Label = Literal['I1', 'I2', 'I3', 'I4', 'I5', 'I6', 'I7', 'U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'N1', 'U7', 'N2']
Role = Literal['target', 'hard_distractor', 'dedicated_n2_secondary', 'updateable_secondary']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Entity(Strict):
    entity_id: Text
    name: Text


class Attribute(Strict):
    attribute_id: Text
    meaning: Text
    units_or_interpretation: Text


class StateKey(Strict):
    state_key: Key
    entity_id: Text
    attribute_id: Text
    initial_value: Text
    role: Role


class ReferenceKey(StateKey):
    value_inventory: list[Text]


class Question(Strict):
    entity_id: Text
    attribute_id: Text
    intent: Text


class Event(Strict):
    event: Label
    state_key: Key
    current_value: Text
    semantics: Literal['initial', 'changed_state', 'same_state']


class ReferenceEvent(Event):
    previous_value: Text | None
    superseded_values: list[Text]
    state_after: dict[Key, Text]


class InputVariants(Strict):
    low: list[Event] = Field(min_length=16, max_length=16)
    medium: list[Event] = Field(min_length=16, max_length=16)
    high: list[Event] = Field(min_length=16, max_length=16)


class ReferenceVariant(Strict):
    events: list[ReferenceEvent] = Field(min_length=16, max_length=16)
    final_state: dict[Key, Text]


class ReferenceVariants(Strict):
    low: ReferenceVariant
    medium: ReferenceVariant
    high: ReferenceVariant


class Input(Strict):
    domain: Literal[DOMAINS]
    entities: list[Entity]
    attributes: list[Attribute]
    state_keys: list[StateKey] = Field(min_length=7, max_length=7)
    initial_order: dict[Initial, Key]
    question_intent: Question
    variants: InputVariants


class Reference(Strict):
    domain: Literal[DOMAINS]
    entities: list[Entity]
    attributes: list[Attribute]
    state_keys: list[ReferenceKey] = Field(min_length=7, max_length=7)
    initial_order: dict[Initial, Key]
    question_intent: Question
    variants: ReferenceVariants
    target_state_key: Key
    hard_distractor_key: Key
    dedicated_n2_secondary_key: Key
    q_target: Key
    gold_current_value: Text
    coverage: list[Text]


class Fixture(Strict):
    schema_version: Literal['generator-qualification-reference/1.0.0']
    fixture_id: Text
    purpose: Literal['GENERATOR-QUALIFICATION-ONLY']
    reference: Reference


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'Duplicate JSON key')
            result[k] = v
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def reference_schema():
    schema = Fixture.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$id'] = 'urn:crst:generator-qualification-reference:1.0.0'
    schema['description'] = ('Reference-only truth. Model-facing input is derived by projection. '
                             'Identifier uniqueness, trajectories and cross-file constraints require the validator. '
                             'State maps and initial_order allow only the enumerated keys with string values; '
                             'state_after contains just keys initialized by that event.')
    return schema


def allocation(index):
    def rotate(items, amount):
        return items[amount:] + items[:amount]
    others = rotate(list(KEYS[3:]), index % 4)
    return {'low': dict(zip([f'U{i}' for i in range(1, 7)],
                           rotate(['k_hard', *others, others[0]], index % 6))),
            'medium': dict(zip(['U2', 'U4', 'U6'], rotate(['k_hard', others[1], others[2]], index % 3))),
            'high': {}}


def project(fixture):
    """One allowlisted projection; never copy reference-only event fields."""
    r = fixture['reference']
    payload = {k: r[k] for k in ('domain', 'entities', 'attributes', 'initial_order', 'question_intent')}
    payload['state_keys'] = [{k: item[k] for k in StateKey.model_fields} for item in r['state_keys']]
    payload['variants'] = {v: [{k: event[k] for k in Event.model_fields} for event in r['variants'][v]['events']]
                           for v in VARIANTS}
    # Materialize an independent object, with no shared mutable reference truth.
    return json.loads(canonical(payload))


def normalized_words(text):
    """NFKC/casefold word comparison; punctuation and spacing are separators."""
    return re.findall(r'\w+', unicodedata.normalize('NFKC', text).casefold())


def validate_input(payload):
    """Input 1.1.0 shape and qualification-specific semantic invariants."""
    Input.model_validate(payload)
    entities = {e['entity_id'] for e in payload['entities']}
    attributes = {a['attribute_id'] for a in payload['attributes']}
    require(len(entities) == len(payload['entities']) and len(attributes) == len(payload['attributes']), 'Duplicate identity')
    names = [tuple(normalized_words(e['name'])) for e in payload['entities']]
    require(all(names) and len(set(names)) == len(names), 'Empty/duplicate normalized entity display name')
    items = payload['state_keys']
    keys = {x['state_key']: x for x in items}
    require(len(items) == 7 and set(keys) == set(KEYS), 'Seven unique state keys required')
    require(Counter(x['role'] for x in items) == Counter(target=1, hard_distractor=1,
            dedicated_n2_secondary=1, updateable_secondary=4), 'Wrong role counts')
    require(len({(x['entity_id'], x['attribute_id']) for x in items}) == 7, 'Duplicate semantic key')
    for x in items:
        require(x['entity_id'] in entities and x['attribute_id'] in attributes, 'Unresolved identity')
    role = {x['role']: x['state_key'] for x in items if x['role'] != 'updateable_secondary'}
    require(role == dict(target='k_target', hard_distractor='k_hard', dedicated_n2_secondary='k_n2'), 'Role/key mismatch')
    require(set(payload['initial_order']) == set(EVENTS[:7]) and
            set(payload['initial_order'].values()) == set(KEYS), 'Initial coverage')
    q = payload['question_intent']
    require((q['entity_id'], q['attribute_id']) ==
            (keys['k_target']['entity_id'], keys['k_target']['attribute_id']), 'Wrong Q target')
    words = normalized_words(q['intent'])
    primary = normalized_words(next(e['name'] for e in payload['entities'] if e['entity_id'] == q['entity_id']))
    require(bool(words) and any(words[i:i + len(primary)] == primary for i in range(len(words))),
            'Q intent missing primary entity name')
    require(all(a != b for a, b in zip(words, words[1:])), 'Q intent repeated word')
    # A hard distractor uses the same property of an explicitly different entity.
    require(keys['k_hard']['attribute_id'] == keys['k_target']['attribute_id'] and
            keys['k_hard']['entity_id'] != keys['k_target']['entity_id'], 'Hard distractor identity')
    # Protocol schedules are explicit here, independent of construction helpers.
    expected_positions = {'low': {'U7'}, 'medium': {'U1', 'U3', 'U5', 'U7'},
                          'high': {'U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7'}}
    ordinary = {x['state_key'] for x in items if x['role'] == 'updateable_secondary'}
    finals, shared_values = [], {}
    for v in VARIANTS:
        events = payload['variants'][v]
        require([e['event'] for e in events] == list(EVENTS), 'Event completeness/order')
        state, seen, positions, secondary = {}, set(), [], {}
        for e in events:
            label, key, value = e['event'], e['state_key'], e['current_value']
            if label.startswith('I'):
                require(key == payload['initial_order'][label] and value == keys[key]['initial_value']
                        and e['semantics'] == 'initial', 'Initial truth mismatch')
            elif label.startswith('U'):
                require(e['semantics'] == 'changed_state' and value != state[key], 'Changed-state violation')
                require(key != 'k_n2', 'Dedicated secondary updated')
                if key == 'k_target':
                    positions.append(label)
                    require(value not in seen, 'Target reversion')
                    require(label not in shared_values or shared_values[label] == value,
                            'Shared target U value mismatch')
                    shared_values[label] = value
                else:
                    secondary[label] = key
            else:
                require(key == ('k_target' if label == 'N1' else 'k_n2') and
                        e['semantics'] == 'same_state' and value == state[key], f'{label} reaffirmation')
            state[key] = value
            if key == 'k_target':
                seen.add(value)
        require(set(positions) == expected_positions[v], 'Target schedule')
        counts = Counter(secondary.values())
        if v == 'low':
            require(len(secondary) == 6 and counts['k_hard'] == 1 and
                    set(counts) == ordinary | {'k_hard'} and
                    sorted(counts[k] for k in ordinary) == [1, 1, 1, 2], 'Low secondary coverage')
        elif v == 'medium':
            require(len(secondary) == 3 and counts['k_hard'] == 1 and
                    len(set(counts) & ordinary) == 2 and set(counts) <= ordinary | {'k_hard'},
                    'Medium secondary coverage')
        else:
            require(not secondary, 'High secondary coverage')
        finals.append(state['k_target'])
    require(len(set(finals)) == 1, 'Final convergence')


def validate_fixture(fixture):
    Fixture.model_validate(fixture)
    r = fixture['reference']
    require(fixture['fixture_id'] == 'gq-' + SLUGS[DOMAINS.index(r['domain'])] + '-01', 'Fixture identity/domain mismatch')
    require((r['target_state_key'], r['hard_distractor_key'], r['dedicated_n2_secondary_key'], r['q_target']) ==
            ('k_target', 'k_hard', 'k_n2', 'k_target'), 'Reference role/Q mismatch')
    require(bool(r['coverage']) and len(r['coverage']) == len(set(r['coverage'])), 'Coverage required')
    payload = project(fixture)
    validate_input(payload)
    keys = {x['state_key']: x for x in r['state_keys']}
    for item in keys.values():
        values = item['value_inventory']
        require(bool(values) and values[0] == item['initial_value'] and len(values) == len(set(values)), 'Value inventory')
    require(len(keys['k_target']['value_inventory']) == 8, 'Eight unique target values required')
    require(len(keys['k_n2']['value_inventory']) == 1, 'Dedicated secondary inventory')
    require(not set(keys['k_target']['value_inventory']) & set(keys['k_hard']['value_inventory']), 'Distractor/target values overlap')
    for v in VARIANTS:
        state, history = {}, {k: [] for k in KEYS}
        for e in r['variants'][v]['events']:
            key, value = e['state_key'], e['current_value']
            require(value in keys[key]['value_inventory'], 'Value outside inventory')
            require(e['previous_value'] == state.get(key), 'Incorrect previous value')
            if e['semantics'] == 'changed_state':
                history[key].append(state[key])
            require(e['superseded_values'] == history[key], 'Incorrect superseded values')
            state[key] = value
            require(e['state_after'] == state, 'Incorrect state_after')
        require(r['variants'][v]['final_state'] == state, 'Incorrect final state')
        require(state['k_target'] == r['gold_current_value'] == keys['k_target']['value_inventory'][-1], 'Incorrect gold current value')
    return payload


def manifest_entry(fixture, raw):
    r = fixture['reference']
    return {'fixture_id': fixture['fixture_id'], 'domain': r['domain'],
            'fixture_path': 'fixtures/' + SLUGS[DOMAINS.index(r['domain'])] + '.json',
            'sha256': sha(raw), 'projection_sha256': sha(canonical(project(fixture))),
            'target_state_key': r['target_state_key'], 'hard_distractor_key': r['hard_distractor_key'],
            'dedicated_n2_secondary_key': r['dedicated_n2_secondary_key'], 'target_schedules': SCHEDULES,
            'secondary_allocation': {v: {e['event']: e['state_key'] for e in r['variants'][v]['events']
                if e['event'].startswith('U') and e['state_key'] != r['target_state_key']} for v in VARIANTS},
            'final_target_value': r['gold_current_value'], 'coverage': r['coverage'], 'purpose': PURPOSE}


def validate_set(fixtures):
    require(len(fixtures) == 12, 'Exactly twelve fixtures required')
    require(len({f['fixture_id'] for f in fixtures}) == 12, 'Duplicate fixture ID')
    require(Counter(f['reference']['domain'] for f in fixtures) == Counter(DOMAINS), 'One fixture per domain')
    return [validate_fixture(f) for f in fixtures]


def validate_directory(directory=DIRECTORY):
    directory = Path(directory)
    manifest = read(directory / 'manifest.json')
    expected_fields = {'schema_version', 'status', 'total_fixtures', 'purpose', 'versions', 'construction_source_commit',
                       'execution_package_reference', 'reference_schema_sha256', 'allocation_rule', 'same_set_for',
                       'not_final_crst_data', 'origin', 'coverage_summary', 'fixtures'}
    require(set(manifest) == expected_fields, 'Manifest fields')
    require(manifest['schema_version'] == 'generator-qualification-manifest/1.0.0' and
            manifest['status'] == 'FROZEN' and manifest['total_fixtures'] == 12 and
            manifest['purpose'] == PURPOSE and manifest['versions'] == VERSIONS and
            manifest['same_set_for'] == ['G1', 'G2'] and manifest['not_final_crst_data'] is True and
            manifest['allocation_rule'] == ALLOCATION_RULE, 'Manifest contract')
    commit = manifest['construction_source_commit']
    require(type(commit) is str and len(commit) == 40 and all(c in '0123456789abcdef' for c in commit), 'Construction commit')
    require(manifest['origin'] == 'Independently authored synthetic structured truth; no external corpus content or model naturalization.', 'Origin')
    require(manifest['execution_package_reference'] == {
        'config_path': 'configs/generator-capability-probe.yaml',
        'capability_evidence_path': 'results/generator-capability-probe/attempt-02/probe.json',
        'capability_evidence_sha256': 'b8982ac18e74fded527c3680e26082cf505fadbe33edf53ea103494b7ad57c8f',
        'status': 'FROZEN'}, 'Execution reference')
    schema_file = directory / 'reference-schema.json'
    require(sha(schema_file.read_bytes()) == manifest['reference_schema_sha256'] and
            read(schema_file) == reference_schema(), 'Reference schema drift')
    require(len(manifest['fixtures']) == 12, 'Manifest fixture count')
    require([e['fixture_path'] for e in manifest['fixtures']] == ['fixtures/' + s + '.json' for s in SLUGS], 'Manifest paths/order')
    require({p.name for p in (directory / 'fixtures').iterdir()} == {s + '.json' for s in SLUGS}, 'Unexpected/missing fixture files')
    fixtures = [read(directory / e['fixture_path']) for e in manifest['fixtures']]
    projections = validate_set(fixtures)
    probe = read(ROOT / 'data/generator-capability-probe/probe-input.json')
    probe_names = {e['name'] for e in probe['entities']}
    for fixture, projection, entry in zip(fixtures, projections, manifest['fixtures']):
        require(entry == manifest_entry(fixture, (directory / entry['fixture_path']).read_bytes()), 'Manifest hash/summary mismatch')
        require(canonical(projection) != canonical(probe) and
                not probe_names & {e['name'] for e in projection['entities']}, 'Capability Probe content reused')
    require(manifest['coverage_summary'] == sorted({c for f in fixtures for c in f['reference']['coverage']}), 'Coverage summary')
    return manifest, fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path, default=DIRECTORY)
    args = parser.parse_args()
    manifest, _ = validate_directory(args.directory)
    print('VALID: 12 frozen qualification-only fixtures; no naturalization or qualification executed.')
    print('Manifest SHA-256:', sha((args.directory / 'manifest.json').read_bytes()))


if __name__ == '__main__':
    main()
