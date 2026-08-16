# DATA.md — Data sources and schema

## Source

`jfinder/data/journals.parquet` is built from the **OpenAlex** `/sources`
endpoint. OpenAlex data is licensed **CC0**.

- Endpoint: `https://api.openalex.org/sources`
- Filter: `type:journal,works_count:>100`
- Pagination: cursor pagination, 200 records/page
- Build script: `scripts/build_index.py` (never called at runtime)
- **Retrieval date: 2026-08-16** (122,851 journals)
- Rebuild: `python scripts/build_index.py`

Selected fields: `id, display_name, issn_l, issn, host_organization_name,
country_code, topics, summary_stats, works_count, is_oa, is_in_doaj, apc_usd`.

## Schema

| column | type | description |
|---|---|---|
| `openalex_id` | str | `S137773608` |
| `name` | str | journal name |
| `issn_l` | str | linking ISSN |
| `issn` | list[str] | all ISSNs |
| `publisher` | str | host organization name (may be null) |
| `country` | str | ISO-2 (may be null) |
| `topics` | list[str] | topic labels (BM25 corpus) |
| `h_index` | int | OpenAlex h-index |
| `citedness_2y` | float | 2-year mean citedness |
| `works_count` | int | total works |
| `quartile` | str | `Q1`–`Q4`, computed within field |
| `is_oa` | bool | |
| `in_doaj` | bool | OpenAlex `is_in_doaj` field |
| `apc_usd` | float | null = **unknown** (not free) |
| `built_at` | str | ISO date; identical across all rows |

## Derived fields

- **Quartile**: group by primary topic (first topic), then `qcut(4)` on
  `h_index` within each group. Groups with fewer than four distinct values
  default to `Q4`.
- **Cost class** (`jfinder/data.py` → `cost_class`): `oa_paid` (OA, author
  pays), `diamond` (OA + DOAJ + no/zero APC), `oa_unknown` (OA but APC unknown
  — displayed as "APC unknown", never "free"), `subscription` (a hybrid OA
  option may exist).
- **Unverified flag** (`flag`): a heuristic *warning*, not an accusation, for
  journals that are OA, not in DOAJ, with APC > $1,500 and h-index < 15.

## Warnings

- APC prices are list prices (OpenAlex/DOAJ); verify actual prices on the
  journal's website.
- **No SCImago-derived columns are present in this repository** (SJR, SJR
  quartile, Scimago categories, cites-per-doc). SCImago data is
  non-commercial-only and conflicts with the MIT license.
