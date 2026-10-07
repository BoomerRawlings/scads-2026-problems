"""Install the audited wheel offline in a fresh venv and run outside checkout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


PROJECT = Path(__file__).resolve().parents[1]


def _environment():
    result = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        result.pop(key, None)
    result.update(PYTHONNOUSERSITE="1", PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CONFIG_FILE=os.devnull)
    return result


def _run(command, cwd, env):
    process = subprocess.run([str(part) for part in command], cwd=cwd, env=env,
                             check=True, capture_output=True, text=True, encoding="utf-8", timeout=180)
    return process.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT / "dist" / "artifacts.json")
    parser.add_argument("--report", type=Path, default=PROJECT / "dist" / "installed-smoke.json")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    wheels = [entry for entry in manifest["artifacts"] if entry["path"].endswith(".whl")]
    if len(wheels) != 1:
        raise RuntimeError("Artifact manifest must name exactly one wheel")
    wheel_entry = wheels[0]
    wheel = (args.manifest.resolve().parent / wheel_entry["path"]).resolve()
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != wheel_entry["sha256"]:
        raise RuntimeError("Wheel hash does not match the artifact manifest")
    env = _environment()
    with tempfile.TemporaryDirectory(prefix="project5-installed-") as temporary:
        root = Path(temporary).resolve()
        if root.is_relative_to(PROJECT):
            raise RuntimeError("Smoke directory must be outside the source checkout")
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        cli = scripts / ("graphrag-discovery.exe" if os.name == "nt" else "graphrag-discovery")
        work = root / "work"
        work.mkdir()
        # --no-index and --no-deps prevent network resolution. ensurepip above
        # seeds pip from the interpreter's bundled wheels, also without network.
        _run([python, "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", wheel], work, env)
        probe_code = """
import importlib.metadata, json
from pathlib import Path
import graphrag_discovery
from graphrag_discovery.resources import read_bytes, read_text
manifest = json.loads(read_text('fixtures', 'pump', 'manifest.json'))
record_schema = json.loads(read_text('schemas', 'record.schema.json'))
assertion_schema = json.loads(read_text('schemas', 'assertion.schema.json'))
static = read_bytes('static', 'index.html')
print(json.dumps({'module': str(Path(graphrag_discovery.__file__).resolve()),
 'version': importlib.metadata.version('scads-graphrag-discovery'),
 'module_version': graphrag_discovery.__version__,
 'runtime_dependencies': importlib.metadata.requires('scads-graphrag-discovery') or [],
 'fixture_batches': len(manifest['batches']), 'schemas': bool(record_schema and assertion_schema),
 'static_bytes': len(static)}))
"""
        probe = json.loads(_run([python, "-I", "-c", probe_code], work, env))
        module_path = Path(probe["module"])
        if not module_path.is_relative_to(environment) or module_path.is_relative_to(PROJECT):
            raise RuntimeError("Import did not resolve to the isolated installation")
        if probe["version"] != manifest["version"] or probe["module_version"] != manifest["version"]:
            raise RuntimeError("Installed version does not match the release manifest")
        if probe["runtime_dependencies"] or probe["fixture_batches"] != 5 or not probe["schemas"] or not probe["static_bytes"]:
            raise RuntimeError("Installed package metadata or assets are incomplete")
        demo = json.loads(_run([cli, "--db", "demo.sqlite3", "demo", "--output", "demo-output"], work, env))
        if demo.get("ok") is not True or demo.get("data", {}).get("all_checks_passed") is not True:
            raise RuntimeError("Installed console entry point failed the authored demonstration")
        module_cli = json.loads(_run([python, "-I", "-m", "graphrag_discovery", "--db", "demo.sqlite3", "status", "--corpus", "pump-fixture"], work, env))
        if module_cli.get("ok") is not True:
            raise RuntimeError("Installed module entry point failed")
        smoke = {
            "schema_version": "1", "ok": True, "created_at": datetime.now(timezone.utc).isoformat(),
            "platform": sys.platform, "python": sys.version.split()[0], "version": probe["version"],
            "wheel": wheel.name, "wheel_sha256": digest, "offline_install": True,
            "fresh_venv": True, "outside_checkout": True, "pythonpath_removed": True,
            "console_entry_point": True, "module_entry_point": True,
            "fixture_batches": probe["fixture_batches"], "schemas_available": probe["schemas"],
            "static_bytes": probe["static_bytes"], "runtime_dependencies": probe["runtime_dependencies"],
            "demo_checks": demo["data"]["checks"],
            "limitations": ["Authored demonstration, not model quality or scale validation", "Only the recorded local OS/Python combination ran; CI matrix execution is separate"],
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(smoke, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "report": str(args.report.resolve()), "demo_checks_passed": len(smoke["demo_checks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
