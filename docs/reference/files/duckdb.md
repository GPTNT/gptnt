---
title: DuckDB result database
tags:
  - Results
---

# DuckDB result database

`gptnt build-db` creates a local query database from player-record Parquet. The database has
exactly two base tables, no views, and no database-version or metadata table. Compatibility is an
exact ordered comparison of the base-table names, columns, types, and nullability.

## `experiment_step`

| Column | DuckDB type | Column | DuckDB type |
| ------ | ----------- | ------ | ----------- |
| `step` | `INTEGER NOT NULL` | `timestamp` | `DOUBLE NOT NULL` |
| `role` | `VARCHAR NOT NULL` | `session_id` | `UUID NOT NULL` |
| `player_uuid` | `UUID NOT NULL` | `player_name` | `VARCHAR NOT NULL` |
| `output` | `VARCHAR NOT NULL` | `raw_output` | `VARCHAR` |
| `thoughts` | `VARCHAR` | `input_messages` | `BLOB` |
| `new_messages` | `BLOB` | `bomb_state` | `JSON` |
| `observation` | `BLOB` | `usage` | `BLOB NOT NULL` |
| `num_prompt_truncations` | `INTEGER NOT NULL` | `error_type` | `VARCHAR[]` |
| `is_reflection` | `BOOLEAN` | | |

These are the player-record step rows. `session_id` joins the table to `experiment_summary`.

## `experiment_summary`

The declared and recorded columns are:

| Group | Columns |
| ----- | ------- |
| Outcome | `outcome`, `seconds_remaining`, `strike_count`, `num_modules_solved`, `is_hard_crash` |
| Provenance | `gptnt_version`, `release_commit`, `release_tag`, `protected_content_modified` |
| Suite and mission | `mission_spec`, `mission_set`, `attempt`, `suite_name`, `suite_revision`, `suite_digest`, `manual_profile` |
| Protocol and names | `defuser_protocol`, `defuser_name`, `expert_protocol`, `expert_name` |
| Runtime instance | `session_id`, `expert_uuid`, `defuser_uuid`, `game_uuid`, `start_time` |
| Capabilities | `defuser_capabilities`, `expert_capabilities` |

Persisted computed columns are:

```text title="Computed columns"
is_solved  is_strike_out  is_timed_out  is_detonated
fingerprint  attempt_name  seed  communication_style  modules
defuser_capability_fingerprint  expert_capability_fingerprint
defuser_has_manual  mission_key
```

All required scalar types and nullability are generated from `ExperimentSummary`. Nested mission,
manual, protocol, and capability objects are DuckDB `JSON`. `modules` is `VARCHAR[]`.

## Query examples

```sql title="Summary counts"
SELECT suite_name, suite_revision, defuser_name, outcome, count(*) AS runs
FROM experiment_summary
GROUP BY ALL
ORDER BY suite_name, defuser_name, outcome;
```

```sql title="Recorded steps"
SELECT summary.attempt_name, step.role, count(*) AS recorded_steps
FROM experiment_summary AS summary
JOIN experiment_step AS step USING (session_id)
GROUP BY ALL
ORDER BY summary.attempt_name, step.role;
```

`build-db` inserts source step rows and derived summaries in one transaction. Rebuilding an
incompatible database requires `--delete-existing-db`. A `.duckdb.wal` file is transient and not a
third application table or a portable result format.
