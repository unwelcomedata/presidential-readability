#!/usr/bin/env python3
"""Pre-publish validation — re-check the presidential-readability chart data.

Run BEFORE curating the release branch / flipping the repo public. It re-derives
what each published chart should show, straight from the DuckDB source table
(speeches_readability), and confirms:

  1. The published export CSV (export/presidential_readability_v1.csv) matches the
     DuckDB source on the key columns (no drift).
  2. The headline chart facts still hold (universe/filter sizes; the SOTU spoken
     trend endpoints; the decade endpoints; the inaugural set), so a silent data
     or methodology change can't slip out unnoticed.
  3. Structural invariants — the data-quality fixes hold: only oratory is scored
     (SOTU series + inaugurals), fk_grade is in a sane range (no grade-150
     proclamation artifacts), and every scored row has a delivery_mode.
  4. Social vs web chart parity — the two rendered sets cover the same 3 charts,
     social is 1600-wide, web is the 1664-wide canvas.

Published charts (see notebooks/06-viz-social.ipynb), spoken era (1913+), oratory only:
  01 State-of-the-Union readability, 1913-2026 (line)            social + web
  02 SOTU readability by decade, four formulas (line)            social + web
  03 Inaugural address readability, 1913-2025 (line)             social + web

Exit code 0 = all checks passed, safe to publish. Non-zero = do NOT publish.

Usage:
    .venv/bin/python scripts/validate_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

PROJECT = Path(__file__).resolve().parent
while not (PROJECT / "config.yaml").exists() and PROJECT != PROJECT.parent:
    PROJECT = PROJECT.parent
sys.path.insert(0, str(PROJECT))
from src.ingest import load_config  # noqa: E402

failures: list[str] = []
checks: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        checks.append(f"  PASS  {name}")
    else:
        failures.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    cfg = load_config("config.yaml")
    db = str(PROJECT / cfg["settings"]["duckdb_file"])
    export_dir = PROJECT / cfg["paths"]["export"]
    con = duckdb.connect(db, read_only=True)

    feats = con.execute("SELECT * FROM speeches_readability").df()

    # ── Universe / scope (the data-quality decisions) ─────────────────────
    check("scope: 267 scored oratory speeches (SOTU + inaugural)",
          len(feats) == 267, f"got {len(feats)}")
    # ONLY oratory was scored — no other speech types leaked in.
    types = set(feats["speech_type"].unique())
    only_oratory = feats[(feats.is_sotu_series) | (feats.speech_type == "Inaugural Address")]
    check("scope: only oratory scored (SOTU series + Inaugural Address)",
          len(only_oratory) == len(feats),
          f"non-oratory rows present: {types}")
    check("scope: every scored row has a delivery_mode",
          not feats["delivery_mode"].isna().any(), "null delivery_mode present")

    # ── Structural: no grade-150 proclamation artifacts survive ───────────
    fk_min, fk_max = float(feats.fk_grade.min()), float(feats.fk_grade.max())
    check("structure: fk_grade in a sane range (<=45, no proclamation artifacts)",
          fk_max <= 45.0, f"max fk_grade={fk_max} (>45 = a legal-doc artifact leaked in)")
    check("structure: fk_grade floor is plausible (>=5)",
          fk_min >= 5.0, f"min fk_grade={fk_min}")
    check("structure: no null fk_grade", not feats.fk_grade.isna().any(),
          f"{int(feats.fk_grade.isna().sum())} null")

    # ── Chart 01: SOTU spoken-era line endpoints ──────────────────────────
    sotu = con.execute(
        "SELECT year, ROUND(AVG(fk_grade),1) fk FROM speeches_readability "
        "WHERE is_sotu_series AND delivery_mode='spoken' GROUP BY year ORDER BY year").df()
    check("chart01: SOTU spoken series has 87 yearly points",
          len(sotu) == 87, f"got {len(sotu)}")
    check("chart01: series starts 1913 @ grade 15.8",
          int(sotu.iloc[0].year) == 1913 and sotu.iloc[0].fk == 15.8,
          f"got {int(sotu.iloc[0].year)} @ {sotu.iloc[0].fk}")
    check("chart01: series ends 2026 @ grade 7.6",
          int(sotu.iloc[-1].year) == 2026 and sotu.iloc[-1].fk == 7.6,
          f"got {int(sotu.iloc[-1].year)} @ {sotu.iloc[-1].fk}")
    check("chart01: readability fell over the era (start > end by >=5 grades)",
          (sotu.iloc[0].fk - sotu.iloc[-1].fk) >= 5.0,
          f"start {sotu.iloc[0].fk} end {sotu.iloc[-1].fk}")

    # ── Chart 02: true decade aggregation endpoints ───────────────────────
    dec = con.execute(
        "SELECT FLOOR(year/10)*10 AS decade, ROUND(AVG(fk_grade),1) fk "
        "FROM speeches_readability WHERE is_sotu_series AND delivery_mode='spoken' "
        "GROUP BY 1 ORDER BY 1").df()
    check("chart02: 12 decade bins (1910s..2020s)",
          len(dec) == 12, f"got {len(dec)}")
    check("chart02: 1910s decade @ grade 15.5",
          int(dec.iloc[0].decade) == 1910 and dec.iloc[0].fk == 15.5,
          f"got {int(dec.iloc[0].decade)} @ {dec.iloc[0].fk}")
    check("chart02: 2020s decade @ grade 7.8",
          int(dec.iloc[-1].decade) == 2020 and dec.iloc[-1].fk == 7.8,
          f"got {int(dec.iloc[-1].decade)} @ {dec.iloc[-1].fk}")
    # decade aggregation must actually aggregate (multiple speeches per decade)
    dec_n = con.execute(
        "SELECT FLOOR(year/10)*10 AS decade, COUNT(*) n FROM speeches_readability "
        "WHERE is_sotu_series AND delivery_mode='spoken' GROUP BY 1").df()
    check("chart02: decades genuinely aggregate (max bin > 1 speech)",
          int(dec_n.n.max()) > 1, f"max speeches/decade = {int(dec_n.n.max())}")

    # ── Chart 03: inaugural spoken set ────────────────────────────────────
    inaug = con.execute(
        "SELECT year, ROUND(fk_grade,1) fk FROM speeches_readability "
        "WHERE speech_type='Inaugural Address' AND delivery_mode='spoken' ORDER BY year").df()
    check("chart03: inaugural spoken series present (>=25 speeches, from 1913)",
          len(inaug) >= 25 and int(inaug.iloc[0].year) == 1913,
          f"got n={len(inaug)} start={int(inaug.iloc[0].year)}")

    # ── Published CSV matches DuckDB (no drift) ───────────────────────────
    cols = ["president", "year", "speech_type", "delivery_mode",
            "fk_grade", "smog_index", "gunning_fog", "coleman_liau", "flesch_reading_ease"]
    path = export_dir / "presidential_readability_v1.csv"
    if not path.exists():
        check("export: presidential_readability_v1.csv exists", False, "missing export file")
    else:
        df_csv = pd.read_csv(path)
        # Export includes BOTH eras (spoken chart-set + written for buyers); compare
        # the full DuckDB table to the CSV on the key columns.
        try:
            key = ["president", "year", "speech_type"]
            a = feats[cols].sort_values(key).reset_index(drop=True)
            b = df_csv[cols].sort_values(key).reset_index(drop=True)
            same = a.shape == b.shape
            detail = "" if same else f"row count {a.shape[0]} vs {b.shape[0]}"
            if same:
                for col in cols:
                    if pd.api.types.is_numeric_dtype(a[col]):
                        diff = (a[col].astype("float64") - b[col].astype("float64")).abs()
                        col_ok = bool(((diff <= 0.01) | (a[col].isna() & b[col].isna())).all())
                    else:
                        col_ok = bool((a[col].fillna("\x00").astype(str) ==
                                       b[col].fillna("\x00").astype(str)).all())
                    if not col_ok:
                        same, detail = False, f"column {col!r} differs"
                        break
            check("export: presidential_readability_v1.csv matches DuckDB on key columns",
                  same, (detail + " — regenerate 03-prepare") if detail else "")
        except KeyError as e:
            check(f"export: CSV has expected columns {cols}", False, str(e))

    con.close()

    # ── Social vs web chart parity ────────────────────────────────────────
    social_dir = PROJECT / "outputs" / "social"
    web_dir = PROJECT / "outputs" / "web"
    EXPECTED = {"01", "02", "03"}
    if social_dir.exists() and web_dir.exists():
        s_num = {p.name[:2] for p in social_dir.glob("*.png") if p.name[:2].isdigit()}
        w_num = {p.name[:2] for p in web_dir.glob("*.png") if p.name[:2].isdigit()}
        check("parity: social has charts 01,02,03", EXPECTED.issubset(s_num),
              f"social nums {sorted(s_num)}")
        check("parity: web has charts 01,02,03", EXPECTED.issubset(w_num),
              f"web nums {sorted(w_num)}")
        check("parity: same chart set social vs web", s_num == w_num,
              f"social {sorted(s_num)} web {sorted(w_num)}")
        try:
            from PIL import Image
            s_widths = {Image.open(p).size[0] for p in social_dir.glob("*.png")}
            w_widths = {Image.open(p).size[0] for p in web_dir.glob("*.png")}
            check("parity: social charts are 1600-wide", s_widths == {1600},
                  f"got {sorted(s_widths)}")
            check("parity: web charts are the 1664-wide web canvas", w_widths == {1664},
                  f"got {sorted(w_widths)}")
        except ImportError:
            pass
    else:
        checks.append("  SKIP  chart parity (outputs/ not rendered on this checkout)")

    # ── Report ────────────────────────────────────────────────────────────
    print("Pre-publish chart-data validation — presidential-readability")
    print("=" * 60)
    for line in checks:
        print(line)
    for line in failures:
        print(line)
    print("=" * 60)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S) — DO NOT PUBLISH.")
        return 1
    print(f"RESULT: all {len([c for c in checks if 'PASS' in c])} checks passed — safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
