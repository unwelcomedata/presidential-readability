"""Build notebooks/03-prepare.ipynb via nbformat.

Feature stage: compute readability scores per speech (Flesch-Kincaid + companions
via textstat), build the analysis-ready `speeches_readability` table, register
provenance, and package the export (CSV/xlsx/parquet + codebook, transcript
dropped). Runs AFTER 02-clean and BEFORE 04-viz.

    .venv/bin/python scripts/_build_nb_03_prepare.py
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/03-prepare.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

PROJECT = Path(__file__).resolve().parents[1]
NB_PATH = PROJECT / "notebooks" / "03-prepare.ipynb"


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


cells = [
    md(
        """
# 03 — Prepare · presidential-readability

**Goal:** compute the project's core measurement — **readability** — for every speech, build
the analysis-ready `speeches_readability` table, and package the public export.

**Readability is computed here, not sourced** (see `SOURCES.md` → readability methodology).
Grade formulas are computed from their components with **`textstat==0.7.13`** for word /
syllable / letter counts, and **NLTK punkt (`nltk==3.10.3`) for sentence counts** — the
sentence denominator is what a naive splitter gets wrong on historical transcripts. Metrics:
- **`fk_grade`** — Flesch–Kincaid Grade Level (the **lead** metric: U.S. school grade level)
- `flesch_reading_ease` — 0–100, higher = easier
- `smog_index`, `gunning_fog`, `coleman_liau` — companion grade-level formulas (guard against
  any single formula's quirks)
- `word_count`, `sentence_count` — the raw inputs behind the grade (transparency)

**Two data-quality decisions (2026-09-26):**
1. **Score only real oratory** — SOTU series + inaugurals — dropping proclamations / veto
   messages / orders that the corpus mislabels as speeches (they score as grade-150 one-sentence
   legal texts). See the filter step below.
2. **The published chart uses the spoken era (1913+) only** — pre-1913 annual messages were
   *written documents* read by a clerk, and reading formulas stay unstable on them even after
   punkt + the oratory filter (grade-40 single-sentence inaugurals persist). The export keeps
   both eras with a `delivery_mode` flag; the chart filters to spoken.

**Export:** the analysis-ready table minus the bulky `transcript` → CSV + Excel + Parquet + codebook.
        """
    ),
    code(
        """
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path.cwd() if (Path.cwd() / "config.yaml").exists() else Path.cwd().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingest import load_config
from src.clean_quality import get_connection, register_source, save_processed, get_sources
from src.prepare import add_readability, package_dataset, READABILITY_METRICS

# Ensure the NLTK punkt sentence tokenizer is available (used by the scorer for
# reliable sentence counts — see the 2026-09-26 investigation note in prepare.py).
import nltk
for pkg in ("punkt", "punkt_tab"):
    try:
        nltk.download(pkg, quiet=True)
    except Exception:
        pass

cfg = load_config(PROJECT_ROOT / "config.yaml")
cfg["paths"] = {k: str(PROJECT_ROOT / v) for k, v in cfg["paths"].items()}
cfg["settings"]["duckdb_file"] = str(PROJECT_ROOT / cfg["settings"]["duckdb_file"])

con = get_connection(cfg)
clean = con.execute("SELECT * FROM speeches_clean").df()
print("speeches_clean (all types):", clean.shape)
print("metrics to compute:", list(READABILITY_METRICS))
        """
    ),
    md(
        """
## 1. Filter to real oratory — SOTU series + inaugural addresses

**Why this filter (2026-09-26 data-quality finding):** the raw corpus buckets many
**legal/administrative documents** (proclamations, veto messages, orders, neutrality
declarations) as generic speeches. Scored as prose, these produce absurd reading grades —
e.g. Washington's 1795 *Proclamation of Pardons* is one 382-word grammatical sentence →
grade ~150. They are documents, not delivered speeches, and don't belong on a
speech-readability chart.

So we score only **coherent, delivered oratory**: the **State-of-the-Union series**
(Annual Message + State of the Union) and **Inaugural Addresses**. Both are real speeches
with consistent form across eras, which is exactly what a readability *trend* needs.
        """
    ),
    code(
        """
oratory = clean[clean["is_sotu_series"] | (clean["speech_type"] == "Inaugural Address")].copy()
print("oratory speeches:", len(oratory), "of", len(clean))
print(oratory.groupby(["speech_type", "delivery_mode"]).size())
        """
    ),
    md(
        """
## 2. Score readability (punkt sentence counts)

`add_readability()` (in `src/prepare.py`) computes each grade formula from its components,
counting **sentences with NLTK punkt** rather than textstat's naive splitter (the naive
splitter is what let one-sentence proclamations reach grade 150). Adds one column per metric
plus `word_count` / `sentence_count`. The one compute-heavy cell.
        """
    ),
    code(
        """
feat = add_readability(oratory, text_col="transcript")

score_cols = list(READABILITY_METRICS) + ["word_count", "sentence_count"]
print("added columns:", score_cols)
feat[["president", "year", "speech_type", "delivery_mode"] + score_cols].head(5)
        """
    ),
    md(
        """
## 2. Sanity-check the scores

Distribution of the lead metric (`fk_grade`) overall and by delivery mode. We EXPECT the
written era to score higher (longer sentences, denser prose) — that's the series break, and
seeing it here confirms the pipeline is measuring what we think.
        """
    ),
    code(
        """
print("fk_grade summary (SOTU + inaugural, punkt):")
print(feat["fk_grade"].describe().round(2).to_string())
print("\\nnull fk_grade:", feat["fk_grade"].isna().sum())
print("max fk_grade:", round(feat["fk_grade"].max(), 1), "(no more grade-150 proclamation artifacts)")

print("\\nmean fk_grade by delivery_mode:")
print(feat.groupby("delivery_mode")["fk_grade"].agg(["count", "mean", "max"]).round(2).to_string())

# The published CHART uses the spoken era only (1913+): pre-1913 messages were written
# documents and reading formulas remain unstable on them. The EXPORT keeps both eras with
# the delivery_mode flag so buyers have the full data + can filter as we do.
        """
    ),
    md(
        """
## 3. Build `speeches_readability` (analysis-ready) → DuckDB + processed parquet

The analysis-ready table = clean metadata + readability scores. `04-viz` reads this.
        """
    ),
    code(
        """
# Order columns: identity/metadata first, then scores. Drop n_chars (raw QC field).
meta_cols = ["president", "speech_date", "year", "title", "speech_type",
             "is_sotu_series", "delivery_mode", "url", "source_file"]
score_cols = list(READABILITY_METRICS) + ["word_count", "sentence_count"]
readability = feat[meta_cols + score_cols + ["transcript"]].copy()

con.register("df_read", readability)
con.execute("CREATE OR REPLACE TABLE speeches_readability AS SELECT * FROM df_read")
con.unregister("df_read")
print("speeches_readability rows:", con.execute("SELECT COUNT(*) FROM speeches_readability").fetchone()[0])

# Processed parquet keeps the transcript (internal); export drops it (below).
save_processed(readability, cfg, "speeches_readability.parquet")
        """
    ),
    md(
        """
## 4. Register provenance for the derived table

`speeches_readability` is derived from the Miller Center corpus via textstat — record that
lineage (source + the exact readability method + the series break) in `_sources`.
        """
    ),
    code(
        """
register_source(
    con,
    table="speeches_readability",
    name="Derived: readability scores over Miller Center corpus",
    url="https://data.millercenter.org/miller_center_speeches.tgz",
    license="Public domain (source corpus); derived scores computed by this project",
    retrieved="2026-09-26",
    notes=(
        "Per-speech readability computed with textstat==0.7.13: fk_grade "
        "(Flesch-Kincaid Grade, lead), flesch_reading_ease, smog_index, gunning_fog, "
        "coleman_liau, plus word_count/sentence_count. Syllable counting is textstat/pyphen."
    ),
    methodology=(
        "Readability formulas were designed for WRITTEN prose; applied to transcribed "
        "SPOKEN speech they are a consistent index, not a literal grade. Scores are "
        "deterministic given the transcript + textstat version."
    ),
    series_breaks=(
        "Written (pre-1913, clerk-read documents) vs spoken (1913+, delivered oratory) "
        "delivery era — segment all readability trends at ~1913 (delivery_mode column)."
    ),
)
get_sources(con)
        """
    ),
    md(
        """
## 5. Package the export (CSV + Excel + Parquet + codebook)

Drop the `transcript` (the readability *input*, not a deliverable) and package the
analysis-ready table with a plain-English codebook for every column.
        """
    ),
    code(
        """
export_df = readability.drop(columns=["transcript"])

codebook = {
    "president": "President who delivered the speech.",
    "speech_date": "Date of the speech (YYYY-MM-DD).",
    "year": "Calendar year of the speech.",
    "title": "Speech title as given by the Miller Center.",
    "speech_type": "Institutional type (Inaugural Address, State of the Union, Annual Message, etc.).",
    "is_sotu_series": "True if part of the unified State-of-the-Union series (Annual Message <=1928 + State of the Union 1929+).",
    "delivery_mode": "'written' (pre-1913, clerk-read documents) or 'spoken' (1913+, delivered oratory) — the readability series break.",
    "url": "Miller Center source URL for the speech.",
    "source_file": "Filename of the source JSON in the corpus (provenance).",
    "fk_grade": "Flesch-Kincaid Grade Level (LEAD metric): approximate U.S. school grade required to read the text. Higher = more complex.",
    "flesch_reading_ease": "Flesch Reading Ease (0-100): higher = easier to read.",
    "smog_index": "SMOG grade-level readability formula.",
    "gunning_fog": "Gunning Fog grade-level readability formula.",
    "coleman_liau": "Coleman-Liau grade-level readability formula.",
    "word_count": "Word (lexicon) count of the transcript, per textstat.",
    "sentence_count": "Sentence count of the transcript, per textstat (the denominator in words/sentence).",
}

written = package_dataset(
    export_df, cfg, name="presidential_readability_v1",
    codebook=codebook,
    notes=(
        "Source: University of Virginia Miller Center presidential speech corpus "
        "(public domain), https://data.millercenter.org/miller_center_speeches.tgz. "
        "Readability computed with textstat==0.7.13 (Flesch-Kincaid + companions). "
        "CAVEAT: readability formulas were built for written prose; scores on transcribed "
        "spoken speech are a consistent index, not a literal grade. Segment trends at the "
        "written->spoken (~1913) delivery break. Coverage density varies sharply by era."
    ),
)
list(written.items())
        """
    ),
    md(
        """
## Cleanup

Close the DuckDB connection (single-writer).
        """
    ),
    code(
        """
con.close()
print("connection closed — prepare complete")
        """
    ),
]

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata["language_info"] = {"name": "python"}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(f"wrote {NB_PATH.relative_to(PROJECT)}  ({len(cells)} cells)")
