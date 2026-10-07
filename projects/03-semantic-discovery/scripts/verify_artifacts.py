"""Verify built artifacts against current runtime source and preserve compact proof.

No downloads, installation, source processing, or modification of built packages.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "reports/build-verification.json")
    args = parser.parse_args()
    wheelhouse = args.wheelhouse.resolve()
    manifest = read(wheelhouse / "manifest.json")
    for item in manifest["wheels"]:
        require(sha(wheelhouse / "wheels" / item["file"]) == item["sha256"], "Wheel bytes changed")
    wheel = next(item for item in manifest["wheels"] if item["name"] == "vopt-discovery")
    runtime_files = sorted(path for path in (ROOT / "vopt").rglob("*") if path.is_file()
        and "__pycache__" not in path.parts and path.suffix in {".py", ".js", ".html", ".css"})
    with zipfile.ZipFile(wheelhouse / "wheels" / wheel["file"]) as archive:
        for path in runtime_files:
            name = path.relative_to(ROOT).as_posix()
            require(archive.read(name) == path.read_bytes(), f"Wheel does not match current runtime: {name}")
        require(not any(name.startswith(("data/", "runs/", "examples/", "reports/")) for name in archive.namelist()),
            "Research material in runtime wheel")
    profiles = {}
    for profile in ("discovery", "extraction"):
        directory = getattr(args, profile).resolve()
        proof = read(directory / "proof-portable.json")
        cold = read(wheelhouse / f"proof-{profile}.json")
        require(proof["status"] == cold["status"] == "passed", "Qualification failed")
        require(proof["profile"] == cold["profile"] == profile, "Profile mismatch")
        require(proof["python_network_attempts"] == cold["python_network_attempts"] == 0, "Network attempts recorded")
        pm = read(directory / "portable-manifest.json")
        for item in pm["files"]:
            require(sha(directory / item["path"]) == item["sha256"], f"Portable file changed: {item['path']}")
        portable_wheel = next(item for item in read(directory / "wheelhouse-manifest.json")["wheels"] if item["name"] == "vopt-discovery")
        require(portable_wheel["sha256"] == wheel["sha256"], "Portable package has a stale runtime wheel")
        with zipfile.ZipFile(directory / "project-source.zip") as archive:
            require(not any(name.startswith(("data/", "runs/", "examples/", "reports/")) for name in archive.namelist()),
                "Private research material in portable runtime source")
        archive_path = directory.parent / (directory.name + ".zip")
        with zipfile.ZipFile(archive_path) as archive:
            for item in pm["files"]:
                require(hashlib.sha256(archive.read(item["path"])).hexdigest() == item["sha256"], "Portable ZIP differs from qualified runtime")
        profiles[profile] = {"path": directory.relative_to(ROOT).as_posix(), "archive_sha256": sha(archive_path),
            "archive_bytes": archive_path.stat().st_size, "unpacked_bytes": sum(item["bytes"] for item in pm["files"]),
            "cold_install": cold, "portable": proof}
    research = args.research.resolve()
    with zipfile.ZipFile(research) as archive:
        rm = json.loads(archive.read("research-manifest.json"))
        require(rm["contains_source_content"] and rm["human_gold"] is False, "Research artifact must identify source content and label limits")
        for item in rm["files"]:
            require(hashlib.sha256(archive.read(item["path"])).hexdigest() == item["sha256"], "Research archive hash mismatch")
    suites = ET.parse(args.junit).getroot().iter("testsuite")
    counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    duration = 0.0
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.get(key, 0))
        duration += float(suite.get("time", 0))
    require(counts["tests"] > 0 and counts["failures"] == counts["errors"] == counts["skipped"] == 0, "Regression run incomplete")
    output = {"schema_version": 1, "status": "verified", "runtime_version": wheel["version"], "wheel_sha256": wheel["sha256"],
        "runtime_source_hashes": {path.relative_to(ROOT).as_posix(): sha(path) for path in runtime_files},
        "regression": {**counts, "seconds": round(duration, 3)}, "profiles": profiles,
        "research": {"path": research.relative_to(ROOT).as_posix(), "sha256": sha(research), "bytes": research.stat().st_size,
            "contains_source_content": True, "human_gold": False, "files": len(rm["files"])},
        "limits": ["Current Windows host; not clean-target or OS-enforced network isolation.",
            "Development corpus records precede native-worker hardening; frozen fingerprints and recorded engine versions retained.",
            "Runtime source and wheel hashes verified; independently labeled accuracy and publication licensing remain open."]}
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "verified", "tests": counts["tests"], "wheel_sha256": wheel["sha256"],
        "research_sha256": output["research"]["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
