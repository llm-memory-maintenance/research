"""All checks are local; no generated model responses or external evidence."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import shutil
import socket
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
import build_generator_qualification_fixtures as b
import validate_generator_qualification_fixtures as v


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Network forbidden in fixture construction/validation')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


@pytest.fixture
def fixtures():
    return b.build_fixtures()


@pytest.fixture
def fixture(fixtures):
    return fixtures[0]


def test_official_manifest_schema_and_reproduction():
    manifest, fixtures = v.validate_directory()
    assert len(fixtures) == 12 and manifest['status'] == 'FROZEN'
    assert manifest['same_set_for'] == ['G1', 'G2'] and manifest['not_final_crst_data'] is True
    assert v.read(v.DIRECTORY / 'reference-schema.json') == v.reference_schema()
    first = b.artifacts(manifest['construction_source_commit'])
    assert first == b.artifacts(manifest['construction_source_commit'])
    for path, expected in first.items():
        assert (v.DIRECTORY / path).read_bytes() == expected


def test_all_structure_roles_schedules_and_state_traces(fixtures):
    assert Counter(f['reference']['domain'] for f in fixtures) == Counter(v.DOMAINS)
    assert len({f['fixture_id'] for f in fixtures}) == 12
    assert len(v.validate_set(fixtures)) == 12
    for f in fixtures:
        r = f['reference']
        assert len(r['state_keys']) == 7
        assert Counter(k['role'] for k in r['state_keys']) == Counter(target=1, hard_distractor=1,
                    dedicated_n2_secondary=1, updateable_secondary=4)
        target = next(k for k in r['state_keys'] if k['role'] == 'target')
        assert len(set(target['value_inventory'])) == 8
        assert set(r['initial_order'].values()) == set(v.KEYS)
        for variant in v.VARIANTS:
            events = r['variants'][variant]['events']
            assert [e['event'] for e in events] == list(v.EVENTS)
            updates = [e for e in events if e['event'].startswith('U')]
            assert len(updates) == 7 and all(e['semantics'] == 'changed_state' for e in updates)
            assert [e['event'] for e in updates if e['state_key'] == 'k_target'] == v.SCHEDULES[variant]
            assert all(e['current_value'] != e['previous_value'] for e in updates)
            assert all(e['state_key'] != 'k_n2' for e in updates)
            if variant != 'high':
                assert any(e['state_key'] == 'k_hard' for e in updates)
            for e in (events[-3], events[-1]):
                assert e['semantics'] == 'same_state' and e['current_value'] == e['previous_value']
            assert events[-3]['state_key'] == 'k_target' and events[-1]['state_key'] == 'k_n2'
            assert events[-2]['state_key'] == 'k_target' and events[-2]['current_value'] == r['gold_current_value']
            assert r['variants'][variant]['final_state']['k_target'] == r['gold_current_value']
            for key in v.KEYS:
                initial = next(e for e in events[:7] if e['state_key'] == key)
                assert initial['previous_value'] is None and initial['superseded_values'] == []


def test_allocation_diversity_and_coverage(fixtures):
    assert len({v.canonical(v.allocation(i)) for i in range(12)}) > 1
    for i, f in enumerate(fixtures):
        allocation = v.allocation(i)
        assert len(allocation['low']) == 6 and len(allocation['medium']) == 3 and allocation['high'] == {}
        assert set(allocation['low'].values()) == {'k_hard', *v.KEYS[3:]}
        assert len(set(allocation['medium'].values())) == 3 and 'k_hard' in allocation['medium'].values()
    coverage = {c for f in fixtures for c in f['reference']['coverage']}
    assert {'numeric_values', 'categorical_values', 'times', 'synthetic_calendar_labels', 'locations',
            'configuration_values', 'preferences', 'assignments', 'quantities', 'subscription_state',
            'communication_settings', 'ordering', 'planning'} <= coverage


def test_projection_exact_fields_determinism_and_independence(fixtures):
    probe = v.read(v.ROOT / 'data/generator-capability-probe/probe-input.json')
    forbidden = {'previous_value', 'superseded_values', 'gold_current_value', 'gold_answer', 'state_after',
                 'final_state', 'reference', 'purpose', 'fixture_id', 'memory_id', 'semantic_timestamp',
                 'reference_operation', 'policy_action', 'expected_outcome', 'value_inventory'}
    def walk(value):
        if isinstance(value, dict):
            assert not forbidden & value.keys()
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for f in fixtures:
        payload = v.project(f)
        v.validate_input(payload)
        assert set(payload) == set(probe)
        assert payload != probe
        assert v.sha(v.canonical(payload)) == v.sha(v.canonical(v.project(f)))
        assert v.canonical(payload) == v.canonical(dict(reversed(list(payload.items()))))
        walk(payload)
        payload['entities'][0]['name'] = 'mutated'
        assert f['reference']['entities'][0]['name'] != 'mutated'


@pytest.mark.parametrize('mutation', ['target_schedule', 'n1', 'n2', 'convergence', 'reversion', 'dedicated',
    'hard_coverage', 'role_count', 'role_identity', 'initial_coverage', 'initial_value', 'event_order',
    'missing_event', 'extra_event', 'unchanged_update', 'update_semantics', 'q_target', 'q_identity',
    'previous', 'superseded', 'state_after', 'final_state', 'gold', 'inventory', 'duplicate_key',
    'duplicate_entity', 'duplicate_attribute', 'semantic_key', 'unresolved_identity', 'extra_reference',
    'fixture_id', 'purpose', 'coverage'])
def test_reference_mutations_rejected(fixture, mutation):
    r = fixture['reference']
    low = r['variants']['low']['events']
    high = r['variants']['high']['events']
    if mutation == 'target_schedule':
        low[7]['state_key'] = 'k_target'
    elif mutation == 'n1':
        low[-3]['current_value'] = '15:15'
    elif mutation == 'n2':
        low[-1]['state_key'] = 'k_hard'
    elif mutation == 'convergence':
        low[-2]['current_value'] = '15:45'
    elif mutation == 'reversion':
        high[-2]['current_value'] = high[7]['current_value']
    elif mutation == 'dedicated':
        low[7]['state_key'] = 'k_n2'
    elif mutation == 'hard_coverage':
        low[7]['state_key'] = 'k_a'
    elif mutation == 'role_count':
        r['state_keys'][1]['role'] = 'target'
    elif mutation == 'role_identity':
        r['hard_distractor_key'] = 'k_n2'
    elif mutation == 'initial_coverage':
        r['initial_order']['I2'] = r['initial_order']['I1']
    elif mutation == 'initial_value':
        low[0]['current_value'] = '99:99'
    elif mutation == 'event_order':
        low[-3], low[-2] = low[-2], low[-3]
    elif mutation == 'missing_event':
        low.pop()
    elif mutation == 'extra_event':
        low.append(deepcopy(low[-1]))
    elif mutation == 'unchanged_update':
        low[7]['current_value'] = low[7]['previous_value']
    elif mutation == 'update_semantics':
        low[7]['semantics'] = 'same_state'
    elif mutation == 'q_target':
        r['q_target'] = 'k_hard'
    elif mutation == 'q_identity':
        r['question_intent']['entity_id'] = r['entities'][1]['entity_id']
    elif mutation == 'previous':
        low[7]['previous_value'] = 'wrong'
    elif mutation == 'superseded':
        low[7]['superseded_values'] = []
    elif mutation == 'state_after':
        low[7]['state_after']['k_target'] = 'wrong'
    elif mutation == 'final_state':
        r['variants']['low']['final_state']['k_target'] = 'wrong'
    elif mutation == 'gold':
        r['gold_current_value'] = 'wrong'
    elif mutation == 'inventory':
        r['state_keys'][0]['value_inventory'][1] = r['state_keys'][0]['initial_value']
    elif mutation == 'duplicate_key':
        r['state_keys'][1]['state_key'] = 'k_target'
    elif mutation == 'duplicate_entity':
        r['entities'].append(deepcopy(r['entities'][0]))
    elif mutation == 'duplicate_attribute':
        r['attributes'].append(deepcopy(r['attributes'][0]))
    elif mutation == 'semantic_key':
        r['state_keys'][1]['entity_id'] = r['state_keys'][0]['entity_id']
    elif mutation == 'unresolved_identity':
        r['state_keys'][0]['entity_id'] = 'unknown'
    elif mutation == 'extra_reference':
        r['extra'] = 'unrecognized'
    elif mutation == 'fixture_id':
        fixture['fixture_id'] = 'generator-capability-probe-only-v1'
    elif mutation == 'purpose':
        fixture['purpose'] = 'FINAL-CRST'
    elif mutation == 'coverage':
        r['coverage'] = []
    with pytest.raises(ValueError):
        v.validate_fixture(fixture)


@pytest.mark.parametrize('field', ['previous_value', 'superseded_values', 'gold_answer', 'evaluator_label',
                                  'memory_id', 'semantic_timestamp', 'policy_action', 'expected_outcome'])
@pytest.mark.parametrize('where', ['root', 'event'])
def test_projection_rejects_reference_leakage(fixture, field, where):
    payload = v.project(fixture)
    target = payload if where == 'root' else payload['variants']['low'][7]
    target[field] = 'forbidden'
    with pytest.raises(ValidationError):
        v.validate_input(payload)


@pytest.mark.parametrize('change', ['duplicate_domain', 'duplicate_id', 'missing', 'extra'])
def test_set_mutations(fixtures, change):
    if change == 'duplicate_domain':
        fixtures[1]['reference']['domain'] = fixtures[0]['reference']['domain']
    elif change == 'duplicate_id':
        fixtures[1]['fixture_id'] = fixtures[0]['fixture_id']
    elif change == 'missing':
        fixtures.pop()
    else:
        fixtures.append(deepcopy(fixtures[0]))
    with pytest.raises(ValueError):
        v.validate_set(fixtures)


@pytest.mark.parametrize('change', ['file_bytes', 'file_hash', 'projection_hash', 'allocation', 'coverage',
                                  'schema', 'path', 'extra_file', 'purpose', 'versions'])
def test_manifest_integrity(tmp_path, change):
    directory = tmp_path / 'fixtures'
    shutil.copytree(v.DIRECTORY, directory)
    path = directory / 'manifest.json'
    m = v.read(path)
    if change == 'file_bytes':
        f = directory / m['fixtures'][0]['fixture_path']
        f.write_bytes(f.read_bytes() + b' ')
    elif change == 'file_hash':
        m['fixtures'][0]['sha256'] = '0' * 64
    elif change == 'projection_hash':
        m['fixtures'][0]['projection_sha256'] = '0' * 64
    elif change == 'allocation':
        m['fixtures'][0]['secondary_allocation']['low']['U1'] = 'k_n2'
    elif change == 'coverage':
        m['coverage_summary'] = []
    elif change == 'schema':
        (directory / 'reference-schema.json').write_text('{}')
    elif change == 'path':
        m['fixtures'][0]['fixture_path'] = '../escape.json'
    elif change == 'extra_file':
        (directory / 'fixtures/unexpected.json').write_text('{}')
    elif change == 'purpose':
        m['purpose'] = 'final data'
    elif change == 'versions':
        m['versions']['input_contract_version'] = 'other'
    path.write_bytes(b.pretty(m))
    with pytest.raises(ValueError):
        v.validate_directory(directory)


def test_probe_entity_reuse_rejected_even_with_rehashed_manifest(tmp_path):
    directory = tmp_path / 'fixtures'
    shutil.copytree(v.DIRECTORY, directory)
    m = v.read(directory / 'manifest.json')
    fpath = directory / m['fixtures'][4]['fixture_path']
    f = v.read(fpath)
    probe = v.read(v.ROOT / 'data/generator-capability-probe/probe-input.json')
    old_name = f['reference']['entities'][0]['name']
    f['reference']['entities'][0]['name'] = probe['entities'][0]['name']
    f['reference']['question_intent']['intent'] = f['reference']['question_intent']['intent'].replace(
        old_name, probe['entities'][0]['name'])
    fpath.write_bytes(b.pretty(f))
    m['fixtures'][4] = v.manifest_entry(f, fpath.read_bytes())
    (directory / 'manifest.json').write_bytes(b.pretty(m))
    with pytest.raises(ValueError, match='Capability Probe content reused'):
        v.validate_directory(directory)


def test_reference_schema_strict_objects():
    schema = v.reference_schema()
    assert schema['additionalProperties'] is False
    for definition in schema['$defs'].values():
        if definition.get('type') == 'object':
            assert definition['additionalProperties'] is False
    assert schema['$defs']['Reference']['properties']['state_keys']['minItems'] == 7
    assert schema['$defs']['ReferenceVariant']['properties']['events']['maxItems'] == 16


@pytest.mark.parametrize('mutation,reason', [
    ('schedule', 'Target schedule'),
    ('low_missing_ordinary', 'Low secondary coverage'),
    ('medium_repeated_ordinary', 'Medium secondary coverage'),
    ('hard_absent', 'Low secondary coverage'),
    ('hard_repeated', 'Low secondary coverage'),
    ('n2_updated', 'Dedicated secondary updated'),
    ('shared_value', 'Shared target U value mismatch'),
    ('duplicate_name', 'normalized entity display name'),
    ('empty_name', 'normalized entity display name'),
    ('repeated_word', 'Q intent repeated word'),
    ('missing_name', 'Q intent missing primary entity name'),
])
def test_independent_semantic_mutations(fixture, monkeypatch, mutation, reason):
    payload = v.project(fixture)
    def no_allocation(*args):
        pytest.fail('Semantic validation must not consult construction allocation')
    monkeypatch.setattr(v, 'allocation', no_allocation)
    low = {e['event']: e for e in payload['variants']['low']}
    medium = {e['event']: e for e in payload['variants']['medium']}
    if mutation == 'schedule':
        # Both events remain actual changes; N1 still reaffirms the target.
        low['U1'].update(state_key='k_target', current_value='08:35')
        low['N1']['current_value'] = '08:35'
    elif mutation == 'low_missing_ordinary':
        low['U5'].update(state_key='k_b', current_value='55 minutes')
    elif mutation == 'medium_repeated_ordinary':
        medium['U6'].update(state_key='k_b', current_value='55 minutes')
    elif mutation == 'hard_absent':
        low['U1'].update(state_key='k_b', current_value='55 minutes')
    elif mutation == 'hard_repeated':
        low['U6'].update(state_key='k_hard', current_value='14:30')
    elif mutation == 'n2_updated':
        low['U1'].update(state_key='k_n2', current_value='TRN-X5')
    elif mutation == 'shared_value':
        medium['U1']['current_value'] = '09:05'
    elif mutation == 'duplicate_name':
        payload['entities'][1]['name'] = '  ＴＥＲＮ   rehearsal  '
    elif mutation == 'empty_name':
        payload['entities'][1]['name'] = '---'
    elif mutation == 'repeated_word':
        payload['question_intent']['intent'] = 'Ask for the CURRENT, current start time of Tern rehearsal.'
    elif mutation == 'missing_name':
        payload['question_intent']['intent'] = 'Ask only for the current rehearsal start time.'
    with pytest.raises(ValueError, match=reason):
        v.validate_input(payload)


def test_valid_alternative_construction_conventions(fixture, monkeypatch):
    payload = v.project(fixture)
    monkeypatch.setattr(v, 'allocation', lambda *args: pytest.fail('Allocation helper called'))
    for variant, events in payload['variants'].items():
        by_label = {e['event']: e for e in events}
        # Different initial placement, preserving complete initial truth.
        for field in ('state_key', 'current_value'):
            by_label['I1'][field], by_label['I2'][field] = by_label['I2'][field], by_label['I1'][field]
        if variant == 'low':
            by_label['U1'].update(state_key='k_a', current_value='Room Lyra')
            by_label['U2'].update(state_key='k_hard', current_value='13:55')
        if variant in ('medium', 'high'):
            by_label['U1']['current_value'] = '09:05'
        if variant == 'high':
            by_label['U2']['current_value'] = '08:35'
    payload['initial_order']['I1'], payload['initial_order']['I2'] = 'k_hard', 'k_target'
    # Shared positions agree, but U1/U2 need not follow inventory indices.
    v.validate_input(payload)


def test_adjudicated_values(fixtures):
    study, communication, quantitative = fixtures[7], fixtures[8], fixtures[11]
    assert study['reference']['question_intent']['intent'] == 'Ask only for the current study topic of Study plan Wren.'
    keys = {k['state_key']: k for k in communication['reference']['state_keys']}
    assert keys['k_target']['value_inventory'] == [f'daily at {hour:02}:00' for hour in range(8, 16)]
    assert keys['k_hard']['value_inventory'] == [f'daily at {hour:02}:00' for hour in range(16, 19)]
    for variant in quantitative['reference']['variants'].values():
        for event in variant['events']:
            state = event['state_after']
            if 'k_a' in state:
                bundle = int(state['k_a'].split()[0])
                for key in ('k_target', 'k_hard'):
                    if key in state:
                        assert int(state[key].split()[0]) % bundle == 0
