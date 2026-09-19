"""Offline tests for the suffix-only B0 calibration procedure (U7 and N2 only); no model or network call."""
import asyncio
from copy import deepcopy
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
import calibrate_b0 as cal
import calibrate_b0_suffix as s
import probe_generators as probe
import qualify_generators as q
import validate_generator_qualification_fixtures as gq
from test_b0_calibration import SYSTEM, TOKENIZER, envelope, fake_git

CONFIG = ROOT / 'configs/b0-suffix-calibration.yaml'
CONTRACT = ROOT / 'configs/b0-suffix-naturalization-contract.json'
OLD_ATTEMPTS = [ROOT / 'results/b0-calibration/attempt-01', ROOT / 'results/b0-calibration/attempt-02']
FORBIDDEN_LABELS = re.compile(r'\b(?:I[1-7]|U[1-6]|N1|Q)\b')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)


@pytest.fixture(scope='module')
def inputs():
    return s.load_inputs()


@pytest.fixture(scope='module')
def config_copy(tmp_path_factory):
    def write(mutate=None, directory=None):
        config = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
        if mutate:
            mutate(config)
        path = (directory or tmp_path_factory.mktemp('config')) / 'suffix.yaml'
        path.write_text(yaml.safe_dump(config), encoding='utf-8')
        return path
    return write


@pytest.fixture(scope='module')
def approved():
    """The real, approved procedure; the live path is exercised offline with a mock transport."""
    return s.load_inputs()


def independent_facts(fixture):
    """U7/N2 facts read straight from the reference events, without the module's helpers."""
    r = fixture['reference']
    entities = {e['entity_id']: e['name'] for e in r['entities']}
    attributes = {a['attribute_id']: a['meaning'] for a in r['attributes']}
    keys = {k['state_key']: k for k in r['state_keys']}
    facts = set()
    for variant in gq.VARIANTS:
        for event in r['variants'][variant]['events']:
            if event['event'] in ('U7', 'N2'):
                key = keys[event['state_key']]
                facts.add((variant, event['event'], entities[key['entity_id']], attributes[key['attribute_id']],
                           event['current_value'], event['semantics']))
    return facts


# --- Suffix projection -----------------------------------------------------------------------------

def test_projection_is_exactly_u7_and_n2_and_nothing_else(inputs):
    for fixture, payload in zip(inputs['fixtures'], inputs['projections']):
        assert set(payload) == {'scenario_id', 'domain', 'entities', 'attributes', 'variants'}
        assert payload['scenario_id'] == fixture['fixture_id'] and payload['domain'] == fixture['reference']['domain']
        assert set(payload['variants']) == {'low', 'medium', 'high'}
        assert all(set(v) == {'U7', 'N2'} for v in payload['variants'].values())
        r = fixture['reference']
        assert [e['name'] for e in payload['entities']] == [
            next(e['name'] for e in r['entities'] if e['entity_id'].endswith('-primary'))]
        assert len(payload['attributes']) == 2
        text = json.dumps(payload)
        assert not FORBIDDEN_LABELS.search(text)
        keys = {k['state_key']: k for k in r['state_keys']}
        allowed = {r['gold_current_value'], keys['k_n2']['initial_value']}
        values = {f['current_value'] for v in payload['variants'].values() for f in v.values()}
        assert values == allowed
        for other in ('k_hard', 'k_a', 'k_b', 'k_c', 'k_d'):
            assert not [x for x in keys[other]['value_inventory'] if json.dumps(x) in text]
        assert not [x for x in keys['k_target']['value_inventory'][:-1] if json.dumps(x) in text]
        assert not [w for w in ('gold', 'superseded', 'previous', 'question', 'state_after', 'coverage', 'final_state')
                    if w in text.lower()]
        distractor = next(e['name'] for e in r['entities'] if e['entity_id'].endswith('-distractor'))
        assert distractor not in text


def test_all_36_variant_projections_match_the_frozen_source_truth(inputs):
    assert len(inputs['fixtures']) == 12 and len(inputs['projections']) == 12
    checked = 0
    for fixture, payload in zip(inputs['fixtures'], inputs['projections']):
        s.verify_projection(fixture, payload)
        names = {e['entity_id']: e['name'] for e in payload['entities']}
        meanings = {a['attribute_id']: a['meaning'] for a in payload['attributes']}
        from_payload = {(v, label, names[f['entity_id']], meanings[f['attribute_id']], f['current_value'], f['semantics'])
                        for v, events in payload['variants'].items() for label, f in events.items()}
        assert from_payload == independent_facts(fixture) and len(from_payload) == 6
        for variant in gq.VARIANTS:
            u7, n2 = payload['variants'][variant]['U7'], payload['variants'][variant]['N2']
            assert (u7['semantics'], n2['semantics']) == ('changed_state', 'same_state')
            assert u7['current_value'] == fixture['reference']['gold_current_value']
            checked += 1
    assert checked == 36


def test_projection_is_deterministic_and_rejects_altered_content(inputs):
    fixture = inputs['fixtures'][0]
    assert gq.canonical(s.projection(fixture)) == gq.canonical(s.projection(deepcopy(fixture)))
    assert len({gq.sha(gq.canonical(p)) for p in inputs['projections']}) == 12
    payload = deepcopy(inputs['projections'][0])
    def swap_all(p):
        for variant in p['variants'].values():
            variant['U7']['semantics'], variant['N2']['semantics'] = 'same_state', 'changed_state'

    def n2_changed_everywhere(p):
        for variant in p['variants'].values():
            variant['N2']['semantics'] = 'changed_state'
    for mutate in (swap_all, n2_changed_everywhere):
        broken = deepcopy(payload)
        mutate(broken)
        with pytest.raises(ValueError, match='Event semantics'):
            s.validate_input(broken)
    for mutate in (lambda p: p['variants']['low']['U7'].update(current_value='other'),
                   lambda p: p['variants']['high']['N2'].update(semantics='changed_state'),
                   lambda p: p['variants']['medium'].update(N1=p['variants']['medium']['U7']),
                   lambda p: p.update(previous_value='x'),
                   lambda p: p['entities'].append({'entity_id': 'extra', 'name': 'Extra'}),
                   lambda p: p['variants'].pop('low')):
        broken = deepcopy(payload)
        mutate(broken)
        with pytest.raises(Exception):
            s.verify_projection(fixture, broken)
        with pytest.raises(Exception):
            s.validate_input(broken)


# --- Contract and schema ---------------------------------------------------------------------------

def test_output_schema_requires_exactly_nonempty_u7_and_n2_per_variant(inputs):
    schema = inputs['contract']['output_schema']
    variant = schema['$defs']['variant']
    assert schema['additionalProperties'] is False and schema['required'] == ['low', 'medium', 'high']
    assert set(schema['properties']) == {'low', 'medium', 'high'}
    assert variant['additionalProperties'] is False and variant['required'] == ['U7', 'N2']
    assert set(variant['properties']) == {'U7', 'N2'}
    assert all(p == {'type': 'string', 'minLength': 1} for p in variant['properties'].values())
    for name in ('output_schema', 'input_schema'):
        assert not FORBIDDEN_LABELS.search(json.dumps(inputs['contract'][name]))
    assert not FORBIDDEN_LABELS.search(inputs['contract']['prompt'])


def test_output_validation_accepts_only_the_exact_suffix_shape():
    good = {v: {'U7': 'a', 'N2': 'b'} for v in gq.VARIANTS}
    s.validate_output(good)
    bad = [
        {**good, 'high': {'U7': '', 'N2': 'b'}}, {**good, 'high': {'U7': 'a', 'N2': ''}},
        {**good, 'medium': {'U7': ' \n', 'N2': 'b'}}, {**good, 'low': {'U7': 'a'}},
        {**good, 'low': {'U7': 'a', 'N2': 'b', 'N1': 'c'}}, {**good, 'low': {'U7': 'a', 'N2': 'b', 'Q': 'q'}},
        {'low': good['low'], 'medium': good['medium']}, {**good, 'extra': good['low']},
        {**good, 'high': {'U7': 1, 'N2': 'b'}},
        {v: {**{k: 'x' for k in gq.EVENTS}, 'Q': 'q'} for v in gq.VARIANTS},
    ]
    for output in bad:
        with pytest.raises(ValueError):
            s.validate_output(output)
    with pytest.raises(ValueError):
        probe.validate_output(good)


def test_procedure_has_its_own_versions_and_hashes_and_leaves_the_qualification_contract_alone(inputs):
    config = inputs['config']['contract']
    old = json.loads((ROOT / 'configs/generator-naturalization-contract.json').read_text(encoding='utf-8'))
    assert probe.file_hash(ROOT / 'configs/generator-naturalization-contract.json') == q.CONTRACT_HASH
    assert (config['prompt_version'], config['input_contract_version'], config['output_schema_version']) == (
        'b0-suffix-naturalization-prompt/1.0.0', 'b0-suffix-naturalization-input/1.0.0',
        'b0-suffix-naturalization-output/1.0.0')
    assert {config['prompt_version'], config['input_contract_version'], config['output_schema_version']}.isdisjoint(
        {old['prompt_version'], old['input_contract_version'], old['output_schema_version']})
    assert {config['prompt_sha256'], config['input_schema_sha256'], config['output_schema_sha256']}.isdisjoint(
        {q.PROMPT_HASH, q.SCHEMA_HASH})
    contract = inputs['contract']
    assert config['sha256'] == probe.file_hash(CONTRACT)
    assert config['prompt_sha256'] == probe.digest(contract['prompt'].encode('utf-8'))
    assert config['input_schema_sha256'] == probe.digest(probe.canonical(contract['input_schema']).encode('utf-8'))
    assert config['output_schema_sha256'] == probe.digest(probe.canonical(contract['output_schema']).encode('utf-8'))
    assert inputs['config']['input_projection']['set_sha256'] == gq.sha(
        gq.canonical([gq.sha(gq.canonical(p)) for p in inputs['projections']]))
    assert inputs['config']['plan']['plan_sha256'] == gq.sha(gq.canonical(s.plan_identity(inputs)))


def test_contract_shape_is_enforced_beyond_the_pinned_hash(config_copy, tmp_path):
    """Even a self-consistent contract with the wrong output shape is refused."""
    original = json.loads(CONTRACT.read_text(encoding='utf-8'))

    def contract_config(mutate):
        contract = deepcopy(original)
        mutate(contract['output_schema'])
        path = tmp_path / f'contract-{len(list(tmp_path.iterdir()))}.json'
        path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        def rewrite(c):
            c['contract'].update(
                path=str(path), sha256=probe.file_hash(path),
                output_schema_sha256=probe.digest(probe.canonical(contract['output_schema']).encode('utf-8')))
        return config_copy(rewrite)
    variant = lambda schema: schema['$defs']['variant']
    shapes = (lambda sc: variant(sc)['properties'].update(N1={'type': 'string', 'minLength': 1}),
              lambda sc: variant(sc)['properties'].update(Q={'type': 'string', 'minLength': 1}),
              lambda sc: variant(sc).update(required=['U7']),
              lambda sc: variant(sc)['properties']['N2'].update(minLength=0),
              lambda sc: variant(sc).update(additionalProperties=True),
              lambda sc: sc.update(additionalProperties=True),
              lambda sc: variant(sc)['properties'].pop('N2'))
    for mutate in shapes:
        with pytest.raises(ValueError, match='exactly nonempty U7 and N2'):
            s.load_contract(s.load_config(contract_config(mutate)))
    s.load_contract(s.load_config(contract_config(lambda sc: None)))


def test_contract_and_plan_drift_is_rejected(config_copy):
    def edit(section, key, value):
        return lambda c: c[section].update({key: value})
    for mutate in (edit('contract', 'prompt_sha256', '0' * 64), edit('contract', 'output_schema_sha256', '0' * 64),
                   edit('contract', 'input_schema_sha256', '0' * 64), edit('contract', 'sha256', '0' * 64),
                   edit('input_projection', 'set_sha256', '0' * 64), edit('plan', 'plan_sha256', '0' * 64),
                   edit('plan', 'planned_logical_calls', 25),
                   lambda c: c['generators'][0].update(model='openai/gpt-5.6-terra'),
                   lambda c: c['generators'][1].update(model='anthropic/claude-opus-5'),
                   lambda c: c.update(b0_context_tokens=100)):
        with pytest.raises(ValueError):
            s.load_inputs(config_copy(mutate))


# --- Generators and requests -----------------------------------------------------------------------

def test_generator_identities_and_provider_constraints_are_unchanged(inputs):
    design = inputs['design']['design']['naturalization']['generators']
    assert [{k: g[k] for k in ('logical_call_id', 'model', 'provider_order')} for g in design] == inputs['config']['generators']
    assert inputs['config']['generators'] == [
        {'logical_call_id': 'G1', 'model': 'openai/gpt-5.6-sol', 'provider_order': ['openai']},
        {'logical_call_id': 'G2', 'model': 'anthropic/claude-fable-5.1', 'provider_order': ['anthropic']}]
    for g in inputs['generators']:
        assert g['slot'] in probe.SLOTS + probe.SECOND_LEVEL_G2_SLOTS
        model = g['entry']['model']
        assert not model.startswith('~') and ':' not in model and 'latest' not in model
        assert not {'terra', 'sonnet', 'opus'} & set(re.split(r'[-/]', model))
        capability = probe.slot_capability(g['entry']['execution_profile'], g['slot'])
        assert (capability['status'], capability['capability_result']) == ('CLOSED', 'PASS')


def test_requests_use_the_suffix_contract_with_unchanged_execution_settings(inputs):
    contract = inputs['contract']
    for generator, fixture, entry, payload in s.plan(inputs):
        body = s.request(inputs, generator, payload)
        assert body['model'] == generator['entry']['model']
        assert body['provider'] == {'order': generator['entry']['provider_order'], 'allow_fallbacks': False,
                                    'require_parameters': True}
        assert body['messages'] == [{'role': 'system', 'content': contract['prompt']},
                                    {'role': 'user', 'content': probe.canonical(payload)}]
        assert json.loads(body['messages'][1]['content']) == s.projection(fixture)
        assert body['response_format'] == {'type': 'json_schema', 'json_schema': {
            'name': 'b0_suffix_naturalization_v1', 'strict': True, 'schema': contract['output_schema']}}
        assert body['reasoning'] == {'effort': 'low'} and body['max_tokens'] == 16384
        assert not {'temperature', 'top_p', 'tools', 'models', 'route'} & body.keys()
        assert payload['scenario_id'] == entry['fixture_id']


# --- Preview ---------------------------------------------------------------------------------------

def test_preview_plans_24_calls_12_sol_12_fable_and_72_suffix_histories(inputs):
    shown = s.preview(inputs)
    assert (shown['status'], shown['credits'], shown['suffix_collection_status']) == (
        'NETWORK_DISABLED', 'CREDITS_NOT_SPENT', 'NOT EXECUTED')
    assert shown['planned_logical_calls'] == 24 and shown['per_generator'] == {'G1': 12, 'G2': 12}
    assert shown['expected_histories'] == 72 and shown['suffix_events'] == ['U7', 'N2']
    ids = shown['scenario_ids']
    calls = shown['calls']
    assert [(c['index'], c['logical_call_id'], c['scenario_id']) for c in calls] == [
        (i, g, sid) for i, (g, sid) in enumerate([(g, sid) for g in ('G1', 'G2') for sid in ids], 1)]
    assert [c['model'] for c in calls] == ['openai/gpt-5.6-sol'] * 12 + ['anthropic/claude-fable-5.1'] * 12
    assert len({(c['logical_call_id'], c['scenario_id']) for c in calls}) == 24
    assert shown['maximum_physical_attempts'] == 72 and shown['budget_status'] == 'OPEN'
    assert shown['b0_context_tokens'] is None
    assert list(shown['old_procedure_closures']) == ['attempt-01', 'attempt-02']


def test_preview_hashes_are_deterministic_and_unique(inputs):
    first, second = s.preview(inputs), s.preview(s.load_inputs())
    assert first == second
    assert len(set(first['request_hashes'])) == 24
    assert len({c['input_sha256'] for c in first['calls']}) == 12
    assert len({c['output_path'] for c in first['calls']}) == 24
    assert first['request_hashes'] == [c['request_sha256'] for c in first['calls']]
    assert all(c['output_path'].startswith('results/b0-suffix-calibration/attempt-01/outputs/') for c in first['calls'])
    assert not any('b0-calibration/' in c['output_path'].replace('b0-suffix-calibration/', '') for c in first['calls'])
    assert not set(first['request_hashes']) & set(cal.plan_identity(cal.load_inputs())['request_sha256'])
    assert 'response' not in ' '.join(first['calls'][0])


def test_preview_and_default_invocation_create_no_result_directory(inputs, capsys):
    target = ROOT / 'results/b0-suffix-calibration'
    before = target.exists()
    s.preview(inputs)
    assert s.main([]) == 0
    assert json.loads(capsys.readouterr().out)['planned_logical_calls'] == 24
    assert target.exists() == before


# --- Approval and execution gates ------------------------------------------------------------------

def test_the_attempt_policy_and_semantic_rule_are_frozen_and_execution_needs_only_the_remaining_gates(
        inputs, tmp_path, monkeypatch):
    config = inputs['config']
    assert config['attempt_policy']['status'] == 'FROZEN' and config['attempt_policy']['cap'] == 1
    assert config['collection_rule']['status'] == 'FROZEN' and config['semantic_eligibility']['status'] == 'FROZEN'
    s.require_official(config)
    for section in ('attempt_policy', 'collection_rule', 'semantic_eligibility'):
        unapproved = deepcopy(config)
        unapproved[section]['status'] = 'PROPOSED_PENDING_RESEARCHER_APPROVAL'
        with pytest.raises(ValueError, match='not fully approved'):
            s.require_official(unapproved)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    official = ROOT / 'results/b0-suffix-calibration/attempt-01'
    existed = official.exists()
    with pytest.raises(ValueError, match='OPENROUTER_API_KEY'):
        s.main(['--execute', '--confirm-spend', '--output-directory', str(official)])
    assert official.exists() == existed


def test_exactly_one_attempt_is_allowed_and_no_second_attempt_can_start(config_copy, tmp_path, monkeypatch):
    extra = {'id': 'attempt-02', 'status': 'PLANNED_NOT_EXECUTED',
             'result_directory': 'results/b0-suffix-calibration/attempt-02'}
    assert s.load_config()['attempt_policy']['cap'] == 1
    for mutate in (lambda c: c['results']['attempts'].append(extra),
                   lambda c: c['attempt_policy'].update(cap=2),
                   lambda c: (c['attempt_policy'].update(cap=2), c['results']['attempts'].append(extra))):
        with pytest.raises(ValueError, match='exactly one attempt'):
            s.load_config(config_copy(mutate))
    closed_path = config_copy(lambda c: c['results']['attempts'][0].update(status='CLOSED_INCOMPLETE'))
    closed = s.load_config(closed_path)
    with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
        s.official_attempt(closed)
    with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
        s.require_official(closed)
    with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
        s.main(['--config', str(closed_path), '--execute', '--confirm-spend',
                '--output-directory', str(ROOT / 'results/b0-suffix-calibration/attempt-01')])


def test_the_closed_full_history_namespace_and_other_suffix_attempts_cannot_be_written(inputs, tmp_path):
    config = inputs['config']
    for name in ('', 'attempt-01', 'attempt-02', 'attempt-03', 'closure'):
        with pytest.raises(ValueError, match='immutable'):
            s.guard_output(ROOT / 'results/b0-calibration' / name, config)
    for name in ('attempt-02', 'attempt-03', 'closure'):
        with pytest.raises(ValueError, match='planned attempt directory'):
            s.guard_output(ROOT / 'results/b0-suffix-calibration' / name, config)
    s.guard_output(ROOT / 'results/b0-suffix-calibration/attempt-01', config)
    s.guard_output(tmp_path / 'anywhere', config)


def test_the_full_history_procedure_still_cannot_run(inputs):
    real = cal.load_inputs()
    with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
        cal.official_attempt(real['design'])
    with pytest.raises(ValueError, match='closed'):
        cal.require_official(real['design'])
    assert s.verify_old_procedure_closed(inputs) == cal.verify_predecessors(real)


# --- Mocked collection -----------------------------------------------------------------------------

def mock_output(fixture, mutate=None):
    r = fixture['reference']
    keys = {k['state_key']: k for k in r['state_keys']}
    name = next(e['name'] for e in r['entities'] if e['entity_id'].endswith('-primary'))
    attrs = {a['attribute_id']: a['meaning'] for a in r['attributes']}
    u7 = f'{name}: {attrs[keys["k_target"]["attribute_id"]]} is now {r["gold_current_value"]}.'
    n2 = f'{name}: {attrs[keys["k_n2"]["attribute_id"]]} is still {keys["k_n2"]["initial_value"]}.'
    output = {v: {'U7': f'{u7} ({v})', 'N2': f'{n2} ({v})'} for v in gq.VARIANTS}
    if mutate:
        mutate(output)
    return output


def run_collect(inputs, path, monkeypatch, respond=None, key='test-secret'):
    monkeypatch.setattr(cal, 'git', fake_git)
    calls = s.plan(inputs)
    position = {probe.digest(probe.canonical(s.request(inputs, g, p)).encode()): i for i, (g, _, _, p) in enumerate(calls)}
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        index = position[probe.digest(probe.canonical(body).encode())]
        bodies.append(body)
        reply = respond(index, body) if respond else None
        return reply or httpx.Response(200, json=envelope(body, mock_output(calls[index][1])))

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    async def no_wait(seconds):
        pass
    return asyncio.run(s.collect(inputs, key, path, client_factory=factory, sleep=no_wait)), bodies


REVIEWED_AT = '2026-09-19T20:00:00+07:00'


def completed_audit(path, inputs, manual_fail=(), fluency_fail=(), mutate=None):
    """A completed copy of the blank audit: every manual cell PASS unless named in manual_fail (item, check)."""
    audit = s.audit_template(path, inputs)
    audit.update(reviewer='Test reviewer', reviewed_at=REVIEWED_AT)
    for item, entry in audit['items'].items():
        entry['manual'] = {check: 'PASS' for check in entry['manual']}
        entry['fluency'] = 'FAIL' if item in fluency_fail else None
    for item, check in manual_fail:
        audit['items'][item]['manual'][check] = 'FAIL'
    if mutate:
        mutate(audit)
    return audit


def test_mocked_collection_completes_and_archives_24_suffix_calls(approved, tmp_path, monkeypatch):
    original = probe.validate_output
    path = tmp_path / 'attempt-01'
    result, bodies = run_collect(approved, path, monkeypatch)
    assert probe.validate_output is original
    shown = s.preview(approved)
    assert result['status'] == 'COMPLETE' and len(result['calls']) == len(bodies) == 24
    assert [probe.digest(probe.canonical(b).encode()) for b in bodies] == shown['request_hashes']
    assert [b['model'] for b in bodies] == ['openai/gpt-5.6-sol'] * 12 + ['anthropic/claude-fable-5.1'] * 12
    names = sorted(str(p.relative_to(path)) for p in path.rglob('*') if p.is_file())
    assert names == sorted([c['output_path'].removeprefix(shown['result_directory'] + '/') for c in shown['calls']]
                           + ['SHA256SUMS', 'collection.json'])
    assert 'test-secret' not in ' '.join(p.read_text(encoding='utf-8') for p in path.rglob('*') if p.is_file())
    provenance = result['provenance']
    assert provenance['attempt'] == 'attempt-01' and provenance['procedure_version'] == s.COLLECTION
    assert list(provenance['old_procedure_closures']) == ['attempt-01', 'attempt-02']
    assert provenance['qualification_implementation']['status'] == q.FROZEN
    assert provenance['plan_sha256'] == approved['config']['plan']['plan_sha256']
    assert provenance['system_prompt_sha256'] == '8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e'
    for call in result['calls']:
        assert (call['attempt'], call['procedure_version']) == ('attempt-01', s.COLLECTION)
        assert call['automated']['status'] == 'PASS' and set(call['attempts'][-1]['parsed_structured_response']) == {
            'low', 'medium', 'high'}
        assert all(set(v) == {'U7', 'N2'} for v in call['attempts'][-1]['parsed_structured_response'].values())


def test_complete_attempt_reads_back_as_72_suffix_histories_and_derives_from_complete_exchanges(
        approved, tmp_path, monkeypatch):
    path = tmp_path / 'attempt-01'
    run_collect(approved, path, monkeypatch)
    histories = s.histories_from_calls(s.official_calls(path), approved)
    assert len(histories) == 72
    assert {(h['generator'], h['model']) for h in histories} == {
        ('G1', 'openai/gpt-5.6-sol'), ('G2', 'anthropic/claude-fable-5.1')}
    assert len({(h['generator'], h['scenario'], h['variant']) for h in histories}) == 72
    for h in histories:
        assert [e['event'] for e in h['exchanges']] == ['U7', 'N2']
        assert all([m['role'] for m in e['messages']] == ['user', 'assistant']
                   and e['messages'][1]['content'] == 'Noted.' for e in h['exchanges'])
        assert 'question' not in h
    result = s.derive_budget(path, completed_audit(path, approved), TOKENIZER, approved, SYSTEM)
    base = [{'role': 'system', 'content': SYSTEM}]

    def independent(h):
        u7, n2 = (e['messages'][0]['content'] for e in h['exchanges'])
        turn = lambda text: [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': 'Noted.'}]
        cost = lambda messages: window.chat_tokens(base + messages, TOKENIZER) - window.chat_tokens(base, TOKENIZER)
        return max(cost(turn(u7) + turn(n2)), cost(turn(n2)))
    expected = {(h['generator'], h['scenario'], h['variant']): independent(h) for h in histories}
    assert {(r['generator'], r['scenario'], r['variant']): r['required_tokens'] for r in result['per_history']} == expected
    assert result['maximum'] == max(expected.values()) == result['b0_context_tokens']
    assert result['retention'] == {'histories': 72, 'retained': 72, 'fraction': 1.0}
    assert len(set(expected.values())) > 3
    for h in histories:
        need = expected[(h['generator'], h['scenario'], h['variant'])]
        assert window.retains(window.select_window(h['exchanges'], need, SYSTEM, TOKENIZER))
        assert not window.retains(window.select_window(h['exchanges'], need - 1, SYSTEM, TOKENIZER))


@pytest.mark.parametrize('label,reply', [
    ('empty U7', lambda i, b, f: httpx.Response(200, json=envelope(b, mock_output(f, lambda o: o['high'].update(U7=''))))),
    ('empty N2', lambda i, b, f: httpx.Response(200, json=envelope(b, mock_output(f, lambda o: o['low'].update(N2=''))))),
    ('blank U7', lambda i, b, f: httpx.Response(200, json=envelope(b, mock_output(f, lambda o: o['medium'].update(U7=' \n'))))),
    ('missing field', lambda i, b, f: httpx.Response(200, json=envelope(b, mock_output(f, lambda o: o['low'].pop('N2'))))),
    ('extra field', lambda i, b, f: httpx.Response(200, json=envelope(b, mock_output(f, lambda o: o['low'].update(N1='x'))))),
    ('missing variant', lambda i, b, f: httpx.Response(200, json=envelope(b, mock_output(f, lambda o: o.pop('high'))))),
    ('parse failure', lambda i, b, f: httpx.Response(200, json={**envelope(b, {}), 'choices': [{
        'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'not json'}}]})),
    ('refusal', lambda i, b, f: httpx.Response(200, json={**envelope(b, mock_output(f)), 'choices': [{
        'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{}', 'refusal': 'cannot help'}}]})),
    ('truncation', lambda i, b, f: httpx.Response(200, json={**envelope(b, mock_output(f)), 'choices': [{
        'finish_reason': 'length', 'message': {'role': 'assistant', 'content': '{"low":'}}]})),
])
def test_any_terminal_output_failure_ends_the_attempt_without_retry_repair_or_resume(
        approved, tmp_path, monkeypatch, label, reply):
    fixtures = [f for _, f, _, _ in s.plan(approved)]

    def respond(index, body):
        return reply(index, body, fixtures[index]) if index == 6 else None
    path = tmp_path / 'attempt-01'
    result, bodies = run_collect(approved, path, monkeypatch, respond)
    assert len(bodies) == 7, label
    assert result['status'] == 'INCOMPLETE' and len(result['calls']) == 7
    assert result['failure_kind'] == 'OUTPUT_CONTRACT_FAILURE'
    assert 'STOP FOR RESEARCHER DECISION' in result['failure_reason']
    assert 'no further B0 suffix attempt is allowed' in result['failure_reason']
    failed = result['calls'][6]
    assert failed['status'] == 'FAIL' and len(failed['attempts']) == 1
    assert len(list((path / 'outputs').rglob('*.json'))) == 7
    assert (path / 'collection.json').is_file() and (path / 'SHA256SUMS').is_file()
    with pytest.raises(ValueError, match='complete suffix attempt'):
        s.official_calls(path)
    with pytest.raises(ValueError):
        s.histories_from_calls(cal.read_calls(path), approved)
    with pytest.raises(FileExistsError):
        run_collect(approved, path, monkeypatch)


def test_only_frozen_infrastructure_retries_repeat_a_suffix_request(approved, tmp_path, monkeypatch):
    seen = []

    def transient(index, body):
        if index == 3 and not seen:
            seen.append(index)
            return httpx.Response(503, json={'error': {'message': 'unavailable'}})
    result, bodies = run_collect(approved, tmp_path / 'a', monkeypatch, transient)
    assert result['status'] == 'COMPLETE' and len(bodies) == 25 and len(result['calls'][3]['attempts']) == 2

    def exhausted(index, body):
        if index == 3:
            return httpx.Response(503, json={'error': {'message': 'unavailable'}})
    result, bodies = run_collect(approved, tmp_path / 'b', monkeypatch, exhausted)
    assert result['status'] == 'INCOMPLETE' and len(bodies) == 6 and len(result['calls'][3]['attempts']) == 3
    assert result['failure_kind'] == 'INFRASTRUCTURE_OR_API_ERROR' and 'STOP FOR RESEARCHER DECISION' in result['failure_reason']


def test_semantic_findings_do_not_stop_later_scheduled_calls(approved, tmp_path, monkeypatch):
    fixtures = [f for _, f, _, _ in s.plan(approved)]

    def respond(index, body):
        if index == 2:
            return httpx.Response(200, json=envelope(body, mock_output(fixtures[index], lambda o: o['low'].update(
                U7='The value was updated.', N2=f'Also {fixtures[index]["reference"]["gold_current_value"]}.'))))
    result, bodies = run_collect(approved, tmp_path / 'attempt-01', monkeypatch, respond)
    assert result['status'] == 'COMPLETE' and len(bodies) == 24 and len(result['calls']) == 24
    findings = result['calls'][2]['automated']
    assert findings['status'] == 'LEVEL1_FINDINGS'
    low = findings['checks']['low']
    assert low['U7'] == {'entity_fidelity': 'FAIL', 'current_value_fidelity': 'FAIL', 'no_superseded_value': 'PASS'}
    assert low['N2']['current_value_fidelity'] == 'FAIL' and low['N2']['no_historical_or_superseded_value'] == 'FAIL'
    assert all(c['automated']['status'] == 'PASS' for i, c in enumerate(result['calls']) if i != 2)
    assert 'failure_reason' in result and result['failure_reason'] is None


def test_refusals_leave_no_side_effect(approved, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)

    def refuse(inputs, message, git=fake_git, key='test-secret'):
        path = tmp_path / message.replace(' ', '-')
        monkeypatch.setattr(cal, 'git', git)
        with pytest.raises(ValueError, match=message):
            asyncio.run(s.collect(inputs, key, path, client_factory=lambda **k: pytest.fail('No client')))
        assert not path.exists()
    refuse(approved, 'OPENROUTER_API_KEY', key=' ')
    refuse(approved, 'clean worktree', git=lambda *a: b' M x' if a[:1] == ('status',) else b'x')
    proposed = deepcopy(approved)
    proposed['config']['attempt_policy']['status'] = 'PROPOSED_PENDING_RESEARCHER_APPROVAL'
    refuse(proposed, 'not fully approved')
    unapproved_rule = deepcopy(approved)
    unapproved_rule['config']['collection_rule']['status'] = 'PROPOSED_PENDING_RESEARCHER_APPROVAL'
    refuse(unapproved_rule, 'not fully approved')
    monkeypatch.setattr(q, 'implementation', lambda protocol='v1': {'status': q.NOT_FROZEN, 'freeze_commit': None})
    refuse(approved, q.NOT_FROZEN)


def test_an_incomplete_full_history_procedure_or_missing_closure_blocks_the_suffix_run(approved, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)
    real = cal.verify_predecessors
    monkeypatch.setattr(cal, 'verify_predecessors', lambda i, root=ROOT: real(i, root=tmp_path / 'empty'))
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='Missing closure'):
        asyncio.run(s.collect(approved, 'test-secret', path, client_factory=lambda **k: pytest.fail('No client')))
    assert not path.exists()
    open_procedure = deepcopy(approved)
    open_procedure['design']['design']['naturalization']['status'] = 'AWAITING_COMPLETE_ATTEMPT'
    with pytest.raises(ValueError, match='must be closed'):
        s.verify_old_procedure_closed(open_procedure)


# --- Old outputs are never read or mixed -----------------------------------------------------------

def test_old_outputs_are_never_read_into_the_suffix_collection_or_derivation(approved, tmp_path, monkeypatch):
    opened = []
    for name in ('read_text', 'read_bytes'):
        original = getattr(Path, name)

        def spy(self, *args, _original=original, **kwargs):
            opened.append(str(self))
            return _original(self, *args, **kwargs)
        monkeypatch.setattr(Path, name, spy)
    path = tmp_path / 'attempt-01'
    run_collect(approved, path, monkeypatch)
    s.derive_budget(path, completed_audit(path, approved), TOKENIZER, approved, SYSTEM)
    old = [p for p in opened if '/results/b0-calibration/attempt-0' in p]
    assert not [p for p in old if '/outputs/' in p]
    assert {Path(p).name for p in old} <= {'collection.json', 'SHA256SUMS'}


def test_old_attempt_records_cannot_supply_suffix_histories(approved, tmp_path, monkeypatch):
    for directory in OLD_ATTEMPTS:
        with pytest.raises(ValueError):
            s.official_calls(directory)
        with pytest.raises(ValueError, match='one suffix attempt'):
            s.histories_from_calls(cal.read_calls(directory), approved)
    run_collect(approved, tmp_path / 'attempt-01', monkeypatch)
    fresh = s.official_calls(tmp_path / 'attempt-01')
    assert len(s.histories_from_calls(fresh, approved)) == 72
    old = cal.read_calls(OLD_ATTEMPTS[0])
    with pytest.raises(ValueError, match='one suffix attempt'):
        s.histories_from_calls(old[:12] + fresh[12:], approved)
    other = [{**c, 'attempt': 'attempt-02'} for c in fresh[:12]] + fresh[12:]
    with pytest.raises(ValueError, match='one suffix attempt'):
        s.histories_from_calls(other, approved)
    relabeled = [{k: v for k, v in c.items() if k != 'procedure_version'} for c in fresh]
    with pytest.raises(ValueError, match='one suffix attempt'):
        s.histories_from_calls(relabeled, approved)
    with pytest.raises(ValueError):
        s.histories_from_calls(fresh[:-1], approved)


def test_collect_refuses_a_closed_namespace_or_unplanned_directory_before_any_side_effect(approved, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)
    for name, message in (('results/b0-calibration/attempt-03', 'immutable'),
                          ('results/b0-calibration/attempt-02', 'immutable'),
                          ('results/b0-suffix-calibration/attempt-02', 'planned attempt directory'),
                          ('results/b0-suffix-calibration/closure', 'planned attempt directory')):
        target = ROOT / name
        existed = target.exists()
        with pytest.raises(ValueError, match=message):
            asyncio.run(s.collect(approved, 'test-secret', target, client_factory=lambda **k: pytest.fail('No client')))
        assert target.exists() == existed


def test_collect_refuses_when_inputs_change_after_preflight(approved, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)
    real, calls = s.provenance, []
    monkeypatch.setattr(s, 'provenance', lambda i: {**real(i), 'python': f'changed-{len(calls.append(1) or calls)}'})
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='changed since preflight'):
        asyncio.run(s.collect(approved, 'test-secret', path, client_factory=lambda **k: pytest.fail('No client')))
    assert not path.exists()


def test_suffix_load_fails_when_the_qualification_contract_drifts(monkeypatch):
    real = probe.file_hash
    monkeypatch.setattr(probe, 'file_hash', lambda p: '0' * 64 if str(p).endswith('generator-naturalization-contract.json') else real(p))
    with pytest.raises(ValueError, match='contract drift'):
        s.load_inputs()


# --- Frozen prompt ---------------------------------------------------------------------------------

PROMPT_SHA256 = '841dd95d7e535f1001e5bcab2f0905562f4140d76a956891487fcdccca33eb03'
CONTRACT_SHA256 = '7138d078f114ea4d5df0743c770c2c84ee409b1322cf2c658cc0e0be495719db'
PLAN_SHA256 = 'd9b7d7f06ab20b38c2bc1ace39b089434320f81cfa9c43a5b8a42b513b801526'
PRE_AMENDMENT_PROMPT_SHA256 = '0dcae47eb1294c67f753abbd234e7862cc41a3224e54fd82210e7dd9d2e7fb35'
PRE_AMENDMENT_PLAN_SHA256 = '9f0045ab5387ba5563398b039f398c94471442570b95f3bdcac03eec28b2f9f8'
OLD_SENTENCE = 'N2 concerns a different attribute than U7 and must not repeat U7.'
NEW_SENTENCE = ('N2 concerns the dedicated N2 state supplied in the input. '
                'It must not repeat, revise, or otherwise alter U7.')


def test_the_final_prompt_is_frozen_byte_for_byte(inputs):
    prompt = inputs['contract']['prompt']
    assert probe.digest(prompt.encode('utf-8')) == PROMPT_SHA256 == inputs['config']['contract']['prompt_sha256']
    assert probe.file_hash(CONTRACT) == CONTRACT_SHA256 == inputs['config']['contract']['sha256']
    assert prompt.count(NEW_SENTENCE) == 1 and OLD_SENTENCE not in prompt
    assert 'different attribute' not in CONTRACT.read_text(encoding='utf-8')
    assert prompt.split('\n\n')[5].endswith(' ' + NEW_SENTENCE)
    assert probe.digest(prompt.replace(NEW_SENTENCE, OLD_SENTENCE).encode('utf-8')) == PRE_AMENDMENT_PROMPT_SHA256


def test_the_prompt_amendment_changes_only_the_prompt_derived_hashes(inputs):
    assert inputs['config']['plan']['plan_sha256'] == PLAN_SHA256
    previous = deepcopy(inputs)
    previous['contract']['prompt'] = inputs['contract']['prompt'].replace(NEW_SENTENCE, OLD_SENTENCE)
    previous['config']['contract']['prompt_sha256'] = PRE_AMENDMENT_PROMPT_SHA256
    assert gq.sha(gq.canonical(s.plan_identity(previous))) == PRE_AMENDMENT_PLAN_SHA256
    now, then = s.plan_identity(inputs), s.plan_identity(previous)
    assert all(a != b for a, b in zip(now['request_sha256'], then['request_sha256']))
    assert {k: v for k, v in now.items() if k not in ('prompt_sha256', 'request_sha256')} == {
        k: v for k, v in then.items() if k not in ('prompt_sha256', 'request_sha256')}
    contract = inputs['config']['contract']
    assert (contract['input_schema_sha256'], contract['output_schema_sha256']) == (
        '23c0783af2c07e3b0869980e67a5d71e3311bcba8b3554ef404cd94122596d99',
        'cee7b2f73bb02fed193ad5fd7da170adf9f55d55a13d9db805feba4117f32064')
    assert inputs['config']['input_projection']['set_sha256'] == (
        '0afea6fe046877983a77c57f4af0d1665e514fe20f758a760b38f445cb361a66')


# --- Semantic eligibility --------------------------------------------------------------------------

@pytest.fixture(scope='module')
def collected(approved, tmp_path_factory):
    path = tmp_path_factory.mktemp('collected') / 'attempt-01'
    with pytest.MonkeyPatch.context() as patch:
        result, _ = run_collect(approved, path, patch)
    assert result['status'] == 'COMPLETE'
    return path


def test_level1_check_registry_matches_the_frozen_rule(inputs):
    assert inputs['config']['semantic_eligibility']['level1_checks'] == s.LEVEL1
    for event, checks in s.LEVEL1.items():
        assert len(checks) == 7 and set(checks.values()) == {'automated', 'manual'}
        assert sum(kind == 'manual' for kind in checks.values()) == 4
        assert {'entity_fidelity', 'attribute_fidelity', 'current_value_fidelity', 'comprehensibility'} <= set(checks)
    assert {'changed_state_semantics', 'no_superseded_value', 'no_invented_value_or_change'} <= set(s.LEVEL1['U7'])
    assert {'same_state_semantics', 'no_invented_change', 'no_historical_or_superseded_value'} <= set(s.LEVEL1['N2'])


def test_level1_registry_drift_in_the_config_is_rejected(config_copy):
    for mutate in (lambda c: c['semantic_eligibility']['level1_checks']['U7'].pop('comprehensibility'),
                   lambda c: c['semantic_eligibility']['level1_checks']['N2'].update(entity_fidelity='manual'),
                   lambda c: c['semantic_eligibility']['level1_checks']['N2'].update(extra_check='manual')):
        with pytest.raises(ValueError, match='registry drift'):
            s.load_config(config_copy(mutate))


def test_blank_audit_covers_all_144_items_and_is_bound_to_the_archived_evidence(collected, approved):
    audit = s.audit_template(collected, approved)
    assert audit == s.audit_template(collected, approved)
    assert (audit['schema_version'], audit['attempt'], audit['procedure_version']) == (
        'b0-suffix-audit/1.0.0', 'attempt-01', s.COLLECTION)
    assert audit['collection_sha256'] == probe.file_hash(collected / 'collection.json')
    assert (audit['reviewer'], audit['reviewed_at'], audit['notes']) == ('', '', '')
    items = audit['items']
    assert len(items) == 144 and len({k.rsplit('/', 1)[0] for k in items}) == 72
    for item, entry in items.items():
        generator, scenario, variant, event = item.split('/')
        assert generator in ('G1', 'G2') and variant in gq.VARIANTS and event in ('U7', 'N2')
        assert set(entry['automated']) == {c for c, kind in s.LEVEL1[event].items() if kind == 'automated'}
        assert entry['manual'] == {c: None for c, kind in s.LEVEL1[event].items() if kind == 'manual'}
        assert entry['fluency'] is None and entry['text_sha256'] == probe.digest(entry['text'].encode('utf-8'))
        assert set(entry['automated'].values()) == {'PASS'}


def test_a_complete_clean_audit_makes_the_collection_eligible(collected, approved):
    verdict = s.adjudicate(collected, completed_audit(collected, approved), approved)
    assert verdict['status'] == 'ELIGIBLE' and verdict['budget_derivation'] == 'ALLOWED'
    assert verdict['level1_failures'] == [] and verdict['items_audited'] == 144
    assert verdict['b0_context_tokens'] is None
    assert len(s.eligible_histories(collected, completed_audit(collected, approved), approved)) == 72


def test_fluency_only_findings_do_not_block_eligibility_or_derivation(collected, approved):
    items = list(s.audit_template(collected, approved)['items'])
    marked = completed_audit(collected, approved, fluency_fail=set(items[::3]))
    verdict = s.adjudicate(collected, marked, approved)
    assert verdict['status'] == 'ELIGIBLE' and verdict['fluency_findings'] == len(items[::3])
    assert verdict['level1_failures'] == []
    assert 'not used for eligibility or ranking' in verdict['fluency_use']
    assert not [k for k in verdict if 'generator' in k.lower() or 'rank' in k.lower()]
    result = s.derive_budget(collected, marked, TOKENIZER, approved, SYSTEM)
    assert result['b0_context_tokens'] == result['maximum'] > 0


@pytest.mark.parametrize('event,check', [(e, c) for e, checks in s.LEVEL1.items() for c, kind in checks.items()
                                         if kind == 'manual'])
def test_any_manual_level1_failure_makes_the_collection_ineligible_and_blocks_derivation(
        collected, approved, event, check):
    item = f'G2/b0cal-travel-01/medium/{event}'
    audit = completed_audit(collected, approved, manual_fail=[(item, check)])
    verdict = s.adjudicate(collected, audit, approved)
    assert verdict['status'] == 'COMPLETE_BUT_INELIGIBLE' and verdict['budget_derivation'] == 'PROHIBITED'
    assert verdict['level1_failures'] == [{'item': item, 'check': check, 'source': 'manual'}]
    assert verdict['b0_context_tokens'] is None
    with pytest.raises(ValueError, match='COMPLETE_BUT_INELIGIBLE'):
        s.derive_budget(collected, audit, TOKENIZER, approved, SYSTEM)
    with pytest.raises(ValueError, match='COMPLETE_BUT_INELIGIBLE'):
        s.eligible_histories(collected, audit, approved)


def test_a_deterministic_level1_failure_blocks_derivation_but_not_the_collection(approved, tmp_path, monkeypatch):
    fixtures = [f for _, f, _, _ in s.plan(approved)]

    def respond(index, body):
        if index == 5:
            return httpx.Response(200, json=envelope(body, mock_output(fixtures[index], lambda o: o['high'].update(
                U7='The plan was updated.'))))
    path = tmp_path / 'attempt-01'
    result, bodies = run_collect(approved, path, monkeypatch, respond)
    assert result['status'] == 'COMPLETE' and len(bodies) == 24
    assert result['calls'][5]['automated']['status'] == 'LEVEL1_FINDINGS'
    audit = completed_audit(path, approved)
    verdict = s.adjudicate(path, audit, approved)
    assert verdict['status'] == 'COMPLETE_BUT_INELIGIBLE' and verdict['b0_context_tokens'] is None
    assert {(f['check'], f['source']) for f in verdict['level1_failures']} == {
        ('entity_fidelity', 'automated'), ('current_value_fidelity', 'automated')}
    assert all(f['item'].endswith('/high/U7') for f in verdict['level1_failures'])
    with pytest.raises(ValueError, match='COMPLETE_BUT_INELIGIBLE'):
        s.derive_budget(path, audit, TOKENIZER, approved, SYSTEM)
    assert json.loads((path / 'collection.json').read_text(encoding='utf-8'))['status'] == 'COMPLETE'


@pytest.mark.parametrize('label,mutate,message', [
    ('null manual cell', lambda a: a['items']['G1/b0cal-scheduling-01/low/U7']['manual'].update(comprehensibility=None), 'incomplete'),
    ('invalid mark', lambda a: a['items']['G1/b0cal-scheduling-01/low/N2']['manual'].update(attribute_fidelity='MAYBE'), 'incomplete'),
    ('no reviewer', lambda a: a.update(reviewer=' '), 'reviewer'),
    ('no timestamp', lambda a: a.update(reviewed_at='yesterday'), 'reviewer'),
    ('edited text', lambda a: a['items']['G1/b0cal-scheduling-01/low/U7'].update(text='edited'), 'archived evidence'),
    ('flipped automated result', lambda a: a['items']['G1/b0cal-scheduling-01/low/U7']['automated'].update(entity_fidelity='FAIL'), 'archived evidence'),
    ('missing manual key', lambda a: a['items']['G1/b0cal-scheduling-01/low/U7']['manual'].pop('comprehensibility'), 'archived evidence'),
    ('dropped item', lambda a: a['items'].pop('G2/b0cal-quantitative-planning-01/high/N2'), 'Audit items'),
    ('other collection', lambda a: a.update(collection_sha256='0' * 64), 'collection_sha256'),
    ('other attempt', lambda a: a.update(attempt='attempt-02'), 'attempt'),
    ('extra field', lambda a: a.update(extra='x'), 'Audit fields'),
    ('bad fluency mark', lambda a: a['items']['G1/b0cal-scheduling-01/low/U7'].update(fluency='BAD'), 'fluency'),
])
def test_an_incomplete_or_altered_audit_refuses_adjudication_and_derivation(
        collected, approved, label, mutate, message):
    audit = completed_audit(collected, approved, mutate=mutate)
    with pytest.raises(ValueError, match=message):
        s.adjudicate(collected, audit, approved)
    with pytest.raises(ValueError, match=message):
        s.derive_budget(collected, audit, TOKENIZER, approved, SYSTEM)


def test_the_blank_audit_and_an_incomplete_collection_can_never_derive_a_budget(collected, approved, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='reviewer'):
        s.derive_budget(collected, s.audit_template(collected, approved), TOKENIZER, approved, SYSTEM)
    fixtures = [f for _, f, _, _ in s.plan(approved)]
    path = tmp_path / 'attempt-01'
    result, _ = run_collect(approved, path, monkeypatch, lambda i, b: httpx.Response(200, json=envelope(
        b, mock_output(fixtures[i], lambda o: o['low'].update(U7='')))) if i == 4 else None)
    assert result['status'] == 'INCOMPLETE'
    with pytest.raises(ValueError, match='complete suffix attempt'):
        s.audit_template(path, approved)
    with pytest.raises(ValueError, match='complete suffix attempt'):
        s.derive_budget(path, completed_audit(collected, approved), TOKENIZER, approved, SYSTEM)


def test_audit_operations_run_offline_through_the_cli(collected, approved, tmp_path, capsys):
    blank = tmp_path / 'blank.json'
    assert s.main(['--audit-template', str(collected), '--template-output', str(blank)]) == 0
    assert json.loads(blank.read_text(encoding='utf-8')) == s.audit_template(collected, approved)
    with pytest.raises(FileExistsError):
        s.main(['--audit-template', str(collected), '--template-output', str(blank)])
    completed = tmp_path / 'completed.json'
    completed.write_text(json.dumps(completed_audit(collected, approved)), encoding='utf-8')
    adjudication = tmp_path / 'adjudication.json'
    assert s.main(['--adjudicate', str(collected), '--audit', str(completed),
                   '--adjudication-output', str(adjudication)]) == 0
    verdict = json.loads(adjudication.read_text(encoding='utf-8'))
    assert verdict['status'] == 'ELIGIBLE' and verdict['audit_file_sha256'] == probe.file_hash(completed)
    assert 'ELIGIBLE' in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        s.main(['--adjudicate', str(collected), '--audit', str(completed), '--adjudication-output', str(adjudication)])
    failed = json.loads(completed.read_text(encoding='utf-8'))
    failed['items']['G1/b0cal-scheduling-01/low/U7']['manual']['comprehensibility'] = 'FAIL'
    (tmp_path / 'failed.json').write_text(json.dumps(failed), encoding='utf-8')
    assert s.main(['--adjudicate', str(collected), '--audit', str(tmp_path / 'failed.json'),
                   '--adjudication-output', str(tmp_path / 'ineligible.json')]) == 0
    ineligible = json.loads((tmp_path / 'ineligible.json').read_text(encoding='utf-8'))
    assert ineligible['status'] == 'COMPLETE_BUT_INELIGIBLE' and ineligible['b0_context_tokens'] is None
    with pytest.raises(ValueError, match='outside the attempt'):
        s.main(['--audit-template', str(collected), '--template-output', str(collected / 'blank.json')])
    for flags in (['--audit-template', str(collected)], ['--template-output', str(blank)],
                  ['--adjudicate', str(collected)], ['--adjudicate', str(collected), '--audit', str(completed)],
                  ['--audit-template', str(collected), '--template-output', str(tmp_path / 'x'), '--adjudicate',
                   str(collected)],
                  ['--audit-template', str(collected), '--template-output', str(tmp_path / 'y'), '--execute',
                   '--confirm-spend']):
        with pytest.raises(SystemExit):
            s.main(flags)
