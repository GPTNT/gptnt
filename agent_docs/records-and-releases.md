# Records and releases

Use this guide when changing recorded experiment output, database code, package placement, or
release metadata.

## Recorded outputs

<!-- rule:gptnt:901 -->

- Treat the fields and observations written to experiment Parquet files as a compatibility boundary.
  A change to that output requires explicit agreement on the new schema and its effect on existing
  readers and recorded files. Keep the current schema when the task changes only the recorder's
  implementation (`src/gptnt/experiments/recorder/`).
