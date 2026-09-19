"""Offline closure of the CRST Small Pilot: evidence verification, researcher review, final checklist, closure.

Nothing here contacts a provider or reruns a live step. Raw evidence is only read. The pilot is a mechanical
validation; no outcome is aggregated, ranked or interpreted.
"""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import crst_policies as pol
import crst_prompts as prompts
import execute_crst_pilot as ex
import naturalize_crst_pilot as nat
import probe_generators as probe
import qualify_generators as q
import run_crst_pilot as run
import validate_generator_qualification_fixtures as gq

ROOT = gq.ROOT
REVIEW_SCHEMA = 'crst-pilot-scoring-review/1.0.0'
CLOSURE_SCHEMA = 'crst-small-pilot-closure/1.0.0'
BACKBONE = ROOT / 'results/crst-small-pilot/backbone/attempt-01'
NATURALIZATION = ROOT / 'results/crst-small-pilot/naturalization/attempt-01'
AUDIT = ROOT / 'results/crst-small-pilot/naturalization/audit/attempt-01.json'
REVIEW = ROOT / 'results/crst-small-pilot/review/attempt-01.json'
CLOSURE = ROOT / 'results/crst-small-pilot/closure/attempt-01.json'
FINAL_STATES = ('PASS_OFFLINE', 'PASS_POST_RUN', 'PASS_RESEARCHER_REVIEW')
SCOPE = ('Mechanical cross-check of each final-answer classification against the deterministic scorer. '
         'No policy interpretation, ranking, effect estimate or power-analysis input is recorded or implied.')
require = gq.require


def file_hash(path):
    return probe.file_hash(Path(path))


def rows_sha(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def committed_hash(commit, path):
    return hashlib.sha256(nat.git('show', f'{commit}:{path}')).hexdigest()


def verify_evidence(backbone=BACKBONE, naturalization=NATURALIZATION, audit=AUDIT, config_path=run.CONFIG_PATH):
    """Read-only checks of identities, integrity, routing, counts and provenance. Raises on any failure."""
    config = run.load_config(config_path)
    run.verify_config(config)
    model = ex.load_model(config)
    nat_collection, _ = nat.verified_collection(naturalization)
    sums = q.read_sums(Path(backbone))
    for name, checksum in sums.items():
        require(file_hash(Path(backbone) / name) == checksum, f'Archived file drifted: {name}')
    collection = json.loads((Path(backbone) / 'collection.json').read_text(encoding='utf-8'))
    require(collection['status'] == 'COMPLETE' and collection['failure_reason'] is None
            and collection['interpretation'] == 'OFFLINE_REPLAY_THEN_RESEARCHER_REVIEW'
            and nat_collection['status'] == 'COMPLETE' and nat_collection['failure_reason'] is None,
            'A collection is not a complete, unaborted execution')
    require(len(collection['runs']) == collection['planned_runs'] == 24
            and collection['planned_backbone_calls'] == 132, 'Run count')
    audit_record = json.loads(Path(audit).read_text(encoding='utf-8'))
    provenance, nat_provenance = collection['provenance'], nat_collection['provenance']
    require(audit_record['status'] == 'ELIGIBLE' and audit_record['semantic_status'] == 'PASS'
            and audit_record['collection_sha256'] == file_hash(Path(naturalization) / 'collection.json')
            and audit_record['sha256sums_sha256'] == file_hash(Path(naturalization) / 'SHA256SUMS'),
            'Naturalization audit identity')
    require(provenance['naturalization_audit_sha256'] == file_hash(audit)
            and provenance['naturalization_collection_sha256'] == file_hash(Path(naturalization) / 'collection.json')
            and provenance['eligibility_status'] == 'ELIGIBLE', 'Backbone provenance does not link the naturalization')
    records = {}
    for name in sums:
        if name.startswith('records/'):
            record = json.loads((Path(backbone) / name).read_text(encoding='utf-8'))
            run.validate_record(record)
            records[record['logical_id']] = record
    planned = ex.logical_ids(run.load_fixtures())
    require(sorted(records) == sorted(planned) and len(records) == 132, 'Logical request set')
    maintenance = sum(not i.endswith('/A') for i in records)
    require((maintenance, len(records) - maintenance) == (108, 24), 'Maintenance/answer split')
    pinned = model['model']['id'], [model['provider']['upstream']]
    for record in records.values():
        body = record['request_body']
        require(record['request_status'] == 'success' and record['routing_ok'] is True
                and record['accounting_ok'] is True and record['model'] == pinned[0]
                and body['model'] == pinned[0] and body['provider'] == {
                    'order': pinned[1], 'allow_fallbacks': False, 'require_parameters': True}
                and body['response_format'] == {'type': 'json_object'} and record['attempts'],
                f'Routing/provider/accounting requirement failed: {record["logical_id"]}')
    documents = [json.loads((Path(backbone) / n).read_text(encoding='utf-8')) for n in sums if n.startswith('runs/')]
    require(len(documents) == 24 and sorted(d['run_id'] for d in documents) == sorted(collection['runs'])
            and all(sum(l in records for l in d['logical_ids']) == len(d['logical_ids']) for d in documents),
            'Run documents')
    for who, prov, commit_key in (('backbone', provenance, 'implementation'),
                                  ('naturalization', nat_provenance, 'implementation')):
        commit = prov['source_commit']
        nat.git('merge-base', '--is-ancestor', commit, 'HEAD')
        require(all(committed_hash(commit, path) == digest for path, digest in prov[commit_key].items()),
                f'{who} implementation differs from its source commit')
        require(committed_hash(commit, 'configs/crst-small-pilot.yaml') == prov['config_sha256'],
                f'{who} config differs from its source commit')
    require(provenance['prompt_identities'] == prompts.identities()
            and provenance['material_manifest_sha256'] == config['material']['manifest_sha256']
            == file_hash(ROOT / 'data/crst-small-pilot/manifest.json'), 'Prompt/material identities')
    b0 = yaml_b0()
    require(pol.B0_CONTEXT_TOKENS == 71 == b0 == config['answering']['b0']['b0_context_tokens'], 'B0 budget')
    return {'backbone_collection_sha256': file_hash(Path(backbone) / 'collection.json'),
            'backbone_sha256sums_sha256': file_hash(Path(backbone) / 'SHA256SUMS'),
            'naturalization_collection_sha256': file_hash(Path(naturalization) / 'collection.json'),
            'naturalization_audit_sha256': file_hash(audit),
            'files_verified': {'backbone': len(sums), 'naturalization': len(q.read_sums(Path(naturalization)))},
            'logical_calls': {'total': 132, 'maintenance': maintenance, 'answering': len(records) - maintenance},
            'runs': 24, 'physical_attempts': sum(len(r['attempts']) for r in records.values()),
            'retried_logical_requests': sum(len(r['attempts']) > 1 for r in records.values()),
            'aborted': False, 'routing_provider_model_verified': True, 'b0_context_tokens': 71,
            'source_commits': {'naturalization': nat_provenance['source_commit'],
                               'backbone': provenance['source_commit']}}


def yaml_b0():
    import yaml
    return yaml.safe_load((ROOT / 'configs/b0-suffix-calibration.yaml').read_text(encoding='utf-8'))['b0_context_tokens']


def review_rows(report):
    return [{'run_id': r['run_id'], 'classification': r['classification']} for r in report['rows']]


def build_review(report, evidence, *, reviewer, date, decision, rows_reviewed, disagreements):
    require(decision == 'APPROVED' and disagreements == 0, 'Only an approved review without disagreements is recorded')
    require(rows_reviewed == len(report['rows']) == 24 and {r['replay'] for r in report['rows']} == {'MATCH'},
            'The review must cover all 24 replayed runs')
    rows = review_rows(report)
    return {'schema_version': REVIEW_SCHEMA, 'reviewer': reviewer, 'review_date': date, 'decision': decision,
            'backbone_collection_sha256': evidence['backbone_collection_sha256'],
            'backbone_sha256sums_sha256': evidence['backbone_sha256sums_sha256'],
            'naturalization_audit_sha256': evidence['naturalization_audit_sha256'],
            'rows_reviewed': rows_reviewed, 'classifications_confirmed': rows_reviewed, 'disagreements': 0,
            'reviewed_rows': rows, 'reviewed_rows_sha256': rows_sha(rows), 'checklist_item': 'SCR-03',
            'scr_03': 'PASS_RESEARCHER_REVIEW', 'scope': SCOPE}


def verify_review(review, report, evidence):
    """The review must belong to this collection and to exactly the replayed classifications."""
    require(set(review) == {'schema_version', 'reviewer', 'review_date', 'decision', 'backbone_collection_sha256',
                            'backbone_sha256sums_sha256', 'naturalization_audit_sha256', 'rows_reviewed',
                            'classifications_confirmed', 'disagreements', 'reviewed_rows', 'reviewed_rows_sha256',
                            'checklist_item', 'scr_03', 'scope'}
            and review['schema_version'] == REVIEW_SCHEMA, 'Review fields')
    require(review['backbone_collection_sha256'] == evidence['backbone_collection_sha256']
            and review['backbone_sha256sums_sha256'] == evidence['backbone_sha256sums_sha256']
            and review['naturalization_audit_sha256'] == evidence['naturalization_audit_sha256'],
            'The review is not bound to this collection')
    require(review['decision'] == 'APPROVED' and review['rows_reviewed'] == review['classifications_confirmed'] == 24
            and review['disagreements'] == 0 and review['scr_03'] == 'PASS_RESEARCHER_REVIEW'
            and review['checklist_item'] == 'SCR-03' and review['scope'] == SCOPE, 'Review decision')
    require(review['reviewed_rows'] == review_rows(report)
            and review['reviewed_rows_sha256'] == rows_sha(review['reviewed_rows'])
            and len({r['run_id'] for r in review['reviewed_rows']}) == 24, 'Reviewed rows differ from the replay')
    return True


def final_checklist(fixtures, report, review, evidence, longmemeval=True):
    """One explicit final state per item, resolved from archived evidence; SCR-03 only through the review."""
    states = run.run_offline_checklist(fixtures, longmemeval=longmemeval)
    for item, state in report['post_run_checks'].items():
        if item != 'SCR-03':
            require(state == 'PASS_POST_RUN', f'{item} did not pass on the archived evidence')
            states[item] = state
    verify_review(review, report, evidence)
    states['SCR-03'] = 'PASS_RESEARCHER_REVIEW'
    config = run.load_config()
    order = [i['id'] for i in config['acceptance_checklist']]
    require(list(states) == order and len(order) == 32 and set(states.values()) <= set(FINAL_STATES),
            'Every checklist item needs a final passing state')
    return states


def counts(states):
    return {s: sum(v == s for v in states.values()) for s in FINAL_STATES}


def build_closure(states, evidence, review_path, review):
    return {'schema_version': CLOSURE_SCHEMA, 'status': 'CLOSED', 'execution_status': 'COMPLETE',
            'mechanical_validation': 'PASS', 'closed_on': review['review_date'],
            'scope': 'Pre-main mechanical validation only. Observed pilot outcomes are not effect estimates, '
                     'policy rankings, or inputs to statistical power or sample-size decisions.',
            'scenarios': [s['scenario_id'] for s in ex.run.material.SCENARIOS], 'policy_runs': 24,
            'evidence': evidence, 'researcher_review_sha256': file_hash(review_path),
            'replay': {'runs_replayed': 24, 'runs_matching': 24},
            'checklist': {'final_states': states, 'counts': counts(states), 'items': len(states), 'pending': 0},
            'protocol_config_sha256': file_hash(run.CONFIG_PATH),
            'protocol_config_note': 'The frozen protocol config is intentionally unchanged; it is bound to the '
                                    'provenance of the archived runs.',
            'outcome_aggregates': None}


def replay_report(args):
    ns = SimpleNamespace(config=run.CONFIG_PATH, eligibility=args.eligibility,
                         naturalization_directory=args.naturalization_directory,
                         tokenizer_directory=args.tokenizer_directory)
    return ex.replay(args.backbone, ex.replay_inputs(ns))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backbone', type=Path, default=BACKBONE)
    parser.add_argument('--naturalization-directory', type=Path, default=NATURALIZATION)
    parser.add_argument('--eligibility', type=Path, default=AUDIT)
    parser.add_argument('--tokenizer-directory', type=Path, default=None)
    parser.add_argument('--verify', action='store_true', help='Verify the archived evidence and print identities')
    parser.add_argument('--record-review', type=Path, help='New immutable researcher-review artifact')
    parser.add_argument('--reviewer')
    parser.add_argument('--review-date')
    parser.add_argument('--decision')
    parser.add_argument('--rows-reviewed', type=int)
    parser.add_argument('--disagreements', type=int)
    parser.add_argument('--close', type=Path, help='New immutable closure record')
    parser.add_argument('--review', type=Path, default=REVIEW)
    args = parser.parse_args(argv)
    evidence = verify_evidence(args.backbone, args.naturalization_directory, args.eligibility)
    if args.record_review:
        report = replay_report(args)
        review = build_review(report, evidence, reviewer=args.reviewer, date=args.review_date,
                              decision=args.decision, rows_reviewed=args.rows_reviewed,
                              disagreements=args.disagreements)
        args.record_review.parent.mkdir(parents=True, exist_ok=True)
        print('review sha256:', q.publish(args.record_review, review))
    elif args.close:
        report = replay_report(args)
        review = json.loads(args.review.read_text(encoding='utf-8'))
        states = final_checklist(run.load_fixtures(), report, review, evidence)
        args.close.parent.mkdir(parents=True, exist_ok=True)
        print('closure sha256:', q.publish(args.close, build_closure(states, evidence, args.review, review)))
        print(json.dumps(counts(states)))
    else:
        print(json.dumps(evidence, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
