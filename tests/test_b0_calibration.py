"""Offline tests for the B0 calibration material, design, plan preview and budget derivation."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import socket
import sys

import httpx
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import b0_window as window
import build_b0_calibration_material as builder
import calibrate_b0 as cal
import probe_generators as probe
import qualify_generators as q
import validate_b0_calibration_material as v
import validate_generator_qualification_fixtures as gq


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)


@pytest.fixture(scope='module')
def material():
    return v.validate_directory()


@pytest.fixture(scope='module')
def fixtures(material):
    return material[1]


@pytest.fixture(scope='module')
def inputs(tmp_path_factory):
    """Inputs of the full-history procedure in its pre-Attempt-02 state, which exercises its machinery.

    The real design is closed and refuses every attempt; that is tested separately.
    """
    return cal.load_inputs(design_copy(tmp_path_factory.mktemp('historical')))


# --- Structured calibration material ---------------------------------------------------------------

SCHEDULES = {'low': {'U7'}, 'medium': {'U1', 'U3', 'U5', 'U7'}, 'high': {f'U{i}' for i in range(1, 8)}}
SECONDARY = {'low': {f'U{i}' for i in range(1, 7)}, 'medium': {'U2', 'U4', 'U6'}, 'high': set()}


def events(fixture, variant):
    return fixture['reference']['variants'][variant]['events']


def test_directory_validates_and_records_calibration_only_status(material):
    manifest, fixtures = material
    assert manifest['status'] == 'FROZEN' and manifest['purpose'] == 'B0-CALIBRATION-ONLY'
    assert manifest['total_scenarios'] == len(fixtures) == 12
    assert manifest['not_final_crst_data'] is True and manifest['not_generator_qualification_data'] is True
    assert manifest['prohibited_uses'] == ['final confirmatory CRST cases', 'Generator Qualification fixtures',
                                           'Model Qualification fixtures', 'LongMemEval-S material',
                                           'capability probe material']
    assert {f['purpose'] for f in fixtures} == {'B0-CALIBRATION-ONLY'}
    assert all(f['fixture_id'].startswith('b0cal-') for f in fixtures)


def test_exactly_twelve_scenarios_one_per_frozen_domain(fixtures):
    assert [f['reference']['domain'] for f in fixtures] == [
        'Scheduling', 'Travel', 'Project Planning', 'Task Assignment', 'Software Configuration',
        'Personal Preference', 'Purchase & Order', 'Study Planning', 'Communication',
        'Service & Subscription', 'Location & Logistics', 'Quantitative Planning']
    assert len({f['fixture_id'] for f in fixtures}) == 12


def test_revision_schedules_follow_the_frozen_crst_design(fixtures):
    for f in fixtures:
        for variant in gq.VARIANTS:
            evs = events(f, variant)
            updates = [e for e in evs if e['event'].startswith('U')]
            assert [e['event'] for e in updates] == [f'U{i}' for i in range(1, 8)]
            assert {e['event'] for e in updates if e['state_key'] == 'k_target'} == SCHEDULES[variant]
            assert {e['event'] for e in updates if e['state_key'] not in ('k_target',)} == SECONDARY[variant]
            assert all(e['semantics'] == 'changed_state' for e in updates)
            assert len(evs) == 16


def test_each_scenario_has_the_required_state_role_composition(fixtures):
    for f in fixtures:
        r = f['reference']
        roles = [k['role'] for k in r['state_keys']]
        assert sorted(roles) == sorted(['target', 'hard_distractor', 'dedicated_n2_secondary'] + ['updateable_secondary'] * 4)
        keys = {k['state_key']: k for k in r['state_keys']}
        assert keys['k_hard']['attribute_id'] == keys['k_target']['attribute_id']
        assert keys['k_hard']['entity_id'] != keys['k_target']['entity_id']
        assert keys['k_n2']['entity_id'] == keys['k_target']['entity_id']
        assert len(keys['k_target']['value_inventory']) == 8 and len(keys['k_n2']['value_inventory']) == 1
        assert set(r['initial_order']) == {f'I{i}' for i in range(1, 8)} and len(set(r['initial_order'].values())) == 7


def test_u7_is_the_final_target_revision_and_n1_n2_are_same_state_reaffirmations(fixtures):
    for f in fixtures:
        for variant in gq.VARIANTS:
            evs = events(f, variant)
            order = [e['event'] for e in evs]
            assert order[-3:] == ['N1', 'U7', 'N2'] and order.index('U6') == order.index('N1') - 1
            by = {e['event']: e for e in evs}
            assert by['U7']['state_key'] == 'k_target' and by['U7']['semantics'] == 'changed_state'
            assert not [e for e in evs[order.index('U7') + 1:] if e['semantics'] == 'changed_state']
            assert by['N1']['state_key'] == 'k_target' and by['N1']['semantics'] == 'same_state'
            assert by['N1']['current_value'] == by['U6']['state_after']['k_target']
            assert by['N2']['state_key'] == 'k_n2' and by['N2']['semantics'] == 'same_state'
            n2_value = {k['state_key']: k for k in f['reference']['state_keys']}['k_n2']['value_inventory'][0]
            assert by['N2']['current_value'] == by['N2']['previous_value'] == n2_value


def test_dedicated_n2_state_is_never_updated_and_target_values_never_return(fixtures):
    for f in fixtures:
        keys = {k['state_key']: k for k in f['reference']['state_keys']}
        for variant in gq.VARIANTS:
            evs = events(f, variant)
            assert not [e for e in evs if e['state_key'] == 'k_n2' and e['semantics'] == 'changed_state']
            assert {e['current_value'] for e in evs if e['state_key'] == 'k_n2'} == set(keys['k_n2']['value_inventory'])
            seen = []
            for e in evs:
                if e['state_key'] == 'k_target' and e['semantics'] != 'same_state':
                    assert e['current_value'] not in seen
                    seen.append(e['current_value'])
            assert seen[-1] == f['reference']['gold_current_value']
            assert set(keys['k_hard']['value_inventory']).isdisjoint(keys['k_target']['value_inventory'])


def test_question_intent_and_final_target_are_shared_across_variants(fixtures):
    for f in fixtures:
        r = f['reference']
        projection = gq.project(f)
        assert projection['question_intent'] == r['question_intent'] and r['q_target'] == 'k_target'
        assert r['question_intent']['entity_id'].endswith('-primary')
        finals = {variant: r['variants'][variant]['final_state']['k_target'] for variant in gq.VARIANTS}
        assert set(finals.values()) == {r['gold_current_value']}
        u7 = {variant: {e['event']: e for e in events(f, variant)}['U7']['current_value'] for variant in gq.VARIANTS}
        assert len(set(u7.values())) == 1


def test_material_reproduces_byte_identically_from_the_builder(material):
    manifest, _ = material
    for path, data in builder.artifacts(manifest['construction_source_commit']).items():
        assert (v.DIRECTORY / path).read_bytes() == data


def test_material_does_not_overlap_generator_qualification_fixtures(fixtures):
    gq_fixtures = [gq.read(p) for p in sorted((gq.DIRECTORY / 'fixtures').glob('*.json'))]
    assert len(gq_fixtures) == 12

    def atoms(items):
        out = {'ids': set(), 'names': set(), 'attributes': set(), 'values': set(), 'meanings': set()}
        for f in items:
            r = f['reference']
            out['ids'] |= {f['fixture_id']} | {e['entity_id'] for e in r['entities']}
            out['names'] |= {' '.join(gq.normalized_words(e['name'])) for e in r['entities']}
            out['attributes'] |= {a['attribute_id'] for a in r['attributes']}
            out['meanings'] |= {a['meaning'] for a in r['attributes']}
            out['values'] |= {x for k in r['state_keys'] for x in k['value_inventory']}
        return out
    mine, theirs = atoms(fixtures), atoms(gq_fixtures)
    for kind in mine:
        assert mine[kind] and not mine[kind] & theirs[kind], kind


def test_separation_check_detects_reuse_of_earlier_material(fixtures):
    gq_fixture = gq.read(gq.DIRECTORY / 'fixtures/scheduling.json')
    for mutate in (
        lambda f: f['reference']['entities'][0].update(name=gq_fixture['reference']['entities'][0]['name']),
        lambda f: f['reference']['state_keys'][0]['value_inventory'].__setitem__(
            3, gq_fixture['reference']['state_keys'][0]['value_inventory'][3]),
        lambda f: f['reference']['attributes'][0].update(attribute_id='session_code'),
    ):
        changed = deepcopy(fixtures)
        mutate(changed[0])
        with pytest.raises(ValueError, match='earlier material'):
            v.check_separation(changed)


def test_validation_rejects_structural_violations(fixtures):
    def low_u7_as_secondary(f):
        event = next(e for e in f['reference']['variants']['low']['events'] if e['event'] == 'U7')
        event['state_key'] = 'k_a'

    def wrong_purpose(f):
        f['purpose'] = 'GENERATOR-QUALIFICATION-ONLY'

    def wrong_identity(f):
        f['fixture_id'] = 'gq-scheduling-01'

    def n2_updated(f):
        event = next(e for e in f['reference']['variants']['high']['events'] if e['event'] == 'U2')
        event['state_key'] = 'k_n2'

    for mutate in (low_u7_as_secondary, wrong_purpose, wrong_identity, n2_updated):
        broken = deepcopy(fixtures[0])
        mutate(broken)
        with pytest.raises(Exception):
            v.validate_fixture(broken)
    with pytest.raises(ValueError):
        v.validate_set(fixtures[:11])
    with pytest.raises(ValueError):
        v.validate_set([*fixtures[:11], deepcopy(fixtures[0])])


def test_manifest_reserves_calibration_identifiers_for_exclusion(material):
    manifest, fixtures = material
    reserved = manifest['reserved_exclusions']
    assert reserved == v.reserved_exclusions(fixtures)
    assert len(reserved['scenario_ids']) == 12 and len(reserved['entity_names']) == 24
    assert {f['reference']['gold_current_value'] for f in fixtures} <= set(reserved['state_values'])


# --- Design and 24-call naturalization plan --------------------------------------------------------

def test_design_records_the_closed_decisions_without_a_budget():
    design = cal.load_design()
    assert design['status'] == 'DESIGN_FROZEN' and design['budget_status'] == 'OPEN'
    assert design['b0_context_tokens'] is None
    calibration = design['calibration']
    assert calibration['histories'] == {'scenarios': 12, 'intensities': ['low', 'medium', 'high'],
                                        'generators': 2, 'total': 72}
    assert calibration['retention'] == {'requirement': 'all_histories', 'fraction': 1.0, 'percentile_rule': 'none'}
    assert calibration['budget']['rule'] == 'exact_maximum' and calibration['budget']['headroom_tokens'] == 0
    assert calibration['budget']['candidate_grid'] == 'none'
    assert design['window_contract']['required_events'] == ['U7', 'N2']
    for path in ('experiments/b0_window.py', 'experiments/calibrate_b0.py', 'configs/b0-calibration.yaml'):
        assert not re.search(r'(?<![\w.])67(?![\w.])', (ROOT / path).read_text(encoding='utf-8')), path


SYSTEM_TEXT = "You are a helpful assistant. Use only the information provided in the context to answer the user's final question."
ANSWER_TEXT = 'Reply with the answer only.'
PROMPT_SHA256 = '8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e'


def test_system_and_answer_prompt_are_frozen_with_exact_text_and_hash():
    design = cal.load_design()
    prompt = design['system_prompt']
    assert prompt['status'] == 'FROZEN'
    assert prompt['system'] == SYSTEM_TEXT and prompt['answer'] == ANSWER_TEXT
    combined = SYSTEM_TEXT + '\n\n' + ANSWER_TEXT
    assert cal.system_message(design) == cal.official_system(design) == combined
    assert combined.encode('utf-8') == (
        b"You are a helpful assistant. Use only the information provided in the context to answer the user's "
        b"final question.\n\nReply with the answer only.")
    assert hashlib.sha256(combined.encode('utf-8')).hexdigest() == prompt['composed_sha256'] == PROMPT_SHA256
    lowered = combined.lower()
    for forbidden in ('latest', 'newest', 'most recent', 'ignore', 'old ', 'outdated', 'superseded', 'update',
                      'memory', 'conversation', 'history'):
        assert forbidden not in lowered, forbidden


def test_unapproved_prompt_wording_is_refused_for_official_use(inputs):
    design = inputs['design']
    proposed = deepcopy(design)
    proposed['system_prompt']['status'] = 'PROPOSED_PENDING_RESEARCHER_APPROVAL'
    with pytest.raises(ValueError, match='not approved'):
        cal.official_system(proposed)
    with pytest.raises(ValueError, match='not fully frozen'):
        cal.require_official(proposed)


def test_coverage_failure_rule_is_frozen_with_the_approved_procedure(inputs):
    design = cal.load_design()
    rule = design['calibration']['coverage_failure']
    assert rule['status'] == 'FROZEN'
    assert 'complete required U7 and N2 historical suffix' in rule['condition']
    assert rule['prohibited'] == [
        'silently increasing the B0 budget for that case', 'partially truncating an exchange',
        'altering the final CRST case to make it fit', 'adding arbitrary headroom',
        'using the failing final CRST case itself as calibration material']
    assert len(rule['response']) == 4
    assert rule['response'][0].startswith('Create new independent calibration-only extension scenarios')
    assert 'all original official calibration histories and all approved extension calibration histories' \
        in ' '.join(rule['response'][2].split())
    assert rule['response'][3].startswith('Freeze the recalibrated budget before the main experiment')
    assert 'separate from B0 calibration material' in rule['separation']
    cal.require_official(inputs['design'])
    assert design['budget_status'] == 'OPEN' and design['b0_context_tokens'] is None
    assert inputs['design']['naturalization']['status'] == 'AWAITING_COMPLETE_ATTEMPT'
    assert design['naturalization']['status'] == 'CLOSED_NO_ELIGIBLE_SET'


def test_preview_plans_exactly_24_calls_12_sol_and_12_fable(inputs):
    shown = cal.preview(inputs)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['naturalization_status'] == 'AWAITING_COMPLETE_ATTEMPT'
    assert shown['planned_logical_calls'] == 24 and shown['expected_histories'] == 72
    assert shown['per_generator'] == {'G1': 12, 'G2': 12}
    assert [(g['logical_call_id'], g['model']) for g in shown['generators']] == [
        ('G1', 'openai/gpt-5.6-sol'), ('G2', 'anthropic/claude-fable-5.1')]
    calls = shown['planned_calls']
    ids = shown['scenario_ids']
    assert calls == [f'{i}:{g}:{s}' for i, (g, s) in enumerate(
        [(g, s) for g in ('G1', 'G2') for s in ids], 1)]
    assert sum(':G1:' in c for c in calls) == sum(':G2:' in c for c in calls) == 12
    assert len(set(shown['request_hashes'])) == 24 and shown['maximum_physical_attempts'] == 72
    assert shown['budget_status'] == 'OPEN' and shown['b0_context_tokens'] is None


def test_requests_use_the_frozen_contract_and_exact_generator_identities(inputs):
    contract = json.loads((ROOT / 'configs/generator-naturalization-contract.json').read_text(encoding='utf-8'))
    for generator, fixture, entry in cal.plan(inputs):
        body = cal.request(generator, fixture)
        assert body['model'] == generator['entry']['model']
        assert body['provider'] == {'order': generator['entry']['provider_order'], 'allow_fallbacks': False,
                                    'require_parameters': True}
        assert body['messages'][0] == {'role': 'system', 'content': contract['prompt']}
        assert json.loads(body['messages'][1]['content']) == gq.project(fixture)
        assert body['response_format']['json_schema']['schema'] == contract['output_schema']
        assert body['reasoning'] == {'effort': 'low'} and body['max_tokens'] == 16384
        assert fixture['fixture_id'] == entry['fixture_id']


def test_preview_is_deterministic_and_makes_no_network_call(inputs):
    assert cal.preview(inputs) == cal.preview(cal.load_inputs(inputs['path']))


def test_design_drift_is_rejected(tmp_path):
    original = yaml.safe_load((ROOT / 'configs/b0-calibration.yaml').read_text(encoding='utf-8'))

    def write(mutate):
        design = deepcopy(original)
        mutate(design)
        path = tmp_path / 'design.yaml'
        path.write_text(yaml.safe_dump(design), encoding='utf-8')
        return path
    mutations = (
        lambda d: d['calibration']['material'].update(manifest_sha256='0' * 64),
        lambda d: d['naturalization']['generators'][0].update(model='openai/gpt-5.6-terra'),
        lambda d: d['naturalization']['generators'][1].update(model='anthropic/claude-opus-5'),
        lambda d: d['calibration']['retention'].update(fraction=0.95),
        lambda d: d.update(b0_context_tokens=100),
        lambda d: d['system_prompt'].update(answer='Reply briefly.'),
        lambda d: d['naturalization'].update(prompt_sha256='0' * 64),
        lambda d: d['naturalization'].update(planned_logical_calls=25),
    )
    for mutate in mutations:
        with pytest.raises(ValueError):
            cal.load_inputs(write(mutate))


# --- Ingestion and exact-maximum derivation (synthetic records only) -------------------------------

class ToyTokenizer:
    def apply_chat_template(self, messages, tokenize, add_generation_prompt):
        assert tokenize is False and add_generation_prompt is False
        return '<|bos|>' + ''.join(f'<|head|>{m["role"]}<|/head|>\n\n{m["content"]}<|eot|>' for m in messages)

    def encode(self, text, add_special_tokens):
        assert add_special_tokens is False
        return re.findall(r'<\|/?\w+\|>|\w+|[^\w\s]', text)


TOKENIZER = ToyTokenizer()
SYSTEM = 'Answer from the conversation.'


def synthetic_calls(inputs, mutate=None):
    """Structurally valid call records with synthetic text; lengths vary by generator, scenario and variant."""
    calls = []
    for gi, generator in enumerate(inputs['generators']):
        for si, entry in enumerate(inputs['manifest']['scenarios']):
            output = {}
            for vi, variant in enumerate(gq.VARIANTS):
                block = {label: ' '.join(['word'] * (3 + (si + vi) % 4)) for label in gq.EVENTS}
                block['U7'] = ' '.join(['seven'] * (2 + (gi * 5 + si * 3 + vi * 7) % 11))
                block['N2'] = ' '.join(['two'] * (2 + (gi * 3 + si * 5 + vi) % 9))
                block['Q'] = 'A synthetic question?'
                output[variant] = block
            calls.append({'logical_call_id': generator['entry']['logical_call_id'], 'fixture_id': entry['fixture_id'],
                          'attempt': 'attempt-02',
                          'status': 'PASS',
                          'attempts': [{'returned_model': generator['entry']['model'], 'parse_status': 'passed',
                                        'schema_status': 'passed', 'parsed_structured_response': output}]})
    if mutate:
        mutate(calls)
    return calls


def test_ingestion_builds_72_histories_from_24_passed_calls(inputs):
    histories = cal.histories_from_calls(synthetic_calls(inputs), inputs)
    assert len(histories) == 72
    assert {(h['generator'], h['model']) for h in histories} == {
        ('G1', 'openai/gpt-5.6-sol'), ('G2', 'anthropic/claude-fable-5.1')}
    assert len({(h['generator'], h['scenario'], h['variant']) for h in histories}) == 72
    assert all([e['event'] for e in h['exchanges']] == list(gq.EVENTS) for h in histories)


def test_ingestion_rejects_incomplete_duplicated_failed_or_misattributed_calls(inputs):
    def drop(calls): calls.pop()
    def duplicate(calls): calls[-1] = deepcopy(calls[0])
    def failed(calls): calls[3]['status'] = 'FAIL'
    def wrong_model(calls): calls[5]['attempts'][-1]['returned_model'] = 'openai/gpt-5.6-terra'
    def missing_variant(calls): del calls[7]['attempts'][-1]['parsed_structured_response']['medium']
    def unparsed(calls): calls[2]['attempts'][-1]['parse_status'] = 'failed'
    def extra_event(calls): calls[9]['attempts'][-1]['parsed_structured_response']['low']['N3'] = 'x'
    for mutate in (drop, duplicate, failed, wrong_model, missing_variant, unparsed, extra_event):
        with pytest.raises(ValueError):
            cal.histories_from_calls(synthetic_calls(inputs, mutate), inputs)


def test_derivation_is_the_exact_maximum_with_full_retention_and_minimality(inputs):
    histories = cal.histories_from_calls(synthetic_calls(inputs), inputs)
    result = cal.derive(histories, SYSTEM, TOKENIZER)
    independent = {(h['generator'], h['scenario'], h['variant']):
                   window.history_tokens(SYSTEM, h['exchanges'][-2:], TOKENIZER) for h in histories}
    assert [(r['generator'], r['scenario'], r['variant']) for r in result['per_history']] == list(independent)
    assert all(r['required_tokens'] == independent[(r['generator'], r['scenario'], r['variant'])]
               for r in result['per_history'])
    maximum = max(independent.values())
    assert len(set(independent.values())) > 3
    assert result['maximum'] == result['b0_context_tokens'] == maximum
    assert {(r['generator'], r['scenario'], r['variant']) for r in result['determined_by']} == {
        k for k, need in independent.items() if need == maximum}
    assert result['retention'] == {'histories': 72, 'retained': 72, 'fraction': 1.0}
    for h in histories:
        at = window.select_window(h['exchanges'], maximum, SYSTEM, TOKENIZER)
        assert window.retains(at) and at['history_tokens'] <= maximum
    for key in independent:
        if independent[key] == maximum:
            h = next(h for h in histories if (h['generator'], h['scenario'], h['variant']) == key)
            assert not window.retains(window.select_window(h['exchanges'], maximum - 1, SYSTEM, TOKENIZER))


def test_derivation_is_deterministic_and_adds_no_headroom(inputs):
    histories = cal.histories_from_calls(synthetic_calls(inputs), inputs)
    first, second = cal.derive(histories, SYSTEM, TOKENIZER), cal.derive(histories, SYSTEM, TOKENIZER)
    assert first == second
    longer = synthetic_calls(inputs)
    longer[0]['attempts'][-1]['parsed_structured_response']['high']['N2'] = ' '.join(['two'] * 40)
    bigger = cal.derive(cal.histories_from_calls(longer, inputs), SYSTEM, TOKENIZER)
    assert bigger['maximum'] > first['maximum']
    assert [r['generator'] for r in bigger['determined_by']] == ['G1']
    assert bigger['maximum'] == window.history_tokens(
        SYSTEM, cal.histories_from_calls(longer, inputs)[2]['exchanges'][-2:], TOKENIZER)


def test_derivation_requires_histories():
    with pytest.raises(ValueError):
        cal.derive([], SYSTEM, TOKENIZER)


# --- Final structured-material audit (independent of the validator) --------------------------------

def test_audit_initial_events_introduce_each_state_exactly_once(fixtures):
    for f in fixtures:
        r = f['reference']
        keys = {k['state_key']: k for k in r['state_keys']}
        assert sorted(r['initial_order']) == [f'I{i}' for i in range(1, 8)]
        assert sorted(r['initial_order'].values()) == sorted(gq.KEYS)
        for variant in gq.VARIANTS:
            initial = [e for e in events(f, variant) if e['event'].startswith('I')]
            assert [e['event'] for e in initial] == [f'I{i}' for i in range(1, 8)]
            assert [e['state_key'] for e in initial] == [r['initial_order'][e['event']] for e in initial]
            assert all(e['semantics'] == 'initial' and e['previous_value'] is None for e in initial)
            assert all(e['current_value'] == keys[e['state_key']]['initial_value'] for e in initial)
            assert {e['state_key'] for e in initial} == set(gq.KEYS)


def test_audit_non_target_updates_touch_only_permitted_secondary_states(fixtures):
    for f in fixtures:
        keys = {k['state_key']: k for k in f['reference']['state_keys']}
        permitted = {k for k, item in keys.items() if item['role'] in ('hard_distractor', 'updateable_secondary')}
        for variant in gq.VARIANTS:
            secondary = [e for e in events(f, variant) if e['event'].startswith('U') and e['state_key'] != 'k_target']
            assert {e['state_key'] for e in secondary} <= permitted
            assert all(e['current_value'] in keys[e['state_key']]['value_inventory'] for e in secondary)
            assert all(e['current_value'] != e['previous_value'] for e in secondary)
            hard = [e for e in secondary if e['state_key'] == 'k_hard']
            if variant != 'high':
                assert len(hard) == 1


def test_audit_n1_reaffirms_the_current_target_without_leaking_superseded_values(fixtures):
    for f in fixtures:
        for variant in gq.VARIANTS:
            evs = events(f, variant)
            order = [e['event'] for e in evs]
            n1 = evs[order.index('N1')]
            assert order.index('U6') < order.index('N1') < order.index('U7')
            target_before = [e for e in evs[:order.index('N1')] if e['state_key'] == 'k_target'][-1]
            assert n1['semantics'] == 'same_state' and n1['current_value'] == target_before['current_value']
            assert n1['previous_value'] == n1['current_value'] and n1['state_after']['k_target'] == n1['current_value']
            assert n1['current_value'] not in n1['superseded_values']
            assert n1['superseded_values'] == target_before['superseded_values']


def test_audit_n2_is_after_u7_and_is_neither_the_target_nor_the_hard_distractor(fixtures):
    for f in fixtures:
        keys = {k['state_key']: k for k in f['reference']['state_keys']}
        assert keys['k_n2']['role'] == 'dedicated_n2_secondary'
        assert (keys['k_n2']['entity_id'], keys['k_n2']['attribute_id']) not in {
            (keys[k]['entity_id'], keys[k]['attribute_id']) for k in ('k_target', 'k_hard')}
        for variant in gq.VARIANTS:
            evs = events(f, variant)
            order = [e['event'] for e in evs]
            n2 = evs[order.index('N2')]
            assert order.index('N2') == order.index('U7') + 1 == 15
            assert n2['state_key'] == 'k_n2' and n2['semantics'] == 'same_state'
            assert [e['current_value'] for e in evs if e['state_key'] == 'k_n2'] == [keys['k_n2']['initial_value']] * 2


def test_audit_question_asks_only_for_the_current_target_and_leaks_no_gold(fixtures):
    for f in fixtures:
        r = f['reference']
        keys = {k['state_key']: k for k in r['state_keys']}
        question = r['question_intent']
        assert (question['entity_id'], question['attribute_id']) == (
            keys['k_target']['entity_id'], keys['k_target']['attribute_id'])
        assert question['intent'].startswith('Ask only for the current ')
        every_value = {x for k in r['state_keys'] for x in k['value_inventory']}
        assert not [x for x in every_value if x.casefold() in question['intent'].casefold()]
        projection = gq.project(f)
        assert set(projection) == {'domain', 'entities', 'attributes', 'initial_order', 'question_intent',
                                   'state_keys', 'variants'}
        text = json.dumps(projection).lower()
        for reference_only in ('gold', 'superseded', 'previous_value', 'state_after', 'final_state', 'coverage'):
            assert reference_only not in text
        assert all(set(e) == {'event', 'state_key', 'current_value', 'semantics'}
                   for variant in gq.VARIANTS for e in projection['variants'][variant])


def test_audit_calibration_identifiers_are_reserved_and_distinct_from_final_crst_conventions(material):
    manifest, fixtures = material
    reserved = manifest['reserved_exclusions']
    for f in fixtures:
        r = f['reference']
        assert f['fixture_id'] in reserved['scenario_ids']
        assert all(e['entity_id'] in reserved['entity_ids'] and e['name'] in reserved['entity_names']
                   for e in r['entities'])
        assert all(a['attribute_id'] in reserved['attribute_ids'] for a in r['attributes'])
        assert all(x in reserved['state_values'] for k in r['state_keys'] for x in k['value_inventory'])
    assert len(reserved['attribute_ids']) == len({a['attribute_id'] for f in fixtures for a in f['reference']['attributes']})


def test_audit_no_scenario_reuses_another_scenarios_entities_or_values(fixtures):
    names = [' '.join(gq.normalized_words(e['name'])) for f in fixtures for e in f['reference']['entities']]
    assert len(names) == len(set(names)) == 24
    codes = [next(k for k in f['reference']['state_keys'] if k['state_key'] == 'k_n2')['initial_value']
             for f in fixtures]
    assert len(set(codes)) == 12
    finals = [f['reference']['gold_current_value'] for f in fixtures]
    assert len(set(finals)) == 12


# --- Naturalization contract and generator settings ------------------------------------------------

def test_naturalization_contract_versions_and_hashes_match_the_qualification_evidence(inputs):
    nat = inputs['design']['naturalization']
    assert (nat['prompt_version'], nat['input_contract_version'], nat['output_schema_version']) == (
        'crst-naturalization-prompt/1.1.0', 'crst-naturalization-input/1.1.0', 'crst-naturalization-triplet/1.0.0')
    assert nat['contract_sha256'] == q.CONTRACT_HASH == probe.file_hash(ROOT / 'configs/generator-naturalization-contract.json')
    assert nat['prompt_sha256'] == q.PROMPT_HASH and nat['output_schema_sha256'] == q.SCHEMA_HASH
    for attempt in ('attempt-01', 'attempt-03'):
        recorded = json.loads((ROOT / f'results/generator-qualification/{attempt}/qualification.json').read_text(
            encoding='utf-8'))['provenance']
        assert recorded['contract_sha256'] == nat['contract_sha256']
        assert recorded['prompt_sha256'] == nat['prompt_sha256']
        assert recorded['output_schema_sha256'] == nat['output_schema_sha256']
        assert {k: recorded[k] for k in probe.VERSIONS} == probe.VERSIONS
    for generator in inputs['generators']:
        assert generator['bundle']['provenance']['prompt_sha256'] == nat['prompt_sha256']


def test_calibration_scenarios_satisfy_the_frozen_input_contract(fixtures):
    for f in fixtures:
        gq.validate_input(gq.project(f))
        assert gq.canonical(gq.project(f)) == gq.canonical(json.loads(gq.canonical(gq.project(f)).decode()))


def test_generator_settings_are_the_exact_qualified_identities_and_routes(inputs):
    assert [(g['entry']['logical_call_id'], g['entry']['model'], g['entry']['provider_order'])
            for g in inputs['generators']] == [
        ('G1', 'openai/gpt-5.6-sol', ['openai']), ('G2', 'anthropic/claude-fable-5.1', ['anthropic'])]
    for g in inputs['generators']:
        model = g['entry']['model']
        assert not model.startswith('~') and ':' not in model and 'latest' not in model
        assert not {'terra', 'sonnet', 'opus'} & set(re.split(r'[-/]', model))
        capability = probe.slot_capability(g['entry']['execution_profile'], g['slot'])
        assert (capability['status'], capability['capability_result']) == ('CLOSED', 'PASS')
        assert capability['model'] == model
        evidence = json.loads((ROOT / g['entry']['qualification_evidence_path']).read_text(encoding='utf-8'))
        assert evidence['candidates'][g['entry']['logical_call_id']] == 'QUALIFIED'
        assert probe.file_hash(ROOT / g['entry']['qualification_evidence_path']) == g['entry']['qualification_evidence_sha256']
    fable = probe.slot_capability('second_level_g2', inputs['generators'][1]['slot'])
    assert fable['evidence_sha256'] == probe.file_hash(ROOT / fable['evidence_path'] / 'probe.json')
    for generator, fixture, _ in cal.plan(inputs):
        body = cal.request(generator, fixture)
        assert body['provider']['allow_fallbacks'] is False and body['provider']['require_parameters'] is True
        assert body['provider']['order'] == generator['entry']['provider_order']
        assert not {'temperature', 'top_p', 'tools', 'models', 'route'} & body.keys()


# --- Official execution plan -----------------------------------------------------------------------

def test_plan_orders_all_sol_calls_then_all_fable_calls_in_manifest_order(inputs):
    shown = cal.preview(inputs)
    ids = shown['scenario_ids']
    assert ids == [e['fixture_id'] for e in inputs['manifest']['scenarios']]
    calls = shown['calls']
    assert [c['index'] for c in calls] == list(range(1, 25))
    assert [(c['logical_call_id'], c['scenario_id']) for c in calls] == (
        [('G1', s) for s in ids] + [('G2', s) for s in ids])
    assert [c['model'] for c in calls] == ['openai/gpt-5.6-sol'] * 12 + ['anthropic/claude-fable-5.1'] * 12
    assert len({(c['logical_call_id'], c['scenario_id']) for c in calls}) == 24
    assert all(sum(c['scenario_id'] == s for c in calls) == 2 for s in ids)
    assert shown['expected_histories'] == 72 and shown['planned_logical_calls'] == 24


def test_plan_records_reproducible_input_request_and_output_metadata(inputs):
    shown = cal.preview(inputs)
    manifest = {e['fixture_id']: e for e in inputs['manifest']['scenarios']}
    for call, (generator, fixture, entry) in zip(shown['calls'], cal.plan(inputs)):
        body = cal.request(generator, fixture)
        assert call['input_sha256'] == manifest[call['scenario_id']]['projection_sha256'] == gq.sha(gq.canonical(gq.project(fixture)))
        assert call['request_sha256'] == probe.digest(probe.canonical(body).encode())
        assert call['output_path'] == (
            f'results/b0-calibration/attempt-02/outputs/{call["logical_call_id"].lower()}/{call["scenario_id"]}.json')
        assert 'response' not in ' '.join(call)
    assert len({c['request_sha256'] for c in shown['calls']}) == 24
    assert len({c['output_path'] for c in shown['calls']}) == 24
    assert len({c['input_sha256'] for c in shown['calls']}) == 12
    assert shown['request_hashes'] == [c['request_sha256'] for c in shown['calls']]
    assert shown['system_prompt_sha256'] == PROMPT_SHA256


def test_preview_does_not_create_the_official_result_directory(inputs):
    official = ROOT / cal.official_attempt(inputs['design'])['result_directory']
    before = official.exists()
    cal.preview(inputs)
    assert cal.main([]) == 0
    assert official.exists() == before


# --- Pre-spend safety of the live path (mocked transport only) -------------------------------------

def fake_git(*args):
    return b'0' * 40 + b'\n' if args[:1] == ('rev-parse',) else b''


def mock_output(scenario_index):
    return {variant: {**{label: f'Scenario {scenario_index} {variant} {label} statement.' for label in gq.EVENTS},
                      'Q': 'What is the current value?'} for variant in gq.VARIANTS}


def envelope(body, output):
    return {'model': body['model'], 'id': 'mock-response',
            'openrouter_metadata': {'endpoints': {'available': [
                {'provider': body['provider']['order'][0], 'selected': True}]}},
            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(output)}}]}


def run_collect(inputs, path, monkeypatch, respond=None, key='test-secret'):
    """Runs the live path against a mock transport; returns (result, request bodies)."""
    monkeypatch.setattr(cal, 'git', fake_git)
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        reply = respond(len(bodies) - 1, body) if respond else None
        return reply or httpx.Response(200, json=envelope(body, mock_output(len(bodies) - 1)))

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    async def no_wait(seconds):
        pass
    result = asyncio.run(cal.collect(inputs, key, path, client_factory=factory, sleep=no_wait))
    return result, bodies


def test_mocked_collection_completes_archives_and_reads_back_72_histories(inputs, tmp_path, monkeypatch):
    path = tmp_path / 'attempt-01'
    result, bodies = run_collect(inputs, path, monkeypatch)
    shown = cal.preview(inputs)
    assert result['status'] == 'COMPLETE' and len(result['calls']) == len(bodies) == 24
    assert [probe.digest(probe.canonical(b).encode()) for b in bodies] == shown['request_hashes']
    names = sorted(str(p.relative_to(path)) for p in path.rglob('*') if p.is_file())
    assert names == sorted([c['output_path'].removeprefix(shown['result_directory'] + '/') for c in shown['calls']]
                           + ['SHA256SUMS', 'collection.json'])
    assert 'test-secret' not in ' '.join(p.read_text(encoding='utf-8') for p in path.rglob('*') if p.is_file())
    records = cal.read_calls(path)
    assert [c['logical_call_index'] for c in records] == list(range(1, 25))
    histories = cal.histories_from_calls(records, inputs)
    assert len(histories) == 72 and {h['model'] for h in histories} == {
        'openai/gpt-5.6-sol', 'anthropic/claude-fable-5.1'}
    provenance = result['provenance']
    assert provenance['system_prompt_sha256'] == PROMPT_SHA256
    assert provenance['qualification_implementation']['status'] == q.FROZEN
    assert set(provenance['implementation']) == set(cal.IMPLEMENTATION)


def test_archive_reader_detects_a_modified_call_record(inputs, tmp_path, monkeypatch):
    path = tmp_path / 'attempt-01'
    run_collect(inputs, path, monkeypatch)
    victim = path / 'outputs/g1/b0cal-scheduling-01.json'
    victim.write_text(victim.read_text(encoding='utf-8').replace('statement', 'edited'), encoding='utf-8')
    with pytest.raises(ValueError, match='drifted'):
        cal.read_calls(path)


def test_existing_output_directory_is_never_overwritten(inputs, tmp_path, monkeypatch):
    path = tmp_path / 'attempt-01'
    path.mkdir()
    marker = path / 'keep.txt'
    marker.write_text('existing evidence')
    with pytest.raises(FileExistsError):
        run_collect(inputs, path, monkeypatch)
    assert [p.name for p in path.iterdir()] == ['keep.txt'] and marker.read_text() == 'existing evidence'
    completed = tmp_path / 'attempt-02'
    run_collect(inputs, completed, monkeypatch)
    with pytest.raises(FileExistsError):
        run_collect(inputs, completed, monkeypatch)


def test_semantic_or_schema_failure_stops_without_retry_and_keeps_partial_evidence(inputs, tmp_path, monkeypatch):
    def respond(index, body):
        if index == 5:
            return httpx.Response(200, json=envelope(body, {'low': {}}))
    path = tmp_path / 'attempt-01'
    result, bodies = run_collect(inputs, path, monkeypatch, respond)
    assert len(bodies) == 6  # The failed call is not repeated and no later call is made.
    assert result['status'] == 'INCOMPLETE' and len(result['calls']) == 6
    assert 'STOP FOR RESEARCHER DECISION' in result['failure_reason']
    failed = result['calls'][5]
    assert failed['status'] == 'FAIL' and len(failed['attempts']) == 1
    assert failed['attempts'][0]['parse_status'] == 'passed' and failed['attempts'][0]['schema_status'] == 'failed'
    assert len(list((path / 'outputs').rglob('*.json'))) == 6
    assert (path / 'collection.json').is_file() and (path / 'SHA256SUMS').is_file()
    assert len(cal.read_calls(path)) == 6
    with pytest.raises(ValueError):
        cal.histories_from_calls(cal.read_calls(path), inputs)


def test_only_frozen_infrastructure_retries_repeat_a_request(inputs, tmp_path, monkeypatch):
    def transient(index, body):
        if index == 2:
            return httpx.Response(503, json={'error': {'message': 'unavailable'}})
    result, bodies = run_collect(inputs, tmp_path / 'transient', monkeypatch, transient)
    assert result['status'] == 'COMPLETE' and len(bodies) == 25 and len(result['calls'][2]['attempts']) == 2

    def exhausted(index, body):
        if 2 <= index <= 4:
            return httpx.Response(503, json={'error': {'message': 'unavailable'}})
    result, bodies = run_collect(inputs, tmp_path / 'exhausted', monkeypatch, exhausted)
    assert result['status'] == 'INCOMPLETE' and len(bodies) == 5
    assert len(result['calls']) == 3 and len(result['calls'][2]['attempts']) == 3


def test_collect_refuses_before_any_side_effect_when_prerequisites_fail(inputs, tmp_path, monkeypatch):
    def refused(message, mutate=None, key='test-secret', git=fake_git):
        path = tmp_path / message.replace(' ', '-')
        monkeypatch.setattr(cal, 'git', git)
        calls = []
        target = deepcopy(inputs)
        if mutate:
            mutate(target)

        def factory(**kwargs):
            calls.append(kwargs)
            raise AssertionError('No client may be created')
        with pytest.raises(ValueError, match=message):
            asyncio.run(cal.collect(target, key, path, client_factory=factory))
        assert not path.exists() and not calls

    refused('OPENROUTER_API_KEY', key=' ')
    refused('clean worktree', git=lambda *a: b' M experiments/calibrate_b0.py' if a[:1] == ('status',) else b'x')
    refused('not fully frozen', lambda i: i['design']['system_prompt'].update(status='PROPOSED_PENDING_RESEARCHER_APPROVAL'))
    refused('not fully frozen', lambda i: i['design']['calibration']['coverage_failure'].update(status='PROPOSED_PENDING_RESEARCHER_APPROVAL'))
    refused('not fully frozen', lambda i: i['design'].update(b0_context_tokens=100))
    refused('not fully frozen', lambda i: i['design']['naturalization'].update(status='EXECUTED'))
    monkeypatch.setattr(q, 'implementation', lambda protocol='v1': {'status': q.NOT_FROZEN, 'freeze_commit': None})
    refused(q.NOT_FROZEN)


def historical(design):
    nat = design['naturalization']
    nat['status'] = 'AWAITING_COMPLETE_ATTEMPT'
    nat['attempts'][1]['status'] = 'PLANNED_NOT_EXECUTED'
    nat['attempts'][1].pop('closure', None)


def design_copy(tmp_path, mutate=None):
    design = yaml.safe_load((ROOT / 'configs/b0-calibration.yaml').read_text(encoding='utf-8'))
    historical(design)
    if mutate:
        mutate(design)
    path = tmp_path / 'design.yaml'
    path.write_text(yaml.safe_dump(design), encoding='utf-8')
    return path


@pytest.mark.parametrize('mutate,message', [
    (lambda d: d['calibration']['material'].update(manifest_sha256='0' * 64), 'Calibration material drift'),
    (lambda d: d['naturalization']['generators'][1].update(
        qualification_evidence_path='results/generator-qualification/adjudication/v2/attempt-01.json',
        qualification_evidence_sha256='0e8cec2bd51543d10efe8ad70b2c3e758b75c708209a9665b20d5877555685da'),
     'evidence mismatch'),
    (lambda d: d['naturalization']['generators'][0].update(qualification_evidence_sha256='0' * 64),
     'evidence mismatch'),
])
def test_collect_refuses_when_material_or_generator_evidence_no_longer_validates(
        inputs, tmp_path, monkeypatch, mutate, message):
    monkeypatch.setattr(cal, 'git', fake_git)
    target = {**inputs, 'path': design_copy(tmp_path, mutate)}
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match=message):
        asyncio.run(cal.collect(target, 'test-secret', path))
    assert not path.exists()


def test_collect_refuses_when_generator_capability_is_not_closed_pass(inputs, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)
    real = probe.slot_capability
    monkeypatch.setattr(probe, 'slot_capability', lambda profile, slot: {
        **real(profile, slot), 'status': 'OPEN', 'capability_result': 'NOT_ASSESSED'})
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='CLOSED/PASS capability evidence'):
        asyncio.run(cal.collect(inputs, 'test-secret', path))
    assert not path.exists()


def test_collect_refuses_when_material_validation_fails(inputs, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)

    def broken(*args, **kwargs):
        raise ValueError('Scenario structure invalid')
    monkeypatch.setattr(cal.material, 'validate_directory', broken)
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='Scenario structure invalid'):
        asyncio.run(cal.collect(inputs, 'test-secret', path))
    assert not path.exists()


def test_collect_refuses_when_inputs_change_after_preflight(inputs, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)
    seen = []
    real = cal.provenance
    monkeypatch.setattr(cal, 'provenance', lambda i: {**real(i), 'python': f'changed-{len(seen.append(1) or seen)}'})
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='changed since preflight'):
        asyncio.run(cal.collect(inputs, 'test-secret', path))
    assert not path.exists()


def test_cli_execution_gates(inputs, tmp_path, monkeypatch, capsys):
    official = ROOT / cal.official_attempt(inputs['design'])['result_directory']
    existed = official.exists()
    design = ['--design', str(inputs['path'])]
    for flags in (['--execute'], ['--confirm-spend'], ['--execute', '--confirm-spend'],
                  ['--output-directory', str(tmp_path / 'x')]):
        with pytest.raises(SystemExit):
            cal.main([*design, *flags])
    with pytest.raises(ValueError, match='frozen result directory'):
        cal.main([*design, '--execute', '--confirm-spend', '--output-directory', str(tmp_path / 'elsewhere')])
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with pytest.raises(ValueError, match='OPENROUTER_API_KEY'):
        cal.main([*design, '--execute', '--confirm-spend', '--output-directory', str(official)])
    assert official.exists() == existed and not (tmp_path / 'x').exists() and not (tmp_path / 'elsewhere').exists()

    async def stub(inputs, key, output, **kwargs):
        stub.seen = (key, Path(output))
        return {'status': stub.status, 'calls': [], 'planned_logical_calls': 24}
    monkeypatch.setattr(cal, 'collect', stub)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'k')
    for status, code in (('COMPLETE', 0), ('INCOMPLETE', 1)):
        stub.status = status
        assert cal.main([*design, '--execute', '--confirm-spend', '--output-directory', str(official)]) == code
        assert stub.seen == ('k', official)
    assert 'no budget derived' in capsys.readouterr().out
