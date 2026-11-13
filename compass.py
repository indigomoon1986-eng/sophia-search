#!/usr/bin/env python3
"""LTOE Heuristic Compass — scores candidate triplets against locked invariants."""

from __future__ import annotations
import json
import math

RYDBERG_THZ = 3280.0  # Rydberg frequency in THz (hydrogen)
SEED_DENOM = 31.92
TARGET_CROSS_RATIO = 29.0 / 20.0
TARGET_GAP = 16.0  # THz even spacing

# Conventional molecular bands — trap flags
BANDS = {
    "CO2_asymmetric_stretch": 70.0,
    "lipid_CH2": 87.0,
    "OH_NH_stretch": 100.0,
    "Walker_membrane_potential": 36.27,
    "glutamate_CCC": 34.5,
}
BAND_TOL = 1.0  # THz tolerance window


def cross_ratio4(z1: complex, z2: complex, z3: complex, z4: complex) -> complex:
    """Projective cross-ratio of four collinear points on the complex plane:

        (z1, z2; z3, z4) = ((z1 - z3) / (z1 - z4)) / ((z2 - z3) / (z2 - z4))

    Any point may be ``math.inf`` (the point at infinity); the factors that
    contain it cancel in the limit. Returns complex nan for degenerate input.
    """
    def _inf(z):
        return isinstance(z, (int, float)) and math.isinf(z)

    num1 = 1.0 if _inf(z1) or _inf(z3) else (z1 - z3)
    den1 = 1.0 if _inf(z1) or _inf(z4) else (z1 - z4)
    num2 = 1.0 if _inf(z2) or _inf(z3) else (z2 - z3)
    den2 = 1.0 if _inf(z2) or _inf(z4) else (z2 - z4)
    try:
        return complex((num1 / den1) / (num2 / den2))
    except ZeroDivisionError:
        return complex(float("nan"), float("nan"))


def cross_ratio(a: float, b: float, c: float) -> float:
    """Triplet cross-ratio for (low, mid, high), as the README audits it:
    103/71 vs 29/20 for the (71, 87, 103) triplet, i.e. high / low.

    Formally this is the four-point cross-ratio (z1, z2; z3, z4) with
    z1 = high, z2 = low, z3 = 0 (the origin of the frequency axis) and
    z4 = infinity, which reduces exactly to high / low. ``mid`` does not enter
    the ratio; it is tested separately by the arithmetic-mean check.

    (Before this fix the code returned (b/a)/(c/b), about 1.035 for the
    Fudan triplet, which is not the README quantity.)
    """
    if a == 0 or c == 0:
        return float("nan")
    lo, hi = min(a, c), max(a, c)
    return cross_ratio4(hi, lo, 0.0, math.inf).real


def arithmetic_mean_error(a: float, b: float, c: float) -> float:
    """How far mid is from the mean of the other two."""
    return abs(b - (a + c) / 2.0)


def gap_list(a: float, b: float, c: float) -> list[float]:
    return [b - a, c - b]


def rydberg_denominator(f: float) -> float:
    return RYDBERG_THZ / f


def trap_flags(freqs: list[float]) -> list[str]:
    flags = []
    for f in freqs:
        for name, center in BANDS.items():
            if abs(f - center) <= BAND_TOL:
                flags.append(f"{f} THz within {BAND_TOL} of {name} ({center} THz)")
    return flags


def score_triplet(low: float, mid: float, high: float) -> dict:
    """Score 0-1. Four checks, equal weight, minus trap penalty."""
    cr = cross_ratio(low, mid, high)
    cr_err = abs(cr - TARGET_CROSS_RATIO) / TARGET_CROSS_RATIO if not math.isnan(cr) else 1.0
    cr_score = max(0.0, 1.0 - cr_err * 20)

    mean_err = arithmetic_mean_error(low, mid, high)
    mean_score = max(0.0, 1.0 - mean_err / 1.0)  # 1 THz tolerance

    gaps = gap_list(low, mid, high)
    gap_err = sum(abs(g - TARGET_GAP) for g in gaps) / (2 * TARGET_GAP)
    gap_score = max(0.0, 1.0 - gap_err)

    denoms = [rydberg_denominator(f) for f in (low, mid, high)]
    denom_err = min(abs(d - SEED_DENOM) for d in denoms) / SEED_DENOM
    denom_score = max(0.0, 1.0 - denom_err * 10)

    traps = trap_flags([low, mid, high])
    trap_penalty = 0.15 * len(traps)

    total = (cr_score + mean_score + gap_score + denom_score) / 4.0 - trap_penalty
    total = max(0.0, min(1.0, total))

    invariant = (cr_score + mean_score + gap_score + denom_score) / 4.0

    return {
        "score": round(total, 4),
        "invariant_score": round(invariant, 4),  # four checks, before trap penalty
        "checks": {"cross_ratio": round(cr_score, 4), "mean": round(mean_score, 4),
                   "spacing": round(gap_score, 4), "rydberg": round(denom_score, 4)},
        "trap_penalty": round(trap_penalty, 4),
        "cross_ratio": round(cr, 6) if not math.isnan(cr) else None,
        "cross_ratio_error_pct": round(cr_err * 100, 3) if not math.isnan(cr) else None,
        "mean_error_thz": round(mean_err, 4),
        "gaps_thz": [round(g, 2) for g in gaps],
        "rydberg_denominators": [round(d, 2) for d in denoms],
        "trap_flags": traps,
    }


def scan_denominators(low_d: float = 20.0, high_d: float = 60.0, step: float = 0.01,
                      min_score: float = 0.85) -> list[dict]:
    """Sweep Rydberg denominators, return triplets above threshold."""
    hits = []
    d = low_d
    while d <= high_d:
        # build triplet from three denominators near seed structure
        for d2 in (d + 5.0, d + 8.0, d + 10.0):
            if d2 > high_d:
                continue
            for d3 in (d2 + 5.0, d2 + 8.0, d2 + 10.0):
                if d3 > high_d:
                    continue
                freqs = sorted([RYDBERG_THZ / d, RYDBERG_THZ / d2, RYDBERG_THZ / d3])
                r = score_triplet(*freqs)
                if r["score"] >= min_score:
                    hits.append({"denominators": [round(d, 2), round(d2, 2), round(d3, 2)],
                                 "frequencies_thz": [round(f, 2) for f in freqs], **r})
        d += step
    # dedupe by frequency set
    seen = set()
    uniq = []
    for h in hits:
        key = tuple(h["frequencies_thz"])
        if key not in seen:
            seen.add(key)
            uniq.append(h)
    return sorted(uniq, key=lambda x: -x["score"])


def breathing(density_shift: float) -> dict:
    """Shift centroid with crista density while locking ratios.
    density_shift: fractional change, e.g. -0.35 tubular, +0.35 lamellar.
    """
    base = [71.0, 87.0, 103.0]
    # ratios locked; total spectral weight tracks density
    weight = 1.0 + density_shift
    shifted = [round(f * weight, 2) for f in base]
    centroid = sum(shifted) / 3.0
    return {
        "density_shift": density_shift,
        "frequencies_thz": shifted,
        "centroid_thz": round(centroid, 2),
        "trace": round(sum(shifted), 2),
        "ratios_locked": True,
        "wavelengths_um": [round(299.792458 / f, 2) for f in shifted],
    }


if __name__ == "__main__":
    fudan = score_triplet(71.0, 87.0, 103.0)
    print(json.dumps(fudan, indent=2))
    print("--- breathing tubular ---")
    print(json.dumps(breathing(-0.35), indent=2))
    print("--- breathing lamellar ---")
    print(json.dumps(breathing(0.35), indent=2))