"""Offline tests for the final B0 suffix budget derivation CLI; no model, tokenizer download or network call."""
from copy import deepcopy
import inspect
import json
from pathlib import Path
import shutil
import socket
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import b0_window as window
import calibrate_b0 as cal
import calibrate_b0_suffix as s
import probe_generators as probe
from test_b0_calibration import SYSTEM, TOKENIZER
from test_b0_suffix import approved, collected, completed_audit, config_copy, mock_output, run_collect  # noqa: F401

STAGED_READER = Path('/tmp/retrieval-implementation-identity/reader')
REAL = ROOT / 'results/b0-suffix-calibration'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)


CONFIG = {}


@pytest.fixture(scope='module', autouse=True)
def prefreeze_config(approved):
    """These tests run the derivation from the pre-closure config; the frozen real config refuses it."""
    CONFIG['path'] = approved['path']


def adjudicated(directory, inputs, tmp_path, name, **audit_options):
    audit = tmp_path / f'{name}-audit.json'
    audit.write_text(json.dumps(completed_audit(directory, inputs, **audit_options)), encoding='utf-8')
    adjudication = tmp_path / f'{name}-adjudication.json'
    assert s.main(['--config', str(CONFIG['path']), '--adjudicate', str(directory), '--audit', str(audit),
                   '--adjudication-output', str(adjudication)]) == 0
    return audit, adjudication


@pytest.fixture(scope='module')
def evidence(collected, approved, tmp_path_factory):
    return adjudicated(collected, approved, tmp_path_factory.mktemp('evidence'), 'clean')


@pytest.fixture
def toy_tokenizer(monkeypatch, approved):
    frozen = approved['design']['design']['tokenizer']
    calls = []

    def loader(directory=None):
        calls.append(directory)
        return TOKENIZER, {'repository_id': frozen['repository_id'], 'revision': frozen['revision'],
                           'source': 'test', 'artifact_sha256': {}}
    monkeypatch.setattr(s, 'load_reader_tokenizer', loader)
    return calls


def derive_args(directory, audit, adjudication, output, *extra):
    return ['--config', str(CONFIG['path']), '--derive-budget', str(directory), '--audit', str(audit),
            '--adjudication', str(adjudication), '--budget-output', str(output), *extra]


def system(inputs):
    return cal.official_system(inputs['design']['design'])


def independent(h, prompt):
    base = [{'role': 'system', 'content': prompt}]
    u7, n2 = (e['messages'][0]['content'] for e in h['exchanges'])
    turn = lambda text: [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': 'Noted.'}]
    cost = lambda messages: window.chat_tokens(base + messages, TOKENIZER) - window.chat_tokens(base, TOKENIZER)
    return max(cost(turn(u7) + turn(n2)), cost(turn(n2)))


# --- The derivation reuses the eligibility-gated derive_budget function ----------------------------

def test_the_cli_calls_the_existing_derive_budget_with_exactly_72_eligible_histories(
        collected, approved, evidence, toy_tokenizer, tmp_path, monkeypatch):
    seen = {}
    original_budget, original_derive = s.derive_budget, cal.derive

    def spy_budget(*args, **kwargs):
        seen['budget'] = (args, kwargs)
        return original_budget(*args, **kwargs)

    def spy_derive(histories, system_message, tokenizer):
        seen['derive'] = (histories, system_message, tokenizer)
        return original_derive(histories, system_message, tokenizer)
    monkeypatch.setattr(s, 'derive_budget', spy_budget)
    monkeypatch.setattr(cal, 'derive', spy_derive)
    audit, adjudication = evidence
    out = tmp_path / 'derivation' / 'attempt-01.json'
    assert s.main(derive_args(collected, audit, adjudication, out)) == 0
    (directory, given_audit, tokenizer, given_inputs), _ = seen['budget']
    assert directory == collected and given_audit == json.loads(audit.read_text(encoding='utf-8'))
    assert tokenizer is TOKENIZER and given_inputs['config']['plan']['expected_histories'] == 72
    histories, prompt, used = seen['derive']
    assert len(histories) == 72 and used is TOKENIZER and prompt == system(approved)
    assert all([e['event'] for e in h['exchanges']] == ['U7', 'N2'] for h in histories)
    source = inspect.getsource(s.derive_final_budget)
    assert 'derive_budget(' in source and 'required_budget' not in source and 'select_window' not in source


def test_the_artifact_records_the_exact_maximum_and_full_provenance(
        collected, approved, evidence, toy_tokenizer, tmp_path, capsys):
    audit, adjudication = evidence
    out = tmp_path / 'derivation' / 'attempt-01.json'
    config_before = Path(CONFIG['path']).read_bytes()
    assert s.main(derive_args(collected, audit, adjudication, out)) == 0
    artifact = json.loads(out.read_text(encoding='utf-8'))
    printed = capsys.readouterr().out
    histories = s.histories_from_calls(s.official_calls(collected), approved)
    expected = {(h['generator'], h['scenario'], h['variant']): independent(h, system(approved)) for h in histories}
    maximum = max(expected.values())
    assert (artifact['status'], artifact['schema_version'], artifact['procedure_version']) == (
        'DERIVED', 'b0-suffix-budget-derivation/1.0.0', 'b0-suffix-collection/1.0.0')
    assert artifact['attempt'] == 'attempt-01' and artifact['b0_context_tokens'] == maximum
    assert f'B0_CONTEXT_TOKENS = {maximum}' in printed and probe.file_hash(out) in printed
    assert {(r['generator'], r['scenario'], r['variant']): r['required_tokens'] for r in artifact['per_history']} == expected
    assert len(artifact['per_history']) == 72 and len(set(expected.values())) > 3
    assert artifact['determined_by'] and all(r['required_tokens'] == maximum for r in artifact['determined_by'])
    assert {(r['generator'], r['scenario'], r['variant']) for r in artifact['determined_by']} == {
        k for k, v in expected.items() if v == maximum}
    assert artifact['histories'] == {'eligible': 72, 'retained_at_maximum': 72}
    assert artifact['retention'] == {'histories': 72, 'retained': 72, 'fraction': 1.0}
    assert artifact['rule'] == {
        'name': 'exact_maximum', 'statistic': approved['design']['design']['calibration']['budget']['statistic'],
        'percentile_rule': 'none', 'candidate_grid': 'none', 'headroom_tokens': 0, 'required_retention_fraction': 1.0}
    assert artifact['source'] == {
        'collection_sha256': probe.file_hash(collected / 'collection.json'), 'audit_sha256': probe.file_hash(audit),
        'adjudication_sha256': probe.file_hash(adjudication), 'adjudication_status': 'ELIGIBLE'}
    design = artifact['design']
    assert design['system_prompt_sha256'] == '8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e'
    assert design['plan_sha256'] == approved['config']['plan']['plan_sha256']
    assert design['window_contract']['required_events'] == ['U7', 'N2'] and set(design['implementation']) == set(s.IMPLEMENTATION)
    assert Path(CONFIG['path']).read_bytes() == config_before
    assert yaml.safe_load(config_before.decode())['b0_context_tokens'] is None


def test_the_frozen_tokenizer_identity_is_recorded_and_a_different_one_is_refused(
        collected, approved, evidence, toy_tokenizer, tmp_path, monkeypatch):
    audit, adjudication = evidence
    out = tmp_path / 'a.json'
    s.main(derive_args(collected, audit, adjudication, out))
    reader = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']
    identity = json.loads(out.read_text(encoding='utf-8'))['tokenizer']
    assert (identity['repository_id'], identity['revision']) == (
        'meta-llama/Llama-3.1-8B-Instruct', '0e9e39f249a16976918f6564b8830bc894c89659')
    assert (identity['repository_id'], identity['revision']) == (reader['repository_id'], reader['revision'])
    assert approved['design']['design']['tokenizer']['revision'] == reader['revision']
    monkeypatch.setattr(s, 'load_reader_tokenizer', lambda directory=None: (TOKENIZER, {
        'repository_id': reader['repository_id'], 'revision': '0' * 40}))
    with pytest.raises(ValueError, match='differs from the frozen design'):
        s.main(derive_args(collected, audit, adjudication, tmp_path / 'b.json'))
    assert not (tmp_path / 'b.json').exists()


def test_the_reader_tokenizer_loader_verifies_the_pinned_artifacts(tmp_path):
    with pytest.raises(ValueError, match='absent'):
        s.load_reader_tokenizer(tmp_path / 'missing')
    reader = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']
    fake = tmp_path / 'fake'
    fake.mkdir()
    for name in reader['artifact_sha256']:
        (fake / name).write_text('not the pinned artifact')
    with pytest.raises(ValueError, match='Checksum mismatch'):
        s.load_reader_tokenizer(fake)


@pytest.mark.skipif(not STAGED_READER.is_dir(), reason='Pinned reader tokenizer files are not staged locally')
def test_the_real_frozen_tokenizer_is_loaded_offline_and_metadata_must_match(tmp_path):
    tokenizer, identity = s.load_reader_tokenizer()
    assert type(tokenizer).__name__ == 'PreTrainedTokenizerFast'
    assert identity['revision'] == '0e9e39f249a16976918f6564b8830bc894c89659' and identity['add_special_tokens'] is False
    reader = yaml.safe_load((ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']
    assert identity['artifact_sha256'] == reader['artifact_sha256']
    copy = tmp_path / 'reader'
    shutil.copytree(STAGED_READER, copy)
    metadata = json.loads((copy / 'repository-metadata.json').read_text(encoding='utf-8'))
    metadata['sha'] = '0' * 40
    (copy / 'repository-metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    with pytest.raises(ValueError, match='frozen repository and revision'):
        s.load_reader_tokenizer(copy)


@pytest.mark.skipif(not STAGED_READER.is_dir(), reason='Pinned reader tokenizer files are not staged locally')
def test_the_real_tokenizer_derivation_matches_an_independent_count(collected, approved, evidence, tmp_path):
    audit, adjudication = evidence
    out = tmp_path / 'real-tokenizer.json'
    assert s.main(derive_args(collected, audit, adjudication, out)) == 0
    artifact = json.loads(out.read_text(encoding='utf-8'))
    tokenizer, _ = s.load_reader_tokenizer()
    prompt = system(approved)
    base = [{'role': 'system', 'content': prompt}]
    cost = lambda messages: window.chat_tokens(base + messages, tokenizer) - window.chat_tokens(base, tokenizer)
    turn = lambda text: [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': 'Noted.'}]
    histories = s.histories_from_calls(s.official_calls(collected), approved)
    expected = max(max(cost(turn(h['exchanges'][0]['messages'][0]['content']) + turn(h['exchanges'][1]['messages'][0]['content'])),
                       cost(turn(h['exchanges'][1]['messages'][0]['content']))) for h in histories)
    assert artifact['b0_context_tokens'] == expected > 0
    assert artifact['tokenizer']['artifact_sha256'] == yaml.safe_load(
        (ROOT / 'configs/retrieval.yaml').read_text(encoding='utf-8'))['reader_tokenizer']['artifact_sha256']


# --- Provenance gate -------------------------------------------------------------------------------

def refuse(collected, audit, adjudication, out, message, extra=(), preexisting=False):
    before = Path(out).read_bytes() if preexisting else None
    with pytest.raises((ValueError, FileNotFoundError), match=message):
        s.main(derive_args(collected, audit, adjudication, out, *extra))
    assert Path(out).read_bytes() == before if preexisting else not Path(out).exists()


def test_an_ineligible_adjudication_or_audit_refuses_derivation(collected, approved, toy_tokenizer, tmp_path):
    audit, adjudication = adjudicated(collected, approved, tmp_path, 'failing', manual_fail=[
        ('G2/b0cal-travel-01/medium/U7', 'comprehensibility')])
    assert json.loads(adjudication.read_text(encoding='utf-8'))['status'] == 'COMPLETE_BUT_INELIGIBLE'
    refuse(collected, audit, adjudication, tmp_path / 'out.json', 'not an ELIGIBLE result')
    forged = json.loads(adjudication.read_text(encoding='utf-8'))
    forged.update(status='ELIGIBLE', level1_failure_count=0, level1_failures=[], budget_derivation='ALLOWED')
    forged_path = tmp_path / 'forged.json'
    forged_path.write_text(json.dumps(forged), encoding='utf-8')
    refuse(collected, audit, forged_path, tmp_path / 'out2.json', 'disagrees with the recomputed eligibility')
    assert not toy_tokenizer


@pytest.mark.parametrize('label,mutate,message', [
    ('schema', lambda a: a.update(schema_version='b0-suffix-adjudication/9.9.9'), 'does not belong to this collection'),
    ('attempt', lambda a: a.update(attempt='attempt-02'), 'does not belong to this collection'),
    ('collection hash', lambda a: a.update(collection_sha256='0' * 64), 'does not belong to this collection'),
    ('audit hash', lambda a: a.update(audit_file_sha256='0' * 64), 'does not belong to this completed audit'),
    ('status', lambda a: a.update(status='COMPLETE_BUT_INELIGIBLE'), 'not an ELIGIBLE result'),
    ('failure count', lambda a: a.update(level1_failure_count=1), 'not an ELIGIBLE result'),
    ('failure list', lambda a: a.update(level1_failures=[{'item': 'x'}]), 'not an ELIGIBLE result'),
    ('derivation flag', lambda a: a.update(budget_derivation='PROHIBITED'), 'not an ELIGIBLE result'),
    ('budget set', lambda a: a.update(b0_context_tokens=5), 'not an ELIGIBLE result'),
    ('items audited', lambda a: a.update(items_audited=143), 'disagrees with the recomputed eligibility'),
    ('extra field', lambda a: a.update(reviewer_override=True), 'Adjudication fields'),
    ('missing field', lambda a: a.pop('fluency_findings'), 'Adjudication fields'),
])
def test_an_altered_or_foreign_adjudication_refuses_derivation(
        collected, evidence, toy_tokenizer, tmp_path, label, mutate, message):
    audit, adjudication = evidence
    altered = json.loads(adjudication.read_text(encoding='utf-8'))
    mutate(altered)
    path = tmp_path / 'altered.json'
    path.write_text(json.dumps(altered), encoding='utf-8')
    refuse(collected, audit, path, tmp_path / 'out.json', message)
    assert not toy_tokenizer


def test_any_audit_or_collection_mismatch_refuses_derivation(
        collected, approved, evidence, toy_tokenizer, tmp_path, monkeypatch):
    audit, adjudication = evidence
    reformatted = tmp_path / 'reformatted.json'
    reformatted.write_text(json.dumps(json.loads(audit.read_text(encoding='utf-8')), indent=2), encoding='utf-8')
    refuse(collected, reformatted, adjudication, tmp_path / 'a.json', 'does not belong to this completed audit')
    other_audit, other_adjudication = adjudicated(collected, approved, tmp_path, 'other')
    other = json.loads(other_audit.read_text(encoding='utf-8'))
    other['reviewer'] = 'Someone else'
    other_audit.write_text(json.dumps(other), encoding='utf-8')
    refuse(collected, other_audit, other_adjudication, tmp_path / 'b.json', 'does not belong to this completed audit')
    fixtures = [f for _, f, _, _ in s.plan(approved)]
    second = tmp_path / 'second' / 'attempt-01'
    run_collect(approved, second, monkeypatch, lambda i, b: __import__('httpx').Response(
        200, json=__import__('test_b0_calibration').envelope(b, mock_output(fixtures[i], lambda o: o['low'].update(
            U7=o['low']['U7'] + ' Also.')))) if i == 0 else None)
    assert probe.file_hash(second / 'collection.json') != probe.file_hash(collected / 'collection.json')
    refuse(second, audit, adjudication, tmp_path / 'c.json', 'does not match the archived collection|archived evidence')
    assert not toy_tokenizer


def test_missing_or_incomplete_audits_refuse_derivation(collected, approved, evidence, toy_tokenizer, tmp_path):
    audit, adjudication = evidence
    refuse(collected, tmp_path / 'absent.json', adjudication, tmp_path / 'a.json', 'must all exist')
    refuse(collected, audit, tmp_path / 'absent.json', tmp_path / 'b.json', 'must all exist')
    refuse(tmp_path / 'no-collection', audit, adjudication, tmp_path / 'c.json', 'must all exist')
    blank = tmp_path / 'blank.json'
    blank.write_text(json.dumps(s.audit_template(collected, approved)), encoding='utf-8')
    refuse(collected, blank, adjudication, tmp_path / 'd.json', 'incomplete|reviewer')
    partial = json.loads(audit.read_text(encoding='utf-8'))
    partial['items']['G1/b0cal-scheduling-01/low/U7']['manual']['comprehensibility'] = None
    incomplete = tmp_path / 'incomplete.json'
    incomplete.write_text(json.dumps(partial), encoding='utf-8')
    refuse(collected, incomplete, adjudication, tmp_path / 'e.json', 'incomplete')
    assert not toy_tokenizer


def test_an_incomplete_collection_refuses_derivation(approved, toy_tokenizer, tmp_path, monkeypatch, evidence):
    fixtures = [f for _, f, _, _ in s.plan(approved)]
    path = tmp_path / 'attempt-01'
    result, _ = run_collect(approved, path, monkeypatch, lambda i, b: __import__('httpx').Response(
        200, json=__import__('test_b0_calibration').envelope(b, mock_output(fixtures[i], lambda o: o['low'].update(
            U7='')))) if i == 3 else None)
    assert result['status'] == 'INCOMPLETE'
    audit, adjudication = evidence
    refuse(path, audit, adjudication, tmp_path / 'out.json', 'complete suffix attempt')


# --- Output ----------------------------------------------------------------------------------------

def test_the_output_must_be_new_and_outside_the_attempt(collected, evidence, toy_tokenizer, tmp_path):
    audit, adjudication = evidence
    existing = tmp_path / 'existing.json'
    existing.write_text('keep')
    refuse(collected, audit, adjudication, existing, 'already exists', preexisting=True)
    assert existing.read_text() == 'keep' and not toy_tokenizer
    refuse(collected, audit, adjudication, audit, 'already exists', preexisting=True)
    refuse(collected, audit, adjudication, collected / 'derivation.json', 'outside the attempt')
    assert not (collected / 'derivation.json').exists()
    out = tmp_path / 'derivation' / 'attempt-01.json'
    assert s.main(derive_args(collected, audit, adjudication, out)) == 0
    first = out.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        s.main(derive_args(collected, audit, adjudication, out))
    assert out.read_bytes() == first


def test_the_derivation_is_deterministic(collected, evidence, toy_tokenizer, tmp_path):
    audit, adjudication = evidence
    s.main(derive_args(collected, audit, adjudication, tmp_path / 'a.json'))
    s.main(derive_args(collected, audit, adjudication, tmp_path / 'b.json'))
    assert (tmp_path / 'a.json').read_bytes() == (tmp_path / 'b.json').read_bytes()


# --- Exclusivity and help --------------------------------------------------------------------------

@pytest.mark.parametrize('extra', [
    ['--execute', '--confirm-spend'], ['--execute'], ['--confirm-spend'],
    ['--output-directory', 'x'], ['--audit-template', 'x'], ['--template-output', 'x'],
    ['--adjudicate', 'x'], ['--adjudication-output', 'x'],
    ['--audit-template', 'x', '--template-output', 'y'],
    ['--adjudicate', 'x', '--adjudication-output', 'y'],
])
def test_derive_budget_is_exclusive_with_execution_audit_template_and_adjudication(
        collected, evidence, toy_tokenizer, tmp_path, extra):
    audit, adjudication = evidence
    out = tmp_path / 'out.json'
    with pytest.raises(SystemExit):
        s.main(derive_args(collected, audit, adjudication, out, *extra))
    assert not out.exists() and not toy_tokenizer


@pytest.mark.parametrize('flags', [
    ['--derive-budget', 'x'], ['--derive-budget', 'x', '--audit', 'a'], ['--derive-budget', 'x', '--audit', 'a',
                                                                       '--adjudication', 'j'],
    ['--adjudication', 'j'], ['--budget-output', 'o'], ['--reader-tokenizer-dir', 'r'],
    ['--audit', 'a', '--adjudication', 'j', '--budget-output', 'o'],
])
def test_derive_budget_needs_all_of_its_inputs(toy_tokenizer, flags):
    with pytest.raises(SystemExit):
        s.main(flags)
    assert not toy_tokenizer


def test_the_other_modes_reject_derivation_flags_and_abbreviations(collected, evidence, toy_tokenizer, tmp_path):
    audit, adjudication = evidence
    with pytest.raises(SystemExit):
        s.main(['--adjudicate', str(collected), '--audit', str(audit), '--adjudication-output',
                str(tmp_path / 'x.json'), '--budget-output', str(tmp_path / 'y.json')])
    out = tmp_path / 'abbreviated.json'
    with pytest.raises(SystemExit):
        s.main(['--derive-budget', str(collected), '--audit', str(audit), '--adjudication', str(adjudication),
                '--budget-out', str(out)])
    assert not (tmp_path / 'x.json').exists() and not out.exists() and not toy_tokenizer


def test_help_names_the_derivation_operation(capsys):
    with pytest.raises(SystemExit) as exit_info:
        s.main(['--help'])
    assert exit_info.value.code == 0
    text = capsys.readouterr().out
    for fragment in ('--derive-budget ATTEMPT_DIRECTORY', '--adjudication ADJUDICATION', '--budget-output',
                     '--reader-tokenizer-dir', 'ELIGIBLE', 'never combined with other modes'):
        assert fragment in text


# --- The real evidence passes the provenance gate (no derivation) ----------------------------------

@pytest.mark.skipif(not (REAL / 'manual-audit/attempt-01.adjudication.json').is_file(),
                    reason='The real suffix collection is not present')
def test_the_real_adjudication_satisfies_the_provenance_gate_without_deriving(approved):
    directory = REAL / 'attempt-01'
    audit_path = REAL / 'manual-audit/attempt-01.completed.json'
    adjudication = json.loads((REAL / 'manual-audit/attempt-01.adjudication.json').read_text(encoding='utf-8'))
    verdict = s.verify_adjudication(directory, audit_path, adjudication, json.loads(audit_path.read_text(encoding='utf-8')),
                                    approved)
    assert verdict['status'] == 'ELIGIBLE' and verdict['level1_failure_count'] == 0 and verdict['items_audited'] == 144
    assert adjudication['b0_context_tokens'] is None
