"""Build notebooks/02-clean.ipynb via nbformat.

Cleaning stage ONLY — no readability scoring (that's 03-prepare). Parses the
date (dropping the source's bogus fixed offset), derives year, classifies
speech_type / sotu_series / delivery_mode (structural, from title+date),
HTML-unescapes + whitespace-collapses the transcript, dedupes, QC, and saves
interim parquet + a DuckDB `speeches_clean` table.

Run from the project root:
    .venv/bin/python scripts/_build_nb_02_clean.py
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/02-clean.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

PROJECT = Path(__file__).resolve().parents[1]
NB_PATH = PROJECT / "notebooks" / "02-clean.ipynb"


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


cells = [
    md(
        """
# 02 — Clean · presidential-readability

**Goal:** turn raw `speeches_raw` into a tidy, analysis-ready `speeches_clean` — **cleaning
only**. No readability scoring here; that is a feature step and lives in `03-prepare`
(readability scoring runs AFTER cleaning, matching the pipeline-stage discipline).

**What this notebook does:**
1. **Parse the date** — the source `date` carries a bogus fixed `-04:56` offset, so we take
   only the date portion and derive `year`.
2. **Classify structure** — `speech_type` (inaugural / SOTU / annual message / …),
   `is_sotu_series` (unify Annual Message + State of the Union), and `delivery_mode`
   (**written** pre-1913 vs **spoken** 1913+ — the load-bearing readability series break).
3. **Clean the transcript** — HTML-unescape (so `&mdash;`/`&amp;` fragments don't leak),
   collapse whitespace. The transcript is the readability *input*, so we keep it here and
   drop it only at export.
4. **Dedupe + QC**, then save `data/interim/speeches_clean.parquet` + DuckDB `speeches_clean`.
        """
    ),
    code(
        """
import sys
import html
import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path.cwd() if (Path.cwd() / "config.yaml").exists() else Path.cwd().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingest import load_config
from src.clean_quality import (
    get_connection, quality_report, save_interim,
    classify_speech_type, sotu_series, delivery_mode, SPOKEN_ERA_START_YEAR,
)

cfg = load_config(PROJECT_ROOT / "config.yaml")
cfg["paths"] = {k: str(PROJECT_ROOT / v) for k, v in cfg["paths"].items()}
cfg["settings"]["duckdb_file"] = str(PROJECT_ROOT / cfg["settings"]["duckdb_file"])

con = get_connection(cfg)
raw = con.execute("SELECT * FROM speeches_raw").df()
print("speeches_raw:", raw.shape)
print("columns:", list(raw.columns))
        """
    ),
    md(
        """
## 1. Parse date → `speech_date` + `year`

The raw `date` string looks like `1789-04-30T13:03:58-04:56` — the `-04:56` offset is a
source artifact (a fixed, meaningless value on every row), so we parse **only the date
portion** (`YYYY-MM-DD`) and derive an integer `year`.
        """
    ),
    code(
        """
# Take the date portion before the 'T'; parse to a real date; derive year.
date_part = raw["date"].astype(str).str.slice(0, 10)
speech_date = pd.to_datetime(date_part, errors="coerce", format="%Y-%m-%d")
raw["speech_date"] = speech_date.dt.date.astype("string")
raw["year"] = speech_date.dt.year.astype("Int64")

print("unparsed dates:", raw["year"].isna().sum())
print("year range:", int(raw["year"].min()), "→", int(raw["year"].max()))
        """
    ),
    md(
        """
## 2. Classify structure — `speech_type`, `is_sotu_series`, `delivery_mode`

All from `src/clean_quality.py` (deterministic, reproducible):
- `speech_type` buckets the title (Inaugural, State of the Union, Annual Message, …).
- `is_sotu_series` unifies Annual Message (≤1928) + State of the Union (1929+) — the same
  constitutional address, so cross-president SOTU readability is comparable.
- `delivery_mode` = **written** (pre-1913, clerk-read documents) vs **spoken** (1913+,
  delivered oratory). This is the readability series break we segment every trend at.
        """
    ),
    code(
        """
raw["speech_type"] = raw["title"].fillna("").map(classify_speech_type)
raw["is_sotu_series"] = raw["speech_type"].map(sotu_series)
raw["delivery_mode"] = raw["year"].map(lambda y: delivery_mode(None if pd.isna(y) else int(y)))

print("speech_type:")
print(raw["speech_type"].value_counts())
print("\\ndelivery_mode:")
print(raw["delivery_mode"].value_counts())
print(f"\\n(spoken-era cutoff = {SPOKEN_ERA_START_YEAR})")
        """
    ),
    md(
        """
## 3. Clean the transcript

HTML-unescape (the source transcripts carry entities like `&mdash;`, `&amp;`, `&nbsp;`
that would otherwise corrupt sentence/word counts) and collapse runs of whitespace to a
single space. We keep the transcript column — it's the readability input for `03-prepare`
— and also trim the president/title strings.
        """
    ),
    code(
        """
_ws = re.compile(r"\\s+")

def clean_text(t):
    if not isinstance(t, str) or not t:
        return ""
    return _ws.sub(" ", html.unescape(t).replace("\\u2019", "'")).strip()

raw["transcript"] = raw["transcript"].map(clean_text)
raw["president"] = raw["president"].astype("string").str.strip()
raw["title"] = raw["title"].astype("string").str.strip()

# Length sanity (chars) — readability needs real text; flag ultra-short transcripts.
raw["n_chars"] = raw["transcript"].str.len()
print("empty transcripts:", (raw["n_chars"] == 0).sum())
print("very short (<200 chars):", (raw["n_chars"] < 200).sum())
raw[["president", "year", "speech_type", "n_chars"]].sort_values("n_chars").head(5)
        """
    ),
    md(
        """
## 4. Dedupe + select columns → `speeches_clean`

Drop any exact duplicate speeches (same president + date + title + transcript). Keep the
columns the readability stage needs; drop bulky raw fields we won't use (`transcript_html`,
`introduction`, `doc_name`, media links).
        """
    ),
    code(
        """
keep = [
    "president", "speech_date", "year", "title", "speech_type",
    "is_sotu_series", "delivery_mode", "transcript", "n_chars", "url", "source_file",
]
clean = raw[keep].copy()

before = len(clean)
clean = clean.drop_duplicates(subset=["president", "speech_date", "title", "transcript"])
print("dropped duplicates:", before - len(clean))

# Drop rows with no usable text or no year (can't score / can't place on a trend).
clean = clean[(clean["n_chars"] > 0) & (clean["year"].notna())].reset_index(drop=True)
print("speeches_clean rows:", len(clean))
clean.head(3)
        """
    ),
    md(
        """
## 5. Quality report + save interim

`quality_report` writes a QC summary; then we persist `speeches_clean` as interim parquet
and as a DuckDB table for `03-prepare` to read.
        """
    ),
    code(
        """
quality_report(clean, "speeches_clean", con)

save_interim(clean, cfg, "speeches_clean.parquet")

con.register("df_clean", clean)
con.execute("CREATE OR REPLACE TABLE speeches_clean AS SELECT * FROM df_clean")
con.unregister("df_clean")
print("speeches_clean in DuckDB:", con.execute("SELECT COUNT(*) FROM speeches_clean").fetchone()[0])

# Coverage snapshot by delivery mode — what the readability trend will rest on.
con.execute('''
    SELECT delivery_mode, COUNT(*) n_speeches,
           MIN(year) min_year, MAX(year) max_year
    FROM speeches_clean GROUP BY 1 ORDER BY 1
''').df()
        """
    ),
    md(
        """
## Cleanup

Close the DuckDB connection (single-writer) so `03-prepare` isn't blocked.
        """
    ),
    code(
        """
con.close()
print("connection closed — clean complete")
        """
    ),
]

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata["language_info"] = {"name": "python"}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(f"wrote {NB_PATH.relative_to(PROJECT)}  ({len(cells)} cells)")
