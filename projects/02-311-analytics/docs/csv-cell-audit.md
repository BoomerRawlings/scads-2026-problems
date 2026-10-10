# Independent raw-capture CSV-cell audit

The actual run checked all nine exported columns for the 9,728-row October 2025 Brooklyn `Noise - Residential` cohort. Four retained export/recovery files produced **350,208 exact cell matches**, zero mismatches. The independently selected cohort included 9,705 original-polygon NTA assignments and 23 missing locations. [Actual receipt](../examples/evidence/csv-cell-audit-38029812736.json).

The [archived method](../tools/csv_cell_audit_38029812736.py) is the exact executed study code, SHA-256 `9d888346d4f0525d4fde175940eb921402ae1daf8712f815a4e9f83dda47a16e`. Its initial execution path was `runs/csv-cell-audit-38029812736.py`, recorded in the unchanged receipt (SHA-256 `d644bfe6bc1250bd15046242255264ea4bf6071f222c737601e382036f848c53`). The `tools/` copy preserves every byte; both locations resolve the same project root. This is a frozen method for this cohort, not a configurable general-purpose auditor.

The script streams the entire raw capture, verifies its hash, byte count, record count and strictly ascending unique identifiers, then selects the cohort without consulting exported IDs. It independently derives text values, UTC millisecond timestamps, elapsed administrative closure, CSV escaping and point-in-polygon assignments. It imports no application, normalizer, exporter or agent-oracle modules. Its contract-aware implementation shares Python timezone data and Shapely/GEOS with the application; it is not a blinded or independent-library GIS validation.

## Exact inputs

Paths are relative to the project root. Input bytes remain read-only.

| Input | Required bytes / SHA-256 |
|---|---|
| `data/real-capture-2025/april-october-2025.jsonl.gz` | 163,696,296; `a0a602baadb06df0ece450ab7b2398e52387bbc436c228ca7c653c497e7f0aba` |
| Decompressed JSONL stream; no full decompressed file needed | 1,306,911,416; `91d84eb6d02dafc402a892298ba92cb121e8e905a189fb75f31b19d4d43aeec7`; 2,133,268 records |
| `data/nta2020-26b.geojson` | 4,532,381; `5049760a4d0936e1d3dbf70d745e2cee4286bd163b11c702f15fa28db46a001e`; all 262 official polygons |
| Four original `*.csv` files in `runs/agent-campaign-38029812736/corpus/real-v1/measurement-work/runs/` | Each 1,139,937; `edb145176437c7d5eeb59c99a90553af2631deaf19662e4f55ed32596b40284c`; exact filenames listed in the receipt |

The CSV columns are `unique_key`, `created_date`, `complaint_type`, `descriptor`, `borough`, `agency`, `status`, `nta2020`, `closure_hours`. “Residential” describes the complaint type; there is no residential-NTA filter. Original latitude/longitude are preferred over lower-precision GeoJSON fallback coordinates.

## Reproduce without replacing evidence

Use a separate scratch project checkout with these exact inputs and the declared Shapely/tzdata dependencies. The measured environment was CPython 3.12.14, Shapely 2.1.2 and GEOS 3.13.1; the receipt also records the installed tzdata version. Ensure the scratch checkout does **not** already contain `examples/evidence/csv-cell-audit-38029812736.json`; preserve the published receipt in the canonical project. Run from the scratch project root:

```text
python tools/csv_cell_audit_38029812736.py
```

The frozen script refuses an existing output, enforces a 240-second deadline, limits individual raw lines to 4 MiB and retained cohort rows to 20,000, and writes only the new receipt. It stores no complete raw dataset or database. A reproduction records its actual method path and execution timing; it must not be substituted for the original execution receipt.

The four CSVs are byte-identical: 87,552 unique logical cells, observed in four actual artifacts. Qualification covers only this cohort. All its closure dates were unambiguous and nonnegative; no actual formula-escaping, exact polygon-boundary, invalid-date or null-closure edge cases occurred. Method self-checks do not qualify those absent real-data cases. Administrative closure remains distinct from first response or historical closure status.
