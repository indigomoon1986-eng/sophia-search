#!/usr/bin/env python3
"""Tests for the compass cross-ratio fix (README: 'Cross-ratio 103/71 vs 29/20 at 0.05% error')."""

import cmath
import math

from compass import TARGET_CROSS_RATIO, cross_ratio, cross_ratio4, score_triplet


def test_cross_ratio4_definition():
    # (z1, z2; z3, z4) = ((z1-z3)/(z1-z4)) / ((z2-z3)/(z2-z4))
    z1, z2, z3, z4 = 1 + 2j, -3 + 0.5j, 4 - 1j, 0.25 + 3j
    want = ((z1 - z3) / (z1 - z4)) / ((z2 - z3) / (z2 - z4))
    assert cmath.isclose(cross_ratio4(z1, z2, z3, z4), want)
    # real collinear points: (0, 1; 2, 3) = (-2/-3)/(-1/-2) = 4/3
    assert math.isclose(cross_ratio4(0, 1, 2, 3).real, 4 / 3)
    # projective invariance under a Mobius map w = (2z+1)/(z+3)
    m = lambda z: (2 * z + 1) / (z + 3)
    assert cmath.isclose(cross_ratio4(*(m(z) for z in (z1, z2, z3, z4))), want)


def test_cross_ratio4_point_at_infinity():
    # (z1, z2; 0, inf) = z1 / z2
    assert math.isclose(cross_ratio4(103.0, 71.0, 0.0, math.inf).real, 103 / 71)


def test_readme_fudan_cross_ratio():
    cr = cross_ratio(71.0, 87.0, 103.0)
    assert math.isclose(cr, 103 / 71)
    err_pct = abs(cr - TARGET_CROSS_RATIO) / TARGET_CROSS_RATIO * 100
    assert err_pct < 0.05  # README: 0.05 % error
    assert math.isclose(err_pct, 0.0486, abs_tol=1e-3)
    # order of the outer points does not matter
    assert math.isclose(cross_ratio(103.0, 87.0, 71.0), 103 / 71)


def test_readme_fudan_checks():
    r = score_triplet(71.0, 87.0, 103.0)
    assert r["cross_ratio"] == round(103 / 71, 6)
    assert r["cross_ratio_error_pct"] == 0.049
    assert r["mean_error_thz"] == 0.0          # README: 87 is the mean at 0.00 %
    assert r["gaps_thz"] == [16, 16]           # README: even 16 THz spacing
    c = r["checks"]
    assert c["cross_ratio"] > 0.85 and c["mean"] == 1.0 and c["spacing"] == 1.0
    assert c["rydberg"] > 0.85
    assert r["invariant_score"] > 0.85
    # Total still carries the trap penalty (71 ~ CO2, 87 ~ lipid CH2): 0.15 each.
    assert len(r["trap_flags"]) == 2 and r["trap_penalty"] == 0.3
    assert math.isclose(r["score"], round(r["invariant_score"] - 0.3, 4), abs_tol=1e-4)


def test_degenerate_inputs():
    assert math.isnan(cross_ratio(0.0, 1.0, 2.0))
    assert cmath.isnan(cross_ratio4(1, 1, 1, 1))
