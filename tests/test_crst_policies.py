"""Offline tests of the CRST policy engine: transitions, journal, contexts, token size and replay."""
import json

import pytest

from crst_common import (ANSWER_INSTRUCTION, ToyTokenizer, follow_reference, material, no_network, pol, references,  # noqa: F401
                         reference_decision)
import b0_window
import crst_prompts as prompts
import crst_scoring as scoring
import retrieval_context as rc

Q = 'Ask only for the target.'


def run(reference, variant, policy, overrides=None, answer=None, **kwargs):
    return pol.run_policy(policy, reference, variant, ask=follow_reference(reference, variant, policy, overrides,
                                                                            answer), question=Q, **kwargs)


def rows(result):
    return {j['event']: j for j in result['journal']}


def target_id(reference, variant):
    return next(e['canonical_target_id'] for e in pol.reference_events(reference, variant, 'M2')
                if e['state_key'] == 'k_target')


def test_semantic_clock_and_identities_follow_the_frozen_basis():
    assert pol.semantic_time(1) == '2000-01-01T00:01:00Z'
    assert pol.semantic_time(15) == '2000-01-01T00:15:00Z'
    assert pol.semantic_time(16) == '2000-01-01T00:16:00Z'
    assert [pol.entry_id(i) for i in (1, 7, 8, 16)] == ['mem_0001', 'mem_0007', 'mem_0008', 'mem_0016']
    assert [pol.EVENT_INDEX[e] for e in ('I1', 'U1', 'U6', 'N1', 'U7', 'N2')] == [1, 8, 13, 14, 15, 16]


def test_initialization_creates_seven_entries_without_any_call(references):
    result = run(references[0], 'low', 'M2')
    first = result['journal'][:7]
    assert [j['decision_source'] for j in first] == ['initialization'] * 7
    assert [t['post_state'][-1]['entry_id'] for t in first] == [f'mem_{i:04d}' for i in range(1, 8)]
    assert all(len(j['post_state']) == i for i, j in enumerate(first, start=1))
    assert all(r['logical_id'].split('/')[-1] not in ('I1', 'I7') for r in result['requests'])


def test_m1_appends_every_candidate_and_keeps_history(references):
    reference = references[0]
    result = run(reference, 'high', 'M1', answer='x')
    assert result['logical_calls'] == 1 and [r['kind'] for r in result['requests']] == ['answer']
    lines = result['final_active_memory'].split('\n')
    assert len(lines) == 16 and result['maintenance'] is None
    assert [j['decision_source'] for j in result['journal'][7:]] == ['deterministic'] * 9
    assert all(j['parsed_operation'] == 'Add' and j['transition']['kind'] == 'add' for j in result['journal'][7:])
    values = pol.target_answer(reference, 'high')
    for old in values['superseded']:
        assert any(old in line for line in lines)
    assert len({line.split(']')[0] for line in lines}) == 16


def test_m2_updates_every_treatment_event_including_same_state(references):
    reference = references[0]
    result = run(reference, 'medium', 'M2')
    treatment = result['journal'][7:]
    assert [j['parsed_operation'] for j in treatment] == ['Update'] * 9
    assert all(j['transition']['kind'] == 'update' for j in treatment)
    assert result['logical_calls'] == 10 and len(result['final_active_memory'].split('\n')) == 7
    n1 = rows(result)['N1']
    tid = target_id(reference, 'medium')
    entry = next(e for e in n1['post_state'] if e['entry_id'] == tid)
    assert entry['last_updated_time'] == pol.semantic_time(14) and entry['created_time'] != entry['last_updated_time']
    assert result['maintenance']['moa_correct'] == 9 and result['maintenance']['update_target_correct'] == 9


def test_m3_noop_changes_neither_content_nor_timestamp(references):
    reference = references[0]
    result = run(reference, 'medium', 'M3')
    j = rows(result)
    for label in ('N1', 'N2'):
        assert j[label]['transition'] == {'kind': 'noop'} and j[label]['post_state'] == j[label]['pre_state']
        assert j[label]['status'] == pol.EXECUTED and j[label]['parsed_operation'] == 'Noop'
    tid = target_id(reference, 'medium')
    after_n1 = next(e for e in j['N1']['post_state'] if e['entry_id'] == tid)
    assert after_n1['last_updated_time'] == pol.semantic_time(pol.EVENT_INDEX['U5'])
    assert result['maintenance']['update_target_eligible'] == 7 and result['maintenance']['moa_correct'] == 9


def test_update_replaces_candidate_text_exactly_and_keeps_identity(references):
    reference = references[0]
    result = run(reference, 'high', 'M3')
    events = {e['event']: e for e in pol.reference_events(reference, 'high', 'M3')}
    u3 = rows(result)['U3']
    entry = next(e for e in u3['post_state'] if e['entry_id'] == events['U3']['canonical_target_id'])
    old = next(e for e in u3['pre_state'] if e['entry_id'] == entry['entry_id'])
    assert entry['text'] == events['U3']['candidate']
    assert entry['created_time'] == old['created_time'] and entry['last_updated_time'] == pol.semantic_time(10)
    assert len(u3['post_state']) == len(u3['pre_state']) == 7


def test_presentation_order_reflects_actual_policy_semantics(references):
    reference = references[0]
    m2, m3 = run(reference, 'low', 'M2'), run(reference, 'low', 'M3')
    for result in (m2, m3):
        stamps = [(l.split('updated=')[1].split(']')[0], l.split('created=')[1].split(';')[0], l.split('=')[1].split(';')[0])
                  for l in result['final_active_memory'].split('\n')]
        assert stamps == sorted(stamps)
    # M2's same-state Update moves the dedicated secondary to the end; M3's Noop leaves it in place.
    assert m2['final_active_memory'].split('\n')[-1] != m3['final_active_memory'].split('\n')[-1]
    assert m2['final_active_memory'] != m3['final_active_memory']


def test_m2_rejects_noop_without_mutation_or_retry(references):
    reference = references[0]
    noop = json.dumps({'operation': 'Noop', 'target_id': None})
    result = run(reference, 'low', 'M2', {'N1': noop})
    n1 = rows(result)['N1']
    assert n1['status'] == pol.INVALID and n1['post_state'] == n1['pre_state'] and n1['parsed_operation'] is None
    assert n1['error'] == 'operation_not_available' and n1['raw_response'] == noop
    assert result['logical_calls'] == 10 and result['maintenance']['invalid_decisions'] == 1
    assert result['maintenance']['moa_correct'] == 8


@pytest.mark.parametrize('raw,reason', [
    ('not json', 'not_json'), (None, 'no_content'), ('[]', 'wrong_fields'), ('{}', 'wrong_fields'),
    ('{"operation":"Update"}', 'wrong_fields'),
    ('{"operation":"Update","target_id":"mem_0001","note":"x"}', 'wrong_fields'),
    ('{"operation":"update","target_id":"mem_0001"}', 'operation_not_available'),
    ('{"operation":"Delete","target_id":null}', 'operation_not_available'),
    ('{"operation":"Update","target_id":null}', 'update_requires_nonempty_target_id'),
    ('{"operation":"Update","target_id":""}', 'update_requires_nonempty_target_id'),
    ('{"operation":"Update","target_id":"  "}', 'update_requires_nonempty_target_id'),
    ('{"operation":"Update","target_id":1}', 'update_requires_nonempty_target_id'),
    ('{"operation":"Add","target_id":"mem_0001"}', 'target_id_must_be_null'),
    ('{"operation":"Update","operation":"Add","target_id":null}', 'not_json'),
    ('{"operation":"Update","target_id":NaN}', 'not_json'),
    ('```json\n{"operation":"Add","target_id":null}\n```', 'not_json')])
def test_unmappable_decisions_leave_state_unchanged_and_are_logged(references, raw, reason):
    reference = references[0]
    result = run(reference, 'low', 'M3', {'U2': raw})
    u2 = rows(result)['U2']
    assert u2['status'] == pol.INVALID and u2['error'] == reason and u2['post_state'] == u2['pre_state']
    assert result['logical_calls'] == 10


def test_unavailable_update_target_is_logged_and_state_is_unchanged(references):
    reference = references[0]
    raw = json.dumps({'operation': 'Update', 'target_id': 'mem_9999'})
    result = run(reference, 'low', 'M2', {'U2': raw})
    u2 = rows(result)['U2']
    assert u2['status'] == pol.TARGET_ERROR and u2['post_state'] == u2['pre_state']
    assert result['maintenance']['target_errors'] == 1 and result['maintenance']['update_target_correct'] == 8


def test_valid_but_wrong_decisions_are_executed_and_propagate(references):
    reference = references[0]
    events = {e['event']: e for e in pol.reference_events(reference, 'low', 'M3')}
    wrong = events['U1']['canonical_target_id']
    other = next(e['canonical_target_id'] for e in events.values()
                 if e['canonical_target_id'] != wrong and e['event'] == 'U2')
    result = run(reference, 'low', 'M3', {'U2': json.dumps({'operation': 'Update', 'target_id': wrong}),
                                          'U1': json.dumps({'operation': 'Update', 'target_id': other})})
    j = rows(result)
    assert j['U1']['status'] == pol.EXECUTED and j['U1']['selected_target_id'] == other
    assert next(e for e in j['U1']['post_state'] if e['entry_id'] == other)['text'] == events['U1']['candidate']
    assert result['maintenance']['update_target_correct'] < result['maintenance']['update_target_eligible']
    # The reference target of U1 is never repaired: its text is still the initial one.
    assert next(e for e in j['U1']['post_state'] if e['entry_id'] == wrong)['text'] != events['U1']['candidate']


def test_erroneous_add_uses_the_reserved_id_and_never_renumbers(references):
    reference = references[0]
    add = json.dumps({'operation': 'Add', 'target_id': None})
    result = run(reference, 'high', 'M3', {'U1': add, 'U3': add})
    j = rows(result)
    assert j['U1']['transition'] == {'kind': 'add', 'entry_id': 'mem_0008'}
    assert j['U3']['transition'] == {'kind': 'add', 'entry_id': 'mem_0010'}
    assert len(j['U3']['post_state']) == 9
    assert result['maintenance']['moa_correct'] == 7


def test_all_reserved_identities_follow_event_order(references):
    add = json.dumps({'operation': 'Add', 'target_id': None})
    result = run(references[0], 'high', 'M3', {label: add for label in pol.TREATMENT_EVENTS})
    ids = [e['entry_id'] for e in result['journal'][-1]['post_state']]
    assert sorted(ids) == [f'mem_{i:04d}' for i in range(1, 17)]
    assert [rows(result)[label]['transition']['entry_id'] for label in pol.TREATMENT_EVENTS] == [
        f'mem_{pol.EVENT_INDEX[label]:04d}' for label in pol.TREATMENT_EVENTS]


def test_update_target_diagnostic_needs_reference_update_and_selected_update(references):
    reference = references[0]
    wrong_reference = json.dumps({'operation': 'Update', 'target_id': 'mem_0001'})
    result = run(reference, 'low', 'M3', {'N1': wrong_reference, 'N2': wrong_reference})
    assert result['maintenance']['update_target_eligible'] == 7
    assert result['maintenance']['moa_correct'] == 7


def test_only_nine_model_decisions_are_journaled_for_m2_and_m3(references):
    for policy in ('M2', 'M3'):
        result = run(references[1], 'high', policy)
        model = [j['event'] for j in result['journal'] if j['decision_source'] == 'model']
        assert model == ['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'N1', 'U7', 'N2']
    with pytest.raises(ValueError):
        pol.maintenance_diagnostics(result['journal'][:-1])


def test_journal_records_frozen_evidence_fields(references):
    result = run(references[0], 'low', 'M3')
    j = rows(result)['U1']
    assert set(j) == {'run_id', 'scenario_id', 'variant', 'policy', 'event', 'event_index', 'semantic_time',
                      'reference_state_key', 'reference_operation', 'canonical_target_id', 'decision_source',
                      'raw_response', 'parsed_operation', 'selected_target_id', 'status', 'error', 'pre_state',
                      'transition', 'post_state'}
    assert j['run_id'] == 'pilot-scheduling-01/low/M3' and j['event_index'] == 8
    assert j['reference_operation'] == 'Update' and j['semantic_time'] == '2000-01-01T00:08:00Z'


def test_reference_annotations_never_reach_a_request(references):
    for reference in references:
        for policy in ('M2', 'M3'):
            for request in run(reference, 'high', policy)['requests']:
                text = ' '.join(m['content'] for m in request['messages'])
                for banned in ('k_target', 'k_hard', 'k_n2', 'canonical', 'reference', 'gold', 'intensity',
                               'changed_state', 'same_state', 'superseded'):
                    assert banned not in text


def test_maintenance_request_is_prompt_plus_serialized_block_and_candidate(references):
    reference = references[0]
    result = run(reference, 'low', 'M2')
    first = result['requests'][0]
    events = pol.reference_events(reference, 'low', 'M2')
    pre = result['journal'][6]['post_state']
    assert [m['role'] for m in first['messages']] == ['system', 'user']
    assert first['messages'][0]['content'] == prompts.MAINTENANCE_SYSTEM['M2']
    assert first['messages'][1]['content'] == (f'Active memory:\n{rc.serialize_context(pre)}\n\n'
                                               f'Candidate:\n{events[7]["candidate"]}')
    assert first['schema'] == 'maintenance_m2'
    assert result['requests'][0]['logical_id'] == 'pilot-scheduling-01/low/M2/U1'


def test_policy_specific_prompts_define_only_their_own_action_space():
    assert 'Noop' not in prompts.MAINTENANCE_SYSTEM['M2'] and 'Noop' in prompts.MAINTENANCE_SYSTEM['M3']
    assert prompts.maintenance_schema('M2')['properties']['operation']['enum'] == ['Add', 'Update']
    assert prompts.maintenance_schema('M3')['properties']['operation']['enum'] == ['Add', 'Update', 'Noop']
    for policy in ('M2', 'M3'):
        schema = prompts.maintenance_schema(policy)
        assert schema['additionalProperties'] is False and schema['required'] == ['operation', 'target_id']


@pytest.mark.parametrize('policy', ['M1', 'M2', 'M3'])
def test_answer_request_carries_complete_active_memory_only(references, policy):
    reference = references[1]
    result = run(reference, 'high', policy, answer='x')
    request = result['requests'][-1]
    assert request['kind'] == 'answer' and request['schema'] == 'answer'
    assert [m['role'] for m in request['messages']] == ['system', 'user']
    assert request['messages'][0]['content'] == prompts.ANSWER_SYSTEM
    assert request['messages'][1]['content'] == (f'Context:\n{result["final_active_memory"]}\n\nQuestion:\n{Q}'
                                                 f'\n\n{ANSWER_INSTRUCTION}')
    context = request['messages'][1]['content']
    assert context.count('[memory_id=') == len(result['final_active_memory'].split('\n'))


def test_token_size_counts_the_exact_serialized_block(references):
    tokenizer = ToyTokenizer()
    reference = references[0]
    result = run(reference, 'medium', 'M1', answer='x', tokenizer=tokenizer)
    block = result['final_active_memory']
    size = result['memory_size']
    assert size['primary_tokens'] == len(tokenizer.encode(block, add_special_tokens=False))
    assert size['active_entries'] == 16
    texts = '\n'.join(e['text'] for e in pol.active_entries(result['journal'][-1]['post_state']))
    assert size['text_only_tokens'] == len(tokenizer.encode(texts, add_special_tokens=False))
    assert size['text_only_tokens'] < size['primary_tokens']
    assert Q not in block and prompts.ANSWER_SYSTEM not in block
    assert [t['active_entries'] for t in result['trajectory']] == list(range(1, 17))
    assert all(t['primary_tokens'] > 0 for t in result['trajectory'])
    assert result['trajectory'][-1]['primary_tokens'] == size['primary_tokens']


def test_token_size_excludes_history_of_replaced_entries(references):
    tokenizer = ToyTokenizer()
    m1 = run(references[0], 'high', 'M1', tokenizer=tokenizer)['memory_size']
    m2 = run(references[0], 'high', 'M2', tokenizer=tokenizer)['memory_size']
    assert m2['active_entries'] == 7 and m1['active_entries'] == 16 and m2['primary_tokens'] < m1['primary_tokens']


def test_end_to_end_timer_starts_at_u1_and_ends_after_answering(references):
    ticks = iter(range(100, 200))
    result = run(references[0], 'low', 'M2', answer='x', clock=lambda: next(ticks))
    assert result['end_to_end_seconds'] == 1


def test_b0_uses_frozen_selector_budget_and_keeps_question_outside_it(references):
    tokenizer = ToyTokenizer()
    reference = references[0]
    texts = {label: f'x{label} y' for label in pol.EVENT_ORDER}
    ask_calls = []

    def ask(request):
        ask_calls.append(request)
        return {'content': None}
    result = pol.run_policy('B0', reference, 'low', ask=ask, question=Q, texts=texts, tokenizer=tokenizer)
    assert pol.B0_CONTEXT_TOKENS == 71 and len(ask_calls) == 1 and result['logical_calls'] == 1
    request = ask_calls[0]
    assert request['schema'] == 'answer' and request['messages'][0]['content'] == prompts.ANSWER_SYSTEM
    assert request['messages'][-1] == {'role': 'user', 'content': f'Question:\n{Q}\n\n{ANSWER_INSTRUCTION}'}
    history = request['messages'][1:-1]
    assert [m['content'] for m in history[-4:]] == ['xU7 y', 'Noted.', 'xN2 y', 'Noted.']
    tokens = b0_window.history_tokens(prompts.ANSWER_SYSTEM, [
        {'messages': history[i:i + 2]} for i in range(0, len(history), 2)], tokenizer)
    assert tokens <= 71 and result['b0_context']['b0_history_tokens'] == tokens
    assert result['b0_context']['b0_selected_events'][-2:] == ['U7', 'N2']
    assert result['final_active_memory'] is None and result['memory_size'] is None and result['maintenance'] is None


def test_b0_history_is_a_complete_contiguous_suffix(references):
    tokenizer = ToyTokenizer()
    texts = {label: f'x{label} y' for label in pol.EVENT_ORDER}
    messages, selection = pol.b0_answer_messages(texts, Q, tokenizer)
    events = [x['event'] for x in selection['exchanges']]
    assert events == list(pol.EVENT_ORDER[len(pol.EVENT_ORDER) - len(events):])
    assert len(messages) == 2 * len(events) + 2
    assert [m['role'] for m in messages[1:-1]] == ['user', 'assistant'] * len(events)
    assert all(m['content'] == 'Noted.' for m in messages[2:-1:2])


def test_b0_coverage_failure_stops_before_any_call(references):
    tokenizer = ToyTokenizer()
    texts = {label: 'word ' * 60 for label in pol.EVENT_ORDER}
    called = []
    with pytest.raises(pol.CoverageFailure):
        pol.run_policy('B0', references[0], 'low', ask=lambda r: called.append(r), question=Q, texts=texts,
                       tokenizer=tokenizer)
    assert called == []


def test_b0_budget_is_never_enlarged_per_case():
    tokenizer = ToyTokenizer()
    texts = {label: 'word ' * 30 for label in pol.EVENT_ORDER}
    with pytest.raises(pol.CoverageFailure):
        pol.b0_selection(texts, tokenizer)
    assert pol.b0_selection(texts, tokenizer, budget=1000)['history_tokens'] > 71


def test_replay_reproduces_state_journal_and_score(references):
    reference = references[1]
    first = run(reference, 'medium', 'M3', {'U2': 'garbage'}, answer=json.dumps({'answer': 'x'}))
    archived = {r['logical_id']: r['response']['content'] for r in first['requests']}
    second = pol.run_policy('M3', reference, 'medium', ask=pol.replayer(archived), question=Q)
    for key in ('journal', 'classification', 'final_active_memory', 'maintenance', 'raw_answer', 'csa', 'srr'):
        assert first[key] == second[key]
    with pytest.raises(KeyError):
        pol.run_policy('M3', reference, 'medium', ask=pol.replayer({}), question=Q)


def test_rescoring_uses_archived_answer_only(references):
    reference = references[0]
    target = pol.target_answer(reference, 'low')
    for answer, label in ((target['current'], scoring.CURRENT_CORRECT), (target['superseded'][0], scoring.STALE_ERROR),
                          ('unrelated', scoring.OTHER_ERROR)):
        result = run(reference, 'low', 'M1', answer=json.dumps({'answer': answer}))
        assert result['classification']['class'] == label
        assert (result['csa'], result['srr']) == (int(label == scoring.CURRENT_CORRECT),
                                                  int(label == scoring.STALE_ERROR))


def test_unknown_policy_is_rejected(references):
    with pytest.raises(ValueError):
        pol.run_policy('M4', references[0], 'low', ask=lambda r: {}, question=Q)


@pytest.mark.parametrize('policy', ['M2', 'M3'])
def test_local_maintenance_schema_is_enforced_exactly(policy):
    schema = prompts.maintenance_schema(policy)
    operations = schema['properties']['operation']['enum']
    assert set(schema['required']) == set(schema['properties']) == {'operation', 'target_id'}
    assert schema['additionalProperties'] is False
    for operation in operations:
        target = 'mem_0001' if operation == 'Update' else None
        assert pol.validate_decision(policy, json.dumps({'operation': operation, 'target_id': target}))['status'] == 'VALID'
        for key in schema['required']:
            partial = {'operation': operation, 'target_id': target}
            del partial[key]
            assert pol.validate_decision(policy, json.dumps(partial))['reason'] == 'wrong_fields'
        extra = {'operation': operation, 'target_id': target, 'reason': 'x'}
        assert pol.validate_decision(policy, json.dumps(extra))['reason'] == 'wrong_fields'
        wrong = None if operation == 'Update' else 'mem_0001'
        assert pol.validate_decision(policy, json.dumps({'operation': operation, 'target_id': wrong}))['status'] == pol.INVALID
    outside = {'M2': 'Noop', 'M3': 'Delete'}[policy]
    assert pol.validate_decision(policy, json.dumps({'operation': outside, 'target_id': None}))['status'] == pol.INVALID


def test_provider_response_mode_is_json_object_and_the_schemas_are_local_only():
    assert prompts.PROVIDER_RESPONSE_MODE == 'json_object' and prompts.response_format() == {'type': 'json_object'}
    identity = prompts.identities()['provider_response_mode']
    assert identity == {'response_format': {'type': 'json_object'}}
    assert not hasattr(prompts, 'json_schema') and 'json_schema' not in json.dumps(prompts.identities())


def test_malformed_maintenance_response_is_invalid_unchanged_and_logged_under_json_object_mode(references):
    result = run(references[0], 'low', 'M3', {'U4': '{"operation": "Add"}'})
    u4 = rows(result)['U4']
    assert u4['status'] == pol.INVALID and u4['post_state'] == u4['pre_state'] and u4['error'] == 'wrong_fields'


def test_b0_history_budget_excludes_the_final_request_and_ignores_its_wording():
    tokenizer = ToyTokenizer()
    texts = {label: f'x{label} y' for label in pol.EVENT_ORDER}
    short, selection = pol.b0_answer_messages(texts, 'Q?', tokenizer)
    long_question = 'A much longer question ' * 20
    longer, other = pol.b0_answer_messages(texts, long_question, tokenizer)
    assert selection['history_tokens'] == other['history_tokens'] <= pol.B0_CONTEXT_TOKENS == 71
    assert [x['event'] for x in selection['exchanges']] == [x['event'] for x in other['exchanges']]
    assert short[:-1] == longer[:-1] and short[0]['content'] == prompts.ANSWER_SYSTEM
    assert short[-1] == {'role': 'user', 'content': f'Question:\nQ?\n\n{ANSWER_INSTRUCTION}'}
    assert longer[-1]['content'] == f'Question:\n{long_question}\n\n{ANSWER_INSTRUCTION}'
    wrapped = b0_window.history_tokens(prompts.ANSWER_SYSTEM, selection['exchanges'], tokenizer)
    assert wrapped == selection['history_tokens']


def test_final_request_carries_context_q_verbatim_and_the_json_instruction_for_every_memory_policy(references):
    question = 'What is "the" registration desk opening time of Seminar Brindle?'
    for policy in ('M1', 'M2', 'M3'):
        result = pol.run_policy(policy, references[0], 'high', ask=follow_reference(references[0], 'high', policy),
                                question=question)
        content = result['requests'][-1]['messages'][1]['content']
        assert content == f'Context:\n{result["final_active_memory"]}\n\nQuestion:\n{question}\n\n{ANSWER_INSTRUCTION}'
        assert result['requests'][-1]['messages'][0]['content'] == prompts.ANSWER_SYSTEM


def test_malformed_final_answers_are_other_error_without_retry_or_repair(references):
    for raw in ('The answer is 07:35', '{"answer": "x", "extra": 1}', '{"answer": ""}', '[]', None,
                '```json\n{"answer": "x"}\n```'):
        result = run(references[0], 'low', 'M1', answer=raw)
        assert result['classification']['class'] == scoring.OTHER_ERROR and result['logical_calls'] == 1
