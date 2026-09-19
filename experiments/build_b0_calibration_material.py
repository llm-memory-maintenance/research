"""Reproduce the calibration-only B0 structured scenarios offline; never naturalize text."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import validate_b0_calibration_material as v
import validate_generator_qualification_fixtures as gq

# Per domain: primary entity, same-property distractor entity, target attribute id, meaning, units,
# eight target values, three distinct distractor values, dedicated N2 (attribute id, meaning, units,
# one value), four secondary inventories, descriptive coverage. Authored independently of every
# qualification fixture; all values are synthetic and self-contained.
SPECS = [
 ('Cedar workshop', 'Willow workshop', 'kickoff_time', 'scheduled workshop kickoff time',
  '24-hour local clock; one synthetic day',
  ['07:20', '07:55', '08:25', '09:15', '09:50', '10:25', '11:05', '11:40'], ['14:10', '14:45', '15:20'],
  ('hall_code', 'workshop hall identifier', 'opaque code', ['HAL-C52']),
  [('lead', 'workshop lead', 'synthetic person', ['Marek Ollin', 'Tamsin Verda', 'Ilse Quorn']),
   ('capacity', 'workshop capacity', 'participants', ['14 participants', '18 participants', '22 participants']),
   ('material_set', 'workshop material set', 'material label', ['clay set', 'felt set', 'wire set']),
   ('break_length', 'scheduled break length', 'minutes', ['10 minutes', '15 minutes', '20 minutes'])],
  ['times', 'scheduling', 'numeric_values']),
 ('Coach tour Larkspur', 'Coach tour Foxglove', 'overnight_stop', 'planned overnight stopover',
  'fictional town name',
  ['Brenmar', 'Coldwick', 'Dunhollow', 'Eskerby', 'Fennimore', 'Garrowick', 'Hollinmere', 'Ivelstone'],
  ['Jaspermoor', 'Kettlewynd', 'Lorimere'], ('ticket_code', 'tour ticket identifier', 'opaque code', ['TKT-L58']),
  [('seat_row', 'assigned seat row', 'row label', ['Row 4', 'Row 9', 'Row 12']),
   ('pickup_stop', 'pickup stop', 'stop label', ['Stop Anvil Lane', 'Stop Bell Court', 'Stop Cobb Way']),
   ('luggage_limit', 'luggage allowance', 'kilograms', ['15 kilograms', '20 kilograms', '25 kilograms']),
   ('guide_style', 'guide style', 'style label', ['storytelling guide', 'technical guide', 'scenic guide'])],
  ['locations', 'travel', 'quantities']),
 ('Initiative Quillon', 'Initiative Bramwell', 'phase_label', 'current project phase', 'phase label',
  ['scoping phase', 'sourcing phase', 'drafting phase', 'prototyping phase', 'piloting phase', 'tuning phase',
   'hardening phase', 'wrap-up phase'], ['audit phase', 'budgeting phase', 'closeout phase'],
  ('ledger_code', 'initiative ledger identifier', 'opaque code', ['LDG-Q31']),
  [('sponsor', 'initiative sponsor', 'synthetic team', ['Team Orchard', 'Team Beacon', 'Team Ferrous']),
   ('checkpoint', 'next checkpoint', 'checkpoint label',
    ['Checkpoint Ridgeline', 'Checkpoint Millrace', 'Checkpoint Tidewater']),
   ('budget_band', 'budget band', 'band label', ['Band Silver', 'Band Copper', 'Band Zinc']),
   ('risk_rating', 'risk rating', 'rating label', ['low risk', 'moderate risk', 'elevated risk'])],
  ['planning', 'categorical_values', 'assignments']),
 ('Ticket Marrow', 'Ticket Tallow', 'ticket_owner', 'assigned ticket owner', 'synthetic person name',
  ['Odalys Prewitt', 'Lennox Farrow', 'Ines Calder', 'Bram Tolliver', 'Hesper Haskett', 'Jovan Pellam',
   'Sabine Orrin', 'Cyrus Delaine'], ['Petra Vance', 'Rilan Moss', 'Ottoline Grey'],
  ('ticket_ref', 'ticket reference code', 'opaque code', ['TIC-M83']),
  [('urgency', 'ticket urgency', 'urgency label', ['urgency routine', 'urgency elevated', 'urgency critical']),
   ('due_stamp', 'ticket due stamp', 'synthetic date label', ['Day Harrow', 'Day Ilbeck', 'Day Jessup']),
   ('attachment', 'required attachment', 'attachment label',
    ['chart attachment', 'photo attachment', 'sheet attachment']),
   ('approver', 'ticket approver', 'synthetic person', ['Talin Rusk', 'Verity Holm', 'Emeric Sayle'])],
  ['assignments', 'categorical_values', 'planning']),
 ('Deploy target Sable', 'Deploy target Umber', 'cache_policy', 'selected cache policy', 'policy label',
  ['ttl-short', 'ttl-medium', 'ttl-long', 'sliding-30', 'sliding-60', 'sliding-90', 'pinned-soft', 'pinned-hard'],
  ['no-cache', 'edge-only', 'bypass-all'],
  ('deploy_code', 'deploy target identifier', 'opaque code', ['DEP-S72']),
  [('pool_size', 'worker pool size', 'workers', ['3 workers', '5 workers', '9 workers']),
   ('request_timeout', 'request timeout', 'seconds', ['12 seconds', '30 seconds', '45 seconds']),
   ('log_sink', 'log destination', 'sink label', ['sink-harbor', 'sink-lantern', 'sink-quarry']),
   ('region_tag', 'deployment region tag', 'region label', ['region-fjord', 'region-mesa', 'region-delta'])],
  ['configuration_values', 'numeric_values', 'categorical_values']),
 ('Guest Perrin Tallis', 'Guest Odessa Kray', 'tea_blend', 'preferred tea blend', 'blend label',
  ['smoky pine', 'malted oat', 'citrus bark', 'wild fennel', 'dry hibiscus', 'rose husk', 'toasted barley',
   'cardamom root'], ['mint stem', 'plain leaf', 'ginger chip'],
  ('guest_code', 'guest preference record identifier', 'opaque code', ['GST-P16']),
  [('sweetener', 'preferred sweetener', 'sweetener label', ['honey drop', 'cane syrup', 'no sweetener']),
   ('cup_style', 'preferred cup style', 'style label', ['tall mug', 'wide bowl', 'narrow glass']),
   ('serving_temp', 'preferred serving temperature', 'degrees Celsius', ['60 degrees', '70 degrees', '80 degrees']),
   ('brew_time', 'preferred brew time', 'minutes', ['3 minutes', '4 minutes', '6 minutes'])],
  ['preferences', 'categorical_values', 'numeric_values']),
 ('Purchase Alcove', 'Purchase Bastion', 'tile_quantity', 'ordered number of ceramic tiles', 'tiles',
  [f'{n} tiles' for n in (36, 44, 52, 61, 73, 88, 94, 107)], ['128 tiles', '136 tiles', '150 tiles'],
  ('po_code', 'purchase identifier', 'opaque code', ['PUR-A47']),
  [('finish', 'tile finish', 'finish label', ['matte finish', 'satin finish', 'gloss finish']),
   ('carrier', 'delivery carrier', 'carrier label', ['Carrier Northgate', 'Carrier Silverline', 'Carrier Redoak']),
   ('invoice_terms', 'invoice terms', 'terms label', ['net 15', 'net 30', 'net 45']),
   ('crate_type', 'crate type', 'crate label', ['slatted crate', 'solid crate', 'folded crate'])],
  ['ordering', 'quantities', 'numeric_values']),
 ('Reading circle Thistle', 'Reading circle Bracken', 'focus_text', 'current focus text', 'fictional text title',
  ['Ledger of Moths', 'The Salt Orchard', 'Notes on Lanterns', 'A Grammar of Tides', 'The Copper Almanac',
   'Field Guide to Echoes', 'The Glass Cartographer', 'Winter Inventory'],
  ['The Quiet Foundry', 'Atlas of Small Rivers', 'Marginalia of Rain'],
  ('circle_code', 'reading circle identifier', 'opaque code', ['RDC-T85']),
  [('session_slot', 'circle session slot', 'slot label', ['Slot Dawn', 'Slot Noon', 'Slot Dusk']),
   ('chapter_range', 'assigned chapter range', 'chapters',
    ['chapters 1 to 3', 'chapters 4 to 6', 'chapters 7 to 9']),
   ('circle_host', 'circle host', 'synthetic person', ['Halden Voss', 'Marisol Teague', 'Corin Ashby']),
   ('note_format', 'note format', 'format label', ['margin notes', 'index cards', 'summary sheet'])],
  ['study_planning', 'categorical_values', 'assignments']),
 ('Mailing list Ember', 'Mailing list Garnet', 'send_window', 'weekly send window', 'named window',
  ['Monday 07:00', 'Tuesday 08:30', 'Wednesday 09:15', 'Thursday 10:45', 'Friday 12:00', 'Saturday 13:30',
   'Sunday 15:15', 'Monday 16:40'], ['Tuesday 18:20', 'Thursday 19:05', 'Saturday 20:10'],
  ('list_code', 'mailing list identifier', 'opaque code', ['MLS-E92']),
  [('sender_name', 'sender display name', 'synthetic sender',
    ['Sender Ruskin Hall', 'Sender Delphine Ward', 'Sender Osric Lane']),
   ('reply_alias', 'reply-to alias', 'alias label', ['alias help-desk', 'alias front-line', 'alias night-shift']),
   ('tone', 'message tone', 'tone label', ['formal tone', 'friendly tone', 'concise tone']),
   ('footer', 'message footer', 'footer label', ['footer plain', 'footer legal', 'footer seasonal'])],
  ['communication_settings', 'times', 'categorical_values']),
 ('Membership Lodestar', 'Membership Zephyrine', 'membership_tier', 'selected membership tier', 'tier label',
  ['Tier Basalt', 'Tier Granite', 'Tier Slate', 'Tier Marble', 'Tier Obsidian', 'Tier Quartzite', 'Tier Jasper',
   'Tier Onyx'], ['Tier Pumice', 'Tier Chalk', 'Tier Flint'],
  ('membership_code', 'membership identifier', 'opaque code', ['MEM-L64']),
  [('billing_period', 'billing period', 'months', ['1 month', '3 months', '12 months']),
   ('device_limit', 'device limit', 'devices', ['2 devices', '4 devices', '6 devices']),
   ('storage_quota', 'storage quota', 'gigabytes', ['50 gigabytes', '200 gigabytes', '1000 gigabytes']),
   ('payment_method', 'payment method', 'method label',
    ['method card-alpha', 'method transfer-beta', 'method voucher-gamma'])],
  ['subscription_state', 'categorical_values', 'quantities']),
 ('Freight lot Halyard', 'Freight lot Keelson', 'loading_dock', 'assigned loading dock', 'dock label',
  ['Dock Aldermere', 'Dock Brackwater', 'Dock Cindermoor', 'Dock Duskfield', 'Dock Emberwick', 'Dock Frostlea',
   'Dock Gladehurst', 'Dock Hartsgill'], ['Dock Ironvale', 'Dock Juniperton', 'Dock Kingsmarch'],
  ('lot_code', 'freight lot identifier', 'opaque code', ['FRL-H29']),
  [('forklift', 'assigned forklift', 'vehicle label', ['Lift F11', 'Lift F12', 'Lift F13']),
   ('pallet_count', 'pallet count', 'pallets', ['8 pallets', '14 pallets', '21 pallets']),
   ('aisle', 'storage aisle', 'aisle label', ['Aisle 3B', 'Aisle 5D', 'Aisle 7F']),
   ('inspector', 'lot inspector', 'synthetic person',
    ['Inspector Yarrow Finch', 'Inspector Dunmore Kade', 'Inspector Tarn Osei'])],
  ['locations', 'logistics', 'assignments']),
 ('Batch Pinnacle', 'Batch Cobalt', 'batch_yield', 'planned batch yield', 'liters',
  ['340 liters', '365 liters', '390 liters', '415 liters', '445 liters', '470 liters', '505 liters', '530 liters'],
  ['610 liters', '640 liters', '675 liters'], ('batch_code', 'batch identifier', 'opaque code', ['BCH-P73']),
  [('vat_count', 'vat count', 'vats', ['4 vats', '6 vats', '9 vats']),
   ('fill_rate', 'fill rate', 'liters per minute',
    ['12 liters per minute', '18 liters per minute', '24 liters per minute']),
   ('shift_length', 'shift length', 'hours', ['6 hours', '8 hours', '10 hours']),
   ('sample_size', 'quality sample size', 'samples', ['5 samples', '7 samples', '11 samples'])],
  ['quantities', 'numeric_values', 'planning']),
]


def build_fixtures():
    fixtures = []
    for i, spec in enumerate(SPECS):
        primary, distractor, attr, meaning, units, target_values, hard_values, n2, others, coverage = spec
        identity = v.scenario_id(i)
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
        initial_order = dict(zip(gq.EVENTS[:7], v.initial_keys(i)))
        reference = {'domain': gq.DOMAINS[i], 'entities': entities, 'attributes': attributes, 'state_keys': keys,
                     'initial_order': initial_order,
                     'question_intent': {'entity_id': entities[0]['entity_id'], 'attribute_id': attr,
                                         'intent': f'Ask only for the current {meaning.removeprefix("current ")} of {primary}.'},
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
                        key = v.allocation(i)[variant][label]
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
    files = {f'fixtures/{slug}.json': pretty(fixture) for slug, fixture in zip(gq.SLUGS, fixtures)}
    files['reference-schema.json'] = pretty(v.reference_schema())
    manifest = {'schema_version': v.MANIFEST_SCHEMA, 'status': 'FROZEN', 'total_scenarios': 12,
                'purpose': v.PURPOSE, 'versions': gq.VERSIONS, 'construction_source_commit': source_commit,
                'reference_schema_sha256': gq.sha(files['reference-schema.json']),
                'allocation_rule': v.ALLOCATION_RULE, 'same_set_for': ['G1', 'G2'],
                'prohibited_uses': v.PROHIBITED_USES, 'not_final_crst_data': True,
                'not_generator_qualification_data': True, 'origin': v.ORIGIN,
                'reserved_exclusions': v.reserved_exclusions(fixtures),
                'coverage_summary': sorted({c for f in fixtures for c in f['reference']['coverage']}),
                'scenarios': [v.manifest_entry(f, files[f'fixtures/{slug}.json'])
                              for slug, f in zip(gq.SLUGS, fixtures)]}
    files['manifest.json'] = pretty(manifest)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Reproduce in memory using the recorded construction commit; never overwrite')
    args = parser.parse_args()
    if args.check:
        manifest, _ = v.validate_directory()
        for path, data in artifacts(manifest['construction_source_commit']).items():
            gq.require((v.DIRECTORY / path).read_bytes() == data, f'Reproduction mismatch: {path}')
        print('Byte-identical reproduction: 12 calibration-only scenarios, schema and manifest.')
    else:
        source = subprocess.check_output(['git', '-C', str(v.ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        # Created once; any later correction must be an explicit, reviewed change.
        v.DIRECTORY.mkdir(exist_ok=False)
        (v.DIRECTORY / 'fixtures').mkdir()
        for path, data in artifacts(source).items():
            with (v.DIRECTORY / path).open('xb') as stream:
                stream.write(data)
        v.validate_directory()
        print('Constructed 12 calibration-only B0 scenarios.')
    print('Manifest SHA-256:', gq.sha((v.DIRECTORY / 'manifest.json').read_bytes()))


if __name__ == '__main__':
    main()
