"""Build a core/optional-extras wheel bundle and verify an offline installation.

Requires installed setuptools>=68 and wheel. --no-network requires every
requested dependency wheel in --wheelhouse. Extras target this Python/platform.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import tomllib
import textwrap
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("config/development.json", "config/catalog.json", "config/mapping.json",
          "fixtures/manifest.json", "fixtures/requests.jsonl")
ALLOWED_EXTRAS = frozenset({"mcp", "geo"})
MAX_DEPENDENCY_BYTES = 100 * 1024 * 1024
HANDOFF_FILES = ("tools/live_parity.py", "tools/capacity_scenarios.py", "tools/benchmark_fixture.py", "tools/stress_exports.py",
                 "examples/capacity/scenarios.json")
NETWORK_GUARD = '''import os, socket, sys, threading
# asyncio uses socketpair; Windows implements that pair using loopback TCP.
# Permit only that stdlib call, never general loopback networking.
_local = threading.local()
_socketpair = socket.socketpair
def _guarded_socketpair(*args, **kwargs):
    _local.in_socketpair = True
    try:
        return _socketpair(*args, **kwargs)
    finally:
        _local.in_socketpair = False
socket.socketpair = _guarded_socketpair
def deny_network(event, args):
    if not event.startswith('socket.') or event == 'socket.gethostname':
        return
    if getattr(_local, 'in_socketpair', False):
        if event == 'socket.__new__':
            return
        if event in ('socket.bind', 'socket.connect'):
            address = args[1]
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return
    raise RuntimeError('Offline distribution smoke forbids networking')
sys.addaudithook(deny_network)
os.environ['ANALYTICS311_OFFLINE_GUARD_ACTIVE'] = '1'
'''


def normalize_extras(extras=()):
    if isinstance(extras, str):
        extras = extras.split(',') if extras else ()
    selected = tuple(sorted(set(extras)))
    if any(extra not in ALLOWED_EXTRAS for extra in selected):
        raise ValueError('Only mcp and geo extras are supported')
    return selected


def target_description():
    return {"os": platform.system(), "architecture": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "python_platform": sysconfig.get_platform(),
            "python_cache_tag": sys.implementation.cache_tag,
            "dependency_target": "current interpreter and platform only"}


def artifact_description(path, relative):
    python_tag, abi_tag, platform_tag = Path(path).stem.rsplit("-", 3)[-3:]
    return {"file": Path(relative).as_posix(), "sha256": sha256(path),
            "bytes": Path(path).stat().st_size,
            "wheel_tags": {"python": python_tag, "abi": abi_tag, "platform": platform_tag}}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def handoff_description(root=ROOT):
    return [{"file": name, "sha256": sha256(root / name),
             "bytes": (root / name).stat().st_size} for name in HANDOFF_FILES]


def verify_assets(root=ROOT):
    """Fail before building if compatibility files diverge from bundled assets."""
    hashes = {}
    for name in ASSETS:
        bundled = root / "analytics311" / "assets" / name
        if bundled.read_bytes() != (root / name).read_bytes():
            raise ValueError(f"Bundled asset differs from compatibility file: {name}")
        hashes[name] = sha256(bundled)
    return hashes


def command(args, *, cwd=None, env=None, input=None, timeout=120):
    process = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, input=input,
                             text=True, capture_output=True, timeout=timeout)
    if process.returncode:
        raise RuntimeError(f"Command failed ({process.returncode}): {process.stderr[-4000:]}")
    return process.stdout


def clean_environment():
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("PIP_") or key in ("PYTHONPATH", "PYTHONHOME", "ANALYTICS311_CONFIG"):
            env.pop(key, None)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def stage_dependencies(wheel, destination, *, wheelhouses=(), no_network=False, extras=()):
    """Resolve binary wheels for the current target within a bounded staging area."""
    extras = normalize_extras(extras)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with temporary_directory(prefix="analytics311-download-") as temporary:
        temporary = Path(temporary)
        env = clean_environment()
        env.update(TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary))
        if no_network:
            env["PIP_NO_INDEX"] = "1"
        requirement = str(wheel) + ("[" + ",".join(extras) + "]" if extras else "")
        args = [sys.executable, "-m", "pip", "download", "--only-binary=:all:",
                "--no-cache-dir", "--timeout", "15", "--retries", "1", "--dest", str(destination)]
        if no_network:
            args.append("--no-index")
        for wheelhouse in wheelhouses:
            path = Path(wheelhouse).resolve()
            if not path.is_dir():
                raise ValueError("Each wheelhouse must be an existing directory")
            args.extend(["--find-links", str(path)])
        args.append(requirement)
        # Pip's temporary downloads count too; checking only completed .whl files
        # would allow a large download to bypass the staging budget.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
            process = subprocess.Popen(args, cwd=temporary, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       text=True)
            deadline = time.monotonic() + 300
            try:
                while process.poll() is None:
                    enforce_dependency_budget(destination, temporary)
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Dependency resolution exceeded five minutes")
                    time.sleep(.1)
                enforce_dependency_budget(destination, temporary)
                if process.returncode:
                    log.seek(0)
                    raise RuntimeError("Dependency wheel resolution failed: " + log.read()[-4000:])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
    # pip download copies the requested project wheel as well as dependencies.
    copied = destination / Path(wheel).name
    if copied.exists():
        if sha256(copied) != sha256(wheel):
            raise AssertionError("Dependency staging changed the project wheel")
        copied.unlink()
    if not list(destination.glob("tzdata-*.whl")):
        raise RuntimeError("Release needs tzdata; provide compatible dependency wheels")
    return sorted(destination.glob("*.whl"))


def enforce_dependency_budget(*directories):
    used = 0
    for directory in directories:
        for path in Path(directory).rglob("*"):
            try:
                if path.is_file():
                    used += path.stat().st_size
            except FileNotFoundError:
                continue  # Pip atomically renames temporary files.
    if used > MAX_DEPENDENCY_BYTES:
        raise RuntimeError("Dependency staging exceeded the 100 MiB budget")


@contextmanager
def temporary_directory(prefix, parent=None):
    """Allow Windows executables a short exit/unlock interval after export."""
    parent = Path(parent or tempfile.gettempdir()).resolve()
    directory = tempfile.TemporaryDirectory(prefix=prefix, dir=parent)
    expected = Path(directory.name).resolve()
    if expected.parent != parent or not expected.name.startswith(prefix):
        raise RuntimeError("Unexpected smoke temporary directory")
    try:
        yield directory.name
    finally:
        for attempt in range(150):
            if Path(directory.name).resolve() != expected:
                raise RuntimeError("Smoke cleanup target changed")
            try:
                directory.cleanup()
                break
            except PermissionError:
                if attempt == 149:
                    raise
                time.sleep(.1)


def publish_release(output, artifacts, manifest):
    """Publish one complete release; never mix artifacts with an old directory."""
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Release output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem, so publication is a directory rename.
    with temporary_directory(".analytics311-release-", output.parent) as temporary:
        staging = Path(temporary)
        for artifact, entry in zip(artifacts, manifest["artifacts"], strict=True):
            destination = staging / entry["file"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact, destination)
            if (destination.stat().st_size != entry["bytes"] or sha256(destination) != entry["sha256"]):
                raise RuntimeError("Release artifact changed while publishing")
        (staging / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        (staging / "SHA256SUMS").write_text("".join(f"{a['sha256']}  {a['file']}\n" for a in manifest["artifacts"]), encoding="utf-8", newline="\n")
        if output.exists() or output.is_symlink():
            raise ValueError("Release output appeared during build; choose a new directory")
        staging.rename(output)


def smoke_optional_features(python, work, env, extras, spec):
    """Exercise installed optional adapters, never the source checkout."""
    result = {"mcp_tested": False, "geo_tested": False}
    if "mcp" in extras:
        script = textwrap.dedent('''
            import asyncio, json, os, sys
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            spec = json.loads(sys.stdin.read())
            async def exercise():
                parameters = StdioServerParameters(command=sys.executable,
                    args=["-m", "analytics311", "mcp"], cwd=os.getcwd(), env=dict(os.environ))
                async with stdio_client(parameters) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        names = sorted(tool.name for tool in listed.tools)
                        assert set(names) == {"describe_dataset", "validate_analysis", "run_analysis",
                            "get_result", "export_csv", "cancel_export", "create_map_link"}, names
                        described = await session.call_tool("describe_dataset", {})
                        assert not described.isError, described
                        assert described.structuredContent["dataset"]["dataset_version"] == "fixture-v1"
                        validated = await session.call_tool("validate_analysis", {"spec": spec})
                        assert not validated.isError, validated
                        analysis = await session.call_tool("run_analysis", {"spec": spec})
                        assert not analysis.isError, analysis
                        value = analysis.structuredContent
                        assert value["total"] == {"relation": "eq", "value": 4}, value
                        assert len(value["rows"]) == 2, value
                        saved = await session.call_tool("get_result", {"result_id": value["result_id"]})
                        assert not saved.isError, saved
                        assert saved.structuredContent["total"] == value["total"]
                        invalid = await session.call_tool("run_analysis", {"spec": {"operation": "delete_index"}})
                        assert invalid.isError, invalid
                        return {"status": "passed", "transport": "stdio", "tools": names,
                            "successful_calls": 4, "rejected_invalid_calls": 1, "matching_records": 4}
            print(json.dumps(asyncio.run(exercise())))
        ''')
        result["mcp"] = json.loads(command([python, "-c", script], cwd=work, env=env,
                                          input=json.dumps(spec), timeout=60))
        result["mcp_tested"] = True
    if "geo" in extras:
        result["geo"] = json.loads(command([python, "-c", textwrap.dedent('''
            import json, shapely
            from shapely.geometry import Point, Polygon
            polygon = Polygon([(0,0), (2,0), (2,2), (0,2)])
            assert polygon.contains(Point(1,1))
            assert not polygon.contains(Point(3,3))
            print(json.dumps({"status": "passed", "shapely_version": shapely.__version__,
                "scope": "installed native geometry dependency; synthetic polygon only"}))
        ''')], cwd=work, env=env, timeout=45))
        result["geo_tested"] = True
    return result


def smoke_handoff(python, work, env):
    """Run transferred harnesses against the installed package, outside checkout."""
    for name in HANDOFF_FILES:
        destination = work / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    command([python, "tools/live_parity.py", "--help"], cwd=work, env=env)
    capacity = json.loads(command([python, "tools/capacity_scenarios.py", "--output", "runs/capacity-scenarios.json"], cwd=work, env=env))
    if capacity["evidence_kind"] != "modeled_capacity" or capacity["ready_for_production"] is not False:
        raise AssertionError("Transferred capacity scenarios changed their evidence scope")
    benchmark = json.loads(command([python, "tools/benchmark_fixture.py", "--data", "data/reference.jsonl",
                                    "--output", "runs/reference-benchmark.json", "--records", "100", "--repeats", "1"], cwd=work, env=env))
    if benchmark["records"] != 100 or benchmark["cases"] != 5:
        raise AssertionError("Transferred reference benchmark did not execute its five bounded cases")
    stress = json.loads(command([python, "tools/stress_exports.py", "--batches", "1", "--concurrency", "2",
                                 "--total-seconds", "40", "--output", "runs/export-stress.json"],
                                cwd=work, env=env, timeout=50))
    if (stress.get("passed") is not True or stress.get("owned_processes_started") != 7
            or type(stress.get("peak_owned_processes_alive")) is not int
            or not 1 <= stress["peak_owned_processes_alive"] <= 2):
        raise AssertionError("Transferred worker stress/recovery trial did not pass")
    stress_receipt = json.loads((work / "runs/export-stress.json").read_text(encoding="utf-8"))
    recovery = stress_receipt.get("recovery", {})
    if (recovery.get("worker_abrupt_exit") is not True or recovery.get("worker_exit_code") != 86
            or recovery.get("active_worker_preserved") is not True
            or recovery.get("partial_removed") is not True or recovery.get("reservation_released") is not True):
        raise AssertionError("Transferred stress tool did not verify actual interpreter-death recovery")
    return {"status": "passed", "live_parity": "argument parsing only; no server",
            "capacity_scenarios": capacity["combination_count"],
            "reference_benchmark": {"records": 100, "cases": 5, "evidence_level": "generated_reference_only"},
            "export_stress": {"status": "passed", "owned_processes_started": 7,
                              "peak_owned_processes_alive": stress["peak_owned_processes_alive"],
                              "seconds": stress["elapsed_seconds"], "crash_method": recovery["method"],
                              "worker_exit_code": 86, "evidence_level": "measured_bounded_local_process_only"}}


def smoke_wheel(wheel, dependency_dir, extras=()):
    """Install outside the checkout and exercise the actual CLI/CSV worker."""
    with temporary_directory(prefix="analytics311-install-") as temporary:
        target = Path(temporary)
        environment = target / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        work = target / "work"
        work.mkdir()
        guard = target / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
        env = clean_environment()
        env.update(PYTHONPATH=str(guard), PIP_NO_INDEX="1")
        extras = normalize_extras(extras)
        requirement = str(wheel) + ("[" + ",".join(extras) + "]" if extras else "")
        command([python, "-m", "pip", "install", "--no-index", "--find-links", dependency_dir,
                 "--no-compile", requirement], cwd=work, env=env)
        probe = json.loads(command([python, "-c",
            "import analytics311,json,os,sys;from pathlib import Path;"
            "from analytics311.resources import ASSETS,asset_path;import hashlib;"
            "print(json.dumps({'installed_in_venv':Path(analytics311.__file__).is_relative_to(Path(sys.prefix)),"
            "'version':analytics311.__version__,'offline_guard':os.environ.get('ANALYTICS311_OFFLINE_GUARD_ACTIVE')=='1',"
            "'assets':{n:hashlib.sha256(asset_path(n).read_bytes()).hexdigest() for n in ASSETS}}))"
        ], cwd=work, env=env))
        if not probe["installed_in_venv"] or not probe["offline_guard"]:
            raise AssertionError("Smoke must import the installed wheel under the offline guard")
        command([python, "-c", textwrap.dedent('''
            import socket
            first, second = socket.socketpair()
            first.close(); second.close()
            for operation in (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
                              lambda: socket.getaddrinfo("example.com", 443)):
                try:
                    operation()
                except RuntimeError as exc:
                    assert "forbids networking" in str(exc)
                else:
                    raise AssertionError("Network guard did not reject network operation")
        ''')], cwd=work, env=env)

        def cli(*args, spec=None):
            return json.loads(command([python, "-m", "analytics311", *args], cwd=work, env=env,
                                      input=json.dumps(spec) if spec is not None else None, timeout=45))

        description = cli("describe")
        capacity = cli("plan-capacity", "--profile", "development", "--target-rows", "1000")
        if (capacity["evidence_kind"] != "modeled_capacity" or capacity["target_rows"] != 1000
                or capacity["backend"] != "fixture" or capacity["ready_for_production"] is not False):
            raise AssertionError("Installed capacity planner did not preserve modeled-evidence boundaries")
        spec = {"schema_version": "1", "dataset_version": "fixture-v1", "operation": "records",
                "timezone": "America/New_York", "as_of": "2026-01-02T12:00:00-05:00",
                "time": {"field": "created_date", "preset": "last_month"},
                "filters": {"all": [{"field": "borough", "op": "eq", "value": "BROOKLYN"},
                                    {"category_family": "noise"}]}, "preview_limit": 2}
        cli("validate", "-", spec=spec)
        result = cli("run", "-", spec=spec)
        if result["total"] != {"relation": "eq", "value": 4} or len(result["rows"]) != 2:
            raise AssertionError("Installed fixture query did not match expected four-row cohort")
        job = cli("export", result["result_id"], "--mode", "records", "--cohort", "all_matching")
        deadline = time.monotonic() + 30
        while job["status"] in ("queued", "running") and time.monotonic() < deadline:
            time.sleep(.1)
            job = cli("result", job["job_id"])
        if job["status"] != "complete" or not job["complete"] or job["rows_written"] != 4:
            raise AssertionError("Installed background CSV worker did not complete")
        exported = Path(job["file"]).resolve()
        if not exported.is_relative_to(work / "runs"):
            raise AssertionError("Default output escaped the selected working directory")
        with exported.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if {row["unique_key"] for row in rows} != {"FIX-021", "FIX-022", "FIX-023", "FIX-032"}:
            raise AssertionError("Installed CSV did not contain the complete fixture cohort")
        after = json.loads(command([python, "-c",
            "import json,hashlib;from analytics311.resources import ASSETS,asset_path;"
            "print(json.dumps({n:hashlib.sha256(asset_path(n).read_bytes()).hexdigest() for n in ASSETS}))"
        ], cwd=work, env=env))
        if after != probe["assets"]:
            raise AssertionError("CLI changed installed resources")
        optional = smoke_optional_features(python, work, env, extras, spec)
        handoff = smoke_handoff(python, work, env)
        return {"status": "passed", "fresh_venv": True, "outside_checkout": True,
                "installation": "pip --no-index", "network_audit_guard": True,
                "network_guard_scope": "Python audit hook; not an OS sandbox",
                "network_guard_exception": "stdlib socketpair only; Windows uses loopback TCP internally",
                "package_version": probe["version"], "dataset_version": description["dataset"]["dataset_version"],
                "evidence_level": "fixture_only", "matching_records": 4, "preview_records": 2,
                "export_rows": len(rows), "export_sha256": sha256(exported),
                "capacity_plan": {"status": "passed", "target_rows": 1000,
                                  "evidence_kind": capacity["evidence_kind"],
                                  "ready_for_production": capacity["ready_for_production"]},
                "default_output": "work/runs", "installed_assets_unchanged": True,
                "handoff": handoff,
                **optional, "elastic_kibana_tested": False}


def build(output, *, wheelhouses=(), no_network=False, smoke=True, extras=()):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Release output already exists; choose a new directory")
    extras = normalize_extras(extras)
    asset_hashes = verify_assets()
    handoff_files = handoff_description()
    for name in ("setuptools", "wheel"):
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Install {name} into this build environment first") from exc
        if name == "setuptools" and int(version.split(".")[0]) < 68:
            raise RuntimeError("setuptools>=68 is required")
    env = clean_environment()
    if no_network:
        env["PIP_NO_INDEX"] = "1"
    with temporary_directory(prefix="analytics311-build-") as temporary:
        staging = Path(temporary)
        source = staging / "source"
        source.mkdir()
        shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
        package = source / "analytics311"
        package.mkdir()
        for original in (ROOT / "analytics311").rglob("*.py"):
            relative = original.relative_to(ROOT / "analytics311")
            if "__pycache__" in relative.parts:
                continue
            destination = package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
        for name in ASSETS:
            destination = package / "assets" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "analytics311" / "assets" / name, destination)
        built = staging / "wheels"
        args = [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", built]
        if no_network:
            args.append("--no-index")
        command([*args, source], cwd=staging, env=env)
        wheels = list(built.glob("analytics311-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one project wheel")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            for name, expected in asset_hashes.items():
                if hashlib.sha256(archive.read("analytics311/assets/" + name)).hexdigest() != expected:
                    raise AssertionError(f"Wheel resource mismatch: {name}")
        dependencies = staging / "dependencies"
        stage_dependencies(wheel, dependencies, wheelhouses=wheelhouses,
                           no_network=no_network, extras=extras)
        verification = smoke_wheel(wheel, dependencies, extras) if smoke else {
            "status": "not_run", "mcp_tested": False, "geo_tested": False}
        project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        if smoke and verification["package_version"] != project["version"]:
            raise AssertionError("Installed package and wheel metadata versions disagree")
        artifacts = [wheel, *sorted(dependencies.glob("*.whl"))]
        manifest_artifacts = []
        for artifact in artifacts:
            relative = Path(artifact.name) if artifact == wheel else Path("dependencies") / artifact.name
            manifest_artifacts.append(artifact_description(artifact, relative))
        manifest = {"name": project["name"], "version": project["version"],
                    "distribution": "core+extras" if extras else "core",
                    "target": target_description(),
                    "install_requirement": project["name"] + ("[" + ",".join(extras) + "]" if extras else "") + "==" + project["version"],
                    "requires_python": project["requires-python"], "artifacts": manifest_artifacts,
                    "bundled_assets_sha256": asset_hashes, "build_network_disabled": no_network,
                    "verification": verification, "extras_bundled": list(extras),
                    "handoff_files": handoff_files,
                    "limits": ["Only selected extras are bundled; dependency wheels target the recorded Python/platform.",
                               "Python socket audit instrumentation is not an OS network sandbox.",
                               "Fixture execution is software evidence, not live Elasticsearch/Kibana or real NYC evidence.",
                               "Install wheels with pip; direct zip-import execution is not a supported deployment."]}
        publish_release(output, artifacts, manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "release")
    parser.add_argument("--wheelhouse", type=Path, action="append", default=[])
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--extras", default="", help="Optional dependency bundles: mcp, geo, or mcp,geo; default core only")
    parser.add_argument("--skip-smoke", action="store_true", help="Build only; manifest explicitly records unverified installation")
    args = parser.parse_args(argv)
    try:
        manifest = build(args.output, wheelhouses=args.wheelhouse, no_network=args.no_network,
                         smoke=not args.skip_smoke, extras=args.extras)
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.SubprocessError) as exc:
        print(f"Release failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
