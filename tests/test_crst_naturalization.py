"""Offline tests of the gated pilot naturalization path (mock transport only) and its audit."""
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from crst_common import (ROOT, ToyTokenizer, chat_envelope, fake_git, good_output, no_network,  # noqa: F401
                         run_naturalization)
import crst_policies as pol
import naturalize_crst_pilot as nat
import probe_generators as probe
import qualify_generators as q
import run_crst_pilot as run
import validate_generator_qualification_fixtures as gq

KEY = 'test-secret'


@pytest.fixture(autouse=True)
def skip_corpus_scan(monkeypatch):
    """The LongMemEval-S scan is exercised by the material tests; mocked collections need not repeat it."""
    monkeypatch.setattr(nat.material, 'LONGMEMEVAL_RAW', ROOT / 'nonexistent-longmemeval.json')


@pytest.fixture(scope='module')
def inputs():
    return nat.load_inputs()


@pytest.fixture()
def git(monkeypatch):
    monkeypatch.setattr(nat, 'git', fake_git)


def files(path):
    return sorted(str(p.relative_to(path)) for p in Path(path).rglob('*') if p.is_file())


# --- Offline preview and plan -------------------------------------------------------------------------

def test_preview_shows_exactly_two_units_with_exact_generators_and_no_fallback(inputs):
    shown = nat.preview(inputs)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['planned_units'] == 2 and shown['max_logical_calls'] == 6
    assert [(u['scenario_id'], u['generator'], u['model'], u['provider_order']) for u in shown['units']] == [
        ('pilot-scheduling-01', 'G1', 'openai/gpt-5.6-sol', ['openai']),
        ('pilot-travel-01', 'G2', 'anthropic/claude-fable-5.1', ['anthropic'])]
    assert all(u['allow_fallbacks'] is False and u['max_logical_attempts'] == 3 for u in shown['units'])
    assert shown['result_directory'] == 'results/crst-small-pilot/naturalization/attempt-01'
    assert all(len(u['attempt_paths']) == 3 for u in shown['units'])
    assert len({u['request_sha256'] for u in shown['units']}) == 2


def test_requests_use_the_frozen_contract_first_party_routing_and_no_fallback(inputs):
    for generator in inputs['generators']:
        body = nat.request(generator)
        assert body['provider']['allow_fallbacks'] is False and body['provider']['require_parameters'] is True
        assert body['provider']['order'] == generator['entry']['provider_order']
        assert body['model'] == generator['entry']['model']
        assert not {'models', 'route', 'tools'} & body.keys()
        assert json.loads(body['messages'][1]['content']) == gq.project(generator['fixture'])
    nat_config = inputs['config']['naturalization']
    assert (nat_config['contract_sha256'], nat_config['prompt_sha256'], nat_config['output_schema_sha256']) == (
        q.CONTRACT_HASH, q.PROMPT_HASH, q.SCHEMA_HASH)
    models = {g['entry']['model'] for g in inputs['generators']}
    assert models == {'openai/gpt-5.6-sol', 'anthropic/claude-fable-5.1'}
    assert not {'terra', 'sonnet', 'opus'} & {p for m in models for p in m.replace('/', '-').split('-')}


def test_preview_and_cli_create_nothing_and_call_nothing(inputs, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert nat.main([]) == 0
    assert json.loads(capsys.readouterr().out)['planned_units'] == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('flags', [['--execute'], ['--confirm-spend']])
def test_execution_needs_both_flags(flags):
    with pytest.raises(SystemExit):
        nat.main(flags)


def test_execution_needs_an_explicit_frozen_output_directory(tmp_path):
    with pytest.raises(SystemExit):
        nat.main(['--execute', '--confirm-spend'])
    with pytest.raises(ValueError, match='frozen result directory'):
        nat.main(['--execute', '--confirm-spend', '--output-directory', str(tmp_path / 'elsewhere')])


# --- Live path (mock transport only) ------------------------------------------------------------------

def test_mocked_collection_runs_exactly_two_units_in_order_and_archives_everything(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    result, bodies = run_naturalization(inputs, path)
    assert result['status'] == 'COMPLETE' and len(bodies) == 2
    assert [b['model'] for b in bodies] == ['openai/gpt-5.6-sol', 'anthropic/claude-fable-5.1']
    assert [probe.digest(probe.canonical(b).encode()) for b in bodies] == [
        u['request_sha256'] for u in nat.preview(inputs)['units']]
    assert files(path) == ['SHA256SUMS', 'collection.json', 'pilot-scheduling-01/attempt-01.json',
                           'pilot-scheduling-01/unit.json', 'pilot-travel-01/attempt-01.json',
                           'pilot-travel-01/unit.json']
    assert [(u['outcomes'], u['decision'], u['accepted_attempt']) for u in result['units']] == [
        (['EVALUABLE_PASS'], 'ACCEPT', 1)] * 2
    assert KEY not in ' '.join(p.read_text(encoding='utf-8') for p in path.rglob('*') if p.is_file())
    provenance = result['provenance']
    assert provenance['source_commit'] == '0' * 40 and provenance['qualification_implementation']['status'] == q.FROZEN
    assert set(provenance['implementation']) == set(nat.IMPLEMENTATION)


def test_terminal_failure_retries_the_same_unit_with_the_same_request_and_archives_each_attempt(
        inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    result, bodies = run_naturalization(inputs, path, replies=['garbage', 'garbage'])
    assert result['status'] == 'COMPLETE' and len(bodies) == 4
    assert bodies[0] == bodies[1] == bodies[2] and bodies[3]['model'] == 'anthropic/claude-fable-5.1'
    first = result['units'][0]
    assert first['outcomes'] == ['TERMINAL_FAILURE', 'TERMINAL_FAILURE', 'EVALUABLE_PASS']
    assert first['logical_attempts'] == 3 and first['accepted_attempt'] == 3
    names = files(path)
    assert {f'pilot-scheduling-01/attempt-0{n}.json' for n in (1, 2, 3)} <= set(names)
    failed = json.loads((path / 'pilot-scheduling-01/attempt-01.json').read_text(encoding='utf-8'))
    assert failed['status'] == 'FAIL' and failed['outcome'] == 'TERMINAL_FAILURE'
    assert failed['request_body'] == bodies[0]


def test_three_terminal_failures_make_the_unit_unbuildable_and_stop_before_the_next_unit(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    result, bodies = run_naturalization(inputs, path, replies=['garbage'] * 3)
    assert result['status'] == 'STOPPED' and len(bodies) == 3
    assert {b['model'] for b in bodies} == {'openai/gpt-5.6-sol'}
    assert result['units'][0]['decision'] == 'UNBUILDABLE_STOP_FOR_RESEARCHER'
    assert 'STOP FOR RESEARCHER DECISION' in result['failure_reason'] and len(result['units']) == 1
    assert not (path / 'pilot-travel-01').exists()


def test_infrastructure_terminal_failure_is_a_terminal_attempt_not_a_substitution(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    result, bodies = run_naturalization(inputs, path, replies=[lambda b: httpx.Response(400, json={'error': 'x'})])
    assert result['units'][0]['outcomes'][0] == 'TERMINAL_FAILURE' and result['status'] == 'COMPLETE'
    assert {b['model'] for b in bodies[:2]} == {'openai/gpt-5.6-sol'}


def test_level_1_semantic_failure_is_never_regenerated(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'

    def corrupt(output):
        generator = inputs['generators'][0]
        hard = next(k for k in generator['fixture']['reference']['state_keys'] if k['state_key'] == 'k_hard')
        output['low']['U7'] += f' Also {hard["value_inventory"][1]}.'
        return output
    result, bodies = run_naturalization(inputs, path, override=lambda o: corrupt(o) if 'Brindle' in o['low']['U7'] else o)
    assert result['status'] == 'STOPPED' and len(bodies) == 1
    unit = result['units'][0]
    assert unit['outcomes'] == ['EVALUABLE_LEVEL1_FAILURE'] and unit['decision'] == 'STOP_FOR_RESEARCHER'
    assert unit['accepted_attempt'] is None and 'STOP FOR RESEARCHER DECISION' in result['failure_reason']


def test_no_field_mixing_or_manual_completion_across_attempts(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    run_naturalization(inputs, path, replies=['garbage'])
    outputs = nat.accepted_outputs(path, inputs)
    record, parsed = outputs['pilot-scheduling-01']
    assert record['unit_attempt'] == 2 and parsed == good_output(inputs['generators'][0]['fixture'])


def refuse(inputs, path, monkeypatch, *, key=KEY, git=fake_git, match):
    monkeypatch.setattr(nat, 'git', git)

    def no_client(**kwargs):
        pytest.fail('A client must not be created')
    with pytest.raises(Exception, match=match):
        asyncio.run(nat.collect(inputs, key, path, client_factory=no_client, sleep=lambda s: None))
    assert not Path(path).exists()


def test_collection_refuses_a_blank_key(inputs, tmp_path, monkeypatch):
    refuse(inputs, tmp_path / 'a', monkeypatch, key='  ', match='OPENROUTER_API_KEY')


def test_collection_refuses_a_dirty_worktree(inputs, tmp_path, monkeypatch):
    dirty = lambda *a: b' M file\0' if a[0] == 'status' else fake_git(*a)
    refuse(inputs, tmp_path / 'a', monkeypatch, git=dirty, match='clean worktree')


def test_collection_refuses_untracked_implementation_files(inputs, tmp_path, monkeypatch):
    import subprocess

    def untracked(*a):
        if a[0] == 'ls-files':
            raise subprocess.CalledProcessError(1, 'git')
        return fake_git(*a)
    refuse(inputs, tmp_path / 'a', monkeypatch, git=untracked, match='git')


def test_collection_refuses_a_non_frozen_directory_inside_the_pilot_namespace(inputs, monkeypatch):
    refuse(inputs, ROOT / 'results/crst-small-pilot/naturalization/attempt-02', monkeypatch,
           match='planned naturalization directory')


def test_collection_refuses_when_source_or_inputs_change_after_preflight(inputs, tmp_path, monkeypatch):
    real, calls = nat.provenance, []

    def drifting(value):
        calls.append(1)
        return {**real(value), 'source_commit': str(len(calls))}
    monkeypatch.setattr(nat, 'provenance', drifting)
    refuse(inputs, tmp_path / 'a', monkeypatch, match='changed since preflight')


def test_collection_refuses_when_qualification_implementation_is_not_frozen(inputs, tmp_path, monkeypatch):
    real = nat.provenance
    monkeypatch.setattr(nat, 'provenance', lambda value: {
        **real(value), 'qualification_implementation': {'status': q.NOT_FROZEN}})
    refuse(inputs, tmp_path / 'a', monkeypatch, match='live execution refused')


def test_existing_collection_directory_is_never_overwritten(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    run_naturalization(inputs, path)
    before = {n: (path / n).read_bytes() for n in files(path)}
    with pytest.raises(FileExistsError):
        run_naturalization(inputs, path)
    assert {n: (path / n).read_bytes() for n in files(path)} == before


def test_guard_allows_only_the_planned_directory_inside_the_pilot_namespace(inputs):
    config = inputs['config']
    nat.guard_output(ROOT / config['naturalization']['result_directory'], config)
    for bad in ('results/crst-small-pilot', 'results/crst-small-pilot/naturalization/attempt-02',
                'results/crst-small-pilot/naturalization/attempt-01/x', 'results/crst-small-pilot/backbone/attempt-01'):
        with pytest.raises(Exception):
            nat.guard_output(ROOT / bad, config)


def test_collection_writes_nothing_inside_the_repository_results(inputs, tmp_path, git):
    run_naturalization(inputs, tmp_path / 'attempt-01')


# --- Step C audit ---------------------------------------------------------------------------------------

@pytest.fixture()
def collected(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    run_naturalization(inputs, path)
    return path


def test_audit_of_a_clean_collection_is_eligible_and_binds_the_collection(inputs, collected):
    record = nat.audit(collected, inputs, ToyTokenizer())
    assert record['status'] == 'ELIGIBLE' and record['semantic_status'] == 'PASS' and record['findings'] == {}
    assert record['collection_sha256'] == probe.file_hash(collected / 'collection.json')
    assert all(c['status'] == 'RETAINED' and c['history_tokens'] <= 71 and c['selected_events'][-2:] == ['U7', 'N2']
               for u in record['units'] for c in u['b0_coverage'].values())
    assert len(record['units']) == 2 and record['b0_budget'] == 71


def test_audit_refuses_an_incomplete_or_tampered_collection(inputs, collected, tmp_path, git):
    (collected / 'pilot-travel-01/attempt-01.json').write_text('{}')
    with pytest.raises(Exception, match='drifted'):
        nat.audit(collected, inputs, ToyTokenizer())
    stopped = tmp_path / 'stopped'
    run_naturalization(inputs, stopped, replies=['garbage'] * 3)
    with pytest.raises(Exception):
        nat.audit(stopped, inputs, ToyTokenizer())


def test_b0_coverage_failure_makes_the_collection_not_eligible(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'

    def long_text(output):
        for variant in output.values():
            for label in ('U7', 'N2'):
                variant[label] += ' word' * 80
        return output
    run_naturalization(inputs, path, override=long_text)
    record = nat.audit(path, inputs, ToyTokenizer())
    assert record['status'] == 'NOT_ELIGIBLE'
    assert any(c['status'] == 'COVERAGE_FAILURE' for u in record['units'] for c in u['b0_coverage'].values())


def test_manual_review_findings_need_a_bound_researcher_review(inputs, tmp_path, git):
    path = tmp_path / 'attempt-01'
    run_naturalization(inputs, path, override=lambda o: {v: {**b, 'N1': 'Nothing more to report here.'}
                                                  for v, b in o.items()})
    pending = nat.audit(path, inputs, ToyTokenizer())
    assert pending['status'] == 'PENDING_RESEARCHER_REVIEW' and pending['findings']

    def review(decision, **extra):
        payload = {'schema_version': nat.REVIEW, 'collection_sha256': probe.file_hash(path / 'collection.json'),
                   'finding_decisions': {k: decision for k in pending['findings']}, **extra}
        target = tmp_path / f'review-{decision}-{len(extra)}.json'
        target.write_text(json.dumps(payload))
        return target
    assert nat.audit(path, inputs, ToyTokenizer(), review('ACCEPT'))['status'] == 'ELIGIBLE'
    assert nat.audit(path, inputs, ToyTokenizer(), review('REJECT'))['status'] == 'NOT_ELIGIBLE'
    with pytest.raises(Exception):
        nat.audit(path, inputs, ToyTokenizer(), review('ACCEPT', extra_field=1))
    partial = tmp_path / 'partial.json'
    partial.write_text(json.dumps({'schema_version': nat.REVIEW, 'finding_decisions': {},
                                   'collection_sha256': probe.file_hash(path / 'collection.json')}))
    with pytest.raises(Exception):
        nat.audit(path, inputs, ToyTokenizer(), partial)
    other = tmp_path / 'other.json'
    other.write_text(json.dumps({'schema_version': nat.REVIEW, 'collection_sha256': '0' * 64,
                                 'finding_decisions': {k: 'ACCEPT' for k in pending['findings']}}))
    with pytest.raises(Exception):
        nat.audit(path, inputs, ToyTokenizer(), other)


def test_only_an_eligible_bound_audit_releases_the_naturalized_texts(inputs, collected, tmp_path):
    record = nat.audit(collected, inputs, ToyTokenizer())
    target = tmp_path / 'audit.json'
    q.publish(target, record)
    texts, loaded = nat.load_eligible(target, collected, inputs)
    assert set(texts) == {'pilot-scheduling-01', 'pilot-travel-01'} and loaded['status'] == 'ELIGIBLE'
    assert texts['pilot-travel-01']['low']['Q'] == good_output(inputs['generators'][1]['fixture'])['low']['Q']
    for status in ('NOT_ELIGIBLE', 'PENDING_RESEARCHER_REVIEW'):
        bad = tmp_path / f'{status}.json'
        bad.write_text(json.dumps({**record, 'status': status}))
        with pytest.raises(Exception, match='not ELIGIBLE'):
            nat.load_eligible(bad, collected, inputs)
    drifted = tmp_path / 'drift.json'
    drifted.write_text(json.dumps({**record, 'collection_sha256': '0' * 64}))
    with pytest.raises(Exception, match='does not belong'):
        nat.load_eligible(drifted, collected, inputs)


def test_audit_output_is_immutable(inputs, collected, tmp_path):
    record = nat.audit(collected, inputs, ToyTokenizer())
    target = tmp_path / 'audit.json'
    q.publish(target, record)
    with pytest.raises(FileExistsError):
        q.publish(target, record)


def test_pilot_workflow_requires_naturalization_before_the_backbone():
    config = run.load_config()
    steps = {s['step']: s for s in config['workflow']}
    assert list(steps) == list('ABCDEF') and steps['B']['live'] and steps['D']['live']
    assert steps['D']['requires'] == 'eligible naturalization' and not steps['C']['live']
