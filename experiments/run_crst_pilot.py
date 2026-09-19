"""CRST Small Pilot planning: offline preview, call plan, request construction, accounting and checklist.

Live steps live in naturalize_crst_pilot.py and execute_crst_pilot.py. Nothing in this module reads credentials
or opens a network connection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

import crst_policies as pol
import crst_prompts as prompts
import crst_scoring as scoring
import validate_crst_pilot_material as material
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
CONFIG_PATH = ROOT / 'configs/crst-small-pilot.yaml'
FORBIDDEN_RANKING_KEYS = frozenset({'ranking', 'rank', 'best_policy', 'mean_csa', 'mean_srr', 'accuracy',
                                    'policy_accuracy', 'winner', 'aggregate'})
NATURALIZATION_OUTCOMES = ('TERMINAL_FAILURE', 'EVALUABLE_PASS', 'EVALUABLE_FLUENCY_ONLY',
                           'EVALUABLE_LEVEL1_FAILURE')


def load_config(path=CONFIG_PATH):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


def file_sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def verify_config(config):
    """Every pinned identity in the protocol equals the artifact it names."""
    gq.require(config['status'] == 'PROTOCOL_FROZEN' and config['execution_status'] == 'NOT_EXECUTED',
               'Protocol status')
    gq.require(config['backbone']['provider_response_mode']['response_format'] == prompts.response_format()
               == {'type': 'json_object'} and config['backbone']['local_validation']['sent_to_provider'] is False,
               'Provider response mode')
    gq.require([g['scenario_id'] for g in config['naturalization']['generators']]
               == [s['scenario_id'] for s in config['material']['scenarios']]
               and [(g['logical_call_id'], g['model']) for g in config['naturalization']['generators']]
               == [(s['generator'], s['model']) for s in config['material']['scenarios']],
               'Generator assignment')
    gq.require(file_sha(config['material']['path'] + '/manifest.json') == config['material']['manifest_sha256'],
               'Pilot manifest hash')
    gq.require(file_sha(config['backbone']['parameters_config']) == config['backbone']['parameters_sha256'],
               'Backbone parameters hash')
    b0 = config['answering']['b0']
    gq.require(file_sha(b0['budget_config']) == b0['budget_config_sha256'], 'B0 budget config hash')
    gq.require(load_config(ROOT / b0['budget_config'])['b0_context_tokens'] == b0['b0_context_tokens']
               == pol.B0_CONTEXT_TOKENS, 'B0 budget')
    gq.require(file_sha(config['naturalization']['contract_path']) == config['naturalization']['contract_sha256'],
               'Naturalization contract hash')
    ids = prompts.identities()
    gq.require(config['answering']['system'] == ids['answer_system']
               and config['answering']['response_schema'] == ids['answer_schema']
               and config['answering']['request'] == ids['answer_request']
               and config['answering']['memory_policies_user_template']
               == prompts.answer_user_text('{context}', '{question}')
               and config['answering']['b0_final_user_template'] == prompts.answer_final_user_text('{question}')
               and config['maintenance']['user_template_sha256'] == ids['maintenance_user_template']['sha256'],
               'Answering identities')
    for policy in ('M2', 'M3'):
        gq.require(config['maintenance']['prompts'][policy] == ids[f'maintenance_{policy.lower()}_system']
                   and config['maintenance']['schemas'][policy] == ids[f'maintenance_{policy.lower()}_schema'],
                   f'{policy} maintenance identities')
    return True


def load_fixtures(longmemeval=False):
    _, fixtures = material.validate_directory(longmemeval=longmemeval)
    return [material.with_scenario_id(f) for f in fixtures]


def call_plan(fixtures):
    """Every planned backbone logical call, in execution order. Contains no naturalization call."""
    plan = []
    for reference in fixtures:
        for variant in gq.VARIANTS:
            for policy in ('M1', 'B0', 'M2', 'M3'):
                run_id = f'{reference["scenario_id"]}/{variant}/{policy}'
                if policy in ('M2', 'M3'):
                    for event in pol.reference_events(reference, variant, policy)[7:]:
                        plan.append({'logical_id': f'{run_id}/{event["event"]}', 'run_id': run_id,
                                     'kind': 'maintenance', 'policy': policy, 'event': event['event']})
                plan.append({'logical_id': f'{run_id}/A', 'run_id': run_id, 'kind': 'answer', 'policy': policy,
                             'event': 'Q'})
    return plan


def plan_counts(plan):
    return {'runs': len({p['run_id'] for p in plan}), 'backbone_calls': len(plan),
            'maintenance': sum(p['kind'] == 'maintenance' for p in plan),
            'answering': sum(p['kind'] == 'answer' for p in plan)}


def naturalization_plan(config, fixtures):
    """One logical generator unit (a Low/Medium/High triplet) per scenario; never repeated per variant."""
    assignment = {s['scenario_id']: s for s in config['material']['scenarios']}
    gq.require([f['scenario_id'] for f in fixtures] == list(assignment), 'Naturalization units differ from the plan')
    return [{'unit': f'naturalize/{f["scenario_id"]}', 'scenario_id': f['scenario_id'],
             'generator': assignment[f['scenario_id']]['generator'],
             'model': assignment[f['scenario_id']]['model'],
             'max_attempts': config['naturalization']['max_logical_attempts_per_unit']} for f in fixtures]


def naturalization_next(outcomes, cap=3):
    """Decision after the recorded attempt outcomes of one unit. Never regenerates a semantic failure."""
    if any(o not in NATURALIZATION_OUTCOMES for o in outcomes) or len(outcomes) > cap:
        raise ValueError('Invalid attempt history')
    if not outcomes:
        return 'ATTEMPT'
    if any(o != 'TERMINAL_FAILURE' for o in outcomes[:-1]):
        raise ValueError('An evaluable attempt ends the unit')
    last = outcomes[-1]
    if last == 'EVALUABLE_PASS':
        return 'ACCEPT'
    if last == 'EVALUABLE_FLUENCY_ONLY':
        return 'ACCEPT_WITH_PROVENANCE_AWARE_SURFACE_EDIT_OPTION'
    if last == 'EVALUABLE_LEVEL1_FAILURE':
        return 'STOP_FOR_RESEARCHER'
    return 'UNBUILDABLE_STOP_FOR_RESEARCHER' if len(outcomes) >= cap else 'RETRY_SAME_UNIT'


def naturalization_audit(fixture, output):
    """Frozen deterministic semantic check on a pilot triplet through the qualification view."""
    import qualify_generators as qg
    return qg.semantic_check(material.qualification_view(fixture), output)


def request_body(model_config, request):
    """Backbone request in the qualified transport form: json_object response mode, local schemas only."""
    if request['schema'] not in ('answer', 'maintenance_m2', 'maintenance_m3'):
        raise ValueError('Unknown request schema')
    return {'model': model_config['model']['id'],
            'provider': {'order': [model_config['provider']['upstream']],
                         'allow_fallbacks': model_config['provider']['allow_fallbacks'],
                         'require_parameters': model_config['provider']['require_parameters']},
            'temperature': model_config['generation']['temperature'],
            'top_p': model_config['generation']['top_p'],
            'max_tokens': model_config['generation']['max_output_tokens'],
            'response_format': prompts.response_format(),
            'messages': request['messages']}


def request_sha(body):
    return prompts.sha256_json(body)


def reference_ask(reference, variant, policy, answer=None):
    """Deterministic stand-in for a provider: follows the reference path. Never a provider response."""
    events = {f'{reference["scenario_id"]}/{variant}/{policy}/{e["event"]}': e
              for e in pol.reference_events(reference, variant, policy)}

    def ask(request):
        if request['kind'] == 'answer':
            return {'content': None if answer is None else json.dumps({'answer': answer})}
        event = events[request['logical_id']]
        operation = event['reference_operation']
        target = event['canonical_target_id'] if operation == 'Update' else None
        return {'content': json.dumps({'operation': operation, 'target_id': target})}
    return ask


def preview_question(reference):
    return reference['question_intent']['intent']


def preview(config, fixtures, model_config, tokenizer=None):
    """Offline preview along the reference path. Contains plan and request identities only: no outcomes."""
    plan = call_plan(fixtures)
    runs = []
    for reference in fixtures:
        for variant in gq.VARIANTS:
            for policy in ('M1', 'M2', 'M3'):
                result = pol.run_policy(policy, reference, variant, ask=reference_ask(reference, variant, policy),
                                        question=preview_question(reference), tokenizer=tokenizer)
                runs.append({'run_id': result['run_id'], 'policy': policy, 'logical_calls': result['logical_calls'],
                             'requests': [{'logical_id': r['logical_id'], 'kind': r['kind'],
                                           'request_sha256': request_sha(request_body(model_config, r))}
                                          for r in result['requests']],
                             'active_entries_at_q': result['trajectory'][-1]['active_entries'],
                             'memory_size': result['memory_size']})
    return {'mode': 'OFFLINE_PREVIEW', 'live_calls_executed': 0, 'network': 'none',
            'note': 'Reference-path stand-in; request hashes are illustrative and not archived evidence.',
            'plan_counts': plan_counts(plan), 'naturalization_units': naturalization_plan(config, fixtures),
            'runs': runs, 'b0_requests': 'require naturalized text and the pinned tokenizer'}


def logical_record(request, body, response, *, policy, scenario, variant, event, model_config):
    """One immutable evidence record per logical request. `response` is the transport record."""
    return {'logical_id': request['logical_id'], 'policy': policy, 'scenario_id': scenario, 'variant': variant,
            'event': event, 'request_body': body, 'request_sha256': request_sha(body),
            'model': model_config['model']['id'], 'provider': model_config['provider']['upstream'],
            'request_status': response.get('request_status'), 'content': response.get('content'),
            'finish_reason': response.get('finish_reason'), 'routing_ok': response.get('routing_ok'),
            'accounting_ok': response.get('accounting_ok'), 'usage': response.get('usage'),
            'latency_seconds': response.get('latency_seconds'), 'cost': response.get('cost'),
            'attempts': response.get('attempts', [])}


RECORD_FIELDS = frozenset({'logical_id', 'policy', 'scenario_id', 'variant', 'event', 'request_body',
                           'request_sha256', 'model', 'provider', 'request_status', 'content', 'finish_reason',
                           'routing_ok', 'accounting_ok', 'usage', 'latency_seconds', 'cost', 'attempts'})


def validate_record(record):
    gq.require(set(record) == RECORD_FIELDS, 'Record fields')
    gq.require(record['request_sha256'] == request_sha(record['request_body']), 'Request hash mismatch')
    return True


def account_run(records):
    """Logical usage counts the accepted attempt once; retry usage and physical attempts stay separate."""
    logical = {'prompt_tokens': 0, 'completion_tokens': 0}
    retry = {'prompt_tokens': 0, 'completion_tokens': 0}
    unknown_retry = 0
    for record in records:
        attempts = record['attempts']
        accepted = record['usage']
        for key in logical:
            logical[key] += (accepted or {}).get(key) or 0
        for attempt in attempts[:-1]:
            usage = attempt.get('usage')
            if usage is None:
                unknown_retry += 1
            else:
                for key in retry:
                    retry[key] += usage.get(key) or 0
    return {'logical_calls': len(records), 'physical_attempts': sum(len(r['attempts']) or 1 for r in records),
            'logical_token_usage': logical, 'retry_token_usage': retry,
            'retry_attempts_without_usage': unknown_retry,
            'api_latency_seconds': sum(r['latency_seconds'] or 0 for r in records),
            'cost': sum(r['cost'] or 0 for r in records)}


def summarize_run(result):
    """Per-run evidence only. No cross-run aggregation, ranking or accuracy comparison."""
    maintenance = result['maintenance']
    size = result['memory_size'] or {}
    return {'run_id': result['run_id'], 'final_answer': result['classification']['answer'],
            'classification': result['classification']['class'], 'csa_contribution': result['csa'],
            'srr_contribution': result['srr'], 'moa': maintenance and {
                k: maintenance[k] for k in ('moa_correct', 'moa_total')},
            'update_target': maintenance and {k: maintenance[k] for k in (
                'update_target_eligible', 'update_target_correct')},
            'active_memory_primary_tokens': size.get('primary_tokens'),
            'text_only_memory_tokens': size.get('text_only_tokens'),
            'active_entry_count': size.get('active_entries'), 'active_entry_trajectory': result['trajectory'],
            'b0_context': result['b0_context'], 'logical_calls': result['logical_calls'],
            'end_to_end_seconds': result['end_to_end_seconds']}


def b0_coverage_report(texts, tokenizer):
    """Structural pre-run check on naturalized text: budget respected and U7 plus N2 retained."""
    selection = pol.b0_selection(texts, tokenizer)
    return {'history_tokens': selection['history_tokens'], 'budget': pol.B0_CONTEXT_TOKENS,
            'selected_events': [x['event'] for x in selection['exchanges']]}


def _events_ok(fixtures):
    return all([e['event'] for e in f['variants'][v]['events']] == list(pol.EVENT_ORDER)
               for f in fixtures for v in gq.VARIANTS)


def _schedules_ok(fixtures):
    for f in fixtures:
        for v in gq.VARIANTS:
            labels = [e['event'] for e in f['variants'][v]['events']
                      if e['state_key'] == 'k_target' and e['semantics'] == 'changed_state']
            values = [e['current_value'] for e in f['variants'][v]['events'] if e['state_key'] == 'k_target']
            seen, distinct = [], True
            for x in values:
                if seen and x == seen[-1]:
                    continue
                distinct &= x not in seen
                seen.append(x)
            if labels != gq.SCHEDULES[v] or not distinct:
                return False
    return True


def _roles_ok(fixtures):
    for f in fixtures:
        for v in gq.VARIANTS:
            ev = {e['event']: e for e in f['variants'][v]['events']}
            n1, u7, n2 = ev['N1'], ev['U7'], ev['N2']
            if not (n1['state_key'] == 'k_target' and n1['semantics'] == 'same_state'
                    and u7['state_key'] == 'k_target' and u7['semantics'] == 'changed_state'
                    and n2['state_key'] == 'k_n2' and n2['semantics'] == 'same_state'
                    and pol.EVENT_INDEX['N1'] < pol.EVENT_INDEX['U7'] < pol.EVENT_INDEX['N2']
                    and not any(e['state_key'] == 'k_n2' and e['semantics'] == 'changed_state'
                                for e in ev.values())):
                return False
    return True


def _hard_ok(fixtures):
    for f in fixtures:
        keys = {k['state_key']: k for k in f['state_keys']}
        if not (keys['k_hard']['attribute_id'] == keys['k_target']['attribute_id']
                and keys['k_hard']['entity_id'] != keys['k_target']['entity_id']):
            return False
    return True


def _shared_ok(fixtures):
    for f in fixtures:
        events = {v: f['variants'][v]['events'] for v in gq.VARIANTS}
        initial = [[(e['event'], e['state_key'], e['current_value']) for e in events[v][:7]] for v in gq.VARIANTS]
        finals = {f['variants'][v]['final_state']['k_target'] for v in gq.VARIANTS}
        if any(x != initial[0] for x in initial) or finals != {f['gold_current_value']}:
            return False
    return True


def _rendering_ok(fixtures):
    for f in fixtures:
        for v in gq.VARIANTS:
            for e in pol.reference_events(f, v, 'M3'):
                pol.parse_candidate(e['candidate'])
    return True


_LEAK = re.compile(r'k_target|k_hard|k_n2|k_[a-d]\b|state_key|reference|canonical|dedicated|hard_distractor|'
                   r'changed_state|same_state|superseded|gold|intensity|\b(?:U[1-7]|N[12]|I[1-7])\b')


def _run(reference, variant, policy, answer=None):
    return pol.run_policy(policy, reference, variant, ask=reference_ask(reference, variant, policy, answer),
                          question=preview_question(reference))


def _no_leak(fixtures):
    for f in fixtures:
        for policy in ('M2', 'M3'):
            for v in gq.VARIANTS:
                for r in _run(f, v, policy)['requests']:
                    if any(_LEAK.search(m['content']) for m in r['messages']):
                        return False
    return not any(_LEAK.search(text) for text in (prompts.MAINTENANCE_SYSTEM['M2'],
                                                   prompts.MAINTENANCE_SYSTEM['M3'], prompts.ANSWER_SYSTEM))


def _m1_ok(fixtures):
    for f in fixtures:
        for v in gq.VARIANTS:
            r = _run(f, v, 'M1')
            events = pol.reference_events(f, v, 'M1')
            lines = r['final_active_memory'].split('\n')
            if len(lines) != 16 or r['logical_calls'] != 1 or any(
                    not any(line.endswith('] ' + e['candidate']) for line in lines) for e in events):
                return False
    return True


def _policy_ok(fixtures):
    add = json.dumps({'operation': 'Add', 'target_id': None})
    upd = json.dumps({'operation': 'Update', 'target_id': 'mem_0001'})
    noop = json.dumps({'operation': 'Noop', 'target_id': None})
    return (pol.validate_decision('M2', noop)['status'] == pol.INVALID
            and pol.validate_decision('M2', add)['status'] == 'VALID'
            and pol.validate_decision('M2', upd)['status'] == 'VALID'
            and pol.validate_decision('M3', noop)['status'] == 'VALID'
            and pol.validate_decision('M3', add)['status'] == 'VALID'
            and pol.validate_decision('M3', upd)['status'] == 'VALID')


def _state():
    state = []
    for index, text in ((1, 'For A, the b is c.'), (2, 'For D, the e is f.')):
        state = pol.add_entry(state, index, text)
    return state


def _event(index=9, candidate='For A, the b is z.'):
    return {'event_index': index, 'semantic_time': pol.semantic_time(index), 'candidate': candidate}


def _update_ok(fixtures):
    state = _state()
    new, status, transition = pol.execute(state, _event(), {'status': 'VALID', 'operation': 'Update',
                                                             'target_id': 'mem_0001'})
    entry = new[0]
    return (status == pol.EXECUTED and entry['entry_id'] == 'mem_0001' and entry['text'] == 'For A, the b is z.'
            and entry['created_time'] == pol.semantic_time(1) and entry['last_updated_time'] == pol.semantic_time(9)
            and len(new) == 2)


def _time_ok(fixtures):
    state = _state()
    return (pol.semantic_time(1) == '2000-01-01T00:01:00Z' and pol.semantic_time(16) == '2000-01-01T00:16:00Z'
            and [e['entry_id'] for e in state] == ['mem_0001', 'mem_0002']
            and pol.entry_id(16) == 'mem_0016')


def _noop_ok(fixtures):
    state = _state()
    new, status, transition = pol.execute(state, _event(), {'status': 'VALID', 'operation': 'Noop',
                                                             'target_id': None})
    r = _run(fixtures[0], 'medium', 'M3')
    return (new == state and status == pol.EXECUTED and transition == {'kind': 'noop'}
            and [j['transition']['kind'] for j in r['journal'] if j['event'] in ('N1', 'N2')] == ['noop', 'noop'])


def _wrong_ok(fixtures):
    state = _state()
    new, status, _ = pol.execute(state, _event(), {'status': 'VALID', 'operation': 'Update', 'target_id': 'mem_0002'})
    return status == pol.EXECUTED and new[1]['text'] == 'For A, the b is z.' and new[0] == state[0]


def _invalid_ok(fixtures):
    f = fixtures[0]
    bad = {'content': 'not json'}
    result = pol.run_policy('M3', f, 'low', ask=lambda r: bad if r['kind'] == 'maintenance' else {'content': None},
                            question=preview_question(f))
    unchanged = all(j['post_state'] == j['pre_state'] and j['status'] == pol.INVALID
                    for j in result['journal'] if j['decision_source'] == 'model')
    state = _state()
    same, status, _ = pol.execute(state, _event(), {'status': 'VALID', 'operation': 'Update', 'target_id': 'mem_9999'})
    return unchanged and result['logical_calls'] == 10 and same == state and status == pol.TARGET_ERROR


def _nine_ok(fixtures):
    return all(_run(f, v, p)['maintenance']['moa_total'] == 9 and _run(f, v, p)['logical_calls'] == 10
               for f in fixtures for v in gq.VARIANTS for p in ('M2', 'M3'))


def _answer_context_ok(fixtures):
    for f in fixtures:
        for p in ('M1', 'M2', 'M3'):
            r = _run(f, 'high', p)
            request = r['requests'][-1]
            expected = prompts.answer_user_text(r['final_active_memory'], preview_question(f))
            if [m['role'] for m in request['messages']] != ['system', 'user'] \
                    or request['messages'][1]['content'] != expected \
                    or request['messages'][0]['content'] != prompts.ANSWER_SYSTEM:
                return False
    return True


def _same_answering_ok(fixtures):
    model = yaml.safe_load((ROOT / 'configs/model.yaml').read_text())
    formats = {json.dumps(request_body(model, {'schema': 'answer', 'messages': []})['response_format'],
                          sort_keys=True) for _ in pol.POLICIES}
    return len(formats) == 1 and prompts.sha256_text(prompts.ANSWER_SYSTEM) == prompts.ANSWER_SYSTEM_SHA256


def _scoring_ok(fixtures):
    def c(raw, cur='07:35', old=('06:35', '07:05')):
        return scoring.classify(raw, cur, list(old))['class']
    ok = lambda a: json.dumps({'answer': a})
    return (c(ok(' 07:35 ')) == scoring.CURRENT_CORRECT and c(ok('06:35')) == scoring.STALE_ERROR
            and c(ok('The answer is 07:35')) == scoring.OTHER_ERROR and c(ok('07:35 or 06:35')) == scoring.OTHER_ERROR
            and c(ok('07:35, 06:35')) == scoring.OTHER_ERROR and c(ok('')) == scoring.OTHER_ERROR
            and c('07:35') == scoring.OTHER_ERROR and c(json.dumps({'answer': '07:35', 'extra': 1})) == scoring.OTHER_ERROR
            and c(ok('07:35.')) == scoring.OTHER_ERROR)


def _pinned_ok(fixtures):
    return verify_config(load_config())


def _replay_ok(fixtures):
    f = fixtures[0]
    first = _run(f, 'high', 'M3', 'x')
    archived = {r['logical_id']: r['response']['content'] for r in first['requests']}
    second = pol.run_policy('M3', f, 'high', ask=pol.replayer(archived), question=preview_question(f))
    return all(first[k] == second[k] for k in ('journal', 'classification', 'final_active_memory', 'maintenance'))


def _plan_ok(fixtures):
    config = load_config()
    counts = plan_counts(call_plan(fixtures))
    units = naturalization_plan(config, fixtures)
    return (counts == {'runs': 24, 'backbone_calls': 132, 'maintenance': 108, 'answering': 24}
            and len(units) == 2 and len({p['logical_id'] for p in call_plan(fixtures)}) == 132
            and config['material']['technical_repetitions'] == 1)


def _no_rank_ok(fixtures):
    text = json.dumps(preview(load_config(), fixtures, yaml.safe_load((ROOT / 'configs/model.yaml').read_text())))
    return not any(f'"{k}"' in text for k in FORBIDDEN_RANKING_KEYS)


def _distinct_ok(fixtures):
    for f in fixtures:
        for v in gq.VARIANTS:
            scoring.assert_distinct(**pol.target_answer(f, v))
    return True


OFFLINE_CHECKS = {
    'DATA-01': lambda fx: len(fx) == 2 and _events_ok(fx), 'DATA-02': lambda fx: _schedules_ok(fx),
    'DATA-03': lambda fx: _roles_ok(fx), 'DATA-04': lambda fx: _hard_ok(fx), 'DATA-05': lambda fx: _shared_ok(fx),
    'DATA-06': lambda fx: _rendering_ok(fx), 'DATA-07': lambda fx: _no_leak(fx),
    'DATA-08': lambda fx: _distinct_ok(fx),
    'POL-01': lambda fx: _m1_ok(fx), 'POL-02': lambda fx: _policy_ok(fx), 'POL-03': lambda fx: _policy_ok(fx),
    'POL-04': lambda fx: _update_ok(fx), 'POL-05': lambda fx: _time_ok(fx), 'POL-06': lambda fx: _noop_ok(fx),
    'POL-07': lambda fx: _wrong_ok(fx), 'POL-08': lambda fx: _invalid_ok(fx), 'POL-09': lambda fx: _nine_ok(fx),
    'ANS-01': lambda fx: _answer_context_ok(fx), 'ANS-03': lambda fx: _same_answering_ok(fx),
    'SCR-01': lambda fx: _scoring_ok(fx), 'SCR-02': lambda fx: _scoring_ok(fx),
    'ACC-03': lambda fx: _pinned_ok(fx), 'ACC-05': lambda fx: _replay_ok(fx), 'ACC-06': lambda fx: _plan_ok(fx),
    'ACC-07': lambda fx: _no_rank_ok(fx)}


STAGE_STATUS = {'OFFLINE': 'PASS_OFFLINE', 'POST_NATURALIZATION': 'PENDING_NATURALIZATION',
                'POST_RUN': 'PENDING_LIVE'}


def run_offline_checklist(fixtures, longmemeval=False):
    """Exactly one status per item: PASS_OFFLINE, FAIL, PENDING_NATURALIZATION or PENDING_LIVE."""
    config = load_config()
    results = {}
    for item in config['acceptance_checklist']:
        if item['stage'] != 'OFFLINE':
            results[item['id']] = STAGE_STATUS[item['stage']]
        elif item['id'] == 'DATA-09':
            material.check_separation([{'fixture_id': f['scenario_id'], 'reference': f} for f in fixtures],
                                      longmemeval)
            results[item['id']] = 'PASS_OFFLINE'
        else:
            results[item['id']] = 'PASS_OFFLINE' if OFFLINE_CHECKS[item['id']](fixtures) else 'FAIL'
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checklist', action='store_true', help='Run the offline mechanical checklist')
    args = parser.parse_args()
    config = load_config()
    verify_config(config)
    fixtures = load_fixtures()
    if args.checklist:
        print(json.dumps(run_offline_checklist(fixtures), indent=2))
        return
    model = yaml.safe_load((ROOT / config['backbone']['parameters_config']).read_text())
    print(json.dumps(preview(config, fixtures, model), indent=2))


if __name__ == '__main__':
    main()
