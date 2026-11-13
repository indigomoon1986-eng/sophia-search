#!/usr/bin/env python3
"""Sophia escalation hook — thin API shim routing ambiguous queries to reasoning.

When query_understanding can't cleanly map a query to a compass mode,
this layer escalates to Sophia (the reasoning companion) instead of
silently returning a bad score or an empty result.

Design principles:
- Escalation is opt-in per query, not default.
- The shim passes structured context, not raw chat transcripts.
- Sophia's response is parsed back into compass-compatible output
  so the ranker never sees unstructured text.
- Every escalation is logged with provenance for audit.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from query_understanding import classify_query
from ranker import rank_query

logger = logging.getLogger("sophia_search.escalation")


@dataclass
class EscalationContext:
    """Structured payload passed to Sophia on escalation."""
    query: str
    classification: dict
    attempted_mode: str
    extracted_frequencies: list[float]
    compass_dimensions_active: list[str]
    timestamp: str
    session_id: Optional[str] = None

    def to_prompt(self) -> str:
        """Render as instructions for Sophia, not a chat transcript."""
        dims = ", ".join(self.compass_dimensions_active) or "none"
        freqs = ", ".join(str(f) for f in self.extracted_frequencies) or "none"
        return (
            f"Query: {self.query}\n"
            f"Classification flagged mode '{self.attempted_mode}' "
            f"but no executable action matched.\n"
            f"Active compass dimensions: {dims}.\n"
            f"Extracted frequencies (THz): {freqs}.\n"
            f"Respond with ONE of:\n"
            f"1. A JSON object: {{"action": "score_triplet", "frequencies": [a, b, c]}}\n"
            f"2. A JSON object: {{"action": "scan", "low_d": x, "high_d": y}}\n"
            f"3. A JSON object: {{"action": "breathing", "density_shift": z}}\n"
            f"4. A JSON object: {{"action": "trap_check", "frequencies": [f, ...]}}\n"
            f"5. A JSON object: {{"action": "clarify", "question": "..."}} if the query is genuinely underspecified.\n"
            f"Do not add commentary outside the JSON."
        )


@dataclass
class EscalationLog:
    """Audit record for one escalation round-trip."""
    context: EscalationContext
    sophia_raw_response: str
    parsed_action: Optional[dict]
    parse_error: Optional[str]
    resolved: bool
    latency_ms: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["context"] = asdict(self.context)
        return d


# Type for the Sophia caller — injected at runtime so this module
# stays testable without a live model.
SophiaCaller = Callable[[str], str]


def _default_sophia_caller(prompt: str) -> str:
    """Placeholder. Wire to the real Sophia endpoint before production use.
    Raises if called unconfigured so silent fallback never happens.
    """
    raise RuntimeError(
        "Sophia caller not configured. Inject a real endpoint via "
        "set_sophia_caller() before enabling escalation."
    )


_SOPHIA_CALLER: SophiaCaller = _default_sophia_caller
_ESCALATION_LOG: list[EscalationLog] = []


def set_sophia_caller(caller: SophiaCaller) -> None:
    """Inject the real Sophia endpoint."""
    global _SOPHIA_CALLER
    _SOPHIA_CALLER = caller


def _parse_sophia_response(raw: str) -> Optional[dict]:
    """Extract the first JSON object from Sophia's reply."""
    raw = raw.strip()
    # direct parse
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "action" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    # find first {-braced block
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict) and "action" in obj:
                return obj
        except json.JSONDecodeError:
            return None
    return None


def _dispatch_action(action: dict) -> dict:
    """Run a Sophia-emitted action through the local compass pipeline."""
    name = action.get("action")
    if name == "score_triplet":
        freqs = sorted(action["frequencies"])
        if len(freqs) != 3:
            return {"error": "score_triplet requires exactly 3 frequencies"}
        from ranker import rank_triplet
        return rank_triplet(*freqs, provenance="sophia_escalation")
    if name == "scan":
        from compass import scan_denominators
        lo = float(action.get("low_d", 20.0))
        hi = float(action.get("high_d", 60.0))
        return {"scan_results": scan_denominators(lo, hi)}
    if name == "breathing":
        from compass import breathing
        return breathing(float(action.get("density_shift", 0.0)))
    if name == "trap_check":
        from compass import trap_flags
        freqs = action["frequencies"]
        return {"frequencies": freqs, "traps": trap_flags(freqs)}
    if name == "clarify":
        return {"clarification_needed": action.get("question", "unspecified")}
    return {"error": f"unknown action: {name}"}


def maybe_escalate(query: str, session_id: Optional[str] = None,
                   force: bool = False) -> dict:
    """Main entry: try local routing first; escalate to Sophia only if
    the query is ambiguous or force=True.
    """
    classification = classify_query(query)
    mode = classification["suggested_mode"]

    # Local path: mode maps to something executable
    if mode != "score" or force:
        if not force:
            local = rank_query(query)
            if local.get("result") is not None:
                return {"source": "local", "classification": classification,
                        "result": local["result"]}

    # Escalation path
    ctx = EscalationContext(
        query=query,
        classification=classification,
        attempted_mode=mode,
        extracted_frequencies=classification["extracted_frequencies_thz"],
        compass_dimensions_active=[k for k, v in classification["dimensions"].items() if v],
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
    )

    t0 = datetime.now(timezone.utc)
    try:
        raw = _SOPHIA_CALLER(ctx.to_prompt())
    except Exception as e:
        log = EscalationLog(context=ctx, sophia_raw_response="",
                            parsed_action=None, parse_error=str(e),
                            resolved=False)
        _ESCALATION_LOG.append(log)
        logger.warning("Sophia escalation failed: %s", e)
        return {"source": "escalation_failed", "classification": classification,
                "error": str(e), "fallback": "local_rank_attempted"}

    latency = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
    parsed = _parse_sophia_response(raw)
    if parsed is None:
        log = EscalationLog(context=ctx, sophia_raw_response=raw,
                            parsed_action=None,
                            parse_error="no JSON action object found",
                            resolved=False, latency_ms=latency)
        _ESCALATION_LOG.append(log)
        return {"source": "escalation_unparseable", "classification": classification,
                "raw": raw[:500], "latency_ms": latency}

    result = _dispatch_action(parsed)
    log = EscalationLog(context=ctx, sophia_raw_response=raw,
                        parsed_action=parsed, parse_error=None,
                        resolved=True, latency_ms=latency)
    _ESCALATION_LOG.append(log)
    return {"source": "sophia", "classification": classification,
            "sophia_action": parsed, "result": result, "latency_ms": latency}


def get_escalation_log() -> list[dict]:
    """Return audit trail."""
    return [e.to_dict() for e in _ESCALATION_LOG]


if __name__ == "__main__":
    # Dry-run: local routing only, no live Sophia call
    for q in ["score 71 87 103", "what does the breathing axis predict for stressed cells",
              "random philosophical question about invariants"]: 
        print(json.dumps(maybe_escalate(q), indent=2, default=str)[:600])
        print("---")
