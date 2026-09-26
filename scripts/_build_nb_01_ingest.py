"""Build notebooks/01-ingest.ipynb via nbformat.

The notebook is the canonical record of the project (workspace norm): every step
is a visible code cell plus a markdown cell explaining what happened and why.
This builder keeps the notebook reproducible — re-run it to regenerate 01-ingest.

Run from the project root:
    .venv/bin/python scripts/_build_nb_01_ingest.py
then execute:
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/01-ingest.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

PROJECT = Path(__file__).resolve().parents[1]
NB_PATH = PROJECT / "notebooks" / "01-ingest.ipynb"


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


cells = [
    md(
        """
# 01 — Ingest · presidential-readability

**Goal of this notebook:** pull the raw speech corpus into DuckDB, untouched, so the
readability pipeline downstream (`02-clean` → `03-prepare`) has a clean starting point.

**Source (see `SOURCES.md` + `config.yaml`):** the University of Virginia **Miller
Center** curated presidential speech corpus — a single public-domain bulk `.tgz` that
expands to `speeches/*.json` (one speech per file: `transcript`, `date`, `president`,
`title`, …). This is the **same corpus** as the shipped `presidential-speeches` project;
we re-use it here to answer a *different* question — **how the reading-grade level of
presidential speeches has changed 1789 → present.**

**What ingest does NOT do:** no cleaning, no readability scoring, no derived columns —
raw only. Date parsing, speech-type classification, and readability computation happen in
`02-clean` and `03-prepare`.

**No API key / auth required** — it's an open bulk download. A polite rate limit
(`rate_limit_seconds: 2.0` in `config.yaml`) applies, and the `.tgz` is cached in
`data/raw/` so re-runs don't re-download.
        """
    ),
    code(
        """
import sys
from pathlib import Path

# Make src/ importable when running from notebooks/ or project root.
PROJECT_ROOT = Path.cwd() if (Path.cwd() / "config.yaml").exists() else Path.cwd().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingest import load_config, ingest_miller_center
from src.clean_quality import get_connection, register_source, get_sources

cfg = load_config(PROJECT_ROOT / "config.yaml")
cfg["paths"] = {k: str(PROJECT_ROOT / v) for k, v in cfg["paths"].items()}
cfg["settings"]["duckdb_file"] = str(PROJECT_ROOT / cfg["settings"]["duckdb_file"])
print("project:", cfg["project_name"])
        """
    ),
    md(
        """
## Download + unpack the Miller Center archive

`ingest_miller_center()` (in `src/ingest.py`, re-used from the sibling project):
1. downloads the `.tgz` to `data/raw/miller_center_speeches.tgz` (cached),
2. extracts `speeches/*.json` **verbatim** into `data/raw/speeches/` (path-traversal guarded),
3. reads every JSON into one row-per-speech DataFrame.

The returned frame is unmodified source content plus a `source_file` provenance column.
        """
    ),
    code(
        """
df = ingest_miller_center(cfg)
print(df.shape)
df.head(3)
        """
    ),
    md(
        """
## What did we get? (raw shape + coverage)

A quick look at columns, per-president coverage, and the date span — so we can see the
corpus we'll be scoring. **Coverage is expected to be uneven** (far more speeches for
modern presidents than 19th-century ones); that's a documented caveat, not a bug.
        """
    ),
    code(
        """
print("columns:", list(df.columns))
print("speeches:", len(df))
print("presidents:", df["president"].nunique())
print("empty transcripts:", (df["transcript"].fillna("").str.strip() == "").sum())

# Date span (raw date string has a known bogus fixed offset; we only read the span here).
dates = df["date"].dropna().astype(str)
print("date span (raw strings):", dates.min(), "→", dates.max())

df["president"].value_counts().head(10)
        """
    ),
    md(
        """
## Load into DuckDB as `speeches_raw` + register provenance

The raw frame goes into `data/project.duckdb` as **`speeches_raw`** (source of truth for
the pipeline). We then register it in the `_sources` metadata table with the corpus URL,
license, and the methodology / series-break notes that keep the readability analysis
honest — especially the **written-address → spoken/broadcast era break (~1913)**, which
dominates any raw 1789→present readability trend.
        """
    ),
    code(
        """
con = get_connection(cfg)
con.register("df_raw", df)
con.execute("CREATE OR REPLACE TABLE speeches_raw AS SELECT * FROM df_raw")
con.unregister("df_raw")

n = con.execute("SELECT COUNT(*) FROM speeches_raw").fetchone()[0]
print("speeches_raw rows:", n)

register_source(
    con,
    table="speeches_raw",
    name="Miller Center Presidential Speech Corpus (UVA)",
    url="https://data.millercenter.org/miller_center_speeches.tgz",
    license="Public domain (U.S. government works)",
    retrieved="2026-09-26",
    notes=(
        "Curated bulk corpus of major presidential speeches, one JSON per speech "
        "(transcript + title/date/president). Same corpus as the presidential-speeches "
        "project; re-used here to measure reading-grade level (readability). Transcript "
        "is the readability input and is dropped before export."
    ),
    methodology=(
        "Editorial curation — the Miller Center selects and transcribes MAJOR speeches, "
        "not every utterance. Readability is not a source field; it is computed downstream "
        "(Flesch-Kincaid + companion formulas) from the transcript."
    ),
    series_breaks=(
        "Written-address vs broadcast era (~1913): pre-radio annual messages to Congress "
        "were written documents, not delivered oratory, and are systematically longer and "
        "more complex — segment any 1789->present readability trend at this break. Coverage "
        "density also varies sharply by era (per-president/decade averages rest on very "
        "different sample sizes)."
    ),
)
get_sources(con)
        """
    ),
    md(
        """
## Cleanup

DuckDB is single-writer — close the connection so `02-clean` (and DBCode) aren't blocked.
        """
    ),
    code(
        """
con.close()
print("connection closed — ingest complete")
        """
    ),
]

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}
nb.metadata["language_info"] = {"name": "python"}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(f"wrote {NB_PATH.relative_to(PROJECT)}  ({len(cells)} cells)")
