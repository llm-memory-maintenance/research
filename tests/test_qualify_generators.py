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
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None: inputs)
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
    def boundary(profile='primary', slot=None):
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
CURRENT_FROZEN_COMMIT = '3d43b6475ca76af7216ba8abb560e7ddb8e5b6ba'  # The current live freeze (fallback support).


def test_real_freeze_record_drifted_again_reports_not_frozen(loaded, capsys):
    """Per-slot capability/single-slot support (this task) edited sources past the last freeze
    (CURRENT_FROZEN_COMMIT): NOT_FROZEN again, gracefully, not a raise. The committed record itself
    is untouched and still authentically pins its own (now-superseded) commit.
    """
    implementation = loaded['provenance']['implementation']
    current_sources = {s: q.probe.file_hash(q.ROOT / s) for s in q.SOURCES}
    assert implementation['source_sha256'] == current_sources
    assert q.FREEZE_RECORD.exists()
    committed = q.fixtures.read(q.FREEZE_RECORD)
    assert committed['implementation_commit'] == CURRENT_FROZEN_COMMIT
    assert committed['source_sha256'] != current_sources  # Genuinely drifted again, not identical.
    assert implementation['status'] == q.NOT_FROZEN and implementation['freeze_commit'] is None
    assert q.main([]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['qualification_implementation_status'] == q.NOT_FROZEN
    assert shown['qualification_status'] == 'NOT EXECUTED' and shown['status'] == 'NETWORK_DISABLED'
    assert shown['planned_calls'][0] == '1:G1:gq-scheduling-01' and shown['planned_calls'][12] == '13:G2:gq-scheduling-01'


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
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None: inputs)
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
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None: inputs)
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


def test_fallback_qualification_preview_24_calls_terra_then_opus(fallback_inputs, capsys):
    default_output = q.ROOT / 'results/generator-qualification/attempt-02'
    assert q.main(['--profile', 'fallback']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['status'] == 'NETWORK_DISABLED' and shown['credits'] == 'CREDITS_NOT_SPENT'
    assert shown['candidate_profile'] == 'FALLBACK'
    assert shown['planned_logical_calls'] == 24 and shown['per_candidate'] == 12
    assert shown['result_directory'] == str(default_output)
    assert not default_output.exists()
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
    assert q.main([]) == 0  # Default --profile is still primary, unaffected.
    assert json.loads(capsys.readouterr().out)['candidate_profile'] == 'PRIMARY'


def test_fallback_qualification_preview_g1_only_12_calls_no_opus(capsys):
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
    assert shown['result_directory'] == 'OPEN: official single-slot result-path identity not yet decided'
    assert not (q.ROOT / 'results/generator-qualification/attempt-02').exists()
    assert not (q.ROOT / 'results/generator-qualification/attempt-03').exists()


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
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None: inputs)
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
    monkeypatch.setattr(q, 'load_inputs', lambda profile='primary', slot=None: inputs)
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
    audit = q.fixtures.read(q.ROOT / 'results/generator-qualification/manual-audit/attempt-01.completed.json')
    verdict = q.adjudicate(result, audit, checksum, loaded['slots'])
    assert verdict['candidates'] == {'G1': 'FAIL', 'G2': 'FAIL'}
    assert q.probe.file_hash(directory / 'manual-audit.json') == \
        '8decf4ba0177c7c5808050f846a61aad624073552c5d2f4a7e5b7db580ebede1'


def test_implementation_not_falsely_frozen_during_per_slot_development(loaded):
    """The runner must not report itself FROZEN while per-slot/single-slot support is implemented
    but not yet reviewed, committed, and re-frozen (this task's own required end state)."""
    implementation = loaded['provenance']['implementation']
    assert implementation['status'] == q.NOT_FROZEN
    assert implementation['freeze_commit'] is None
    # The stale record on disk is untouched and still names the SUPERSEDED reviewed commit.
    assert q.fixtures.read(q.FREEZE_RECORD)['implementation_commit'] == CURRENT_FROZEN_COMMIT
