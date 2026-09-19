"""Offline tests of the pilot protocol config, call plan, request construction, accounting and checklist."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from crst_common import ANSWER_INSTRUCTION, ROOT, ToyTokenizer, material, no_network, pol, references  # noqa: F401
import crst_prompts as prompts
import run_crst_pilot as run

MODEL = yaml.safe_load((ROOT / 'configs/model.yaml').read_text())


@pytest.fixture(scope='module')
def config():
    return run.load_config()


def test_protocol_config_is_frozen_offline_and_pinned(config):
    assert config['status'] == 'PROTOCOL_FROZEN' and config['execution_status'] == 'NOT_EXECUTED'
    assert 'live_execution_authorized' not in config and config['material']['technical_repetitions'] == 1
    assert run.verify_config(config)


@pytest.mark.parametrize('mutate', [
    lambda c: c['material'].__setitem__('manifest_sha256', '0' * 64),
    lambda c: c['backbone'].__setitem__('parameters_sha256', '0' * 64),
    lambda c: c['answering']['b0'].__setitem__('b0_context_tokens', 72),
    lambda c: c['answering']['system'].__setitem__('sha256', '0' * 64),
    lambda c: c['answering']['response_schema'].__setitem__('sha256', '0' * 64),
    lambda c: c['maintenance']['prompts']['M3'].__setitem__('sha256', '0' * 64),
    lambda c: c['maintenance']['schemas']['M2'].__setitem__('sha256', '0' * 64),
    lambda c: c['naturalization'].__setitem__('contract_sha256', '0' * 64),
    lambda c: c.__setitem__('execution_status', 'AUTHORIZED'),
    lambda c: c['backbone']['provider_response_mode'].__setitem__('response_format', {'type': 'json_schema'}),
    lambda c: c['backbone']['local_validation'].__setitem__('sent_to_provider', True),
    lambda c: c['naturalization']['generators'][0].__setitem__('model', 'openai/gpt-5.6-terra'),
    lambda c: c['naturalization']['generators'].reverse()])
def test_config_drift_is_detected(config, mutate):
    broken = deepcopy(config)
    mutate(broken)
    with pytest.raises(Exception):
        run.verify_config(broken)


def test_frozen_identities_match_the_b0_answering_freeze():
    b0 = yaml.safe_load((ROOT / 'configs/b0-calibration.yaml').read_text())['system_prompt']
    assert prompts.ANSWER_SYSTEM == f'{b0["system"]}\n\n{b0["answer"]}'
    assert prompts.sha256_text(prompts.ANSWER_SYSTEM) == b0['composed_sha256']


def test_call_plan_is_exactly_132_backbone_calls_in_24_runs(references):
    plan = run.call_plan(references)
    assert run.plan_counts(plan) == {'runs': 24, 'backbone_calls': 132, 'maintenance': 108, 'answering': 24}
    assert len({p['logical_id'] for p in plan}) == 132
    per_variant = {}
    for p in plan:
        per_variant.setdefault(p['run_id'].rsplit('/', 1)[0], {}).setdefault(p['policy'], 0)
        per_variant[p['run_id'].rsplit('/', 1)[0]][p['policy']] += 1
    assert len(per_variant) == 6 and all(v == {'M1': 1, 'B0': 1, 'M2': 10, 'M3': 10} for v in per_variant.values())
    assert not any('naturalize' in p['logical_id'] for p in plan)
    assert [p['event'] for p in plan if p['run_id'].endswith('low/M2')][:3] == ['U1', 'U2', 'U3']


def test_no_technical_repetition_of_any_run(references):
    ids = [p['run_id'] for p in run.call_plan(references) if p['kind'] == 'answer']
    assert len(ids) == len(set(ids)) == 24


def test_two_naturalization_units_not_repeated_per_variant(config, references):
    units = run.naturalization_plan(config, references)
    assert [(u['scenario_id'], u['generator'], u['max_attempts']) for u in units] == [
        ('pilot-scheduling-01', 'G1', 3), ('pilot-travel-01', 'G2', 3)]
    assert [u['model'] for u in units] == ['openai/gpt-5.6-sol', 'anthropic/claude-fable-5.1']


@pytest.mark.parametrize('history,decision', [
    ([], 'ATTEMPT'), (['TERMINAL_FAILURE'], 'RETRY_SAME_UNIT'),
    (['TERMINAL_FAILURE', 'TERMINAL_FAILURE'], 'RETRY_SAME_UNIT'),
    (['TERMINAL_FAILURE'] * 3, 'UNBUILDABLE_STOP_FOR_RESEARCHER'),
    (['EVALUABLE_PASS'], 'ACCEPT'), (['TERMINAL_FAILURE', 'EVALUABLE_PASS'], 'ACCEPT'),
    (['EVALUABLE_LEVEL1_FAILURE'], 'STOP_FOR_RESEARCHER'),
    (['TERMINAL_FAILURE', 'EVALUABLE_LEVEL1_FAILURE'], 'STOP_FOR_RESEARCHER'),
    (['EVALUABLE_FLUENCY_ONLY'], 'ACCEPT_WITH_PROVENANCE_AWARE_SURFACE_EDIT_OPTION')])
def test_naturalization_attempt_cap_and_stop_rules(history, decision):
    assert run.naturalization_next(history) == decision


@pytest.mark.parametrize('history', [['TERMINAL_FAILURE'] * 4, ['EVALUABLE_PASS', 'TERMINAL_FAILURE'],
                                     ['EVALUABLE_LEVEL1_FAILURE', 'EVALUABLE_PASS'], ['other']])
def test_invalid_naturalization_histories_are_rejected(history):
    with pytest.raises(ValueError):
        run.naturalization_next(history)


def test_naturalization_config_forbids_repair_shortcuts(config):
    n = config['naturalization']
    assert n['max_logical_attempts_per_unit'] == 3 and n['semantic_failure']['regenerate'] is False
    assert set(n['prohibited']) == {'field mixing', 'manual completion', 'selective field retry',
                                    'generator substitution'}
    assert 'probab' not in json.dumps(n).lower()


def test_request_body_uses_pinned_backbone_and_json_object_mode_only():
    for schema in ('answer', 'maintenance_m2', 'maintenance_m3'):
        body = run.request_body(MODEL, {'schema': schema, 'messages': [{'role': 'user', 'content': 'x'}]})
        assert body['model'] == 'meta-llama/llama-3.1-8b-instruct'
        assert body['provider'] == {'order': ['coreweave/bf16'], 'allow_fallbacks': False,
                                    'require_parameters': True}
        assert (body['temperature'], body['top_p'], body['max_tokens']) == (0.0, 1.0, 2048)
        assert body['response_format'] == {'type': 'json_object'}
        assert 'json_schema' not in json.dumps(body) and 'strict' not in json.dumps(body)
        assert body['messages'] == [{'role': 'user', 'content': 'x'}]
    with pytest.raises(ValueError):
        run.request_body(MODEL, {'schema': 'other', 'messages': []})


def test_answer_local_schema_is_identical_for_every_condition_and_forbids_extra_fields():
    schema = prompts.answer_schema()
    assert schema == {'type': 'object', 'properties': {'answer': {'type': 'string', 'minLength': 1}},
                      'required': ['answer'], 'additionalProperties': False}
    bodies = [run.request_body(MODEL, {'schema': 'answer', 'messages': []}) for _ in pol.POLICIES]
    assert len({json.dumps(b['response_format'], sort_keys=True) for b in bodies}) == 1


def test_request_hash_is_stable_and_content_sensitive():
    body = run.request_body(MODEL, {'schema': 'answer', 'messages': [{'role': 'user', 'content': 'x'}]})
    other = run.request_body(MODEL, {'schema': 'answer', 'messages': [{'role': 'user', 'content': 'y'}]})
    assert run.request_sha(body) == run.request_sha(deepcopy(body)) != run.request_sha(other)


def test_preview_is_deterministic_offline_and_contains_no_outcomes(config, references):
    first = run.preview(config, references, MODEL)
    second = run.preview(config, deepcopy(references), MODEL)
    assert first == second
    assert first['live_calls_executed'] == 0 and first['network'] == 'none'
    assert first['plan_counts'] == {'runs': 24, 'backbone_calls': 132, 'maintenance': 108, 'answering': 24}
    assert len(first['runs']) == 18 and len(first['naturalization_units']) == 2
    text = json.dumps(first)
    for word in run.FORBIDDEN_RANKING_KEYS | {'CURRENT_CORRECT', 'STALE_ERROR', 'OTHER_ERROR', 'csa', 'srr'}:
        assert word not in text


def test_preview_writes_nothing_and_needs_no_credentials(config, references, tmp_path, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.chdir(tmp_path)
    run.preview(config, references, MODEL)
    assert list(tmp_path.iterdir()) == []


def test_planning_module_has_no_live_mode(config):
    done = subprocess.run([sys.executable, str(ROOT / 'experiments/run_crst_pilot.py'), '--live'],
                          capture_output=True, text=True)
    assert done.returncode != 0 and 'unrecognized arguments' in done.stderr


def record(logical_id, attempts, usage, latency=1.0, cost=0.5):
    body = run.request_body(MODEL, {'schema': 'answer', 'messages': [{'role': 'user', 'content': logical_id}]})
    return run.logical_record({'logical_id': logical_id}, body,
                              {'content': '{"answer":"x"}', 'usage': usage, 'latency_seconds': latency,
                               'cost': cost, 'attempts': attempts},
                              policy='M2', scenario='s', variant='low', event='U1', model_config=MODEL)


def test_logical_records_carry_the_frozen_evidence_fields():
    rec = record('a', [{'status': 200}], {'prompt_tokens': 10, 'completion_tokens': 2})
    assert run.validate_record(rec)
    assert rec['model'] == 'meta-llama/llama-3.1-8b-instruct' and rec['provider'] == 'coreweave/bf16'
    forged = {**rec, 'request_body': {**rec['request_body'], 'temperature': 1.0}}
    with pytest.raises(Exception):
        run.validate_record(forged)
    with pytest.raises(Exception):
        run.validate_record({k: v for k, v in rec.items() if k != 'usage'})


def test_retry_attempts_are_accounted_separately_from_logical_usage():
    first = record('a', [{'status': 200, 'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}],
                   {'prompt_tokens': 10, 'completion_tokens': 2})
    retried = record('b', [{'status': 503, 'usage': None}, {'status': 429, 'usage': {
        'prompt_tokens': 7, 'completion_tokens': 1}}, {'status': 200}], {'prompt_tokens': 11, 'completion_tokens': 3},
        latency=2.0, cost=0.25)
    totals = run.account_run([first, retried])
    assert totals['logical_calls'] == 2 and totals['physical_attempts'] == 4
    assert totals['logical_token_usage'] == {'prompt_tokens': 21, 'completion_tokens': 5}
    assert totals['retry_token_usage'] == {'prompt_tokens': 7, 'completion_tokens': 1}
    assert totals['retry_attempts_without_usage'] == 1
    assert totals['api_latency_seconds'] == 3.0 and totals['cost'] == 0.75


def test_missing_optional_usage_is_never_replaced_by_a_guess():
    rec = record('a', [{'status': 200}], None, latency=None, cost=None)
    assert rec['usage'] is None and rec['cost'] is None and rec['latency_seconds'] is None


def test_run_summary_has_per_run_evidence_and_no_aggregation(references):
    from crst_common import follow_reference
    reference = references[0]
    result = pol.run_policy('M3', reference, 'low', ask=follow_reference(reference, 'low', 'M3', answer='{"answer":"z"}'),
                            question='q', tokenizer=ToyTokenizer())
    summary = run.summarize_run(result)
    assert summary['classification'] == 'OTHER_ERROR' and summary['moa'] == {'moa_correct': 9, 'moa_total': 9}
    assert summary['active_memory_primary_tokens'] and summary['text_only_memory_tokens']
    assert summary['active_entry_count'] == 7 and len(summary['active_entry_trajectory']) == 16
    assert summary['logical_calls'] == 10
    assert not any(k in summary for k in run.FORBIDDEN_RANKING_KEYS)


def test_b0_coverage_report_uses_the_frozen_budget():
    texts = {label: f'x{label} y' for label in pol.EVENT_ORDER}
    report = run.b0_coverage_report(texts, ToyTokenizer())
    assert report['budget'] == 71 and report['history_tokens'] <= 71 and report['selected_events'][-2:] == ['U7', 'N2']


def test_offline_checklist_passes_every_offline_item_and_leaves_the_rest_pending(config, references):
    results = run.run_offline_checklist(references)
    ids = [i['id'] for i in config['acceptance_checklist']]
    assert list(results) == ids and len(ids) == len(set(ids))
    for item in config['acceptance_checklist']:
        expected = {'OFFLINE': 'PASS_OFFLINE', 'POST_NATURALIZATION': 'PENDING_NATURALIZATION',
                    'POST_RUN': 'PENDING_LIVE'}[item['stage']]
        assert results[item['id']] == expected, item['id']
    assert {i['stage'] for i in config['acceptance_checklist']} == {'OFFLINE', 'POST_NATURALIZATION', 'POST_RUN'}
    pending = {k for k, v in results.items() if v.startswith('PENDING')}
    assert pending == {'DATA-10', 'ANS-02', 'SCR-03', 'ACC-01', 'ACC-02', 'ACC-04'}


def test_every_offline_checklist_item_has_a_check(config):
    offline = {i['id'] for i in config['acceptance_checklist'] if i['stage'] == 'OFFLINE'}
    assert set(run.OFFLINE_CHECKS) == offline - {'DATA-09'}


def test_checklist_detects_a_broken_engine(references, monkeypatch):
    monkeypatch.setattr(pol, 'execute', lambda state, event, decision: (state, pol.EXECUTED, {'kind': 'none'}))
    results = run.run_offline_checklist(references)
    assert results['POL-04'] == 'FAIL' and 'PASS' not in results['POL-04']


def test_naturalization_audit_reuses_the_frozen_semantic_check(material):
    _, fixtures = material
    fixture = fixtures[0]
    output = {v: {e['event']: f'{e["event"]} note' for e in fixture['reference']['variants'][v]['events']}
              for v in ('low', 'medium', 'high')}
    for v in output:
        output[v]['Q'] = 'What is it?'
    audit = run.naturalization_audit(fixture, output)
    assert audit['status'] in ('FAIL', 'MANUAL_REVIEW_REQUIRED')


def test_pilot_modules_never_import_a_network_client_or_read_credentials():
    import ast
    banned = {'httpx', 'requests', 'urllib', 'socket', 'aiohttp', 'asyncio', 'http', 'os', 'subprocess'}
    for name in ('run_crst_pilot', 'crst_policies', 'crst_scoring', 'crst_prompts'):
        tree = ast.parse((ROOT / f'experiments/{name}.py').read_text())
        imported = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not imported & banned, (name, imported & banned)


def test_checklist_has_exactly_32_items_each_with_exactly_one_current_status(config, references):
    items = config['acceptance_checklist']
    results = run.run_offline_checklist(references)
    assert len(items) == 32 and len({i['id'] for i in items}) == 32 and len(results) == 32
    allowed = {'PASS_OFFLINE', 'PENDING_NATURALIZATION', 'PENDING_LIVE'}
    assert all(results[i['id']] in allowed for i in items)
    counts = {status: sum(v == status for v in results.values()) for status in allowed}
    assert counts == {'PASS_OFFLINE': 26, 'PENDING_NATURALIZATION': 2, 'PENDING_LIVE': 4}
    assert sum(counts.values()) == 32
    vocabulary = config['checklist_status_vocabulary']
    assert {i['stage'] for i in items} == set(k for k in vocabulary if k != 'failed_offline_check')
    for item in items:
        assert results[item['id']] == vocabulary[item['stage']]


def test_live_dependent_items_are_never_passed_before_execution(config, references):
    results = run.run_offline_checklist(references)
    for item in config['acceptance_checklist']:
        if item['stage'] != 'OFFLINE':
            assert results[item['id']].startswith('PENDING_') and 'PASS' not in results[item['id']]


def test_backbone_requests_match_the_already_qualified_transport_so_no_new_qualification_is_needed():
    import qualify_model as qm
    qualified = qm.request_body(MODEL, 'M1')
    pilot = run.request_body(MODEL, {'schema': 'maintenance_m2', 'messages': qualified['messages']})
    for key in ('model', 'provider', 'temperature', 'top_p', 'max_tokens', 'response_format'):
        assert pilot[key] == qualified[key]
    assert pilot['response_format'] == {'type': 'json_object'}
    assert MODEL['model']['id'] == qm.MODEL and MODEL['provider']['upstream'] == qm.PROVIDER
    assert run.file_sha('configs/model.yaml') == run.load_config()['backbone']['parameters_sha256']


def test_provenance_records_the_response_mode_and_local_schema_identities(config):
    ids = prompts.identities()
    assert ids['provider_response_mode'] == {'response_format': {'type': 'json_object'}}
    backbone = config['backbone']
    assert backbone['provider_response_mode']['response_format'] == {'type': 'json_object'}
    assert backbone['provider_response_mode']['applies_to'] == ['maintenance', 'answer']
    assert backbone['local_validation'] == {'schemas': 'exact_keys_no_repair', 'sent_to_provider': False}
    assert config['answering']['response_schema_role'] == config['maintenance']['schema_role'] == 'local_validation_only'
    for policy in ('M2', 'M3'):
        assert config['maintenance']['schemas'][policy] == ids[f'maintenance_{policy.lower()}_schema']
    assert config['answering']['response_schema'] == ids['answer_schema']


# --- Final answer-request amendment ---------------------------------------------------------------------

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def test_frozen_answering_system_text_is_byte_and_hash_unchanged(config):
    literal = ("You are a helpful assistant. Use only the information provided in the context to answer the user's "
               "final question.\n\nReply with the answer only.")
    assert prompts.ANSWER_SYSTEM == literal
    assert sha(literal) == '8a6abc2b52c63340aa483023a823c6ff9d8142ab9749b3ae7d6d2f216da5e71e'
    assert prompts.ANSWER_SYSTEM_SHA256 == config['answering']['system']['sha256'] == sha(literal)
    assert config['answering']['system']['version'] == 'crst-pilot-answer/1.0.0'
    assert 'json' not in prompts.ANSWER_SYSTEM.casefold() and 'answer' in prompts.ANSWER_SYSTEM
    b0 = yaml.safe_load((ROOT / 'configs/b0-calibration.yaml').read_text())['system_prompt']
    assert b0['composed_sha256'] == sha(literal)


def test_final_user_requests_are_exactly_the_approved_texts():
    assert prompts.ANSWER_FORMAT_INSTRUCTION == ANSWER_INSTRUCTION
    assert prompts.answer_user_text('CTX', 'Q?') == f'Context:\nCTX\n\nQuestion:\nQ?\n\n{ANSWER_INSTRUCTION}'
    assert prompts.answer_final_user_text('Q?') == f'Question:\nQ?\n\n{ANSWER_INSTRUCTION}'
    assert ANSWER_INSTRUCTION.count('\n') == 2 and ANSWER_INSTRUCTION.count('"answer"') == 2
    tricky = 'What is "the" {question}\nnow?'
    assert tricky in prompts.answer_user_text('CTX', tricky) and tricky in prompts.answer_final_user_text(tricky)


def test_wrapper_version_and_hashes_changed_and_are_recorded(config):
    request = prompts.identities()['answer_request']
    assert request['version'] == 'crst-pilot-answer-request/1.1.0'
    assert request['superseded'] == {'version': 'crst-pilot-answer-request/1.0.0',
                                     'sha256': '458e0a8e8a53ed92620386f4211606a2dac6735dd173782a966047e55cf54f2a'}
    old = 'Context:\n{context}\n\nQuestion:\n{question}'
    assert sha(old) == request['superseded']['sha256']
    assert request['memory_policies_sha256'] == sha('Context:\n{context}\n\nQuestion:\n{question}\n\n' + ANSWER_INSTRUCTION)
    assert request['b0_final_user_sha256'] == sha('Question:\n{question}\n\n' + ANSWER_INSTRUCTION)
    assert request['format_instruction_sha256'] == sha(ANSWER_INSTRUCTION)
    assert request['memory_policies_sha256'] != request['superseded']['sha256']
    assert config['answering']['request'] == request
    assert config['answering']['memory_policies_user_template'] == 'Context:\n{context}\n\nQuestion:\n{question}\n\n' + ANSWER_INSTRUCTION
    assert config['answering']['b0_final_user_template'] == 'Question:\n{question}\n\n' + ANSWER_INSTRUCTION


@pytest.mark.parametrize('mutate', [
    lambda c: c['answering']['request'].__setitem__('version', 'crst-pilot-answer-request/1.0.0'),
    lambda c: c['answering']['request'].__setitem__('b0_final_user_sha256', '0' * 64),
    lambda c: c['answering'].__setitem__('memory_policies_user_template',
                                         'Context:\n{context}\n\nQuestion:\n{question}'),
    lambda c: c['answering'].__setitem__('b0_final_user_template', 'Question:\n{question}')])
def test_wrapper_drift_is_detected(config, mutate):
    broken = deepcopy(config)
    mutate(broken)
    with pytest.raises(Exception):
        run.verify_config(broken)


def test_answer_schema_maintenance_prompts_and_budget_are_unchanged(config):
    ids = prompts.identities()
    assert ids['answer_schema'] == {'version': 'crst-pilot-answer-schema/1.0.0', 'sha256':
                                    'ee52628cf2b7d10e8d9cd8b9a96eb2468b541a9eabb05aef91693a3ed4abba64'}
    assert ids['maintenance_m2_system'] == {'version': 'crst-pilot-maintenance-m2/1.0.0', 'sha256':
                                            'b71c30935771918348d346b58ae32ccf3f0cc9fe836c6382480c6e956721f626'}
    assert ids['maintenance_m3_system'] == {'version': 'crst-pilot-maintenance-m3/1.0.0', 'sha256':
                                            '7027ca9804f5bdf0bca370aa124312d9b4e5d2702e093816a20f19f33a356a75'}
    assert ids['maintenance_m2_schema']['sha256'] == '00fe3cab18d4c25a26e4c04a962822009852568cdc72b77c51bab19ae28cae87'
    assert ids['maintenance_m3_schema']['sha256'] == '5d1b47e125e8732e926e66365f43b62607a8df91556a9a15fe327f8e965c8832'
    assert ids['maintenance_user_template']['sha256'] == '09c0006cd2de916d6be52d258681b04ea3a4c64a901d28db43da83c018fd99be'
    assert pol.B0_CONTEXT_TOKENS == 71 == config['answering']['b0']['b0_context_tokens']
    assert config['answering']['b0']['budget_config_sha256'] == run.file_sha('configs/b0-suffix-calibration.yaml')
    assert pol.TEMPLATE == 'For {entity_name}, the {attribute_meaning} is {current_value}.'


def test_provider_mode_stays_json_object_and_local_answer_schema_stays_exact():
    for schema in ('answer', 'maintenance_m2', 'maintenance_m3'):
        body = run.request_body(MODEL, {'schema': schema, 'messages': []})
        assert body['response_format'] == {'type': 'json_object'}
    assert prompts.answer_schema() == {'type': 'object', 'properties': {'answer': {'type': 'string', 'minLength': 1}},
                                       'required': ['answer'], 'additionalProperties': False}


def test_amended_request_changes_the_derived_request_hashes_and_nothing_else_in_the_plan(config, references):
    first = run.preview(config, references, MODEL)
    assert first['plan_counts'] == {'runs': 24, 'backbone_calls': 132, 'maintenance': 108, 'answering': 24}
    assert len(first['naturalization_units']) == 2
    answers = [r for run_ in first['runs'] for r in run_['requests'] if r['kind'] == 'answer']
    maintenance = [r for run_ in first['runs'] for r in run_['requests'] if r['kind'] == 'maintenance']
    assert len(answers) == 18 and len(maintenance) == 108
