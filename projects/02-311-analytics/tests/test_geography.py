import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from analytics311.errors import AnalyticsError
from analytics311.geography import NtaEnricher, _features


def feature(code="BK0101", name="Synthetic West", west=-74, east=-73):
    return {"type": "Feature", "properties": {"NTA2020": code, "NTAName": name},
            "geometry": {"type": "Polygon", "coordinates": [[[west, 40], [east, 40], [east, 41], [west, 41], [west, 40]]]}}


@unittest.skipUnless(importlib.util.find_spec("shapely"), "optional Shapely geo extra not installed")
class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "boundaries.geojson"

    def write(self, features):
        self.path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
        return NtaEnricher(self.path)

    def test_matches_official_property_names_and_preserves_input(self):
        enricher = self.write([feature()])
        record = {"unique_key": "1", "location": {"lon": -73.5, "lat": 40.5}, "quality_flags": []}
        output = enricher.enrich(record)
        self.assertEqual(output["nta2020"], "BK0101")
        self.assertEqual(output["ntaname"], "Synthetic West")
        self.assertEqual(output["nta_join_status"], "matched")
        self.assertNotIn("nta2020", record)
        self.assertEqual(enricher.boundary_sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_shared_border_is_ambiguous_not_arbitrarily_assigned(self):
        enricher = self.write([feature(), feature("BK0102", "Synthetic East", -73, -72)])
        output = enricher.enrich({"location": {"lon": -73, "lat": 40.5}, "nta2020": "stale", "ntaname": "stale"})
        self.assertEqual(output["nta_join_status"], "ambiguous")
        self.assertNotIn("nta2020", output)
        self.assertIn("nta_ambiguous", output["quality_flags"])

    def test_missing_invalid_and_unmatched_geography_remain_visible(self):
        enricher = self.write([feature()])
        for record, status in (({}, "missing_geometry"), ({"location": {"lat": 99, "lon": 0}}, "invalid_geometry"),
                               ({"location": {"lat": 42, "lon": -73.5}}, "unmatched")):
            with self.subTest(status=status):
                result = enricher.enrich(record)
                self.assertEqual(result["nta_join_status"], status)
                self.assertNotIn("nta2020", result)

    def test_polygon_holes_and_multipolygons(self):
        polygon = feature()
        polygon["geometry"]["coordinates"].append([[-73.8, 40.2], [-73.2, 40.2], [-73.2, 40.8], [-73.8, 40.8], [-73.8, 40.2]])
        polygon["geometry"] = {"type": "MultiPolygon", "coordinates": [polygon["geometry"]["coordinates"]]}
        enricher = self.write([polygon])
        self.assertEqual(enricher.enrich({"location": {"lon": -73.5, "lat": 40.5}})["nta_join_status"], "unmatched")
        self.assertEqual(enricher.enrich({"location": {"lon": -73.9, "lat": 40.5}})["nta_join_status"], "matched")

    def test_duplicate_same_area_features_do_not_create_false_ambiguity(self):
        enricher = self.write([feature(), feature()])
        self.assertEqual(enricher.enrich({"location": {"lon": -73.5, "lat": 40.5}})["nta_join_status"], "matched")

    def test_missing_nta_metadata_rejected(self):
        invalid = feature()
        invalid["properties"] = {"ZIP": "10001"}
        with self.assertRaises(AnalyticsError) as caught:
            self.write([invalid])
        self.assertEqual(caught.exception.code, "invalid_boundaries")

    def test_lowercase_schema_allowed(self):
        value = feature()
        value["properties"] = {"nta2020": "BK0101", "ntaname": "Synthetic"}
        self.assertEqual(self.write([value]).neighborhood_count, 1)

    def test_invalid_collection_and_projected_crs_rejected(self):
        self.path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature()],
                                      "crs": {"properties": {"name": "EPSG:2263"}}}), encoding="utf-8")
        with self.assertRaises(AnalyticsError):
            NtaEnricher(self.path)


class StreamingParserTests(unittest.TestCase):
    def test_feature_stream_spanning_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "features.geojson"
            features = [feature(str(i)) for i in range(1000)]
            path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
            self.assertEqual(len(list(_features(path))), 1000)

    def test_partial_and_duplicate_collections_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "features.geojson"
            for text in ('{"type":"FeatureCollection","features":[',
                         '{"type":"FeatureCollection","features":[],"features":[]}',
                         '{"type":"FeatureCollection","features":[],}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(AnalyticsError):
                    list(_features(path))


if __name__ == "__main__":
    unittest.main()
