"""Build notebooks/04-viz.ipynb via nbformat — EXPLORATION stage (v2).

Spoken-era (1913+), oratory-only readability charts. Written era chopped: pre-1913
messages were written documents and reading formulas stay unstable on them (see
the 2026-09-26 data-quality investigation). Uses the shared Pillow factory
(matplotlib RecursionErrors on Py3.14). Charts render inline. Read-only DuckDB.

    .venv/bin/python scripts/_build_nb_04_viz.py
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/04-viz.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

PROJECT = Path(__file__).resolve().parents[1]
NB_PATH = PROJECT / "notebooks" / "04-viz.ipynb"


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


cells = [
    md(
        """
# 04 — Viz (exploration) · presidential-readability

**Goal:** settle the story + the chart set before building publication charts (`06-viz-social`,
only after owner review).

**Scope decisions locked from the data-quality pass (2026-09-26):**
- **Oratory only** — State-of-the-Union series + inaugural addresses. Proclamations / veto
  messages / orders were dropped in `03-prepare` (they scored as grade-150 one-sentence legal
  texts).
- **Spoken era only (1913+)** — pre-1913 annual messages were written documents read by a
  clerk; reading formulas stay unstable on them even after punkt + the oratory filter. 1913→2026
  is plenty of history on its own, and it's clean.
- Sentence counts via **NLTK punkt** (not textstat's naive splitter).

**Rendering:** shared Pillow factory (`../../shared`); charts export to `outputs/social/`
(gitignored) AND render inline.

**The story:** the State-of-the-Union has gotten markedly simpler to read across the broadcast
era — from ~grade 15–20 in the mid-20th century to ~grade 7–8 today.
        """
    ),
    code(
        """
import sys, os
from pathlib import Path

PROJECT_ROOT = Path.cwd() if (Path.cwd() / "config.yaml").exists() else Path.cwd().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent.parent / "shared"))
os.chdir(PROJECT_ROOT)

import duckdb
from colors import c
from chart_factory import render_chart

con = duckdb.connect(str(PROJECT_ROOT / "data" / "project.duckdb"), read_only=True)
print("scored speeches:", con.execute("SELECT COUNT(*) FROM speeches_readability").fetchone()[0])
print("spoken-era oratory:", con.execute("SELECT COUNT(*) FROM speeches_readability WHERE delivery_mode='spoken'").fetchone()[0])
        """
    ),
    md(
        """
## Chart A — State-of-the-Union reading grade level, spoken era (LEAD)

Avg Flesch–Kincaid grade per year, State-of-the-Union series, 1913→present. No x-axis label
(the year axis is self-evident).
        """
    ),
    code(
        """
sotu = con.execute('''
    SELECT year, ROUND(AVG(fk_grade), 2) AS fk_grade
    FROM speeches_readability
    WHERE is_sotu_series AND delivery_mode = 'spoken'
    GROUP BY year ORDER BY year
''').df()

render_chart({
    "type": "line",
    "table": sotu,
    "x_col": "year",
    "series": [{"col": "fk_grade", "label": "State of the Union", "color": c("teal")}],
    "x_axis_label": "",
    "y_axis_label": "Flesch-Kincaid grade level",
    "markers": True, "label_last": False, "y_min": 0,
    "title": "State-of-the-Union readability, 1913\u20132026",
    "subtitle": "Average Flesch-Kincaid reading-grade level per address.",
    "source": "Miller Center corpus; readability via textstat + NLTK punkt",
    "filename": "explore_A_sotu_spoken_line",
})
        """
    ),
    md(
        """
## Chart C — four readability formulas agree (SOTU, spoken era)

The credibility chart: if the decline were an artifact of one formula it wouldn't replicate.
Flesch–Kincaid, SMOG, Gunning Fog, and Coleman–Liau, decade-averaged. No x-axis label (the
subtitle says decade).
        """
    ),
    code(
        """
metrics_dec = con.execute('''
    SELECT (year/10)*10 AS decade,
           ROUND(AVG(fk_grade),2) fk_grade,
           ROUND(AVG(smog_index),2) smog_index,
           ROUND(AVG(gunning_fog),2) gunning_fog,
           ROUND(AVG(coleman_liau),2) coleman_liau
    FROM speeches_readability WHERE is_sotu_series AND delivery_mode='spoken'
    GROUP BY 1 ORDER BY 1
''').df()

render_chart({
    "type": "line",
    "table": metrics_dec,
    "x_col": "decade",
    "series": [
        {"col": "fk_grade",     "label": "Flesch-Kincaid", "color": c("teal")},
        {"col": "smog_index",   "label": "SMOG",           "color": c("gold")},
        {"col": "gunning_fog",  "label": "Gunning Fog",    "color": c("spice")},
        {"col": "coleman_liau", "label": "Coleman-Liau",   "color": c("navy")},
    ],
    "x_axis_label": "",
    "y_axis_label": "Grade level",
    "legend": True, "markers": True, "label_last": False, "y_min": 0,
    "title": "State-of-the-Union readability, four formulas by decade",
    "subtitle": "Grade-level formulas, decade-averaged, State-of-the-Union series, spoken era.",
    "source": "Miller Center corpus; readability via textstat + NLTK punkt",
    "filename": "explore_C_multimetric_spoken_line",
})
        """
    ),
    md(
        """
## Chart E — inaugural address readability, spoken era

Inaugurals are their own speech type — delivered oratory, one per term. Noisier than the SOTU
series (single speeches, and 1973 is a real high outlier), but the downward drift holds.
        """
    ),
    code(
        """
inaug = con.execute('''
    SELECT year, ROUND(fk_grade,2) AS fk_grade
    FROM speeches_readability
    WHERE speech_type = 'Inaugural Address' AND delivery_mode='spoken'
    ORDER BY year
''').df()

render_chart({
    "type": "line",
    "table": inaug,
    "x_col": "year",
    "series": [{"col": "fk_grade", "label": "Inaugural address", "color": c("caramel")}],
    "x_axis_label": "",
    "y_axis_label": "Flesch-Kincaid grade level",
    "markers": True, "label_last": False, "y_min": 0,
    "title": "Inaugural address readability, 1913\u20132025",
    "subtitle": "Average Flesch-Kincaid reading-grade level per inaugural address.",
    "source": "Miller Center corpus; readability via textstat + NLTK punkt",
    "filename": "explore_E_inaugural_spoken_line",
})
        """
    ),
    md(
        """
## Exploration summary — the chart set

**Lead finding:** across the broadcast era (1913+), presidential oratory has gotten markedly
simpler — the State of the Union falls from ~grade 15–20 to ~grade 7–8. Four formulas agree, so
it's not an artifact. Written-era (pre-1913) numbers are excluded because those were written
documents and the reading formulas are unstable on them.

**Chart set for social (owner confirmed):**
- **A** — SOTU spoken-era line (lead).
- **C** — four-formula agreement (credibility).
- **E** — inaugural addresses (a second, independently-delivered speech type).

(Dropped from the earlier pass: the all-types decade line and the per-president ranked bar.)

⏸ Ready for `06-viz-social` once the owner OKs these three.
        """
    ),
    md("## Cleanup"),
    code(
        """
con.close()
print("connection closed — exploration complete")
        """
    ),
]

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata["language_info"] = {"name": "python"}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(f"wrote {NB_PATH.relative_to(PROJECT)}  ({len(cells)} cells)")
