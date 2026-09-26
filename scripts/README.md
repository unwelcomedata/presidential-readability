# Scripts

Reproduce and verify the published dataset.

## Prerequisites

```bash
pip install -r ../requirements.txt
```

Python 3.11+. The first run downloads the Miller Center corpus (cached afterward) and the
NLTK punkt tokenizer.

## Reproduce (raw → export)

```bash
python scripts/reproduce.py
```

Runs the full pipeline in order — ingest (Miller Center corpus) → clean (parse, classify,
strip HTML, dedupe) → prepare (filter to oratory, score readability with Flesch–Kincaid +
companions via NLTK punkt) — and writes `export/presidential_readability_v1.*` plus its
codebook. Uses the same `src/` logic the analysis used; standalone (no notebooks).

## Verify

```bash
python scripts/validate_charts.py
```

Re-derives the chart facts straight from the source, checks the export matches, and confirms
the rendered social/web chart sets line up. Exits 0 when everything checks out.
