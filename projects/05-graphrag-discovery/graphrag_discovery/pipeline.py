"""Bounded, cached local extraction. Publication remains a separate operation."""
import json
import time

from .records import DomainError, cache_key, validate_assertion
from .model_budget import call_allowance


class PipelineMixin:
    def extract_job(self, job_id, client, *, max_calls=100, max_wall_seconds=600, max_assertions_per_record=32):
        if type(max_calls) is not int or not 1 <= max_calls <= 1000 or type(max_wall_seconds) not in (int, float) or not 1 <= max_wall_seconds <= 3600:
            raise DomainError("invalid_budget", "Invalid local extraction allowance")
        if type(max_assertions_per_record) is not int or not 1 <= max_assertions_per_record <= 128:
            raise DomainError("invalid_budget", "Assertion allowance must be 1–128 per source")
        job = self._one("jobs", job_id)
        if job["snapshot_id"] or job["status"] == "cancelled":
            raise DomainError("job_closed", "Cannot extract a closed job")
        if job["assertions"] is not None:
            raise DomainError("already_prepared", "Assertions already prepared; inspect or publish the job")
        assertions, outcomes, calls, hits, began = [], [], 0, 0, time.monotonic()
        config = dict(client.profile, max_assertions=max_assertions_per_record)
        for record in json.loads(job["records"]):
            if record["operation"] != "upsert":
                continue
            current = self._one("jobs", job_id)
            if current["snapshot_id"] or current["status"] == "cancelled":
                raise DomainError("job_closed", "Job closed during extraction; nothing staged")
            if time.monotonic()-began >= max_wall_seconds:
                raise DomainError("extraction_budget_exhausted", "No assertions staged; validated per-record cache is available for retry", {"calls": calls, "cache_hits": hits})
            key = cache_key(record, config, prompt_version=str(client.profile.get("prompt_version", "1")))
            cached = self.db.execute("SELECT payload FROM model_cache WHERE cache_key=?", (key,)).fetchone()
            if cached:
                output = json.loads(cached["payload"])
                hits += 1
            else:
                if calls >= max_calls:
                    raise DomainError("extraction_budget_exhausted", "No assertions staged; validated per-record cache is available for retry", {"calls": calls, "cache_hits": hits})
                calls += 1
                with call_allowance(client, max_wall_seconds - (time.monotonic()-began)):
                    output = client.extract(record, max_assertions=max_assertions_per_record)
            normalized = [validate_assertion(a, record) for a in output["assertions"]]
            if len(normalized) > max_assertions_per_record or any(a["method"] != "local-model-v1" for a in normalized):
                raise DomainError("invalid_model_output", "Local extractor exceeded its declared output contract")
            if not cached:
                with self.db:
                    self.db.execute("INSERT OR IGNORE INTO model_cache VALUES(?,?,?)", (key, json.dumps(dict(output, assertions=normalized), allow_nan=False), self._now()))
            assertions.extend(normalized)
            if len(assertions) > 5000:
                raise DomainError("batch_limit", "Extract smaller jobs; assertion count exceeds 5000")
            outcomes.append({"document_id": record["document_id"], "version_id": record["version_id"], "assertions": len(normalized), "status": "succeeded_with_assertions" if normalized else "abstained", "cache_hit": bool(cached), "metadata": output["metadata"]})
        if time.monotonic()-began >= max_wall_seconds:
            raise DomainError("extraction_budget_exhausted", "Local call exceeded allowance; nothing staged", {"calls": calls, "cache_hits": hits})
        metadata = {"method": "local-model-v1", "profile": config, "model_calls": calls, "cache_hits": hits, "outcomes": outcomes, "elapsed_ms": round((time.monotonic()-began)*1000, 3)}
        staged = self.stage_assertions(job_id, assertions, preparation=metadata)
        return dict(staged, extraction=metadata)
