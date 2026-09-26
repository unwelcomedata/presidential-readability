# Scripts — Pipeline Run Order

Full rebuild from raw data to export. Each step depends on the previous.

## Prerequisites

- Python 3.11+ with packages from `requirements.txt`
- `data/raw/` populated with source files (see SOURCES.md)
- Playwright + Chromium installed if any source uses `js_render: true`

## Run order

```bash
# 1. Ingestion — fetch all sources → data/raw/ → DuckDB tables
python scripts/ingest_all.py

# 2. Cleaning — standardize raw tables → data/interim/ (Parquet)
python scripts/clean_all.py

# 3. Export — join clean tables → export/ (CSV, Excel, Parquet + codebook)
python scripts/prepare_export.py

# 4. Validate — re-check chart data before publishing (REQUIRED gate)
python scripts/validate_charts.py   # must exit 0 ("safe to publish")
```

## ⭐ Pre-publish validation gate (REQUIRED before going public)

Every project must ship a `scripts/validate_charts.py` that re-derives what each
published chart should show, straight from the DuckDB source, and **exits non-zero
on any failure**. Run it and confirm exit 0 before curating the `release` branch
(see `.kiro/steering/public-release.md` → "Pre-publish data-validation gate"). It
must assert, at minimum:

- each published `export/*.csv` still matches its DuckDB source table (no drift);
- the headline chart facts (top item per chart + a spot-check value) are unchanged;
- structural invariants (row counts, sums that must reconcile, ordering).

Write it as you build the charts — assert the EXACT figures the charts display, so
a silent data change (or a bad methodology swap) can't ship unnoticed. A project
without this script is not releasable.

## Conventions

- **One script per pipeline stage.** Don't accumulate one-off scripts — if logic
  is absorbed into a main script, delete the original.
- **Only the current export version lives in `export/`.** Tag old versions in git.
- **Interim parquets must 1:1 match their DuckDB table names.** When you rename a
  table, rename or delete the corresponding parquet.
- **Document run order here** whenever you add a new script.

## Script descriptions

| Script | Purpose | Inputs | Outputs |
|--------|---------|--------|---------|
| `ingest_all.py` | Fetch and load all data sources | `config.yaml`, web | DuckDB tables, `data/raw/` |
| `clean_all.py` | Standardize and quality-check | DuckDB raw tables | `data/interim/*.parquet` |
| `prepare_export.py` | Build final joined dataset | DuckDB clean tables | `export/*` |
| `validate_charts.py` | Pre-publish gate: re-check chart data vs DuckDB | DuckDB + `export/*.csv` | exit 0/non-zero |

## Adding a new script

1. Add it to the run-order table above
2. Ensure it reads from DuckDB (not from other scripts' intermediate files)
3. Ensure it writes its output to DuckDB and/or interim parquet
4. Update the `_sources` metadata table if ingesting new data
