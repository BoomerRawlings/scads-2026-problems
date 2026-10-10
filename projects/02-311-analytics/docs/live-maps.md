# Live Maps qualification

`tools/live_maps.py` is an explicit-target integration runner. It starts no
services, installs nothing, and supports the pinned Elasticsearch/Kibana 9.5.5
contract only. Its deterministic tests are not evidence of a live import or
render. `provision` creates new objects; do not point it at indices owned by
another run. Existing objects are never overwritten or deleted.

Provision requires an actual `version.number` from Kibana `/api/status`.
Kibana 9.5.5 can return only `status.overall.level` for callers without status
access, including the unsecured local CI configuration. An `available` response
does not establish the version. Use credentials with the `monitor` cluster
privilege; for the isolated loopback-only test container, set
`STATUS_ALLOWANONYMOUS: "true"` (`status.allowAnonymous=true`) before startup.
The runner reports `kibana_status_version_unavailable` and performs no index or
saved-object writes when this evidence is absent. See the pinned
[status route](https://github.com/elastic/kibana/blob/v9.5.5/src/core/packages/status/server-internal/src/routes/status.ts)
and [status settings](https://www.elastic.co/docs/reference/kibana/configuration-reference/general-settings).

The saved-object format derives from official versioned source, not guessed
object exports: [sample objects](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/server/sample_data/ecommerce_saved_objects.js),
[layer schema](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/server/content_management/schema/v1/layer_schemas/layer_schemas.ts),
[search-source schema](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/server/content_management/schema/v1/source_schemas/es_source_schemas.ts),
[join-source schema](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/server/content_management/schema/v1/source_schemas/es_join_source_schemas.ts),
and [joined metric keys](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/common/get_agg_key.ts).
The saved-object CRUD route is deprecated; successful creation/readback is a
mandatory gate, and a future replacement must be qualified against its version.
The Maps Inspector selectors are used by
[Kibana's GIS tests](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/test/functional/page_objects/gis_page.ts)
and [Inspector tests](https://github.com/elastic/kibana/blob/v9.5.5/src/platform/test/functional/services/inspector.ts).
The explicit test target must enable `xpack.maps.showMapsInspectorAdapter: true`
and `xpack.maps.preserveDrawingBuffer: true` in `kibana.yml` or native CLI flags,
then restart before verification. These are the pinned
[functional-test settings](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/test/functional/config.base.ts).
The [configuration](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/server/config.ts)
defaults both to false; without the first, the
[adapter constructor](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/public/reducers/non_serializable_instances.js)
omits Map details. The pinned Docker entrypoint does not allowlist these settings,
so environment variables alone do not enable them. Real run `38027551047`
loaded the saved maps and visible geometry but failed this Inspector gate;
its screenshots and CSV checks do not establish rendered-value parity.

Maps registers `MAPS_APP_LOCATOR` in the browser. The server short-URL API
requires a server-registered locator, so it cannot accept that ID directly.
The bridge retains the original Maps locator payload and uses
`LEGACY_SHORT_URL_LOCATOR` for server storage. See the pinned
[Maps registration](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/public/plugin.ts),
[short-URL route](https://github.com/elastic/kibana/blob/v9.5.5/src/platform/plugins/shared/share/server/url_service/http/short_urls/register_create_route.ts),
[redirect parameters](https://github.com/elastic/kibana/blob/v9.5.5/src/platform/plugins/shared/share/common/url_service/locators/redirect/format_search_params.ts),
and [legacy URL locator](https://github.com/elastic/kibana/blob/v9.5.5/src/platform/plugins/shared/share/common/url_service/locators/legacy_short_url_locator.ts).
The link uses the returned object ID at `/goto/{id}`; a slug is never passed
to that route. Its legacy branch performs a full browser navigation.
See the pinned [redirect manager](https://github.com/elastic/kibana/blob/v9.5.5/src/platform/plugins/shared/share/public/url_service/redirect/redirect_manager.ts).
HTTP failures retain status, method, and API path in the render receipt;
arbitrary server bodies and credentials are omitted.

Kibana **9.5.5** has a locator/router mismatch, confirmed by the blank Create
screen and absent Maps searches in real run `38025638157`. Its locator emits
`/map#/{mapId}`, but the router matches the exact `/map` creation route before
its legacy hash redirect. `mapId` is the correct locator parameter; renaming it
would discard the saved-map identity. This exact version therefore uses
`/app/maps/map/{mapId}#/?_g=...&_a=...` inside the legacy short URL. The canonical
path loads the saved object. State remains in the **fragment query**, since
MapApp's URL storage retains `useHashQuery=true`; `useHash=false` disables
session-storage state hashes, not the fragment query. Complete DSL filters,
query, time range and optional refresh interval are Rison encoded unchanged;
pinned filters go to `_g`, other filters to `_a`. Unqualified locator options
such as ad-hoc data views and initial layers fail closed. No KQL translation
or implicit date selection is introduced.

This narrow bridge follows source commit
`a2890159e2486503b9e3a0c6f422b153a746651a`:
[locator](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/public/locators/map_locator/get_location.ts),
[router](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/public/render_app.tsx),
[MapApp](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/public/routes/map_page/map_app/map_app.tsx),
[storage defaults](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/src/platform/plugins/shared/kibana_utils/public/state_sync/state_sync_state_storage/create_kbn_url_state_storage.ts),
and [state reader](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/src/platform/plugins/shared/kibana_utils/public/state_management/url/kbn_url_storage.ts).
`tests/fixtures/kibana-9.5.5-map-url.json` retains exact references and encoded
fixtures independently decoded by the upstream `rison-node 2.1.1` parser, including
escaped text, nested selections, dates, coordinates and JSON primitives.
Other versions keep the versioned browser locator `/app/r/?l=...&v=...&p=...`
transport; they are not qualified by the 9.5.5 integration runner or this fix.

## Provision

Start with a frozen source index and its validated profile. Its result index
must be a fresh concrete index. Obtain and retain the official NTA2020 GeoJSON
and provenance receipt before this command; the provisioner retains its SHA256.
Its file hash must equal the source manifest's `geography.nta_version`, binding
the displayed boundaries to the actual point assignment. It accepts lower-case
NYC properties `nta2020`, `ntaname`, `ntatype` and creates
an immutable geo-shape boundary index. Nonresidential polygons remain available
as geometry; the selected analytical result determines which groups are joined.

```sh
python tools/live_maps.py provision \
  --config config/live.json --boundaries data/nta2020-26b.geojson \
  --boundary-index nyc311-nta2020-26b-v1 \
  --output-config runs/maps-profile.json --output runs/maps-provision.json
```

The generated profile points to three exact-index data views without time
fields and reusable request/trend maps. No EMS basemap or external tiles are
used. Request layers respect saved DSL filters and report missing locations.
The boundary source ignores request/result filters; its NTA terms join applies
the result filter to the dedicated result index. `max` of each metric selects
the single immutable result document for each neighborhood. The map styles
`rate_change`, measured in requests per calendar day.

Trend publication revalidates the saved comparison against the current
manifest and exact period bounds. A validated frozen `reconciled_observed_snapshot`
certificate qualifies these comparisons while `coverage_complete` remains false.
The map response preserves that scope and its population/reporting caveat;
a saved scope label without a matching certificate cannot authorize publication.

## Render and compare

Install Playwright and its Chromium dependency on the explicit test target.
Prepare an **independent** expectation from the captured data, not by copying
the service result or Kibana response. The runner records its hash/reference,
but cannot establish reference independence by itself. Its intended scope is a
bounded cohort drawn from the real million-record index, not rendering millions
of markers at once. The exact source cohort and CSV must contain at most 10,000
rows and the CSV at most 16 MiB.

Request expectation:

```json
{
  "dataset_version": "qualified-capture-version",
  "reference": {"kind": "independent-sqlite-query", "sha256": "SHA256_OF_REFERENCE_RECEIPT"},
  "source_count": 3,
  "unique_keys": ["key1", "key2", "key3"],
  "mapped_unique_keys": ["key1", "key2"]
}
```

Trend expectation replaces the three count/ID properties with `groups`, a map
of NTA code to all five values `baseline_count`, `current_count`,
`absolute_change`, `relative_change`, `rate_change`; use `null` for undefined
relative change. Set `excluded_group_count` for CSV rows missing an NTA.
The CSV is a completed records export for requests or aggregate export for
trends, with the same saved result and selection.

```sh
python tools/live_maps.py render --config runs/maps-profile.json \
  --result-id SAVED_RESULT_ID --mode requests \
  --expectation runs/point-reference.json --csv runs/COMPLETED_EXPORT.csv \
  --output-dir runs/render-points
```

Use `--mode neighborhood_trends` for the joined map, and repeat `--group-id`
to qualify an explicit saved-group selection. Cover both all-matching and
selected-groups cases during acceptance.

The browser opens the actual short URL, requires the expected saved-map path
before inspecting layers, then waits for its exact named layer in `mapLayerTOC`
and for all `.euiLoadingSpinner` descendants to detach before opening Inspector.
This mirrors the pinned [GIS functional-test loading sequence](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/test/functional/page_objects/gis_page.ts#L128-L165)
under the remaining original render deadline. Loading indicators alone do not
qualify data: the complete independent source/metric checks remain mandatory.
This sequencing avoids opening the large highlighted style while the layer is
still loading. Real run `38030378224` passed point and selected-trend rendering,
but its full-trend Inspector timed out after an initial empty style; those failed
results remain retained, and only a fresh actual run can qualify the change.
Every blocking navigation/Inspector action, including the Mapbox style tab,
close button and final screenshot, receives the remaining shared deadline and
is checked again afterward. It does not receive a fresh per-action budget.
The close control uses pinned Inspector's exact [Close Inspector accessible name](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/src/platform/plugins/shared/inspector/public/plugin.tsx), scoped to its flyout.
Run `38031560273` passed loading readiness but both trend maps hit the prior
implicit 30-second tab-click timeout; failure screenshots subsequently showed
the style and polygon map. That run remains failed. The default qualification
deadline stays 120 seconds. A failed run may additionally spend at most a
requested 5 seconds capturing a diagnostic screenshot, followed by browser
cleanup; this is outside qualification time and is reported separately in
browser diagnostics. Cleanup and diagnostic capture explain why raw stage
elapsed time can exceed the qualification deadline.
The browser captures actual search bodies,
requires the saved DSL filter in a browser search, and opens Inspector's Map
details. It compares the **rendered style's GeoJSON source** IDs or joined
metrics with the independent expectation and CSV; a server response alone
does not pass. The trend style must reference the declared joined metric.
It then closes Inspector and saves the visible map screenshot. Request bodies,
rendered style, screenshot and a machine-readable receipt remain in the output
directory. Reference membership and numeric disagreement, missing Inspector
data, absent DSL, application error or absent canvas fail closed. Timeout and
UI incompatibility leave `rendered_parity_verified=false`; failed screenshots
aid diagnosis. A passing bounded-map check never sets overall release acceptance.
`browser-diagnostics.json` and the render receipt retain the last browser stage,
final path, expected saved-map ID, path-identity check, and bounded error types.
Query/fragment state, credentials and raw DOM are omitted from these diagnostics.
The style reader targets only `code[data-code-language="json"]` inside the
Inspector and reads its `textContent`. In pinned EUI116.5.0, the surrounding
code-block wrapper also contains screen-reader labels and no-copy markers;
its complete `innerText` is not JSON. `textContent` also avoids forcing layout
of the large highlighted polygon text. Kibana's
[MapDetails](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/public/inspector/map_adapter/map_details.tsx)
does not enable Copy or virtualization. EUI's
[code block](https://github.com/elastic/eui/blob/v116.5.0/packages/eui/src/components/code/code_block.tsx)
and [line renderer](https://github.com/elastic/eui/blob/v116.5.0/packages/eui/src/components/code/utils.tsx)
preserve the complete JSON text and newlines in this code element. The read uses
the remaining declared render deadline and retains the observed UTF-8 byte count,
SHA256, and any JSON error position, without retaining non-JSON raw text. The
32 MiB style limit and full source/metric checks remain in force. Real run
`38028955870` reached Map details and verified 242 live document identities but
failed the old wrapper-text extraction; it remains failed evidence until rerun.

Kibana loads tooltip fields lazily. The initial point GeoJSON can therefore omit
`unique_key` while retaining Elasticsearch `_id` and `_index`. Our ingester
assigns `_id=unique_key`; the live verifier additionally reads the bounded
independent located-ID set from the actual frozen index and requires that
each `_id` equals its stored `unique_key`. It then compares rendered metadata
against that exact index and the independent IDs. If a rendered `unique_key`
is present it must also agree. Missing IDs, foreign indices, duplicates,
partial searches and mismatches fail closed. This follows the pinned
[ES source metadata handling](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/public/classes/sources/es_search_source/es_search_source.tsx)
and [GeoJSON conversion](https://github.com/elastic/kibana/blob/a2890159e2486503b9e3a0c6f422b153a746651a/x-pack/platform/plugins/shared/maps/common/elasticsearch_util/elasticsearch_geo_utils.ts).
The additional ES read proves document identity; it does not replace the
required Inspector source, browser filter, geometry, or screenshot evidence.

Kibana adds flagged centroid Points alongside polygons for labels and symbols.
The checker separates only these flagged companions, verifies each against its
polygon's ID, NTA, and all five joined metrics, and counts the polygon once.
Unflagged points, orphan/mismatched centroids, and duplicate polygons still fail.
This follows the pinned [centroid implementation](https://github.com/elastic/kibana/blob/v9.5.5/x-pack/platform/plugins/shared/maps/public/classes/layers/vector_layer/geojson_vector_layer/get_centroid_features.ts).

Rendered-source checks establish the values supplied to visible layers, not
human perceptual accuracy or exhaustive pixel-level map correctness. Inspect
the retained screenshot before publishing a visual acceptance claim. Browser
WebGL may use software rendering on CI; its speed is not end-user GPU evidence.
