# Sophia Search

Invariant-based search engine. Ranks results by structural invariants rather than link graphs or keyword frequency, with first-class trap flags for conventional explanations.

## Architecture

- **compass.py** — LTOE heuristic compass. Scores any candidate triplet 0-1 across four checks: cross-ratio against 29/20, arithmetic-mean condition, even 16 THz spacing, Rydberg denominator proximity to 31.92. Auto-flags conventional molecular bands (CO2 asymmetric stretch at 70, lipid C-H2 at 87, O-H/N-H at 100, Walker at 36.27, glutamate C-C-C at 34.5).
- **schema.sql** — Five-table index: Spectra, Lines, Bands, Scores, Morphologies. Frequency normalized to THz. Mechanism-type column future-proofs capacitive dispersion testing.
- **query_understanding.py** — Classifies incoming queries by matching against invariant space before hitting the index. Maps user intent onto compass dimensions (cross-ratio, mean, spacing, denominator) and morphology axis (crista density, lamellar vs tubular).
- **ranker.py** — Combines compass score, trap flags, and breathing-axis centroid shift into a single ranked result with provenance.
- **ingest.py** — Stores DOI references and normalized spectra in a SQLite index, matches conventional bands, and scores frequency triplets.

## Ingest

Initialize a SQLite connection with `initialize_database` before calling `ingest`:

```python
import sqlite3
from ingest import ingest, initialize_database

db = sqlite3.connect("sophia.db")
initialize_database(db)
result = ingest([71000, 87000, 103000], db, frequency_unit="GHz", metadata={
    "sample_type": "tissue", "live_or_dried": "live",
    "crista_density_per_micron": 4.2, "lamellar_vs_tubular": "tubular",
})
```

The source is a frequency list or a DOI string. DOI-only ingest stores a reference;
it does not fetch paper data. Missing sample type and condition are stored as
`unknown`. Units can be Hz, kHz, MHz, GHz, or THz (the default): raw input values
are retained in `spectra.raw_frequencies`, while line frequencies are stored in THz.

Optional metadata keys are `sample_type`, `live_or_dried` (`live` or `dried`),
`temperature_k`, `intensity`, `claimed_assignment`, `crista_density_per_micron`,
`lamellar_vs_tubular` (`lamellar` or `tubular`), `lumen_width_nm`, and
`kappa_sensitivity_note`. Intensity and assignment may be scalars applied to all
lines or lists aligned with the input frequencies.

The result contains `spectrum_id`, `score`, `traps`, and `morphology_id`.
All three-line combinations are scored and stored; `score` is the highest-scoring
triplet, or `None` when fewer than three lines are provided. `traps` covers all
lines using the database's non-Fudan band tolerances, while each stored score's
flags cover its own triplet. The compass score itself uses the existing compass
band constants. Ingest is atomic and respects an existing caller transaction;
otherwise it commits on success. Schema initialization uses `executescript` and
should be called outside an active transaction.

## What Survived Audit

- Cross-ratio 103/71 vs 29/20 at 0.05% error
- 87 as arithmetic mean of 103 and 71 at 0.00% error
- Even 16 THz spacing (signature of any weakly coupled 3-mode chain)
- Rydberg/31.92 at 0.19% (corrected from initial 0.004% claim)

## What Failed

- Curvature-sourced frequency generation: energy density overshot 13 orders, entropy density 10 billion, vacuum cutoff exceeded cell scale
- Capacitive dispersion kappa from real membrane physics: 0.008-0.40, cannot reach 7/3 or reproduce spacing
- 7/3 coupling only appears at 290 nm ridge spacing — outside biology
- 4.22 micron pi-signature was wavelength/2pi artifact, not membrane geometry

## Status

Pattern language with one real convergence (derived triplet matches independent FT-IR detection). Not yet a physics. Treat as heuristic compass, not derivation engine.

## Next

- Ingest published THz bio-spectroscopy datasets
- Test breathing-axis predictions against live-cell imaging
- Pre-register compass as scoring rule before new experimental results land