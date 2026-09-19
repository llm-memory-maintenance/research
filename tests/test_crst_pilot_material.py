"""Offline tests for the pilot-only CRST structured material; no naturalization or model call."""
from copy import deepcopy
import json

import pytest

from crst_common import ROOT, builder, material, pol, references, built, no_network, v  # noqa: F401
import crst_scoring as scoring
import validate_generator_qualification_fixtures as gq


def test_directory_validates_and_reproduces_byte_identically(material):
    manifest, _ = material
    for path, data in builder.artifacts(manifest['construction_source_commit']).items():
        assert (v.DIRECTORY / path).read_bytes() == data


def test_two_pilot_scenarios_with_preassigned_generators(material):
    manifest, fixtures = material
    assert [f['fixture_id'] for f in fixtures] == ['pilot-scheduling-01', 'pilot-travel-01']
    assert manifest['generator_assignment'] == {'pilot-scheduling-01': 'G1', 'pilot-travel-01': 'G2'}
    assert [(s['scenario_id'], s['model']) for s in v.SCENARIOS] == [
        ('pilot-scheduling-01', 'openai/gpt-5.6-sol'), ('pilot-travel-01', 'anthropic/claude-fable-5.1')]
    assert manifest['purpose'] == 'CRST-SMALL-PILOT-ONLY' and manifest['not_final_crst_data'] is True
    assert manifest['candidate_template'] == 'For {entity_name}, the {attribute_meaning} is {current_value}.'
    assert 'effect-size estimation, policy ranking or power analysis' in manifest['prohibited_uses']


def test_every_variant_has_the_sixteen_events_in_frozen_order(references):
    for reference in references:
        assert set(reference['variants']) == {'low', 'medium', 'high'}
        for variant in reference['variants'].values():
            assert [e['event'] for e in variant['events']] == list(pol.EVENT_ORDER)


def test_target_schedules_have_no_return(references):
    expected = {'low': ['U7'], 'medium': ['U1', 'U3', 'U5', 'U7'], 'high': [f'U{i}' for i in range(1, 8)]}
    for reference in references:
        for name, variant in reference['variants'].items():
            events = variant['events']
            assert [e['event'] for e in events if e['state_key'] == 'k_target'
                    and e['semantics'] == 'changed_state'] == expected[name]
            path = [e['current_value'] for e in events if e['state_key'] == 'k_target']
            distinct = [x for i, x in enumerate(path) if i == 0 or x != path[i - 1]]
            assert len(distinct) == len(set(distinct))
            assert variant['final_state']['k_target'] == reference['gold_current_value']


def test_n1_u7_n2_semantics(references):
    for reference in references:
        for variant in reference['variants'].values():
            ev = {e['event']: e for e in variant['events']}
            assert (ev['N1']['state_key'], ev['N1']['semantics']) == ('k_target', 'same_state')
            assert ev['N1']['current_value'] == ev['U6']['state_after']['k_target']
            assert (ev['U7']['state_key'], ev['U7']['semantics']) == ('k_target', 'changed_state')
            assert (ev['N2']['state_key'], ev['N2']['semantics']) == ('k_n2', 'same_state')
            assert not any(e['state_key'] == 'k_n2' and e['semantics'] == 'changed_state'
                           for e in variant['events'])
            order = [e['event'] for e in variant['events']]
            assert order.index('N1') < order.index('U7') < order.index('N2')


def test_hard_distractor_dedicated_n2_and_shared_controls(references):
    for reference in references:
        keys = {k['state_key']: k for k in reference['state_keys']}
        assert keys['k_hard']['attribute_id'] == keys['k_target']['attribute_id']
        assert keys['k_hard']['entity_id'] != keys['k_target']['entity_id']
        assert keys['k_n2']['role'] == 'dedicated_n2_secondary' and len(keys['k_n2']['value_inventory']) == 1
        initial = [[(e['event'], e['state_key'], e['current_value']) for e in reference['variants'][n]['events'][:7]]
                   for n in reference['variants']]
        assert initial[0] == initial[1] == initial[2]
        shared = {}
        for variant in reference['variants'].values():
            for e in variant['events']:
                if e['state_key'] == 'k_target' and e['semantics'] == 'changed_state':
                    assert shared.setdefault(e['event'], e['current_value']) == e['current_value']


def test_candidates_render_with_the_frozen_template_and_round_trip(references):
    for reference in references:
        names = {e['entity_id']: e['name'] for e in reference['entities']}
        meanings = {a['attribute_id']: a['meaning'] for a in reference['attributes']}
        keys = {k['state_key']: k for k in reference['state_keys']}
        for name in reference['variants']:
            for event in pol.reference_events(reference, name, 'M3'):
                key = keys[event['state_key']]
                value = next(e['current_value'] for e in reference['variants'][name]['events']
                             if e['event'] == event['event'])
                assert event['candidate'] == (f'For {names[key["entity_id"]]}, the '
                                              f'{meanings[key["attribute_id"]]} is {value}.')
                assert pol.parse_candidate(event['candidate']) == (names[key['entity_id']],
                                                                    meanings[key['attribute_id']], value)


def test_candidates_expose_only_the_three_permitted_fields(references):
    """Same-state events render identically to their earlier text, and no label or annotation enters."""
    pattern = ('k_', 'state_key', 'role', 'changed_state', 'same_state', 'superseded', 'reference', 'Update',
               'Noop', 'intensity')
    for reference in references:
        for event in pol.reference_events(reference, 'high', 'M3'):
            assert not any(word in event['candidate'] for word in pattern)
    reference = references[0]
    events = pol.reference_events(reference, 'high', 'M3')
    by_label = {e['event']: e for e in events}
    last_target = [e for e in events if e['state_key'] == 'k_target' and e['event'] not in ('N1', 'U7', 'N2')][-1]
    assert by_label['N1']['candidate'] == last_target['candidate']
    assert by_label['N2']['candidate'] == next(e for e in events if e['state_key'] == 'k_n2')['candidate']


@pytest.mark.parametrize('bad', ['', ' x', 'x ', 'a\nb'])
def test_renderer_rejects_unrepresentable_fields(bad):
    with pytest.raises(ValueError):
        pol.render_candidate(bad, 'meaning', 'value')


def test_parser_rejects_noncanonical_text():
    for text in ('for A, the b is c.', 'For A, the b is c', 'For A the b is c.', 'For A, the b is c. '):
        with pytest.raises(ValueError):
            pol.parse_candidate(text)


def test_normalized_current_and_superseded_values_are_distinguishable(references):
    for reference in references:
        for name in reference['variants']:
            target = pol.target_answer(reference, name)
            scoring.assert_distinct(target['current'], target['superseded'])
            assert target['current'] == reference['gold_current_value']
            assert target['current'] not in target['superseded']


def test_time_neutral_wording_is_enforced(built):
    for mutate in (lambda f: f['reference']['state_keys'][3]['value_inventory'].__setitem__(1, 'latest handout'),
                   lambda f: f['reference']['attributes'][0].__setitem__('meaning', 'now opening time'),
                   lambda f: f['reference']['entities'][0].__setitem__('name', 'New Seminar Brindle')):
        broken = deepcopy(built)
        mutate(broken[0])
        with pytest.raises(Exception):
            v.validate_set(broken)


def test_rendering_ambiguity_is_rejected(built):
    for mutate in (lambda f: f['reference']['entities'][0].__setitem__('name', 'Seminar, the Brindle'),
                   lambda f: f['reference']['attributes'][0].__setitem__('meaning', 'desk is opening'),
                   lambda f: f['reference']['state_keys'][1].__setitem__('value_inventory', ['12:25.', '12:55', '13:35'])):
        broken = deepcopy(built)
        mutate(broken[0])
        with pytest.raises(Exception):
            v.validate_set(broken)


def test_case_collisions_after_normalization_are_rejected(built):
    broken = deepcopy(built)
    hard = next(k for k in broken[0]['reference']['state_keys'] if k['state_key'] == 'k_hard')
    hard['value_inventory'][1] = hard['value_inventory'][1].upper() + ' '
    with pytest.raises(Exception):
        v.validate_set(broken)


def test_normalization_collision_between_target_values_is_rejected():
    with pytest.raises(ValueError):
        scoring.assert_distinct('Gate  Amber', ['gate amber'])


def test_schedule_and_role_mutations_are_rejected(built):
    broken = deepcopy(built)
    events = broken[0]['reference']['variants']['high']['events']
    events[14]['semantics'] = 'same_state'
    with pytest.raises(Exception):
        v.validate_set(broken)


def test_separation_rejects_reuse_of_every_reserved_set(built):
    for source, extract in (
            ('generator qualification', lambda: gq.read(sorted((ROOT / 'data/generator-qualification/fixtures').glob('*.json'))[0])),
            ('b0 calibration', lambda: gq.read(sorted((ROOT / 'data/b0-calibration/fixtures').glob('*.json'))[0]))):
        prior = extract()['reference']
        broken = deepcopy(built)
        broken[0]['reference']['entities'][1]['name'] = prior['entities'][0]['name']
        with pytest.raises(Exception, match='Pilot'):
            v.check_separation(broken, longmemeval=False)
        broken = deepcopy(built)
        broken[1]['reference']['state_keys'][3]['value_inventory'][1] = prior['state_keys'][3]['value_inventory'][1]
        with pytest.raises(Exception, match='Pilot'):
            v.check_separation(broken, longmemeval=False)


def test_separation_rejects_reused_attribute_meaning(built):
    prior = gq.read(sorted((ROOT / 'data/b0-calibration/fixtures').glob('*.json'))[0])['reference']
    broken = deepcopy(built)
    broken[0]['reference']['attributes'][0]['meaning'] = prior['attributes'][0]['meaning']
    with pytest.raises(Exception, match='attribute_meanings'):
        v.check_separation(broken, longmemeval=False)


def test_pilot_is_separate_from_the_reserved_sets(built):
    v.check_separation(built, longmemeval=False)


def test_pilot_is_separate_from_longmemeval_when_available(built):
    if not v.LONGMEMEVAL_RAW.exists():
        pytest.skip('LongMemEval-S raw data not present')
    v.check_separation(built, longmemeval=True)


def test_manifest_and_schema_drift_are_rejected(tmp_path):
    import shutil
    copy = tmp_path / 'pilot'
    shutil.copytree(v.DIRECTORY, copy)
    v.validate_directory(copy, longmemeval=False)
    manifest = json.loads((copy / 'manifest.json').read_text())
    manifest['not_final_crst_data'] = False
    (copy / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(Exception):
        v.validate_directory(copy, longmemeval=False)


def test_material_files_never_contain_naturalized_text_or_provider_data(material):
    text = (v.DIRECTORY / 'manifest.json').read_text()
    assert 'raw_assistant_content' not in text and 'usage' not in text
    for path in (v.DIRECTORY / 'fixtures').iterdir():
        assert json.loads(path.read_text())['purpose'] == 'CRST-SMALL-PILOT-ONLY'
