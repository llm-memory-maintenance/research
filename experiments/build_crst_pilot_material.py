"""Build or reproduce the pilot-only CRST structured scenarios offline, without naturalizing text or calling a model."""
import argparse
from copy import deepcopy
import json
import subprocess

import validate_crst_pilot_material as v
import validate_generator_qualification_fixtures as gq

# Per scenario: primary entity, hard-distractor entity (same attribute, different entity),
# target attribute id, meaning, units, eight target values, three distinct distractor values, dedicated N2
# (attribute id, meaning, units, one value), four secondary inventories, descriptive coverage. Authored
# independently of every earlier material set; all values are synthetic, self-contained and free of status
# or time wording.
SPECS = [
 ('Seminar Brindle', 'Seminar Kestrel', 'desk_opening', 'registration desk opening time',
  '24-hour local clock; one synthetic day',
  ['06:35', '06:50', '07:35', '08:05', '08:40', '09:20', '10:05', '10:55'], ['12:25', '12:55', '13:35'],
  ('room_code', 'seminar room identifier', 'opaque code', ['ROM-B47']),
  [('moderator', 'seminar moderator', 'synthetic person', ['Ansel Wickham', 'Perpetua Drune', 'Kolya Thrale']),
   ('hall_capacity', 'seating capacity', 'seats', ['40 seats', '55 seats', '72 seats']),
   ('handout', 'handout format', 'format label', ['stapled packet', 'folded card', 'loose sheets']),
   ('coffee_break', 'coffee break length', 'minutes', ['22 minutes', '33 minutes', '42 minutes'])],
  ['times', 'scheduling', 'numeric_values']),
 ('Ferry crossing Wrenfield', 'Ferry crossing Halloway', 'embark_gate', 'assigned embarkation gate', 'gate label',
  ['Gate Amberlyn', 'Gate Bristlecone', 'Gate Corvane', 'Gate Dunmere', 'Gate Eldrith', 'Gate Fallowick',
   'Gate Gorsemoor', 'Gate Hazelgrave'], ['Gate Ivorlea', 'Gate Jessamere', 'Gate Kelderby'],
  ('reservation_code', 'ferry reservation identifier', 'opaque code', ['BKG-W38']),
  [('cabin_class', 'cabin class', 'class label', ['class Harbor', 'class Anchor', 'class Beacon']),
   ('deck_level', 'passenger deck level', 'deck label', ['Deck 2', 'Deck 5', 'Deck 7']),
   ('meal_plan', 'onboard meal plan', 'plan label', ['plan pantry', 'plan galley', 'plan hearth']),
   ('bag_limit', 'carry-on limit', 'kilograms', ['6 kilograms', '9 kilograms', '12 kilograms'])],
  ['locations', 'travel', 'categorical_values']),
]


def build_fixtures():
    fixtures = []
    for i, spec in enumerate(SPECS):
        primary, distractor, attr, meaning, units, target_values, hard_values, n2, others, coverage = spec
        identity = v.SCENARIOS[i]['scenario_id']
        entities = [{'entity_id': identity + '-primary', 'name': primary},
                    {'entity_id': identity + '-distractor', 'name': distractor}]
        definitions = [(attr, meaning, units, target_values), n2, *others]
        attributes = [{'attribute_id': a, 'meaning': m, 'units_or_interpretation': u} for a, m, u, _ in definitions]
        keys = []
        for key, entity, definition, role in [
            ('k_target', entities[0]['entity_id'], definitions[0], 'target'),
            ('k_hard', entities[1]['entity_id'], (attr, meaning, units, hard_values), 'hard_distractor'),
            ('k_n2', entities[0]['entity_id'], n2, 'dedicated_n2_secondary'),
            *[(k, entities[0]['entity_id'], d, 'updateable_secondary') for k, d in zip(gq.KEYS[3:], others)]]:
            keys.append({'state_key': key, 'entity_id': entity, 'attribute_id': definition[0],
                         'initial_value': definition[3][0], 'role': role, 'value_inventory': definition[3]})
        keymap = {k['state_key']: k for k in keys}
        domain_index = gq.DOMAINS.index(v.SCENARIOS[i]['domain'])
        initial_order = dict(zip(gq.EVENTS[:7], v.initial_keys(domain_index)))
        reference = {'domain': v.SCENARIOS[i]['domain'], 'entities': entities, 'attributes': attributes,
                     'state_keys': keys, 'initial_order': initial_order,
                     'question_intent': {'entity_id': entities[0]['entity_id'], 'attribute_id': attr,
                                         'intent': f'Ask only for the current {meaning} of {primary}.'},
                     'target_state_key': 'k_target', 'hard_distractor_key': 'k_hard',
                     'dedicated_n2_secondary_key': 'k_n2', 'q_target': 'k_target',
                     'gold_current_value': target_values[-1], 'coverage': coverage, 'variants': {}}
        for variant in gq.VARIANTS:
            state, counts, history, events = {}, {k: 0 for k in gq.KEYS}, {k: [] for k in gq.KEYS}, []
            for label in gq.EVENTS:
                if label.startswith('I'):
                    key, semantics = initial_order[label], 'initial'
                    value = keymap[key]['initial_value']
                elif label.startswith('U'):
                    semantics = 'changed_state'
                    if label in gq.SCHEDULES[variant]:
                        key, value = 'k_target', target_values[int(label[1:])]
                    else:
                        key = v.allocation(domain_index)[variant][label]
                        counts[key] += 1
                        value = keymap[key]['value_inventory'][counts[key]]
                else:
                    key, semantics = ('k_target' if label == 'N1' else 'k_n2'), 'same_state'
                    value = state[key]
                previous = state.get(key)
                if semantics == 'changed_state':
                    history[key].append(previous)
                state[key] = value
                events.append({'event': label, 'state_key': key, 'current_value': value, 'semantics': semantics,
                               'previous_value': previous, 'superseded_values': list(history[key]),
                               'state_after': dict(state)})
            reference['variants'][variant] = {'events': events, 'final_state': dict(state)}
        fixtures.append({'schema_version': v.SCHEMA, 'fixture_id': identity, 'purpose': v.PURPOSE,
                         'reference': reference})
    v.validate_set(fixtures)
    return deepcopy(fixtures)


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def artifacts(source_commit):
    fixtures = build_fixtures()
    files = {f'fixtures/{s["slug"]}.json': pretty(f) for s, f in zip(v.SCENARIOS, fixtures)}
    files['reference-schema.json'] = pretty(v.reference_schema())
    manifest = {'schema_version': v.MANIFEST_SCHEMA, 'status': 'FROZEN', 'total_scenarios': 2,
                'purpose': v.PURPOSE, 'versions': gq.VERSIONS, 'construction_source_commit': source_commit,
                'reference_schema_sha256': gq.sha(files['reference-schema.json']),
                'allocation_rule': v.ALLOCATION_RULE, 'candidate_template': v.pol.TEMPLATE,
                'generator_assignment': {s['scenario_id']: s['generator'] for s in v.SCENARIOS},
                'prohibited_uses': v.PROHIBITED_USES, 'not_final_crst_data': True,
                'not_generator_qualification_data': True, 'origin': v.ORIGIN,
                'reserved_exclusions': v.reserved_exclusions(fixtures),
                'coverage_summary': sorted({c for f in fixtures for c in f['reference']['coverage']}),
                'scenarios': [v.manifest_entry(f, files[f'fixtures/{s["slug"]}.json'])
                              for s, f in zip(v.SCENARIOS, fixtures)]}
    files['manifest.json'] = pretty(manifest)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Rebuild in memory with the recorded construction commit and compare byte for byte; '
                             'writes nothing')
    args = parser.parse_args()
    if args.check:
        manifest, _ = v.validate_directory()
        for path, data in artifacts(manifest['construction_source_commit']).items():
            gq.require((v.DIRECTORY / path).read_bytes() == data, f'Reproduction mismatch: {path}')
        print('Byte-identical reproduction: 2 pilot-only scenarios, schema and manifest.')
    else:
        source = subprocess.check_output(['git', '-C', str(v.ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        fixtures = build_fixtures()
        v.check_separation(fixtures)
        v.DIRECTORY.mkdir(exist_ok=False)
        (v.DIRECTORY / 'fixtures').mkdir()
        for path, data in artifacts(source).items():
            with (v.DIRECTORY / path).open('xb') as stream:
                stream.write(data)
        v.validate_directory()
        print('Constructed 2 pilot-only CRST scenarios.')
    print('Manifest SHA-256:', gq.sha((v.DIRECTORY / 'manifest.json').read_bytes()))


if __name__ == '__main__':
    main()
