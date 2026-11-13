-- Sophia Search index schema
-- Five tables: Spectra, Lines, Bands, Scores, Morphologies

CREATE TABLE IF NOT EXISTS spectra (
    spectrum_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_doi       TEXT,
    sample_type     TEXT NOT NULL,          -- cell_line, tissue, isolated_mitochondria
    condition       TEXT NOT NULL,          -- live, dried
    temperature_k   REAL,
    freq_unit       TEXT DEFAULT 'THz',     -- normalized to THz
    raw_frequencies TEXT,                   -- JSON array of raw values pre-normalization
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lines (
    line_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    spectrum_id     INTEGER NOT NULL REFERENCES spectra(spectrum_id),
    frequency_thz   REAL NOT NULL,
    intensity       REAL,
    author_assignment TEXT,
    FOREIGN KEY (spectrum_id) REFERENCES spectra(spectrum_id)
);

CREATE TABLE IF NOT EXISTS bands (
    band_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    center_thz      REAL NOT NULL,
    tolerance_thz   REAL NOT NULL DEFAULT 1.0,
    category        TEXT                    -- molecular, bio_scale, walker, fudan
);

CREATE TABLE IF NOT EXISTS scores (
    score_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    spectrum_id     INTEGER NOT NULL REFERENCES spectra(spectrum_id),
    compass_score   REAL,
    cross_ratio     REAL,
    mean_error_thz  REAL,
    gaps_thz        TEXT,                   -- JSON array
    rydberg_denominators TEXT,              -- JSON array
    trap_flags      TEXT,                   -- JSON array
    kappa_sensitivity TEXT,                 -- capacitive dispersion result if tested
    mechanism_type  TEXT,                   -- future-proofs dispersion testing
    scored_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (spectrum_id) REFERENCES spectra(spectrum_id)
);

CREATE TABLE IF NOT EXISTS morphologies (
    morph_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    spectrum_id     INTEGER REFERENCES spectra(spectrum_id),
    crista_density_per_micron REAL,
    morphology      TEXT,                   -- lamellar, tubular, globular
    lumen_width_nm  REAL,
    ridge_spacing_nm REAL,
    notes           TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_lines_freq ON lines(frequency_thz);
CREATE INDEX IF NOT EXISTS idx_scores_score ON scores(compass_score DESC);
CREATE INDEX IF NOT EXISTS idx_morph_density ON morphologies(crista_density_per_micron);

-- Seed conventional bands
INSERT OR IGNORE INTO bands (name, center_thz, tolerance_thz, category) VALUES
    ('CO2_asymmetric_stretch', 70.0, 1.0, 'molecular'),
    ('lipid_CH2', 87.0, 1.0, 'molecular'),
    ('OH_NH_stretch', 100.0, 1.0, 'molecular'),
    ('Walker_membrane_potential', 36.27, 1.0, 'walker'),
    ('glutamate_CCC', 34.5, 1.0, 'bio_scale'),
    ('Fudan_71', 71.0, 1.0, 'fudan'),
    ('Fudan_87', 87.0, 1.0, 'fudan'),
    ('Fudan_103', 103.0, 1.0, 'fudan);

-- Example queries (commented)
-- Ranking: SELECT s.spectrum_id, s.paper_doi, sc.compass_score, sc.trap_flags
--          FROM scores sc JOIN spectra s ON sc.spectrum_id = s.spectrum_id
--          ORDER BY sc.compass_score DESC;
-- Trap matching: SELECT * FROM scores WHERE trap_flags LIKE '%CO2%';
-- Morphology centroid: SELECT m.morphology, m.crista_density_per_micron, sc.compass_score
--                     FROM morphologies m JOIN scores sc ON m.spectrum_id = sc.spectrum_id;