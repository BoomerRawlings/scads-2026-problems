import copy
import io
import json
import unittest
from unittest.mock import patch

from analytics311.elastic import ElasticBackend, ElasticClient, validate_index
from analytics311.errors import AnalyticsError


INDEX = "nyc311-test-v1"
MANIFEST = {"immutable": True, "index": INDEX, "index_uuid": "test-uuid"}


def page(total=2, hits=None, buckets=None, after=None, **updates):
    response = {"timed_out": False, "_shards": {"total": 1, "successful": 1, "failed": 0},
                "hits": {"total": {"value": total, "relation": "eq"}, "hits": hits or []}}
    if buckets is not None:
        response["aggregations"] = {"groups": {"buckets": buckets}}
        if after is not None:
            response["aggregations"]["groups"]["after_key"] = after
    response.update(updates)
    return response


def hit(identifier):
    return {"_source": {"unique_key": str(identifier)}, "sort": [1, str(identifier), identifier]}


def spec(operation="records", **updates):
    value = {"operation": operation, "metrics": ["count"], "group_by": [],
             "preview_limit": 100, "timezone": "America/New_York"}
    value.update(updates)
    return value


class FakeClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []
        self.write_block = "true"
        self.uuid = "test-uuid"
        self.pit_shards = {"failed": 0}

    def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path.endswith("/_settings"):
            return {INDEX: {"settings": {"index": {"blocks": {"write": self.write_block}, "uuid": self.uuid}}}}
        if "/_pit?" in path:
            return {"id": "pit-original", "_shards": self.pit_shards}
        if method == "DELETE":
            return {"succeeded": True}
        return next(self.pages)


class ElasticTests(unittest.TestCase):
    def backend(self, client, **budgets):
        return ElasticBackend({"index": INDEX, "budgets": budgets}, {}, MANIFEST, client=client)

    def test_complete_composite_enumeration_uses_returned_after_key(self):
        first = page(buckets=[{"key": {"borough": "BRONX"}, "doc_count": 1}],
                     after={"borough": "BROOKLYN"}, pit_id="pit-2")
        second = page(buckets=[{"key": {"borough": "QUEENS"}, "doc_count": 1}], pit_id="pit-3")
        client = FakeClient([first, second])
        result = self.backend(client).execute(spec("aggregate", group_by=[{"field": "borough"}]))
        self.assertEqual([r["group"]["borough"] for r in result["rows"]], ["BRONX", "QUEENS"])
        requests = [c[2] for c in client.calls if c[1].startswith("/_search")]
        self.assertEqual(requests[1]["aggs"]["groups"]["composite"]["after"], {"borough": "BROOKLYN"})
        self.assertEqual(requests[1]["pit"]["id"], "pit-2")
        self.assertEqual(client.calls[-1][2], {"id": "pit-3"})

    def test_export_exceeds_10000_and_closes_latest_pit(self):
        pages = [page(10003, hits=[hit(i) for i in range(start, min(start + 5000, 10003))],
                      pit_id=f"pit-{start}") for start in range(0, 10003, 5000)]
        pages.append(page(10003, pit_id="pit-finished"))
        client = FakeClient(pages)
        records = list(self.backend(client, page_size=5000).iter_records(spec()))
        self.assertEqual(len(records), 10003)
        self.assertEqual(len({r["unique_key"] for r in records}), 10003)
        search = [c[2] for c in client.calls if c[1].startswith("/_search")]
        self.assertEqual(search[1]["search_after"], [1, "4999", 4999])
        self.assertEqual(client.calls[-1][2], {"id": "pit-finished"})

    def test_cancel_generator_closes_latest_pit(self):
        client = FakeClient([page(hits=[hit(1), hit(2)], pit_id="updated")])
        iterator = self.backend(client).iter_records(spec())
        self.assertEqual(next(iterator)["unique_key"], "1")
        iterator.close()
        self.assertEqual(client.calls[-1], ("DELETE", "/_pit", {"id": "updated"}))

    def test_partial_timeout_and_lower_bound_results_fail_and_close(self):
        responses = [page(timed_out=True), page(_shards={"failed": 1}),
                     page(hits={"total": {"value": 2, "relation": "gte"}, "hits": []}),
                     page(terminated_early=True)]
        for response in responses:
            if isinstance(response["hits"]["hits"], dict):
                response["hits"] = response["hits"]["hits"]
            with self.subTest(response=response):
                client = FakeClient([response])
                with self.assertRaises(AnalyticsError) as caught:
                    self.backend(client).execute(spec())
                self.assertEqual(caught.exception.code, "partial_execution")
                self.assertEqual(client.calls[-1][0], "DELETE")

    def test_pit_open_partial_failure_still_closes(self):
        client = FakeClient([])
        client.pit_shards = {"failed": 1}
        with self.assertRaises(AnalyticsError):
            self.backend(client).execute(spec())
        self.assertEqual(client.calls[-1][0], "DELETE")

    def test_group_budget_rejects_truncated_answer(self):
        client = FakeClient([page(buckets=[{"key": {"borough": b}, "doc_count": 1} for b in ("A", "B")])])
        with self.assertRaises(AnalyticsError) as caught:
            self.backend(client, max_groups=1).execute(spec("aggregate", group_by=[{"field": "borough"}]))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_export_short_read_rejected(self):
        client = FakeClient([page(2, hits=[hit(1)]), page(2)])
        with self.assertRaises(AnalyticsError) as caught:
            list(self.backend(client).iter_records(spec()))
        self.assertEqual(caught.exception.code, "partial_execution")

    def test_export_counts_once_then_uses_pit_for_remaining_pages(self):
        second = page(2, hits=[hit(2)])
        final = page(2)
        second["hits"].pop("total")
        final["hits"].pop("total")
        client = FakeClient([page(2, hits=[hit(1)]), second, final])
        self.assertEqual(len(list(self.backend(client).iter_records(spec()))), 2)
        searches = [call[2] for call in client.calls if call[1].startswith("/_search")]
        self.assertEqual([body["track_total_hits"] for body in searches], [True, False, False])

    def test_deadline_rejects_before_query_and_releases_pit(self):
        client = FakeClient([])
        with patch("analytics311.elastic.time.monotonic", side_effect=[0, 31]):
            with self.assertRaises(AnalyticsError) as caught:
                self.backend(client).execute(spec())
        self.assertEqual(caught.exception.code, "budget_exceeded")
        self.assertEqual(client.calls[-1][0], "DELETE")

    def test_export_limit_checked_before_first_row(self):
        client = FakeClient([page(2, hits=[hit(1)])])
        with self.assertRaises(AnalyticsError) as caught:
            next(self.backend(client, max_export_rows=1).iter_records(spec()))
        self.assertEqual(caught.exception.code, "budget_exceeded")

    def test_mutable_or_replaced_snapshot_rejected(self):
        for setting, value in (("write_block", "false"), ("uuid", "new-uuid")):
            client = FakeClient([])
            setattr(client, setting, value)
            with self.assertRaises(AnalyticsError):
                self.backend(client).execute(spec())
            self.assertEqual(len(client.calls), 1)

    def test_metrics_and_date_keys(self):
        response = page(buckets=[{"key": {"created_date": "2025-01-01T00:00:00.000-05:00"},
                                 "doc_count": 2, "closed_count": {"doc_count": 1},
                                 "median_closure_hours": {"values": {"50.0": 2.5}}}])
        result = self.backend(FakeClient([response])).execute(spec("aggregate", metrics=["count", "closed_count", "median_closure_hours"],
                              group_by=[{"field": "created_date", "interval": "month"}]))
        self.assertTrue(result["approximate"])
        self.assertEqual(result["rows"][0], {"group": {"created_date": "2025-01-01T00:00:00-05:00"},
                         "count": 2, "closed_count": 1, "median_closure_hours": 2.5})

    def test_no_group_count_empty_result(self):
        result = self.backend(FakeClient([page(0)])).execute(spec("aggregate"))
        self.assertEqual(result["rows"], [{"group": {}, "count": 0}])

    def test_index_selectors_rejected(self):
        for index in ("*", "nyc", "nyc-v1,other-v1", "../nyc-v1", "_all", "NYC-v1"):
            with self.subTest(index=index), self.assertRaises(AnalyticsError):
                validate_index(index)

    @patch.dict("os.environ", {}, clear=True)
    def test_http_requires_explicit_loopback_development(self):
        for url in ("http://example.com:9200", "https://localhost:9200", "http://localhost:9200", "https://name:secret@example.com"):
            with self.subTest(url=url), self.assertRaises(AnalyticsError):
                ElasticClient(url)
        ElasticClient("http://127.0.0.1:9200", allow_insecure_local=True, opener=object())

    @patch.dict("os.environ", {"ELASTIC_API_KEY": "test-secret"}, clear=True)
    def test_transport_auth_header_and_ndjson(self):
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return io.BytesIO(b'{"errors":false}')
        opener = Opener()
        client = ElasticClient("https://elastic.example", opener=opener)
        client.request("POST", "/nyc-v1/_bulk", b'{}\n')
        self.assertEqual(opener.request.get_header("Authorization"), "ApiKey test-secret")
        self.assertNotIn("test-secret", opener.request.full_url)
        self.assertEqual(opener.request.get_header("Content-type"), "application/x-ndjson")

    @patch.dict("os.environ", {"ELASTIC_API_KEY": "reader-only"}, clear=True)
    def test_artifact_client_never_falls_back_to_read_credentials(self):
        with self.assertRaises(AnalyticsError) as caught:
            ElasticClient("https://elastic.example", api_key_env="ELASTIC_ARTIFACT_API_KEY", opener=object())
        self.assertIn("ELASTIC_ARTIFACT_API_KEY", caught.exception.message)
        self.assertNotIn("reader-only", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
