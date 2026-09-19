"""Offline tests for the closed B0 suffix calibration: frozen budget, lifecycle and derivation binding."""
import asyncio
import json
from pathlib import Path
import socket
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import calibrate_b0 as cal
import calibrate_b0_suffix as s
import probe_generators as probe
from test_b0_calibration import fake_git
from test_b0_suffix import config_copy  # noqa: F401

REAL = ROOT / 'results/b0-suffix-calibration'
DERIVATION = REAL / 'derivation/attempt-01.json'
DERIVATION_SHA256 = '70ed6e326e82378f8f4ab0a4e88cf639a21f7da58cf255c9c693cf24eb4ed365'


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
def artifact():
    return json.loads(DERIVATION.read_text(encoding='utf-8'))


# --- Final state -----------------------------------------------------------------------------------

def test_the_budget_is_frozen_at_71_and_the_calibration_is_closed(inputs):
    config = inputs['config']
    assert (config['calibration_status'], config['budget_status'], config['b0_context_tokens']) == (
        'CLOSED', 'FROZEN', 71)
    assert config['status'] == 'PROCEDURE_FROZEN' and config['attempt_policy'] == {
        'status': 'FROZEN', 'cap': 1, 'policy': config['attempt_policy']['policy']}


def test_the_attempt_lifecycle_records_the_completed_eligible_derived_collection(inputs):
    attempts = inputs['config']['results']['attempts']
    assert len(attempts) == 1 and attempts[0]['id'] == 'attempt-01'
    attempt = attempts[0]
    assert attempt['status'] == 'COMPLETE' and 'PLANNED_NOT_EXECUTED' not in json.dumps(inputs['config']['results'])
    assert (attempt['calls_recorded'], attempt['histories'], attempt['derivation_status']) == (24, 72, 'DERIVED')
    assert attempt['adjudication']['status'] == 'ELIGIBLE' and attempt['adjudication']['level1_failures'] == 0
    assert (attempt['adjudication']['items_audited'], attempt['adjudication']['fluency_findings']) == (144, 2)
    collection = json.loads((REAL / 'attempt-01/collection.json').read_text(encoding='utf-8'))
    assert collection['status'] == 'COMPLETE' and len(collection['calls']) == 24 == collection['planned_logical_calls']
    assert collection['expected_histories'] == 72
    for path, recorded in ((REAL / 'attempt-01/collection.json', attempt['collection_sha256']),
                           (ROOT / attempt['audit']['path'], attempt['audit']['sha256']),
                           (ROOT / attempt['adjudication']['path'], attempt['adjudication']['sha256'])):
        assert probe.file_hash(path) == recorded


# --- Derivation binding ----------------------------------------------------------------------------

def test_the_derivation_artifact_is_immutable_and_bound_to_the_frozen_budget(inputs, artifact):
    binding = inputs['config']['budget_derivation']
    assert probe.file_hash(DERIVATION) == DERIVATION_SHA256 == binding['sha256']
    assert binding == {'artifact': 'results/b0-suffix-calibration/derivation/attempt-01.json',
                       'sha256': DERIVATION_SHA256, 'attempt': 'attempt-01'}
    verified = s.verify_frozen_budget(inputs['config'], inputs['design'])
    assert verified == artifact
    assert (artifact['status'], artifact['schema_version'], artifact['procedure_version'], artifact['attempt']) == (
        'DERIVED', 'b0-suffix-budget-derivation/1.0.0', 'b0-suffix-collection/1.0.0', 'attempt-01')
    assert artifact['b0_context_tokens'] == inputs['config']['b0_context_tokens'] == 71
    assert artifact['histories'] == {'eligible': 72, 'retained_at_maximum': 72}
    assert artifact['retention'] == {'histories': 72, 'retained': 72, 'fraction': 1.0}
    assert [(r['generator'], r['scenario'], r['variant'], r['required_tokens']) for r in artifact['determined_by']] == [
        ('G2', 'b0cal-travel-01', 'high', 71), ('G2', 'b0cal-purchase-order-01', 'medium', 71)]
    assert max(r['required_tokens'] for r in artifact['per_history']) == 71 and len(artifact['per_history']) == 72
    assert artifact['source'] == {
        'collection_sha256': '39d8c7ac1297a2fd432d956657b32f318dfc62846dc28c3722c31a562203735b',
        'audit_sha256': 'bb2084058e15f643b3f7a347e9d50a1dbc106be7903f96456e374bf7125a7377',
        'adjudication_sha256': '92230d273941317de0298eb08ca3c3c4b1ac679f367cf2eb7065d7b76a3eaa12',
        'adjudication_status': 'ELIGIBLE'}


def test_the_rule_and_tokenizer_are_the_frozen_ones(inputs, artifact):
    design = inputs['design']['design']
    assert design['calibration']['budget'] == {
        'rule': 'exact_maximum', 'statistic': design['calibration']['budget']['statistic'],
        'headroom_tokens': 0, 'candidate_grid': 'none'}
    assert design['calibration']['retention'] == {'requirement': 'all_histories', 'fraction': 1.0,
                                                  'percentile_rule': 'none'}
    assert artifact['rule'] == {'name': 'exact_maximum', 'statistic': design['calibration']['budget']['statistic'],
                                'percentile_rule': 'none', 'candidate_grid': 'none', 'headroom_tokens': 0,
                                'required_retention_fraction': 1.0}
    reader = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']
    assert (reader['repository_id'], reader['revision']) == (
        'meta-llama/Llama-3.1-8B-Instruct', '0e9e39f249a16976918f6564b8830bc894c89659')
    assert (artifact['tokenizer']['repository_id'], artifact['tokenizer']['revision']) == (
        reader['repository_id'], reader['revision'])
    assert artifact['tokenizer']['artifact_sha256'] == reader['artifact_sha256']
    assert design['window_contract']['required_events'] == ['U7', 'N2'] == artifact['design']['window_contract']['required_events']
    assert artifact['design']['system_prompt_sha256'] == '8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e'
    assert artifact['design']['plan_sha256'] == inputs['config']['plan']['plan_sha256']
    assert design['budget_status'] == 'OPEN' and design['b0_context_tokens'] is None
    assert design['naturalization']['status'] == 'CLOSED_NO_ELIGIBLE_SET'


# --- The frozen state cannot drift -----------------------------------------------------------------

@pytest.mark.parametrize('label,mutate,message', [
    ('other budget', lambda c: c.update(b0_context_tokens=70), 'disagrees with its derivation artifact'),
    ('higher budget', lambda c: c.update(b0_context_tokens=72), 'disagrees with its derivation artifact'),
    ('zero budget', lambda c: c.update(b0_context_tokens=0), 'closed calibration'),
    ('text budget', lambda c: c.update(b0_context_tokens='71'), 'closed calibration'),
    ('artifact hash', lambda c: c['budget_derivation'].update(sha256='0' * 64), 'artifact drifted'),
    ('artifact attempt', lambda c: c['budget_derivation'].update(attempt='attempt-02'), 'closed calibration'),
    ('collection hash', lambda c: c['results']['attempts'][0].update(collection_sha256='0' * 64), 'evidence drifted'),
    ('audit hash', lambda c: c['results']['attempts'][0]['audit'].update(sha256='0' * 64), 'evidence drifted'),
    ('adjudication hash', lambda c: c['results']['attempts'][0]['adjudication'].update(sha256='0' * 64), 'evidence drifted'),
    ('histories', lambda c: c['results']['attempts'][0].update(histories=71), 'disagrees with its derivation artifact'),
    ('planned again', lambda c: c['results']['attempts'][0].update(status='PLANNED_NOT_EXECUTED'), 'closed calibration'),
    ('not derived', lambda c: c['results']['attempts'][0].update(derivation_status='PENDING'), 'closed calibration'),
    ('open calibration', lambda c: c.update(calibration_status='OPEN'), 'closed calibration'),
    ('reopened budget', lambda c: c.update(budget_status='OPEN'), 'set only by the official calibration run'),
    ('no derivation', lambda c: c.pop('budget_derivation'), 'closed calibration|budget_derivation'),
])
def test_a_drifted_frozen_state_is_refused(config_copy, label, mutate, message):
    with pytest.raises((ValueError, KeyError), match=message):
        s.load_inputs(config_copy(mutate, frozen=True))
    s.load_inputs(config_copy(None, frozen=True))


def test_a_modified_derivation_artifact_is_refused_even_with_a_matching_hash(config_copy, artifact, tmp_path):
    def point_at(mutate):
        changed = json.loads(json.dumps(artifact))
        mutate(changed)
        path = tmp_path / f'derivation-{len(list(tmp_path.iterdir()))}.json'
        path.write_text(json.dumps(changed, indent=2) + '\n', encoding='utf-8')
        return config_copy(lambda c: c['budget_derivation'].update(artifact=str(path), sha256=probe.file_hash(path)),
                           frozen=True)
    for mutate in (lambda a: a.update(b0_context_tokens=70), lambda a: a.update(status='PENDING'),
                   lambda a: a['rule'].update(headroom_tokens=1), lambda a: a['rule'].update(percentile_rule='p95'),
                   lambda a: a['rule'].update(candidate_grid='[60, 70, 80]'),
                   lambda a: a['tokenizer'].update(revision='0' * 40),
                   lambda a: a['source'].update(audit_sha256='0' * 64),
                   lambda a: a['determined_by'].pop(), lambda a: a['per_history'].pop(),
                   lambda a: a['per_history'][0].update(required_tokens=99)):
        with pytest.raises(ValueError):
            s.load_inputs(point_at(mutate))


# --- No further attempt, derivation or execution ---------------------------------------------------

def test_no_second_suffix_attempt_or_execution_is_allowed(inputs, config_copy, tmp_path, monkeypatch):
    config = inputs['config']
    for check in (s.official_attempt, s.require_official):
        with pytest.raises(ValueError, match='closed and its budget is frozen'):
            check(config)
    extra = {'id': 'attempt-02', 'status': 'PLANNED_NOT_EXECUTED',
             'result_directory': 'results/b0-suffix-calibration/attempt-02'}
    with pytest.raises(ValueError, match='exactly one attempt'):
        s.load_inputs(config_copy(lambda c: c['results']['attempts'].append(extra), frozen=True))
    monkeypatch.setattr(cal, 'git', fake_git)
    target = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='closed and its budget is frozen'):
        asyncio.run(s.collect(inputs, 'test-secret', target, client_factory=lambda **k: pytest.fail('No client')))
    assert not target.exists()
    for name in ('attempt-01', 'attempt-02'):
        official = REAL / name
        existed = official.exists()
        with pytest.raises(ValueError, match='closed and its budget is frozen'):
            s.main(['--execute', '--confirm-spend', '--output-directory', str(official)])
        assert official.exists() == existed


def test_the_budget_cannot_be_derived_again(inputs, tmp_path, monkeypatch):
    def forbidden(directory=None):
        pytest.fail('The tokenizer must not be loaded once the budget is frozen')
    monkeypatch.setattr(s, 'load_reader_tokenizer', forbidden)
    out = tmp_path / 'again.json'
    with pytest.raises(ValueError, match='closed and its budget is frozen'):
        s.main(['--derive-budget', str(REAL / 'attempt-01'),
                '--audit', str(REAL / 'manual-audit/attempt-01.completed.json'),
                '--adjudication', str(REAL / 'manual-audit/attempt-01.adjudication.json'), '--budget-output', str(out)])
    assert not out.exists() and probe.file_hash(DERIVATION) == DERIVATION_SHA256


def test_preview_and_loader_are_consistent_with_a_closed_calibration(inputs, capsys):
    shown = s.preview(inputs)
    assert (shown['calibration_status'], shown['budget_status'], shown['b0_context_tokens']) == ('CLOSED', 'FROZEN', 71)
    assert (shown['attempt'], shown['attempt_status'], shown['suffix_collection_status']) == (
        'attempt-01', 'COMPLETE', 'COMPLETE')
    assert shown['planned_logical_calls'] == 24 and shown['expected_histories'] == 72
    assert shown['per_generator'] == {'G1': 12, 'G2': 12} and len(set(shown['request_hashes'])) == 24
    assert s.main([]) == 0
    assert json.loads(capsys.readouterr().out)['b0_context_tokens'] == 71
    assert s.verify_old_procedure_closed(inputs) == cal.verify_predecessors(cal.load_inputs())
