#!/usr/bin/env python
"""Reproduce the presidential-readability published dataset from the raw source.

Serious-tier reproducibility entrypoint: a single command that goes from the raw
Miller Center speech corpus all the way to the published export in ``export/``
(``presidential_readability_v1`` CSV + codebook). It runs the exact same ``src/``
logic the notebooks use, in the documented pipeline order (ingest -> clean ->
prepare), and is fully standalone (it does NOT execute the notebooks).

What it does, in order:
  1. INGEST  — download + unpack the Miller Center corpus tgz into data/raw/ and
               load it into DuckDB as ``speeches_raw`` (cached; skips re-download
               if a fresh copy exists).
  2. CLEAN   — parse the date (dropping the source's bogus fixed offset), classify
               speech_type / is_sotu_series / delivery_mode, strip HTML tags +
               collapse whitespace in the transcript, dedupe -> ``speeches_clean``.
  3. PREPARE — filter to real oratory (SOTU series + inaugurals), score readability
               (Flesch-Kincaid + companions, sentences via NLTK punkt) ->
               ``speeches_readability`` and package the export (CSV + Excel +
               Parquet + codebook).

Usage:
    python scripts/reproduce.py                 # full run: raw -> export
    python scripts/reproduce.py --db /tmp/x.duckdb --export-dir /tmp/exp  # scratch run

Prerequisites:
  - Python 3.11+ with the packages in requirements.txt (textstat + nltk).
  - The NLTK punkt tokenizer (this script downloads it if missing).
  - Network access on the first run (to fetch the Miller Center tgz). Subsequent
    runs reuse the cached archive in data/raw/.

Verify afterwards with:  python scripts/validate_charts.py
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from src.ingest import load_config, ingest_miller_center  # noqa: E402
from src.clean_quality import (  # noqa: E402
    get_connection, register_source, save_interim,
    classify_speech_type, sotu_series, delivery_mode,
)
from src.prepare import add_readability, package_dataset, READABILITY_METRICS  # noqa: E402

# Transcript cleaning (mirrors 02-clean exactly).
_WS = re.compile(r"\s+")
_BLOCK_TAG = re.compile(r"(?i)<\s*(br|/p|/div|/li|/h[1-6])\s*/?\s*>")
_ANY_TAG = re.compile(r"<[^>]+>")


def _clean_text(t: str) -> str:
    if not isinstance(t, str) or not t:
        return ""
    t = html.unescape(t).replace("\u2019", "'")
    t = _BLOCK_TAG.sub(". ", t)   # paragraph/line breaks -> sentence boundary
    t = _ANY_TAG.sub(" ", t)       # drop remaining inline tags
    t = _WS.sub(" ", t)
    t = re.sub(r"(\.\s*){2,}", ". ", t)
    return t.strip()


CODEBOOK = {
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
    "sentence_count": "Sentence count of the transcript, per NLTK punkt (the denominator in words/sentence).",
}

NOTES = (
    "Source: University of Virginia Miller Center presidential speech corpus (public domain), "
    "https://data.millercenter.org/miller_center_speeches.tgz. Readability computed with "
    "textstat==0.7.13 (Flesch-Kincaid + companions), sentence counts via NLTK punkt. "
    "SCORED SET = real oratory only (State-of-the-Union series + inaugural addresses); "
    "proclamations/veto messages/orders are excluded (they score as one-sentence legal texts). "
    "CAVEAT: readability formulas were built for written prose; scores on transcribed spoken "
    "speech are a consistent index, not a literal grade. The published CHARTS use the spoken "
    "era (1913+) only — pre-1913 messages were written documents and the formulas are unstable "
    "on them; this export keeps both eras with the delivery_mode flag. Absolute levels are "
    "tokenizer/source-dependent (independent series run 2-5 grades lower); the decline replicates. "
    "See SOURCES.md for full methodology and series breaks."
)


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _ensure_punkt() -> None:
    import nltk
    for pkg in ("punkt", "punkt_tab"):
        try:
            nltk.download(pkg, quiet=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. INGEST
# ---------------------------------------------------------------------------

def step_ingest(cfg: dict, con) -> None:
    df = ingest_miller_center(cfg)
    con.register("df_raw", df)
    con.execute("CREATE OR REPLACE TABLE speeches_raw AS SELECT * FROM df_raw")
    con.unregister("df_raw")
    register_source(
        con, table="speeches_raw",
        name="Miller Center Presidential Speech Corpus (UVA)",
        url="https://data.millercenter.org/miller_center_speeches.tgz",
        license="Public domain (U.S. government works)", retrieved="2026-09-26",
        notes="Curated bulk corpus of major presidential speeches, one JSON per speech.",
        methodology="Editorial curation; readability computed downstream, not a source field.",
        series_breaks="Written (pre-1913) vs spoken (1913+) delivery era; coverage density varies by era.",
    )
    print(f"speeches_raw: {len(df):,} speeches, {df['president'].nunique()} presidents")


# ---------------------------------------------------------------------------
# 2. CLEAN
# ---------------------------------------------------------------------------

def step_clean(cfg: dict, con) -> None:
    raw = con.execute("SELECT * FROM speeches_raw").df()

    date_part = raw["date"].astype(str).str.slice(0, 10)
    sd = pd.to_datetime(date_part, errors="coerce", format="%Y-%m-%d")
    raw["speech_date"] = sd.dt.date.astype("string")
    raw["year"] = sd.dt.year.astype("Int64")

    raw["speech_type"] = raw["title"].fillna("").map(classify_speech_type)
    raw["is_sotu_series"] = raw["speech_type"].map(sotu_series)
    raw["delivery_mode"] = raw["year"].map(lambda y: delivery_mode(None if pd.isna(y) else int(y)))

    raw["transcript"] = raw["transcript"].map(_clean_text)
    raw["president"] = raw["president"].astype("string").str.strip()
    raw["title"] = raw["title"].astype("string").str.strip()
    raw["n_chars"] = raw["transcript"].str.len()

    keep = ["president", "speech_date", "year", "title", "speech_type",
            "is_sotu_series", "delivery_mode", "transcript", "n_chars", "url", "source_file"]
    clean = raw[keep].drop_duplicates(subset=["president", "speech_date", "title", "transcript"])
    clean = clean[(clean["n_chars"] > 0) & (clean["year"].notna())].reset_index(drop=True)

    save_interim(clean, cfg, "speeches_clean.parquet")
    con.register("df_clean", clean)
    con.execute("CREATE OR REPLACE TABLE speeches_clean AS SELECT * FROM df_clean")
    con.unregister("df_clean")
    print(f"speeches_clean: {len(clean):,} speeches")


# ---------------------------------------------------------------------------
# 3. PREPARE
# ---------------------------------------------------------------------------

def step_prepare(cfg: dict, con) -> None:
    clean = con.execute("SELECT * FROM speeches_clean").df()
    oratory = clean[clean["is_sotu_series"] | (clean["speech_type"] == "Inaugural Address")].copy()
    print(f"oratory (SOTU + inaugural): {len(oratory):,} of {len(clean):,}")

    feat = add_readability(oratory, text_col="transcript")

    meta = ["president", "speech_date", "year", "title", "speech_type",
            "is_sotu_series", "delivery_mode", "url", "source_file"]
    score = list(READABILITY_METRICS) + ["word_count", "sentence_count"]
    readability = feat[meta + score + ["transcript"]].copy()

    con.register("df_read", readability)
    con.execute("CREATE OR REPLACE TABLE speeches_readability AS SELECT * FROM df_read")
    con.unregister("df_read")
    register_source(
        con, table="speeches_readability",
        name="Derived: readability scores over Miller Center corpus",
        url="https://data.millercenter.org/miller_center_speeches.tgz",
        license="Public domain (source); derived scores computed by this project",
        retrieved="2026-09-26",
        notes="Per-speech readability via textstat==0.7.13 + NLTK punkt sentence counts. Oratory only.",
        methodology="Grade formulas recomputed from components; punkt sentence counts.",
        series_breaks="Charts use spoken era (1913+); export keeps both via delivery_mode.",
    )

    export_df = readability.drop(columns=["transcript"])
    package_dataset(export_df, cfg, name="presidential_readability_v1",
                    codebook=CODEBOOK, notes=NOTES)
    print(f"exported: presidential_readability_v1 ({len(export_df):,} rows)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Reproduce the raw->export pipeline (standalone).")
    ap.add_argument("--db", default=None, help="DuckDB path (default: config settings.duckdb_file)")
    ap.add_argument("--export-dir", default=None, help="export dir (default: export/)")
    args = ap.parse_args()

    cfg = load_config("config.yaml")
    if args.db:
        cfg.setdefault("settings", {})["duckdb_file"] = args.db
    if args.export_dir:
        cfg.setdefault("paths", {})["export"] = args.export_dir

    _ensure_punkt()
    con = get_connection(cfg)
    try:
        _rule("1. INGEST — Miller Center corpus -> speeches_raw")
        step_ingest(cfg, con)
        _rule("2. CLEAN — parse/classify/strip-HTML -> speeches_clean")
        step_clean(cfg, con)
        _rule("3. PREPARE — oratory filter + readability scoring -> export")
        step_prepare(cfg, con)
    finally:
        con.close()

    print("\nPipeline complete. Export written to export/.")
    print("Verify with: python scripts/validate_charts.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
