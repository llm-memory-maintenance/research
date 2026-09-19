"""Offline tests for the Attempt-01 closure and the bounded, complete Attempt-02 restart."""
import asyncio
import inspect
import json
from pathlib import Path
import shutil
import socket
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import calibrate_b0 as cal
import probe_generators as probe
from test_b0_calibration import design_copy, envelope, fake_git, mock_output, run_collect

ATTEMPT_01 = ROOT / 'results/b0-calibration/attempt-01'
CLOSURE = ROOT / 'results/b0-calibration/closure/attempt-01.json'
TERMINAL = 'b0cal-software-configuration-01'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)


@pytest.fixture(scope='module')
def inputs(tmp_path_factory):
    """The full-history procedure in its pre-Attempt-02 state; the real design is closed (tested below)."""
    return cal.load_inputs(design_copy(tmp_path_factory.mktemp('historical')))


@pytest.fixture(scope='module')
def real_inputs():
    return cal.load_inputs()


@pytest.fixture(scope='module')
def closure():
    return json.loads(CLOSURE.read_text(encoding='utf-8'))


def record(name, root=ATTEMPT_01):
    return json.loads((root / 'outputs' / name).read_text(encoding='utf-8'))


def empty_high(index, body):
    output = mock_output(index)
    output['high'].update(N1='', N2='', Q='')
    return httpx.Response(200, json=envelope(body, output))


# --- Attempt-01 closure ----------------------------------------------------------------------------

def test_attempt_01_is_a_terminal_output_contract_failure_derived_from_its_evidence(inputs, closure):
    assert closure == cal.classify_attempt(ATTEMPT_01, inputs)
    assert (closure['status'], closure['attempt']) == ('CLOSED_INCOMPLETE', 'attempt-01')
    assert closure['terminal_reason'] == 'OUTPUT_CONTRACT_FAILURE'
    assert closure['terminal_detail'] == 'REQUIRED_EMPTY_FIELD_SCHEMA_FAILURE'
    call = closure['terminal_call']
    assert (call['logical_call_index'], call['logical_call_id'], call['model'], call['scenario_id']) == (
        17, 'G2', 'anthropic/claude-fable-5.1', TERMINAL)
    assert (call['http_status'], call['finish_reason'], call['refusal'], call['incomplete_or_truncated']) == (
        200, 'stop', False, False)
    assert (call['parse_status'], call['schema_status']) == ('passed', 'failed')
    assert (call['processing_or_charge_uncertain'], call['retry_reason'], call['physical_attempts']) == (False, None, 1)
    assert call['failure_reason'] == 'Expected nonempty string' and call['empty_fields'] == {'high': ['N1', 'N2', 'Q']}
    assert closure['schema_recheck'] == {'local_validator': {'result': 'FAILS', 'reason': 'Expected nonempty string'},
                                         'frozen_schema_nonempty_minimum': [1]}
    assert closure['budget_derivation'] == 'PROHIBITED' and closure['b0_context_tokens'] is None
    assert closure['any_processing_or_charge_uncertain'] is False


def test_attempt_01_recorded_17_calls_16_passed_and_calls_18_to_24_never_ran(closure):
    assert closure['calls'] == {'planned': 24, 'recorded': 17, 'passed': 16, 'failed': 1,
                                'never_executed': list(range(18, 25))}
    collection = json.loads((ATTEMPT_01 / 'collection.json').read_text(encoding='utf-8'))
    assert collection['status'] == 'INCOMPLETE' and len(collection['calls']) == 17
    assert [c['logical_call_index'] for c in collection['calls']] == list(range(1, 18))
    assert [c['status'] for c in collection['calls']] == ['PASS'] * 16 + ['FAIL']
    assert not any(a['processing_or_charge_uncertain'] for c in collection['calls'] for a in c['attempts'])
    assert len(list((ATTEMPT_01 / 'outputs').rglob('*.json'))) == 17
    assert not (ATTEMPT_01 / 'outputs/g2/b0cal-study-planning-01.json').exists()


def test_attempt_01_checksums_verify_and_match_the_closure(closure):
    sums = cal.q.read_sums(ATTEMPT_01)
    assert len(sums) == 18 and set(sums) == set(closure['evidence']['files'])
    for name, checksum in sums.items():
        assert probe.file_hash(ATTEMPT_01 / name) == checksum
    assert probe.file_hash(ATTEMPT_01 / 'collection.json') == closure['evidence']['collection_sha256']
    assert probe.file_hash(ATTEMPT_01 / 'SHA256SUMS') == closure['evidence']['sha256sums_sha256']
    assert closure['evidence']['source_commit'] == '99b3082521fcc530890c4df749df1b5242a66290'


def test_three_empty_high_fields_are_preserved_as_raw_evidence():
    call = record(f'g2/{TERMINAL}.json')
    attempt = call['attempts'][-1]
    assert call['status'] == 'FAIL' and len(call['attempts']) == 1
    parsed = attempt['parsed_structured_response']
    assert {k: v for k, v in parsed['high'].items() if v == ''} == {'N1': '', 'N2': '', 'Q': ''}
    assert all(v for v in parsed['low'].values()) and all(v for v in parsed['medium'].values())
    content = json.loads(attempt['raw_response'])['choices'][0]['message']['content']
    assert json.loads(content) == parsed
    assert [k for k, v in json.loads(content)['high'].items() if v == ''] == ['N1', 'N2', 'Q']
    assert (attempt['parse_status'], attempt['schema_status'], attempt['failure_reason']) == (
        'passed', 'failed', 'Expected nonempty string')


def test_attempt_01_cannot_derive_a_budget(inputs, closure):
    with pytest.raises(ValueError, match='complete attempt'):
        cal.official_calls(ATTEMPT_01)
    with pytest.raises(ValueError):
        cal.histories_from_calls(cal.read_calls(ATTEMPT_01), inputs)
    assert closure['budget_derivation'] == 'PROHIBITED' and closure['b0_context_tokens'] is None
    assert closure['output_use'].startswith('No output of this attempt may be combined')


def test_closure_operation_is_offline_deterministic_and_refuses_overwrite(inputs, tmp_path):
    out = tmp_path / 'closure.json'
    assert cal.main(['--close-attempt', str(ATTEMPT_01), '--closure-output', str(out)]) == 0
    assert out.read_bytes() == CLOSURE.read_bytes()
    with pytest.raises(FileExistsError):
        cal.main(['--close-attempt', str(ATTEMPT_01), '--closure-output', str(out)])
    copy = tmp_path / 'attempt-01'
    shutil.copytree(ATTEMPT_01, copy)
    with pytest.raises(ValueError, match='outside the attempt'):
        cal.main(['--close-attempt', str(copy), '--closure-output', str(copy / 'closure.json')])
    for flags in (['--close-attempt', str(ATTEMPT_01)], ['--closure-output', str(out)],
                  ['--close-attempt', str(ATTEMPT_01), '--closure-output', str(tmp_path / 'x.json'), '--execute',
                   '--confirm-spend']):
        with pytest.raises(SystemExit):
            cal.main(flags)


def test_only_an_incomplete_attempt_with_one_terminal_call_can_be_closed(inputs, tmp_path, monkeypatch):
    complete, _ = run_collect(inputs, tmp_path / 'complete', monkeypatch)
    assert complete['status'] == 'COMPLETE'
    with pytest.raises(ValueError, match='Not an incomplete collection'):
        cal.classify_attempt(tmp_path / 'complete', inputs)


def test_closure_derivation_rejects_evidence_that_is_not_exactly_the_planned_prefix(inputs, tmp_path, monkeypatch):
    def failing_at_five(i, b):
        return empty_high(i, b) if i == 4 else None
    result, _ = run_collect(inputs, tmp_path / 'attempt', monkeypatch, failing_at_five)
    assert result['status'] == 'INCOMPLETE'
    path = tmp_path / 'attempt'
    assert cal.classify_attempt(path, inputs)['calls']['recorded'] == 5
    extra = path / 'outputs/g1/unplanned.json'
    extra.write_text('{}')
    sums = (path / 'SHA256SUMS').read_text(encoding='utf-8')
    (path / 'SHA256SUMS').write_text(sums + f'{probe.file_hash(extra)}  outputs/g1/unplanned.json\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Unexpected archived files'):
        cal.classify_attempt(path, inputs)

    other = tmp_path / 'other'
    shutil.copytree(path, other)
    (other / 'outputs/g1/unplanned.json').unlink()
    lines = [line for line in (other / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
             if 'unplanned' not in line]
    (other / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    assert cal.classify_attempt(other, inputs)['calls']['recorded'] == 5
    victim = other / 'outputs/g1/b0cal-project-planning-01.json'
    record_ = json.loads(victim.read_text(encoding='utf-8'))
    record_['wire_request_sha256'] = '0' * 64
    victim.write_text(json.dumps(record_, indent=2) + '\n', encoding='utf-8')
    collection_file = other / 'collection.json'
    collection = json.loads(collection_file.read_text(encoding='utf-8'))
    collection['calls'][2]['wire_request_sha256'] = '0' * 64
    collection_file.write_text(json.dumps(collection, indent=2) + '\n', encoding='utf-8')
    (other / 'SHA256SUMS').write_text(''.join(
        f'{probe.file_hash(other / name)}  {name}\n' for name in sorted(cal.q.read_sums(other))), encoding='utf-8')
    with pytest.raises(ValueError, match='differs from the plan'):
        cal.classify_attempt(other, inputs)


# --- No selective retry or resume ------------------------------------------------------------------

def test_no_resume_or_selective_retry_entry_point_exists():
    assert set(inspect.signature(cal.collect).parameters) == {'inputs', 'key', 'output', 'client_factory', 'sleep'}
    for flag in ('--resume', '--start-at', '--retry', '--skip', '--from-call', '--continue'):
        with pytest.raises(SystemExit):
            cal.main([flag])
    assert not [name for name in dir(cal) if any(word in name.lower() for word in ('resume', 'retry_call', 'repair'))]


def test_the_attempt_01_failure_pattern_ends_the_attempt_without_retry_or_resume(inputs, tmp_path, monkeypatch):
    path = tmp_path / 'attempt'
    result, bodies = run_collect(inputs, path, monkeypatch, lambda i, b: empty_high(i, b) if i == 16 else None)
    assert len(bodies) == 17 and result['status'] == 'INCOMPLETE' and len(result['calls']) == 17
    assert result['failure_kind'] == 'OUTPUT_CONTRACT_FAILURE'
    terminal = result['calls'][16]
    assert terminal['status'] == 'FAIL' and len(terminal['attempts']) == 1
    assert terminal['attempts'][0]['parsed_structured_response']['high']['N1'] == ''
    assert 'Expected nonempty string' in result['failure_reason'] and 'STOP FOR RESEARCHER DECISION' in result['failure_reason']
    assert len(list((path / 'outputs').rglob('*.json'))) == 17
    closed = cal.classify_attempt(path, inputs)
    assert closed['terminal_detail'] == 'REQUIRED_EMPTY_FIELD_SCHEMA_FAILURE'
    assert closed['calls']['never_executed'] == list(range(18, 25)) and closed['budget_derivation'] == 'PROHIBITED'
    with pytest.raises(ValueError):
        cal.official_calls(path)


# --- Attempt-02 plan -------------------------------------------------------------------------------

def test_attempt_02_plans_all_24_calls_from_call_1_with_unchanged_requests(inputs, closure):
    shown = cal.preview(inputs)
    assert (shown['attempt'], shown['attempt_cap'], shown['result_directory']) == (
        'attempt-02', 2, 'results/b0-calibration/attempt-02')
    calls = shown['calls']
    assert [c['index'] for c in calls] == list(range(1, 25))
    assert (calls[0]['logical_call_id'], calls[0]['scenario_id']) == ('G1', 'b0cal-scheduling-01')
    assert [c['model'] for c in calls] == ['openai/gpt-5.6-sol'] * 12 + ['anthropic/claude-fable-5.1'] * 12
    assert shown['planned_logical_calls'] == 24 and shown['per_generator'] == {'G1': 12, 'G2': 12}
    assert shown['expected_histories'] == 72
    assert shown['predecessor_closures'] == {'attempt-01': probe.file_hash(CLOSURE)}
    assert cal.plan_identity(inputs) == closure['plan_identity']
    assert shown['request_hashes'] == closure['plan_identity']['request_sha256']
    for call, (generator, fixture, _) in zip(calls[:17], cal.plan(inputs)):
        sent = record(f'{call["logical_call_id"].lower()}/{call["scenario_id"]}.json')
        assert sent['wire_request_sha256'] == call['request_sha256']
        assert sent['wire_request'] == probe.canonical(cal.request(generator, fixture))
    assert all(c['output_path'].startswith('results/b0-calibration/attempt-02/outputs/') for c in calls)


def test_attempt_02_mocked_collection_reruns_from_call_1_and_never_reads_attempt_01_outputs(
        inputs, tmp_path, monkeypatch):
    opened = []
    for name in ('read_text', 'read_bytes'):
        original = getattr(Path, name)

        def spy(self, *args, _original=original, **kwargs):
            opened.append(str(self))
            return _original(self, *args, **kwargs)
        monkeypatch.setattr(Path, name, spy)
    for name in ('read_calls', 'official_calls', 'histories_from_calls', 'classify_attempt'):
        monkeypatch.setattr(cal, name, lambda *a, **k: pytest.fail('Attempt-01 outputs must not be read'))
    result, bodies = run_collect(inputs, tmp_path / 'attempt-02', monkeypatch)
    shown = cal.preview(inputs)
    assert result['status'] == 'COMPLETE' and result['attempt'] == 'attempt-02' and len(bodies) == 24
    assert [probe.digest(probe.canonical(b).encode()) for b in bodies] == shown['request_hashes']
    assert [b['model'] for b in bodies] == ['openai/gpt-5.6-sol'] * 12 + ['anthropic/claude-fable-5.1'] * 12
    assert [c['logical_call_index'] for c in result['calls']] == list(range(1, 25))
    assert {c['attempt'] for c in result['calls']} == {'attempt-02'}
    assert result['provenance']['attempt'] == 'attempt-02'
    assert result['provenance']['predecessor_closures'] == {'attempt-01': probe.file_hash(CLOSURE)}
    touched = [p for p in opened if '/results/b0-calibration/attempt-01/' in p]
    assert not [p for p in touched if '/outputs/' in p]
    assert set(Path(p).name for p in touched) <= {'collection.json', 'SHA256SUMS'}


def test_attempt_01_outputs_cannot_be_mixed_into_an_official_calibration_set(inputs, tmp_path, monkeypatch):
    run_collect(inputs, tmp_path / 'attempt-02', monkeypatch)
    fresh = cal.official_calls(tmp_path / 'attempt-02')
    assert len(cal.histories_from_calls(fresh, inputs)) == 72
    old = cal.read_calls(ATTEMPT_01)
    assert len(old) == 17 and all('attempt' not in c for c in old)
    mixed = old[:16] + fresh[16:]
    with pytest.raises(ValueError, match='one attempt'):
        cal.histories_from_calls(mixed, inputs)
    relabeled = [{**c, 'attempt': 'attempt-01'} for c in old[:16]] + fresh[16:]
    with pytest.raises(ValueError, match='one attempt'):
        cal.histories_from_calls(relabeled, inputs)


# --- One additional attempt only -------------------------------------------------------------------

def test_exactly_one_additional_complete_attempt_is_permitted(inputs, tmp_path):
    design = inputs['design']
    assert cal.official_attempt(design)['id'] == 'attempt-02'
    assert design['naturalization']['attempt_cap'] == 2
    extra = {'id': 'attempt-03', 'status': 'PLANNED_NOT_EXECUTED', 'result_directory': 'results/b0-calibration/attempt-03'}

    def add_third(d):
        d['naturalization']['attempts'].append(extra)

    def cap_three(d):
        d['naturalization']['attempt_cap'] = 3
        add_third(d)

    def second_closed(d):
        d['naturalization']['attempts'][1].update(status='CLOSED_INCOMPLETE',
                                                  closure='results/b0-calibration/closure/attempt-02.json')

    def both_planned(d):
        d['naturalization']['attempts'][0].update(status='PLANNED_NOT_EXECUTED')
        del d['naturalization']['attempts'][0]['closure']

    def reordered(d):
        d['naturalization']['attempts'].reverse()

    for mutate in (add_third, cap_three, reordered):
        with pytest.raises(ValueError, match='attempt'):
            cal.load_design(design_copy(tmp_path, mutate))
    for mutate in (second_closed, both_planned):
        loaded = cal.load_design(design_copy(tmp_path, mutate))
        with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
            cal.official_attempt(loaded)
        with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
            cal.require_official(loaded)
    with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
        cal.main(['--design', str(design_copy(tmp_path, second_closed)), '--execute', '--confirm-spend',
                  '--output-directory', str(ROOT / 'results/b0-calibration/attempt-02')])


def test_a_second_terminal_failure_stops_for_a_researcher_decision(inputs, tmp_path, monkeypatch):
    result, bodies = run_collect(inputs, tmp_path / 'a', monkeypatch, lambda i, b: empty_high(i, b) if i == 2 else None)
    assert result['status'] == 'INCOMPLETE' and len(bodies) == 3 and result['failure_kind'] == 'OUTPUT_CONTRACT_FAILURE'
    assert 'STOP FOR RESEARCHER DECISION' in result['failure_reason']
    assert 'no further B0 attempt is allowed' in result['failure_reason']

    def unavailable(index, body):
        if index >= 1:
            return httpx.Response(503, json={'error': {'message': 'unavailable'}})
    result, bodies = run_collect(inputs, tmp_path / 'b', monkeypatch, unavailable)
    assert result['status'] == 'INCOMPLETE' and result['failure_kind'] == 'INFRASTRUCTURE_OR_API_ERROR'
    assert 'STOP FOR RESEARCHER DECISION' in result['failure_reason'] and len(bodies) == 4


def test_no_attempt_03_or_existing_attempt_directory_can_be_written(inputs, tmp_path, monkeypatch):
    design = inputs['design']
    for name in ('attempt-01', 'attempt-03', 'closure', ''):
        with pytest.raises(ValueError, match='planned attempt directory'):
            cal.guard_output(ROOT / 'results/b0-calibration' / name, design)
    cal.guard_output(ROOT / 'results/b0-calibration/attempt-02', design)
    cal.guard_output(tmp_path / 'anywhere', design)
    monkeypatch.setattr(cal, 'git', fake_git)
    for name in ('attempt-01', 'attempt-03'):
        target = ROOT / 'results/b0-calibration' / name
        existed = target.exists()
        with pytest.raises(ValueError, match='planned attempt directory'):
            asyncio.run(cal.collect(inputs, 'test-secret', target, client_factory=lambda **k: pytest.fail('No client')))
        assert target.exists() == existed
        with pytest.raises(ValueError, match='frozen result directory'):
            cal.main(['--design', str(inputs['path']), '--execute', '--confirm-spend',
                      '--output-directory', str(target)])
    assert not (ROOT / 'results/b0-calibration/attempt-03').exists()


def test_existing_attempt_directories_are_never_overwritten(inputs, tmp_path, monkeypatch):
    for name in ('attempt-01', 'attempt-02'):
        existing = tmp_path / name
        existing.mkdir()
        (existing / 'keep.txt').write_text('evidence')
        with pytest.raises(FileExistsError):
            run_collect(inputs, existing, monkeypatch)
        assert [p.name for p in existing.iterdir()] == ['keep.txt']


# --- Predecessor verification ----------------------------------------------------------------------

def test_predecessor_closure_must_be_authentic_and_for_the_same_plan(inputs, tmp_path, monkeypatch):
    root = tmp_path / 'root'
    shutil.copytree(ROOT / 'results/b0-calibration', root / 'results/b0-calibration')
    assert cal.verify_predecessors(inputs, root=root) == {'attempt-01': probe.file_hash(CLOSURE)}
    closure_file = root / 'results/b0-calibration/closure/attempt-01.json'
    original = closure_file.read_text(encoding='utf-8')

    def refuse(message):
        with pytest.raises(ValueError, match=message):
            cal.verify_predecessors(inputs, root=root)
    closure_file.write_text(original.replace('"CLOSED_INCOMPLETE"', '"COMPLETE"', 1), encoding='utf-8')
    refuse('not CLOSED_INCOMPLETE')
    closure_file.write_text(original.replace('"PROHIBITED"', '"ALLOWED"'), encoding='utf-8')
    refuse('not CLOSED_INCOMPLETE')
    closure_file.write_text(original, encoding='utf-8')
    collection = root / 'results/b0-calibration/attempt-01/collection.json'
    saved = collection.read_bytes()
    collection.write_bytes(saved + b' ')
    refuse('drifted')
    collection.write_bytes(saved)
    sums = root / 'results/b0-calibration/attempt-01/SHA256SUMS'
    sums_saved = sums.read_text(encoding='utf-8')
    sums.write_text(sums_saved.replace('0', '1', 1), encoding='utf-8')
    refuse('drifted')
    sums.write_text(sums_saved, encoding='utf-8')
    real = cal.plan_identity
    monkeypatch.setattr(cal, 'plan_identity', lambda i: {**real(i), 'order': 'reordered'})
    refuse('frozen plan changed')
    monkeypatch.setattr(cal, 'plan_identity', real)
    closure_file.unlink()
    refuse('Missing closure')


def test_live_collection_refuses_when_the_predecessor_closure_is_missing(inputs, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, 'git', fake_git)
    empty_root = tmp_path / 'empty'
    real = cal.verify_predecessors
    monkeypatch.setattr(cal, 'verify_predecessors', lambda i, root=ROOT: real(i, root=empty_root))
    path = tmp_path / 'attempt'
    with pytest.raises(ValueError, match='Missing closure'):
        asyncio.run(cal.collect(inputs, 'test-secret', path, client_factory=lambda **k: pytest.fail('No client')))
    assert not path.exists()


# --- Attempt-02 closure and the closed full-history procedure --------------------------------------

ATTEMPT_02 = ROOT / 'results/b0-calibration/attempt-02'
CLOSURE_02 = ROOT / 'results/b0-calibration/closure/attempt-02.json'
TERMINAL_02 = 'b0cal-task-assignment-01'


@pytest.fixture(scope='module')
def closure_02():
    return json.loads(CLOSURE_02.read_text(encoding='utf-8'))


def test_attempt_02_is_a_terminal_output_contract_failure_derived_from_its_evidence(real_inputs, closure_02):
    assert closure_02 == cal.classify_attempt(ATTEMPT_02, real_inputs)
    assert (closure_02['status'], closure_02['attempt']) == ('CLOSED_INCOMPLETE', 'attempt-02')
    assert closure_02['terminal_reason'] == 'OUTPUT_CONTRACT_FAILURE'
    assert closure_02['terminal_detail'] == 'REQUIRED_EMPTY_FIELD_SCHEMA_FAILURE'
    call = closure_02['terminal_call']
    assert (call['logical_call_index'], call['logical_call_id'], call['model'], call['scenario_id']) == (
        16, 'G2', 'anthropic/claude-fable-5.1', TERMINAL_02)
    assert (call['http_status'], call['finish_reason'], call['refusal'], call['incomplete_or_truncated']) == (
        200, 'stop', False, False)
    assert (call['parse_status'], call['schema_status']) == ('passed', 'failed')
    assert (call['processing_or_charge_uncertain'], call['retry_reason'], call['physical_attempts']) == (False, None, 1)
    assert call['failure_reason'] == 'Expected nonempty string' and call['empty_fields'] == {'high': ['N1']}
    assert closure_02['calls'] == {'planned': 24, 'recorded': 16, 'passed': 15, 'failed': 1,
                                   'never_executed': list(range(17, 25))}
    assert closure_02['budget_derivation'] == 'PROHIBITED' and closure_02['b0_context_tokens'] is None
    assert closure_02['any_processing_or_charge_uncertain'] is False
    assert closure_02['evidence']['source_commit'] == '5b08811310b6b1036e17b8a6c9d4397a187eaaed'


def closure_02_hash(field):
    return json.loads(CLOSURE_02.read_text(encoding='utf-8'))['evidence'][field]


def test_attempt_02_raw_evidence_shows_only_n1_empty_and_the_budget_fields_present(closure_02):
    call = record(f'g2/{TERMINAL_02}.json', ATTEMPT_02)
    attempt = call['attempts'][-1]
    parsed = attempt['parsed_structured_response']
    assert {k: v for k, v in parsed['high'].items() if v == ''} == {'N1': ''}
    assert parsed['high']['U7'] and parsed['high']['N2'] and parsed['high']['Q']
    assert all(v for variant in ('low', 'medium') for v in parsed[variant].values())
    content = json.loads(attempt['raw_response'])['choices'][0]['message']['content']
    assert json.loads(content) == parsed and json.loads(content)['high']['N1'] == ''
    sums = cal.q.read_sums(ATTEMPT_02)
    assert len(sums) == 17
    for name, checksum in sums.items():
        assert probe.file_hash(ATTEMPT_02 / name) == checksum
    assert probe.file_hash(ATTEMPT_02 / 'collection.json') == closure_02_hash('collection_sha256')
    collection = json.loads((ATTEMPT_02 / 'collection.json').read_text(encoding='utf-8'))
    assert [c['status'] for c in collection['calls']] == ['PASS'] * 15 + ['FAIL']
    assert not any(a['processing_or_charge_uncertain'] for c in collection['calls'] for a in c['attempts'])
    assert not (ATTEMPT_02 / 'outputs/g2/b0cal-software-configuration-01.json').exists()


def test_attempt_02_cannot_derive_a_budget(real_inputs):
    with pytest.raises(ValueError, match='complete attempt'):
        cal.official_calls(ATTEMPT_02)
    with pytest.raises(ValueError):
        cal.histories_from_calls(cal.read_calls(ATTEMPT_02), real_inputs)


def test_the_full_history_procedure_is_closed_and_can_run_no_further_attempt(real_inputs, tmp_path, monkeypatch):
    design = real_inputs['design']
    assert design['naturalization']['status'] == 'CLOSED_NO_ELIGIBLE_SET'
    assert [a['status'] for a in design['naturalization']['attempts']] == ['CLOSED_INCOMPLETE'] * 2
    assert cal.planned_attempt(design) is None
    with pytest.raises(ValueError, match='STOP FOR RESEARCHER DECISION'):
        cal.official_attempt(design)
    with pytest.raises(ValueError, match='closed'):
        cal.require_official(design)
    assert cal.verify_predecessors(real_inputs) == {'attempt-01': probe.file_hash(CLOSURE),
                                                    'attempt-02': probe.file_hash(CLOSURE_02)}
    monkeypatch.setattr(cal, 'git', fake_git)
    for name in ('attempt-01', 'attempt-02', 'attempt-03'):
        target = ROOT / 'results/b0-calibration' / name
        existed = target.exists()
        with pytest.raises(ValueError):
            asyncio.run(cal.collect(real_inputs, 'test-secret', target,
                                    client_factory=lambda **k: pytest.fail('No client')))
        assert target.exists() == existed
        with pytest.raises(ValueError, match='closed'):
            cal.main(['--execute', '--confirm-spend', '--output-directory', str(target)])
    shown = cal.preview(real_inputs)
    assert shown['attempt'] is None and shown['result_directory'] is None
    assert all(c['output_path'] is None for c in shown['calls'])
    assert shown['naturalization_status'] == 'CLOSED_NO_ELIGIBLE_SET'
    assert not (ROOT / 'results/b0-calibration/attempt-03').exists()


def test_neither_old_attempt_can_be_reused_or_mixed(real_inputs):
    one, two = cal.read_calls(ATTEMPT_01), cal.read_calls(ATTEMPT_02)
    assert len(one) == 17 and len(two) == 16
    with pytest.raises(ValueError):
        cal.histories_from_calls(one[:16] + two[16:], real_inputs)
