"""Prepare a platform-specific wheelhouse, locks, licenses and cold-start proof.

Run with the qualified project interpreter. Optional downloads happen only during
preparation. Verification always installs with no index, no network, and no cache.
The Python socket guard used by the smoke tests is not an OS-level air gap.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import time
import tomllib
import zipfile


PROJECT = Path(__file__).resolve().parents[1]


def canonical_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, *, cwd=None, timeout=300):
    result = subprocess.run([str(value) for value in command], cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}\n{result.stderr[-6000:]}\n{result.stdout[-2000:]}")
    return result


def dependency_closure(requirements):
    """Read exact installed versions, honoring active Python/platform markers."""
    if not requirements:
        return {}
    try:
        from packaging.requirements import Requirement
    except ImportError as error:
        raise RuntimeError("Preparation needs packaging installed in the source environment; discovery runtime does not.") from error
    pending = deque(Requirement(value) for value in requirements)
    versions = {}
    visited = set()
    while pending:
        requirement = pending.popleft()
        name = canonical_name(requirement.name)
        extras = tuple(sorted(requirement.extras))
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        dist = metadata.distribution(requirement.name)
        if requirement.specifier and not requirement.specifier.contains(dist.version, prereleases=True):
            raise RuntimeError(f"Installed {name}=={dist.version} does not satisfy {requirement}.")
        versions[name] = dist.version
        for item in dist.requires or []:
            dependency = Requirement(item)
            if dependency.marker is None or any(dependency.marker.evaluate({"extra": extra}) for extra in ("", *extras)):
                pending.append(dependency)
    return dict(sorted(versions.items()))


def wheel_inventory(directory):
    inventory = {}
    for path in sorted(directory.glob("*.whl")):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            meta_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
            info = BytesParser().parsebytes(archive.read(meta_name))
            name = canonical_name(info["Name"])
            license_files = [item for item in names if ".dist-info/licenses/" in item.lower() or
                             (".dist-info/" in item and any(token in Path(item).name.lower() for token in ("license", "copying", "notice")))]
            model_files = [item for item in names if item.lower().endswith(".onnx")]
            record = {"name": name, "version": info["Version"], "file": path.name, "bytes": path.stat().st_size,
                      "sha256": sha256(path), "license_expression": info.get("License-Expression"),
                      "license_metadata": (info.get("License") or "")[:1000],
                      "license_classifiers": [value for value in info.get_all("Classifier", []) if value.startswith("License")],
                      "license_files": [{"member": item, "sha256": hashlib.sha256(archive.read(item)).hexdigest()} for item in license_files],
                      "model_files": [{"member": item, "bytes": archive.getinfo(item).file_size,
                                       "sha256": hashlib.sha256(archive.read(item)).hexdigest()} for item in model_files]}
            for index, item in enumerate(license_files):
                output = directory.parent / "licenses" / name / f"{index:02d}-{Path(item).name}"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(archive.read(item))
        if name in inventory:
            raise RuntimeError(f"Multiple wheels for {name}; use a fresh platform-specific output directory.")
        inventory[name] = record
    return inventory


_SMOKE = r'''
import importlib.metadata as metadata
import json
from pathlib import Path
import socket
import sys
import time

attempts = []
def deny(*args, **kwargs):
    attempts.append("Python network call")
    raise RuntimeError("Network denied by offline smoke-test guard")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.socket.sendto = deny
socket.create_connection = deny
socket.getaddrinfo = deny

import vopt
from vopt.cli import doctor
from vopt.catalog import Catalog
from vopt.schema import seal_bundle

installed = Path(vopt.__file__).resolve()
assert installed.is_relative_to(Path(sys.prefix).resolve()), "Loaded source checkout instead of installed wheel"
probe = doctor()
assert probe["discovery_ready"], probe
doc = {"doc_id":"offline-fixture","title":"Offline Fixture Drill Manual","manufacturer":"Fixture", "models":["F-1","F-2"],
       "category":"drill","language":"en","revision":"1","request_ref":"request:offline-fixture:1","processing_status":"complete"}
def fact(identifier, model, attribute, value, unit):
    return {"assertion_id":identifier,"doc_id":doc["doc_id"],"model":model,"variant":None,"attribute":attribute,"qualifier":"rated",
            "status":"reviewed","value":value,"value_max":None,"unit":unit}
facts = [fact("f1-v","F-1","input_voltage",120,"V"),fact("f1-h","F-1","horsepower",1,"hp"),
         fact("f2-v","F-2","input_voltage",230,"V"),fact("f2-h","F-2","horsepower",3,"hp")]
bundle = seal_bundle({"schema_version":1,"catalog_id":"offline-smoke","sequence":1,"profile":"values",
                      "policy":{"version":1,"revoked_doc_ids":[],"revoked_assertion_ids":[]},"documents":[doc],"assertions":facts})
catalog = Catalog("metadata.sqlite")
catalog.import_bundle(bundle)
checks = {}
for method in ("lexical","semantic"):
    result = catalog.search("input voltage > 200 V and horsepower > 2 hp",method=method)
    assert [r["model"] for r in result["results"]] == ["F-2"], result
    wrong = catalog.search("input voltage < 200 V and horsepower > 2 hp",method=method)
    assert not wrong["results"], wrong
    checks[method] = {"matching_models":[r["model"] for r in result["results"]],"wrong_model_join":wrong["status"]}
assert catalog.search("private-source-sentinel")["status"] == "no_match"
bundle["sequence"] = 2
bundle["profile"] = "coverage"
bundle["policy"]["version"] = 2
bundle["assertions"] = [{key:value for key,value in f.items() if key not in {"value","value_max","unit"}} for f in facts]
catalog.import_bundle(seal_bundle(bundle))
assert catalog.search("input voltage > 200 V")["status"] == "unsupported"
assert catalog.search("input voltage")["results"]
extraction = None
if sys.argv[1] == "extraction":
    assert probe["extraction_ready"], probe
    import pymupdf as fitz
    from vopt.ingest import ingest_pdf
    original = fitz.open()
    page = original.new_page(width=650,height=300)
    page.insert_text((35,55),"Model F-1",fontsize=20)
    page.insert_text((35,100),"Input voltage: 120 V",fontsize=20)
    page.insert_text((35,145),"Motor horsepower: 2 hp",fontsize=20)
    pixels = page.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes("png")
    scan = fitz.open()
    scan.new_page(width=650,height=300).insert_image(fitz.Rect(0,0,650,300),stream=pixels)
    scan.save("synthetic-scan.pdf")
    scan.close()
    original.close()
    private = dict(doc)
    private["models"] = ["F-1"]
    private["source_uri"] = "authored:offline-smoke-synthetic"
    private["rights"] = {"basis":"synthetic_fixture","evidence_url":"authored:offline-smoke","attribution":"Authored packaging test; not real-manual accuracy evidence"}
    started = time.perf_counter()
    record = ingest_pdf("synthetic-scan.pdf",private,"processing",force_ocr=True)
    assert record["pages"] and record["pages"][0]["status"] == "ok", record
    assert record["execution"]["mode"] == "subprocess", record
    assert all(page.get("worker_network_attempts") == 0 for page in record["pages"]), record
    assert all(page.get("worker_pid_verified") is True for page in record["pages"]), record
    assert "120" in record["pages"][0]["text"], record["pages"]
    attributes = sorted({a["attribute"] for a in record["assertions"]})
    assert "input_voltage" in attributes, record["assertions"]
    extraction = {"fixture":"authored image-only PDF; synthetic","elapsed_seconds":round(time.perf_counter()-started,3),
                  "page_status":record["pages"][0]["status"],"engine":record["pages"][0]["engine"],"attributes":attributes,
                  "assertion_count":len(record["assertions"]), "execution":record["execution"],
                  "worker_python_network_attempts":sum(page["worker_network_attempts"] for page in record["pages"]),
                  "native_worker_pid_verified":all(page["worker_pid_verified"] for page in record["pages"])}
assert attempts == [], attempts
print(json.dumps({"status":"passed","profile":sys.argv[1],"python":sys.version.split()[0],"doctor":probe,
                  "installed_wheel_import":True,"ranker_checks":checks,"coverage_downgrade_numeric_filter":"unsupported",
                  "private_source_files_present_during_discovery":False,"python_network_attempts":len(attempts),
                  "guard_scope":"Python socket operations blocked; native/OS networking not independently isolated",
                  "extraction":extraction},indent=2))
'''


def verify(uv, output, profiles):
    results = []
    for profile in profiles:
        target = output / f"proof-{profile}"
        target.mkdir()
        environment = target / "environment"
        run([uv, "venv", "--python", sys.executable, "--offline", "--no-python-downloads", "--no-config", environment])
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        lock = output / f"requirements-{profile}.lock"
        started = time.perf_counter()
        # --no-cache ensures cached wheels cannot rescue an incomplete wheelhouse.
        run([uv, "pip", "install", "--python", python, "--no-index", "--offline", "--no-cache", "--no-config", "--no-python-downloads",
             "--find-links", output / "wheels", "--require-hashes", "-r", lock], cwd=target)
        install_seconds = round(time.perf_counter() - started, 3)
        smoke = target / "smoke.py"
        smoke.write_text(_SMOKE, encoding="utf-8")
        result = run([python, "-I", smoke, profile], cwd=target)
        evidence = json.loads(result.stdout)
        evidence["installation"] = {"new_virtual_environment": True, "no_index": True, "offline": True,
                                     "cache_disabled": True, "hashes_required": True, "elapsed_seconds": install_seconds,
                                     "packaged_python_runtime": False}
        write_json(output / f"proof-{profile}.json", evidence)
        results.append(evidence)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("discovery", "extraction", "all"), default="discovery")
    parser.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    parser.add_argument("--allow-download", action="store_true", help="Allow preparatory dependency/build downloads; verification stays offline")
    parser.add_argument("--from-wheelhouse", type=Path, help="Existing local wheels used when downloads are disabled")
    parser.add_argument("--verify", action="store_true", help="Install fresh profile environments and run guarded cold-start tests")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Output directory must be empty; existing artifacts are never deleted.")
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("Preparation/verification needs uv on PATH; discovery runtime does not.")
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    project_name = canonical_name(project["name"])
    profiles = ["discovery", "extraction"] if args.profile == "all" else [args.profile]
    versions = {profile: {project_name: project["version"], **dependency_closure(project.get("dependencies", []) +
                        (project["optional-dependencies"]["extraction"] if profile == "extraction" else []))} for profile in profiles}
    output.mkdir(parents=True, exist_ok=True)
    wheels = output / "wheels"
    wheels.mkdir()
    command = [uv, "build", "--wheel", "--python", sys.executable, "--no-python-downloads", "--no-config", "--out-dir", wheels, PROJECT]
    if not args.allow_download:
        command += ["--offline"]
    run(command)
    all_versions = {name: version for profile in versions.values() for name, version in profile.items()}
    dependencies = {name: version for name, version in all_versions.items() if name != project_name}
    if dependencies:
        # Ensure pip from the interpreter's bundled wheel, without internet.
        if not any(d.metadata["Name"].lower() == "pip" for d in metadata.distributions()):
            run([sys.executable, "-m", "ensurepip"])
        pins = output / "installed-dependencies.txt"
        pins.write_text("\n".join(f"{name}=={version}" for name, version in sorted(dependencies.items())) + "\n", encoding="utf-8")
        command = [sys.executable, "-m", "pip", "download", "--disable-pip-version-check", "--no-deps", "--only-binary=:all:",
                   "--dest", wheels, "-r", pins]
        if not args.allow_download:
            command += ["--no-index"]
        if args.from_wheelhouse:
            command += ["--find-links", args.from_wheelhouse.resolve()]
        run(command)
    inventory = wheel_inventory(wheels)
    for profile, packages in versions.items():
        lines = [f"# {profile}; exact installed versions; interpreter platform {sysconfig.get_platform()}; Python {platform.python_version()}"]
        for name, version in sorted(packages.items()):
            if name not in inventory or inventory[name]["version"] != version:
                raise RuntimeError(f"Required wheel missing: {name}=={version}")
            lines.append(f"{name}=={version} --hash=sha256:{inventory[name]['sha256']}")
        (output / f"requirements-{profile}.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {"format_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                "system": platform.system(), "host_machine": platform.machine(), "interpreter_platform": sysconfig.get_platform(), "python_implementation": platform.python_implementation(),
                "profiles": profiles, "preparation_downloads_allowed": args.allow_download, "wheels": list(inventory.values()),
                "python_runtime_included": False, "model_assets_included_in_wheels": sum(len(item["model_files"]) for item in inventory.values()),
                "license_status": "Wheel license metadata and shipped license files inventoried; " + ("project license is declared in pyproject." if project.get("license") else "project distribution license is not yet declared in pyproject."),
                "verification": "not requested"}
    write_json(output / "manifest.json", manifest)
    if args.verify:
        evidence = verify(uv, output, profiles)
        manifest["verification"] = [{"profile": item["profile"], "status": item["status"], "proof": f"proof-{item['profile']}.json"} for item in evidence]
    manifest["artifacts"] = [{"file": path.name, "sha256": sha256(path)} for path in sorted(output.iterdir())
                             if path.is_file() and path.name != "manifest.json"]
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "profiles": profiles, "wheel_count": len(inventory),
                      "bytes": sum(item["bytes"] for item in inventory.values()), "verification": manifest["verification"]}, indent=2))


if __name__ == "__main__":
    main()
