"""Offline tests of the CRST power simulation machinery. Tiny data only; lme4 fits run only when R is present."""
import json
import math
from pathlib import Path
import shutil
import socket
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments'))
import power_simulation as ps  # noqa: E402
import simulate_power as sim  # noqa: E402

CONFIG = ps.load_config()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Network forbidden')
    for method in ('connect', 'connect_ex'):
        monkeypatch.setattr(socket.socket, method, blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)


def dgp(scenario='NULL:zero', het='HET2', scale='population_averaged', endpoint='CSA', reference=0.75,
        profile='MODERATE', anchor=None):
    return ps.build_dgp(endpoint, reference, profile, het, scenario, scale, anchor, CONFIG)


# --- 1-5 design ----------------------------------------------------------------------------------------------------

def test_policy_and_revision_contrasts_are_explicit_centered_orthonormal_and_full_rank():
    for coding in (ps.POLICY_CODING, ps.REVISION_CODING):
        assert coding.shape == (3, 2)
        assert np.allclose(coding.sum(axis=0), 0)
        assert np.allclose(coding.T @ coding, np.eye(2))
        assert np.allclose((coding ** 2).sum(axis=1), 2 / 3)
        assert np.linalg.matrix_rank(np.column_stack([np.ones(3), coding])) == 3
    expected = np.array([[-1 / math.sqrt(2), -1 / math.sqrt(6)], [1 / math.sqrt(2), -1 / math.sqrt(6)],
                         [0, 2 / math.sqrt(6)]])
    assert np.array_equal(ps.POLICY_CODING, expected) and np.array_equal(ps.REVISION_CODING, expected)


def test_full_design_is_centered_full_rank_and_deterministically_ordered():
    x = ps.design_matrix()
    assert x.shape == (9, 9) and np.linalg.matrix_rank(x) == 9
    assert np.allclose(x[:, 1:].sum(axis=0), 0)
    assert ps.cells() == [(p, r) for p in ('M1', 'M2', 'M3') for r in ('low', 'medium', 'high')]
    assert ps.FIXED_NAMES == ('(Intercept)', 'P1', 'P2', 'V1', 'V2', 'P1:V1', 'P1:V2', 'P2:V1', 'P2:V2')
    assert np.array_equal(x, ps.design_matrix())
    assert np.allclose(x[:, 5], x[:, 1] * x[:, 3]) and np.allclose(x[:, 8], x[:, 2] * x[:, 4])


def test_simulation_and_fitting_share_the_same_coding(tmp_path):
    data = ps.simulate_data(np.zeros(9), np.zeros((5, 5)), 2, 1, np.random.default_rng(0))
    x = ps.design_matrix()
    assert np.allclose(np.array([data[c] for c in ('P1', 'P2', 'V1', 'V2')]).T, np.tile(x[:, 1:5], (2, 1)))
    for structure in ps.STRUCTURES:
        f = ps.formulas(structure)
        for column in ps.RE_COMPONENTS[structure][1:]:
            assert column in f['full'].split('+ (')[1]
        assert 'policy' not in f['full'] and 'revision' not in f['full']


def test_n_divisible_by_12_from_the_floor_and_r_limited():
    assert ps.n_candidates(168, CONFIG) == [120, 132, 144, 156, 168]
    ps.check_design(132, 2, CONFIG)
    for n, r in ((126, 1), (108, 1), (120.0, 1), (120, 4), (120, 0)):
        with pytest.raises(ValueError):
            ps.check_design(n, r, CONFIG)


# --- 6 seeds -------------------------------------------------------------------------------------------------------

def test_seed_derivation_is_stable_and_order_independent():
    fields = sim.dgp_fields('P0', 'CSA', 0.75, 'FLAT', 'HET1', 'NULL:zero', 'conditional', ps.ANCHOR, 120, 2)
    reordered = dict(reversed(list(fields.items())))
    assert ps.cell_id(fields) == ps.cell_id(reordered)
    seed = ps.derive_seed(20260920, ps.cell_id(fields), 7)
    assert seed == ps.derive_seed(20260920, ps.cell_id(reordered), 7)
    assert 0 <= seed < 2 ** 64
    assert len({ps.derive_seed(20260920, ps.cell_id(fields), r) for r in range(100)}) == 100
    assert ps.derive_seed(20260920, 'a', 1) != ps.derive_seed(20260921, 'a', 1)
    assert ps.derive_seed(20260920, 'a', 1) == int.from_bytes(
        __import__('hashlib').sha256(b'20260920\x1fa\x1f1\x1fdata').digest()[:8], 'big')


# --- 7-8 data and validity --------------------------------------------------------------------------------------

def test_grouped_binomial_data_shape():
    d = dgp(het='STRESS')
    data = ps.simulate_data(d['beta'], d['covariance'], 12, 3, ps.rng_for(1, 'x', 0))
    assert all(len(v) == 108 for v in data.values())
    assert data['scenario'][:9] == [1] * 9 and data['scenario'][-1] == 12
    assert set(data['n']) == {3} and all(0 <= y <= 3 for y in data['y'])
    assert data['policy'][:9] == [p for p, _ in ps.cells()]


def test_same_seed_same_data_regardless_of_random_effect_profile_structure():
    a = ps.simulate_data(np.zeros(9), np.zeros((5, 5)), 5, 2, ps.rng_for(1, 'x', 0))
    b = ps.simulate_data(np.zeros(9), np.zeros((5, 5)), 5, 2, ps.rng_for(1, 'x', 0))
    assert a == b


def test_probabilities_outside_the_unit_interval_fail_loudly():
    with pytest.raises(ValueError, match='outside'):
        ps.cell_targets(np.array([0.02, 0.05, 0.10]), (-0.15,) * 3, (0,) * 3, ps.ANCHOR)
    with pytest.raises(ValueError):
        ps.invert_probability(np.array([1.0]), 0.5, 'population_averaged')


def test_fractional_grid_is_p0_to_p5_plus_a_separate_stress_point():
    cells, invalid = sim.enumerate_cells(120, 1, ('RE1',), config=CONFIG)
    assert invalid == []
    library = ps.scenarios(CONFIG)
    assert len(cells) == 7 * 2 * len(library)
    points = {c['dgp']['point'] for c in cells}
    assert points == {'P0', 'P1', 'P2', 'P3', 'P4', 'P5', 'S0'}
    primary = {c['dgp']['point'] for c in cells if c['grid'] == 'primary'}
    assert primary == {'P0', 'P1', 'P2', 'P3', 'P4', 'P5'}
    assert {c['dgp']['het'] for c in cells if c['grid'] == 'stress'} == {'STRESS'}
    assert {c['family'] for c in cells} == {'primary', 'sensitivity', 'stress'}
    assert all(c['family'] != 'primary' or c['grid'] == 'primary' for c in cells)
    settings = {(c['dgp']['point'], c['dgp']['endpoint'], c['dgp']['reference'], c['dgp']['revision_profile'],
                 c['dgp']['het']) for c in cells}
    assert ('P0', 'CSA', '0.75', 'MODERATE', 'HET2') in settings
    assert ('P1', 'SRR', '0.10', 'MODERATE', 'HET2') in settings
    assert ('P2', 'CSA', '0.85', 'MODERATE', 'HET2') in settings
    assert ('P3', 'SRR', '0.18', 'FLAT', 'HET2') in settings
    assert ('P4', 'CSA', '0.75', 'MODERATE', 'HET1') in settings
    assert ('P5', 'SRR', '0.18', 'MODERATE', 'HET3') in settings
    assert len(settings) == 14
    assert {c['dgp']['target_scale'] for c in cells} == {'population_averaged'}
    for cell in cells[:: max(1, len(cells) // 40)]:
        d = sim.dgp_of(cell['dgp'], CONFIG)
        for p in d['probabilities'].values():
            assert np.all((p > 0) & (p < 1))


# --- 9-13 calibration --------------------------------------------------------------------------------------------

@pytest.mark.parametrize('het', ['HET1', 'HET2', 'HET3', 'STRESS'])
@pytest.mark.parametrize('scale', ps.TARGET_SCALES)
def test_cell_targets_are_recovered_within_0_001(het, scale):
    for scenario in ('H1SENS:M3-M2:-0.05', 'H1SENS:M2-M1:+0.05', 'H2:M3-M2:HIGH_STEP:mirrored'):
        d = dgp(scenario, het, scale, 'SRR', 0.10)
        assert np.max(np.abs(d['probabilities'][scale] - d['targets'])) <= 0.001
        assert np.max(np.abs(d['probabilities'][scale] - d['targets'])) < 1e-9


def test_population_averaged_integration_is_accurate():
    eta, variance = np.array([-2.0, 0.3, 1.7]), np.array([0.25, 1.0, 2.0])
    grid = np.linspace(-12, 12, 200001)
    density = np.exp(-grid ** 2 / 2) / math.sqrt(2 * math.pi)
    reference = [np.trapezoid(ps.expit(e + math.sqrt(v) * grid) * density, grid) for e, v in zip(eta, variance)]
    assert np.allclose(ps.cell_probability(eta, variance, 'population_averaged'), reference, atol=1e-10)


@pytest.mark.parametrize('contrast', list(ps.CONTRASTS))
@pytest.mark.parametrize('sign', ['+0.05', '-0.05'])
@pytest.mark.parametrize('het', ['HET1', 'HET2', 'HET3', 'STRESS'])
@pytest.mark.parametrize('point', ['P0', 'P1', 'P2', 'P3'])
def test_primary_h1_dgp_has_zero_interaction_and_an_exact_equal_weighted_estimand_b_contrast(
        contrast, sign, het, point):
    spec = CONFIG['nuisance_grid'][point]
    d = ps.build_dgp('SRR', spec['references']['SRR'], spec['revision_profile'], het, f'H1:{contrast}:{sign}',
                     'population_averaged', config=CONFIG)
    other = 'M3-M2' if contrast == 'M2-M1' else 'M2-M1'
    assert np.all(d['beta'][5:] == 0) and d['truth']['interaction_absent']
    assert abs(d['truth']['B'][contrast] - float(sign)) <= 0.001
    assert abs(d['truth']['B'][contrast] - float(sign)) < 1e-9
    assert abs(d['truth']['B'][other]) < 1e-9
    assert d['calibration_error'] <= CONFIG['calibration']['tolerance']
    assert ps.scenarios(CONFIG)[f'H1:{contrast}:{sign}']['family'] == 'primary'
    high, low = ps.CONTRASTS[contrast]
    per_revision = d['probabilities']['population_averaged'][high] - d['probabilities']['population_averaged'][low]
    assert abs(per_revision.mean() - float(sign)) < 1e-9
    if spec['revision_profile'] == 'FLAT' and het != 'STRESS':
        # Equal baselines and a cell-independent random-effect variance make the per-revision differences identical.
        assert np.ptp(per_revision) < 1e-9


@pytest.mark.parametrize('contrast', list(ps.CONTRASTS))
@pytest.mark.parametrize('sign', ['+0.05', '-0.05'])
@pytest.mark.parametrize('scale', ps.TARGET_SCALES)
def test_sensitivity_h1_dgp_keeps_the_constant_per_revision_construction(contrast, sign, scale):
    d = dgp(f'H1SENS:{contrast}:{sign}', 'HET3', scale)
    estimand = 'A' if scale == 'conditional' else 'B'
    other = 'M3-M2' if contrast == 'M2-M1' else 'M2-M1'
    assert abs(d['truth'][estimand][contrast] - float(sign)) < 1e-9
    assert abs(d['truth'][estimand][other]) < 1e-9
    high, low = ps.CONTRASTS[contrast]
    assert np.allclose(d['probabilities'][scale][high] - d['probabilities'][scale][low], float(sign), atol=1e-9)
    assert ps.scenarios(CONFIG)[f'H1SENS:{contrast}:{sign}']['family'] == 'sensitivity'


@pytest.mark.parametrize('shape', ['LINEAR', 'HIGH_STEP', 'MIDDLE_PEAK'])
@pytest.mark.parametrize('contrast', list(ps.CONTRASTS))
def test_h2_shapes_have_a_5pp_range_zero_mean_and_mirrors(shape, contrast):
    high, low = ps.CONTRASTS[contrast]
    primary = dgp(f'H2:{contrast}:{shape}:primary')
    mirrored = dgp(f'H2:{contrast}:{shape}:mirrored')
    p, m = primary['probabilities']['population_averaged'], mirrored['probabilities']['population_averaged']
    difference, reflected = p[high] - p[low], m[high] - m[low]
    assert abs(np.ptp(difference) - 0.05) < 1e-9 and abs(difference.mean()) < 1e-9
    assert np.allclose(reflected, -difference, atol=1e-9)
    assert np.allclose(difference, CONFIG['alternatives']['h2_shapes'][shape], atol=1e-9)
    assert not primary['truth']['interaction_absent']
    other = 'M3-M2' if contrast == 'M2-M1' else 'M2-M1'
    oh, ol = ps.CONTRASTS[other]
    assert np.allclose(p[oh] - p[ol], 0, atol=1e-9)


@pytest.mark.parametrize('scenario', ['NULL:zero', 'H1:M2-M1:+0.05', 'H1:M2-M1:-0.05', 'H1:M3-M2:+0.05',
                                      'H2NULL:both:+0.05:+0.05', 'H2NULL:both:+0.05:-0.05'])
@pytest.mark.parametrize('het', ['HET1', 'HET3', 'STRESS'])
@pytest.mark.parametrize('scale', ps.TARGET_SCALES)
def test_h2_nulls_have_exactly_no_fixed_interaction_and_hit_their_marginal_targets(scenario, het, scale):
    d = dgp(scenario, het, scale, 'SRR', 0.10)
    assert np.all(d['beta'][5:] == 0) and d['truth']['interaction_absent']
    spec = d['spec']
    estimand = 'A' if scale == 'conditional' else 'B'
    if spec['kind'] == 'additive':
        assert abs(d['truth'][estimand]['M2-M1'] - spec['avg21']) < 1e-9
        assert abs(d['truth'][estimand]['M3-M2'] - spec['avg32']) < 1e-9
        levels = ps.revision_levels('SRR', 0.10, 'MODERATE', CONFIG)
        assert np.allclose(d['probabilities'][scale].mean(axis=0), levels, atol=1e-9)


def test_only_the_sensitivity_construction_carries_a_logit_interaction():
    """'Constant 5 pp at every revision' with unequal baselines is not a reduced-model null; the primary is."""
    sensitivity = dgp('H1SENS:M2-M1:+0.05', 'HET1', 'population_averaged')
    assert not sensitivity['truth']['interaction_absent'] and np.max(np.abs(sensitivity['beta'][5:])) > 1e-3
    primary = dgp('H1:M2-M1:+0.05', 'HET1', 'population_averaged')
    p = primary['probabilities']['population_averaged']
    assert primary['truth']['interaction_absent']
    assert np.ptp(p[1] - p[0]) > 1e-4 and abs(np.mean(p[1] - p[0]) - 0.05) < 1e-9
    flat = dgp('H1SENS:M2-M1:+0.05', 'HET1', 'population_averaged', profile='FLAT')
    assert flat['truth']['interaction_absent']


def test_the_reference_probability_anchor_is_the_policy_mean_and_m1_is_refused():
    assert CONFIG['calibration']['anchor'] == ps.ANCHOR == 'policy_averaged_reference_probability'
    targets = dgp('H1SENS:M2-M1:+0.05')['targets']
    assert np.allclose(targets.mean(axis=0), ps.revision_levels('CSA', 0.75, 'MODERATE', CONFIG))
    for anchor in ('M1', 'policy_mean'):
        with pytest.raises(ValueError, match='never an M1 baseline'):
            ps.cell_targets(np.array([0.5] * 3), (0,) * 3, (0,) * 3, anchor)
        with pytest.raises(ValueError, match='never an M1 baseline'):
            ps.calibrate_additive(np.array([0.5] * 3), 0.0, 0.0, np.zeros(9), 'conditional', anchor)


def test_estimand_b_is_the_frozen_primary_and_a_remains_a_diagnostic():
    assert ps.PRIMARY_ESTIMAND == 'B' and ps.DIAGNOSTIC_ESTIMAND == 'A'
    assert CONFIG['calibration']['primary_estimand'] == 'B'
    assert CONFIG['calibration']['diagnostic_estimand'] == 'A'
    assert CONFIG['calibration']['primary_target_scale'] == ps.ESTIMANDS['B'] == 'population_averaged'
    assert 'emmeans' in CONFIG['calibration']['integration'] and 'Gauss-Hermite' in CONFIG['calibration']['integration']
    assert CONFIG['inference']['h1_variance_component_uncertainty'] == 'ignored_pending_coverage_validation'
    assert 'variance components' in ps.h1_inference.__doc__ and 'not propagated' in ps.h1_inference.__doc__
    d = dgp('H1:M2-M1:+0.05', 'HET3')
    result = ps.h1_inference(d['beta'], np.eye(9) * 0.01, d['covariance'], 'A')
    assert result['M2-M1']['estimate'] != pytest.approx(d['truth']['B']['M2-M1'], abs=1e-6)


def test_staged_execution_policy_labels_screening_separately():
    stages = CONFIG['stages']
    assert [s['name'] for s in stages.values()][:1] == ['real GLMM smoke']
    assert stages['C']['replications'] == 2000 and stages['C']['status'] == 'NOT_RUN'
    assert stages['D']['status'] == 'NOT_RUN' and stages['B']['status'] == 'NOT_RUN'
    assert sim.stage_decision('PASS', 'screening', CONFIG) == 'CANDIDATE'
    assert sim.stage_decision('FAIL', 'screening', CONFIG) == 'CLEAR_FAILURE'
    assert sim.stage_decision('INCONCLUSIVE', 'screening', CONFIG) == 'INCONCLUSIVE'
    for decision in ('PASS', 'FAIL', 'INCONCLUSIVE'):
        assert sim.stage_decision(decision, 'confirmation', CONFIG) == decision


# --- 14-16 H2 --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('structure', ps.STRUCTURES)
def test_full_and_reduced_share_the_identical_random_structure(structure):
    f = ps.formulas(structure)
    term = ps.RE_TERMS[structure]
    assert f['full'].endswith(' + ' + term) and f['reduced'].endswith(' + ' + term)
    assert f['full'].replace(' + P1:V1 + P1:V2 + P2:V1 + P2:V2', '') == f['reduced']
    assert f['full'].count('||') == f['reduced'].count('||') == (structure != 'RE1')


def test_h2_lrt_statistic_df_and_p_value():
    result = ps.h2_lrt(-100.0, -104.7438645)
    assert result['df'] == 4 and abs(result['statistic'] - 9.487729) < 1e-6
    assert abs(result['p'] - 0.05) < 1e-6
    assert ps.h2_lrt(-100.0, -100.0)['p'] == 1.0
    small = ps.h2_lrt(-100.0, -100.00001)
    assert small['valid'] and small['p'] == pytest.approx(1.0, abs=1e-4)
    assert not ps.h2_lrt(-100.0, -99.0)['valid']
    with pytest.raises(ValueError):
        ps.h2_lrt(-100.0, -101.0, df=3)
    assert len(ps.INTERACTION_NAMES) == 4 == len(ps.FIXED_NAMES) - len(ps.REDUCED_NAMES)


def test_chi_square_4df_survival_matches_known_quantiles():
    for quantile, tail in ((7.779440, 0.10), (9.487729, 0.05), (11.143287, 0.025), (13.276704, 0.01)):
        assert abs(ps.chi2_sf_df4(quantile) - tail) < 1e-6


def test_parametric_bootstrap_p_value_and_scaffold():
    assert ps.bootstrap_p(5.0, [1.0, 6.0, None, 5.0]) == {'p': 3 / 4, 'valid': 3, 'failed': 1}
    reduced = {'beta': [0.2, 0.0, 0.0, 0.0, 0.0], 'components': {'(Intercept)': 0.5}}
    data = ps.simulate_data(np.zeros(9), np.zeros((5, 5)), 12, 1, np.random.default_rng(0))
    result = sim.parametric_bootstrap_h2(data, reduced, 2.0, 'RE1', fake_fitter, CONFIG, 'cell', 3)
    again = sim.parametric_bootstrap_h2(data, reduced, 2.0, 'RE1', fake_fitter, CONFIG, 'cell', 3)
    assert result == again and result['draws'] == 3 and result['valid'] == 3


# --- 17-19 Monte Carlo and acceptance ------------------------------------------------------------------------

def test_wilson_interval_matches_reference_values():
    w = ps.wilson(100, 2000, 0.90)
    assert w['estimate'] == 0.05
    z, n, p = 1.6448536269514722, 2000, 0.05
    centre, half = (p + z * z / (2 * n)) / (1 + z * z / n), z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n
                                                                                             + z * z / (4 * n * n))
    assert w['lower'] == pytest.approx(centre - half, abs=1e-12) == pytest.approx(0.042574, abs=1e-6)
    assert w['upper'] == pytest.approx(centre + half, abs=1e-12) == pytest.approx(0.058642, abs=1e-6)
    assert ps.wilson(0, 10)['lower'] == 0.0 and ps.wilson(10, 10)['upper'] == pytest.approx(1.0, abs=1e-12)
    assert ps.wilson(0, 0) == {'estimate': None, 'lower': 0.0, 'upper': 1.0, 'successes': 0, 'trials': 0}


def test_acceptance_rules():
    band = CONFIG['acceptance']['primary']['type_i_band']
    assert ps.band_decision(ps.wilson(500, 10000), band) == 'PASS'
    assert ps.band_decision(ps.wilson(100, 2000), band) == 'PASS'
    assert ps.band_decision(ps.wilson(110, 2000), band) == 'INCONCLUSIVE'
    assert ps.band_decision(ps.wilson(300, 2000), band) == 'FAIL'
    assert ps.band_decision(ps.wilson(9500, 10000), CONFIG['acceptance']['primary']['coverage_band']) == 'PASS'
    assert ps.power_decision(ps.wilson(4200, 5000)) == 'PASS'
    assert ps.power_decision(ps.wilson(4000, 5000)) == 'INCONCLUSIVE'
    assert ps.power_decision(ps.wilson(3500, 5000)) == 'FAIL'
    assert ps.needs_escalation(ps.wilson(4000, 5000), 0.80, 5000, 10000)
    assert not ps.needs_escalation(ps.wilson(4000, 10000), 0.80, 10000, 10000)
    assert ps.boundary_instability(30, 100, 0.35) and not ps.boundary_instability(30, 100, 0.0)
    assert not ps.boundary_instability(20, 100, 0.35)


def test_design_selection_minimizes_burden_and_prefers_breadth_on_ties():
    feasible = {(120, 1): False, (132, 1): False, (144, 1): True, (120, 2): True, (120, 3): True}
    assert ps.select_design(feasible)['N'] == 144 and ps.select_design(feasible)['R'] == 1
    tie = {(240, 1): True, (120, 2): True}
    assert ps.select_design(tie)['N'] == 240 and ps.select_design(tie)['R'] == 1
    assert ps.select_design({(120, 1): False}) is None


def test_holm_adjustment():
    assert ps.holm([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])


def fitted(beta, names, sds, loglik, **extra):
    size = len(names)
    return {'status': 'fitted', 'beta': dict(zip(names, beta)), 'vcov_names': list(names),
            'vcov': (np.eye(size) * 0.01).tolist(), 're_components': list(sds), 're_sd': list(sds.values()),
            'loglik': loglik, 'singular': False, 'optimizer_code': 0, 'convergence_warnings': [],
            'vcov_warnings': [], 'messages': [], **extra}


def test_convergence_failure_is_separate_from_singular_boundary():
    sds = {'(Intercept)': 0.5, 'P1': 0.0, 'P2': 0.3}
    ok = ps.classify_fit(fitted([0.0] * 9, ps.FIXED_NAMES, sds, -10.0, singular=True), 'RE2', ps.FIXED_NAMES)
    assert ok['status'] == 'ok' and ok['singular'] and ok['boundary'] == {'(Intercept)': False, 'P1': True,
                                                                           'P2': False}
    warned = ps.classify_fit(fitted([0.0] * 9, ps.FIXED_NAMES, sds, -10.0, convergence_warnings=['failed']),
                             'RE2', ps.FIXED_NAMES)
    assert warned['status'] == 'convergence_failure'
    assert ps.classify_fit(fitted([0.0] * 9, ps.FIXED_NAMES, sds, -10.0, optimizer_code=1), 'RE2',
                           ps.FIXED_NAMES)['status'] == 'convergence_failure'
    assert ps.classify_fit({'status': 'error'}, 'RE2', ps.FIXED_NAMES)['status'] == 'numerical_failure'
    bad = fitted([0.0] * 9, ps.FIXED_NAMES, sds, -10.0)
    bad['vcov'][0][0] = -1.0
    assert ps.classify_fit(bad, 'RE2', ps.FIXED_NAMES)['status'] == 'invalid_inference'
    warned_vcov = fitted([0.0] * 9, ps.FIXED_NAMES, sds, -10.0, vcov_warnings=['not positive definite'])
    record = sim.analyze_replicate({'full': warned_vcov, 'reduced': fitted([0.0] * 5, ps.REDUCED_NAMES, sds, -11.0)},
                                   'RE2', CONFIG)
    assert record['full']['status'] == 'invalid_inference' and record['h1'] is None and record['h2'] is None


# --- 20 estimands --------------------------------------------------------------------------------------------

def test_estimand_a_and_b_differ_and_are_computed_separately():
    d = dgp('H1:M2-M1:+0.05', 'HET3', 'population_averaged')
    a, b = d['truth']['A']['M2-M1'], d['truth']['B']['M2-M1']
    assert abs(b - 0.05) < 1e-9 and abs(a - b) > 1e-3
    zero = dgp('NULL:zero', 'HET3')
    assert abs(zero['truth']['A']['M2-M1']) < 1e-12 and abs(zero['truth']['B']['M2-M1']) < 1e-12


def test_delta_method_matches_numerical_gradient_for_both_estimands():
    d = dgp('H2:M2-M1:LINEAR:primary', 'HET2')
    rng = np.random.default_rng(3)
    root = rng.standard_normal((9, 9)) * 0.05
    vcov = root @ root.T + np.eye(9) * 1e-3
    for estimand in ps.ESTIMANDS:
        result = ps.h1_inference(d['beta'], vcov, d['covariance'], estimand)
        for name in ps.CONTRASTS:
            gradient = np.zeros(9)
            for k in range(9):
                step = np.zeros(9)
                step[k] = 1e-6
                up = ps.contrasts_on_scale(d['beta'] + step, d['covariance'], ps.ESTIMANDS[estimand])[name]
                down = ps.contrasts_on_scale(d['beta'] - step, d['covariance'], ps.ESTIMANDS[estimand])[name]
                gradient[k] = (up - down) / 2e-6
            assert result[name]['se'] == pytest.approx(math.sqrt(gradient @ vcov @ gradient), rel=1e-5)
            assert result[name]['estimate'] == pytest.approx(d['truth'][estimand][name], abs=1e-12)
            assert result[name]['lower'] < result[name]['estimate'] < result[name]['upper']


def test_simple_contrasts_are_six_with_holm():
    d = dgp('H2:M2-M1:LINEAR:primary', 'HET1')
    rows = ps.simple_contrasts(d['beta'], np.eye(9) * 0.01, d['covariance'], 'A')
    assert len(rows) == 6 and all(r['p_holm'] >= r['p'] for r in rows)


# --- 21 runner determinism with a fake fitter ------------------------------------------------------------------

def fake_fitter(jobs):
    """Deterministic data-dependent stand-in for lme4 (tests only): empirical cell logits solved exactly."""
    out = {}
    for job in jobs:
        y, n = np.array(job['data']['y']), np.array(job['data']['n'])
        rate = (y.reshape(-1, 9).sum(0) + 0.5) / (n.reshape(-1, 9).sum(0) + 1.0)
        beta = np.linalg.solve(ps.design_matrix(), ps.logit(rate))
        loglik = float(np.sum(y * np.log(rate[np.tile(np.arange(9), len(y) // 9)])))
        components = {c: 0.4 for c in ('(Intercept)', 'P1', 'P2', 'V1', 'V2')
                      if c == '(Intercept)' or ('P' in c and '|| scenario' in job['formulas']['full'])}
        out[job['job_id']] = {'full': fitted(beta, ps.FIXED_NAMES, components, loglik),
                              'reduced': fitted(beta[:5], ps.REDUCED_NAMES, components, loglik - 1.3)}
    return {'R': 'fake'}, out


def smoke_cell(scenario='H1:M2-M1:+0.05', structure='RE2'):
    fields = sim.dgp_fields('P0', 'CSA', 0.75, 'FLAT', 'HET2', scenario, 'population_averaged', ps.ANCHOR, 120, 1)
    return {'dgp': fields, 'structure': structure, 'grid': 'primary', 'family': 'primary'}


def test_results_are_identical_for_any_cell_order_and_worker_count(tmp_path):
    cells = [smoke_cell('H1:M2-M1:+0.05'), smoke_cell('NULL:zero'), smoke_cell('NULL:zero', 'RE1')]
    config = {**CONFIG, 'fitting': {**CONFIG['fitting'], 'batch_size': 2}}
    for index, (order, workers) in enumerate(((cells, 1), (cells[::-1], 3))):
        for cell in order:
            sim.run_cell(cell, list(range(5)), fake_fitter, tmp_path / str(index), config, workers)
    for cell in cells:
        first = sim.read_records(sim.cell_directory(tmp_path / '0', cell))
        second = sim.read_records(sim.cell_directory(tmp_path / '1', cell))
        assert first == second and [r['replicate'] for r in first] == list(range(5))
    same_dgp = [sim.read_records(sim.cell_directory(tmp_path / '0', c))[0]['seed'] for c in cells[1:]]
    assert same_dgp[0] == same_dgp[1]


def test_run_cell_resumes_without_overwriting(tmp_path):
    cell, config = smoke_cell(), {**CONFIG, 'fitting': {**CONFIG['fitting'], 'batch_size': 2}}
    directory = sim.run_cell(cell, list(range(2)), fake_fitter, tmp_path, config)
    before = (directory / 'batch-000000.json').read_bytes()
    calls = []

    def counting(jobs):
        calls.append([j['job_id'] for j in jobs])
        return fake_fitter(jobs)
    sim.run_cell(cell, list(range(4)), counting, tmp_path, config)
    assert calls == [['2', '3']] and (directory / 'batch-000000.json').read_bytes() == before
    with pytest.raises(ValueError, match='another cell'):
        (directory / 'cell.json').write_text(json.dumps(smoke_cell('NULL:zero')))
        sim.run_cell(cell, list(range(4)), fake_fitter, tmp_path, config)


def test_aggregation_retains_estimates_bounds_denominators_and_failures(tmp_path):
    cell = smoke_cell('NULL:zero')
    sim.run_cell(cell, list(range(4)), fake_fitter, tmp_path, CONFIG)
    [summary] = sim.aggregate(tmp_path, CONFIG)
    assert summary['requested'] == 4 and summary['completed'] == 4
    assert summary['fit_status_full'] == {'ok': 4, 'convergence_failure': 0, 'invalid_inference': 0,
                                          'numerical_failure': 0}
    test = summary['tests']['h1/B/M2-M1']
    assert test['role'] == 'null' and test['valid'] == 4
    assert set(test['rejection_nominal']) == {'estimate', 'lower', 'upper', 'successes', 'trials'}
    assert 'type_i' in test['decisions'] and 'coverage' in test['decisions']
    assert summary['tests']['h2/lrt_chisq4']['role'] == 'null'
    assert summary['boundary']['P1']['true_sd'] == pytest.approx(0.35)


def test_test_roles_follow_the_true_parameters():
    alternative = smoke_cell('H1:M2-M1:+0.05')
    d = sim.dgp_of(alternative['dgp'], CONFIG)
    assert sim.test_role(alternative, d, 'M2-M1', 'B') == 'alternative'
    assert sim.test_role(alternative, d, 'M3-M2', 'B') == 'null'
    assert sim.test_role(alternative, d, 'M2-M1', 'A') == 'other'
    h2 = smoke_cell('H2:M2-M1:LINEAR:primary')
    assert sim.test_role(h2, sim.dgp_of(h2['dgp'], CONFIG)) == 'alternative'
    null = smoke_cell('H1:M2-M1:+0.05')
    assert sim.test_role(null, sim.dgp_of(null['dgp'], CONFIG)) == 'null'
    assert sim.test_role(null, sim.dgp_of(null['dgp'], CONFIG), 'M2-M1', 'B') == 'alternative'


def test_monte_carlo_plan_values_are_configured_not_executed():
    mc = CONFIG['monte_carlo']
    assert mc['master_seed'] == 20260920 and mc['screening_replications'] == 2000
    assert mc['final_replications'] == {'type_i': 10000, 'coverage': 10000, 'power': 5000, 'power_escalation': 10000}
    assert CONFIG['inference']['planning_thresholds'] == {'h1': 0.0125, 'h2': 0.025}
    assert CONFIG['inference']['final_multiplicity'] == 'holm' and CONFIG['status'] == 'MACHINERY_ONLY_NOT_EXECUTED'


# --- Real lme4 smoke fits (skipped only when R is absent) -------------------------------------------------------

EXPECTED_COMPONENTS = {'RE1': ['(Intercept)'], 'RE2': ['(Intercept)', 'P1', 'P2'],
                       'RE3': ['(Intercept)', 'P1', 'P2', 'V1', 'V2']}


def smoke_fits(structure, replicate=0, scenario='NULL:zero'):
    """One real grouped-binomial GLMM fit pair at the central point; non-inferential."""
    cell = smoke_cell(scenario, structure)
    d = sim.dgp_of(cell['dgp'], CONFIG)
    data = ps.simulate_data(d['beta'], d['covariance'], cell['dgp']['N'], cell['dgp']['R'],
                            ps.rng_for(CONFIG['monte_carlo']['master_seed'], ps.cell_id(cell['dgp']), replicate))
    versions, fits = sim.RFitter(CONFIG)([sim.job('smoke', data, structure)])
    return versions, {k: sim.normalize_fit(v) for k, v in fits['smoke'].items()}, data


@pytest.mark.skipif(shutil.which('Rscript') is None, reason='R with lme4 is not installed')
@pytest.mark.parametrize('structure', ps.STRUCTURES)
def test_real_lme4_smoke_fit_has_the_declared_variance_components_and_no_correlations(structure):
    versions, fits, data = smoke_fits(structure)
    assert set(versions) == {'R', 'lme4', 'Matrix', 'jsonlite'} and all(versions.values())
    assert len(data['y']) == 120 * 9 and set(data['n']) == {1}
    for part, names in (('full', ps.FIXED_NAMES), ('reduced', ps.REDUCED_NAMES)):
        fit = fits[part]
        assert fit['status'] == 'fitted'
        assert list(fit['beta']) == list(names) and fit['vcov_names'] == list(names)
        assert fit['re_components'] == EXPECTED_COMPONENTS[structure]
        assert len(fit['re_sd']) == len(EXPECTED_COMPONENTS[structure])
        assert fit['re_correlation_terms'] == 0
        assert set(fit['re_groups']) == {'scenario'} | {f'scenario.{i}' for i in range(1, len(fit['re_sd']))}
        assert math.isfinite(fit['loglik']) and isinstance(fit['singular'], bool)
        assert ps.classify_fit(fit, structure, names, CONFIG['fitting']['singular_tol'])['status'] in ps.FIT_STATUSES
    record = sim.analyze_replicate(fits, structure, CONFIG)
    assert record['h2'] is not None and record['h2']['df'] == 4
    assert math.isfinite(record['h2']['statistic'])
    assert set(record['full']['boundary']) == set(EXPECTED_COMPONENTS[structure])


@pytest.mark.skipif(shutil.which('Rscript') is None, reason='R with lme4 is not installed')
def test_real_full_and_reduced_fits_share_the_random_structure_and_differ_by_four_fixed_terms():
    _, fits, _ = smoke_fits('RE2')
    assert fits['full']['re_components'] == fits['reduced']['re_components']
    assert len(fits['full']['beta']) - len(fits['reduced']['beta']) == 4
    assert [n for n in fits['full']['beta'] if n not in fits['reduced']['beta']] == list(ps.INTERACTION_NAMES)


@pytest.mark.skipif(shutil.which('Rscript') is None, reason='R with lme4 is not installed')
def test_real_smoke_run_through_the_runner_records_batches(tmp_path):
    cell = smoke_cell('NULL:zero', 'RE1')
    directory = sim.run_cell(cell, [0, 1], sim.RFitter(CONFIG), tmp_path, CONFIG)
    records = sim.read_records(directory)
    payload = json.loads(next(directory.glob('batch-*.json')).read_text())
    assert len(records) == 2 and payload['versions']['lme4'] and payload['environment']['numpy']
    assert payload['fit_control'] == sim.fit_control(CONFIG)
    assert all(r['full']['status'] in ps.FIT_STATUSES for r in records)


def test_random_effect_profiles_are_diagonal_except_the_correlated_stress_profile():
    for name, sigmas in (('HET1', (0.5, 0, 0, 0, 0)), ('HET2', (0.75, 0.35, 0.35, 0, 0)),
                         ('HET3', (0.75, 0.35, 0.35, 0.35, 0.35))):
        covariance, _, sds = ps.re_covariance(ps.profile(name, CONFIG))
        assert np.allclose(sds, sigmas) and np.allclose(covariance, np.diag(np.square(sigmas)))
    covariance, corr, sds = ps.re_covariance(ps.profile('STRESS', CONFIG))
    assert np.allclose(sds, (1.0, 0.5, 0.5, 0.5, 0.5))
    assert np.allclose(corr[~np.eye(5, dtype=bool)], 0.30) and np.all(np.linalg.eigvalsh(covariance) > 0)
    partial, corr, _ = ps.re_covariance({'sigma_intercept': 1.0, 'sigma_policy': 0.5, 'sigma_revision': 0.0,
                                         'rho': 0.3})
    assert np.allclose(corr[:3, :3][~np.eye(3, dtype=bool)], 0.3) and np.allclose(corr[3:, :3], 0)
    data = ps.simulate_data(np.zeros(9), covariance, 4000, 1, np.random.default_rng(5))
    assert len(data['y']) == 36000
