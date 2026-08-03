"""Small, dependency-free statistics for the "is any of this real?" chapter.

Everything here exists so the esoteric chapter can disarm itself with real numbers
instead of asserted ones. Hand-rolled rather than pulling in scipy: the public
generator ships to anyone who clones it, and ~100 MB of scientific Python for one
tongue-in-cheek chapter is a bad trade. Each function is small enough to verify
against a textbook example, which is what tests/test_stats.py does.

Conventions: p-values are two-sided; groups with fewer than MIN_N samples are the
caller's problem, not ours.
"""
import math

# ---------------------------------------------------------------- distributions

def _erf(x):
    """Abramowitz & Stegun 7.1.26 — |error| < 1.5e-7, plenty for p-values."""
    sign = -1 if x < 0 else 1
    x = abs(x)
    t = 1 / (1 + 0.3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741)
              * t - 0.284496736) * t + 0.254829592) * t * math.exp(-x * x)
    return sign * y


def normal_sf(z):
    """P(Z > z) for standard normal."""
    return 0.5 * (1 - _erf(z / math.sqrt(2)))


def _gamma_ln(x):
    """Lanczos approximation of ln Γ(x)."""
    g = [676.5203681218851, -1259.1392167224028, 771.32342877765313,
         -176.61502916214059, 12.507343278686905, -0.13857109526572012,
         9.9843695780195716e-6, 1.5056327351493116e-7]
    if x < 0.5:
        return math.log(math.pi / math.sin(math.pi * x)) - _gamma_ln(1 - x)
    x -= 1
    a = 0.99999999999980993
    t = x + 7.5
    for i, c in enumerate(g):
        a += c / (x + i + 1)
    return 0.5 * math.log(2 * math.pi) + (x + 0.5) * math.log(t) - t + math.log(a)


def _gamma_inc_lower_reg(s, x):
    """Regularised lower incomplete gamma P(s, x), series + continued fraction."""
    if x < 0 or s <= 0:
        raise ValueError("domain")
    if x == 0:
        return 0.0
    if x < s + 1:                                    # series expansion
        term = 1.0 / s
        total = term
        n = s
        for _ in range(500):
            n += 1
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        return total * math.exp(-x + s * math.log(x) - _gamma_ln(s))
    # continued fraction for Q(s, x), then P = 1 - Q
    tiny = 1e-300
    b = x + 1 - s
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-14:
            break
    q = math.exp(-x + s * math.log(x) - _gamma_ln(s)) * h
    return 1 - q


def chi2_sf(x, df):
    """P(X > x) for chi-squared with df degrees of freedom."""
    if x <= 0:
        return 1.0
    return 1 - _gamma_inc_lower_reg(df / 2, x / 2)


def t_sf_two_sided(t, df):
    """Two-sided p-value for Student's t via the incomplete beta identity.

    Uses the normal approximation above df=200, where the difference is far below
    the precision anything here is reported at.
    """
    t = abs(t)
    if df <= 0:
        return 1.0
    if df > 200:
        return 2 * normal_sf(t)
    x = df / (df + t * t)
    return _betainc_reg(df / 2, 0.5, x)


def _betainc_reg(a, b, x):
    """Regularised incomplete beta I_x(a, b) via Lentz's continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = _gamma_ln(a) + _gamma_ln(b) - _gamma_ln(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    if x >= (a + 1) / (a + b + 2):                   # converges faster mirrored
        return 1 - _betainc_reg(b, a, 1 - x)
    tiny = 1e-300
    f, c, d = 1.0, 1.0, 0.0
    for i in range(300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1 + num * d
        if abs(d) < tiny:
            d = tiny
        d = 1 / d
        c = 1 + num / c
        if abs(c) < tiny:
            c = tiny
        f *= c * d
        if abs(1 - c * d) < 1e-14:
            break
    return front * (f - 1)


# ---------------------------------------------------------------------- tests

def _ranks(values):
    """Ranks 1..n with ties averaged; also returns the tie-correction term."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    tie_term = 0.0
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        t = j - i + 1
        if t > 1:
            tie_term += t ** 3 - t
        i = j + 1
    return ranks, tie_term


def kruskal_wallis(groups):
    """H test for k independent samples. Returns (H, df, p).

    Non-parametric on purpose: pace distributions are skewed by long easy runs.
    """
    groups = [g for g in groups if g]
    k = len(groups)
    if k < 2:
        return 0.0, 0, 1.0
    flat = [v for g in groups for v in g]
    n = len(flat)
    ranks, tie_term = _ranks(flat)
    h, pos = 0.0, 0
    for g in groups:
        r = sum(ranks[pos:pos + len(g)])
        h += r * r / len(g)
        pos += len(g)
    h = 12 / (n * (n + 1)) * h - 3 * (n + 1)
    if tie_term:
        # every observation identical -> the correction denominator is 0 and the
        # test has nothing to distinguish; that is a null result, not an error
        correction = 1 - tie_term / (n ** 3 - n)
        if correction <= 0:
            return 0.0, k - 1, 1.0
        h /= correction
    df = k - 1
    return h, df, chi2_sf(h, df)


def welch_t(a, b):
    """Welch's unequal-variance t test. Returns (t, df, p)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0, 0, 1.0
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    sa, sb = va / len(a), vb / len(b)
    if sa + sb == 0:
        return 0.0, 0, 1.0
    t = (ma - mb) / math.sqrt(sa + sb)
    df = (sa + sb) ** 2 / (sa ** 2 / (len(a) - 1) + sb ** 2 / (len(b) - 1))
    return t, df, t_sf_two_sided(t, df)


def pearson_r(xs, ys):
    """Pearson correlation. Returns (r, n, p) with p from the t transform."""
    n = len(xs)
    if n < 3:
        return 0.0, n, 1.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return 0.0, n, 1.0
    r = sxy / math.sqrt(sxx * syy)
    r = max(-0.999999999, min(0.999999999, r))
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return r, n, t_sf_two_sided(t, n - 2)


def benjamini_hochberg(pvalues, fdr=0.05):
    """Return a list of booleans: which hypotheses survive at the given FDR.

    Controls the expected proportion of false discoveries. With seven tests at
    alpha 0.05 you expect 0.35 hits by chance alone, which is exactly the point
    the chapter is making, so the correction has to be real rather than decorative.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    keep = [False] * m
    cutoff_rank = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= fdr * rank / m:
            cutoff_rank = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= cutoff_rank:
            keep[idx] = True
    return keep


# -------------------------------------------------------------------- modelling

def ols(y, xs):
    """Least squares with an intercept. xs is a list of predictor columns.

    Solved by Gauss-Jordan on the normal equations — fine for the 2-3 predictors
    here, and it keeps the dependency list at zero. Returns (coeffs, residuals)
    where coeffs[0] is the intercept. Returns (None, None) if the system is
    singular, which is the caller's cue to drop a predictor.
    """
    n = len(y)
    cols = [[1.0] * n] + [list(c) for c in xs]
    k = len(cols)
    if n <= k:
        return None, None
    a = [[sum(cols[i][r] * cols[j][r] for r in range(n)) for j in range(k)]
         + [sum(cols[i][r] * y[r] for r in range(n))] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(a[r][i]))
        if abs(a[p][i]) < 1e-12:
            return None, None
        a[i], a[p] = a[p], a[i]
        piv = a[i][i]
        a[i] = [v / piv for v in a[i]]
        for r in range(k):
            if r != i and a[r][i]:
                f = a[r][i]
                a[r] = [v - f * w for v, w in zip(a[r], a[i])]
    coeffs = [row[k] for row in a]
    resid = [y[r] - sum(coeffs[i] * cols[i][r] for i in range(k)) for r in range(n)]
    return coeffs, resid


def mean(v):
    return sum(v) / len(v) if v else 0.0


def stdev(v):
    if len(v) < 2:
        return 0.0
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def sem(v):
    """Standard error of the mean — drives the noise band in the charts."""
    return stdev(v) / math.sqrt(len(v)) if len(v) > 1 else 0.0
