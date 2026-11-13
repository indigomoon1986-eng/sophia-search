#!/usr/bin/env python3
"""Query-understanding layer: classify intent against invariant space before indexing."""

from __future__ import annotations
import re
from compass import BANDS, TARGET_CROSS_RATIO, TARGET_GAP, SEED_DENOM, RYDBERG_THZ

# Intent patterns mapped to compass dimensions
INTENT_MAP = {
    "cross_ratio": [r"cross.?ratio", r"29/?20", r"invariant ratio", r"scale.?free"],
    "mean": [r"arithmetic.?mean", r"midpoint", r"balance.?point", r"centroid"],
    "spacing": [r"spacing", r"gap", r"even.?spaced", r"ladder", r"harmonic"],
    "denominator": [r"rydberg", r"denominator", r"seed", r"2\^5", r"binary"],
    "breathing": [r"breathing", r"morphology", r"crista.?density", r"lamellar", r"tubular", r"live.?cell"],
    "trap": [r"conventional", r"molecular.?band", r"false.?positive", r"CO2", r"lipid"],
    "kappa": [r"capacitive", r"dispersion", r"kappa", r"coupling", r"permitt"],
}


def classify_query(query: str) -> dict:
    """Return intent dimensions and a suggested compass mode."""
    q = query.lower()
    dims = {k: bool(re.search(pat, q)) for k, pats in INTENT_MAP.items() for pat in ["|".join(pats)]}
    # collapse per-dimension
    collapsed = {k: any(re.search(p, q) for p in pats) for k, pats in INTENT_MAP.items()}

    # frequency extraction
    freqs = [float(x) for x in re.findall(r"(\d+\.?\d*)\s*t?hz", q)]

    mode = "score"
    if collapsed["breathing"]:
        mode = "breathing"
    elif collapsed["trap"]:
        mode = "trap_check"
    elif collapsed["kappa"]:
        mode = "kappa"
    elif len(freqs) == 3:
        mode = "score_triplet"
    elif collapsed["spacing"] or collapsed["denominator"]:
        mode = "scan"

    return {
        "query": query,
        "dimensions": collapsed,
        "extracted_frequencies_thz": freqs,
        "suggested_mode": mode,
    }


def route(query: str) -> str:
    """One-line routing decision."""
    c = classify_query(query)
    return f"mode={c['suggested_mode']} dims={[k for k,v in c['dimensions'].items() if v]} freqs={c['extracted_frequencies_thz']}"


if __name__ == "__main__":
    tests = [
        "does 71 87 103 match the cross ratio",
        "breathing spectrum tubular mitochondria",
        "is 87 a lipid C-H false positive",
        "capacitive dispersion kappa value",
        "scan denominators 25 to 45",
        "what is the Rydberg seed 2^5",
    ]
    for t in tests:
        print(route(t))