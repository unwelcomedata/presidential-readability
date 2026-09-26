"""Sellable dataset preparation and export utilities.

Takes a processed DataFrame and packages it for sale/distribution:
  - Drops any PII columns listed in config.yaml
  - Exports to CSV, Excel, and/or Parquet
  - Generates a plain-text codebook (column descriptions)

Usage in a notebook:
    from src.prepare import package_dataset
    package_dataset(df, cfg, name="my_dataset", codebook={"col": "description"})
"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# PII stripping
# ---------------------------------------------------------------------------

def strip_pii(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Drop columns listed under export.strip_pii_columns in config.yaml."""
    cols_to_drop = cfg.get("export", {}).get("strip_pii_columns", [])
    if cols_to_drop:
        existing = [c for c in cols_to_drop if c in df.columns]
        if existing:
            df = df.drop(columns=existing)
            print(f"Stripped PII columns: {existing}")
    return df


# ---------------------------------------------------------------------------
# Codebook
# ---------------------------------------------------------------------------

def build_codebook(
    df: pd.DataFrame,
    descriptions: dict[str, str] | None = None,
    project_name: str = "",
    notes: str = "",
) -> str:
    """Generate a plain-text codebook for the dataset.

    Args:
        df:           The export-ready DataFrame.
        descriptions: Dict mapping column name → human-readable description.
                      Columns not in the dict get a placeholder.
        project_name: Printed in the header.
        notes:        Free-text notes appended at the bottom (source info, license, etc.).

    Returns:
        Codebook as a string (written to a .md file by package_dataset).
    """
    descriptions = descriptions or {}
    today = date.today().isoformat()

    lines = [
        f"# {project_name} — Dataset Codebook",
        f"Generated: {today}",
        "",
        "## Columns",
        "",
    ]

    for col in df.columns:
        dtype = str(df[col].dtype)
        desc = descriptions.get(col, "_No description provided._")
        non_null = df[col].notna().sum()
        total = len(df)
        lines.append(f"### `{col}`")
        lines.append(f"- **Type**: `{dtype}`")
        lines.append(f"- **Non-null**: {non_null:,} / {total:,} ({non_null/total:.1%})")
        lines.append(f"- **Description**: {desc}")
        lines.append("")

    if notes:
        lines += ["## Notes", "", textwrap.dedent(notes).strip(), ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def package_dataset(
    df: pd.DataFrame,
    cfg: dict[str, Any],
    name: str,
    codebook: dict[str, str] | None = None,
    notes: str = "",
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """Strip PII, export to configured formats, and write a codebook.

    Args:
        df:       Processed DataFrame ready for packaging.
        cfg:      Loaded config dict.
        name:     Base filename (no extension).
        codebook: Column description dict passed to build_codebook().
        notes:    Free-text appended to the codebook (source, license, etc.).
        formats:  Override config export.formats. Supported: csv, xlsx, parquet.

    Returns:
        Dict of {format: Path} for every file written.
    """
    df = strip_pii(df, cfg)

    export_dir = Path(cfg["paths"]["export"])
    export_dir.mkdir(parents=True, exist_ok=True)

    export_cfg = cfg.get("export", {})
    active_formats = formats or export_cfg.get("formats", ["csv"])
    include_codebook = export_cfg.get("include_codebook", True)
    project_name = cfg.get("project_name", name)

    written: dict[str, Path] = {}

    if "csv" in active_formats:
        p = export_dir / f"{name}.csv"
        df.to_csv(p, index=False, encoding=cfg["settings"]["encoding"])
        written["csv"] = p
        print(f"Exported CSV     → {p}")

    if "xlsx" in active_formats:
        p = export_dir / f"{name}.xlsx"
        with pd.ExcelWriter(p, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        written["xlsx"] = p
        print(f"Exported Excel   → {p}")

    if "parquet" in active_formats:
        p = export_dir / f"{name}.parquet"
        df.to_parquet(p, index=False, engine=cfg["settings"]["parquet_engine"])
        written["parquet"] = p
        print(f"Exported Parquet → {p}")

    if include_codebook:
        cb_text = build_codebook(df, descriptions=codebook, project_name=project_name, notes=notes)
        cb_path = export_dir / f"{name}_codebook.md"
        cb_path.write_text(cb_text, encoding="utf-8")
        written["codebook"] = cb_path
        print(f"Wrote codebook   → {cb_path}")

    print(f"\n✓  Package complete: {len(df):,} rows × {len(df.columns)} columns")
    return written


# ---------------------------------------------------------------------------
# Quick summary helpers (useful before packaging)
# ---------------------------------------------------------------------------

def value_counts_all(df: pd.DataFrame, top_n: int = 10) -> None:
    """Print top-N value counts for every column — quick sanity check."""
    for col in df.columns:
        print(f"\n── {col} ──")
        print(df[col].value_counts(dropna=False).head(top_n).to_string())


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return describe() output for numeric columns only, transposed for readability."""
    return df.select_dtypes("number").describe().T.round(2)


# ---------------------------------------------------------------------------
# Readability scoring (this project's core measurement)
# ---------------------------------------------------------------------------
#
# Readability is COMPUTED here (not sourced), so the formula choice is a
# methodology decision documented in SOURCES.md. We use the `textstat` library
# (pinned in requirements.txt) which implements the standard formulas. The lead
# metric is Flesch-Kincaid Grade Level; companion metrics guard against any one
# formula's quirks. Syllable counting (the fuzzy step) is textstat/pyphen's.
#
# CAVEAT (carry into charts/codebook): readability formulas were built for
# WRITTEN prose. Applying them to transcribed SPOKEN speech is a consistent
# index, not a literal measure of how hard a speech sounded. Segment any trend
# at the written->spoken (~1913) delivery break.

# SENTENCE SEGMENTATION: we count sentences with NLTK's punkt tokenizer, NOT
# textstat's naive splitter. Sentence count is the denominator of words/sentence
# in every grade formula, so a bad splitter inflates grades on historical
# transcripts. (Investigation 2026-09-26 showed the naive splitter — and the raw
# corpus — produced grade-150 "speeches" that were actually one-sentence legal
# proclamations; punkt + a speech-type filter is the fix.) Syllable and word
# counts still come from textstat/pyphen.

READABILITY_METRICS = ("fk_grade", "flesch_reading_ease", "smog_index",
                       "gunning_fog", "coleman_liau")


def _punkt_sentence_count(text: str) -> int:
    """Sentence count via NLTK punkt (downloaded in the notebook/reproduce step)."""
    from nltk.tokenize import sent_tokenize
    return max(len(sent_tokenize(text)), 1)


def score_readability(text: str) -> dict[str, float]:
    """Compute readability metrics using punkt sentence counts + textstat parts.

    Grade formulas are recomputed from their components so the SENTENCE count is
    punkt's, not textstat's naive splitter:
      - fk_grade            = 0.39*(W/S) + 11.8*(Syl/W) - 15.59
      - flesch_reading_ease = 206.835 - 1.015*(W/S) - 84.6*(Syl/W)
      - gunning_fog         = 0.4*((W/S) + 100*(complex/W))
      - smog_index          = 1.043*sqrt(polysyll * 30/S) + 3.1291
      - coleman_liau        = 0.0588*(letters/W*100) - 0.296*(S/W*100) - 15.8
    W=words, S=sentences (punkt), Syl=syllables, complex/polysyll=>=3-syllable words.
    Empty text -> all None.
    """
    import math
    import textstat

    if not isinstance(text, str) or not text.strip():
        return {k: None for k in READABILITY_METRICS}

    try:
        W = max(textstat.lexicon_count(text, removepunct=True), 1)
        S = _punkt_sentence_count(text)
        Syl = textstat.syllable_count(text)
        poly = textstat.polysyllabcount(text)
        letters = textstat.letter_count(text, ignore_spaces=True)

        wps = W / S
        spw = Syl / W

        fk = 0.39 * wps + 11.8 * spw - 15.59
        ease = 206.835 - 1.015 * wps - 84.6 * spw
        fog = 0.4 * (wps + 100.0 * (poly / W))
        smog = 1.043 * math.sqrt(poly * (30.0 / S)) + 3.1291
        cli = 0.0588 * (letters / W * 100.0) - 0.296 * (S / W * 100.0) - 15.8

        return {
            "fk_grade": round(fk, 2),
            "flesch_reading_ease": round(ease, 2),
            "smog_index": round(smog, 2),
            "gunning_fog": round(fog, 2),
            "coleman_liau": round(cli, 2),
        }
    except Exception:
        return {k: None for k in READABILITY_METRICS}


def add_readability(df: pd.DataFrame, text_col: str = "transcript") -> pd.DataFrame:
    """Add one readability column per READABILITY_METRICS entry, plus counts.

    Adds fk_grade (LEAD), flesch_reading_ease, smog_index, gunning_fog,
    coleman_liau, and word_count / sentence_count (punkt) — the inputs behind the
    grade, for the codebook. Deterministic given text + textstat + punkt.
    """
    import textstat

    out = df.copy()
    scores = out[text_col].fillna("").map(score_readability).apply(pd.Series)
    for col in READABILITY_METRICS:
        out[col] = pd.to_numeric(scores[col], errors="coerce").astype("Float64")

    def _wc(t):
        return textstat.lexicon_count(t, removepunct=True) if isinstance(t, str) and t.strip() else pd.NA

    def _sc(t):
        return _punkt_sentence_count(t) if isinstance(t, str) and t.strip() else pd.NA

    out["word_count"] = out[text_col].map(_wc).astype("Int64")
    out["sentence_count"] = out[text_col].map(_sc).astype("Int64")
    return out
