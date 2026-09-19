"""Mocked qualification tests: no naturalization service is invoked."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments'))
import qualify_generators as q


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)


@pytest.fixture(scope='module')
def loaded():
    return q.load_inputs()


@pytest.fixture
def inputs(loaded):
    """Simulated frozen implementation: live execution also requires a committed freeze record."""
    frozen = deepcopy(loaded)
    frozen['provenance']['implementation'].update(status=q.FROZEN, freeze_commit='f' * 40)
    return frozen


def mock_output(truth):
    r = truth['reference']
    keys = {k['state_key']: k for k in r['state_keys']}
    names = {e['entity_id']: e['name'] for e in r['entities']}
    attrs = {a['attribute_id']: a['meaning'] for a in r['attributes']}
    question = r['question_intent']
    return {v: {**{e['event']: f"{names[keys[e['state_key']]['entity_id']]}: {attrs[keys[e['state_key']]['attribute_id']]} is now {e['current_value']}."
                     for e in r['variants'][v]['events']},
                'Q': f"What is the {attrs[question['attribute_id']]} of {names[question['entity_id']]}?"}
            for v in q.fixtures.VARIANTS}


def envelope(body, output):
    return {'model': body['model'], 'id': 'fake-response',
            'openrouter_metadata': {'endpoints': {'available': [
                {'provider': body['provider']['order'][0], 'selected': True}]}},
            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(output)}}]}


def fake_git(*args):
    """Real bytes for the three SOURCES paths (so verify_archived_implementation authenticates
    correctly against the real current file content); empty for every other call (status/ls-files/
    merge-base all just need a falsy/no-exception result).
    """
    if args[:1] == ('show',) and ':' in args[1]:
        path = args[1].split(':', 1)[1]
        if path in q.SOURCES:
            return (q.ROOT / path).read_bytes()
    return b''


def mocked_collect(inputs, tmp_path, monkeypatch, mutate=None):
    monkeypatch.setattr(q, 'git', fake_git)
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None, protocol='v1': inputs)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        index = len(calls)
        calls.append(body)
        reply = envelope(body, mock_output(inputs['fixtures'][index % 12]))
        if mutate:
            mutate(index, reply)
        return httpx.Response(200, json=reply)
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    path = tmp_path / 'attempt'
    async def no_wait(seconds): pass
    result = asyncio.run(q.collect(inputs, 'test-secret', path, client_factory=factory, sleep=no_wait))
    return result, calls, path


def test_preview_and_request_package(inputs, tmp_path, capsys):
    path = tmp_path / 'absent'
    assert q.main(['--output-directory', str(path)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['credits'] == 'CREDITS_NOT_SPENT'
    assert shown['planned_logical_calls'] == 24 and shown['maximum_physical_attempts'] == 72
    assert not path.exists()
    bodies = [q.request(inputs, s, f) for s, f, _ in q.plan(inputs)]
    assert [b['model'] for b in bodies] == [q.probe.SLOTS[0]['model']] * 12 + [q.probe.SLOTS[1]['model']] * 12
    for b in bodies:
        assert b['max_tokens'] == 16384 and b['reasoning'] == {'effort': 'low'}
        assert b['provider']['allow_fallbacks'] is False and b['provider']['require_parameters'] is True
        assert not {'temperature', 'top_p', 'tools'} & b.keys()
        assert b['response_format']['json_schema']['strict'] is True
        assert b['messages'][0]['content'] == inputs['bundle']['contract']['prompt']
        q.fixtures.validate_input(json.loads(b['messages'][1]['content']))


@pytest.mark.parametrize('flags', [['--execute'], ['--confirm-spend']])
def test_one_flag_blocked(flags, tmp_path):
    with pytest.raises(SystemExit):
        q.main(flags + ['--output-directory', str(tmp_path / 'absent')])
    assert not (tmp_path / 'absent').exists()


def test_missing_key(monkeypatch, tmp_path):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with pytest.raises(ValueError, match='API_KEY'):
        q.main(['--execute', '--confirm-spend', '--output-directory', str(tmp_path / 'absent')])
    assert not (tmp_path / 'absent').exists()


@pytest.mark.parametrize('state', ['clean', 'modified', 'staged', 'untracked', 'runner_untracked'])
def test_real_git_execution_boundary(inputs, tmp_path, monkeypatch, state):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)
    git('init')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Test')
    (repo / 'experiments').mkdir()
    for source in q.SOURCES:
        (repo / source).write_text('tracked test placeholder')
    runner = repo / 'experiments/qualify_generators.py'
    (repo / '.gitignore').write_text('ignored\n')
    git('add', '.')
    git('commit', '-m', 'test baseline')
    (repo / 'ignored').write_text('harmless')
    if state in ('modified', 'staged'):
        runner.write_text('modified')
        if state == 'staged': git('add', '.')
    elif state == 'untracked':
        (repo / 'new.py').write_text('new')
    elif state == 'runner_untracked':
        git('rm', '--cached', 'experiments/qualify_generators.py')
        (repo / '.gitignore').write_text('ignored\nexperiments/qualify_generators.py\n')
        git('add', '.')
        git('commit', '-m', 'remove runner')
    monkeypatch.setattr(q, 'ROOT', repo)
    reached = []
    def boundary(profile='primary', slot=None, protocol='v1'):
        reached.append(True)
        raise RuntimeError('mock execution boundary')
    monkeypatch.setattr(q, 'load_inputs', boundary)
    output = tmp_path / 'absent'
    with pytest.raises((ValueError, RuntimeError, subprocess.CalledProcessError)):
        asyncio.run(q.collect(inputs, 'test-secret', output))
    assert reached == ([True] if state == 'clean' else [])
    assert not output.exists()


@pytest.mark.parametrize('kind', ['manifest', 'fixture', 'projection', 'package', 'prompt', 'schema', 'provenance'])
def test_frozen_drift(inputs, monkeypatch, kind):
    if kind in ('manifest', 'package'):
        original = q.probe.file_hash
        suffix = 'manifest.json' if kind == 'manifest' else 'generator-capability-probe.yaml'
        monkeypatch.setattr(q.probe, 'file_hash', lambda p: '0' * 64 if str(p).endswith(suffix) else original(p))
    elif kind in ('fixture', 'projection'):
        original = q.fixtures.read
        def read(path):
            obj = original(path)
            if kind == 'fixture' and str(path).endswith('scheduling.json'):
                obj['reference']['gold_current_value'] = 'wrong'
            elif kind == 'projection' and str(path).endswith('manifest.json'):
                obj['fixtures'][0]['projection_sha256'] = '0' * 64
            return obj
        monkeypatch.setattr(q.fixtures, 'read', read)
    elif kind in ('prompt', 'schema'):
        bundle = deepcopy(inputs['bundle'])
        bundle['provenance']['prompt_sha256' if kind == 'prompt' else 'output_schema_sha256'] = '0' * 64
        monkeypatch.setattr(q.probe, 'load_bundle', lambda *a, **k: bundle)
    else:
        monkeypatch.setattr(q, 'git', lambda *args: b'incorrect committed bytes')
    with pytest.raises(ValueError):
        q.load_inputs()


@pytest.mark.parametrize('mutation', ['malformed', 'duplicate', 'missing_variant', 'extra_variant',
                                    'missing_event', 'extra_event', 'nonstring', 'empty'])
def test_parser_schema(inputs, mutation):
    out = mock_output(inputs['fixtures'][0])
    if mutation == 'malformed': raw = '{'
    elif mutation == 'duplicate': raw = '{"low":{},"low":{}}'
    else:
        if mutation == 'missing_variant': del out['high']
        if mutation == 'extra_variant': out['extra'] = {}
        if mutation == 'missing_event': del out['low']['N1']
        if mutation == 'extra_event': out['low']['extra'] = 'x'
        if mutation == 'nonstring': out['low']['I1'] = 1
        if mutation == 'empty': out['low']['I1'] = '  '
        raw = json.dumps(out)
    with pytest.raises(ValueError):
        q.probe.validate_output(q.probe.parse_json(raw))


@pytest.mark.parametrize('kind', ['correct', 'stale', 'wrong', 'n1', 'n2', 'q_answer', 'q_entity', 'q_attribute', 'q_different', 'paraphrase', 'overlap'])
def test_semantic_checks(inputs, kind):
    truth = deepcopy(inputs['fixtures'][0])
    out = mock_output(truth)
    if kind == 'stale': out['low']['U7'] += ' Previously 08:10.'
    if kind == 'wrong': out['low']['U7'] += ' 13:20.'
    if kind == 'n1': out['high']['N1'] = 'Tern rehearsal is at 08:10.'
    if kind == 'n2': out['low']['N2'] = 'Tern rehearsal has 45 minutes.'
    if kind.startswith('q_'):
        for v in q.fixtures.VARIANTS:
            if kind == 'q_answer': out[v]['Q'] += ' 12:05?'
            if kind == 'q_entity': out[v]['Q'] = out[v]['Q'].replace('Tern', 'Gull')
            if kind == 'q_attribute': out[v]['Q'] = 'What is the rehearsal duration of Tern rehearsal?'
        if kind == 'q_different': out['high']['Q'] += ' Please.'
    if kind == 'paraphrase': out['low']['I1'] = 'Tern rehearsal starts at eight ten.'
    if kind == 'overlap': truth['reference']['state_keys'][1]['value_inventory'].append('Room')
    result = q.semantic_check(truth, out)
    assert result['status'] == ('PASS' if kind == 'correct' else
                               'MANUAL_REVIEW_REQUIRED' if kind in ('paraphrase', 'overlap') else 'FAIL')


@pytest.mark.parametrize('kind', ['success', 'model', 'provider', 'refusal', 'truncation', 'usage', 'malformed', 'semantic'])
def test_mock_collection_continuation_and_replay(inputs, tmp_path, monkeypatch, kind):
    def mutate(index, reply):
        if index: return
        if kind == 'model': reply['model'] = 'wrong'
        if kind == 'provider': reply['openrouter_metadata']['endpoints']['available'][0]['provider'] = 'wrong'
        if kind == 'refusal': reply['choices'][0]['message']['refusal'] = 'refused'
        if kind == 'truncation': reply['choices'][0]['finish_reason'] = 'length'
        if kind == 'usage': reply['usage'] = {'prompt_tokens': -1}
        if kind == 'malformed': reply['choices'][0]['message']['content'] = '{}'
        if kind == 'semantic':
            out = json.loads(reply['choices'][0]['message']['content'])
            out['low']['U7'] += ' 08:10.'
            reply['choices'][0]['message']['content'] = json.dumps(out)
    result, calls, path = mocked_collect(inputs, tmp_path, monkeypatch, mutate)
    invalid = kind in ('model', 'provider', 'usage')
    assert len(calls) == (1 if invalid else 24)
    assert result['status'] == ('INVALIDATED' if invalid else 'PENDING_MANUAL_AUDIT')
    assert (result['invalidation'] or {}).get('kind') == (q.CONTRACT if invalid else None)
    assert q.replay(path, inputs)[0] == result
    if kind == 'success':
        assert all(c['automated']['status'] == 'PASS' for c in result['calls'])
        assert all(v is None for v in result['calls'][0]['attempts'][0]['usage'].values())
    assert 'test-secret' not in (path / 'qualification.json').read_text()
    with pytest.raises(FileExistsError):
        asyncio.run(q.collect(inputs, 'test-secret', path))


REVIEWED_AT = '2026-09-18T21:30:00+07:00'


def fill_audit(audit):
    audit['reviewer'], audit['reviewed_at'] = 'test-reviewer', REVIEWED_AT
    for candidate in audit['candidates'].values():
        candidate['disposition'] = 'PASS'
        for f in candidate['fixtures'].values():
            f['disposition'] = 'PASS'
            for resolution in f['ambiguities'].values():
                resolution.update(disposition='PASS', notes='Manually resolved in simulated test')
            for variant in f['variants'].values():
                variant['disposition'] = 'PASS'
                for event in variant['events'].values():
                    for key in q.CHECKS:
                        if event[key] is None: event[key] = 'PASS'


def collected(inputs, tmp_path, monkeypatch, mutate=None):
    result, _, path = mocked_collect(inputs, tmp_path, monkeypatch, mutate)
    return result, q.fixtures.read(path / 'manual-audit.json'), q.probe.file_hash(path / 'qualification.json'), path


def first_call(content):
    def mutate(index, reply):
        if index == 0:
            reply['choices'][0]['message']['content'] = content(json.loads(reply['choices'][0]['message']['content']))
    return mutate


def verdict(result, audit, checksum):
    return q.adjudicate(result, audit, checksum)['candidates']


def test_all_valid_complete_manual_pass_qualifies(inputs, tmp_path, monkeypatch):
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    assert sum(len(v['events']) for c in audit['candidates'].values() for f in c['fixtures'].values()
               for v in f['variants'].values()) == 24 * 3 * 17
    assert set(verdict(result, audit, checksum).values()) == {'PENDING_MANUAL_AUDIT'}
    fill_audit(audit)
    assert verdict(result, audit, checksum) == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}
    for holdout in ('fixture', 'variant', 'event', 'candidate'):
        partial = deepcopy(audit)
        g1 = partial['candidates']['G1']
        record = g1['fixtures']['gq-travel-01']
        if holdout == 'fixture': record['disposition'] = None
        if holdout == 'variant': record['variants']['high']['disposition'] = None
        if holdout == 'event': record['variants']['high']['events']['Q']['answer_leakage'] = None
        if holdout == 'candidate': g1['disposition'] = None
        assert verdict(result, partial, checksum) == {'G1': 'PENDING_MANUAL_AUDIT', 'G2': 'QUALIFIED'}
    anonymous = deepcopy(audit)
    anonymous['reviewer'] = ' '
    with pytest.raises(ValueError, match='reviewer'): q.adjudicate(result, anonymous, checksum)


@pytest.mark.parametrize('kind', ['malformed_json', 'schema_invalid', 'refusal', 'truncation'])
def test_terminal_call_failure_fails_without_manual_records(inputs, tmp_path, monkeypatch, kind):
    def mutate(index, reply):
        if index: return
        choice = reply['choices'][0]
        if kind == 'malformed_json': choice['message']['content'] = '{"low":'
        if kind == 'schema_invalid': choice['message']['content'] = '{}'
        if kind == 'refusal': choice['message']['refusal'] = 'refused'
        if kind == 'truncation': choice['finish_reason'] = 'length'
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch, mutate)
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(result['calls']) == 24  # G1 continued, G2 ran.
    record = audit['candidates']['G1']['fixtures']['gq-scheduling-01']
    assert record['call_status'] == 'FAIL' and record['variants'] == {} and record['ambiguities'] == {}
    assert record['output_sha256'] is None
    blank = q.adjudicate(result, audit, checksum)
    assert blank['candidates'] == {'G1': 'FAIL', 'G2': 'PENDING_MANUAL_AUDIT'}
    assert blank['basis']['G1']['terminal_failures'][0].startswith('gq-scheduling-01: terminal logical-call failure')
    fill_audit(audit)
    with pytest.raises(ValueError, match='contradicts'):  # A terminal failure can never be reviewed into PASS.
        q.adjudicate(result, audit, checksum)
    record['disposition'], record['notes'] = 'FAIL', 'Terminal call failure'
    with pytest.raises(ValueError, match='Candidate PASS contradicts'):
        q.adjudicate(result, audit, checksum)
    audit['candidates']['G1']['disposition'] = 'FAIL'
    assert verdict(result, audit, checksum) == {'G1': 'FAIL', 'G2': 'QUALIFIED'}


def test_deterministic_semantic_fail_with_incomplete_audit(inputs, tmp_path, monkeypatch):
    def stale(out):
        out['low']['U7'] += ' 08:10.'
        return json.dumps(out)
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch, first_call(stale))
    assert result['calls'][0]['automated']['status'] == 'FAIL'
    assert audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']  # Still reviewable, not required.
    outcome = q.adjudicate(result, audit, checksum)
    assert outcome['candidates'] == {'G1': 'FAIL', 'G2': 'PENDING_MANUAL_AUDIT'}
    assert outcome['basis']['G1']['terminal_failures'] == ['gq-scheduling-01: deterministic automated semantic FAIL']


def test_manual_review_required_pending_until_resolved(inputs, tmp_path, monkeypatch):
    def paraphrase(out):
        out['low']['I1'] = 'Tern rehearsal starts at eight ten.'
        return json.dumps(out)
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch, first_call(paraphrase))
    assert result['calls'][0]['automated']['status'] == 'MANUAL_REVIEW_REQUIRED'
    ambiguities = audit['candidates']['G1']['fixtures']['gq-scheduling-01']['ambiguities']
    assert ambiguities and all(r == {'disposition': None, 'notes': ''} for r in ambiguities.values())
    fill_audit(audit)
    for r in ambiguities.values(): r.update(disposition=None, notes='')
    assert verdict(result, audit, checksum) == {'G1': 'PENDING_MANUAL_AUDIT', 'G2': 'QUALIFIED'}
    for r in ambiguities.values(): r['disposition'] = 'PASS'
    with pytest.raises(ValueError, match='notes'): q.adjudicate(result, audit, checksum)
    for r in ambiguities.values(): r['notes'] = 'Spelled-out clock time is faithful'
    assert verdict(result, audit, checksum) == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}
    failed = next(iter(ambiguities.values()))
    failed.update(disposition='FAIL', notes='Value is not the assigned current value')
    with pytest.raises(ValueError, match='Fixture PASS contradicts'): q.adjudicate(result, audit, checksum)
    record = audit['candidates']['G1']['fixtures']['gq-scheduling-01']
    record['disposition'], record['notes'] = 'FAIL', 'Ambiguity resolved FAIL'
    audit['candidates']['G1']['disposition'] = 'FAIL'
    assert verdict(result, audit, checksum) == {'G1': 'FAIL', 'G2': 'QUALIFIED'}


def test_completed_manual_check_fail(inputs, tmp_path, monkeypatch):
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    audit['reviewer'], audit['reviewed_at'] = 'test-reviewer', REVIEWED_AT
    event = audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']
    event['entity_fidelity'] = 'FAIL'
    with pytest.raises(ValueError, match='evidence notes'): q.adjudicate(result, audit, checksum)
    event['notes'] = 'Entity renamed'
    # One completed manual FAIL resolves FAIL while other items remain unreviewed.
    assert verdict(result, audit, checksum) == {'G1': 'FAIL', 'G2': 'PENDING_MANUAL_AUDIT'}
    audit['candidates']['G2']['disposition'] = 'FAIL'
    with pytest.raises(ValueError, match='Candidate FAIL without'): q.adjudicate(result, audit, checksum)


def test_manual_check_applicability(inputs, tmp_path, monkeypatch):
    applicable = {c: {e for e in q.EVENTS if q.applicable(c, e)} for c in q.CHECKS}
    assert applicable['changed_vs_hypothetical_wording'] == {f'U{i}' for i in range(1, 8)}
    assert applicable['same_state_fidelity'] == {'N1', 'N2'}
    assert applicable['q_intent_fidelity'] == applicable['answer_leakage'] == {'Q'}
    assert applicable['current_value_fidelity'] == set(q.EVENTS) - {'Q'}
    assert applicable['superseded_value_leakage'] == set(q.EVENTS) - {f'I{i}' for i in range(1, 8)}
    for check in ('natural_english', 'entity_fidelity', 'attribute_fidelity', 'output_boundary',
                  'invented_information_or_state_change', 'merged_or_omitted_event'):
        assert applicable[check] == set(q.EVENTS)
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    events = audit['candidates']['G2']['fixtures']['gq-travel-01']['variants']['medium']['events']
    for event, checks in events.items():
        assert {c for c in q.CHECKS if checks[c] is None} == {c for c in q.CHECKS if event in applicable[c]}
        assert {c for c in q.CHECKS if checks[c] == 'NA'} == {c for c in q.CHECKS if event not in applicable[c]}
    assert audit['check_applicability'] == {c: list(e) for c, e in q.APPLICABILITY.items()}
    fill_audit(audit)
    for value in ('PASS', None):
        changed = deepcopy(audit)
        changed['candidates']['G2']['fixtures']['gq-travel-01']['variants']['medium']['events']['I1']['answer_leakage'] = value
        with pytest.raises(ValueError, match='applicability'): q.adjudicate(result, changed, checksum)
    changed = deepcopy(audit)
    changed['candidates']['G2']['fixtures']['gq-travel-01']['variants']['medium']['events']['Q']['q_intent_fidelity'] = 'NA'
    with pytest.raises(ValueError, match='check value'): q.adjudicate(result, changed, checksum)
    changed = deepcopy(audit)
    changed['check_applicability']['answer_leakage'] = list(q.EVENTS)
    with pytest.raises(ValueError, match='provenance'): q.adjudicate(result, changed, checksum)


def reseal(path, result=None, extra=None):
    """Rewrite evidence as a consistent-but-tampered archive, so replay's semantic gates are tested."""
    result = result or q.fixtures.read(path / 'qualification.json')
    for call in result['calls']:
        entry = next(e for e in q.fixtures.read(q.fixtures.DIRECTORY / 'manifest.json')['fixtures']
                     if e['fixture_id'] == call['fixture_id'])
        (path / q.evidence_path({'logical_call_id': call['candidate']}, entry)).unlink()
        q.publish(path / q.evidence_path({'logical_call_id': call['candidate']}, entry), call)
    for name in ('qualification.json', 'manual-audit.json', 'SHA256SUMS'):
        (path / name).unlink()
    sums = {q.evidence_path({'logical_call_id': c['candidate']}, {'fixture_id': c['fixture_id']}):
            q.probe.file_hash(path / 'outputs' / c['candidate'].lower() / f'{c["fixture_id"]}.json')
            for c in result['calls']}
    sums['qualification.json'] = q.publish(path / 'qualification.json', result)
    sums['manual-audit.json'] = q.publish(path / 'manual-audit.json', q.audit_template(result, sums['qualification.json']))
    lines = [f'{h}  {n}' for n, h in sorted(sums.items())] + (extra or [])
    (path / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')


def test_replay_rejects_altered_evidence(inputs, tmp_path, monkeypatch):
    result, _, _, path = collected(inputs, tmp_path, monkeypatch)
    reseal(path)
    assert q.replay(path, inputs)[0] == result  # The resealing helper itself is faithful.
    def attempt_copy(name):
        target = tmp_path / name
        subprocess.check_call(['cp', '-a', str(path), str(target)])
        return target
    checks = {}
    tampered = attempt_copy('checksum')
    (tampered / 'manual-audit.json').write_text('{}\n')
    checks['checksum'] = (tampered, 'checksum mismatch')
    for name, line in [('unsafe', '0' * 64 + '  ../escape.json'), ('absolute', '0' * 64 + '  /etc/passwd'),
                       ('duplicate', None), ('malformed', 'not a checksum line')]:
        tampered = attempt_copy(name)
        text = (tampered / 'SHA256SUMS').read_text()
        (tampered / 'SHA256SUMS').write_text(text + (text.splitlines()[0] if line is None else line) + '\n')
        checks[name] = (tampered, {'duplicate': 'Duplicate', 'malformed': 'Malformed'}.get(name, 'Unsafe'))
    tampered = attempt_copy('unlisted')
    (tampered / 'outputs/g1/notes.txt').write_text('unlisted')
    checks['unlisted'] = (tampered, 'Unlisted or missing')
    tampered = attempt_copy('missing_call')
    truncated = deepcopy(result)
    truncated['calls'].pop()
    (tampered / 'outputs/g2/gq-quantitative-planning-01.json').unlink()
    reseal(tampered, truncated)
    checks['missing_call'] = (tampered, 'Incomplete attempt')
    tampered = attempt_copy('reordered')
    swapped = deepcopy(result)
    swapped['calls'][0], swapped['calls'][1] = swapped['calls'][1], swapped['calls'][0]
    reseal(tampered, swapped)
    checks['reordered'] = (tampered, 'order')
    tampered = attempt_copy('template')
    template = q.fixtures.read(tampered / 'manual-audit.json')
    template['reviewer'] = 'edited in place'
    (tampered / 'manual-audit.json').unlink()
    digest = q.publish(tampered / 'manual-audit.json', template)
    text = (tampered / 'SHA256SUMS').read_text().splitlines()
    (tampered / 'SHA256SUMS').write_text('\n'.join(l if not l.endswith('manual-audit.json') else f'{digest}  manual-audit.json'
                                                  for l in text) + '\n')
    checks['template'] = (tampered, 'blank audit template drift')
    tampered = attempt_copy('unfrozen')
    unfrozen = deepcopy(result)
    unfrozen['provenance']['implementation']['status'] = q.NOT_FROZEN
    for call in unfrozen['calls']: call['provenance'] = unfrozen['provenance']
    reseal(tampered, unfrozen)
    checks['unfrozen'] = (tampered, 'without implementation freeze')
    for name, (directory, message) in checks.items():
        with pytest.raises(ValueError, match=message):
            q.replay(directory, inputs)


def test_replay_keeps_terminal_failures_terminal(inputs, tmp_path, monkeypatch):
    result, _, _, path = collected(inputs, tmp_path, monkeypatch, first_call(lambda out: '{}'))
    assert q.replay(path, inputs)[0] == result
    promoted = deepcopy(result)
    promoted['calls'][0].update(status='PASS', failure_reason=None)
    reseal(path, promoted)
    with pytest.raises(ValueError):  # Re-inspection of the archived response rejects it again.
        q.replay(path, inputs)
    relabelled = deepcopy(result)
    relabelled['calls'][0]['automated'] = {'status': 'PASS', 'findings': [], 'meaning': ''}
    reseal(path, relabelled)
    with pytest.raises(ValueError, match='Terminal failure altered'):
        q.replay(path, inputs)
    passing = deepcopy(result)
    passing['calls'][0]['attempts'][-1]['raw_response'] = result['calls'][1]['attempts'][-1]['raw_response']
    reseal(path, passing)
    with pytest.raises(ValueError):  # Swapping a passing response in cannot pass request/semantic replay.
        q.replay(path, inputs)


def test_offline_adjudication_cli_uses_separate_copy(inputs, tmp_path, monkeypatch, capsys):
    result, audit, _, path = collected(inputs, tmp_path, monkeypatch)
    fill_audit(audit)
    completed = tmp_path / 'completed-audit.json'
    completed.write_text(json.dumps(audit))
    output = tmp_path / 'adjudication.json'
    for bad_audit, bad_output in [(path / 'manual-audit.json', output), (completed, path / 'adjudication.json')]:
        with pytest.raises(ValueError, match='separate copies'):
            q.main(['--attempt', str(path), '--audit', str(bad_audit), '--adjudication-output', str(bad_output)])
    blank = q.probe.file_hash(path / 'manual-audit.json')
    assert q.main(['--attempt', str(path), '--audit', str(completed), '--adjudication-output', str(output)]) == 0
    capsys.readouterr()
    written = q.fixtures.read(output)
    assert written['candidates'] == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}
    assert written['manual_audit_file_sha256'] == q.probe.file_hash(completed)
    assert q.probe.file_hash(path / 'manual-audit.json') == blank
    with pytest.raises(FileExistsError):
        q.main(['--attempt', str(path), '--audit', str(completed), '--adjudication-output', str(output)])


FROZEN_HISTORICAL_COMMIT = 'e5e9d500d3e3f0805f5dfbce53eaed5d957ab74e'  # The first reviewed, committed freeze.
CURRENT_FROZEN_COMMIT = '585b5e2844504fec703287f8dd4869668615671d'  # The historical v1-era freeze (per-slot support).
# Hardcoded, independent of whatever the live repository's CURRENT bytes happen to be: these pin what
# the historical Protocol-v1-era freeze record itself must always say, so a future silent overwrite of
# v1 implementation provenance is caught even if someone also edited q.SOURCES' current live bytes.
HISTORICAL_FREEZE_RECORD_SHA256 = 'dd9d12ffdfe86e63788dc1facbacee81914c7374e6d548ff6594f03c3f896f4c'
HISTORICAL_QUALIFY_GENERATORS_SHA256 = '89f82fe9f617275d117d793f936ca1d81fd63aa2ed6f138a8bd8e5b4bc731258'
PROBE_GENERATORS_SHA256 = 'bf414f46d02400127ba60aa0af1bbcfd4f72c12acba0cdcc8718c9b34774c9cf'
VALIDATE_FIXTURES_SHA256 = '2b099896e4f63022dbe54c08eaa6d37a2ff781625907943e4bf30c26f3604f3e'
# Implementation freeze lineage (docs/generator-qualification.md Sec. 14). Every record is immutable and
# checked below against hardcoded values: the Protocol-v1-era record; v2 revision 1 (Commit A); v2 revision
# 2 (Commit C, deterministic v2 summaries); and v2 revision 3 (the second_level_g2 profile support), the
# current record. Revision suffixes name freeze revisions, not methodology versions.
V2_R1_FREEZE_RECORD = q.ROOT / 'configs/generator-qualification-implementation-freeze-v2.json'
V2_R1_FREEZE_RECORD_SHA256 = '9ff527e613a9d7096691c41216277c7e17705ca99515160016391d8d70a1d183'
V2_R2_FREEZE_RECORD_NAME = 'generator-qualification-implementation-freeze-v2-r2.json'
V2_R2_FREEZE_RECORD = q.ROOT / 'configs' / V2_R2_FREEZE_RECORD_NAME
V2_R3_FREEZE_RECORD_NAME = 'generator-qualification-implementation-freeze-v2-r3.json'
V2_R3_FREEZE_RECORD = q.ROOT / 'configs' / V2_R3_FREEZE_RECORD_NAME
V2_R3_FREEZE_RECORD_SHA256 = '335895b84454d5a327e2f600067550f645c6ba4d441f4cbd4e61a29508bf5231'
COMMIT_R3 = '45f06ae8508485ff2f4d5a886fef89f01bf1b807'  # feat: support second-level G2 generator profile
V2_R3_QUALIFY_GENERATORS_SHA256 = '6765c1e456a7223ea2108cb79851cbfd8858f0f7eba557beb67ff871afe5687d'
V2_R3_PROBE_GENERATORS_SHA256 = 'b48729d6603fa2f5abdf4c468d67ed7e00e335162abf4fbf7f86d680d33248c0'
V2_R2_FREEZE_RECORD_SHA256 = 'ddbeaee285d5874c2a4a7b6a38dab0262cafcd277449b7d1f073f0e9a497872a'
COMMIT_C = '30d65102e618aa5713f0710964978f1eb46c4a15'  # fix: derive protocol v2 qualification dispositions
V2_R2_QUALIFY_GENERATORS_SHA256 = '4f985518dec34731737794009f4c7841a3584dc0d11c1a9c83ee2e367644f09e'
V2_COMMIT_A_QUALIFY_GENERATORS_SHA256 = '38896235ec7a4b9b1fff59d2ae0d0ec6ef7c22ee567e131ac614ca8134355dc0'
COMMIT_A = '6412b368e9c49891510aeb73d1fa208442df3c01'  # feat: implement generator qualification protocol v2


def test_historical_v1_freeze_record_preserved_not_reinterpreted_as_current(loaded, capsys):
    """The historical Protocol-v1-era freeze record is immutable implementation provenance, checked
    here against its own hardcoded historical values -- independent of whatever the live repository's
    current bytes happen to be. Current qualify_generators.py has legitimately moved past it (Protocol-
    v2 support added on top): the runner correctly reports NOT_FROZEN, never a false FROZEN claim, and
    this historical record is never silently reinterpreted as validating that current state.
    """
    assert q.FREEZE_RECORD.exists()
    assert q.probe.file_hash(q.FREEZE_RECORD) == HISTORICAL_FREEZE_RECORD_SHA256
    committed = q.fixtures.read(q.FREEZE_RECORD)
    assert committed == {
        'schema_version': q.FREEZE_SCHEMA,
        'implementation_commit': CURRENT_FROZEN_COMMIT,
        'source_sha256': {
            'experiments/qualify_generators.py': HISTORICAL_QUALIFY_GENERATORS_SHA256,
            'experiments/probe_generators.py': PROBE_GENERATORS_SHA256,
            'experiments/validate_generator_qualification_fixtures.py': VALIDATE_FIXTURES_SHA256,
        },
    }
    implementation = loaded['provenance']['implementation']
    assert implementation['status'] == q.NOT_FROZEN and implementation['freeze_commit'] is None
    current = implementation['source_sha256']['experiments/qualify_generators.py']
    assert current == q.probe.file_hash(q.ROOT / 'experiments/qualify_generators.py')
    assert current != HISTORICAL_QUALIFY_GENERATORS_SHA256  # Moved past the v1-era freeze...
    assert current != V2_COMMIT_A_QUALIFY_GENERATORS_SHA256  # ...and past the Commit-A v2 freeze too.
    assert q.main([]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['qualification_implementation_status'] == q.NOT_FROZEN
    assert shown['qualification_status'] == 'NOT EXECUTED' and shown['status'] == 'NETWORK_DISABLED'
    assert shown['planned_calls'][0] == '1:G1:gq-scheduling-01' and shown['planned_calls'][12] == '13:G2:gq-scheduling-01'


def test_v2_r1_freeze_record_is_immutable_commit_a_provenance_now_superseded(loaded):
    """(B) Protocol-v2 freeze revision 1 pins Commit A's real hash and the source bytes reviewed then,
    using the same protocol-agnostic schema as the historical record (no new field invented). It is
    checked by whole-file hash and hardcoded content so it cannot be silently repinned, renamed or
    repurposed; later changes have since moved qualify_generators.py and probe_generators.py past it (only
    the validator still matches), and a successor freeze revision is required, never an overwrite of it.
    """
    assert V2_R1_FREEZE_RECORD.exists()
    assert q.probe.file_hash(V2_R1_FREEZE_RECORD) == V2_R1_FREEZE_RECORD_SHA256
    record = q.fixtures.read(V2_R1_FREEZE_RECORD)
    assert record == {
        'schema_version': q.FREEZE_SCHEMA,
        'implementation_commit': COMMIT_A,
        'source_sha256': {
            'experiments/qualify_generators.py': V2_COMMIT_A_QUALIFY_GENERATORS_SHA256,
            'experiments/probe_generators.py': PROBE_GENERATORS_SHA256,
            'experiments/validate_generator_qualification_fixtures.py': VALIDATE_FIXTURES_SHA256,
        },
    }
    assert_moved_past(record, loaded)


def assert_moved_past(record, loaded):
    """A historical freeze record no longer describes the current source: qualify_generators.py and
    probe_generators.py have changed since, while the fixture validator is still identical."""
    current = loaded['provenance']['implementation']['source_sha256']
    assert record['source_sha256']['experiments/validate_generator_qualification_fixtures.py'] == \
        current['experiments/validate_generator_qualification_fixtures.py']
    for path in ('experiments/qualify_generators.py', 'experiments/probe_generators.py'):
        assert record['source_sha256'][path] != current[path]


def test_freeze_history_distinct_records_no_record_substitutes_for_another(monkeypatch):
    """Four distinct immutable records exist on disk (v1, v2 r1, r2 and r3) with different paths, commits
    and qualify_generators.py hashes. No record substitutes for another: only r3 freezes the current
    implementation, while the active lookup pointed at any historical record still validates it as
    authentic (no raise) yet never reports FROZEN for the current bytes.
    """
    assert q.V2_FREEZE_RECORD == V2_R3_FREEZE_RECORD
    assert len({q.FREEZE_RECORD, V2_R1_FREEZE_RECORD, V2_R2_FREEZE_RECORD, V2_R3_FREEZE_RECORD}) == 4
    assert all(path.exists() for path in (q.FREEZE_RECORD, V2_R1_FREEZE_RECORD, V2_R2_FREEZE_RECORD, V2_R3_FREEZE_RECORD))
    assert q.implementation('v2')['status'] == q.FROZEN  # Only because r3 is the active record.
    for historical in (V2_R1_FREEZE_RECORD, V2_R2_FREEZE_RECORD, q.FREEZE_RECORD):
        monkeypatch.setattr(q, 'V2_FREEZE_RECORD', historical)
        authentic = q.implementation('v2')
        assert authentic['status'] == q.NOT_FROZEN and authentic['freeze_commit'] is None
    records = [q.fixtures.read(path) for path in (q.FREEZE_RECORD, V2_R1_FREEZE_RECORD, V2_R2_FREEZE_RECORD, V2_R3_FREEZE_RECORD)]
    assert [r['implementation_commit'] for r in records] == [CURRENT_FROZEN_COMMIT, COMMIT_A, COMMIT_C, COMMIT_R3]
    assert [r['source_sha256']['experiments/qualify_generators.py'] for r in records] == [
        HISTORICAL_QUALIFY_GENERATORS_SHA256, V2_COMMIT_A_QUALIFY_GENERATORS_SHA256,
        V2_R2_QUALIFY_GENERATORS_SHA256, V2_R3_QUALIFY_GENERATORS_SHA256]
    assert len({r['source_sha256']['experiments/qualify_generators.py'] for r in records}) == 4


def test_v2_r2_freeze_record_is_immutable_commit_c_provenance_now_superseded(loaded):
    """(B) Protocol-v2 freeze revision 2 (the deterministic-summary fix) pins Commit C's real hash and the
    source bytes reviewed then, by whole-file hash and hardcoded content so it cannot be silently repinned,
    renamed or repurposed. It is no longer the active record: adding the second_level_g2 profile has since
    moved qualify_generators.py and probe_generators.py past it, and only revision 3 can freeze the current
    implementation.
    """
    assert V2_R2_FREEZE_RECORD.exists() and q.V2_FREEZE_RECORD != V2_R2_FREEZE_RECORD
    assert q.probe.file_hash(V2_R2_FREEZE_RECORD) == V2_R2_FREEZE_RECORD_SHA256
    record = q.fixtures.read(V2_R2_FREEZE_RECORD)
    assert record == {
        'schema_version': q.FREEZE_SCHEMA,
        'implementation_commit': COMMIT_C,
        'source_sha256': {
            'experiments/qualify_generators.py': V2_R2_QUALIFY_GENERATORS_SHA256,
            'experiments/probe_generators.py': PROBE_GENERATORS_SHA256,
            'experiments/validate_generator_qualification_fixtures.py': VALIDATE_FIXTURES_SHA256,
        },
    }
    assert COMMIT_C != COMMIT_A
    assert_moved_past(record, loaded)


def test_v2_r3_freeze_record_points_to_its_implementation_commit_and_matches_current_sources(loaded):
    """The current v2 freeze (revision 3) pins the implementation commit and exactly the current source
    bytes, using the same schema as the historical records. It is checked by whole-file hash and hardcoded
    content so it cannot be silently repinned."""
    assert q.V2_FREEZE_RECORD == V2_R3_FREEZE_RECORD and V2_R3_FREEZE_RECORD.exists()
    assert q.probe.file_hash(V2_R3_FREEZE_RECORD) == V2_R3_FREEZE_RECORD_SHA256
    record = q.fixtures.read(V2_R3_FREEZE_RECORD)
    assert record == {
        'schema_version': q.FREEZE_SCHEMA,
        'implementation_commit': COMMIT_R3,
        'source_sha256': {
            'experiments/qualify_generators.py': V2_R3_QUALIFY_GENERATORS_SHA256,
            'experiments/probe_generators.py': V2_R3_PROBE_GENERATORS_SHA256,
            'experiments/validate_generator_qualification_fixtures.py': VALIDATE_FIXTURES_SHA256,
        },
    }
    current = {s: q.probe.file_hash(q.ROOT / s) for s in q.SOURCES}
    assert record['source_sha256'] == current == loaded['provenance']['implementation']['source_sha256']
    assert COMMIT_R3 not in (CURRENT_FROZEN_COMMIT, COMMIT_A, COMMIT_C)


def test_v2_real_gate_reports_frozen_only_because_r3_exists():
    """The real load_inputs(protocol='v2') pipeline reads the r3 record, validates it against the
    implementation commit's git history, and reports FROZEN for every profile; live execution is otherwise
    still subject to the capability gate and the other execution guards."""
    for profile in ('primary', 'second_level_g2'):
        implementation = q.load_inputs(profile=profile, protocol='v2', slot=None if profile == 'primary' else 'G2'
                                       )['provenance']['implementation']
        assert implementation == {'status': q.FROZEN, 'freeze_commit': COMMIT_R3,
                                  'source_sha256': {s: q.probe.file_hash(q.ROOT / s) for s in q.SOURCES}}


def test_v1_live_execution_still_refuses_before_network_when_unfrozen(monkeypatch, tmp_path):
    """(A) v1's own live-execution gate is unaffected by the new v2 record: it still refuses BEFORE
    any network/API request (development has moved past the historical v1 freeze), with a message
    specifically about the implementation not being frozen, never a claim v1 itself is unsupported.
    """
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-must-never-be-sent')
    output = tmp_path / 'must-not-be-created'
    with pytest.raises(ValueError) as excinfo:
        q.main(['--execute', '--confirm-spend', '--output-directory', str(output)])
    assert 'NOT YET FROZEN FOR LIVE EXECUTION' in str(excinfo.value)
    assert 'unsupported' not in str(excinfo.value).lower()
    assert not output.exists()


def test_v2_freeze_gate_reports_frozen_once_a_valid_v2_record_exists(tmp_path, monkeypatch):
    """Mirrors test_matching_freeze_record_reports_frozen for the SEPARATE v2 record: the exact same
    reproducibility principles (real, reachable, authentic ancestor commit whose git-archived bytes
    match the pinned hashes) apply to v2, never weakened -- demonstrated here on a synthetic repo
    independent of the real Commit A, to isolate the gate LOGIC from this particular real commit.
    """
    repo, commit, sources = synthetic_frozen_repo(tmp_path, monkeypatch)
    record = repo / 'v2-freeze.json'
    record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA, 'implementation_commit': commit,
                                  'source_sha256': sources}))
    monkeypatch.setattr(q, 'V2_FREEZE_RECORD', record)
    assert q.implementation('v2') == {'status': q.FROZEN, 'freeze_commit': commit, 'source_sha256': sources}


def test_v2_gate_never_falls_back_to_v1_record_even_when_v1_is_frozen(tmp_path, monkeypatch):
    """Protocol selection cannot silently fall back: even when a well-formed, genuinely FROZEN v1
    record exists, protocol='v2' still requires its OWN separate V2_FREEZE_RECORD, never v1's.
    """
    repo, commit, sources = synthetic_frozen_repo(tmp_path, monkeypatch)
    v1_record = repo / 'v1-freeze.json'
    v1_record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA, 'implementation_commit': commit,
                                     'source_sha256': sources}))
    monkeypatch.setattr(q, 'FREEZE_RECORD', v1_record)
    monkeypatch.setattr(q, 'V2_FREEZE_RECORD', repo / 'absent-v2-freeze.json')
    assert q.implementation('v1') == {'status': q.FROZEN, 'freeze_commit': commit, 'source_sha256': sources}
    assert q.implementation('v2')['status'] == q.NOT_FROZEN  # v1 being FROZEN never leaks into v2.


def test_hiding_r3_returns_v2_to_not_frozen_even_with_r1_r2_present_and_refuses_before_network(monkeypatch, tmp_path):
    """(F) With r3 hidden, current v2 reports NOT_FROZEN even though the historical r1 and r2 records are
    present and untouched, and live v2 execution refuses before any network call and before any output
    directory is created, with a message about the implementation not being frozen (never a claim that
    Protocol v2 is unsupported). This test always hides the real r3 first: with it present the freeze gate
    passes."""
    assert V2_R1_FREEZE_RECORD.exists() and V2_R2_FREEZE_RECORD.exists()
    monkeypatch.setattr(q, 'V2_FREEZE_RECORD', tmp_path / V2_R3_FREEZE_RECORD_NAME)
    assert not q.V2_FREEZE_RECORD.exists()
    assert q.implementation('v2')['status'] == q.NOT_FROZEN
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-must-never-be-sent')
    output = tmp_path / 'must-not-be-created'
    for profile in ('primary', 'second_level_g2'):
        with pytest.raises(ValueError) as excinfo:
            q.main(['--execute', '--confirm-spend', '--protocol-version', 'v2', '--profile', profile,
                   '--output-directory', str(output)])
        assert 'NOT YET FROZEN FOR LIVE EXECUTION' in str(excinfo.value)
        assert 'unsupported' not in str(excinfo.value).lower()
        assert not output.exists()


def test_removing_v2_freeze_record_reverts_to_not_frozen_refuses_before_network(monkeypatch, tmp_path):
    """(H) Hiding V2_FREEZE_RECORD (e.g. as if Commit B had never happened) reverts protocol='v2' to
    NOT_FROZEN, and live v2 execution again refuses before any network call: the freeze is contingent
    on the record's presence, not a permanently-cached fact.
    """
    monkeypatch.setattr(q, 'V2_FREEZE_RECORD', tmp_path / 'no-such-v2-freeze.json')
    assert q.implementation('v2')['status'] == q.NOT_FROZEN
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret-must-never-be-sent')
    output = tmp_path / 'must-not-be-created'
    with pytest.raises(ValueError, match='NOT YET FROZEN FOR LIVE EXECUTION'):
        q.main(['--execute', '--confirm-spend', '--protocol-version', 'v2', '--output-directory', str(output)])
    assert not output.exists()


def synthetic_frozen_repo(tmp_path, monkeypatch, *, content=None):
    """A self-contained repo where a freeze record's commit/hashes can genuinely, verifiably match."""
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)
    git('init')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Test')
    (repo / 'experiments').mkdir()
    for source in q.SOURCES:
        (repo / source).write_text((content or {}).get(source, f'frozen content for {source}'))
    git('add', '.')
    git('commit', '-m', 'frozen baseline')
    commit = git('rev-parse', 'HEAD').decode().strip()
    sources = {s: q.probe.digest((repo / s).read_bytes()) for s in q.SOURCES}
    monkeypatch.setattr(q, 'ROOT', repo)
    return repo, commit, sources


def test_matching_freeze_record_reports_frozen(tmp_path, monkeypatch):
    """Self-contained: commit is a real ancestor, and its git content matches the record exactly."""
    repo, commit, sources = synthetic_frozen_repo(tmp_path, monkeypatch)
    record = repo / 'freeze.json'
    record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA, 'implementation_commit': commit,
                                  'source_sha256': sources}))
    monkeypatch.setattr(q, 'FREEZE_RECORD', record)
    assert q.implementation() == {'status': q.FROZEN, 'freeze_commit': commit, 'source_sha256': sources}


def test_missing_freeze_record_is_not_frozen(loaded, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(q, 'FREEZE_RECORD', tmp_path / 'absent-freeze.json')
    implementation = q.implementation()
    assert implementation['status'] == q.NOT_FROZEN and implementation['freeze_commit'] is None
    assert implementation['source_sha256'] == loaded['provenance']['implementation']['source_sha256']
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret')
    output = tmp_path / 'absent'
    with pytest.raises(ValueError, match='NOT YET FROZEN'):
        q.main(['--execute', '--confirm-spend', '--output-directory', str(output)])
    assert not output.exists()


@pytest.mark.parametrize('kind', ['malformed_schema', 'malformed_commit_shape', 'malformed_source_shape'])
def test_freeze_record_malformed_fails_closed(loaded, tmp_path, monkeypatch, kind):
    record = tmp_path / 'freeze.json'
    monkeypatch.setattr(q, 'FREEZE_RECORD', record)
    sources = loaded['provenance']['implementation']['source_sha256']
    schema = q.FREEZE_SCHEMA if kind != 'malformed_schema' else 'wrong-schema/1.0.0'
    commit = 'f' * 40 if kind != 'malformed_commit_shape' else 'not-a-commit'
    if kind == 'malformed_source_shape':
        sources = {**sources, 'extra/unexpected.py': '0' * 64}
    record.write_text(json.dumps({'schema_version': schema, 'implementation_commit': commit,
                                  'source_sha256': sources}))
    with pytest.raises(ValueError, match='Malformed implementation freeze record'):
        q.implementation()


def test_freeze_record_wrong_source_hash_fails_closed(loaded, tmp_path, monkeypatch):
    """A well-formed record naming the real, permanently-committed freeze commit, but a wrong pinned hash."""
    record = tmp_path / 'freeze.json'
    monkeypatch.setattr(q, 'FREEZE_RECORD', record)
    real = loaded['provenance']['implementation']
    for path, wrong in [(q.SOURCES[0], {**real['source_sha256'], q.SOURCES[0]: '0' * 64}),
                        (q.SOURCES[1], {**real['source_sha256'], q.SOURCES[1]: '0' * 64})]:
        record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA,
                                      'implementation_commit': FROZEN_HISTORICAL_COMMIT, 'source_sha256': wrong}))
        with pytest.raises(ValueError, match='Implementation differs from frozen commit'):
            q.implementation()


def test_freeze_record_nonexistent_commit_fails_closed(loaded, tmp_path, monkeypatch):
    """A well-formed 40-hex commit that is not an ancestor/object at all."""
    record = tmp_path / 'freeze.json'
    monkeypatch.setattr(q, 'FREEZE_RECORD', record)
    record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA, 'implementation_commit': 'a' * 40,
                                  'source_sha256': loaded['provenance']['implementation']['source_sha256']}))
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        q.implementation()


def test_freeze_record_source_drift_from_frozen_commit_fails_closed(tmp_path, monkeypatch):
    """Record's declared hash disagrees with what its own cited commit's git history actually holds."""
    repo, commit, sources = synthetic_frozen_repo(tmp_path, monkeypatch)
    record = repo / 'freeze.json'
    tampered = {**sources, q.SOURCES[0]: '0' * 64}  # Declared hash no longer matches that commit's content.
    record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA, 'implementation_commit': commit,
                                  'source_sha256': tampered}))
    monkeypatch.setattr(q, 'FREEZE_RECORD', record)
    with pytest.raises(ValueError, match='Implementation differs from frozen commit'):
        q.implementation()


def test_implementation_reports_not_frozen_after_synthetic_development(tmp_path, monkeypatch):
    """A previously-FROZEN synthetic repo whose sources are then edited: gracefully NOT_FROZEN, not a raise."""
    repo, commit, sources = synthetic_frozen_repo(tmp_path, monkeypatch)
    record = repo / 'freeze.json'
    record.write_text(json.dumps({'schema_version': q.FREEZE_SCHEMA, 'implementation_commit': commit,
                                  'source_sha256': sources}))
    monkeypatch.setattr(q, 'FREEZE_RECORD', record)
    assert q.implementation()['status'] == q.FROZEN
    (repo / q.SOURCES[0]).write_text('development continued past the freeze')
    result = q.implementation()
    assert result['status'] == q.NOT_FROZEN and result['freeze_commit'] is None
    assert result['source_sha256'][q.SOURCES[0]] == q.probe.digest((repo / q.SOURCES[0]).read_bytes())


def test_probe_default_behavior_unchanged(loaded, monkeypatch):
    bundle = q.probe.load_bundle()
    assert q.probe.request_body(bundle, q.probe.SLOTS[0]) == q.probe.request_body(
        bundle, q.probe.SLOTS[0], input_validator=q.probe.validate_input)
    with pytest.raises(ValueError, match='domain'):  # Default still enforces the probe-local input.
        q.probe.request_body(dict(bundle, input=q.fixtures.project(loaded['fixtures'][0])), q.probe.SLOTS[0])
    archived = q.fixtures.read(q.ROOT / 'results/generator-capability-probe/attempt-02/probe.json')
    assert [q.probe.digest(q.probe.canonical(q.probe.request_body(bundle, s)).encode()) for s in q.probe.SLOTS] == [
        c['wire_request_sha256'] for c in archived['logical_calls']]
    seen = []
    monkeypatch.setattr(q.probe, 'request_body', lambda *a: seen.append(a) or {'late': 'bound'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as client:
            return await q.probe.probe_call(client, bundle, q.probe.SLOTS[0], 'secret')
    assert asyncio.run(run())['request_body'] == {'late': 'bound'} and seen  # Call-time lookup, as before.


@pytest.mark.parametrize('failure', ['http_503', 'read_timeout'])
def test_infrastructure_retry_exhaustion_invalidates_attempt(inputs, tmp_path, monkeypatch, failure):
    monkeypatch.setattr(q, 'git', fake_git)
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None, protocol='v1': inputs)
    requests, waits = [], []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) > 3:  # Logical call 4 (G1 gq-task-assignment-01) never gets through.
            if failure == 'read_timeout': raise httpx.ReadTimeout('simulated', request=request)
            return httpx.Response(503, json={'error': {'code': 503}})
        return httpx.Response(200, json=envelope(body, mock_output(inputs['fixtures'][len(requests) - 1])))
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    async def sleep(seconds): waits.append(seconds)
    path = tmp_path / 'attempt'
    result = asyncio.run(q.collect(inputs, 'test-secret', path, client_factory=factory, sleep=sleep))
    assert result['status'] == 'INVALIDATED'
    assert result['invalidation']['kind'] == q.EXHAUSTED and result['invalidation']['logical_call_index'] == 4
    assert result['failure_reason'] == result['invalidation']['reason']
    assert 'G1/gq-task-assignment-01' in result['failure_reason'] and '3 physical attempts exhausted' in result['failure_reason']
    # Stop at once, with no automatic rerun: 3 good requests plus exactly 3 physical attempts.
    assert len(requests) == 6 and waits == [1, 2] and len(result['calls']) == 4
    assert [len(c['attempts']) for c in result['calls']] == [1, 1, 1, 3]
    assert result['candidates'] == {'G1': 'CANDIDATE', 'G2': 'CANDIDATE'}
    assert sorted(p.name for p in tmp_path.iterdir()) == ['attempt']
    replayed, checksum = q.replay(path, inputs)  # Evidence up to invalidation remains replayable.
    assert replayed == result
    audit = q.fixtures.read(path / 'manual-audit.json')
    outcome = q.adjudicate(result, audit, checksum)
    assert outcome['candidates'] == {'G1': 'INVALIDATED', 'G2': 'INVALIDATED'}  # Never candidate FAIL.
    assert outcome['basis'] == {'invalidation': result['invalidation']}
    fill_audit(audit)  # Even a completed review cannot turn an invalidated attempt into a verdict.
    assert set(q.adjudicate(result, audit, checksum)['candidates'].values()) == {'INVALIDATED'}
    with pytest.raises(FileExistsError):  # A later approved run needs a new attempt directory.
        asyncio.run(q.collect(inputs, 'test-secret', path, client_factory=factory, sleep=sleep))
    assert len(requests) == 6


def test_retries_within_budget_do_not_invalidate(inputs, tmp_path, monkeypatch):
    monkeypatch.setattr(q, 'git', fake_git)
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None, protocol='v1': inputs)
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) in (1, 2):
            return httpx.Response(503, json={'error': {'code': 503}})
        return httpx.Response(200, json=envelope(body, mock_output(inputs['fixtures'][(len(requests) - 3) % 12])))
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    async def no_wait(seconds): pass
    path = tmp_path / 'attempt'
    result = asyncio.run(q.collect(inputs, 'test-secret', path, client_factory=factory, sleep=no_wait))
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and result['invalidation'] is None
    assert len(result['calls']) == 24 and len(requests) == 26 and len(result['calls'][0]['attempts']) == 3
    assert q.replay(path, inputs)[0] == result


def test_replay_rejects_inconsistent_invalidation(inputs, tmp_path, monkeypatch):
    def refuse_late(index, reply):
        if index == 5: reply['model'] = 'wrong'
    result, _, path = mocked_collect(inputs, tmp_path, monkeypatch, refuse_late)
    assert result['invalidation']['kind'] == q.CONTRACT and len(result['calls']) == 6
    for name, change in [('kind', lambda r: r['invalidation'].update(kind=q.EXHAUSTED)),
                         ('cleared', lambda r: r.update(status='PENDING_MANUAL_AUDIT', invalidation=None, failure_reason=None)),
                         ('earlier', lambda r: r['calls'].pop())]:
        tampered = tmp_path / name
        subprocess.check_call(['cp', '-a', str(path), str(tampered)])
        altered = deepcopy(result)
        change(altered)
        if name == 'earlier':
            (tampered / 'outputs/g1/gq-personal-preference-01.json').unlink()
        reseal(tampered, altered)
        with pytest.raises(ValueError, match='nvalidat|Incomplete'):
            q.replay(tampered, inputs)


@pytest.mark.parametrize('stamp', ['test-only', '2026-09-18T21:30:00', '2026-09-18 21:30:00+07:00',
                                   '2026-09-18', '2026-09-18T21:30+07:00', '2026-13-18T21:30:00+07:00'])
def test_reviewed_at_requires_rfc3339_offset(inputs, tmp_path, monkeypatch, stamp):
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    assert audit['reviewer'] == '' and audit['reviewed_at'] == ''  # Never auto-populated.
    fill_audit(audit)
    for valid in (REVIEWED_AT, '2026-09-18T14:30:00Z', '2026-09-18T21:30:00.5-03:00'):
        audit['reviewed_at'] = valid
        assert set(verdict(result, audit, checksum).values()) == {'QUALIFIED'}
    audit['reviewed_at'] = stamp
    with pytest.raises(ValueError, match='RFC 3339'):
        q.adjudicate(result, audit, checksum)


def test_bounded_retries(inputs):
    body = q.request(inputs, q.probe.SLOTS[0], inputs['fixtures'][0])
    waits, attempts = [], []
    def handler(request):
        attempts.append(1)
        return httpx.Response(503, json={'error': {'code': 503}})
    async def sleep(seconds): waits.append(seconds)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await q.probe.probe_call(client, inputs['bundle'], q.probe.SLOTS[0], 'secret',
                                          sleep=sleep, request_factory=lambda *_: body)
    assert asyncio.run(run())['status'] == 'FAIL'
    assert len(attempts) == 3 and waits == [1, 2]
    assert q.probe.retryable(error=httpx.ReadTimeout('test'))
    assert not q.probe.retryable(status=401) and not q.probe.retryable(error=ValueError('semantic'))


# --- Predeclared fallback candidate profile (Terra/Opus): offline design only, never executed here. ---

@pytest.fixture(scope='module')
def loaded_fallback():
    return q.load_inputs(profile='fallback')


@pytest.fixture
def fallback_inputs(loaded_fallback):
    """Simulated frozen implementation, matching the `inputs` fixture's convention for the primary."""
    frozen = deepcopy(loaded_fallback)
    frozen['provenance']['implementation'].update(status=q.FROZEN, freeze_commit='f' * 40)
    return frozen


def test_fallback_load_inputs_shares_frozen_contract_but_not_package(loaded, loaded_fallback):
    assert loaded_fallback['profile'] == 'fallback' and loaded['profile'] == 'primary'
    assert loaded_fallback['slots'] == q.probe.FALLBACK_SLOTS
    assert [s['model'] for s in loaded_fallback['slots']] == ['openai/gpt-5.6-terra', 'anthropic/claude-opus-5']
    shared = ('fixture_set_commit', 'fixture_manifest_sha256', 'contract_sha256',
             'prompt_sha256', 'output_schema_sha256', *q.probe.VERSIONS)
    for key in shared:
        assert loaded_fallback['provenance'][key] == loaded['provenance'][key]
    assert loaded_fallback['provenance']['execution_config_sha256'] == q.FALLBACK_PACKAGE_HASH
    assert loaded['provenance']['execution_config_sha256'] == q.PACKAGE_HASH
    assert loaded_fallback['provenance']['execution_config_sha256'] != loaded['provenance']['execution_config_sha256']
    assert loaded_fallback['provenance']['candidate_profile'] == 'FALLBACK'
    assert loaded['provenance']['candidate_profile'] == 'PRIMARY'
    # Fixture set/manifest/reference schema, not any downstream Generator Qualification fixture.
    assert loaded_fallback['fixtures'] == loaded['fixtures'] and loaded_fallback['manifest'] == loaded['manifest']


def test_fallback_qualification_preview_24_calls_terra_then_opus(fallback_inputs, capsys, tmp_path):
    default_output = q.ROOT / 'results/generator-qualification/attempt-02'
    assert q.main(['--profile', 'fallback']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['credits'] == 'CREDITS_NOT_SPENT'
    assert shown['candidate_profile'] == 'FALLBACK'
    assert shown['planned_logical_calls'] == 24 and shown['per_candidate'] == 12
    # The frozen default output path is correctly computed and reported -- a pure string check,
    # independent of whether that real, historical attempt-02 directory already exists on disk.
    assert shown['result_directory'] == str(default_output)
    ids = shown['fixture_ids']
    assert shown['planned_calls'][:12] == [f'{i + 1}:G1:{fid}' for i, fid in enumerate(ids)]
    assert shown['planned_calls'][12:] == [f'{i + 13}:G2:{fid}' for i, fid in enumerate(ids)]
    assert [c['model'] for c in shown['candidates']] == ['openai/gpt-5.6-terra', 'anthropic/claude-opus-5']
    assert len(shown['request_hashes']) == 24 and len(set(shown['request_hashes'])) == 24
    bodies = [q.request(fallback_inputs, s, f) for s, f, _ in q.plan(fallback_inputs)]
    assert [b['model'] for b in bodies] == ['openai/gpt-5.6-terra'] * 12 + ['anthropic/claude-opus-5'] * 12
    for b in bodies:
        assert not {'temperature', 'top_p'} & b.keys()
        assert b['reasoning'] == {'effort': 'low'} and b['max_tokens'] == 16384
        assert b['provider']['allow_fallbacks'] is False and b['provider']['require_parameters'] is True
    # Preview never creates an output directory, verified hermetically against an isolated,
    # guaranteed-nonexistent path rather than relying on the real default's historical state.
    isolated = tmp_path / 'fallback-preview-must-not-create'
    assert not isolated.exists()
    assert q.main(['--profile', 'fallback', '--output-directory', str(isolated)]) == 0
    isolated_shown = json.loads(capsys.readouterr().out)
    assert isolated_shown['result_directory'] == str(isolated)
    assert not isolated.exists()
    assert q.main([]) == 0  # Default --profile is still primary, unaffected.
    assert json.loads(capsys.readouterr().out)['candidate_profile'] == 'PRIMARY'


def test_fallback_qualification_preview_g1_only_12_calls_no_opus(capsys, tmp_path):
    """Single-slot preview: --profile fallback --slot G1 plans exactly Terra's 12 calls, the same
    frozen fixture order, and no Opus calls at all; no output directory is created."""
    assert q.main(['--profile', 'fallback', '--slot', 'G1']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['credits'] == 'CREDITS_NOT_SPENT'
    assert shown['candidate_profile'] == 'FALLBACK'
    assert shown['planned_logical_calls'] == 12 and shown['per_candidate'] == 12
    assert [c['logical_call_id'] for c in shown['candidates']] == ['G1']
    assert [c['model'] for c in shown['candidates']] == ['openai/gpt-5.6-terra']
    ids = shown['fixture_ids']
    assert shown['planned_calls'] == [f'{i + 1}:G1:{fid}' for i, fid in enumerate(ids)]
    assert all(':G2:' not in call for call in shown['planned_calls'])  # No Opus calls at all.
    assert len(shown['request_hashes']) == 12 and len(set(shown['request_hashes'])) == 12
    # Without an explicit --output-directory, single-slot preview reports the OPEN placeholder --
    # a plain string, never a real candidate path -- so no attempt directory is even named yet.
    assert shown['result_directory'] == 'OPEN: official single-slot result-path identity not yet decided'
    # Preview never creates an output directory, verified hermetically against an isolated,
    # guaranteed-nonexistent path rather than relying on real historical attempt directories.
    isolated = tmp_path / 'g1-only-preview-must-not-create'
    assert not isolated.exists()
    assert q.main(['--profile', 'fallback', '--slot', 'G1', '--output-directory', str(isolated)]) == 0
    isolated_shown = json.loads(capsys.readouterr().out)
    assert isolated_shown['result_directory'] == str(isolated)
    assert not isolated.exists()


def test_fallback_qualification_preview_g2_only_12_calls_no_terra(capsys):
    """Symmetric single-slot preview for G2: Opus's 12 calls only, same fixture order."""
    assert q.main(['--profile', 'fallback', '--slot', 'G2']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['planned_logical_calls'] == 12
    assert [c['logical_call_id'] for c in shown['candidates']] == ['G2']
    assert [c['model'] for c in shown['candidates']] == ['anthropic/claude-opus-5']
    ids = shown['fixture_ids']
    assert shown['planned_calls'] == [f'{i + 1}:G2:{fid}' for i, fid in enumerate(ids)]
    assert all(':G1:' not in call for call in shown['planned_calls'])


def test_single_slot_preview_explicit_output_directory_still_shown_and_not_created(tmp_path, capsys):
    """An explicit --output-directory with --slot is honored and still never created by preview."""
    target = tmp_path / 'terra-only-attempt'
    assert q.main(['--profile', 'fallback', '--slot', 'G1', '--output-directory', str(target)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['result_directory'] == str(target) and not target.exists()


def test_single_slot_live_execution_requires_explicit_output_directory(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-secret')
    with pytest.raises(SystemExit):
        q.main(['--profile', 'fallback', '--slot', 'G1', '--execute', '--confirm-spend'])


def test_default_two_slot_qualification_behavior_unaffected_by_slot_support(inputs, tmp_path, capsys):
    """Full backward compatibility: omitting --slot still plans the historical 24-call, two-candidate
    attempt, byte-identically to before single-slot support existed."""
    path = tmp_path / 'absent'
    assert q.main(['--output-directory', str(path)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['planned_logical_calls'] == 24 and shown['maximum_physical_attempts'] == 72
    assert shown['order'] == 'G1 all fixtures, then G2 all fixtures; frozen manifest order'
    assert not path.exists()


def test_slot_capability_terra_pass_opus_fail(loaded_fallback):
    """Per-slot capability, read from the frozen Attempt-03 adjudication: Terra CLOSED/PASS,
    Opus CLOSED/FAIL by provider-policy refusal, cross-checked against the exact candidate identity."""
    terra, opus = q.probe.FALLBACK_SLOTS
    terra_capability = q.probe.slot_capability('fallback', terra)
    assert terra_capability['status'] == 'CLOSED' and terra_capability['capability_result'] == 'PASS'
    assert terra_capability['model'] == 'openai/gpt-5.6-terra' and terra_capability['reason'] is None
    assert terra_capability['evidence_attempt'] == 'attempt-03'
    opus_capability = q.probe.slot_capability('fallback', opus)
    assert opus_capability['status'] == 'CLOSED' and opus_capability['capability_result'] == 'FAIL'
    assert opus_capability['model'] == 'anthropic/claude-opus-5'
    assert opus_capability['reason'] == 'provider-policy refusal'
    assert opus_capability['evidence_attempt'] == 'attempt-03'
    # Both slots' evidence cites the SAME attempt (a mixed per-candidate outcome within one attempt);
    # its own overall roll-up is unaffected and remains FAIL.
    assert terra_capability['evidence_path'] == opus_capability['evidence_path'] \
        == 'results/generator-capability-probe/attempt-03'
    attempt = q.fixtures.read(q.ROOT / 'results/generator-capability-probe/attempt-03/probe.json')
    assert attempt['status'] == 'FAIL'
    # The whole-profile config fields (unchanged, distinct from the per-slot section) still read
    # OPEN/NOT_ASSESSED: the profile did not pass as a whole.
    fallback_config = q.yaml.safe_load(q.probe.FALLBACK_CONFIG.read_text())
    assert fallback_config['status'] == 'OPEN' and fallback_config['capability_result'] == 'NOT_ASSESSED'


def test_slot_capability_gate_g1_pass_g2_fail_no_cross_authorization(loaded_fallback):
    terra, opus = q.probe.FALLBACK_SLOTS
    q.slot_capability_gate('fallback', terra)  # Does not raise.
    with pytest.raises(ValueError, match=r'G2 \(anthropic/claude-opus-5\).*CLOSED/PASS'):
        q.slot_capability_gate('fallback', opus)
    with pytest.raises(ValueError, match='provider-policy refusal'):
        q.slot_capability_gate('fallback', opus)


def test_fallback_qualification_g2_execution_blocked_by_closed_fail_capability(loaded_fallback, monkeypatch, tmp_path):
    inputs = q.load_inputs(profile='fallback', slot='G2')
    inputs['provenance']['implementation'].update(status=q.FROZEN, freeze_commit='f' * 40)
    monkeypatch.setattr(q, 'git', fake_git)
    output = tmp_path / 'absent'

    def forbidden(**kwargs):
        pytest.fail('G2 execution reached the network before its capability gate')
    with pytest.raises(ValueError, match=r'G2 \(anthropic/claude-opus-5\).*CLOSED/PASS'):
        asyncio.run(q.collect(inputs, 'test-secret', output, client_factory=forbidden))
    assert not output.exists()
    # Primary's own real, genuinely-CLOSED/PASS evidence cannot accidentally satisfy the fallback gate:
    # slot_capability reads the FALLBACK config specifically, keyed by exact candidate identity.
    primary_config = q.yaml.safe_load(q.probe.CONFIG.read_text())
    assert primary_config['status'] == 'CLOSED' and primary_config['capability_result'] == 'PASS'


def test_fallback_qualification_g1_execution_gate_passes_capability_check(loaded_fallback, monkeypatch, tmp_path):
    """G1 Terra's capability gate itself must NOT block (it is CLOSED/PASS); a mocked run then
    proceeds to make 12 calls, confirming the gate ran but did not refuse."""
    inputs = q.load_inputs(profile='fallback', slot='G1')
    inputs['provenance']['implementation'].update(status=q.FROZEN, freeze_commit='f' * 40)
    monkeypatch.setattr(q, 'git', fake_git)
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None, protocol='v1': inputs)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=envelope(json.loads(request.content),
                                                 mock_output(inputs['fixtures'][(len(calls) - 1) % 12])))
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    async def no_wait(seconds): pass
    result = asyncio.run(q.collect(inputs, 'test-secret', tmp_path / 'attempt',
                                   client_factory=factory, sleep=no_wait))
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(calls) == 12  # Single slot: 12, not 24.
    assert result['candidates'] == {'G1': 'CANDIDATE'}
    assert {c['candidate'] for c in result['calls']} == {'G1'}


def test_primary_qualification_execution_gate_transparently_passes(inputs, monkeypatch, tmp_path):
    """The per-slot gate is generic and runs for every profile, but the primary config has no
    `slots:` section, so it is derived uniformly from the whole (CLOSED/PASS) profile and never
    blocks primary execution."""
    monkeypatch.setattr(q, 'git', fake_git)
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None, protocol='v1': inputs)
    checked = []
    original = q.slot_capability_gate
    def tracking(profile_name, slot):
        checked.append((profile_name, slot['logical_call_id']))
        return original(profile_name, slot)
    monkeypatch.setattr(q, 'slot_capability_gate', tracking)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=envelope(json.loads(request.content),
                                                 mock_output(inputs['fixtures'][(len(calls) - 1) % 12])))
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    async def no_wait(seconds): pass
    result = asyncio.run(q.collect(inputs, 'test-secret', tmp_path / 'attempt',
                                   client_factory=factory, sleep=no_wait))
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(calls) == 24
    assert checked == [('primary', 'G1'), ('primary', 'G2')]  # The gate ran, and did not block.


def test_slot_capability_gate_rejects_stale_or_unassessed_candidate_identity():
    """A hypothetical replaced G2 candidate (not the recorded anthropic/claude-opus-5) has no
    evidence at all -- never silently inherits Opus's (or anyone else's) recorded outcome."""
    unknown = dict(logical_call_id='G2', model='anthropic/claude-hypothetical-next', provider_order=['anthropic'])
    with pytest.raises(ValueError, match=r'G2 \(anthropic/claude-hypothetical-next\).*CLOSED/PASS'):
        q.slot_capability_gate('fallback', unknown)
    capability = q.probe.slot_capability('fallback', unknown)
    assert capability == {'model': 'anthropic/claude-hypothetical-next', 'status': 'OPEN',
                          'capability_result': 'NOT_ASSESSED', 'reason': None,
                          'evidence_attempt': None, 'evidence_path': None, 'evidence_sha256': None}


def test_fallback_cannot_replay_primary_archive(loaded_fallback):
    """A fallback-profile inputs object cannot be substituted to replay the archived primary Attempt-01:
    every archived call's returned Sol/Sonnet identity mismatches the fallback Terra/Opus slots at once.
    """
    with pytest.raises(ValueError, match='should have been invalidated'):
        q.replay(q.ROOT / 'results/generator-qualification/attempt-01', loaded_fallback)


def test_real_attempt_01_replay_unaffected_by_fallback_support(loaded):
    """Critical regression: Attempt-01 remains reproducible, Sol/Sonnet-only, after adding fallback support."""
    directory = q.ROOT / 'results/generator-qualification/attempt-01'
    result, checksum = q.replay(directory, loaded)
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(result['calls']) == 24
    assert {c['request_body']['model'] for c in result['calls']} == {'openai/gpt-5.6-sol', 'anthropic/claude-sonnet-5'}
    assert not any('terra' in c['request_body']['model'] or 'opus' in c['request_body']['model']
                  for c in result['calls'])
    audit = q.fixtures.read(q.ROOT / 'results/generator-qualification/manual-audit/v1/attempt-01.completed.json')
    verdict = q.adjudicate(result, audit, checksum, loaded['slots'])
    assert verdict['candidates'] == {'G1': 'FAIL', 'G2': 'FAIL'}
    assert q.probe.file_hash(directory / 'manual-audit.json') == \
        '8decf4ba0177c7c5808050f846a61aad624073552c5d2f4a7e5b7db580ebede1'


def test_v1_implementation_unaffected_by_v2_freeze_completion(loaded):
    """The historical per-slot-support (v1) freeze record still pins CURRENT_FROZEN_COMMIT/its own
    hashes, completely unaffected by the Protocol-v2 freeze workflow completing on top: the runner
    still correctly reports NOT_FROZEN for protocol='v1' against current bytes (not a false FROZEN
    claim), and the v2 freeze records' own existence/commits are fully separate facts.
    """
    implementation = loaded['provenance']['implementation']  # loaded defaults to protocol='v1'.
    assert implementation['status'] == q.NOT_FROZEN and implementation['freeze_commit'] is None
    assert implementation['source_sha256'] == {s: q.probe.file_hash(q.ROOT / s) for s in q.SOURCES}
    assert q.fixtures.read(q.FREEZE_RECORD)['implementation_commit'] == CURRENT_FROZEN_COMMIT
    assert V2_R1_FREEZE_RECORD.exists()  # v2 revision 1 (Commit A) is preserved historical provenance.
    assert q.fixtures.read(V2_R1_FREEZE_RECORD)['implementation_commit'] == COMMIT_A
    assert q.fixtures.read(V2_R2_FREEZE_RECORD)['implementation_commit'] == COMMIT_C  # r2: historical.
    assert q.fixtures.read(V2_R3_FREEZE_RECORD)['implementation_commit'] == COMMIT_R3  # Current v2 record.


# --- Protocol v2 (docs/generator-qualification.md Sec. 14): comprehensibility/fluency split, the
# offline v1 -> v2 audit mapping, and the primary-precedence helper. Every test below uses SYNTHETIC,
# mocked evidence (via collected()/mocked_collect()) -- never the real archived Attempt-01/Attempt-02
# evidence -- so no Sol, Sonnet, or Terra Protocol-v2 disposition is ever produced. ---

def fill_audit_v2(audit):
    """Analogous to fill_audit, but for a Protocol-v2 template (comprehensibility/fluency). The human
    completes only applicable cells and ambiguity resolutions: variant/fixture/candidate dispositions
    are derived by the adjudicator under v2 and stay unset."""
    audit['reviewer'], audit['reviewed_at'] = 'test-reviewer', REVIEWED_AT
    for candidate in audit['candidates'].values():
        for f in candidate['fixtures'].values():
            for resolution in f['ambiguities'].values():
                resolution.update(disposition='PASS', notes='Manually resolved in simulated test')
            for variant in f['variants'].values():
                for event in variant['events'].values():
                    for key in q.CHECKS_V2:
                        if event[key] is None: event[key] = 'PASS'


def test_v2_constants_unchanged_v1_surface(loaded):
    """(A) Protocol v1 constants/behavior are untouched by adding Protocol v2 support."""
    assert q.PROCEDURE == q.PROCEDURE_V1 == 'generator-qualification-procedure/1.0.0'
    assert q.AUDIT_SCHEMA == q.AUDIT_SCHEMA_V1 == 'generator-manual-audit/1.0.0'
    assert q.PROCEDURE_V2 == 'generator-qualification-procedure/2.0.0'
    assert q.AUDIT_SCHEMA_V2 == 'generator-manual-audit/2.0.0'
    assert 'natural_english' in q.CHECKS and 'natural_english' not in q.CHECKS_V2
    assert {'comprehensibility', 'fluency'} <= set(q.CHECKS_V2)
    assert set(q.CHECKS) - {'natural_english'} <= set(q.CHECKS_V2)
    # Every applicability entry other than natural_english/comprehensibility/fluency is unchanged.
    for check in set(q.CHECKS) - {'natural_english'}:
        assert q.APPLICABILITY_V2[check] == q.APPLICABILITY[check]
    assert q.APPLICABILITY_V2['comprehensibility'] == q.APPLICABILITY_V2['fluency'] == q.APPLICABILITY['natural_english']


def test_v2_comprehensibility_fail_disqualifies_level1(inputs, tmp_path, monkeypatch):
    """(B) A Level-1 comprehensibility FAIL disqualifies the fixture/candidate, exactly like v1
    natural_english did."""
    result, _, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    audit = q.audit_template(result, checksum, protocol='v2')
    audit['reviewer'], audit['reviewed_at'] = 'test-reviewer', REVIEWED_AT
    event = audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']
    event['comprehensibility'] = 'FAIL'
    with pytest.raises(ValueError, match='evidence notes'):
        q.adjudicate(result, audit, checksum, protocol='v2')
    event['notes'] = 'Sentence structure obscures which entity changed'
    outcome = q.adjudicate(result, audit, checksum, protocol='v2')
    assert outcome['candidates']['G1'] == 'FAIL'
    assert outcome['basis']['G1']['manual_failures'] == ['gq-scheduling-01/low/I1: comprehensibility FAIL']
    assert outcome['basis']['G1']['level2_findings'] == []


def test_v2_fluency_only_fail_does_not_disqualify(inputs, tmp_path, monkeypatch):
    """(C) A Level-2 fluency FAIL is recorded but never fails the fixture/candidate; it still
    requires evidence notes and is retained as a finding."""
    result, _, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    audit = q.audit_template(result, checksum, protocol='v2')
    fill_audit_v2(audit)
    event = audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']
    event['fluency'] = 'FAIL'
    with pytest.raises(ValueError, match='evidence notes'):
        q.adjudicate(result, audit, checksum, protocol='v2')
    event['notes'] = 'Awkward phrasing but unambiguous meaning'
    outcome = q.adjudicate(result, audit, checksum, protocol='v2')
    assert outcome['candidates']['G1'] == 'QUALIFIED'  # Fluency alone never fails a fixture/candidate.
    assert outcome['basis']['G1']['manual_failures'] == []
    assert outcome['basis']['G1']['level2_findings'] == ['gq-scheduling-01/low/I1: fluency FAIL']


def test_v2_incomplete_review_cannot_qualify(inputs, tmp_path, monkeypatch):
    """(F) Fluency remains a required manual cell (non-disqualifying, but still gates completeness)."""
    result, _, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    audit = q.audit_template(result, checksum, protocol='v2')
    fill_audit_v2(audit)
    audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']['fluency'] = None
    assert q.adjudicate(result, audit, checksum, protocol='v2')['candidates']['G1'] == 'PENDING_MANUAL_AUDIT'


# --- Protocol v2: variant/fixture/candidate dispositions are DETERMINISTIC DERIVED outcomes, never
# manual reviewer inputs (docs/generator-qualification.md Sec. 14). The human decides only applicable
# cells and ambiguity resolutions; historical v1 keeps its manual summary dispositions. ---

def v2_scenario(inputs, tmp_path, monkeypatch, mutate=None):
    result, _, checksum, _ = collected(inputs, tmp_path, monkeypatch, mutate)
    return result, q.audit_template(result, checksum, protocol='v2'), checksum


def derived(outcome, slot):
    return outcome['basis'][slot]['derived_dispositions']


def test_v2_summaries_start_unset_and_zero_level1_review_derives_pass_qualified(inputs, tmp_path, monkeypatch):
    """(A)+(B) A native v2 template has every summary unset; a blank audit derives nothing (unresolved,
    not PASS); a completed cell-level review with zero Level-1 failures derives PASS everywhere and
    QUALIFIED, with no manual summary entered."""
    result, audit, checksum = v2_scenario(inputs, tmp_path, monkeypatch)
    for candidate in audit['candidates'].values():
        assert candidate['disposition'] is None
        for f in candidate['fixtures'].values():
            assert f['disposition'] is None and f['notes'] == ''
            assert all(v['disposition'] is None and v['notes'] == '' for v in f['variants'].values())
    blank = q.adjudicate(result, audit, checksum, protocol='v2')
    assert blank['candidates'] == {'G1': 'PENDING_MANUAL_AUDIT', 'G2': 'PENDING_MANUAL_AUDIT'}
    assert all(f['disposition'] is None and set(f['variants'].values()) == {None}
               for f in derived(blank, 'G1').values())
    fill_audit_v2(audit)  # Cells and ambiguity resolutions only.
    done = q.adjudicate(result, audit, checksum, protocol='v2')
    assert done['candidates'] == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}
    assert done['basis']['G1']['pending_manual_items'] == 0
    for slot in ('G1', 'G2'):
        assert set(derived(done, slot)) == {c['fixture_id'] for c in result['calls'] if c['candidate'] == slot}
        assert all(f['disposition'] == 'PASS' and set(f['variants']) == {'low', 'medium', 'high'}
                   and set(f['variants'].values()) == {'PASS'} for f in derived(done, slot).values())
    assert audit['candidates']['G1']['disposition'] is None  # The audit itself was never given summaries.


def test_v2_partial_review_derives_unresolved_not_pass(inputs, tmp_path, monkeypatch):
    """A required cell left unreviewed makes exactly its variant/fixture unresolved (None) and the candidate
    pending; nothing else is affected and nothing is assumed PASS."""
    result, audit, checksum = v2_scenario(inputs, tmp_path, monkeypatch)
    fill_audit_v2(audit)
    audit['candidates']['G1']['fixtures']['gq-travel-01']['variants']['medium']['events']['Q']['answer_leakage'] = None
    out = q.adjudicate(result, audit, checksum, protocol='v2')
    assert out['candidates'] == {'G1': 'PENDING_MANUAL_AUDIT', 'G2': 'QUALIFIED'}
    travel = derived(out, 'G1')['gq-travel-01']
    assert travel == {'disposition': None, 'variants': {'low': 'PASS', 'medium': None, 'high': 'PASS'}}
    assert all(f['disposition'] == 'PASS' for k, f in derived(out, 'G1').items() if k != 'gq-travel-01')


def test_v2_comprehensibility_fail_propagates_cell_to_variant_fixture_candidate(inputs, tmp_path, monkeypatch):
    """(C) One Level-1 comprehensibility FAIL deterministically fails its variant, its fixture and the
    candidate, and no other variant/fixture/candidate; summaries are derived, none supplied."""
    result, audit, checksum = v2_scenario(inputs, tmp_path, monkeypatch)
    fill_audit_v2(audit)
    event = audit['candidates']['G1']['fixtures']['gq-travel-01']['variants']['medium']['events']['I2']
    event['comprehensibility'], event['notes'] = 'FAIL', 'Meaning ambiguous from the visible text'
    out = q.adjudicate(result, audit, checksum, protocol='v2')
    assert out['candidates'] == {'G1': 'FAIL', 'G2': 'QUALIFIED'}
    assert out['basis']['G1']['manual_failures'] == ['gq-travel-01/medium/I2: comprehensibility FAIL']
    assert out['basis']['G1']['level2_findings'] == []
    travel = derived(out, 'G1')['gq-travel-01']
    assert travel == {'disposition': 'FAIL', 'variants': {'low': 'PASS', 'medium': 'FAIL', 'high': 'PASS'}}
    assert all(f['disposition'] == 'PASS' for k, f in derived(out, 'G1').items() if k != 'gq-travel-01')
    assert set(f['disposition'] for f in derived(out, 'G2').values()) == {'PASS'}


def test_v2_fluency_only_fail_never_propagates(inputs, tmp_path, monkeypatch):
    """(D) A Level-2 fluency FAIL is recorded descriptively but derives PASS for its variant, fixture and
    candidate."""
    result, audit, checksum = v2_scenario(inputs, tmp_path, monkeypatch)
    fill_audit_v2(audit)
    event = audit['candidates']['G1']['fixtures']['gq-travel-01']['variants']['medium']['events']['I2']
    event['fluency'], event['notes'] = 'FAIL', 'Unidiomatic but unambiguous'
    out = q.adjudicate(result, audit, checksum, protocol='v2')
    assert out['candidates'] == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}
    assert out['basis']['G1']['level2_findings'] == ['gq-travel-01/medium/I2: fluency FAIL']
    assert derived(out, 'G1')['gq-travel-01'] == {'disposition': 'PASS',
                                                  'variants': {'low': 'PASS', 'medium': 'PASS', 'high': 'PASS'}}


def test_v2_terminal_failure_fails_candidate_without_unrelated_manual_cells(inputs, tmp_path, monkeypatch):
    """(E) A terminal Level-1 failure consumed from archived evidence fails the fixture and candidate even
    though every other manual cell (and the reviewer identity) is still blank; the other candidate is
    unaffected."""
    def empty_field(index, reply):
        if index == 0:
            reply['choices'][0]['message']['content'] = '{}'
    result, audit, checksum = v2_scenario(inputs, tmp_path, monkeypatch, empty_field)
    assert audit['reviewer'] == ''
    out = q.adjudicate(result, audit, checksum, protocol='v2')
    assert out['candidates'] == {'G1': 'FAIL', 'G2': 'PENDING_MANUAL_AUDIT'}
    assert out['basis']['G1']['terminal_failures'] and out['basis']['G1']['pending_manual_items'] > 0
    g1 = derived(out, 'G1')
    assert g1['gq-scheduling-01'] == {'disposition': 'FAIL', 'variants': {}}
    assert all(f['disposition'] is None for k, f in g1.items() if k != 'gq-scheduling-01')


@pytest.mark.parametrize('level', ['variant', 'fixture', 'candidate'])
@pytest.mark.parametrize('value', ['PASS', 'FAIL'])
@pytest.mark.parametrize('with_real_failure', [False, True])
def test_v2_manual_summary_disposition_is_rejected_never_overrides_derived(
        inputs, tmp_path, monkeypatch, level, value, with_real_failure):
    """(F) Any manually supplied v2 variant/fixture/candidate disposition -- whether it agrees with or
    contradicts the derived evidence -- makes the audit invalid instead of being used or ignored."""
    result, audit, checksum = v2_scenario(inputs, tmp_path, monkeypatch)
    fill_audit_v2(audit)
    g1 = audit['candidates']['G1']
    if with_real_failure:
        event = g1['fixtures']['gq-travel-01']['variants']['low']['events']['I1']
        event['comprehensibility'], event['notes'] = 'FAIL', 'Ambiguous'
    if level == 'variant': g1['fixtures']['gq-travel-01']['variants']['low']['disposition'] = value
    if level == 'fixture': g1['fixtures']['gq-travel-01']['disposition'] = value
    if level == 'candidate': g1['disposition'] = value
    with pytest.raises(ValueError, match='derived'):
        q.adjudicate(result, audit, checksum, protocol='v2')


def test_v1_summary_dispositions_remain_manual_and_v1_basis_shape_unchanged(inputs, tmp_path, monkeypatch):
    """(G) Historical v1 still requires (and validates) manual summaries: leaving them unset is PENDING,
    contradictions are rejected as before, and the v1 basis gains no derived/level-2 keys."""
    result, audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    fill_audit(audit)
    assert verdict(result, audit, checksum) == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}
    audit['candidates']['G1']['fixtures']['gq-travel-01']['variants']['low']['disposition'] = None
    out = q.adjudicate(result, audit, checksum)
    assert out['candidates'] == {'G1': 'PENDING_MANUAL_AUDIT', 'G2': 'QUALIFIED'}
    assert set(out['basis']['G1']) == {'terminal_failures', 'manual_failures', 'pending_manual_items'}
    event = audit['candidates']['G1']['fixtures']['gq-travel-01']['variants']['low']['events']['I1']
    audit['candidates']['G1']['fixtures']['gq-travel-01']['variants']['low']['disposition'] = 'PASS'
    event['entity_fidelity'], event['notes'] = 'FAIL', 'Entity renamed'
    with pytest.raises(ValueError, match='Variant PASS contradicts'):
        q.adjudicate(result, audit, checksum)


@pytest.mark.parametrize('kind', ['malformed_json', 'schema_invalid'])
def test_v2_terminal_failure_remains_level1_regardless_of_protocol(inputs, tmp_path, monkeypatch, kind):
    """(G) Execution/contract terminal failures are protocol-agnostic and remain Level-1 under v2."""
    def mutate(index, reply):
        if index: return
        choice = reply['choices'][0]
        if kind == 'malformed_json': choice['message']['content'] = '{"low":'
        if kind == 'schema_invalid': choice['message']['content'] = '{}'
    result, _, checksum, _ = collected(inputs, tmp_path, monkeypatch, mutate)
    audit = q.audit_template(result, checksum, protocol='v2')
    outcome = q.adjudicate(result, audit, checksum, protocol='v2')
    assert outcome['candidates']['G1'] == 'FAIL'
    assert outcome['basis']['G1']['terminal_failures'][0].startswith(
        'gq-scheduling-01: terminal logical-call failure')


def test_v2_carried_over_semantic_check_remains_level1(inputs, tmp_path, monkeypatch):
    """(H) A carried-over semantic/structural check (e.g. entity_fidelity) is still Level-1 under v2:
    only fluency is Level 2."""
    result, _, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    audit = q.audit_template(result, checksum, protocol='v2')
    audit['reviewer'], audit['reviewed_at'] = 'test-reviewer', REVIEWED_AT
    event = audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']
    event['entity_fidelity'] = 'FAIL'
    event['notes'] = 'Entity renamed'
    outcome = q.adjudicate(result, audit, checksum, protocol='v2')
    assert outcome['candidates']['G1'] == 'FAIL'
    assert outcome['basis']['G1']['manual_failures'] == ['gq-scheduling-01/low/I1: entity_fidelity FAIL']
    assert outcome['basis']['G1']['level2_findings'] == []


def test_v2_mapping_natural_english_pass_maps_mechanically(inputs, tmp_path, monkeypatch):
    """(D) v1 natural_english = PASS maps mechanically to comprehensibility = PASS, fluency = PASS;
    every other v1 manual cell (including ambiguity resolutions) carries forward unchanged."""
    result, v1_audit, checksum, _ = collected(inputs, tmp_path, monkeypatch, first_call(
        lambda out: json.dumps({**out, 'low': {**out['low'], 'I1': 'Tern rehearsal starts at eight ten.'}})))
    fill_audit(v1_audit)
    ambiguities = v1_audit['candidates']['G1']['fixtures']['gq-scheduling-01']['ambiguities']
    for r in ambiguities.values(): r.update(disposition='PASS', notes='Spelled-out clock time is faithful')
    v2_template, pending = q.derive_v2_audit_template(result, checksum, v1_audit, inputs['slots'])
    assert pending == []
    fixture = v2_template['candidates']['G1']['fixtures']['gq-scheduling-01']
    event = fixture['variants']['low']['events']['I1']
    assert event['comprehensibility'] == 'PASS' and event['fluency'] == 'PASS'
    assert event['entity_fidelity'] == 'PASS'  # Carried forward unchanged.
    assert fixture['ambiguities'] and all(r == {'disposition': 'PASS', 'notes': 'Spelled-out clock time is faithful'}
                                          for r in fixture['ambiguities'].values())
    # Summary dispositions are derived, not carried-forward "cells": always left for fresh v2 review.
    assert fixture['disposition'] is None and fixture['variants']['low']['disposition'] is None
    assert v2_template['candidates']['G1']['disposition'] is None


def test_v2_mapping_natural_english_fail_stays_pending_not_autoclassified(inputs, tmp_path, monkeypatch):
    """(E) v1 natural_english = FAIL is never auto-classified: comprehensibility/fluency stay None,
    the cell is listed in pending_reclassification, and the stale v1 note is never copied into the
    v2 judgment field itself."""
    result, v1_audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    fill_audit(v1_audit)
    fixture = v1_audit['candidates']['G1']['fixtures']['gq-scheduling-01']
    event = fixture['variants']['low']['events']['I1']
    event['natural_english'], event['notes'] = 'FAIL', 'Wording garbled but meaning recoverable'
    fixture['variants']['low']['disposition'] = fixture['disposition'] = 'FAIL'
    v1_audit['candidates']['G1']['disposition'] = 'FAIL'
    v2_template, pending = q.derive_v2_audit_template(result, checksum, v1_audit, inputs['slots'])
    assert pending == [{'fixture_id': 'gq-scheduling-01', 'variant': 'low', 'event': 'I1',
                        'v1_natural_english_note': 'Wording garbled but meaning recoverable'}]
    mapped = v2_template['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']
    assert mapped['comprehensibility'] is None and mapped['fluency'] is None
    assert mapped['notes'] == ''
    assert mapped['entity_fidelity'] == 'PASS'  # Every other cell in the same event still carries forward.


def test_v2_mapping_rejects_wrong_source_audit(inputs, tmp_path, monkeypatch):
    result, v1_audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    v1_audit['schema_version'] = q.AUDIT_SCHEMA_V2
    with pytest.raises(ValueError, match='not a Protocol-v1 audit'):
        q.derive_v2_audit_template(result, checksum, v1_audit, inputs['slots'])
    v1_audit['schema_version'] = q.AUDIT_SCHEMA_V1
    v1_audit['qualification_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='does not match this result'):
        q.derive_v2_audit_template(result, checksum, v1_audit, inputs['slots'])


def test_v2_mapping_and_adjudication_do_not_depend_on_candidate_identity(inputs, tmp_path, monkeypatch):
    """(J) Neither the mapping tool nor adjudication branches on candidate/model identity."""
    result, v1_audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    fill_audit(v1_audit)
    renamed_slots = [dict(s, model='some/renamed-model') for s in inputs['slots']]
    baseline, baseline_pending = q.derive_v2_audit_template(result, checksum, v1_audit, inputs['slots'])
    renamed, renamed_pending = q.derive_v2_audit_template(result, checksum, v1_audit, renamed_slots)
    assert baseline_pending == renamed_pending
    for slot_id in baseline['candidates']:
        b, r = baseline['candidates'][slot_id], renamed['candidates'][slot_id]
        assert b['fixtures'] == r['fixtures']
    assert renamed['candidates']['G1']['model'] == 'some/renamed-model'
    assert baseline['candidates']['G1']['model'] != 'some/renamed-model'


def test_v2_mapping_cli_writes_template_and_pending_list(inputs, tmp_path, monkeypatch, capsys):
    result, v1_audit, _, path = collected(inputs, tmp_path, monkeypatch)
    fill_audit(v1_audit)
    completed = tmp_path / 'completed-v1-audit.json'
    completed.write_text(json.dumps(v1_audit))
    output = tmp_path / 'v2-mapping.json'
    assert q.main(['--attempt', str(path), '--audit', str(completed),
                  '--v2-mapping-output', str(output)]) == 0
    capsys.readouterr()
    written = q.fixtures.read(output)
    assert written['pending_reclassification'] == []
    assert written['v2_audit_template']['schema_version'] == q.AUDIT_SCHEMA_V2
    with pytest.raises(FileExistsError):
        q.main(['--attempt', str(path), '--audit', str(completed), '--v2-mapping-output', str(output)])


def test_offline_v2_mapping_and_adjudication_independent_of_live_freeze(inputs, tmp_path, monkeypatch):
    """(I) Offline v1->v2 mapping and v2 adjudication never consult any implementation-freeze record
    (neither derive_v2_audit_template() nor adjudicate() calls implementation() or reads FREEZE_RECORD/
    V2_FREEZE_RECORD): they behave identically whether or not a v2 freeze record exists on disk.
    """
    result, v1_audit, checksum, _ = collected(inputs, tmp_path, monkeypatch)
    fill_audit(v1_audit)

    def run_offline_v2_pipeline():
        v2_template, pending = q.derive_v2_audit_template(result, checksum, v1_audit, inputs['slots'])
        assert pending == []
        fill_audit_v2(v2_template)
        outcome = q.adjudicate(result, v2_template, checksum, inputs['slots'], protocol='v2')
        assert outcome['candidates'] == {'G1': 'QUALIFIED', 'G2': 'QUALIFIED'}

    assert q.V2_FREEZE_RECORD.exists()  # Real state: the active r3 record is present.
    run_offline_v2_pipeline()
    monkeypatch.setattr(q, 'V2_FREEZE_RECORD', tmp_path / 'hidden-r3.json')  # r3 hidden.
    assert not q.V2_FREEZE_RECORD.exists()
    run_offline_v2_pipeline()
    for record in (V2_R1_FREEZE_RECORD, V2_R2_FREEZE_RECORD):  # A historical record visible instead.
        monkeypatch.setattr(q, 'V2_FREEZE_RECORD', record)
        run_offline_v2_pipeline()  # Identical result whichever freeze record is (or isn't) visible.


def test_v2_cli_flag_validation(tmp_path):
    a, o, m = (tmp_path / n for n in ('a.json', 'o.json', 'm.json'))
    with pytest.raises(SystemExit):  # Adjudication and mapping are separate, non-combinable modes.
        q.main(['--attempt', str(tmp_path), '--audit', str(a),
               '--adjudication-output', str(o), '--v2-mapping-output', str(m)])
    with pytest.raises(SystemExit):  # Mapping mode needs its own complete flag triple.
        q.main(['--attempt', str(tmp_path), '--v2-mapping-output', str(m)])


@pytest.mark.parametrize('primary_qualified,fallback_qualified,expected', [
    (True, True, 'primary'),
    (True, False, 'primary'),
    (False, True, 'fallback'),
    (False, False, None),
])
def test_resolve_primary_precedence(primary_qualified, fallback_qualified, expected):
    """docs/generator-qualification.md Sec. 14, "Primary precedence": a pure offline helper, never
    itself used inside per-candidate qualification adjudication."""
    assert q.resolve_primary_precedence(primary_qualified, fallback_qualified) == expected


def test_real_attempt_02_v1_replay_reproduces_frozen_terra_fail():
    """(I) Critical regression: the archived, CLOSED Terra Attempt-02 still reproduces its frozen
    Protocol-v1 verdict exactly. No Protocol-v2 disposition is produced for it here.
    """
    inputs = q.load_inputs(profile='fallback', slot='G1')
    directory = q.ROOT / 'results/generator-qualification/attempt-02'
    result, checksum = q.replay(directory, inputs)
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(result['calls']) == 12
    audit = q.fixtures.read(q.ROOT / 'results/generator-qualification/manual-audit/v1/attempt-02.completed.json')
    verdict = q.adjudicate(result, audit, checksum, inputs['slots'])
    assert verdict['candidates'] == {'G1': 'FAIL'}


# --- Protocol v2 as a DIRECT, native qualification protocol for a future candidate (docs/
# generator-qualification.md Sec. 14) -- distinct from the historical v1 -> v2 mapping above.
# collect() and load_inputs() accept protocol='v2' and never touch the network here: the no_network
# fixture (autouse) blocks real sockets, and every "execution" below is httpx.MockTransport. ---

def mocked_collect_v2(inputs, tmp_path, monkeypatch, mutate=None):
    """Native Protocol-v2 mocked collection: identical generation contract to v1 (same fixtures,
    prompt, request construction); only the recorded procedure/audit-schema metadata differs."""
    v2_inputs = {**inputs, 'provenance': {**inputs['provenance'], 'procedure_version': q.PROCEDURE_V2}}
    monkeypatch.setattr(q, 'git', fake_git)
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None, protocol='v1': v2_inputs)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        index = len(calls)
        calls.append(body)
        reply = envelope(body, mock_output(v2_inputs['fixtures'][index % 12]))
        if mutate:
            mutate(index, reply)
        return httpx.Response(200, json=reply)
    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    path = tmp_path / 'attempt'
    async def no_wait(seconds): pass
    result = asyncio.run(q.collect(v2_inputs, 'test-secret', path, client_factory=factory,
                                   sleep=no_wait, protocol='v2'))
    return result, calls, path, v2_inputs


def test_v2_preview_constructed_offline_no_network(tmp_path, capsys):
    """(A) A native Protocol-v2 preview is available with no network access and no execution."""
    output = tmp_path / 'v2-preview-must-not-be-created'
    assert q.main(['--protocol-version', 'v2', '--output-directory', str(output)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['credits'] == 'CREDITS_NOT_SPENT'
    assert shown['procedure_version'] == q.PROCEDURE_V2
    assert not output.exists()
    # v1 preview (default, unaffected) still reports the v1 procedure.
    assert q.main(['--output-directory', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['procedure_version'] == q.PROCEDURE_V1


def test_v2_mocked_execution_accepted_not_rejected_for_protocol_alone(inputs, tmp_path, monkeypatch):
    """(B) A mocked v2 execution path completes; it is not refused solely because protocol='v2'."""
    result, calls, path, _ = mocked_collect_v2(inputs, tmp_path, monkeypatch)
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(result['calls']) == 24 and len(calls) == 24


def test_v2_mocked_execution_reaches_transport_and_real_r3_gate_agrees(inputs, tmp_path, monkeypatch):
    """Native v2 mocked execution passes the freeze gate and reaches the mocked transport, with no real
    network request (the inputs simulate FROZEN per the suite's hermetic convention); the real,
    unmocked implementation('v2') independently reports FROZEN via r3, so the simulation matches reality."""
    assert q.implementation('v2') == {'status': q.FROZEN, 'freeze_commit': COMMIT_R3,
                                      'source_sha256': {s: q.probe.file_hash(q.ROOT / s) for s in q.SOURCES}}
    result, calls, path, _ = mocked_collect_v2(inputs, tmp_path, monkeypatch)
    assert result['status'] == 'PENDING_MANUAL_AUDIT' and len(result['calls']) == 24 and len(calls) == 24
    assert result['procedure_version'] == q.PROCEDURE_V2


def test_v2_mocked_execution_archives_v2_procedure(inputs, tmp_path, monkeypatch):
    """(C) A native v2 collection archives procedure_version generator-qualification-procedure/2.0.0."""
    result, _, path, _ = mocked_collect_v2(inputs, tmp_path, monkeypatch)
    assert result['procedure_version'] == q.PROCEDURE_V2 == 'generator-qualification-procedure/2.0.0'
    archived = q.fixtures.read(path / 'qualification.json')
    assert archived['procedure_version'] == q.PROCEDURE_V2
    assert archived['provenance']['procedure_version'] == q.PROCEDURE_V2


def test_v2_mocked_execution_produces_v2_blank_audit(inputs, tmp_path, monkeypatch):
    """(D)+(E) The archived blank audit uses generator-manual-audit/2.0.0, exposes comprehensibility
    and fluency, and never uses natural_english as an operative v2 check."""
    result, _, path, _ = mocked_collect_v2(inputs, tmp_path, monkeypatch)
    audit = q.fixtures.read(path / 'manual-audit.json')
    assert audit['schema_version'] == q.AUDIT_SCHEMA_V2 == 'generator-manual-audit/2.0.0'
    assert 'natural_english' not in audit['check_applicability']
    assert {'comprehensibility', 'fluency'} <= set(audit['check_applicability'])
    event = audit['candidates']['G1']['fixtures']['gq-scheduling-01']['variants']['low']['events']['I1']
    assert 'comprehensibility' in event and 'fluency' in event and 'natural_english' not in event
    # This IS the template a human completes directly -- adjudicating it natively needs no mapping step.
    outcome = q.adjudicate(result, audit, q.probe.file_hash(path / 'qualification.json'),
                           inputs['slots'], protocol='v2')
    assert set(outcome['candidates'].values()) == {'PENDING_MANUAL_AUDIT'}


def test_v2_mocked_execution_shares_v1_generation_contract(inputs, tmp_path, monkeypatch):
    """(F) The request bodies sent under native v2 execution are byte-identical to what v1 execution
    would send: v2 changes qualification/audit interpretation, never the naturalization task."""
    _, calls_v2, _, v2_inputs = mocked_collect_v2(inputs, tmp_path, monkeypatch)
    v1_bodies = [q.request(inputs, s, f) for s, f, _ in q.plan(inputs)]
    assert calls_v2 == v1_bodies


def test_v2_direct_execution_no_longer_refused_for_protocol_alone(monkeypatch, tmp_path):
    """(B) The CLI no longer refuses --protocol-version v2 --execute outright: it fails downstream
    (missing API key here) exactly like v1 would, not on the protocol flag itself."""
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    output = tmp_path / 'v2-execute-absent'
    with pytest.raises(ValueError, match='API_KEY'):
        q.main(['--execute', '--confirm-spend', '--protocol-version', 'v2', '--output-directory', str(output)])
    assert not output.exists()


def test_v1_direct_execution_behavior_unchanged(inputs, tmp_path, monkeypatch):
    """(G) Default (v1) mocked execution is byte-for-byte unaffected by adding v2 support."""
    result, calls, path = mocked_collect(inputs, tmp_path, monkeypatch)
    assert result['procedure_version'] == q.PROCEDURE_V1
    audit = q.fixtures.read(path / 'manual-audit.json')
    assert audit['schema_version'] == q.AUDIT_SCHEMA_V1 and 'natural_english' in audit['check_applicability']


def test_v2_historical_mapping_stays_separate_from_native_v2_audit_creation(inputs, tmp_path, monkeypatch):
    """(H) A natively-v2-collected archive is rejected as a mapping SOURCE: derive_v2_audit_template()
    is for historical Protocol-v1 evidence only, never for a candidate qualified natively under v2."""
    result, _, path, v2_inputs = mocked_collect_v2(inputs, tmp_path, monkeypatch)
    checksum = q.probe.file_hash(path / 'qualification.json')
    v2_audit = q.fixtures.read(path / 'manual-audit.json')
    with pytest.raises(ValueError, match='not a Protocol-v1 collection'):
        q.derive_v2_audit_template(result, checksum, v2_audit, v2_inputs['slots'])


# --- Second-level G2 profile (anthropic/claude-fable-5.1): offline support for both its Capability Probe and
# future native Protocol-v2 Generator Qualification; nothing here executes or calls any API. ---

FABLE = 'anthropic/claude-fable-5.1'


def test_second_level_g2_qualification_preview_is_12_g2_calls_native_v2(capsys):
    primary = q.load_inputs()
    for argv in (['--profile', 'second_level_g2', '--slot', 'G2', '--protocol-version', 'v2'],
                 ['--profile', 'second_level_g2', '--protocol-version', 'v2']):
        assert q.main(argv) == 0
        shown = json.loads(capsys.readouterr().out)
        assert shown['status'] == 'NETWORK_DISABLED' and shown['credits'] == 'CREDITS_NOT_SPENT'
        assert shown['candidate_profile'] == 'SECOND_LEVEL_G2' and shown['procedure_version'] == q.PROCEDURE_V2
        assert shown['planned_logical_calls'] == 12 and shown['per_candidate'] == 12
        assert [(c['logical_call_id'], c['model'], c['provider_order']) for c in shown['candidates']] == [
            ('G2', FABLE, ['anthropic'])]
        ids = shown['fixture_ids']  # The SAME 12 frozen qualification fixtures, in manifest order.
        assert ids == [f['fixture_id'] for f in primary['fixtures']] and len(ids) == 12
        assert shown['planned_calls'] == [f'{i + 1}:G2:{fid}' for i, fid in enumerate(ids)]  # No G1 call.
        assert shown['execution_config_sha256'] == q.SECOND_LEVEL_G2_PACKAGE_HASH
        assert shown['qualification_implementation_status'] == q.FROZEN  # r3 freezes the current sources.
        assert shown['result_directory'].startswith('OPEN:')  # Never defaults into an existing attempt directory.


def test_second_level_g2_shares_frozen_package_and_pins_first_party_route():
    inputs = q.load_inputs(profile='second_level_g2', slot='G2', protocol='v2')
    reference = q.load_inputs()
    assert q.PACKAGE_HASHES == {'primary': q.PACKAGE_HASH, 'fallback': q.FALLBACK_PACKAGE_HASH,
                                'second_level_g2': q.SECOND_LEVEL_G2_PACKAGE_HASH}
    assert len(set(q.PACKAGE_HASHES.values())) == 3
    shared = ('fixture_set_commit', 'fixture_manifest_sha256', 'contract_sha256', 'prompt_sha256',
              'output_schema_sha256', *q.probe.VERSIONS)
    for key in shared:
        assert inputs['provenance'][key] == reference['provenance'][key]
    assert inputs['fixtures'] == reference['fixtures'] and inputs['manifest'] == reference['manifest']
    bodies = [q.request(inputs, slot, truth) for slot, truth, _ in q.plan(inputs)]
    assert len(bodies) == 12 and len({json.dumps(b, sort_keys=True) for b in bodies}) == 12
    for body in bodies:
        assert body['model'] == FABLE and body['provider'] == {
            'order': ['anthropic'], 'allow_fallbacks': False, 'require_parameters': True}
        assert not {'temperature', 'top_p', 'tools'} & body.keys()
        assert body['reasoning'] == {'effort': 'low'} and body['max_tokens'] == 16384
        assert body['response_format']['json_schema']['strict'] is True
    primary_body = q.request(reference, reference['slots'][1], reference['fixtures'][0])  # Sonnet, same fixture.
    assert {**primary_body, 'model': FABLE} == bodies[0]  # Identical request semantics; only identity differs.


def test_second_level_g2_live_execution_requires_explicit_output_directory_and_never_uses_existing_attempts(tmp_path):
    with pytest.raises(SystemExit):  # No official result-path convention exists; none is invented.
        q.main(['--profile', 'second_level_g2', '--execute', '--confirm-spend', '--protocol-version', 'v2'])
    assert not (q.ROOT / 'results/generator-qualification/attempt-03').exists()


def test_second_level_g2_qualification_blocked_until_its_own_capability_closes_pass(monkeypatch, tmp_path):
    """The frozen candidate has no capability evidence yet, so live Generator Qualification for it is refused
    by the existing per-slot capability gate BEFORE any network client is created, even with the freeze
    gate simulated as satisfied; no other candidate's recorded PASS/FAIL can authorize it."""
    inputs = q.load_inputs(profile='second_level_g2', slot='G2', protocol='v2')
    inputs['provenance']['implementation'].update(status=q.FROZEN, freeze_commit='f' * 40)
    monkeypatch.setattr(q, 'git', fake_git)
    output = tmp_path / 'absent'

    def forbidden(**kwargs):
        pytest.fail('Second-level G2 execution reached the network before its capability gate')
    with pytest.raises(ValueError, match=r'G2 \(anthropic/claude-fable-5.1\).*CLOSED/PASS.*OPEN/NOT_ASSESSED'):
        asyncio.run(q.collect(inputs, 'test-secret', output, client_factory=forbidden, protocol='v2'))
    assert not output.exists()
