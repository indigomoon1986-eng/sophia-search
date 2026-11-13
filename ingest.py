#!/usr/bin/env python3
"""Store DOI references and normalized spectra in the Sophia Search index."""

from __future__ import annotations
import json
import math
import sqlite3
from itertools import combinations
from pathlib import Path

from compass import score_triplet


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the index and seed its reference bands from schema.sql."""
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    connection.executescript(schema)


def _number(value: object, name: str, *, positive: bool = False,
            non_negative: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if (positive and number <= 0) or (non_negative and number < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
    return number


def _line_values(value: object, count: int, name: str) -> list:
    if isinstance(value, (list, tuple)):
        if len(value) != count:
            raise ValueError(f"{name} must have one value per frequency")
        return list(value)
    return [value] * count


def ingest(source: str | list[float], connection: sqlite3.Connection, *,
           frequency_unit: str = "THz", metadata: dict | None = None) -> dict:
    """Ingest a DOI or frequency list into an initialized SQLite index.

    A DOI is stored as a reference only; no external lookup is performed.
    For more than three lines, all triplets are scored and the best is returned.
    """
    metadata = dict(metadata or {})
    allowed = {"sample_type", "live_or_dried", "temperature_k", "intensity",
               "claimed_assignment", "crista_density_per_micron",
               "lamellar_vs_tubular", "lumen_width_nm", "kappa_sensitivity_note"}
    unknown = metadata.keys() - allowed
    if unknown:
        raise ValueError(f"unknown metadata fields: {', '.join(sorted(unknown))}")

    units = {"hz": 1e-12, "khz": 1e-9, "mhz": 1e-6, "ghz": 1e-3, "thz": 1.0}
    if not isinstance(frequency_unit, str) or frequency_unit.lower() not in units:
        raise ValueError("frequency_unit must be Hz, kHz, MHz, GHz, or THz")
    if isinstance(source, str):
        if not source.strip():
            raise ValueError("DOI must not be empty")
        doi, raw = source.strip(), []
    elif isinstance(source, (list, tuple)):
        doi, raw = None, [_number(value, "frequency", positive=True) for value in source]
    else:
        raise ValueError("source must be a DOI string or a frequency list")
    frequencies = [value * units[frequency_unit.lower()] for value in raw]
    if any(not math.isfinite(value) or value <= 0 or
           not math.isfinite(3280.0 / value) for value in frequencies):
        raise ValueError("normalized frequencies must be finite and positive")

    sample_type = metadata.get("sample_type", "unknown")
    condition = metadata.get("live_or_dried", "unknown")
    if not isinstance(sample_type, str) or not sample_type.strip():
        raise ValueError("sample_type must be a non-empty string")
    if condition not in ("live", "dried", "unknown"):
        raise ValueError("live_or_dried must be live or dried")
    temperature = metadata.get("temperature_k")
    if temperature is not None:
        temperature = _number(temperature, "temperature_k")
    intensities = _line_values(metadata.get("intensity"), len(raw), "intensity")
    intensities = [None if value is None else _number(value, "intensity", non_negative=False)
                   for value in intensities]
    assignments = _line_values(metadata.get("claimed_assignment"), len(raw),
                               "claimed_assignment")
    if any(value is not None and not isinstance(value, str) for value in assignments):
        raise ValueError("claimed_assignment must contain strings")
    density = metadata.get("crista_density_per_micron")
    width = metadata.get("lumen_width_nm")
    density = None if density is None else _number(density, "crista_density_per_micron")
    width = None if width is None else _number(width, "lumen_width_nm")
    morphology = metadata.get("lamellar_vs_tubular")
    if morphology not in (None, "lamellar", "tubular"):
        raise ValueError("lamellar_vs_tubular must be lamellar or tubular")
    kappa = metadata.get("kappa_sensitivity_note")
    if kappa is not None and not isinstance(kappa, str):
        raise ValueError("kappa_sensitivity_note must be a string")

    connection.execute("SAVEPOINT ingest_spectrum")
    try:
        cursor = connection.execute(
            "INSERT INTO spectra (paper_doi, sample_type, condition, temperature_k, "
            "freq_unit, raw_frequencies) VALUES (?, ?, ?, ?, 'THz', ?)",
            (doi, sample_type, condition, temperature, json.dumps(raw)))
        spectrum_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO lines (spectrum_id, frequency_thz, intensity, author_assignment) "
            "VALUES (?, ?, ?, ?)",
            [(spectrum_id, frequency, intensity, assignment)
             for frequency, intensity, assignment in zip(frequencies, intensities, assignments)])
        matches = connection.execute(
            "SELECT l.line_id, l.frequency_thz, b.name, b.center_thz, b.tolerance_thz "
            "FROM lines l LEFT JOIN bands b ON ABS(l.frequency_thz - b.center_thz) "
            "<= b.tolerance_thz AND (b.category IS NULL OR b.category != 'fudan') "
            "WHERE l.spectrum_id = ? ORDER BY l.line_id, b.band_id", (spectrum_id,)).fetchall()
        line_flags = {}
        for line_id, frequency, name, center, tolerance in matches:
            line_flags.setdefault(line_id, [])
            if name is not None:
                line_flags[line_id].append(
                    f"{frequency} THz within {tolerance} of {name} ({center} THz)")
        traps = [flag for flags in line_flags.values() for flag in flags]
        lines = list(zip(frequencies, line_flags.values()))
        scores = []
        for triplet in combinations(lines, 3):
            ordered = sorted(triplet, key=lambda line: line[0])
            score = score_triplet(*(line[0] for line in ordered))
            numbers = [score["score"], score["cross_ratio"], score["mean_error_thz"],
                       *score["gaps_thz"], *score["rydberg_denominators"]]
            if any(value is not None and not math.isfinite(value) for value in numbers):
                raise ValueError("frequencies produce a non-finite score")
            score["trap_flags"] = [flag for line in ordered for flag in line[1]]
            connection.execute(
                "INSERT INTO scores (spectrum_id, compass_score, cross_ratio, mean_error_thz, "
                "gaps_thz, rydberg_denominators, trap_flags, kappa_sensitivity) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (spectrum_id, score["score"], score["cross_ratio"], score["mean_error_thz"],
                 json.dumps(score["gaps_thz"]), json.dumps(score["rydberg_denominators"]),
                 json.dumps(score["trap_flags"]), kappa))
            scores.append(score)

        morph_id = None
        if any(value is not None for value in (density, morphology, width)):
            cursor = connection.execute(
                "INSERT INTO morphologies (spectrum_id, crista_density_per_micron, "
                "morphology, lumen_width_nm) VALUES (?, ?, ?, ?)",
                (spectrum_id, density, morphology, width))
            morph_id = cursor.lastrowid
        connection.execute("RELEASE SAVEPOINT ingest_spectrum")
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT ingest_spectrum")
        connection.execute("RELEASE SAVEPOINT ingest_spectrum")
        raise

    return {"spectrum_id": spectrum_id,
            "score": max(scores, key=lambda score: score["score"]) if scores else None,
            "traps": traps, "morphology_id": morph_id}
