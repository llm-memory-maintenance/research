"""CRST Small Pilot policy engine: M1/M2/M3 state transitions, journal, B0 context, replay. No I/O, no network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re

import b0_window
import crst_prompts as prompts
import crst_scoring as scoring
import retrieval_context as rc

POLICIES = ('M1', 'M2', 'M3', 'B0')
MEMORY_POLICIES = ('M1', 'M2', 'M3')
EVENT_ORDER = b0_window.EVENT_ORDER
INITIAL_EVENTS = EVENT_ORDER[:7]
TREATMENT_EVENTS = EVENT_ORDER[7:]
EVENT_INDEX = {label: i for i, label in enumerate(EVENT_ORDER, start=1)}
TIME_ORIGIN = datetime(2000, 1, 1, tzinfo=timezone.utc)
TEMPLATE = 'For {entity_name}, the {attribute_meaning} is {current_value}.'
_PARSE = re.compile(r'^For (?P<entity>.+?), the (?P<attribute>.+?) is (?P<value>.+)\.$')
B0_CONTEXT_TOKENS = 71
INVALID, TARGET_ERROR, EXECUTED = 'INVALID_DECISION', 'TARGET_ERROR', 'EXECUTED'


class CoverageFailure(Exception):
    """B0 cannot retain the complete U7 and N2 exchanges within the frozen budget."""


def semantic_time(event_index):
    """Frozen semantic clock: 2000-01-01T00:00:00Z plus event_index minutes; acknowledgements never advance it."""
    return (TIME_ORIGIN + timedelta(minutes=event_index)).strftime('%Y-%m-%dT%H:%M:%SZ')


def entry_id(event_index):
    return f'mem_{event_index:04d}'


def render_candidate(entity_name, attribute_meaning, current_value):
    parts = (entity_name, attribute_meaning, current_value)
    if any(type(p) is not str or not p or p != p.strip() or '\n' in p or '\r' in p for p in parts):
        raise ValueError('Candidate fields must be nonempty single-line strings without edge whitespace')
    return TEMPLATE.format(entity_name=entity_name, attribute_meaning=attribute_meaning,
                           current_value=current_value)


def parse_candidate(text):
    match = _PARSE.match(text)
    if not match:
        raise ValueError('Not a canonical candidate')
    entity, attribute, value = match.group('entity', 'attribute', 'value')
    if render_candidate(entity, attribute, value) != text:
        raise ValueError('Candidate does not round-trip')
    return entity, attribute, value


def reference_events(reference, variant, policy):
    """Ordered event records for one variant. Reference fields are evaluator-only."""
    names = {e['entity_id']: e['name'] for e in reference['entities']}
    meanings = {a['attribute_id']: a['meaning'] for a in reference['attributes']}
    keys = {k['state_key']: k for k in reference['state_keys']}
    events, canonical = [], {}
    for event in reference['variants'][variant]['events']:
        label = event['event']
        index = EVENT_INDEX[label]
        key = keys[event['state_key']]
        if label in INITIAL_EVENTS:
            canonical[event['state_key']] = entry_id(index)
            operation = 'Add'
        elif policy == 'M3' and label in ('N1', 'N2'):
            operation = 'Noop'
        elif policy in ('M2', 'M3'):
            operation = 'Update'
        else:
            operation = None
        events.append({'event': label, 'event_index': index, 'semantic_time': semantic_time(index),
                       'state_key': event['state_key'], 'semantics': event['semantics'],
                       'candidate': render_candidate(names[key['entity_id']], meanings[key['attribute_id']],
                                                     event['current_value']),
                       'reference_operation': operation,
                       'canonical_target_id': canonical[event['state_key']]})
    return events


def target_answer(reference, variant):
    """Evaluator keys for Q: the current target value and the target values superseded by Q."""
    last = [e for e in reference['variants'][variant]['events'] if e['state_key'] == 'k_target'][-1]
    return {'current': reference['gold_current_value'], 'superseded': list(last['superseded_values'])}


def active_entries(state):
    return sorted(deepcopy(state), key=rc.chronological_key)


def serialize_state(state):
    return rc.serialize_context(active_entries(state))


def add_entry(state, event_index, text):
    return [*state, {'entry_id': entry_id(event_index), 'created_time': semantic_time(event_index),
                     'last_updated_time': semantic_time(event_index), 'text': text}]


def validate_decision(policy, raw):
    """Strict policy-specific decision check. No repair; returns status/operation/target_id/reason."""
    def bad(reason):
        return {'status': INVALID, 'operation': None, 'target_id': None, 'reason': reason}
    if not isinstance(raw, str):
        return bad('no_content')
    try:
        value = json.loads(raw, object_pairs_hook=scoring.strict_pairs, parse_constant=scoring.reject_constant)
    except ValueError:
        return bad('not_json')
    if type(value) is not dict or set(value) != {'operation', 'target_id'}:
        return bad('wrong_fields')
    operation, target = value['operation'], value['target_id']
    if type(operation) is not str or operation not in prompts.OPERATIONS[policy]:
        return bad('operation_not_available')
    if operation == 'Update':
        if type(target) is not str or not target.strip():
            return bad('update_requires_nonempty_target_id')
    elif target is not None:
        return bad('target_id_must_be_null')
    return {'status': 'VALID', 'operation': operation, 'target_id': target, 'reason': None}


def execute(state, event, decision):
    """Apply a validated-or-invalid decision. Returns (new_state, status, transition)."""
    if decision['status'] != 'VALID':
        return state, INVALID, {'kind': 'none'}
    operation, target = decision['operation'], decision['target_id']
    if operation == 'Add':
        return add_entry(state, event['event_index'], event['candidate']), EXECUTED, {
            'kind': 'add', 'entry_id': entry_id(event['event_index'])}
    if operation == 'Noop':
        return state, EXECUTED, {'kind': 'noop'}
    if target not in {e['entry_id'] for e in state}:
        return state, TARGET_ERROR, {'kind': 'none'}
    new = [{**e, 'text': event['candidate'], 'last_updated_time': event['semantic_time']}
           if e['entry_id'] == target else dict(e) for e in state]
    return new, EXECUTED, {'kind': 'update', 'entry_id': target}


def maintenance_messages(policy, state, event):
    return [{'role': 'system', 'content': prompts.MAINTENANCE_SYSTEM[policy]},
            {'role': 'user', 'content': prompts.maintenance_user_text(serialize_state(state), event['candidate'])}]


def answer_messages_from_memory(state, question):
    return [{'role': 'system', 'content': prompts.ANSWER_SYSTEM},
            {'role': 'user', 'content': prompts.answer_user_text(serialize_state(state), question)}]


def memory_size(state, tokenizer):
    """Primary: tokens of the exact serialized block shown at Q. Diagnostic: entry texts only."""
    entries = active_entries(state)
    return {'primary_tokens': rc.count_context_tokens(rc.serialize_context(entries), tokenizer),
            'text_only_tokens': rc.count_context_tokens('\n'.join(e['text'] for e in entries), tokenizer),
            'active_entries': len(entries)}


def b0_selection(texts, tokenizer, budget=B0_CONTEXT_TOKENS):
    """Frozen selector on complete exchanges; coverage of U7 and N2 is checked structurally only afterward."""
    exchanges = b0_window.build_exchanges(texts)
    selection = b0_window.select_window(exchanges, budget, prompts.ANSWER_SYSTEM, tokenizer)
    if not b0_window.retains(selection):
        raise CoverageFailure('B0 budget does not retain the complete U7 and N2 exchanges')
    return selection


def b0_answer_messages(texts, question, tokenizer, budget=B0_CONTEXT_TOKENS):
    selection = b0_selection(texts, tokenizer, budget)
    return b0_window.assemble(prompts.ANSWER_SYSTEM, selection, prompts.answer_final_user_text(question)), selection


def maintenance_diagnostics(journal):
    """MOA and Update-target diagnostics from the nine treatment decisions; never repairs state."""
    rows = [r for r in journal if r['decision_source'] == 'model']
    if len(rows) != 9:
        raise ValueError('Exactly nine maintenance decisions are required')
    correct = [r['parsed_operation'] == r['reference_operation'] for r in rows]
    eligible = [r for r in rows if r['reference_operation'] == 'Update' and r['parsed_operation'] == 'Update']
    hits = [r['selected_target_id'] == r['canonical_target_id'] for r in eligible]
    return {'moa_correct': sum(correct), 'moa_total': 9, 'operation_correct': dict(
                (r['event'], c) for r, c in zip(rows, correct)),
            'update_target_eligible': len(eligible), 'update_target_correct': sum(hits),
            'invalid_decisions': sum(r['status'] == INVALID for r in rows),
            'target_errors': sum(r['status'] == TARGET_ERROR for r in rows)}


def run_policy(policy, reference, variant, *, ask, question, run_id=None, texts=None, tokenizer=None,
               clock=None):
    """Execute one policy run through `ask(request) -> {'content': str|None, ...}`.

    The same code path serves preview stubs, the future live transport and archived replay. The scenario's
    naturalized `texts` are used only by B0; `question` is the naturalized Q for every condition.
    """
    if policy not in POLICIES:
        raise ValueError('Unknown policy')
    scenario = reference['scenario_id']
    run_id = run_id or f'{scenario}/{variant}/{policy}'
    events = reference_events(reference, variant, policy if policy != 'B0' else 'M1')
    target = target_answer(reference, variant)
    scoring.assert_distinct(target['current'], target['superseded'])
    requests, journal, trajectory, state = [], [], [], []
    start = None

    def track(label):
        row = {'event': label, 'active_entries': len(state)}
        if tokenizer is not None:
            row['primary_tokens'] = memory_size(state, tokenizer)['primary_tokens']
        trajectory.append(row)

    def ask_logged(logical_id, kind, messages, schema_name):
        request = {'logical_id': logical_id, 'kind': kind, 'schema': schema_name, 'messages': messages}
        response = ask(request)
        requests.append({**request, 'response': response})
        return response.get('content')

    if policy != 'B0':
        for event in events[:7]:
            state = add_entry(state, event['event_index'], event['candidate'])
            journal.append(_journal(run_id, scenario, variant, policy, event, 'initialization', None, [], state,
                                    {'kind': 'add', 'entry_id': entry_id(event['event_index'])}, EXECUTED, None))
            track(event['event'])
        start = clock() if clock else None
        for event in events[7:]:
            pre = state
            if policy == 'M1':
                state = add_entry(state, event['event_index'], event['candidate'])
                journal.append(_journal(run_id, scenario, variant, policy, event, 'deterministic', None, pre,
                                        state, {'kind': 'add', 'entry_id': entry_id(event['event_index'])},
                                        EXECUTED, None, operation='Add'))
            else:
                raw = ask_logged(f'{run_id}/{event["event"]}', 'maintenance',
                                 maintenance_messages(policy, pre, event), f'maintenance_{policy.lower()}')
                decision = validate_decision(policy, raw)
                state, status, transition = execute(pre, event, decision)
                journal.append(_journal(run_id, scenario, variant, policy, event, 'model', raw, pre, state,
                                        transition, status, decision))
            track(event['event'])
        messages = answer_messages_from_memory(state, question)
        extra = memory_size(state, tokenizer) if tokenizer is not None else None
    else:
        start = clock() if clock else None
        messages, selection = b0_answer_messages(texts, question, tokenizer)
        extra = {'b0_history_tokens': selection['history_tokens'],
                 'b0_selected_events': [x['event'] for x in selection['exchanges']]}
    raw_answer = ask_logged(f'{run_id}/A', 'answer', messages, 'answer')
    classification = scoring.classify(raw_answer, target['current'], target['superseded'])
    end = clock() if clock else None
    result = {'run_id': run_id, 'scenario_id': scenario, 'variant': variant, 'policy': policy,
              'requests': requests, 'journal': journal, 'trajectory': trajectory, 'raw_answer': raw_answer,
              'classification': classification, **scoring.run_contributions(classification),
              'logical_calls': len(requests),
              'memory_size': extra if policy != 'B0' else None,
              'b0_context': extra if policy == 'B0' else None,
              'final_active_memory': serialize_state(state) if policy != 'B0' else None,
              'end_to_end_seconds': None if start is None or end is None else end - start}
    result['maintenance'] = maintenance_diagnostics(journal) if policy in ('M2', 'M3') else None
    return result


def _journal(run_id, scenario, variant, policy, event, source, raw, pre, post, transition, status, decision,
             operation=None):
    parsed = decision['operation'] if decision else operation
    return {'run_id': run_id, 'scenario_id': scenario, 'variant': variant, 'policy': policy,
            'event': event['event'], 'event_index': event['event_index'], 'semantic_time': event['semantic_time'],
            'reference_state_key': event['state_key'], 'reference_operation': event['reference_operation'],
            'canonical_target_id': event['canonical_target_id'], 'decision_source': source,
            'raw_response': raw, 'parsed_operation': parsed,
            'selected_target_id': decision['target_id'] if decision else None,
            'status': status, 'error': decision['reason'] if decision else None,
            'pre_state': active_entries(pre), 'transition': transition, 'post_state': active_entries(post)}


def replayer(archived):
    """`ask` that answers from archived raw responses keyed by logical ID; missing evidence is an error."""
    def ask(request):
        if request['logical_id'] not in archived:
            raise KeyError(f'No archived response for {request["logical_id"]}')
        return {'content': archived[request['logical_id']]}
    return ask
