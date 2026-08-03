"""Check the hand-rolled statistics against values computed independently.

Reference numbers come from textbook worked examples and from scipy runs done
outside this repo (scipy is deliberately not a dependency here). Tolerances are
loose enough for the approximations used and tight enough to catch a real bug.
"""
import math

import pytest

from lib_stats import (benjamini_hochberg, chi2_sf, kruskal_wallis, mean, ols,
                       pearson_r, sem, t_sf_two_sided, welch_t)


# ------------------------------------------------------------- distributions

@pytest.mark.parametrize("x,df,expected", [
    (3.84, 1, 0.0500),      # the classic 95% critical value
    (5.99, 2, 0.0500),
    (11.07, 5, 0.0500),
    (0.0, 3, 1.0),
    (18.31, 10, 0.0500),
])
def test_chi2_survival_matches_critical_values(x, df, expected):
    assert chi2_sf(x, df) == pytest.approx(expected, abs=5e-4)


@pytest.mark.parametrize("t,df,expected", [
    (2.776, 4, 0.05),       # two-sided 95% critical value, df=4
    (2.228, 10, 0.05),
    (1.960, 100000, 0.05),  # normal limit
    (0.0, 8, 1.0),
])
def test_t_two_sided_matches_critical_values(t, df, expected):
    assert t_sf_two_sided(t, df) == pytest.approx(expected, abs=1e-3)


# --------------------------------------------------------------------- tests

def test_kruskal_wallis_known_example():
    # Three groups, worked example: H = 6.4, df = 2
    groups = [[2.9, 3.0, 2.5, 2.6, 3.2],
              [3.8, 2.7, 4.0, 2.4],
              [2.8, 3.4, 3.7, 2.2, 2.0]]
    h, df, p = kruskal_wallis(groups)
    assert df == 2
    assert h == pytest.approx(0.7714, abs=1e-3)
    assert p == pytest.approx(0.680, abs=1e-2)


def test_kruskal_wallis_separated_groups_are_significant():
    h, df, p = kruskal_wallis([[1, 2, 3, 4, 5], [100, 101, 102, 103, 104]])
    assert df == 1
    assert p < 0.01


def test_kruskal_wallis_handles_ties_without_blowing_up():
    h, df, p = kruskal_wallis([[1, 1, 1, 1], [1, 1, 1, 1]])
    assert h == pytest.approx(0.0, abs=1e-9)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_kruskal_wallis_needs_two_groups():
    assert kruskal_wallis([[1, 2, 3]]) == (0.0, 0, 1.0)
    assert kruskal_wallis([]) == (0.0, 0, 1.0)


def test_welch_t_known_example():
    # Means 19.55 vs 23.49, sample variances 19.9494 and 3.6877 (both hand-checked),
    # so t = -3.94 / sqrt(1.99494 + 0.36877) and Welch-Satterthwaite df = 12.217.
    a = [27.5, 21.0, 19.0, 23.6, 17.0, 17.9, 16.9, 15.3, 13.1, 24.2]
    b = [27.1, 22.0, 20.8, 23.4, 23.4, 23.5, 25.8, 22.0, 24.7, 22.2]
    t, df, p = welch_t(a, b)
    assert t == pytest.approx(-2.5627, abs=1e-3)
    assert df == pytest.approx(12.217, abs=0.01)
    assert 0.02 < p < 0.03


def test_welch_t_identical_samples_is_null():
    t, df, p = welch_t([1, 2, 3, 4], [1, 2, 3, 4])
    assert t == pytest.approx(0.0)
    assert p == pytest.approx(1.0, abs=1e-6)


def test_pearson_perfect_and_zero():
    r, n, p = pearson_r([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
    assert r == pytest.approx(1.0, abs=1e-6)
    assert p < 1e-6
    r, n, p = pearson_r([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert r == pytest.approx(-1.0, abs=1e-6)


def test_pearson_known_example():
    xs = [43, 21, 25, 42, 57, 59]
    ys = [99, 65, 79, 75, 87, 81]
    r, n, p = pearson_r(xs, ys)
    assert r == pytest.approx(0.5298, abs=1e-3)
    assert p == pytest.approx(0.2795, abs=5e-3)


def test_pearson_constant_input_is_not_a_crash():
    assert pearson_r([1, 1, 1, 1], [1, 2, 3, 4]) == (0.0, 4, 1.0)


# ------------------------------------------------------------------ multiplicity

def test_benjamini_hochberg_textbook_case():
    # Benjamini & Hochberg 1995 worked example; at FDR 0.05 the first four survive
    p = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344,
         0.0459, 0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.000]
    keep = benjamini_hochberg(p, 0.05)
    assert keep[:4] == [True, True, True, True]
    assert not any(keep[4:])


def test_benjamini_hochberg_is_stricter_than_raw_alpha():
    # Seven tests, one at 0.04: significant raw, not after correction.
    p = [0.04, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    assert p[0] < 0.05
    assert benjamini_hochberg(p, 0.05) == [False] * 7


def test_benjamini_hochberg_keeps_a_genuine_hit():
    p = [0.0001, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    assert benjamini_hochberg(p, 0.05)[0] is True


def test_benjamini_hochberg_empty():
    assert benjamini_hochberg([], 0.05) == []


# --------------------------------------------------------------------- modelling

def test_ols_recovers_known_coefficients():
    # y = 3 + 2*x1 - 1*x2, exactly
    x1 = [1, 2, 3, 4, 5, 6]
    x2 = [2, 1, 4, 3, 6, 5]
    y = [3 + 2 * a - b for a, b in zip(x1, x2)]
    coeffs, resid = ols(y, [x1, x2])
    assert coeffs[0] == pytest.approx(3.0, abs=1e-6)
    assert coeffs[1] == pytest.approx(2.0, abs=1e-6)
    assert coeffs[2] == pytest.approx(-1.0, abs=1e-6)
    assert all(abs(r) < 1e-6 for r in resid)


def test_ols_residuals_shrink_variance_when_predictor_is_real():
    x = [float(i) for i in range(40)]
    y = [5 + 3 * v + ((-1) ** i) * 0.5 for i, v in enumerate(x)]
    _, resid = ols(y, [x])
    assert max(abs(r) for r in resid) < 1.0
    assert max(y) - min(y) > 100


def test_ols_singular_system_returns_none():
    x = [1, 2, 3, 4]
    coeffs, resid = ols([1, 2, 3, 4], [x, x])   # perfectly collinear
    assert coeffs is None and resid is None


def test_ols_refuses_underdetermined_system():
    assert ols([1.0, 2.0], [[1, 2], [3, 4], [5, 6]]) == (None, None)


# ------------------------------------------------------------------ descriptives

def test_sem_and_mean():
    v = [2, 4, 4, 4, 5, 5, 7, 9]
    assert mean(v) == pytest.approx(5.0)
    assert sem(v) == pytest.approx(2.13809 / math.sqrt(8), abs=1e-4)


def test_sem_of_single_value_is_zero_not_a_crash():
    assert sem([4.2]) == 0.0
    assert mean([]) == 0.0
