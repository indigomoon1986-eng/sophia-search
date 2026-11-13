# Sophia Search

Invariant-based search engine. Ranks results by structural invariants rather than link graphs or keyword frequency, with first-class trap flags for conventional explanations.

## Architecture

- **compass.py** — LTOE heuristic compass. Scores any candidate triplet 0-1 across four checks: cross-ratio against 29/20, arithmetic-mean condition, even 16 THz spacing, Rydberg denominator proximity to 31.92. Auto-flags conventional molecular bands (CO2 asymmetric stretch at 70, lipid C-H2 at 87, O-H/N-H at 100, Walker at 36.27, glutamate C-C-C at 34.5).
- **schema.sql** — Five-table index: Spectra, Lines, Bands, Scores, Morphologies. Frequency normalized to THz. Mechanism-type column future-proofs capacitive dispersion testing.
- **query_understanding.py** — Classifies incoming queries by matching against invariant space before hitting the index. Maps user intent onto compass dimensions (cross-ratio, mean, spacing, denominator) and morphology axis (crista density, lamellar vs tubular).
- **ranker.py** — Combines compass score, trap flags, and breathing-axis centroid shift into a single ranked result with provenance.

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