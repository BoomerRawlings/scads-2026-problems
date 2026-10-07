"""Optional, indexed point-to-NTA enrichment using locally staged GeoJSON."""

import hashlib
import json
import math
from pathlib import Path

from .errors import AnalyticsError


class _JsonStream:
    """Decode a FeatureCollection one bounded feature at a time."""

    def __init__(self, stream):
        self.stream, self.buffer = stream, ""
        self.decoder = json.JSONDecoder()

    def peek(self):
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer:
                return self.buffer[0]
            self.buffer = self.stream.read(65536)
            if not self.buffer:
                return ""

    def token(self, expected):
        if self.peek() != expected:
            raise AnalyticsError("invalid_boundaries", "Malformed GeoJSON FeatureCollection.")
        self.buffer = self.buffer[1:]

    def value(self):
        self.peek()
        while True:
            try:
                value, consumed = self.decoder.raw_decode(self.buffer)
                self.buffer = self.buffer[consumed:]
                return value
            except json.JSONDecodeError:
                addition = self.stream.read(65536)
                if not addition:
                    raise AnalyticsError("invalid_boundaries", "Malformed or incomplete GeoJSON value.") from None
                self.buffer += addition
                if len(self.buffer) > 16 * 1024 * 1024:
                    raise AnalyticsError("budget_exceeded", "One GeoJSON feature or metadata value exceeds 16 MiB.")


def _features(path):
    with path.open(encoding="utf-8-sig") as stream:
        reader, metadata, keys = _JsonStream(stream), {}, set()
        reader.token("{")
        while reader.peek() != "}":
            key = reader.value()
            if not isinstance(key, str) or key in keys:
                raise AnalyticsError("invalid_boundaries", "Duplicate or invalid GeoJSON collection key.")
            keys.add(key)
            reader.token(":")
            if key == "features":
                reader.token("[")
                while reader.peek() != "]":
                    yield reader.value()
                    if reader.peek() == "]":
                        break
                    reader.token(",")
                    if reader.peek() == "]":
                        raise AnalyticsError("invalid_boundaries", "Trailing comma in GeoJSON features.")
                reader.token("]")
            else:
                metadata[key] = reader.value()
            if reader.peek() == "}":
                break
            reader.token(",")
            if reader.peek() == "}":
                raise AnalyticsError("invalid_boundaries", "Trailing comma in GeoJSON collection.")
        reader.token("}")
        if reader.peek() or metadata.get("type") != "FeatureCollection" or "features" not in keys:
            raise AnalyticsError("invalid_boundaries", "Expected one complete GeoJSON FeatureCollection.")
        crs = metadata.get("crs")
        if crs is not None:
            name = crs.get("properties", {}).get("name") if isinstance(crs, dict) else None
            if name not in {"urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326", "EPSG:4326"}:
                raise AnalyticsError("invalid_boundaries", "NTA boundaries must use WGS84 longitude/latitude coordinates.")


class NtaEnricher:
    def __init__(self, boundaries_path):
        try:
            import shapely
            from shapely.geometry import Point, shape
            from shapely.strtree import STRtree
            from shapely.errors import ShapelyError
        except ImportError:
            raise AnalyticsError("missing_dependency", "NTA enrichment requires the optional geo extra: pip install -e '.[geo]'.") from None
        if int(shapely.__version__.split(".")[0]) != 2:
            raise AnalyticsError("missing_dependency", "NTA enrichment requires Shapely 2.x; install the project's geo extra.")
        path = Path(boundaries_path)
        before = path.stat()
        if before.st_size > 256 * 1024 * 1024:
            raise AnalyticsError("budget_exceeded", "Boundary file exceeds the 256 MiB load limit; stage a suitable NTA boundary layer.")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self.boundary_sha256 = digest.hexdigest()
        self.boundaries_sha256 = self.boundary_sha256
        self._point = Point
        geometries, self._areas, names = [], [], {}
        try:
            for feature in _features(path):
                if len(geometries) >= 100000:
                    raise AnalyticsError("budget_exceeded", "NTA boundary file exceeds 100,000 features.")
                if not isinstance(feature, dict) or feature.get("type") != "Feature":
                    raise AnalyticsError("invalid_boundaries", "Every NTA boundary must be a GeoJSON Feature.")
                props = feature.get("properties") or {}
                code = props.get("NTA2020", props.get("nta2020"))
                name = props.get("NTAName", props.get("ntaname"))
                if not isinstance(code, str) or not code.strip() or not isinstance(name, str) or not name.strip():
                    raise AnalyticsError("invalid_boundaries", "NTA boundaries require NTA2020 and NTAName properties (or lowercase nta2020/ntaname).")
                code, name = code.strip(), name.strip()
                if code in names and names[code] != name:
                    raise AnalyticsError("invalid_boundaries", "A single NTA code has conflicting neighborhood names.")
                names[code] = name
                geometry = shape(feature.get("geometry"))
                if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
                    raise AnalyticsError("invalid_boundaries", "NTA geometry must be a valid nonempty Polygon or MultiPolygon.")
                xmin, ymin, xmax, ymax = geometry.bounds
                if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
                    raise AnalyticsError("invalid_boundaries", "NTA geometry is outside valid WGS84 coordinate bounds.")
                geometries.append(geometry)
                self._areas.append((code, name))
        except (AttributeError, TypeError, ValueError, UnicodeError, ShapelyError):
            raise AnalyticsError("invalid_boundaries", "NTA GeoJSON contains invalid properties or geometry.") from None
        if not geometries:
            raise AnalyticsError("invalid_boundaries", "NTA boundary collection is empty.")
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise AnalyticsError("source_changed", "Boundary file changed during loading; use a frozen local file.")
        self._tree = STRtree(geometries)
        self.feature_count = len(geometries)
        self.neighborhood_count = len(names)

    def enrich(self, record):
        """Return a copy. Shared borders/overlaps remain explicitly ambiguous."""
        if not isinstance(record, dict):
            raise AnalyticsError("invalid_record", "NTA enrichment expects a normalized record object.")
        result = {k: v for k, v in record.items() if k not in {"nta2020", "ntaname", "nta_join_status"}}
        flags = [flag for flag in record.get("quality_flags", []) if not flag.startswith("nta_")]
        location = record.get("location")
        if location is None:
            status = "missing_geometry"
        else:
            try:
                if not isinstance(location, dict) or any(isinstance(location.get(k), bool) for k in ("lat", "lon")):
                    raise ValueError()
                lat, lon = float(location["lat"]), float(location["lon"])
                if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    raise ValueError()
                point = self._point(lon, lat)
                # covered_by tests point against polygon and includes shared borders.
                matches = {self._areas[int(index)] for index in self._tree.query(point, predicate="covered_by")}
                if len(matches) == 1:
                    result["nta2020"], result["ntaname"] = next(iter(matches))
                    status = "matched"
                else:
                    status = "ambiguous" if matches else "unmatched"
            except (KeyError, TypeError, ValueError, OverflowError):
                status = "invalid_geometry"
        result["nta_join_status"] = status
        if status != "matched":
            flags.append("nta_" + status)
        result["quality_flags"] = sorted(set(flags))
        return result
