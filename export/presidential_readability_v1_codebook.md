# presidential-readability — Dataset Codebook
Generated: 2026-09-26

## Columns

### `president`
- **Type**: `str`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: President who delivered the speech.

### `speech_date`
- **Type**: `str`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Date of the speech (YYYY-MM-DD).

### `year`
- **Type**: `int64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Calendar year of the speech.

### `title`
- **Type**: `str`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Speech title as given by the Miller Center.

### `speech_type`
- **Type**: `str`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Institutional type (Inaugural Address, State of the Union, Annual Message, etc.).

### `is_sotu_series`
- **Type**: `bool`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: True if part of the unified State-of-the-Union series (Annual Message <=1928 + State of the Union 1929+).

### `delivery_mode`
- **Type**: `str`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: 'written' (pre-1913, clerk-read documents) or 'spoken' (1913+, delivered oratory) — the readability series break.

### `url`
- **Type**: `str`
- **Non-null**: 262 / 267 (98.1%)
- **Description**: Miller Center source URL for the speech.

### `source_file`
- **Type**: `str`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Filename of the source JSON in the corpus (provenance).

### `fk_grade`
- **Type**: `Float64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Flesch-Kincaid Grade Level (LEAD metric): approximate U.S. school grade required to read the text. Higher = more complex.

### `flesch_reading_ease`
- **Type**: `Float64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Flesch Reading Ease (0-100): higher = easier to read.

### `smog_index`
- **Type**: `Float64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: SMOG grade-level readability formula.

### `gunning_fog`
- **Type**: `Float64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Gunning Fog grade-level readability formula.

### `coleman_liau`
- **Type**: `Float64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Coleman-Liau grade-level readability formula.

### `word_count`
- **Type**: `Int64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Word (lexicon) count of the transcript, per textstat.

### `sentence_count`
- **Type**: `Int64`
- **Non-null**: 267 / 267 (100.0%)
- **Description**: Sentence count of the transcript, per textstat (the denominator in words/sentence).

## Notes

Source: University of Virginia Miller Center presidential speech corpus (public domain), https://data.millercenter.org/miller_center_speeches.tgz. Readability computed with textstat==0.7.13 (Flesch-Kincaid + companions). CAVEAT: readability formulas were built for written prose; scores on transcribed spoken speech are a consistent index, not a literal grade. Segment trends at the written->spoken (~1913) delivery break. Coverage density varies sharply by era.
