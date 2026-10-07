import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from analytics311.errors import AnalyticsError
from analytics311.ingest import create_index, ingest_jsonl
from analytics311.resources import asset_path


class IndexSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'mapping.json'
        self.mapping=json.loads(asset_path('config/mapping.json').read_text())
        self.client=Mock()
        self.client.request.return_value={'acknowledged':True}

    def create(self):
        self.path.write_text(json.dumps(self.mapping))
        return create_index(self.client,'test-v1',self.path)

    def test_larger_shard_replica_settings_keep_contract(self):
        self.mapping['settings'].update(number_of_shards=4,number_of_replicas=1)
        self.assertTrue(self.create()['created'])
        self.assertEqual(self.client.request.call_args.args[2]['settings']['number_of_shards'],4)
        self.assertEqual(self.client.request.call_args.args[2]['settings']['index.final_pipeline'],'_none')

    def test_mapping_semantics_cannot_change_silently(self):
        self.mapping['mappings']['properties']['borough']['type']='text'
        with self.assertRaises(AnalyticsError):
            self.create()
        self.client.request.assert_not_called()

    def test_pipeline_variants_rejected_before_mutation(self):
        for key, value in [('default_pipeline','mutate'),('index.final_pipeline','mutate'),('index',{'default_pipeline':'mutate'})]:
            with self.subTest(key=key):
                self.mapping=json.loads(asset_path('config/mapping.json').read_text())
                self.mapping['settings'][key]=value
                with self.assertRaises(AnalyticsError):
                    self.create()
        self.client.request.assert_not_called()

    def test_invalid_json_is_stable_configuration_error(self):
        self.path.write_text('{broken')
        with self.assertRaises(AnalyticsError) as caught:
            create_index(self.client,'test-v1',self.path)
        self.assertEqual(caught.exception.code,'invalid_configuration')

    def test_existing_index_pipeline_rejected_before_source_read_or_write(self):
        self.client.request.return_value={'test-v1':{'settings':{'index':{'uuid':'u','final_pipeline':'mutate'}}}}
        with self.assertRaises(AnalyticsError) as caught:
            ingest_jsonl(self.path,self.client,'test-v1')
        self.assertEqual(caught.exception.code,'invalid_configuration')
        self.assertEqual(self.client.request.call_count,1)
