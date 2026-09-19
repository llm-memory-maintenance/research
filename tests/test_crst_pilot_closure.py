"""Closure tests: the archived Small Pilot evidence, the researcher review and the final checklist (read-only)."""
from copy import deepcopy
import json

import pytest

from crst_common import ROOT, material, no_network, references  # noqa: F401
import close_crst_pilot as close
import execute_crst_pilot as ex
import crst_policies as pol
import qualify_generators as q
import run_crst_pilot as run

BACKBONE = close.BACKBONE
REVIEW = json.loads(close.REVIEW.read_text(encoding='utf-8'))
CLOSURE = json.loads(close.CLOSURE.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def evidence():
    return close.verify_evidence()


@pytest.fixture(scope='module')
def report(references):
    """The replay rows rebuilt, in plan order, from the archived run documents only (no tokenizer needed)."""
    rows = []
    for run_id in dict.fromkeys(p['run_id'] for p in run.call_plan(references)):
        document = json.loads((BACKBONE / ex.run_path(run_id)).read_text(encoding='utf-8'))
        rows.append({'run_id': run_id, 'replay': 'MATCH', 'classification': document['classification']['class']})
    return {'rows': rows, 'post_run_checks': {k: 'PASS_POST_RUN' for k in (
        'ACC-01', 'ACC-02', 'ACC-04', 'ACC-05', 'ANS-02', 'DATA-10')} | {'SCR-03': 'PENDING_RESEARCHER_REVIEW'}}


def planned_runs(references):
    return list(dict.fromkeys(p['run_id'] for p in run.call_plan(references)))


# --- Evidence and provenance -----------------------------------------------------------------------------

def test_archived_evidence_has_the_recorded_identities_and_counts(evidence):
    assert evidence['naturalization_audit_sha256'] == '0ff0962bef5b5a3714bab049831ff5a135e308bcc8f8625a91de0fb0cd172f48'
    assert evidence['backbone_collection_sha256'] == 'ee18a9d719a02054ecc782f9ec1f74f726ce1894b5d2dc31dcac2af7e0e4af6f'
    assert evidence['logical_calls'] == {'total': 132, 'maintenance': 108, 'answering': 24} and evidence['runs'] == 24
    assert evidence['aborted'] is False and evidence['routing_provider_model_verified'] is True
    assert evidence['files_verified'] == {'backbone': 157, 'naturalization': 5}
    assert evidence['b0_context_tokens'] == pol.B0_CONTEXT_TOKENS == 71


def test_archived_evidence_is_not_mutated_and_is_never_rewritten():
    for directory in (BACKBONE, close.NATURALIZATION):
        for name, checksum in q.read_sums(directory).items():
            assert close.file_hash(directory / name) == checksum
    with pytest.raises(FileExistsError):
        q.publish(close.REVIEW, REVIEW)
    with pytest.raises(FileExistsError):
        q.publish(close.CLOSURE, CLOSURE)


def test_verification_fails_on_a_tampered_or_incomplete_collection(tmp_path):
    import shutil
    copy = tmp_path / 'backbone'
    shutil.copytree(BACKBONE, copy)
    victim = copy / next(n for n in q.read_sums(copy) if n.startswith('records/'))
    victim.write_text(victim.read_text().replace('CoreWeave', 'Other'))
    with pytest.raises(ValueError, match='drifted'):
        close.verify_evidence(backbone=copy)


# --- Researcher review ------------------------------------------------------------------------------------

def test_review_is_bound_to_the_backbone_collection_and_approved_without_disagreement(evidence):
    assert REVIEW['schema_version'] == close.REVIEW_SCHEMA and REVIEW['decision'] == 'APPROVED'
    assert REVIEW['reviewer'] == 'Muhammad Rafly Ash Shiddiqi' and REVIEW['review_date'] == '2026-09-20'
    assert REVIEW['backbone_collection_sha256'] == evidence['backbone_collection_sha256'] == (
        'ee18a9d719a02054ecc782f9ec1f74f726ce1894b5d2dc31dcac2af7e0e4af6f')
    assert REVIEW['backbone_sha256sums_sha256'] == evidence['backbone_sha256sums_sha256']
    assert REVIEW['naturalization_audit_sha256'] == evidence['naturalization_audit_sha256']
    assert (REVIEW['rows_reviewed'], REVIEW['classifications_confirmed'], REVIEW['disagreements']) == (24, 24, 0)
    assert REVIEW['checklist_item'] == 'SCR-03' and REVIEW['scr_03'] == 'PASS_RESEARCHER_REVIEW'


def test_review_covers_exactly_the_24_archived_runs_and_classifications(evidence, report, references):
    assert close.verify_review(REVIEW, report, evidence)
    assert [r['run_id'] for r in REVIEW['reviewed_rows']] == [r['run_id'] for r in report['rows']]
    assert sorted(r['run_id'] for r in REVIEW['reviewed_rows']) == sorted(planned_runs(references))
    assert len(REVIEW['reviewed_rows']) == 24 == len({r['run_id'] for r in REVIEW['reviewed_rows']})
    assert REVIEW['reviewed_rows_sha256'] == close.rows_sha(REVIEW['reviewed_rows'])


def test_review_records_no_policy_interpretation_or_aggregate():
    assert REVIEW['scope'] == close.SCOPE and 'No policy interpretation' in REVIEW['scope']
    body = {k: v for k, v in REVIEW.items() if k != 'scope'}
    text = json.dumps(body).lower()
    for word in ('better', 'worse', 'rank', 'accuracy', 'csa', 'srr', 'moa', 'mean', 'winner'):
        assert word not in text
    assert set(REVIEW) == {'schema_version', 'reviewer', 'review_date', 'decision', 'backbone_collection_sha256',
                           'backbone_sha256sums_sha256', 'naturalization_audit_sha256', 'rows_reviewed',
                           'classifications_confirmed', 'disagreements', 'reviewed_rows', 'reviewed_rows_sha256',
                           'checklist_item', 'scr_03', 'scope'}
    assert all(set(row) == {'run_id', 'classification'} for row in REVIEW['reviewed_rows'])


@pytest.mark.parametrize('mutate', [
    lambda r: r.__setitem__('backbone_collection_sha256', '0' * 64),
    lambda r: r.__setitem__('naturalization_audit_sha256', '0' * 64),
    lambda r: r.__setitem__('decision', 'REJECTED'),
    lambda r: r.__setitem__('disagreements', 1),
    lambda r: r.__setitem__('rows_reviewed', 23),
    lambda r: r.__setitem__('scr_03', 'PENDING_RESEARCHER_REVIEW'),
    lambda r: r['reviewed_rows'].pop(),
    lambda r: r['reviewed_rows'][0].__setitem__('classification', 'OTHER_ERROR'),
    lambda r: r.__setitem__('extra', 1)])
def test_a_review_that_is_not_bound_complete_and_approved_is_rejected(evidence, report, mutate):
    broken = deepcopy(REVIEW)
    mutate(broken)
    with pytest.raises(ValueError):
        close.verify_review(broken, report, evidence)


def test_only_an_approved_complete_review_can_be_recorded(evidence, report):
    good = dict(reviewer='r', date='2026-09-20', decision='APPROVED', rows_reviewed=24, disagreements=0)
    assert close.build_review(report, evidence, **good)['scr_03'] == 'PASS_RESEARCHER_REVIEW'
    for override in ({'decision': 'REJECTED'}, {'disagreements': 1}, {'rows_reviewed': 23}):
        with pytest.raises(ValueError):
            close.build_review(report, evidence, **{**good, **override})
    partial = {**report, 'rows': report['rows'][:23]}
    with pytest.raises(ValueError):
        close.build_review(partial, evidence, **{**good, 'rows_reviewed': 23})
    mismatch = {**report, 'rows': [{**report['rows'][0], 'replay': 'MISMATCH'}, *report['rows'][1:]]}
    with pytest.raises(ValueError):
        close.build_review(mismatch, evidence, **good)


# --- Final checklist --------------------------------------------------------------------------------------

def test_all_32_items_have_a_final_non_pending_state_and_scr_03_resolves_through_the_review(
        evidence, report, references):
    states = close.final_checklist(references, report, REVIEW, evidence, longmemeval=False)
    config = run.load_config()
    assert list(states) == [i['id'] for i in config['acceptance_checklist']] and len(states) == 32
    assert set(states.values()) <= set(close.FINAL_STATES) and not any('PENDING' in v for v in states.values())
    assert states['SCR-03'] == 'PASS_RESEARCHER_REVIEW'
    assert close.counts(states) == {'PASS_OFFLINE': 25, 'PASS_POST_RUN': 6, 'PASS_RESEARCHER_REVIEW': 1}
    assert {k for k, v in states.items() if v == 'PASS_POST_RUN'} == {'ACC-01', 'ACC-02', 'ACC-04', 'ACC-05',
                                                                      'ANS-02', 'DATA-10'}


def test_scr_03_does_not_pass_from_replay_classifications_alone(evidence, report, references):
    broken = {**deepcopy(REVIEW), 'backbone_collection_sha256': '1' * 64}
    with pytest.raises(ValueError, match='not bound'):
        close.final_checklist(references, report, broken, evidence, longmemeval=False)
    assert report['post_run_checks']['SCR-03'] == 'PENDING_RESEARCHER_REVIEW'


def test_a_failed_post_run_check_blocks_the_final_checklist(evidence, report, references):
    failing = {**report, 'post_run_checks': {**report['post_run_checks'], 'ANS-02': 'FAIL'}}
    with pytest.raises(ValueError, match='ANS-02'):
        close.final_checklist(references, failing, REVIEW, evidence, longmemeval=False)


# --- Closure record ---------------------------------------------------------------------------------------

def test_closure_records_the_final_state_and_binds_the_evidence(evidence):
    assert CLOSURE['schema_version'] == close.CLOSURE_SCHEMA and CLOSURE['status'] == 'CLOSED'
    assert (CLOSURE['execution_status'], CLOSURE['mechanical_validation']) == ('COMPLETE', 'PASS')
    assert CLOSURE['evidence'] == evidence and CLOSURE['policy_runs'] == 24
    assert CLOSURE['scenarios'] == ['pilot-scheduling-01', 'pilot-travel-01']
    assert CLOSURE['researcher_review_sha256'] == close.file_hash(close.REVIEW)
    assert CLOSURE['replay'] == {'runs_replayed': 24, 'runs_matching': 24}
    checklist = CLOSURE['checklist']
    assert checklist['items'] == len(checklist['final_states']) == 32 and checklist['pending'] == 0
    assert checklist['counts'] == close.counts(checklist['final_states'])
    assert set(checklist['final_states'].values()) <= set(close.FINAL_STATES)
    assert checklist['final_states']['SCR-03'] == 'PASS_RESEARCHER_REVIEW'
    assert CLOSURE['evidence']['b0_context_tokens'] == 71


def test_closure_is_mechanical_only_and_contains_no_ranking_or_effect_summary():
    assert 'Pre-main mechanical validation only' in CLOSURE['scope']
    assert 'not effect estimates' in CLOSURE['scope'] and 'power' in CLOSURE['scope']
    assert CLOSURE['outcome_aggregates'] is None
    text = json.dumps(CLOSURE)
    for word in run.FORBIDDEN_RANKING_KEYS - {'aggregate'}:
        assert f'"{word}"' not in text
    for label in ('CURRENT_CORRECT', 'STALE_ERROR', 'OTHER_ERROR'):
        assert label not in text


def test_the_frozen_protocol_config_is_unchanged_and_still_bound_to_the_runs():
    assert CLOSURE['protocol_config_sha256'] == close.file_hash(run.CONFIG_PATH)
    provenance = json.loads((BACKBONE / 'collection.json').read_text())['provenance']
    assert provenance['config_sha256'] == close.file_hash(run.CONFIG_PATH)
    assert run.load_config()['execution_status'] == 'NOT_EXECUTED'


def test_closure_documentation_states_mechanical_validation_only():
    for path in ('docs/crst-specification.md', 'docs/decisions.md'):
        text = (ROOT / path).read_text(encoding='utf-8')
        assert 'Small Pilot' in text and 'mechanical validation' in text
    spec = (ROOT / 'docs/crst-specification.md').read_text(encoding='utf-8')
    assert 'not effect estimates, rankings, or inputs to statistical power' in spec
    assert 'no pilot results\nexist' not in spec
