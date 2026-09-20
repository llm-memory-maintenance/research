"""Pre-main power simulation machinery for the CRST Policy x Revision binomial-logit GLMM (offline only).

Everything that determines the statistics lives here and is tested without R: contrast coding, random-effect
profiles, probability-scale DGP calibration, deterministic seeds, grouped-binomial data, the two candidate
probability estimands, delta-method H1 inference, the H2 likelihood-ratio statistic, Monte Carlo intervals,
acceptance rules and the N x R selection rule. Only maximum-likelihood fitting is delegated to R lme4
(fit_glmm.R), through formulas built here so that coding is identical in simulation and fitting.
"""
from functools import lru_cache
import hashlib
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'configs/statistical-planning.yaml'

POLICIES = ('M1', 'M2', 'M3')
REVISIONS = ('low', 'medium', 'high')
ENDPOINTS = ('CSA', 'SRR')
STRUCTURES = ('RE1', 'RE2', 'RE3')
CONTRASTS = {'M2-M1': (1, 0), 'M3-M2': (2, 1)}
ESTIMANDS = {'A': 'conditional', 'B': 'population_averaged'}
TARGET_SCALES = ('conditional', 'population_averaged')
# FROZEN: ESTIMAND_B is the primary thesis estimand; ESTIMAND_A is an implementation diagnostic.
PRIMARY_ESTIMAND = 'B'
DIAGNOSTIC_ESTIMAND = 'A'
ANCHOR = 'policy_averaged_reference_probability'

# Orthonormal Helmert coding for a three-level factor. Columns are centered, orthogonal and unit-norm; every level
# has the same row norm (2/3), so equal per-column random-slope SDs imply the same random-effect variance at every
# level, and the implied level distribution is invariant to rotating the coding.
HELMERT = np.array([[-1 / math.sqrt(2), -1 / math.sqrt(6)],
                    [1 / math.sqrt(2), -1 / math.sqrt(6)],
                    [0.0, 2 / math.sqrt(6)]])
POLICY_CODING = HELMERT
REVISION_CODING = HELMERT
FIXED_NAMES = ('(Intercept)', 'P1', 'P2', 'V1', 'V2', 'P1:V1', 'P1:V2', 'P2:V1', 'P2:V2')
REDUCED_NAMES = FIXED_NAMES[:5]
INTERACTION_NAMES = FIXED_NAMES[5:]
RANDOM_NAMES = ('(Intercept)', 'P1', 'P2', 'V1', 'V2')
RE_COMPONENTS = {'RE1': ('(Intercept)',), 'RE2': ('(Intercept)', 'P1', 'P2'),
                 'RE3': ('(Intercept)', 'P1', 'P2', 'V1', 'V2')}
RE_TERMS = {'RE1': '(1 | scenario)', 'RE2': '(1 + P1 + P2 || scenario)',
            'RE3': '(1 + P1 + P2 + V1 + V2 || scenario)'}
FIXED_FULL = 'cbind(y, n - y) ~ P1 + P2 + V1 + V2 + P1:V1 + P1:V2 + P2:V1 + P2:V2'
FIXED_REDUCED = 'cbind(y, n - y) ~ P1 + P2 + V1 + V2'
NULL_TOL = 1e-9


def load_config(path=CONFIG_PATH):
    return yaml.safe_load(Path(path).read_text(encoding='utf-8'))


# --- Design --------------------------------------------------------------------------------------------------

def cells():
    """Canonical cell order: policy-major, then revision."""
    return [(p, r) for p in POLICIES for r in REVISIONS]


def design_matrix():
    """Full fixed-effect design (9 x 9) for the canonical cell order; columns FIXED_NAMES."""
    rows = []
    for p, r in cells():
        a, b = POLICY_CODING[POLICIES.index(p)], REVISION_CODING[REVISIONS.index(r)]
        rows.append([1.0, a[0], a[1], b[0], b[1], a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1]])
    return np.array(rows)


def random_design():
    """Scenario random-effect design (9 x 5) for the canonical cell order; columns RANDOM_NAMES."""
    return design_matrix()[:, :5]


def formulas(structure):
    """FULL and REDUCED formulas share one random-effects term; only the four interaction columns differ."""
    term = RE_TERMS[structure]
    return {'full': f'{FIXED_FULL} + {term}', 'reduced': f'{FIXED_REDUCED} + {term}'}


def n_candidates(n_max, config=None):
    config = config or load_config()
    start, step = config['design']['n_start'], config['design']['n_step']
    if start % 12 or step % 12:
        raise ValueError('N candidates must stay divisible by 12')
    return list(range(start, n_max + 1, step))


def check_design(n, r, config=None):
    config = config or load_config()
    if type(n) is not int or n < config['design']['n_start'] or n % 12:
        raise ValueError('N must be an integer multiple of 12 at or above the search floor')
    if r not in config['design']['r_candidates']:
        raise ValueError('R must be one of the candidate technical repetition counts')


# --- Random-effect profiles ------------------------------------------------------------------------------------

def profile(name, config=None):
    config = config or load_config()
    profiles = {**config['het_profiles'], **config['stress_profiles']}
    return profiles[name]


def re_covariance(spec):
    """5 x 5 logit-scale covariance over RANDOM_NAMES. A correlation applies only between nonzero components."""
    sds = np.array([spec['sigma_intercept'], spec['sigma_policy'], spec['sigma_policy'],
                    spec['sigma_revision'], spec['sigma_revision']], dtype=float)
    active = sds > 0
    corr = np.eye(5)
    corr[np.ix_(active, active)] = np.where(np.eye(active.sum(), dtype=bool), 1.0, spec.get('rho', 0.0))
    np.linalg.cholesky(corr)
    return corr * np.outer(sds, sds), corr, sds


def cell_variances(covariance):
    """Variance of the scenario random-effect linear predictor in each cell."""
    z = random_design()
    return np.einsum('ij,jk,ik->i', z, covariance, z)


# --- Probability scales --------------------------------------------------------------------------------------

def expit(x):
    return 0.5 * (1.0 + np.tanh(0.5 * np.asarray(x, dtype=float)))


def logit(p):
    p = np.asarray(p, dtype=float)
    return np.log(p) - np.log1p(-p)


@lru_cache(maxsize=None)
def gauss_hermite(nodes=64):
    x, w = np.polynomial.hermite.hermgauss(nodes)
    return math.sqrt(2.0) * x, w / math.sqrt(math.pi)


def cell_probability(eta, variance, scale, nodes=64):
    """conditional: expit(eta). population_averaged: E[expit(eta + u)], u ~ N(0, variance), by Gauss-Hermite."""
    eta = np.asarray(eta, dtype=float)
    if scale == 'conditional':
        return expit(eta)
    z, w = gauss_hermite(nodes)
    sd = np.sqrt(np.broadcast_to(np.asarray(variance, dtype=float), eta.shape))
    return expit(eta[..., None] + sd[..., None] * z) @ w


def cell_slope(eta, variance, scale, nodes=64):
    """d probability / d eta on the given scale."""
    eta = np.asarray(eta, dtype=float)
    if scale == 'conditional':
        p = expit(eta)
        return p * (1 - p)
    z, w = gauss_hermite(nodes)
    sd = np.sqrt(np.broadcast_to(np.asarray(variance, dtype=float), eta.shape))
    p = expit(eta[..., None] + sd[..., None] * z)
    return (p * (1 - p)) @ w


def invert_probability(target, variance, scale, nodes=64):
    """Linear predictor whose cell probability on `scale` equals `target` (monotone; bisection)."""
    target = np.asarray(target, dtype=float)
    if np.any((target <= 0) | (target >= 1)):
        raise ValueError('Target probabilities must lie strictly inside (0, 1)')
    if scale == 'conditional':
        return logit(target)
    lo, hi = np.full(target.shape, -60.0), np.full(target.shape, 60.0)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        above = cell_probability(mid, variance, scale, nodes) > target
        hi, lo = np.where(above, mid, hi), np.where(above, lo, mid)
    return 0.5 * (lo + hi)


# --- Scenarios and DGP calibration ---------------------------------------------------------------------------

def scenarios(config=None):
    """Scenario library. `additive`: reduced (no-interaction) logit model. `cell`: every cell probability targeted.

    The primary H1 alternative is additive: the fixed interaction is exactly zero and the equal-weighted contrast on
    the target scale is exactly the MOI. The cell construction, which forces the MOI at every revision level and
    therefore implies a logit interaction, is retained only as a labelled secondary sensitivity DGP.
    """
    config = config or load_config()
    moi, zero = config['alternatives']['moi'], (0.0, 0.0, 0.0)
    # The all-zero scenario is an H1 null and an H2 null, so it is built from the reduced model (exact zero
    # interaction) rather than by cell calibration.
    out = {'NULL:zero': {'kind': 'additive', 'avg21': 0.0, 'avg32': 0.0, 'h1_target': None,
                         'h2_alternative': False, 'family': 'primary'}}
    for contrast in CONTRASTS:
        for sign in config['alternatives']['h1_signs']:
            value = sign * moi
            out[f'H1:{contrast}:{value:+.2f}'] = {
                'kind': 'additive', 'avg21': value if contrast == 'M2-M1' else 0.0,
                'avg32': value if contrast == 'M3-M2' else 0.0, 'h1_target': contrast, 'h2_alternative': False,
                'family': 'primary'}
            d = (value,) * 3
            out[f'H1SENS:{contrast}:{value:+.2f}'] = {
                'kind': 'cell', 'd21': d if contrast == 'M2-M1' else zero, 'd32': d if contrast == 'M3-M2' else zero,
                'h1_target': contrast, 'h2_alternative': False, 'family': 'sensitivity'}
    for contrast in CONTRASTS:
        for shape, values in config['alternatives']['h2_shapes'].items():
            for mirror in ((1, -1) if config['alternatives']['h2_mirrored'] else (1,)):
                d = tuple(mirror * v for v in values)
                out[f'H2:{contrast}:{shape}:{"mirrored" if mirror < 0 else "primary"}'] = {
                    'kind': 'cell', 'd21': d if contrast == 'M2-M1' else zero,
                    'd32': d if contrast == 'M3-M2' else zero, 'h1_target': None, 'h2_alternative': True,
                    'family': 'primary'}
    # The single-contrast constant-difference H2 nulls are exactly the primary H1 alternatives above, which carry
    # zero fixed interaction; only the two-contrast cases are additional.
    out['H2NULL:both:+0.05:+0.05'] = {'kind': 'additive', 'avg21': moi, 'avg32': moi, 'h1_target': None,
                                      'h2_alternative': False, 'family': 'primary'}
    out['H2NULL:both:+0.05:-0.05'] = {'kind': 'additive', 'avg21': moi, 'avg32': -moi, 'h1_target': None,
                                      'h2_alternative': False, 'family': 'primary'}
    return out


def revision_levels(endpoint, reference, revision_profile, config=None):
    config = config or load_config()
    offsets = config['baseline']['revision_profiles'][revision_profile][endpoint]
    return np.array([reference + o for o in offsets])


def cell_targets(levels, d21, d32, anchor):
    """3 x 3 [policy, revision] probability targets; fails loudly outside (0, 1), never clips."""
    d21, d32 = np.asarray(d21, dtype=float), np.asarray(d32, dtype=float)
    if anchor != ANCHOR:
        raise ValueError('The reference probability is the equal-weighted policy mean, never an M1 baseline')
    m1 = levels - (2 * d21 + d32) / 3
    targets = np.vstack([m1, m1 + d21, m1 + d21 + d32])
    if np.any((targets <= 0) | (targets >= 1)):
        raise ValueError(f'Cell probability outside (0, 1): {np.round(targets, 6).tolist()}')
    return targets


def calibrate_cells(targets, variances, scale, nodes=64):
    """Saturated calibration: invert each cell target on `scale`, then solve the 9 x 9 design exactly."""
    eta = invert_probability(np.asarray(targets).reshape(-1), variances, scale, nodes)
    return np.linalg.solve(design_matrix(), eta)


def _anchor_rows(anchor):
    if anchor != ANCHOR:
        raise ValueError('The reference probability is the equal-weighted policy mean, never an M1 baseline')
    rows = []
    for j in range(3):
        row = np.zeros(9)
        for i in range(3):
            row[3 * i + j] = 1 / 3
        rows.append(row)
    for high, low in CONTRASTS.values():
        row = np.zeros(9)
        row[3 * high:3 * high + 3] += 1 / 3
        row[3 * low:3 * low + 3] -= 1 / 3
        rows.append(row)
    return np.array(rows)


def calibrate_additive(levels, avg21, avg32, variances, scale, anchor, nodes=64, tol=1e-12):
    """Reduced-model calibration: the 4 interaction coefficients are exactly zero; the 5 main-effect coefficients
    solve anchor-level targets per revision and the equal-weighted policy contrasts on `scale` (Newton)."""
    if np.any((np.asarray(levels) <= 0) | (np.asarray(levels) >= 1)):
        raise ValueError('Revision reference levels must lie strictly inside (0, 1)')
    x5, a = design_matrix()[:, :5], _anchor_rows(anchor)
    goal = np.concatenate([levels, [avg21, avg32]])
    beta = np.array([float(logit(np.mean(levels))), 0.0, 0.0, 0.0, 0.0])

    def residual(b):
        return a @ cell_probability(x5 @ b, variances, scale, nodes) - goal
    f = residual(beta)
    for _ in range(200):
        if np.max(np.abs(f)) < tol:
            break
        jac = a @ (cell_slope(x5 @ beta, variances, scale, nodes)[:, None] * x5)
        step, t = np.linalg.solve(jac, f), 1.0
        while t > 1e-8:
            trial = beta - t * step
            if np.all(np.isfinite(trial)) and np.max(np.abs(residual(trial))) < np.max(np.abs(f)):
                break
            t /= 2
        beta, f = beta - t * step, residual(beta - t * step)
    if np.max(np.abs(f)) >= tol or np.max(np.abs(beta)) > 30:
        raise ValueError('Additive calibration has no valid solution inside (0, 1)')
    return np.concatenate([beta, np.zeros(4)])


def build_dgp(endpoint, reference, revision_profile, het, scenario, target_scale, anchor=None, config=None):
    """True fixed effects and random-effect covariance for one DGP condition; truth recorded for both estimands."""
    config = config or load_config()
    anchor = anchor or config['calibration']['anchor']
    nodes = config['calibration']['gauss_hermite_nodes']
    spec = scenarios(config)[scenario]
    covariance, _, sds = re_covariance(profile(het, config))
    variances = cell_variances(covariance)
    levels = revision_levels(endpoint, reference, revision_profile, config)
    if spec['kind'] == 'cell':
        targets = cell_targets(levels, spec['d21'], spec['d32'], anchor)
        beta = calibrate_cells(targets, variances, target_scale, nodes)
    else:
        targets = None
        beta = calibrate_additive(levels, spec['avg21'], spec['avg32'], variances, target_scale, anchor, nodes)
    probabilities = {s: cell_probability(design_matrix() @ beta, variances, s, nodes).reshape(3, 3)
                     for s in TARGET_SCALES}
    achieved = truth(beta, covariance, nodes)
    estimand = next(e for e, scale in ESTIMANDS.items() if scale == target_scale)
    if targets is not None:
        error = float(np.max(np.abs(probabilities[target_scale] - targets)))
    else:
        error = max(abs(achieved[estimand]['M2-M1'] - spec['avg21']),
                    abs(achieved[estimand]['M3-M2'] - spec['avg32']))
    if error > config['calibration']['tolerance']:
        raise ValueError(f'Calibration error {error} exceeds tolerance')
    return {'beta': beta, 'covariance': covariance, 'sds': sds, 'variances': variances, 'targets': targets,
            'probabilities': probabilities, 'target_scale': target_scale, 'anchor': anchor,
            'scenario': scenario, 'spec': spec, 'truth': achieved, 'calibration_error': error}


def truth(beta, covariance, nodes=64):
    """True estimand values under both definitions and whether the fixed-effect interaction is exactly absent."""
    out = {name: contrasts_on_scale(beta, covariance, scale, nodes) for name, scale in ESTIMANDS.items()}
    out['interaction_absent'] = bool(np.all(np.abs(np.asarray(beta)[5:]) < 1e-10))
    return out


def contrasts_on_scale(beta, covariance, scale, nodes=64):
    p = cell_probability(design_matrix() @ np.asarray(beta, dtype=float), cell_variances(covariance), scale,
                         nodes).reshape(3, 3)
    return {name: float(np.mean(p[high] - p[low])) for name, (high, low) in CONTRASTS.items()}


# --- Seeds and data --------------------------------------------------------------------------------------------

def cell_id(fields):
    """Canonical, order-independent identity string: sorted key=value pairs."""
    return '|'.join(f'{k}={fields[k]}' for k in sorted(fields))


def derive_seed(master_seed, dgp_cell_id, replicate, stream='data'):
    """SHA-256 of the canonical inputs, first 8 bytes big-endian. Never Python hash(), order or wall-clock."""
    text = f'{master_seed}\x1f{dgp_cell_id}\x1f{replicate}\x1f{stream}'.encode('utf-8')
    return int.from_bytes(hashlib.sha256(text).digest()[:8], 'big')


def rng_for(master_seed, dgp_cell_id, replicate, stream='data'):
    return np.random.Generator(np.random.PCG64(derive_seed(master_seed, dgp_cell_id, replicate, stream)))


def simulate_data(beta, covariance, n_scenarios, repetitions, rng):
    """Grouped-binomial rows (scenario-major, canonical cell order). Draw order is fixed: all random effects, then
    all binomial counts, so the stream never depends on which components are active."""
    sds = np.sqrt(np.diag(covariance))
    corr = np.where(np.outer(sds, sds) > 0, covariance / np.where(np.outer(sds, sds) > 0, np.outer(sds, sds), 1), 0)
    np.fill_diagonal(corr, 1.0)
    effects = (rng.standard_normal((n_scenarios, 5)) @ np.linalg.cholesky(corr).T) * sds
    x, z = design_matrix(), random_design()
    eta = (x @ np.asarray(beta))[None, :] + effects @ z.T
    y = rng.binomial(repetitions, expit(eta))
    rows = n_scenarios * 9
    return {'scenario': np.repeat(np.arange(1, n_scenarios + 1), 9).tolist(),
            'policy': [p for _ in range(n_scenarios) for p, _ in cells()],
            'revision': [r for _ in range(n_scenarios) for _, r in cells()],
            **{name: np.tile(x[:, k], n_scenarios).tolist() for k, name in enumerate(('P1', 'P2', 'V1', 'V2'), 1)},
            'y': y.reshape(rows).astype(int).tolist(), 'n': [int(repetitions)] * rows}


# --- Estimands and inference -------------------------------------------------------------------------------------

def fitted_covariance(components):
    """Diagonal 5 x 5 covariance from fitted component SDs {name: sd}; absent components are zero."""
    cov = np.zeros((5, 5))
    for name, sd in components.items():
        cov[RANDOM_NAMES.index(name), RANDOM_NAMES.index(name)] = sd ** 2
    return cov


def h1_inference(beta, vcov, covariance, estimand, level=0.95, nodes=64):
    """Equal-weighted absolute probability contrasts with delta-method SE, two-sided z test and Wald CI.

    ESTIMAND_A treats the random effect as zero. ESTIMAND_B integrates over the fitted random-effect distribution;
    its delta method conditions on the fitted variance components (their uncertainty is not propagated).
    """
    scale = ESTIMANDS[estimand]
    x, beta, vcov = design_matrix(), np.asarray(beta, dtype=float), np.asarray(vcov, dtype=float)
    variances = cell_variances(covariance)
    eta = x @ beta
    p = cell_probability(eta, variances, scale, nodes)
    grad_cells = cell_slope(eta, variances, scale, nodes)[:, None] * x
    z = NormalDist().inv_cdf(0.5 + level / 2)
    out = {}
    for name, (high, low) in CONTRASTS.items():
        weights = np.zeros(9)
        weights[3 * high:3 * high + 3], weights[3 * low:3 * low + 3] = 1 / 3, -1 / 3
        estimate, gradient = float(weights @ p), weights @ grad_cells
        variance = float(gradient @ vcov @ gradient)
        if not math.isfinite(variance) or variance <= 0:
            out[name] = {'estimate': estimate, 'se': None, 'lower': None, 'upper': None, 'p': None}
            continue
        se = math.sqrt(variance)
        out[name] = {'estimate': estimate, 'se': se, 'lower': estimate - z * se, 'upper': estimate + z * se,
                     'p': math.erfc(abs(estimate / se) / math.sqrt(2))}
    return out


def simple_contrasts(beta, vcov, covariance, estimand, nodes=64):
    """Six descriptive per-revision contrasts (2 policy contrasts x 3 revisions) with Holm-adjusted p-values."""
    scale = ESTIMANDS[estimand]
    x, beta, vcov = design_matrix(), np.asarray(beta, dtype=float), np.asarray(vcov, dtype=float)
    variances = cell_variances(covariance)
    eta = x @ beta
    p, grad = cell_probability(eta, variances, scale, nodes), cell_slope(eta, variances, scale, nodes)[:, None] * x
    rows = []
    for name, (high, low) in CONTRASTS.items():
        for j, revision in enumerate(REVISIONS):
            estimate = float(p[3 * high + j] - p[3 * low + j])
            g = grad[3 * high + j] - grad[3 * low + j]
            se = math.sqrt(float(g @ vcov @ g))
            rows.append({'contrast': name, 'revision': revision, 'estimate': estimate, 'se': se,
                         'p': math.erfc(abs(estimate / se) / math.sqrt(2))})
    for row, adjusted in zip(rows, holm([r['p'] for r in rows])):
        row['p_holm'] = adjusted
    return rows


def holm(pvalues):
    """Holm step-down adjusted p-values in the input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, running, m = [0.0] * len(pvalues), 0.0, len(pvalues)
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def chi2_sf_df4(d):
    """Exact chi-square survival function for 4 df: exp(-d/2)(1 + d/2)."""
    return math.exp(-d / 2) * (1 + d / 2)


def h2_lrt(loglik_full, loglik_reduced, df=4, negative_tolerance=1e-4):
    """D = 2 (logLik_full - logLik_reduced) with the asymptotic chi-square(4) p-value (H2-A candidate)."""
    if df != 4:
        raise ValueError('The Policy x Revision interaction has exactly 4 fixed-effect df')
    d = 2.0 * (loglik_full - loglik_reduced)
    if not math.isfinite(d) or d < -negative_tolerance:
        return {'statistic': d, 'df': 4, 'p': None, 'valid': False}
    return {'statistic': d, 'df': 4, 'p': chi2_sf_df4(max(d, 0.0)), 'valid': True}


def bootstrap_p(observed, simulated):
    """Parametric-bootstrap p-value (1 + #{D* >= D}) / (1 + B_valid) for the same LRT statistic (H2-B)."""
    valid = [d for d in simulated if d is not None and math.isfinite(d)]
    return {'p': (1 + sum(d >= observed for d in valid)) / (1 + len(valid)), 'valid': len(valid),
            'failed': len(simulated) - len(valid)}


# --- Fit status ------------------------------------------------------------------------------------------------

FIT_STATUSES = ('ok', 'convergence_failure', 'invalid_inference', 'numerical_failure')
FIT_FLAGS = ('convergence_warning', 'vcov_warning', 'singular')
# Counts every report keeps separately; `inference_usable` is the only denominator for Monte Carlo metrics.
FIT_COUNTS = ('fit_returned', 'inference_usable', 'convergence_warning', 'vcov_warning', 'singular',
              'convergence_failure', 'invalid_inference', 'numerical_failure')
MAX_MESSAGES = 3
MESSAGE_CHARS = 200


def concise(messages):
    """A few truncated raw lme4 messages, kept for audit; never used to decide status."""
    if isinstance(messages, (str, int, float)):
        messages = [messages]
    return [str(m)[:MESSAGE_CHARS] for m in (messages or [])[:MAX_MESSAGES]]


def classify_fit(fit, structure, names, singular_tol=1e-4):
    """Status of the fit itself, with independent flags.

    `fit_returned` says the backend returned a fitted model object. `status` says whether that fit yielded usable
    estimates: 'ok', 'convergence_failure' (the optimizer itself did not report success), 'invalid_inference'
    (estimates or vcov unusable) and 'numerical_failure' (no fit at all). A convergence warning, a vcov warning and
    a singular/boundary fit are separate flags: a fit may be returned successfully, carry a warning and be
    singular, all at once. Nothing is retried automatically.

    `inference_usable` is status 'ok' with no convergence warning and no vcov warning, all inferential quantities
    finite and valid. It is the only denominator for Monte Carlo rejection, coverage and power. Singularity is
    deliberately excluded: it is governed by the separate pre-specified boundary criterion.
    """
    record = {'fit_returned': False, 'inference_usable': False, 'status': None, 'convergence_warning': None,
              'vcov_warning': None, 'singular': None, 'boundary': {}, 'components': {}, 'messages': []}
    if fit is None or fit.get('status') != 'fitted':
        record['status'] = 'numerical_failure'
        record['messages'] = concise([fit.get('error')] if fit and fit.get('error') else
                                     (fit or {}).get('warnings'))
        return record
    record['fit_returned'] = True
    record['components'] = dict(zip(fit['re_components'], fit['re_sd']))
    record['boundary'] = {c: record['components'].get(c, 0.0) < singular_tol for c in RE_COMPONENTS[structure]}
    record['singular'] = bool(fit['singular'])
    record['convergence_warning'] = bool(fit['convergence_warnings'])
    record['vcov_warning'] = bool(fit.get('vcov_warnings'))
    record['messages'] = concise(list(fit['convergence_warnings'] or []) + list(fit.get('vcov_warnings') or []))
    if fit['optimizer_code'] is None or fit['optimizer_code'] != 0:
        record['status'] = 'convergence_failure'
        return record
    beta = [fit['beta'].get(n) for n in names]
    vcov = fit.get('vcov')
    if (vcov is None or any(v is None or not math.isfinite(v) for v in beta) or fit['vcov_names'] != list(names)
            or not math.isfinite(fit['loglik'])):
        record['status'] = 'invalid_inference'
        return record
    matrix = np.asarray(vcov, dtype=float)
    if not np.all(np.isfinite(matrix)) or not np.allclose(matrix, matrix.T) or np.min(np.linalg.eigvalsh(matrix)) <= 0:
        record['status'] = 'invalid_inference'
        return record
    record.update(status='ok', beta=beta, vcov=matrix.tolist(), loglik=fit['loglik'],
                  inference_usable=not (record['convergence_warning'] or record['vcov_warning']))
    return record


# --- Monte Carlo uncertainty and acceptance ---------------------------------------------------------------------

def wilson(successes, trials, level=0.90):
    """Wilson score interval for a binomial rate (the single Monte Carlo interval method)."""
    if trials == 0:
        return {'estimate': None, 'lower': 0.0, 'upper': 1.0, 'successes': 0, 'trials': 0}
    z = NormalDist().inv_cdf(0.5 + level / 2)
    p, n = successes / trials, trials
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {'estimate': p, 'lower': max(0.0, centre - half), 'upper': min(1.0, centre + half),
            'successes': successes, 'trials': trials}


def band_decision(interval, band):
    """PASS when the MC interval lies wholly inside the band, FAIL when wholly outside, else INCONCLUSIVE."""
    if interval['trials'] == 0:
        return 'INCONCLUSIVE'
    if interval['lower'] >= band[0] and interval['upper'] <= band[1]:
        return 'PASS'
    if interval['upper'] < band[0] or interval['lower'] > band[1]:
        return 'FAIL'
    return 'INCONCLUSIVE'


def power_decision(interval, minimum=0.80):
    if interval['trials'] and interval['lower'] >= minimum:
        return 'PASS'
    if interval['trials'] and interval['upper'] < minimum:
        return 'FAIL'
    return 'INCONCLUSIVE'


def needs_escalation(interval, minimum, requested, escalation):
    """Final power cell whose MC interval still crosses the threshold is rerun at the escalation count."""
    return interval['lower'] < minimum <= interval['upper'] and requested < escalation


def boundary_instability(boundary_count, usable, true_sd, threshold=0.20):
    """Flag a richer structure only when the true added slope variance is nonzero."""
    if true_sd <= 0 or usable == 0:
        return False
    return boundary_count / usable > threshold


def select_design(feasible):
    """feasible: {(N, R): bool}. Smallest feasible N per R, then minimize N*R; ties prefer larger N, smaller R."""
    per_r = {}
    for (n, r), ok in sorted(feasible.items()):
        if ok and r not in per_r:
            per_r[r] = n
    if not per_r:
        return None
    n, r = min(((n, r) for r, n in per_r.items()), key=lambda d: (d[0] * d[1], -d[0], d[1]))
    return {'N': n, 'R': r, 'burden': n * r, 'smallest_feasible_n_per_r': per_r}
