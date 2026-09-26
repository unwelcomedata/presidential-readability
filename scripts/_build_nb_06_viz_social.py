"""Build notebooks/06-viz-social.ipynb via nbformat — publication social + web renders.

Renders the 3 owner-approved charts (spoken-era oratory readability) twice each:
  - social: twitter_landscape 1600x900, full chrome (title/subtitle/source/watermark)
  - web:    web preset 1664x936, web_mode=True (drops title/subtitle/source, keeps watermark)

A direct-builder helper is used because render_chart() only exports to outputs/social;
the web target is built via the factory's builder fn and saved to outputs/web manually.

    .venv/bin/python scripts/_build_nb_06_viz_social.py
    .venv/bin/python -m nbconvert --to notebook --execute --inplace notebooks/06-viz-social.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

PROJECT = Path(__file__).resolve().parents[1]
NB_PATH = PROJECT / "notebooks" / "06-viz-social.ipynb"


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


cells = [
    md(
        """
# 06 — Viz (social + web) · presidential-readability

Publication-ready renders of the 3 owner-approved charts. Each is rendered **twice** from the
same config (the workspace two-target system):
- **social** — `twitter_landscape` 1600×900, full chrome (title, subtitle, source,
  `@unwelcomedata` watermark) → `outputs/social/`.
- **web** — `web` preset 1664×936, `web_mode=True` (drops title/subtitle/source, keeps the
  watermark, gives the freed space to the data) → `outputs/web/`.

**The charts (spoken era 1913+, oratory only — see 03/04 for the data-quality decisions):**
- **01** — State-of-the-Union reading grade level, 1913–2026 (LEAD).
- **02** — SOTU readability by decade, four formulas (credibility).
- **03** — Inaugural address readability, 1913–2025.

Descriptive titles (owner preference). No x-axis labels (year/decade is self-evident).
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
from PIL import Image
from IPython.display import display
from colors import c
import chart_factory as cf

con = duckdb.connect(str(PROJECT_ROOT / "data" / "project.duckdb"), read_only=True)

SOCIAL = PROJECT_ROOT / "outputs" / "social"
WEB = PROJECT_ROOT / "outputs" / "web"
SOCIAL.mkdir(parents=True, exist_ok=True)
WEB.mkdir(parents=True, exist_ok=True)


def render_dual(base_config, filename):
    \"\"\"Render one chart to BOTH social and web from a single base config.

    social = twitter_landscape + full chrome; web = web preset + web_mode (no
    title/subtitle/source). Builds via the factory builder fn directly so we can
    target two output dirs. Displays the social version inline.
    \"\"\"
    ctype = base_config["type"]
    builder = cf._CHART_TYPES[ctype]

    # Social (full chrome)
    social_cfg = {**base_config, "preset": "twitter_landscape", "web_mode": False}
    img_social = builder(social_cfg, con)
    p_social = SOCIAL / f"{filename}.png"
    img_social.save(p_social)

    # Web (chrome stripped)
    web_cfg = {**base_config, "preset": "web", "web_mode": True,
               "title": "", "subtitle": None, "source": None}
    img_web = builder(web_cfg, con)
    p_web = WEB / f"{filename}.png"
    img_web.save(p_web)

    print(f"{filename}: social {img_social.size} -> {p_social.name} | web {img_web.size} -> {p_web.name}")
    display(img_social)
    return p_social, p_web

print("ready")
        """
    ),
    md(
        """
## 01 — State-of-the-Union readability, 1913–2026 (LEAD)

Subtitle names the spoken/broadcast era (the reason the series starts at 1913). No x-axis label.
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

render_dual({
    "type": "line",
    "table": sotu,
    "x_col": "year",
    "series": [{"col": "fk_grade", "label": "State of the Union", "color": c("teal")}],
    "y_axis_label": "Flesch-Kincaid grade level",
    "markers": True, "label_last": False, "y_min": 0,
    "title": "State-of-the-Union readability, 1913\u20132026",
    "subtitle": "Average Flesch-Kincaid reading-grade level per address, spoken/broadcast era (1913 on).",
    "source": "Miller Center corpus; readability via textstat + NLTK punkt",
}, "01_sotu_readability")
        """
    ),
    md(
        """
## 02 — SOTU readability by decade, four formulas (credibility)

**True decade aggregation** (`FLOOR(year/10)*10`, averaging all speeches in each 10-year bin) —
this smooths single-speech spikes (e.g. Nixon's long 1970–72 addresses) into the decade trend.
Four independent formulas converging downward = the decline isn't an artifact of one formula.
No x-axis label (subtitle says decade).
        """
    ),
    code(
        """
metrics_dec = con.execute('''
    SELECT FLOOR(year/10)*10 AS decade,
           ROUND(AVG(fk_grade),2) fk_grade,
           ROUND(AVG(smog_index),2) smog_index,
           ROUND(AVG(gunning_fog),2) gunning_fog,
           ROUND(AVG(coleman_liau),2) coleman_liau
    FROM speeches_readability WHERE is_sotu_series AND delivery_mode='spoken'
    GROUP BY 1 ORDER BY 1
''').df()

render_dual({
    "type": "line",
    "table": metrics_dec,
    "x_col": "decade",
    "series": [
        {"col": "fk_grade",     "label": "Flesch-Kincaid", "color": c("teal")},
        {"col": "smog_index",   "label": "SMOG",           "color": c("gold")},
        {"col": "gunning_fog",  "label": "Gunning Fog",    "color": c("spice")},
        {"col": "coleman_liau", "label": "Coleman-Liau",   "color": c("navy")},
    ],
    "y_axis_label": "Grade level",
    "legend": True, "markers": True, "label_last": False, "y_min": 0,
    "title": "State-of-the-Union readability by decade, four formulas",
    "subtitle": "Grade-level formulas, decade-averaged, spoken/broadcast era (1913 on).",
    "source": "Miller Center corpus; readability via textstat + NLTK punkt",
}, "02_sotu_four_formulas")
        """
    ),
    md(
        """
## 03 — Inaugural address readability, 1913–2025

A second, independently-delivered speech type. Noisier than the SOTU series (single speeches;
1973 is a real high point) but the downward drift holds. No x-axis label.
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

render_dual({
    "type": "line",
    "table": inaug,
    "x_col": "year",
    "series": [{"col": "fk_grade", "label": "Inaugural address", "color": c("caramel")}],
    "y_axis_label": "Flesch-Kincaid grade level",
    "markers": True, "label_last": False, "y_min": 0,
    "title": "Inaugural address readability, 1913\u20132025",
    "subtitle": "Average Flesch-Kincaid reading-grade level per inaugural, spoken/broadcast era.",
    "source": "Miller Center corpus; readability via textstat + NLTK punkt",
}, "03_inaugural_readability")
        """
    ),
    md("## Cleanup"),
    code(
        """
con.close()
print("connection closed — social + web renders complete")
        """
    ),
]

nb = new_notebook(cells=cells)
nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb.metadata["language_info"] = {"name": "python"}

NB_PATH.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, NB_PATH)
print(f"wrote {NB_PATH.relative_to(PROJECT)}  ({len(cells)} cells)")
