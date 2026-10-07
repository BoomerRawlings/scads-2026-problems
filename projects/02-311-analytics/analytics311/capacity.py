"""Read-only host inventory and explicitly modeled deployment estimates.

This module never starts services, edits profiles, samples a dataset, or predicts
throughput. A modeled fit is only a reason to try a measured experiment.
"""
import ctypes
from datetime import datetime, timezone
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess

from .errors import AnalyticsError


GIB = 1024 ** 3
MIB = 1024 ** 2
PROFILES = ("development", "local-integration", "full-demo", "scale-lab")
_PROFILES = {
    "development": {"backend": "fixture", "memory_floor": 256 * MIB, "cpu_floor": 1, "workers": 1},
    "local-integration": {"backend": "elasticsearch", "memory_floor": 4 * GIB, "cpu_floor": 2, "workers": 1},
    "full-demo": {"backend": "elasticsearch", "memory_floor": 12 * GIB, "cpu_floor": 4, "workers": 2},
    "scale-lab": {"backend": "elasticsearch", "memory_floor": 32 * GIB, "cpu_floor": 8, "workers": 4},
}


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def _minimum(values):
    known = [value for value in values if value is not None]
    return min(known) if known else None


def _windows_memory():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
            (name, ctypes.c_uint64) for name in (
                "total", "available", "total_pagefile", "available_pagefile",
                "total_virtual", "available_virtual", "extended_virtual")]

    value = MemoryStatus()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise OSError("GlobalMemoryStatusEx failed")
    return value.total, value.available, "GlobalMemoryStatusEx"


def _linux_memory():
    text = _read("/proc/meminfo") or ""
    values = {key: int(number) * 1024 for key, number in
              re.findall(r"^(MemTotal|MemAvailable|MemFree):\s+(\d+)\s+kB$", text, re.M)}
    available = values.get("MemAvailable", values.get("MemFree"))
    return values.get("MemTotal"), available, "/proc/meminfo"


def _mac_memory():
    total = int(subprocess.check_output(["/usr/sbin/sysctl", "-n", "hw.memsize"], text=True, timeout=2))
    # Free pages are a conservative lower bound; do not count compressed/cache
    # pages as immediately available without a supported availability interface.
    text = subprocess.check_output(["/usr/bin/vm_stat"], text=True, timeout=2)
    size = re.search(r"page size of (\d+) bytes", text)
    free = re.search(r"^Pages free:\s+(\d+)", text, re.M)
    available = int(size[1]) * int(free[1]) if size and free else None
    return total, available, "sysctl hw.memsize; vm_stat free pages (lower bound)"


def _unescape_mount(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


def _cgroup_locations(membership, mounts):
    """Map this process's v1/v2 membership to visible mount directories."""
    groups = {}
    for line in membership.splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3:
            for controller in fields[1].split(","):
                groups[controller] = PurePosixPath(fields[2])
    found = []
    for line in mounts.splitlines():
        before, separator, after = line.partition(" - ")
        left, right = before.split(), after.split()
        if not separator or len(left) < 6 or len(right) < 3 or right[0] not in ("cgroup", "cgroup2"):
            continue
        controllers = ("",) if right[0] == "cgroup2" else tuple(set(right[2].split(",")) & {"memory", "cpu"})
        for controller in controllers:
            group = groups.get(controller)
            root = PurePosixPath(_unescape_mount(left[3]))
            mount = Path(_unescape_mount(left[4]))
            if group is None or not group.is_absolute() or ".." in group.parts:
                continue
            # A cgroup namespace can expose membership relative to a subtree.
            namespace = not group.is_relative_to(root)
            relative = group.relative_to(PurePosixPath("/") if namespace else root)
            current = mount.joinpath(*relative.parts)
            found.append((controller, current, mount, namespace or root != PurePosixPath("/")))
    return found


def _linux_limits(read=_read):
    membership, mounts = read("/proc/self/cgroup"), read("/proc/self/mountinfo")
    result = {"memory_limit_bytes": None, "memory_headroom_bytes": None,
              "cpu_quota_count": None, "status": "observed", "warnings": []}
    if membership is None or mounts is None:
        result["status"] = "unknown"
        result["warnings"].append("Linux cgroup membership or mounts unavailable; effective limits unknown.")
        return result
    locations = _cgroup_locations(membership, mounts)
    if membership and not locations:
        result["status"] = "unknown"
        result["warnings"].append("Linux cgroup membership could not be mapped; effective limits unknown.")
        return result
    limits, headrooms, quotas = [], [], []
    missing_usage = False
    for controller, current, mount, hidden in locations:
        memory_read = controller == "cpu"
        cpu_read = controller == "memory"
        if hidden:
            result["status"] = "unknown"
            result["warnings"].append("Cgroup namespace hides ancestors; their resource limits cannot be inspected.")
        for _ in range(256):
            if controller in ("", "memory"):
                maximum = read(current / ("memory.max" if controller == "" else "memory.limit_in_bytes"))
                memory_read = memory_read or maximum is not None
                if maximum is not None and maximum != "max":
                    try:
                        limit = int(maximum)
                        if limit < 0:
                            raise ValueError()
                        # v1's unlimited sentinel is near signed 64-bit maximum.
                        if controller == "" or limit < 2 ** 60:
                            limits.append(limit)
                            usage = read(current / ("memory.current" if controller == "" else "memory.usage_in_bytes"))
                            if usage is None or int(usage) < 0:
                                missing_usage = True
                            else:
                                headrooms.append(max(0, limit - int(usage)))
                    except ValueError:
                        result["status"] = "unknown"
            if controller in ("", "cpu"):
                quota = read(current / ("cpu.max" if controller == "" else "cpu.cfs_quota_us"))
                cpu_read = cpu_read or quota is not None
                if quota is not None:
                    try:
                        raw, period = quota.split() if controller == "" else (quota, read(current / "cpu.cfs_period_us"))
                        if raw not in ("max", "-1"):
                            if int(raw) <= 0 or int(period) <= 0:
                                raise ValueError()
                            quotas.append(int(raw) / int(period))
                    except (TypeError, ValueError):
                        result["status"] = "unknown"
            if current == mount:
                break
            current = current.parent
        else:
            result["status"] = "unknown"
        if not memory_read or not cpu_read:
            result["status"] = "unknown"
    if missing_usage:
        result["status"] = "unknown"
        result["warnings"].append("Cgroup memory usage unavailable; effective available memory unknown.")
    result.update(memory_limit_bytes=_minimum(limits),
                  memory_headroom_bytes=None if missing_usage else _minimum(headrooms),
                  cpu_quota_count=_minimum(quotas))
    if result["status"] == "unknown":
        result["warnings"].append("At least one cgroup resource limit is unreadable or invalid.")
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result


def inventory(path="."):
    """Probe resources without writing files; null means unavailable/unknown.

    Values describe the process's current host/mount, not a Docker VM, remote
    Elasticsearch cluster, GPU, disk quota, or future resource reservation.
    """
    system = platform.system()
    warnings = ["Inventory is a point-in-time observation, not a resource reservation.",
                "Disk quotas, remote nodes, GPU/LLM memory and Docker VM limits are not probed."]
    logical = os.cpu_count()
    effective_cpu = logical
    if hasattr(os, "sched_getaffinity"):
        try:
            effective_cpu = _minimum([effective_cpu, len(os.sched_getaffinity(0))])
        except OSError:
            warnings.append("CPU affinity unavailable.")
    total = available = None
    source = "unknown"
    try:
        probe = {"Windows": _windows_memory, "Linux": _linux_memory, "Darwin": _mac_memory}.get(system)
        if probe:
            total, available, source = probe()
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        warnings.append("Host physical-memory probe failed.")
    if total is None or available is None:
        warnings.append("Host physical-memory information is incomplete.")
    effective_total, effective_available = total, available
    limits = None
    if system == "Linux":
        limits = _linux_limits()
        warnings.extend(limits["warnings"])
        effective_total = _minimum([total, limits["memory_limit_bytes"]])
        effective_available = _minimum([available, limits["memory_headroom_bytes"]])
        effective_cpu = _minimum([effective_cpu, limits["cpu_quota_count"]])
        if limits["status"] == "unknown":
            effective_total = effective_available = effective_cpu = None
    elif system == "Windows":
        warnings.append("Windows job-object/process resource restrictions are not probed.")
    disk = {"total_bytes": None, "free_bytes": None, "source": "shutil.disk_usage"}
    try:
        usage = shutil.disk_usage(path)
        disk.update(total_bytes=usage.total, free_bytes=usage.free)
    except OSError:
        warnings.append("Disk information unavailable at requested path; use an existing data directory.")
    return {"schema_version": 1, "evidence_kind": "observed_inventory",
            "observed_at": datetime.now(timezone.utc).isoformat(), "platform": system,
            "cpu": {"logical_count": logical, "effective_count": effective_cpu},
            "memory": {"total_bytes": total, "available_bytes": available,
                       "effective_total_bytes": effective_total, "effective_available_bytes": effective_available,
                       "source": source}, "disk": disk, "cgroup": limits, "warnings": warnings}


def default_assumptions(profile="development"):
    if profile not in PROFILES:
        raise AnalyticsError("invalid_capacity_plan", "Unknown capacity profile.")
    return {"raw_bytes_per_record": 1200, "staging_bytes_per_record": 2000,
            "normalized_bytes_per_record": 900, "index_bytes_per_record": 1600,
            "fixture_memory_bytes_per_record": 4096,
            "raw_copies": 1, "normalized_copies": 1,
            "replicas": 1 if profile in ("full-demo", "scale-lab") else 0,
            "merge_overhead_fraction": 0.5, "free_disk_fraction": 0.25,
            "fixed_disk_bytes": GIB if profile == "development" else 5 * GIB}


def _assumptions(profile, supplied):
    result = default_assumptions(profile)
    if supplied is not None:
        if not isinstance(supplied, dict) or set(supplied) - result.keys():
            raise AnalyticsError("invalid_capacity_plan", "Unknown capacity assumption.")
        result.update(supplied)
    for key, value in result.items():
        if key.endswith("fraction"):
            high = 0.9 if key == "free_disk_fraction" else 10
            valid = type(value) in (int, float) and 0 <= value <= high and math.isfinite(value)
        else:
            low, high = (0, 10) if key == "replicas" else ((1, 10) if key.endswith("copies") else (1, 10 ** 12))
            valid = type(value) is int and low <= value <= high
        if not valid:
            raise AnalyticsError("invalid_capacity_plan", f"Invalid capacity assumption: {key}.")
    return result


def _observed(value, section, field, *, integer=True):
    group = value.get(section, {})
    if not isinstance(group, dict):
        raise AnalyticsError("invalid_capacity_plan", f"Inventory {section} must be an object.")
    number = group.get(field)
    if number is None:
        return None
    valid_type = type(number) is int if integer else type(number) in (int, float)
    if not valid_type or number < 0 or number > 10 ** 24 or not math.isfinite(number):
        raise AnalyticsError("invalid_capacity_plan", f"Inventory {section}.{field} must be a nonnegative number or null.")
    return number


def plan_capacity(profile="development", target_rows=1000, inventory=None, assumptions=None):
    """Return advisory budgets and a transparent, unmeasured capacity model."""
    if profile not in PROFILES or type(target_rows) is not int or not 1 <= target_rows <= 10 ** 12:
        raise AnalyticsError("invalid_capacity_plan", "Use a documented profile and target_rows from 1 to 1000000000000.")
    observed = globals()["inventory"]() if inventory is None else inventory
    if not isinstance(observed, dict):
        raise AnalyticsError("invalid_capacity_plan", "Inventory must be an object.")
    if not isinstance(observed.get("warnings", []), list) or any(not isinstance(item, str) for item in observed.get("warnings", [])):
        raise AnalyticsError("invalid_capacity_plan", "Inventory warnings must be an array of strings.")
    values = _assumptions(profile, assumptions)
    settings = _PROFILES[profile]
    ram = _observed(observed, "memory", "effective_available_bytes")
    cpu = _observed(observed, "cpu", "effective_count", integer=False)
    free_disk = _observed(observed, "disk", "free_bytes")
    # Missing resources always suggest the smallest pipeline, never an inferred
    # large machine. These settings change scheduling only, not analytical scope.
    workers = min(settings["workers"], max(1, math.floor(cpu or 1)), max(1, (ram or 0) // (512 * MIB)))
    page = 1000 if ram is not None and ram >= 16 * GIB and cpu is not None and cpu >= 8 else (
        500 if ram is not None and ram >= 2 * GIB and cpu is not None and cpu >= 2 else 100)
    copies = 1 + values["replicas"]
    indexed = target_rows * values["index_bytes_per_record"] * copies if settings["backend"] == "elasticsearch" else 0
    storage = {"raw_bytes": target_rows * values["raw_bytes_per_record"] * values["raw_copies"],
               "staging_bytes": target_rows * values["staging_bytes_per_record"],
               "normalized_bytes": target_rows * values["normalized_bytes_per_record"] * values["normalized_copies"],
               "index_including_replicas_bytes": indexed,
               "merge_extra_bytes": math.ceil(indexed * values["merge_overhead_fraction"]),
               "fixed_bytes": values["fixed_disk_bytes"]}
    storage["peak_before_headroom_bytes"] = sum(storage.values())
    storage["required_free_bytes"] = math.ceil(storage["peak_before_headroom_bytes"] / (1 - values["free_disk_fraction"]))
    # Query cardinality, JVM/cache demand and shard layout require measurements;
    # this is only a startup/workflow floor plus bounded transport buffers.
    buffers = workers * page * (values["raw_bytes_per_record"] + values["normalized_bytes_per_record"]) * 8
    required_ram = settings["memory_floor"] + buffers
    if settings["backend"] == "fixture":
        required_ram += target_rows * values["fixture_memory_bytes_per_record"]
    checks = []
    for resource, actual, required in (("available_memory_bytes", ram, required_ram),
                                       ("free_disk_bytes", free_disk, storage["required_free_bytes"]),
                                       ("effective_cpu_count", cpu, settings["cpu_floor"])):
        checks.append({"resource": resource, "observed": actual, "required": required,
                       "status": "unknown" if actual is None else ("modeled_fit" if actual >= required else "insufficient")})
    if settings["backend"] == "fixture" and target_rows > 100000:
        checks.append({"resource": "default_fixture_row_budget", "observed": target_rows,
                       "required": 100000, "status": "insufficient"})
    states = {check["status"] for check in checks}
    status = "insufficient" if "insufficient" in states else ("unknown" if "unknown" in states else "modeled_fit")
    warnings = ["Sizing assumptions are estimates, not measured dataset sizes or throughput.",
                "Modeled fit does not validate Elasticsearch/Kibana, latency, concurrency, coverage or production readiness.",
                "Memory is a workflow floor; query cardinality, shards, JVM heap and filesystem cache require real measurements.",
                "Storage models all capture/staging/normalized/index copies coexisting on the probed filesystem; backups/LLM/assets are additional.",
                "No rows are sampled or removed; configured analytical/export limits remain unchanged."]
    if copies > 1 and settings["backend"] == "elasticsearch":
        warnings.append(f"Replica assumption requires at least {copies} suitable Elasticsearch data nodes; combined disk is not per-node sizing.")
    if profile == "development" and target_rows > 100000:
        warnings.append("Requested rows exceed the default fixture guard; use Elasticsearch or explicitly review a bounded fixture configuration.")
    if profile == "scale-lab":
        warnings.append("Scale-lab is a planning scenario only; distributed topology and physical scaling remain unvalidated.")
    return {"schema_version": 1, "evidence_kind": "modeled_capacity", "profile": profile,
            "target_rows": target_rows, "backend": settings["backend"], "status": status,
            "ready_for_production": False, "assumptions": values, "storage": storage,
            "memory": {"workflow_floor_bytes": settings["memory_floor"], "buffer_estimate_bytes": buffers,
                       "required_available_bytes": required_ram},
            "checks": checks, "suggestions": {"budgets": {"page_size": page, "max_concurrent_exports": workers},
                                             "capture": {"page_size": page}, "ingest": {"batch_size": page}},
            "next_steps": ["Review and explicitly apply desired budgets to your configuration.",
                           "Measure indexed bytes/record and representative queries on the intended engine/host.",
                           "Repeat at increasing real row counts; record correctness, latency, memory, disk and failure recovery."],
            "warnings": warnings, "inventory_warnings": observed.get("warnings", [])}
