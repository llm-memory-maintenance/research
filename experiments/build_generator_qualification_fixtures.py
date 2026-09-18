"""Reproduce structured qualification-only fixtures offline; never naturalize text."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import validate_generator_qualification_fixtures as v

# Per domain: primary entity, same-property distractor entity, target attribute,
# meaning, units, eight target values, three distinct distractor values,
# dedicated N2 (attribute, meaning, units, one value), four secondary inventories,
# descriptive coverage. Names/values are independently authored and self-contained.
SPECS = [
 ('Tern rehearsal', 'Gull rehearsal', 'start_time', 'scheduled rehearsal start time', '24-hour local clock; one synthetic day',
  ['08:10','08:35','09:05','09:40','10:15','10:50','11:25','12:05'], ['13:20','13:55','14:30'],
  ('session_code','rehearsal identification code','opaque code',['TRN-X4']),
  [('room','rehearsal room','room label',['Room Vela','Room Lyra','Room Ara']),
   ('duration','rehearsal duration','minutes',['35 minutes','45 minutes','55 minutes']),
   ('facilitator','rehearsal facilitator','synthetic person',['Person Zerin','Person Odel','Person Fira']),
   ('agenda','rehearsal agenda','agenda label',['opening practice','ensemble practice','closing practice'])], ['times','scheduling','locations']),
 ('Voyage Pavo', 'Voyage Grus', 'destination', 'designated voyage destination', 'fictional location name',
  ['Islet Azuri','Islet Belori','Islet Cedari','Islet Doruni','Islet Esari','Islet Feluni','Islet Garuni','Islet Hesari'],
  ['Islet Irovi','Islet Jeruni','Islet Kelari'], ('booking_code','voyage booking identifier','opaque code',['VYG-P4']),
  [('departure','departure calendar label','synthetic calendar label',['Cycle Tavi','Cycle Ulen','Cycle Vori']),
   ('cabin','assigned cabin','cabin label',['Cabin E1','Cabin E2','Cabin E3']),
   ('bag_count','reserved baggage count','bags',['2 bags','3 bags','4 bags']),
   ('boarding_gate','boarding gate','gate label',['Gate J1','Gate J2','Gate J3'])], ['locations','synthetic_calendar_labels','travel','quantities']),
 ('Project Halcyon', 'Project Petrel', 'milestone', 'next planned milestone', 'milestone label',
  ['outline review','sketch review','component review','layout review','integration review','rehearsal review','delivery review','archive review'],
  ['inventory review','license review','handover review'], ('project_code','project identifier','opaque code',['PRJ-H7']),
  [('owner','project owner','synthetic team',['Team Eru','Team Nalo','Team Suri']),
   ('delivery_cycle','delivery cycle','synthetic calendar label',['Cycle Leris','Cycle Meris','Cycle Neris']),
   ('workstream','active workstream','workstream label',['layout drafting','asset assembly','package preparation']),
   ('priority','priority tier','ordered tier label',['Tier P1','Tier P2','Tier P3'])], ['planning','categorical_values','assignments','synthetic_calendar_labels']),
 ('Task Vireo', 'Task Siskin', 'assignee', 'person assigned to the task', 'synthetic person name',
  ['Person Aven','Person Belu','Person Ceri','Person Dovan','Person Etri','Person Falun','Person Gemi','Person Haru'],
  ['Person Iven','Person Jora','Person Kemi'], ('task_code','task identifier','opaque code',['TSK-V6']),
  [('priority','task priority','tier label',['Tier R1','Tier R2','Tier R3']),
   ('due_cycle','task due cycle','synthetic calendar label',['Cycle Avo','Cycle Bori','Cycle Celu']),
   ('output','required task deliverable','deliverable label',['diagram package','table package','index package']),
   ('reviewer','task reviewer','synthetic person',['Person Loru','Person Mavi','Person Nelu'])], ['assignments','categorical_values','planning']),
 ('Render profile Ibis', 'Render profile Egret', 'export_format', 'selected export file format', 'format label',
  ['FMT-QA','FMT-QB','FMT-QC','FMT-QD','FMT-QE','FMT-QF','FMT-QG','FMT-QH'],
  ['FMT-QJ','FMT-QK','FMT-QL'], ('profile_code','render profile identifier','opaque code',['RND-I9']),
  [('tile_size','output tile size','pixels per side',['240 pixels','320 pixels','400 pixels']),
   ('compression','compression preset','preset label',['CMP-R1','CMP-R2','CMP-R3']),
   ('output_folder','export folder','synthetic folder label',['Folder Nacre','Folder Opal','Folder Quartz']),
   ('render_scale','render scale','percent',['60 percent','80 percent','100 percent'])], ['configuration_values','numeric_values','categorical_values']),
 ('Person Fenli', 'Person Gavri', 'notebook_style', 'preferred notebook cover style', 'style label',
  ['woven cover','dotted cover','striped cover','grid cover','leaf cover','wave cover','spiral cover','plain cover'],
  ['star cover','ring cover','cloud cover'], ('member_code','preference record identifier','opaque code',['PREF-F3']),
  [('binding','preferred notebook binding','binding label',['sewn binding','glued binding','ring binding']),
   ('page_size','preferred page size','synthetic size label',['Size N1','Size N2','Size N3']),
   ('paper_finish','preferred paper finish','finish label',['smooth finish','rough finish','ribbed finish']),
   ('ruling','preferred page ruling','ruling label',['wide lines','narrow lines','blank pages'])], ['preferences','categorical_values']),
 ('Order Kittiwake', 'Order Sandpiper', 'item_count', 'ordered number of empty storage sleeves', 'sleeves',
  [f'{n} sleeves' for n in (120,145,170,195,220,245,270,295)], ['330 sleeves','355 sleeves','380 sleeves'],
  ('order_code','order identifier','opaque code',['ORD-K8']),
  [('packaging','packaging style','style label',['flat packs','rolled packs','boxed packs']),
   ('delivery_point','delivery point','synthetic location',['Dock Ranu','Dock Selu','Dock Tavi']),
   ('label_format','package label format','format label',['Label Aster','Label Briar','Label Clover']),
   ('dispatch_cycle','dispatch cycle','synthetic calendar label',['Cycle Dori','Cycle Evi','Cycle Falu'])], ['ordering','quantities','numeric_values','locations']),
 ('Study plan Wren', 'Study plan Lark', 'topic', 'current study topic', 'self-contained fictional course label',
  ['Course Ena','Course Felo','Course Gira','Course Hanu','Course Iro','Course Jelu','Course Kora','Course Lavi'],
  ['Course Mero','Course Nori','Course Ovu'], ('plan_code','study plan identifier','opaque code',['STU-W2']),
  [('session_length','study session length','minutes',['25 minutes','40 minutes','65 minutes']),
   ('exercise_pack','assigned exercise pack','pack label',['Pack Uva','Pack Veli','Pack Wora']),
   ('desk','designated study desk','desk label',['Desk Oris','Desk Peri','Desk Qeli']),
   ('review_cycle','review cycle','synthetic calendar label',['Cycle Garo','Cycle Heli','Cycle Iru'])], ['study_planning','categorical_values','numeric_values']),
 ('Channel Skylark', 'Channel Starling', 'digest_schedule', 'digest delivery schedule', 'named schedule',
  ['daily at 08:00','daily at 09:00','daily at 10:00','daily at 11:00',
   'daily at 12:00','daily at 13:00','daily at 14:00','daily at 15:00'],
  ['daily at 16:00','daily at 17:00','daily at 18:00'], ('channel_code','channel identifier','opaque code',['COM-S5']),
  [('delivery_mode','digest delivery mode','mode label',['inbox delivery','panel delivery','archive delivery']),
   ('subject_prefix','digest subject prefix','literal prefix',['DG-RU','DG-SE','DG-TO']),
   ('layout','digest layout','layout label',['compact cards','expanded cards','summary rows']),
   ('recipient_group','digest recipient group','synthetic group',['Group Daru','Group Efi','Group Feno'])], ['communication_settings','categorical_values','assignments','times']),
 ('Service account Curlew', 'Service account Avocet', 'plan', 'selected fictional service plan', 'plan label',
  ['Plan Navo','Plan Orel','Plan Peli','Plan Qari','Plan Renu','Plan Savi','Plan Tero','Plan Ulin'],
  ['Plan Vena','Plan Weri','Plan Xalo'], ('account_code','service account identifier','opaque code',['SVC-C6']),
  [('renewal_cycle','renewal cycle','synthetic calendar label',['Cycle Javi','Cycle Kelo','Cycle Luri']),
   ('report_mode','usage report mode','mode label',['brief report','detailed report','tabular report']),
   ('seat_count','account seat count','seats',['6 seats','8 seats','12 seats']),
   ('support_channel','support contact channel','channel label',['Channel Ash','Channel Beech','Channel Cedar'])], ['subscription_state','categorical_values','quantities']),
 ('Parcel route Plover', 'Parcel route Dunlin', 'destination_bay', 'assigned destination bay', 'fictional bay label',
  ['Bay Alden','Bay Bexel','Bay Cavor','Bay Deren','Bay Evor','Bay Falin','Bay Goran','Bay Halen'],
  ['Bay Irel','Bay Javin','Bay Koren'], ('route_code','parcel route identifier','opaque code',['LOG-P9']),
  [('vehicle','assigned vehicle','vehicle label',['Cart D1','Cart D2','Cart D3']),
   ('loading_slot','loading slot','slot label',['Slot V1','Slot V2','Slot V3']),
   ('container','assigned container','container label',['Crate M1','Crate M2','Crate M3']),
   ('handling_team','handling team','synthetic team',['Team Galu','Team Heri','Team Ivo'])], ['locations','logistics','assignments']),
 ('Plan Osprey', 'Plan Kestrel', 'sheet_count', 'planned number of blank craft sheets', 'sheets',
  [f'{n} sheets' for n in (420,450,480,510,540,570,600,630)], ['720 sheets','750 sheets','780 sheets'],
  ('plan_code','quantity plan identifier','opaque code',['QNT-O7']),
  [('bundle_size','sheets per bundle','sheets per bundle',['10 sheets per bundle','15 sheets per bundle','20 sheets per bundle']),
   ('storage_zone','storage zone','zone label',['Zone P1','Zone P2','Zone P3']),
   ('sheet_shape','sheet shape','shape label',['square sheets','round sheets','oval sheets']),
   ('dispatch_order','dispatch priority','priority label',['Priority D1','Priority D2','Priority D3'])], ['quantities','numeric_values','planning'])
]


def build_fixtures():
    fixtures = []
    for i, spec in enumerate(SPECS):
        primary, distractor, attr, meaning, units, target_values, hard_values, n2, others, coverage = spec
        identity = 'gq-' + v.SLUGS[i] + '-01'
        entities = [{'entity_id': identity + '-primary', 'name': primary},
                    {'entity_id': identity + '-distractor', 'name': distractor}]
        definitions = [(attr, meaning, units, target_values), n2, *others]
        attributes = [{'attribute_id': a, 'meaning': m, 'units_or_interpretation': u} for a, m, u, _ in definitions]
        keys = []
        for key, entity, definition, role in [
            ('k_target', entities[0]['entity_id'], definitions[0], 'target'),
            ('k_hard', entities[1]['entity_id'], (attr, meaning, units, hard_values), 'hard_distractor'),
            ('k_n2', entities[0]['entity_id'], n2, 'dedicated_n2_secondary'),
            *[(k, entities[0]['entity_id'], d, 'updateable_secondary') for k, d in zip(v.KEYS[3:], others)]]:
            keys.append({'state_key': key, 'entity_id': entity, 'attribute_id': definition[0],
                         'initial_value': definition[3][0], 'role': role, 'value_inventory': definition[3]})
        keymap = {k['state_key']: k for k in keys}
        initial_keys = list(v.KEYS[i % 7:] + v.KEYS[:i % 7])
        initial_order = dict(zip(v.EVENTS[:7], initial_keys))
        reference = {'domain': v.DOMAINS[i], 'entities': entities, 'attributes': attributes, 'state_keys': keys,
                     'initial_order': initial_order,
                     'question_intent': {'entity_id': entities[0]['entity_id'], 'attribute_id': attr,
                                         'intent': f'Ask only for the current {meaning.removeprefix("current ")} of {primary}.'},
                     'target_state_key': 'k_target', 'hard_distractor_key': 'k_hard',
                     'dedicated_n2_secondary_key': 'k_n2', 'q_target': 'k_target',
                     'gold_current_value': target_values[-1], 'coverage': coverage, 'variants': {}}
        for variant in v.VARIANTS:
            state, counts, history, events = {}, {k: 0 for k in v.KEYS}, {k: [] for k in v.KEYS}, []
            for label in v.EVENTS:
                if label.startswith('I'):
                    key, semantics = initial_order[label], 'initial'
                    value = keymap[key]['initial_value']
                elif label.startswith('U'):
                    semantics = 'changed_state'
                    if label in v.SCHEDULES[variant]:
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
                               'previous_value': previous, 'superseded_values': list(history[key]), 'state_after': dict(state)})
            reference['variants'][variant] = {'events': events, 'final_state': dict(state)}
        fixtures.append({'schema_version': 'generator-qualification-reference/1.0.0', 'fixture_id': identity,
                         'purpose': v.PURPOSE, 'reference': reference})
    v.validate_set(fixtures)
    return deepcopy(fixtures)


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def artifacts(source_commit):
    fixtures = build_fixtures()
    files = {f'fixtures/{slug}.json': pretty(fixture) for slug, fixture in zip(v.SLUGS, fixtures)}
    files['reference-schema.json'] = pretty(v.reference_schema())
    manifest = {'schema_version': 'generator-qualification-manifest/1.0.0', 'status': 'FROZEN',
                'total_fixtures': 12, 'purpose': v.PURPOSE, 'versions': v.VERSIONS,
                'construction_source_commit': source_commit,
                'execution_package_reference': {'config_path': 'configs/generator-capability-probe.yaml',
                    'capability_evidence_path': 'results/generator-capability-probe/attempt-02/probe.json',
                    'capability_evidence_sha256': 'b8982ac18e74fded527c3680e26082cf505fadbe33edf53ea103494b7ad57c8f',
                    'status': 'FROZEN'},
                'reference_schema_sha256': v.sha(files['reference-schema.json']),
                'allocation_rule': v.ALLOCATION_RULE, 'same_set_for': ['G1', 'G2'], 'not_final_crst_data': True,
                'origin': 'Independently authored synthetic structured truth; no external corpus content or model naturalization.',
                'coverage_summary': sorted({c for f in fixtures for c in f['reference']['coverage']}),
                'fixtures': [v.manifest_entry(f, files[f'fixtures/{slug}.json']) for slug, f in zip(v.SLUGS, fixtures)]}
    files['manifest.json'] = pretty(manifest)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Reproduce in memory using recorded construction HEAD; never overwrite')
    parser.add_argument('--refresh', action='store_true', help='Refresh existing generated artifacts from the authoritative builder')
    args = parser.parse_args()
    if args.check and args.refresh:
        parser.error('--check and --refresh are mutually exclusive')
    if args.check:
        manifest, _ = v.validate_directory()
        expected = artifacts(manifest['construction_source_commit'])
        for path, data in expected.items():
            v.require((v.DIRECTORY / path).read_bytes() == data, f'Reproduction mismatch: {path}')
        print('Byte-identical reproduction: 12 fixtures, schema and manifest.')
    else:
        source = subprocess.check_output(['git', '-C', str(v.ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        if args.refresh:
            manifest = v.read(v.DIRECTORY / 'manifest.json')
            v.require(type(manifest.get('construction_source_commit')) is str, 'Missing construction source commit')
            source = manifest['construction_source_commit']
        expected = artifacts(source)
        if args.refresh:
            expected_paths = set(expected)
            actual_paths = {str(p.relative_to(v.DIRECTORY)) for p in v.DIRECTORY.rglob('*') if p.is_file()}
            v.require(actual_paths == expected_paths, 'Unexpected/missing generated artifact path')
        else:
            # This constructor creates once; review corrections must be explicit.
            v.DIRECTORY.mkdir(exist_ok=False)
            (v.DIRECTORY / 'fixtures').mkdir()
        for path, data in expected.items():
            target = v.DIRECTORY / path
            if args.refresh:
                if target.read_bytes() != data:
                    target.write_bytes(data)
            else:
                with target.open('xb') as stream:
                    stream.write(data)
        v.validate_directory()
        print(('Refreshed' if args.refresh else 'Constructed') + ' 12 frozen qualification-only fixtures.')
    print('Manifest SHA-256:', v.sha((v.DIRECTORY / 'manifest.json').read_bytes()))


if __name__ == '__main__':
    main()
