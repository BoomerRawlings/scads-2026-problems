import copy
import json
from pathlib import Path
import tempfile
import unittest

from analytics311.errors import AnalyticsError
from analytics311.service import AnalyticsService
from analytics311.settings import effective_budgets, validate_manifest


class SettingsTests(unittest.TestCase):
    def test_effective_limits_are_explicit_and_typed(self):
        limits = effective_budgets({})
        self.assertEqual(limits['max_concurrent_exports'], 2)
        for value in (True, 0, -1, 3.1, float('inf'), float('nan'), '3'):
            with self.subTest(value=value), self.assertRaises(AnalyticsError):
                effective_budgets({'max_export_bytes': value})
        with self.assertRaises(AnalyticsError):
            effective_budgets({'max_export_byte': 100})

    def test_omitted_preview_uses_lower_configured_cap(self):
        from analytics311.contracts import normalize_spec
        spec={'dataset_version':'fixture-v1','operation':'aggregate'}
        self.assertEqual(normalize_spec(spec,{}, {'max_preview_rows':10})['preview_limit'],5)
        self.assertEqual(normalize_spec(spec,{}, {'max_preview_rows':3})['preview_limit'],3)
        self.assertEqual(normalize_spec({**spec,'preview_limit':10},{},{'max_preview_rows':10})['preview_limit'],10)
        with self.assertRaises(AnalyticsError):
            normalize_spec({**spec,'preview_limit':11},{},{'max_preview_rows':10})

    def test_manifest_does_not_coerce_coverage_truth(self):
        for value in ('false', 'true', 1, None):
            with self.subTest(value=value), self.assertRaises(AnalyticsError):
                validate_manifest({'dataset_version':'x','coverage':{'complete':value}})
        validate_manifest({'dataset_version':'x','coverage':{'complete':False}})

    def test_manifest_rejects_unusable_complete_intervals(self):
        for span in ({}, {'gte':'2025-01-01','lt':'2026-01-01'},
                     {'gte':'2026-01-01T00:00:00Z','lt':'2025-01-01T00:00:00Z'}):
            with self.subTest(span=span), self.assertRaises(AnalyticsError):
                validate_manifest({'dataset_version':'x','coverage':{**span,'complete':True}})

    def test_nested_date_filter_without_enclosing_window_cannot_claim_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            from analytics311.resources import default_config_path, load_profile
            _, config = load_profile(default_config_path(), workdir=directory)
            file = Path(directory)/'config.json'
            file.write_text(json.dumps(config))
            service = AnalyticsService(file)
            spec = {'dataset_version':'fixture-v1','operation':'aggregate','filters':{'any':[
                {'field':'created_date','op':'range','value':{'gte':'2030-01-01T00:00:00Z'}},
                {'field':'borough','op':'eq','value':'BROOKLYN'}]}}
            result = service.run_analysis(spec)
            self.assertFalse(result['coverage_complete'])
            bounded = copy.deepcopy(spec)
            bounded['time']={'gte':'2025-12-01T00:00:00-05:00','lt':'2026-01-01T00:00:00-05:00'}
            self.assertTrue(service.validate_analysis(bounded)['coverage_complete'])
