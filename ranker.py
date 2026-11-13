#!/usr/bin/env python3
"""Ranking engine: compass score + trap flags + breathing axis -> ranked results with provenance."""

from __future__ import annotations
import json
from compass import score_triplet, breathing
from query_understanding import classify_query


def rank_triplet(low: float, mid: float, high: float, provenance: str = "") -> dict:
    s = score_triplet(low, mid, high)
    s["provenance"] = provenance or f"manual input {low},{mid},{high}"
    s["frequencies_thz"] = [low, mid, high]
    # breathing context at current density
    s["breathing_at_rest"] = breathing(0.0)
    return s


def rank_query(query: str) -> dict:
    """Full pipeline: understand -> score -> rank."""
    c = classify_query(query)
    mode = c["suggested_mode"]
    freqs = c["extracted_frequencies_thz"]

    if mode == "score_triplet" and len(freqs) == 3:
        freqs = sorted(freqs)
        return {"classification": c, "result": rank_triplet(*freqs, provenance=f"query: {query}")}

    if mode == "breathing":
        # default: compare tubular vs lamellar vs rest
        return {"classification": c,
                "result": {"rest": breathing(0.0), "tubular": breathing(-0.35), "lamellar": breathing(0.35)}}

    if mode == "trap_check" and freqs:
        from compass import trap_flags
        return {"classification": c, "result": {"frequencies": freqs, "traps": trap_flags(freqs)}}

    if mode == "scan":
        from compass import scan_denominators
        # parse range if present
        import re
        m = re.findall(r"(\d+\.?\d*)\s*to\s*(\d+\.?\d*)", query)
        lo, hi = (float(m[0][0]), float(m[0][1])) if m else (20.0, 60.0)
        return {"classification": c, "result": scan_denominators(lo, hi)}

    return {"classification": c, "result": None, "note": "no executable mode; query did not map to compass action"}


if __name__ == "__main__":
    for q in ["score 71 87 103", "breathing mode", "scan 30 to 40", "is 87 lipid"]: 
        print(json.dumps(rank_query(q), indent=2)[:500])
        print("---")