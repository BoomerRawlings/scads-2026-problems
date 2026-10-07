import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics311.capacity import (
    GIB, MIB, PROFILES, _cgroup_locations, _linux_limits, _linux_memory,
    _mac_memory, default_assumptions, inventory, plan_capacity,
)
from analytics311.errors import AnalyticsError
from analytics311.settings import effective_budgets


def host(ram=24 * GIB, cpu=8, disk=900 * GIB):
    return {"cpu": {"effective_count": cpu}, "memory": {"effective_available_bytes": ram},
            "disk": {"free_bytes": disk}, "warnings": []}


def cgroup_reader(files):
    normalized = {str(Path(path)): value for path, value in files.items()}
    return lambda path: normalized.get(str(Path(path)))


class CapacityModelTests(unittest.TestCase):
    def test_exact_storage_arithmetic_includes_all_concurrent_copies(self):
        result = plan_capacity("full-demo", 1000, host(), {
            "raw_bytes_per_record": 100, "staging_bytes_per_record": 200,
            "normalized_bytes_per_record": 50, "index_bytes_per_record": 150,
            "raw_copies": 2, "normalized_copies": 1, "replicas": 1,
            "merge_overhead_fraction": 0.5, "free_disk_fraction": 0.25, "fixed_disk_bytes": 1000})
        storage = result["storage"]
        self.assertEqual(storage["index_including_replicas_bytes"], 300000)
        self.assertEqual(storage["merge_extra_bytes"], 150000)
        self.assertEqual(storage["peak_before_headroom_bytes"], 901000)
        self.assertEqual(storage["required_free_bytes"], 1201334)
        self.assertEqual(result["evidence_kind"], "modeled_capacity")
        self.assertFalse(result["ready_for_production"])

    def test_weak_machine_can_plan_fixture_but_not_elastic(self):
        weak = host(ram=600 * MIB, cpu=2, disk=16 * GIB)
        self.assertEqual(plan_capacity("development", 1000, weak)["status"], "modeled_fit")
        self.assertEqual(plan_capacity("local-integration", 1000, weak)["status"], "insufficient")
        self.assertEqual(plan_capacity("full-demo", 2000000, weak)["status"], "insufficient")

    def test_large_fixture_request_never_becomes_sample(self):
        result = plan_capacity("development", 2000000, host(ram=200 * GIB))
        self.assertEqual(result["target_rows"], 2000000)
        self.assertEqual(result["status"], "insufficient")
        self.assertNotIn("max_fixture_rows", result["suggestions"]["budgets"])
        self.assertIn("default_fixture_row_budget", [item["resource"] for item in result["checks"]])

    def test_billion_rows_is_arithmetic_only_with_no_allocation(self):
        strong = host(ram=192 * GIB, cpu=64, disk=16 * 1024 * GIB)
        result = plan_capacity("scale-lab", 1000000000, strong)
        self.assertEqual(result["target_rows"], 1000000000)
        self.assertEqual(result["status"], "modeled_fit")
        self.assertGreater(result["storage"]["required_free_bytes"], 10 * 1024 * GIB)
        self.assertFalse(result["ready_for_production"])
        self.assertTrue(any("unvalidated" in item for item in result["warnings"]))
        self.assertNotIn("throughput", result)

    def test_unknowns_are_unknown_not_zero_or_fit(self):
        result = plan_capacity("full-demo", 2000000, {})
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(all(item["observed"] is None and item["status"] == "unknown" for item in result["checks"]))
        self.assertEqual(result["suggestions"]["budgets"], {"page_size": 100, "max_concurrent_exports": 1})
        self.assertEqual(plan_capacity("full-demo", 2000000, host(ram=0))["status"], "insufficient")

    def test_low_current_availability_wins_over_large_installed_ram(self):
        values = host(ram=100 * MIB)
        values["memory"]["total_bytes"] = 256 * GIB
        values["memory"]["effective_total_bytes"] = 256 * GIB
        result = plan_capacity("development", 1000, values)
        self.assertEqual(result["status"], "insufficient")

    def test_unknown_and_insufficient_prioritize_known_shortage(self):
        values = host(ram=None, disk=1)
        self.assertEqual(plan_capacity("full-demo", 2000000, values)["status"], "insufficient")

    def test_suggestions_only_change_scheduling_and_fit_runtime_contract(self):
        for profile in PROFILES:
            for values in ({}, host(ram=100 * MIB, cpu=0.5), host(), host(ram=200 * GIB, cpu=64)):
                with self.subTest(profile=profile, values=values):
                    result = plan_capacity(profile, 1000, values)
                    budgets = result["suggestions"]["budgets"]
                    self.assertEqual(set(budgets), {"page_size", "max_concurrent_exports"})
                    effective_budgets(budgets)
                    self.assertLessEqual(result["suggestions"]["ingest"]["batch_size"], 1000)
                    self.assertLessEqual(budgets["max_concurrent_exports"], 4)

    def test_model_does_not_mutate_inputs(self):
        values, assumptions = host(), {"replicas": 2}
        original = copy.deepcopy((values, assumptions))
        plan_capacity("full-demo", 2000000, values, assumptions)
        self.assertEqual((values, assumptions), original)

    def test_invalid_profiles_and_counts(self):
        for profile, rows in (("auto", 1000), ("full-demo", True), ("full-demo", 0), ("full-demo", 10 ** 13), ("full-demo", "1000")):
            with self.subTest(profile=profile, rows=rows), self.assertRaises(AnalyticsError):
                plan_capacity(profile, rows, {})

    def test_invalid_assumptions_reject_false_precision(self):
        for assumptions in ({"raw_bytes_per_record": True}, {"replicas": -1}, {"raw_copies": 0},
                            {"merge_overhead_fraction": float("nan")}, {"free_disk_fraction": float("inf")},
                            {"free_disk_fraction": 1}, {"merge_overhead_fraction": 10 ** 1000},
                            {"index_bytes_per_record": 1.5}, {"workers": 1000}, []):
            with self.subTest(assumptions=assumptions), self.assertRaises(AnalyticsError):
                plan_capacity("full-demo", 1000, {}, assumptions)

    def test_invalid_observations_are_rejected(self):
        for values in ({"cpu": {"effective_count": True}}, {"cpu": {"effective_count": float("nan")}},
                       {"memory": {"effective_available_bytes": -1}}, {"disk": []},
                       {"disk": {"free_bytes": 10 ** 1000}}, {"warnings": "good"}, []):
            with self.subTest(values=values), self.assertRaises(AnalyticsError):
                plan_capacity("full-demo", 1000, values)

    def test_stated_replication_increases_estimate_and_requires_nodes(self):
        one = plan_capacity("local-integration", 2000000, host())
        two = plan_capacity("local-integration", 2000000, host(), {"replicas": 1})
        self.assertGreater(two["storage"]["required_free_bytes"], one["storage"]["required_free_bytes"])
        self.assertTrue(any("at least 2" in item for item in two["warnings"]))


class InventoryTests(unittest.TestCase):
    def test_linux_memavailable_and_conservative_fallback(self):
        with patch("analytics311.capacity._read", return_value="MemTotal: 100 kB\nMemAvailable: 30 kB\nMemFree: 5 kB"):
            self.assertEqual(_linux_memory()[:2], (102400, 30720))
        with patch("analytics311.capacity._read", return_value="MemTotal: 100 kB\nMemFree: 5 kB"):
            self.assertEqual(_linux_memory()[:2], (102400, 5120))
        with patch("analytics311.capacity._read", return_value=None):
            self.assertEqual(_linux_memory()[:2], (None, None))

    def test_mac_uses_reported_page_size_and_free_lower_bound(self):
        text = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 100.\nPages inactive: 999999."
        with patch("analytics311.capacity.subprocess.check_output", side_effect=[str(16 * GIB), text]):
            result = _mac_memory()
        self.assertEqual(result[:2], (16 * GIB, 1638400))
        self.assertIn("lower bound", result[2])

    def test_cgroup_v2_ancestors_limit_memory_headroom_and_cpu(self):
        read = cgroup_reader({"/proc/self/cgroup": "0::/parent/child",
            "/proc/self/mountinfo": "1 0 0:1 / /cg rw - cgroup2 cgroup rw",
            "/cg/parent/child/memory.max": str(8 * GIB), "/cg/parent/child/memory.current": str(2 * GIB),
            "/cg/parent/memory.max": str(4 * GIB), "/cg/parent/memory.current": str(3 * GIB),
            "/cg/parent/child/cpu.max": "200000 100000", "/cg/parent/cpu.max": "50000 100000"})
        result = _linux_limits(read)
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["memory_limit_bytes"], 4 * GIB)
        self.assertEqual(result["memory_headroom_bytes"], GIB)
        self.assertEqual(result["cpu_quota_count"], 0.5)

    def test_cgroup_v1_cpu_and_memory_with_unlimited_parent(self):
        read = cgroup_reader({"/proc/self/cgroup": "5:memory:/x\n4:cpu,cpuacct:/x",
            "/proc/self/mountinfo": "1 0 0:1 / /cg/mem rw - cgroup cgroup rw,memory\n2 0 0:2 / /cg/cpu rw - cgroup cgroup rw,cpu,cpuacct",
            "/cg/mem/x/memory.limit_in_bytes": str(2 * GIB), "/cg/mem/x/memory.usage_in_bytes": str(GIB),
            "/cg/mem/memory.limit_in_bytes": str(2 ** 63 - 4096),
            "/cg/cpu/x/cpu.cfs_quota_us": "150000", "/cg/cpu/x/cpu.cfs_period_us": "100000",
            "/cg/cpu/cpu.cfs_quota_us": "-1"})
        result = _linux_limits(read)
        self.assertEqual(result["memory_limit_bytes"], 2 * GIB)
        self.assertEqual(result["memory_headroom_bytes"], GIB)
        self.assertEqual(result["cpu_quota_count"], 1.5)

    def test_cgroup_unknown_usage_or_hidden_ancestors_not_capacity_claim(self):
        files = {"/proc/self/cgroup": "0::/x", "/proc/self/mountinfo": "1 0 0:1 / /cg rw - cgroup2 cgroup rw",
                 "/cg/x/memory.max": "1000"}
        result = _linux_limits(cgroup_reader(files))
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["memory_headroom_bytes"])
        files["/proc/self/mountinfo"] = "1 0 0:1 /container /cg rw - cgroup2 cgroup rw"
        files["/cg/x/memory.current"] = "100"
        result = _linux_limits(cgroup_reader(files))
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(any("hides ancestors" in item for item in result["warnings"]))

    def test_unreadable_unmappable_or_malformed_cgroups_are_unknown(self):
        for files in ({}, {"/proc/self/cgroup": "0::/x", "/proc/self/mountinfo": ""},
                      {"/proc/self/cgroup": "0::/x", "/proc/self/mountinfo": "1 0 0:1 / /cg rw - cgroup2 cgroup rw"},
                      {"/proc/self/cgroup": "0::/x", "/proc/self/mountinfo": "1 0 0:1 / /cg rw - cgroup2 cgroup rw",
                       "/cg/x/cpu.max": "2 0"},
                      {"/proc/self/cgroup": "0::/x", "/proc/self/mountinfo": "1 0 0:1 / /cg rw - cgroup2 cgroup rw",
                       "/cg/x/memory.max": "-1", "/cg/x/cpu.max": "max 100000"}):
            with self.subTest(files=files):
                self.assertEqual(_linux_limits(cgroup_reader(files))["status"], "unknown")

    def test_unlimited_cgroups_do_not_invent_zero_capacity(self):
        result = _linux_limits(cgroup_reader({"/proc/self/cgroup": "0::/x",
            "/proc/self/mountinfo": "1 0 0:1 / /cg rw - cgroup2 cgroup rw",
            "/cg/x/memory.max": "max", "/cg/x/cpu.max": "max 100000"}))
        self.assertEqual(result["status"], "observed")
        self.assertIsNone(result["memory_limit_bytes"])
        self.assertIsNone(result["cpu_quota_count"])

    def test_mount_escapes_and_namespace_paths_remain_under_mount(self):
        locations = _cgroup_locations("0::/a", "1 0 0:1 / /cg\\040space rw - cgroup2 cgroup rw")
        self.assertEqual(locations[0][1], Path("/cg space/a"))
        self.assertEqual(_cgroup_locations("0::/../escape", "1 0 0:1 / /cg rw - cgroup2 cgroup rw"), [])

    def test_inventory_applies_limits_not_installed_memory(self):
        limits = {"status": "observed", "warnings": [], "memory_limit_bytes": 4 * GIB,
                  "memory_headroom_bytes": GIB, "cpu_quota_count": 0.5}
        with tempfile.TemporaryDirectory() as directory, patch("analytics311.capacity.platform.system", return_value="Linux"), \
                patch("analytics311.capacity._linux_memory", return_value=(32 * GIB, 24 * GIB, "test")), \
                patch("analytics311.capacity._linux_limits", return_value=limits):
            observed = inventory(directory)
        self.assertEqual(observed["memory"]["effective_total_bytes"], 4 * GIB)
        self.assertEqual(observed["memory"]["effective_available_bytes"], GIB)
        self.assertEqual(observed["cpu"]["effective_count"], 0.5)
        self.assertNotIn(directory, json.dumps(observed))

    def test_missing_memory_and_disk_are_explicit_nulls(self):
        with patch("analytics311.capacity.platform.system", return_value="unknown"), \
                patch("analytics311.capacity.shutil.disk_usage", side_effect=OSError):
            result = inventory("missing")
        self.assertIsNone(result["memory"]["effective_available_bytes"])
        self.assertIsNone(result["disk"]["free_bytes"])
        self.assertEqual(plan_capacity("development", 1000, result)["status"], "unknown")

    def test_read_only_inventory_serializes_and_does_not_touch_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            before = list(Path(directory).iterdir())
            result = inventory(directory)
            self.assertEqual(list(Path(directory).iterdir()), before)
            json.dumps(result, allow_nan=False)
        self.assertEqual(result["evidence_kind"], "observed_inventory")


if __name__ == "__main__":
    unittest.main()
