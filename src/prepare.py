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

# Metric name -> textstat function name. Kept explicit so the codebook can state
# exactly what each column is and which formula produced it.
READABILITY_METRICS = {
    "fk_grade": "flesch_kincaid_grade",        # LEAD: U.S. school grade level
    "flesch_reading_ease": "flesch_reading_ease",  # 0-100, higher = easier
    "smog_index": "smog_index",                # grade level (SMOG)
    "gunning_fog": "gunning_fog",              # grade level (Gunning Fog)
    "coleman_liau": "coleman_liau_index",      # grade level (Coleman-Liau)
}


def score_readability(text: str) -> dict[str, float]:
    """Compute the readability metrics for one text via textstat.

    Returns a dict keyed by READABILITY_METRICS names. Empty/whitespace text
    yields all-None (can't score). Any per-metric failure yields None for that
    metric rather than aborting the row.
    """
    import textstat

    if not isinstance(text, str) or not text.strip():
        return {k: None for k in READABILITY_METRICS}

    out: dict[str, float] = {}
    for name, fn_name in READABILITY_METRICS.items():
        try:
            out[name] = round(float(getattr(textstat, fn_name)(text)), 2)
        except Exception:
            out[name] = None
    return out


def add_readability(df: pd.DataFrame, text_col: str = "transcript") -> pd.DataFrame:
    """Add one readability column per READABILITY_METRICS entry, plus counts.

    Adds: fk_grade, flesch_reading_ease, smog_index, gunning_fog, coleman_liau,
    and word_count / sentence_count (via textstat, so the codebook can report the
    inputs behind the grade). Deterministic given the text + textstat version.
    """
    import textstat

    out = df.copy()
    scores = out[text_col].fillna("").map(score_readability).apply(pd.Series)
    for col in READABILITY_METRICS:
        out[col] = pd.to_numeric(scores[col], errors="coerce").astype("Float64")

    # Report the raw inputs behind the grade (transparency for the codebook).
    def _wc(t):
        return textstat.lexicon_count(t, removepunct=True) if isinstance(t, str) and t.strip() else pd.NA

    def _sc(t):
        return textstat.sentence_count(t) if isinstance(t, str) and t.strip() else pd.NA

    out["word_count"] = out[text_col].map(_wc).astype("Int64")
    out["sentence_count"] = out[text_col].map(_sc).astype("Int64")
    return out
