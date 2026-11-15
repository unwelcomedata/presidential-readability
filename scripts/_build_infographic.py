"""Build the presidential-readability infographic (tall + social SVG -> PNG) and
validate every data mark back to the DuckDB source.

Every bar width, line point and dot is COMPUTED here from data/project.duckdb
(speeches_readability). Nothing is hand-placed. Tall and social are fed the same
queried values; only the canvas mapping differs.

Usage (from project root):
    .venv/bin/python scripts/_build_infographic.py
Writes docs/infographic_presidential_readability{,_social}.{svg,png}
and artifacts/INFOGRAPHIC-VALIDATION.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

PROJECT = Path(__file__).resolve().parents[1]
DOCS = PROJECT / "docs"
ART = PROJECT / "artifacts"
DOCS.mkdir(exist_ok=True)
ART.mkdir(exist_ok=True)

NAVY, TEAL, GOLD, SPICE = "#003049", "#005F73", "#EE9B00", "#BB3E03"
AQUA, VANILLA, GREY, BG = "#94D2BD", "#E9D8A6", "#6B7280", "#FBF8F0"
FORMULAS = [("fk_grade", "Flesch&#8211;Kincaid", TEAL), ("smog_index", "SMOG", GOLD),
            ("gunning_fog", "Gunning Fog", SPICE), ("coleman_liau", "Coleman&#8211;Liau", NAVY)]


# ───────────────────────── data (all from DuckDB) ─────────────────────────
def load():
    con = duckdb.connect(str(PROJECT / "data/project.duckdb"), read_only=True)
    q = lambda s: con.execute(s).fetchall()
    sotu = q("""SELECT year, ROUND(AVG(fk_grade),2) FROM speeches_readability
                WHERE is_sotu_series AND delivery_mode='spoken' GROUP BY year ORDER BY year""")
    dec = q("""SELECT CAST(FLOOR(year/10)*10 AS INT), ROUND(AVG(fk_grade),2), ROUND(AVG(smog_index),2),
                      ROUND(AVG(gunning_fog),2), ROUND(AVG(coleman_liau),2), COUNT(*)
               FROM speeches_readability WHERE is_sotu_series AND delivery_mode='spoken'
               GROUP BY 1 ORDER BY 1""")
    inaug = q("""SELECT year, ROUND(fk_grade,2) FROM speeches_readability
                 WHERE speech_type='Inaugural Address' AND delivery_mode='spoken' ORDER BY year""")
    wps = q("""SELECT CAST(FLOOR(year/10)*10 AS INT) d, ROUND(AVG(word_count*1.0/sentence_count),1), COUNT(*)
               FROM speeches_readability WHERE is_sotu_series AND delivery_mode='spoken'
               GROUP BY 1 ORDER BY 1""")
    con.close()
    return dict(sotu=sotu, dec=dec, inaug=inaug, wps={r[0]: (r[1], r[2]) for r in wps})


class Lin:
    """value -> pixel, linear."""
    def __init__(self, v0, v1, p0, p1):
        self.v0, self.v1, self.p0, self.p1 = v0, v1, p0, p1
    def __call__(self, v):
        return self.p0 + (v - self.v0) / (self.v1 - self.v0) * (self.p1 - self.p0)
    def inv(self, p):
        return self.v0 + (p - self.p0) / (self.p1 - self.p0) * (self.v1 - self.v0)


def f(x):
    return f"{x:.1f}"


def t(x, y, s, size, fill, weight="", anchor="", extra=""):
    w = f' font-weight="{weight}"' if weight else ""
    a = f' text-anchor="{anchor}"' if anchor else ""
    return f'<text x="{f(x)}" y="{f(y)}" fill="{fill}" font-size="{size}"{w}{a}{extra}>{s}</text>'


# ───────────────────────── reusable pieces (computed marks) ─────────────────────────
def sotu_line(d, xs, ys, sw=3.0, r=6.0, lab=18):
    """SOTU yearly line. Breaks into solid segments; dashed connector across gaps > 3 yrs.
    Dots on the real first, last, max and min points."""
    out, pts = [], d["sotu"]
    segs, cur = [], [pts[0]]
    for a, b in zip(pts, pts[1:]):
        if b[0] - a[0] > 3:
            segs.append(cur); cur = [b]
            out.append(f'<line x1="{f(xs(a[0]))}" y1="{f(ys(a[1]))}" x2="{f(xs(b[0]))}" y2="{f(ys(b[1]))}" '
                       f'stroke="{GREY}" stroke-width="1.5" stroke-dasharray="5 5"/>'
                       f'<!-- gap {a[0]}->{b[0]}: no address in dataset -->')
        else:
            cur.append(b)
    segs.append(cur)
    for s in segs:
        ptxt = " ".join(f"{f(xs(y))},{f(ys(v))}" for y, v in s)
        out.append(f'<polyline class="sotu" points="{ptxt}" fill="none" stroke="{TEAL}" stroke-width="{sw}" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')
    first, last = pts[0], pts[-1]
    mx = max(pts, key=lambda p: p[1]); mn = min(pts, key=lambda p: p[1])
    for (y, v), col in ((first, NAVY), (last, SPICE), (mx, GOLD), (mn, GOLD)):
        out.append(f'<circle class="dot" data-year="{y}" cx="{f(xs(y))}" cy="{f(ys(v))}" r="{r}" fill="{col}"/>'
                   f'<!-- {y} -> {v} -->')
    return "\n  ".join(out), first, last, mx, mn


def formula_rows(d, x_of, y0, pitch, label_x, n_x, r, lab_size, nsize):
    out = []
    for i, row in enumerate(d["dec"]):
        decade, vals, n = row[0], row[1:5], row[5]
        y = y0 + i * pitch
        lo, hi = min(vals), max(vals)
        out.append(f'<line x1="{f(x_of(lo))}" y1="{f(y)}" x2="{f(x_of(hi))}" y2="{f(y)}" stroke="{VANILLA}" '
                   f'stroke-width="{r*0.8:.1f}" stroke-linecap="round"/>')
        out.append(t(label_x, y + lab_size * 0.35, f"{decade}s", lab_size, NAVY, "bold"))
        out.append(t(n_x, y + nsize * 0.35, f"n={n}", nsize, "#9CA3AF"))
        for (col, _, color), v in zip(FORMULAS, vals):
            out.append(f'<circle class="fdot" data-decade="{decade}" data-f="{col}" cx="{f(x_of(v))}" '
                       f'cy="{f(y)}" r="{r}" fill="{color}"/><!-- {decade}s {col} {v} -->')
    return "\n  ".join(out)


def inaug_lollipops(d, xs, ys, base_y, r):
    out = []
    pts = d["inaug"]
    for y, v in pts:
        out.append(f'<line x1="{f(xs(y))}" y1="{f(base_y)}" x2="{f(xs(y))}" y2="{f(ys(v))}" '
                   f'stroke="{VANILLA}" stroke-width="3"/>')
    for y, v in pts:
        out.append(f'<circle class="idot" data-year="{y}" cx="{f(xs(y))}" cy="{f(ys(v))}" r="{r}" fill="{TEAL}"/>'
                   f'<!-- {y} -> {v} -->')
    return "\n  ".join(out)


def legend(x, y, size, gap):
    out, cx = [], x
    for _, name, color in FORMULAS:
        out.append(f'<circle cx="{f(cx+7)}" cy="{f(y-size*0.33)}" r="7" fill="{color}"/>')
        out.append(t(cx + 22, y, name, size, GREY))
        cx += gap
    return "\n  ".join(out)


# ───────────────────────── TALL poster ─────────────────────────
def build_tall(d):
    W, H = 1200, 2590
    sotu, first, last, mx, mn = None, None, None, None, None
    # S1 sparkline: x 150..1120 (1913..2026), y 570..870 (grade 6..20 -> bottom..top)
    xs1 = Lin(1913, 2026, 150, 1120); ys1 = Lin(6, 20, 870, 570)
    line, first, last, mx, mn = sotu_line(d, xs1, ys1)
    grid1 = []
    for g in (8, 12, 16, 20):
        grid1.append(f'<line x1="150" y1="{f(ys1(g))}" x2="1120" y2="{f(ys1(g))}" stroke="#E5E0D0" stroke-width="1.5"/>')
        grid1.append(t(135, ys1(g) + 6, str(g), 18, GREY, anchor="end"))
    ticks1 = "\n  ".join(t(xs1(y), 898, str(y), 18, GREY, anchor="middle") for y in (1920, 1960, 2000))
    # S2 formulas: x 260..1120 (grade 8..20), rows from y=1130 pitch 42
    x2 = Lin(8, 20, 260, 1120)
    rows = formula_rows(d, x2, 1135, 42, 80, 170, 8, 24, 16)
    grid2 = []
    for g in (8, 12, 16, 20):
        grid2.append(f'<line x1="{f(x2(g))}" y1="1105" x2="{f(x2(g))}" y2="1640" stroke="#E5E0D0" stroke-width="1.5"/>')
        grid2.append(t(x2(g), 1668, str(g), 18, GREY, anchor="middle"))
    # S3 words per sentence: bars, scale px per word
    w10, w20 = d["wps"][1910][0], d["wps"][2020][0]
    pw = 26.0  # px per word
    # S4 inaugural: x 150..1120 (1913..2025), y baseline grade 4 at 2420, 16 at 2180
    xs4 = Lin(1913, 2025, 150, 1120); ys4 = Lin(4, 16, 2420, 2180)
    lol = inaug_lollipops(d, xs4, ys4, 2420, 7)
    inaug = dict(d["inaug"])
    imax = max(d["inaug"], key=lambda p: p[1]); imin = min(d["inaug"], key=lambda p: p[1])
    ilast = d["inaug"][-1]; ifirst = d["inaug"][0]

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  @unwelcomedata — PROJECT INFOGRAPHIC (tall portrait poster)
  Project: presidential-readability
  Generated by scripts/_build_infographic.py. Every mark is computed from
  data/project.duckdb (speeches_readability); coordinates written as comments.
  Canvas 1200 x {H}.
-->
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <!-- HEADER -->
  <rect x="0" y="0" width="{W}" height="300" fill="{NAVY}"/>
  {t(80,126,"Presidential Readability",68,"#FFFFFF","bold")}
  {t(80,190,"The State of the Union got simpler",40,AQUA,"bold")}
  {t(80,242,"Reading-grade level of every spoken-era address, 1913&#8211;2026.",26,VANILLA)}

  <!-- SECTION 1 — the slide -->
  {t(80,372,"From college level to middle school",34,NAVY,"bold")}
  {t(80,406,"Average Flesch&#8211;Kincaid grade of each State of the Union, 1913 on (spoken/broadcast era).",22,GREY)}
  {t(80,508,f"{first[1]:.1f}",96,NAVY,"bold")}
  {t(80,540,f"grade level in {first[0]}",22,GREY)}
  {t(1120,508,f"{last[1]:.1f}",96,SPICE,"bold",anchor="end")}
  {t(1120,540,f"grade level in {last[0]}",22,GREY,anchor="end")}
  {chr(10).join("  "+g for g in grid1)}
  {line}
  {t(xs1(mx[0])+12, ys1(mx[1])+6, f"{mx[1]:.1f} in {mx[0]} (peak)", 18, "#CA6702", "bold")}
  {t(xs1(mn[0])-12, ys1(mn[1])+30, f"{mn[1]:.1f} in {mn[0]} (low)", 18, "#CA6702", "bold", anchor="end")}
  {ticks1}
  {t(80,930,"Dashed = years with no address in the dataset. Y-axis: grade level.",18,GREY)}
  <line x1="80" y1="960" x2="1120" y2="960" stroke="{VANILLA}" stroke-width="3"/>

  <!-- SECTION 2 — four formulas -->
  {t(80,1030,"Not one formula&#8217;s quirk",34,NAVY,"bold")}
  {t(80,1064,"Decade-average grade under four formulas (State of the Union, spoken era).",22,GREY)}
  {legend(80,1096,20,215)}
  {chr(10).join("  "+g for g in grid2)}
  {rows}
  <line x1="80" y1="1700" x2="1120" y2="1700" stroke="{VANILLA}" stroke-width="3"/>

  <!-- SECTION 3 — sentences -->
  {t(80,1770,"Sentences got less than half as long",34,NAVY,"bold")}
  {t(80,1804,"Average words per sentence, State of the Union, by decade.",22,GREY)}
  {t(80,1872,"1910s",26,NAVY,"bold")}
  <!-- 1910s {w10} words -> {w10*pw:.1f}px -->
  <rect x="200" y="1844" width="{f(w10*pw)}" height="40" fill="{TEAL}"/>
  {t(200+w10*pw+14,1874,f"{w10:.1f} words",26,NAVY,"bold")}
  {t(80,1952,"2020s",26,NAVY,"bold")}
  <!-- 2020s {w20} words -> {w20*pw:.1f}px -->
  <rect x="200" y="1924" width="{f(w20*pw)}" height="40" fill="{SPICE}"/>
  {t(200+w20*pw+14,1954,f"{w20:.1f} words",26,NAVY,"bold")}
  {t(80,2010,"Shorter sentences are a large part of why the grade-level formulas fall.",22,GREY)}
  <line x1="80" y1="2050" x2="1120" y2="2050" stroke="{VANILLA}" stroke-width="3"/>

  <!-- SECTION 4 — inaugurals -->
  {t(80,2118,"Inaugural addresses slid too, with more noise",34,NAVY,"bold")}
  {t(80,2152,f"Flesch&#8211;Kincaid grade of each spoken-era inaugural ({len(d['inaug'])} addresses), 1913&#8211;2025.",22,GREY)}
  <line x1="150" y1="2420" x2="1120" y2="2420" stroke="{GREY}" stroke-width="2"/>
  {lol}
  {t(xs4(ifirst[0]),ys4(ifirst[1])-16,f"{ifirst[1]:.1f}",20,NAVY,"bold",anchor="middle")}
  {t(xs4(imax[0]),ys4(imax[1])-16,f"{imax[1]:.1f}",20,"#CA6702","bold",anchor="middle")}
  {t(xs4(imin[0]),ys4(imin[1])-16,f"{imin[1]:.1f}",20,"#CA6702","bold",anchor="middle")}
  {t(xs4(ilast[0]),ys4(ilast[1])-16,f"{ilast[1]:.1f}",20,SPICE,"bold",anchor="middle")}
  {t(xs4(1913),2448,"1913",18,GREY,anchor="middle")}{t(xs4(1965),2448,"1965",18,GREY,anchor="middle")}{t(xs4(2025),2448,"2025",18,GREY,anchor="middle")}

  <!-- FOOTER -->
  <rect x="0" y="{H-90}" width="{W}" height="90" fill="{NAVY}"/>
  {t(80,H-45,"@unwelcomedata",24,"#FFFFFF","bold")}
  {t(80,H-15,"Miller Center speech archive &#183; spoken era (1913+) &#183; absolute grades vary 2&#8211;5 levels by tool; the decline replicates.",18,AQUA)}
</svg>
'''
    return svg


# ───────────────────────── SOCIAL 1600x900 ─────────────────────────
def build_social(d):
    W, H = 1600, 900
    xs1 = Lin(1913, 2026, 130, 760); ys1 = Lin(6, 20, 640, 410)
    line, first, last, mx, mn = sotu_line(d, xs1, ys1, sw=2.6, r=5.5)
    grid1 = []
    for g in (8, 12, 16, 20):
        grid1.append(f'<line x1="130" y1="{f(ys1(g))}" x2="760" y2="{f(ys1(g))}" stroke="#E5E0D0" stroke-width="1.5"/>')
        grid1.append(t(118, ys1(g) + 5, str(g), 16, GREY, anchor="end"))
    ticks1 = "".join(t(xs1(y), 662, str(y), 16, GREY, anchor="middle") for y in (1920, 1960, 2000))
    # right-top formulas: x 1000..1520 grade 8..20, rows from y=285 pitch 24
    x2 = Lin(8, 20, 1010, 1520)
    rows = formula_rows(d, x2, 292, 23.5, 840, 925, 5.5, 17, 13)
    grid2 = []
    for g in (8, 12, 16, 20):
        grid2.append(f'<line x1="{f(x2(g))}" y1="272" x2="{f(x2(g))}" y2="560" stroke="#E5E0D0" stroke-width="1.5"/>')
        grid2.append(t(x2(g), 580, str(g), 15, GREY, anchor="middle"))
    # right-bottom inaugural: x 860..1520 (1913..2025), baseline grade 4 at 780, 16 at 645
    xs4 = Lin(1913, 2025, 860, 1520); ys4 = Lin(4, 16, 780, 650)
    lol = inaug_lollipops(d, xs4, ys4, 780, 5)
    imax = max(d["inaug"], key=lambda p: p[1]); imin = min(d["inaug"], key=lambda p: p[1])
    ifirst, ilast = d["inaug"][0], d["inaug"][-1]
    w10, w20 = d["wps"][1910][0], d["wps"][2020][0]
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<!--
  @unwelcomedata — PROJECT INFOGRAPHIC (landscape social render)
  Project: presidential-readability
  1600x900 feed render. Same brand FRAME, two columns. Generated by
  scripts/_build_infographic.py from the SAME queried values as the tall poster.
-->
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Helvetica, Arial, sans-serif">
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect x="0" y="0" width="{W}" height="190" fill="{NAVY}"/>
  {t(80,90,"Presidential Readability",56,"#FFFFFF","bold")}
  {t(80,138,"The State of the Union got simpler",32,AQUA,"bold")}
  {t(80,172,"Reading-grade level of every spoken-era address, 1913&#8211;2026.",22,VANILLA)}
  <line x1="800" y1="222" x2="800" y2="800" stroke="{VANILLA}" stroke-width="3"/>

  <!-- LEFT — the slide -->
  {t(80,262,"From college level to middle school",30,NAVY,"bold")}
  {t(80,292,"State of the Union, average Flesch&#8211;Kincaid grade per year.",20,GREY)}
  {t(80,372,f"{first[1]:.1f}",64,NAVY,"bold")}
  {t(200,372,f"in {first[0]}",22,GREY)}
  {t(760,372,f"{last[1]:.1f}",64,SPICE,"bold",anchor="end")}
  {t(640,372,f"in {last[0]}",22,GREY,anchor="end")}
  {chr(10).join("  "+g for g in grid1)}
  {line}
  {t(xs1(mx[0])+10, ys1(mx[1])+5, f"{mx[1]:.1f} ({mx[0]})", 16, "#CA6702", "bold")}
  {t(xs1(mn[0])-10, ys1(mn[1])+26, f"{mn[1]:.1f} ({mn[0]})", 16, "#CA6702", "bold", anchor="end")}
  {ticks1}
  <line x1="80" y1="700" x2="760" y2="700" stroke="{VANILLA}" stroke-width="3"/>
  {t(80,742,"Sentences shrank too (words per sentence, by decade):",20,GREY)}
  {t(80,786,f"{w10:.1f}",44,TEAL,"bold")}{t(200,786,"in the 1910s",20,GREY)}
  {t(420,786,"&#8594;",36,GREY)}
  {t(490,786,f"{w20:.1f}",44,SPICE,"bold")}{t(590,786,"in the 2020s",20,GREY)}

  <!-- RIGHT TOP — four formulas -->
  {t(840,262,"Not one formula&#8217;s quirk",30,NAVY,"bold")}
  {t(840,282,"",1,GREY)}
  {legend(1010,262,16,128)}
  {chr(10).join("  "+g for g in grid2)}
  {rows}
  <line x1="840" y1="608" x2="1520" y2="608" stroke="{VANILLA}" stroke-width="3"/>

  <!-- RIGHT BOTTOM — inaugurals -->
  {t(840,640,"Inaugurals slid too, noisier",24,NAVY,"bold")}
  <line x1="860" y1="780" x2="1520" y2="780" stroke="{GREY}" stroke-width="2"/>
  {lol}
  {t(xs4(ifirst[0]),ys4(ifirst[1])-10,f"{ifirst[1]:.1f}",15,NAVY,"bold",anchor="middle")}
  {t(xs4(imax[0]),ys4(imax[1])-10,f"{imax[1]:.1f}",15,"#CA6702","bold",anchor="middle")}
  {t(xs4(imin[0]),ys4(imin[1])-10,f"{imin[1]:.1f}",15,"#CA6702","bold",anchor="middle")}
  {t(xs4(ilast[0]),ys4(ilast[1])-10,f"{ilast[1]:.1f}",15,SPICE,"bold",anchor="middle")}
  {t(xs4(1913),800,"1913",14,GREY,anchor="middle")}{t(xs4(2025),800,"2025",14,GREY,anchor="middle")}

  <rect x="0" y="{H-70}" width="{W}" height="70" fill="{NAVY}"/>
  {t(80,H-34,"@unwelcomedata",22,"#FFFFFF","bold")}
  {t(80,H-12,"Miller Center speech archive &#183; spoken era (1913+) &#183; absolute grades vary 2&#8211;5 levels by tool; the decline replicates.",16,AQUA)}
</svg>
'''
    return svg


# ───────────────────────── validation (parse SVG back, compare to DB) ─────────────────────────
def validate(d, tall, social):
    lines, ok = [], True

    def chk(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        lines.append(f"- {'PASS' if cond else 'FAIL'} — {name}" + (f" ({detail})" if detail else ""))

    spec = {
        "tall": dict(svg=tall, xs=Lin(1913, 2026, 150, 1120), ys=Lin(6, 20, 870, 570),
                     x2=Lin(8, 20, 260, 1120), xi=Lin(1913, 2025, 150, 1120), yi=Lin(4, 16, 2420, 2180)),
        "social": dict(svg=social, xs=Lin(1913, 2026, 130, 760), ys=Lin(6, 20, 640, 410),
                       x2=Lin(8, 20, 1010, 1520), xi=Lin(1913, 2025, 860, 1520), yi=Lin(4, 16, 780, 650)),
    }
    sotu = dict(d["sotu"])
    for name, s in spec.items():
        svg = s["svg"]
        # sparkline points
        pts = []
        for m in re.finditer(r'<polyline class="sotu" points="([^"]+)"', svg):
            for p in m.group(1).split():
                x, y = map(float, p.split(","))
                pts.append((round(s["xs"].inv(x)), s["ys"].inv(y)))
        errs = [abs(v - sotu[yr]) for yr, v in pts if yr in sotu]
        chk(f"{name}: sparkline has all {len(sotu)} yearly points", len(pts) == len(sotu), f"{len(pts)} parsed")
        chk(f"{name}: every sparkline point matches DB grade (max err {max(errs):.3f})", max(errs) < 0.05)
        chk(f"{name}: sparkline years match DB exactly", sorted(y for y, _ in pts) == sorted(sotu))
        # marked dots sit on real points
        dots = [(int(m.group(1)), float(m.group(2)), float(m.group(3))) for m in
                re.finditer(r'class="dot" data-year="(\d+)" cx="([\d.]+)" cy="([\d.]+)"', svg)]
        bad = [(yr) for yr, cx, cy in dots if abs(s["ys"].inv(cy) - sotu[yr]) > 0.05 or abs(s["xs"].inv(cx) - yr) > 0.5]
        chk(f"{name}: 4 marked dots (first/last/max/min) sit on real data points", len(dots) == 4 and not bad, str(dots and [d_[0] for d_ in dots]))
        # formula dots
        decs = {r[0]: r for r in d["dec"]}
        fcols = ["fk_grade", "smog_index", "gunning_fog", "coleman_liau"]
        fd = [(int(m.group(1)), m.group(2), float(m.group(3))) for m in
              re.finditer(r'class="fdot" data-decade="(\d+)" data-f="(\w+)" cx="([\d.]+)"', svg)]
        ferr = max(abs(s["x2"].inv(cx) - decs[dec][1 + fcols.index(fc)]) for dec, fc, cx in fd)
        chk(f"{name}: {len(fd)} formula dots (12 decades x 4) match DB decade averages (max err {ferr:.3f})",
            len(fd) == 48 and ferr < 0.05)
        # inaugural
        idt = [(int(m.group(1)), float(m.group(2)), float(m.group(3))) for m in
               re.finditer(r'class="idot" data-year="(\d+)" cx="([\d.]+)" cy="([\d.]+)"', svg)]
        inaug = dict(d["inaug"])
        ierr = max(abs(s["yi"].inv(cy) - inaug[yr]) for yr, cx, cy in idt)
        chk(f"{name}: {len(idt)} inaugural dots match DB (max err {ierr:.3f})", len(idt) == len(inaug) and ierr < 0.05)
    # tall-only bars + big numbers
    w10, w20 = d["wps"][1910][0], d["wps"][2020][0]
    bw = [float(x) for x in re.findall(r'<rect x="200" y="\d+" width="([\d.]+)"', tall)]
    chk("tall: sentence bars width = words x 26px", len(bw) == 2 and abs(bw[0] / 26 - w10) < 0.05 and abs(bw[1] / 26 - w20) < 0.05, f"{bw[0]/26:.2f}, {bw[1]/26:.2f}")
    chk("big numbers: 1913 and 2026 values in both renders",
        all(f"{sotu[y]:.1f}" in svg for svg in (tall, social) for y in (1913, 2026)))
    chk("headline: FK 1913 = 15.81, 2026 = 7.62, drop >= 5 grades", sotu[1913] == 15.81 and sotu[2026] == 7.62)
    chk("sentence length falls by more than half 1910s -> 2020s", w20 < w10 / 2, f"{w10} -> {w20}")
    return ok, lines


def render():
    from playwright.sync_api import sync_playwright
    jobs = [("infographic_presidential_readability.svg", "infographic_presidential_readability.png", 1200, 2590),
            ("infographic_presidential_readability_social.svg", "infographic_presidential_readability_social.png", 1600, 900)]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for sv, pn, w, h in jobs:
            html = f"<!doctype html><html><head><style>*{{margin:0;padding:0}}</style></head><body>{(DOCS/sv).read_text(encoding='utf-8')}</body></html>"
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg.set_content(html); pg.wait_for_timeout(300)
            pg.screenshot(path=str(DOCS / pn), clip={"x": 0, "y": 0, "width": w, "height": h}); pg.close()
            print("rendered", pn, w, h)
        b.close()


def main():
    d = load()
    tall, social = build_tall(d), build_social(d)
    (DOCS / "infographic_presidential_readability.svg").write_text(tall, encoding="utf-8")
    (DOCS / "infographic_presidential_readability_social.svg").write_text(social, encoding="utf-8")
    ok, lines = validate(d, tall, social)
    (ART / "INFOGRAPHIC-VALIDATION.md").write_text(
        "# Infographic data-mark validation — presidential-readability\n\n"
        "Every data mark in both renders parsed back out of the SVG and compared with a fresh DuckDB query.\n\n"
        + "\n".join(lines) + f"\n\n**Result: {'PASS' if ok else 'FAIL'}**\n", encoding="utf-8")
    print("\n".join(lines)); print("VALIDATION", "PASS" if ok else "FAIL")
    render()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
