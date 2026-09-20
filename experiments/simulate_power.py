"""CRST power simulation runner: cell enumeration, lme4 bridge, checkpointed replicates and aggregation.

Offline and configuration-driven. A simulation cell is one DGP condition fitted with one random-effects structure.
Replicate data depend only on the DGP cell identity and the replicate index, so every structure sees the same
datasets and results are identical for any execution order or worker count. Batches are fixed replicate ranges,
written once; an interrupted run resumes by skipping batches already on disk.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

import numpy as np

import power_simulation as ps

R_SCRIPT = Path(__file__).resolve().with_name('fit_glmm.R')
# 0.2.0 stores per-replicate fit flags (convergence warning, vcov warning, singular) separately from status and
# names each batch after the replicate IDs it holds. Batches written by 0.1.0 lack those fields and are refused.
RESULT_SCHEMA = 'crst-power-batch/0.2.0'
UNSET = object()  # distinguishes "caller gave no request count" from "the request count is unknown" (None)


# --- Cells ---------------------------------------------------------------------------------------------------

def dgp_fields(point, endpoint, reference, revision_profile, het, scenario, target_scale, anchor, n, r):
    return {'point': point, 'endpoint': endpoint, 'reference': f'{reference:.2f}',
            'revision_profile': revision_profile, 'het': het, 'scenario': scenario, 'target_scale': target_scale,
            'anchor': anchor, 'N': n, 'R': r}


def grid_points(config, include_robustness=True):
    """The pre-specified fractional nuisance points, plus the separate robustness point."""
    points = [(name, spec, 'primary') for name, spec in config['nuisance_grid'].items()]
    if include_robustness:
        points += [(name, spec, 'stress') for name, spec in config['robustness_grid'].items()]
    return points


def enumerate_cells(n, r, structures=ps.STRUCTURES, points=None, target_scales=None, config=None,
                    include_robustness=True):
    """Every (DGP condition x structure) cell for one design point, over the fractional grid, never the full
    Cartesian crossing. Only cells whose family is 'primary' may determine primary N."""
    config = config or ps.load_config()
    ps.check_design(n, r, config)
    target_scales = target_scales or (config['calibration']['primary_target_scale'],)
    anchor = config['calibration']['anchor']
    selected = points or grid_points(config, include_robustness)
    library = ps.scenarios(config)
    cells, invalid = [], []
    for point, spec, grid in selected:
        for endpoint in ps.ENDPOINTS:
            reference = spec['references'][endpoint]
            for scenario, definition in library.items():
                for scale in target_scales:
                    fields = dgp_fields(point, endpoint, reference, spec['revision_profile'], spec['het'],
                                        scenario, scale, anchor, n, r)
                    try:
                        ps.build_dgp(endpoint, reference, spec['revision_profile'], spec['het'], scenario, scale,
                                     anchor, config)
                    except ValueError as exc:
                        invalid.append({'dgp': fields, 'reason': str(exc)})
                        continue
                    family = 'stress' if grid == 'stress' else definition['family']
                    for structure in structures:
                        cells.append({'dgp': fields, 'structure': structure, 'grid': grid, 'family': family})
    return cells, invalid


def dgp_of(fields, config):
    return ps.build_dgp(fields['endpoint'], float(fields['reference']), fields['revision_profile'], fields['het'],
                        fields['scenario'], fields['target_scale'], fields['anchor'], config)


def stage_decision(decision, stage, config):
    """Screening resolution never produces a final PASS/FAIL for Type-I or coverage."""
    if stage == 'screening':
        return config['screening_decision_labels'][decision]
    return decision


def cell_key(cell):
    return ps.cell_id({**cell['dgp'], 'structure': cell['structure']})


def cell_directory(root, cell):
    return Path(root) / ps.derive_seed(0, cell_key(cell), 0, 'directory').to_bytes(8, 'big').hex()


# --- Fitting bridge ----------------------------------------------------------------------------------------------

def fit_control(config):
    f = config['fitting']
    return {k: f[k] for k in ('optimizer', 'maxfun', 'grad_tol', 'singular_tol', 'nagq')}


class RFitter:
    """Runs fit_glmm.R on a batch of jobs. Refuses clearly when R is unavailable."""

    def __init__(self, config, rscript=None):
        self.rscript = rscript or config['fitting']['rscript']
        self.control = fit_control(config)
        if shutil.which(self.rscript) is None:
            raise RuntimeError(f'{self.rscript} not found: R with lme4 and jsonlite is required for fitting')

    def __call__(self, jobs):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'in.json', Path(directory) / 'out.json'
            source.write_text(json.dumps({'control': self.control, 'jobs': jobs}), encoding='utf-8')
            subprocess.run([self.rscript, '--vanilla', str(R_SCRIPT), str(source), str(target)], check=True,
                           capture_output=True, text=True)
            output = json.loads(target.read_text(encoding='utf-8'))
        return output['versions'], {r['job_id']: r['fits'] for r in output['results']}


def job(job_id, data, structure):
    columns = ('scenario', 'P1', 'P2', 'V1', 'V2', 'y', 'n')
    return {'job_id': job_id, 'formulas': ps.formulas(structure), 'data': {c: data[c] for c in columns}}


def normalize_fit(fit):
    """jsonlite unboxes length-one vectors; restore lists so the record shape does not depend on length."""
    if fit is None or fit.get('status') != 'fitted':
        return fit
    out = dict(fit)
    for key in ('re_components', 're_sd', 'convergence_warnings', 'vcov_warnings', 'messages', 'vcov_names'):
        if isinstance(out.get(key), (str, int, float)):
            out[key] = [out[key]]
    return out


# --- Replicate analysis ---------------------------------------------------------------------------------------

def analyze_replicate(fits, structure, config):
    """Raw per-replicate evidence: fit statuses, H1 inference for both estimands, and the H2 LRT."""
    tol = config['fitting']['singular_tol']
    full = normalize_fit(fits.get('full'))
    reduced = normalize_fit(fits.get('reduced'))
    status_full = ps.classify_fit(full, structure, ps.FIXED_NAMES, tol)
    status_reduced = ps.classify_fit(reduced, structure, ps.REDUCED_NAMES, tol)
    kept = ('fit_returned', 'inference_usable', 'status', *ps.FIT_FLAGS, 'boundary', 'components', 'messages')
    record = {'full': {k: status_full[k] for k in kept}, 'reduced': {k: status_reduced[k] for k in kept},
              'h1': None, 'h2': None}
    nodes = config['calibration']['gauss_hermite_nodes']
    if status_full['status'] == 'ok':
        covariance = ps.fitted_covariance(status_full['components'])
        record['h1'] = {e: ps.h1_inference(status_full['beta'], status_full['vcov'], covariance, e,
                                           config['inference']['ci_level'], nodes) for e in ps.ESTIMANDS}
    if status_full['status'] == 'ok' and status_reduced['status'] == 'ok':
        record['h2'] = ps.h2_lrt(status_full['loglik'], status_reduced['loglik'],
                                 config['inference']['h2_interaction_df'],
                                 config['fitting']['lrt_negative_tolerance'])
    return record


def run_batch(cell, replicates, fitter, config):
    dgp = dgp_of(cell['dgp'], config)
    dgp_id = ps.cell_id(cell['dgp'])
    seed = config['monte_carlo']['master_seed']
    jobs = []
    for replicate in replicates:
        data = ps.simulate_data(dgp['beta'], dgp['covariance'], cell['dgp']['N'], cell['dgp']['R'],
                                ps.rng_for(seed, dgp_id, replicate))
        jobs.append(job(str(replicate), data, cell['structure']))
    versions, fits = fitter(jobs)
    return versions, [{'replicate': r, 'seed': ps.derive_seed(seed, dgp_id, r),
                       **analyze_replicate(fits[str(r)], cell['structure'], config)} for r in replicates]


def environment():
    return {'python': platform.python_version(), 'numpy': np.__version__,
            'pyyaml': importlib.metadata.version('pyyaml')}


def present_replicates(directory):
    """Replicate IDs actually stored, read from the records themselves rather than from file names."""
    return {record['replicate'] for record in read_records(directory)}


def requested_replicates(directory):
    path = Path(directory) / 'requested.json'
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding='utf-8'))['replicates'])


def record_request(directory, replicates):
    """Union of every replicate ID ever requested for this cell, so aggregation can verify coverage."""
    union = sorted(requested_replicates(directory) | set(replicates))
    (Path(directory) / 'requested.json').write_text(
        json.dumps({'replicates': union}, sort_keys=True) + '\n', encoding='utf-8')
    return union


def coverage(directory, requested=None):
    """Requested-versus-present replicate coverage.

    Without the request manifest the requested set is unknown, so coverage fails closed as UNKNOWN rather than
    reporting COMPLETE from a requested count of zero.
    """
    present = present_replicates(directory)
    if requested is None and not (Path(directory) / 'requested.json').exists():
        return {'requested': None, 'present': len(present), 'missing': None, 'status': 'UNKNOWN',
                'reason': 'requested.json is absent: requested-replicate provenance is missing, so the stored '
                          'replicates cannot be shown to cover any request'}
    wanted = set(requested) if requested is not None else requested_replicates(directory)
    missing = sorted(wanted - present)
    return {'requested': len(wanted), 'present': len(present), 'missing': missing,
            'status': 'COMPLETE' if not missing else 'INCOMPLETE'}


def run_cell(cell, replicates, fitter, root, config, workers=1):
    """Run exactly the requested replicate IDs that are not already stored.

    Resume is decided by the replicate IDs actually present, never by batch-file names, so an arbitrary range
    completes its missing IDs while stored ones are never rerun or overwritten. Each batch file is named after the
    IDs it holds, and the run fails loudly if any requested ID is still absent afterwards.
    """
    size = config['fitting']['batch_size']
    directory = cell_directory(root, cell)
    directory.mkdir(parents=True, exist_ok=True)
    cell_file = directory / 'cell.json'
    if not cell_file.exists():
        cell_file.write_text(json.dumps(cell, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    elif json.loads(cell_file.read_text(encoding='utf-8')) != cell:
        raise ValueError('Output directory belongs to another cell')
    requested = sorted(set(replicates))
    record_request(directory, requested)
    missing = sorted(set(requested) - present_replicates(directory))
    pending = [missing[i:i + size] for i in range(0, len(missing), size)]

    def work(batch):
        versions, records = run_batch(cell, batch, fitter, config)
        payload = {'schema_version': RESULT_SCHEMA, 'cell': cell, 'cell_key': cell_key(cell),
                   'replicates': batch, 'fit_control': fit_control(config), 'versions': versions,
                   'environment': environment(), 'records': records}
        with (directory / f'batch-{batch[0]:06d}-{batch[-1]:06d}.json').open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(payload, sort_keys=True) + '\n')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, pending))
    outstanding = coverage(directory, requested)
    if outstanding['status'] != 'COMPLETE':
        raise ValueError(f'Replicates requested but not produced: {outstanding["missing"]}')
    return directory


# --- Aggregation ------------------------------------------------------------------------------------------------

def read_records(directory):
    records = {}
    for path in sorted(Path(directory).glob('batch-*.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('schema_version') != RESULT_SCHEMA:
            raise ValueError(f'{path.name} uses {payload.get("schema_version")}, not {RESULT_SCHEMA}; '
                             'regenerate the cell rather than mixing schemas')
        for record in payload['records']:
            if record['replicate'] in records:
                raise ValueError('Duplicate replicate')
            records[record['replicate']] = record
    return [records[k] for k in sorted(records)]


def test_role(cell, dgp, contrast=None, estimand=None):
    """null / alternative / other for one test in one DGP; truth is computed from the true parameters."""
    spec = dgp['spec']
    if contrast is None:
        if dgp['truth']['interaction_absent']:
            return 'null'
        return 'alternative' if spec['h2_alternative'] else 'other'
    value = dgp['truth'][estimand][contrast]
    if abs(value) < ps.NULL_TOL:
        return 'null'
    if spec['h1_target'] == contrast and ps.ESTIMANDS[estimand] == cell['dgp']['target_scale']:
        return 'alternative'
    return 'other'


def summarize_cell(cell, records, config, requested=UNSET, stage='screening'):
    """Monte Carlo summary with failure counts, intervals and acceptance decisions for every test."""
    dgp = dgp_of(cell['dgp'], config)
    acceptance = config['acceptance'][cell['grid']]
    level = config['monte_carlo']['interval']['level']
    alpha = config['inference']['alpha']
    thresholds = config['inference']['planning_thresholds']
    n = len(records)
    status_counts = {s: sum(r['full']['status'] == s for r in records) for s in ps.FIT_STATUSES}
    usable = [r for r in records if r['full']['inference_usable']]
    usable_full = len(usable)
    usable_h2 = sum(r['full']['inference_usable'] and r['reduced']['inference_usable']
                    and r['h2'] is not None and r['h2']['valid'] for r in records)
    out = {'cell': cell, 'cell_key': cell_key(cell), 'stage': stage,
           'requested': n if requested is UNSET else requested,
           'completed': n, 'fit_status_full': status_counts,
           'fit_status_reduced': {s: sum(r['reduced']['status'] == s for r in records) for s in ps.FIT_STATUSES},
           'fit_flags_full': {flag: sum(bool(r['full'][flag]) for r in records) for flag in ps.FIT_FLAGS},
           'fit_flags_reduced': {flag: sum(bool(r['reduced'][flag]) for r in records) for flag in ps.FIT_FLAGS},
           'counts_full': fit_counts(records, 'full'), 'counts_reduced': fit_counts(records, 'reduced'),
           'singular_full': sum(bool(r['full']['singular']) for r in records if r['full']['status'] == 'ok'),
           'usable_rate_full': usable_full / n if n else None, 'usable_rate_h2': usable_h2 / n if n else None,
           'truth': dgp['truth'], 'tests': {}, 'boundary': {}}
    minimum = acceptance['usable_rate_min']
    out['usable_decision'] = 'PASS' if n and usable_full / n >= minimum and usable_h2 / n >= minimum else 'FAIL'
    added = {'RE2': ('P1', 'P2'), 'RE3': ('V1', 'V2')}.get(cell['structure'], ())
    for component in added:
        count = sum(r['full']['boundary'].get(component, False) for r in usable)
        true_sd = float(dgp['sds'][ps.RANDOM_NAMES.index(component)])
        out['boundary'][component] = {
            'count': count, 'usable': usable_full, 'true_sd': true_sd,
            'unstable': ps.boundary_instability(count, usable_full, true_sd, acceptance.get(
                'unstable_boundary_rate', 1.0))}
    for estimand in ps.ESTIMANDS:
        for contrast in ps.CONTRASTS:
            rows = [r['h1'][estimand][contrast] for r in usable if r['h1'] is not None
                    and r['h1'][estimand][contrast]['se'] is not None]
            role, true_value = test_role(cell, dgp, contrast, estimand), dgp['truth'][estimand][contrast]
            nominal = ps.wilson(sum(x['p'] < alpha for x in rows), len(rows), level)
            planning = ps.wilson(sum(x['p'] < thresholds['h1'] for x in rows), len(rows), level)
            coverage = ps.wilson(sum(x['lower'] <= true_value <= x['upper'] for x in rows), len(rows), level)
            test = {'role': role, 'truth': true_value, 'valid': len(rows), 'rejection_nominal': nominal,
                    'rejection_planning': planning, 'coverage': coverage}
            test['decisions'] = decisions(cell['grid'], role, nominal, planning, coverage, acceptance, config,
                                          stage)
            out['tests'][f'h1/{estimand}/{contrast}'] = test
    rows = [r['h2'] for r in records if r['full']['inference_usable'] and r['reduced']['inference_usable']
            and r['h2'] is not None and r['h2']['valid']]
    role = test_role(cell, dgp)
    nominal = ps.wilson(sum(x['p'] < alpha for x in rows), len(rows), level)
    planning = ps.wilson(sum(x['p'] < thresholds['h2'] for x in rows), len(rows), level)
    out['tests']['h2/lrt_chisq4'] = {'role': role, 'valid': len(rows), 'invalid_lrt': sum(
        r['h2'] is not None and not r['h2']['valid'] for r in records),
        'excluded_not_usable': sum(not (r['full']['inference_usable'] and r['reduced']['inference_usable'])
                                   for r in records), 'rejection_nominal': nominal,
        'rejection_planning': planning,
        'decisions': decisions(cell['grid'], role, nominal, planning, None, acceptance, config, stage)}
    return out


def fit_counts(records, part):
    """Every category kept separately; only `inference_usable` feeds the Monte Carlo denominators."""
    counts = {}
    for name in ps.FIT_COUNTS:
        if name in ps.FIT_STATUSES:
            counts[name] = sum(r[part]['status'] == name for r in records)
        else:
            counts[name] = sum(bool(r[part][name]) for r in records)
    counts['boundary'] = {component: sum(bool(r[part]['boundary'].get(component)) for r in records)
                          for component in (records[0][part]['boundary'] if records else {})}
    return counts


def decisions(grid, role, nominal, planning, coverage, acceptance, config, stage='screening'):
    out = {}
    if grid == 'primary':
        if role == 'null':
            out['type_i'] = stage_decision(ps.band_decision(nominal, acceptance['type_i_band']), stage, config)
        if role == 'alternative':
            out['power'] = ps.power_decision(planning, acceptance['power_lower_bound_min'])
            out['power_escalation'] = ps.needs_escalation(
                planning, acceptance['power_lower_bound_min'], planning['trials'],
                config['monte_carlo']['final_replications']['power_escalation'])
        if coverage is not None:
            out['coverage'] = stage_decision(ps.band_decision(coverage, acceptance['coverage_band']), stage,
                                             config)
    elif role == 'null' and nominal['trials']:
        out['type_i'] = 'PASS' if nominal['estimate'] <= acceptance['type_i_point_max'] else 'FAIL'
    return out


def aggregate(root, config, stage='screening'):
    summaries = []
    for cell_file in sorted(Path(root).glob('*/cell.json')):
        cell = json.loads(cell_file.read_text(encoding='utf-8'))
        directory = cell_file.parent
        cell_coverage = coverage(directory)
        summary = summarize_cell(cell, read_records(directory), config, stage=stage,
                                 requested=cell_coverage['requested'])
        summary['coverage'] = cell_coverage
        summaries.append(summary)
    return summaries


# --- H2-B parametric bootstrap scaffold ---------------------------------------------------------------------------

def parametric_bootstrap_h2(data, reduced_fit, observed, structure, fitter, config, key, draws):
    """Simulate from the fitted REDUCED model (same scenarios, R, structure), refit FULL and REDUCED, and calibrate
    the same LRT statistic. Scaffold only: production B is OPEN and not executed here."""
    beta = np.concatenate([np.asarray(reduced_fit['beta'], dtype=float), np.zeros(4)])
    covariance = ps.fitted_covariance(reduced_fit['components'])
    n, repetitions = len(set(data['scenario'])), data['n'][0]
    jobs = []
    for b in range(draws):
        rng = ps.rng_for(config['monte_carlo']['master_seed'], key, b, 'h2-bootstrap')
        jobs.append(job(str(b), ps.simulate_data(beta, covariance, n, repetitions, rng), structure))
    _, fits = fitter(jobs)
    statistics = []
    for b in range(draws):
        record = analyze_replicate(fits[str(b)], structure, config)
        statistics.append(record['h2']['statistic'] if record['h2'] and record['h2']['valid'] else None)
    return {**ps.bootstrap_p(observed, statistics), 'statistics': statistics, 'draws': draws}


# --- CLI -------------------------------------------------------------------------------------------------------------

def parse_range(text):
    start, _, stop = text.partition(':')
    return list(range(int(start), int(stop)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='List the cells of one design point (no fitting)')
    for p in (plan, run := sub.add_parser('run', help='Run replicates of selected cells')):
        p.add_argument('--n', type=int, required=True)
        p.add_argument('--r', type=int, required=True)
        p.add_argument('--structure', choices=ps.STRUCTURES, action='append')
    run.add_argument('--cell', type=int, action='append', help='Cell index from `plan`; default all')
    run.add_argument('--replicates', required=True, help='start:stop replicate range')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--workers', type=int, default=1)
    run.add_argument('--rscript')
    agg = sub.add_parser('aggregate', help='Summarize every cell under an output directory')
    agg.add_argument('--output', type=Path, required=True)
    agg.add_argument('--stage', choices=('screening', 'confirmation'), default='screening')
    args = parser.parse_args(argv)
    config = ps.load_config()
    if args.command == 'aggregate':
        print(json.dumps(aggregate(args.output, config, args.stage), indent=2, sort_keys=True))
        return 0
    cells, invalid = enumerate_cells(args.n, args.r, tuple(args.structure or ps.STRUCTURES), config=config)
    if args.command == 'plan':
        print(json.dumps({'cells': len(cells), 'invalid_dgps': invalid,
                          'families': {f: sum(c['family'] == f for c in cells)
                                       for f in ('primary', 'sensitivity', 'stress')},
                          'index': [{'index': i, 'key': cell_key(c)} for i, c in enumerate(cells)]}, indent=2))
        return 0
    fitter = RFitter(config, args.rscript)
    selected = [cells[i] for i in args.cell] if args.cell else cells
    for cell in selected:
        run_cell(cell, parse_range(args.replicates), fitter, args.output, config, args.workers)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
