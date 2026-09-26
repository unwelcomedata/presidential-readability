# Data Sources — presidential-readability

Source standards are **tiered**:
- **Serious tier** (methodology invites scrutiny): use official government or
  authoritative primary sources only. Crowd-edited references (Wikipedia, etc.)
  are NOT used — credibility is the product.
- **Fun tier** (low-stakes pop-culture): crowd-sourced references (fan wikis,
  SuperSummary, etc.) and owner-as-primary (hand-collected counts from a book or
  broadcast) are fine — just cite them plainly below.

Document every data source here before ingesting it. Include enough detail
that someone else could independently locate and verify the original data.

---

## Source Template

Copy and fill in for each source. The **How the source collects the data**,
**How the source defines the data**, and **Methodology changes / series breaks**
sections are required — they are what keep our analysis honest and prevent
apples-to-oranges comparisons. Do not leave them blank; if something is genuinely
not applicable or unknown, write "N/A" or "unknown" so it's clear it was considered.

### [Source Name]
- **Publisher:** [Agency, organization, or author]
- **URL:** [Direct link to the file or page]
- **Format:** [CSV | JSON | HTML table | ZIP | PDF | hand-curated]
- **License:** [Public domain | CC0 | CC-BY | proprietary | etc.]
- **Fields used:** [Column names or description of what was extracted]
- **Coverage:** [Geographic scope, date range, or other relevant bounds]
- **How the source collects the data:** [How does the publisher actually gather it?
  Survey / administrative records / registration / model estimate / scraped, etc.
  For surveys: sampling frame, sample size, response rate. For counts: the universe
  and denominator. Who is included and who is excluded from the raw collection?]
- **How the source defines the data:** [How is the thing being measured *defined*?
  Spell out the judgment calls in what counts. Example: a "COVID death" can mean died
  *from* COVID (underlying cause) vs. died *with* COVID (contributing/any mention) —
  very different counts. Note the exact definition this source uses.]
- **Methodology changes / series breaks:** [Dates when the definition or collection
  method changed, and which time periods are therefore NOT directly comparable.
  If the whole series is consistent, say so explicitly. This is the flag that stops
  us from charting a pre-change number next to a post-change number as if they match.]
- **Known controversies / debates:** [Any contested measurement choices worth a
  footnote or caveat in a published chart. Optional but encouraged. "None known" is
  a valid answer once you've checked.]
- **Notes:** [Anything else — data-quality quirks, suppression rules, imputation, etc.]
- **Retrieved:** [YYYY-MM-DD]

---

## Sources

### Miller Center Presidential Speech Corpus
- **Publisher:** University of Virginia, Miller Center of Public Affairs
- **URL:** https://data.millercenter.org/miller_center_speeches.tgz
- **Format:** bulk gzipped tar (`.tgz`) expanding to `speeches/*.json` (one speech per file:
  transcript + title, date, president, document name/URL)
- **License:** Public domain (U.S. government works; Miller Center distributes the corpus as
  an open bulk download after deprecating its API)
- **Fields used:** `transcript` (the speech text — the readability input), `date`, `president`,
  `title` (used to classify speech type: inaugural, State of the Union / Annual Message, etc.)
- **Coverage:** 1789 → present; ~1,059 speeches across 45 presidents (as ingested for the
  sibling `presidential-speeches` project on 2026-09-25)
- **How the source collects the data:** editorial curation — the Miller Center selects and
  transcribes *major* speeches (set-piece addresses, not every utterance). It is a curated
  archive, not an exhaustive record.
- **How the source defines the data:** each JSON is one speech, with the delivered/prepared
  transcript. "Readability" is NOT a field in the source — it is computed by this project from
  the transcript (see the readability-methodology note below).
- **Methodology changes / series breaks:**
  - **Written-address vs broadcast era (~1913).** Pre-radio annual messages to Congress were
    *written documents*, not delivered oratory, and are systematically longer and more complex.
    This is a genuine break in what "a speech" is — the readability trend must mark it and not
    read the written era and the spoken era as one continuous line.
  - **Coverage density varies by era** — far more speeches for modern presidents than 19th-c.
    ones, so per-president/per-decade averages rest on very different sample sizes.
  - **Curation selection bias** — inclusion is an editorial choice; the corpus over-represents
    formal set-piece speeches, which affects any absolute readability level.
- **Known controversies / debates:** none specific to the corpus. The interpretive caveat is
  that readability formulas were designed for written prose (see below), so applying them to
  transcribed *spoken* speech is an approximation, not a measurement of how "hard" a speech
  sounded when heard.
- **Notes:** same corpus as the published `presidential-speeches` project; re-used for a
  different (readability) question. The transcript is dropped before export (it's the input,
  not a deliverable); the published dataset carries per-speech readability scores + metadata.
- **Retrieved:** 2026-09-26 (to be confirmed when 01-ingest runs; corpus last pulled for the
  sibling project 2026-09-25)

---

## Readability methodology (this project's core measurement choice)

Readability is **computed by this project**, not sourced, so the formula choice is a
methodology decision a skeptic will scrutinize — document it fully here and in the codebook.

- **Primary metric:** Flesch–Kincaid Grade Level (maps text to a U.S. school-grade reading
  level from syllables/word and words/sentence). Report at least one companion metric
  (Flesch Reading Ease, and optionally SMOG / Gunning Fog / Coleman–Liau) so the trend
  isn't an artifact of one formula.
- **Library:** to be pinned in `requirements.txt` at ingest time (e.g. `textstat`) OR a
  hand-rolled, transparent implementation of the FK formula — decide in `03-prepare` and
  record the exact version/definition here. Syllable counting is the fuzzy step; note the
  method used.
- **Caveats to carry into every chart/caption:**
  - Formulas were built for *written* prose; transcribed speech (especially unscripted) has
    different sentence structure — treat scores as a consistent *index*, not literal grade.
  - The written→spoken era break (above) dominates any raw 1789→present trend; segment it.
  - Sentence segmentation on historical transcripts is imperfect (punctuation conventions
    changed) and directly affects words/sentence — sentences are counted with **NLTK punkt**,
    not textstat's naive splitter.
  - **HTML line-break tags in transcripts (fixed 2026-09-26).** Some Miller Center transcripts
    use `<br />` tags in place of sentence punctuation between paragraphs. Left in, they merge
    text into 250-word "sentences" and inflate the grade (the Nixon 1970–72 SOTUs read as
    grade ~26 instead of ~11). `02-clean` now converts block-level HTML tags to sentence
    boundaries before scoring, so words-per-sentence reflects real sentences.
  - **Absolute levels are tokenizer- and source-dependent.** Independent readability series that
    use the UCSB/American Presidency Project transcripts (rather than the Miller Center corpus)
    typically sit **2–5 grade points lower** in absolute terms, especially pre-1980, because of
    differences in sentence-boundary detection and syllable counting. The **long-term decline
    replicates across all of them** — treat the grade values as a consistent *index*, not a
    literal grade, and state this in any published caption. (Cross-checked against Smart
    Politics / U. Minnesota, Berkeley datascience@berkeley, Guardian, Priceonomics, and the
    stateoftheunion.onetwothree.net full-corpus visualization — independent validation
    2026-09-26, verdict "Pass with notes".)

---

## Notes on Data Quality

- All source files are saved verbatim to `data/raw/` and never modified.
- Discrepancies between sources should be noted here and resolved explicitly.
- **Series breaks:** whenever a source changed its definition or method mid-series,
  document the break date under that source and treat pre/post as separate series —
  never chart or aggregate across a break without a visible caveat.
- **Definitions drive comparisons:** before comparing two numbers (across years,
  places, or sources), confirm they are defined the same way. If not, say so in the
  chart, the codebook, and any social copy.

---

## Source Provenance in DuckDB

Every table in `data/project.duckdb` has a corresponding entry in the
`_sources` metadata table:

```sql
SELECT * FROM _sources;
```
