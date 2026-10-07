"""Opt-in isolated media protocol tests; scripted output is not visual accuracy."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_local_agent import HAS_MCP, RawModelOutput, abstention, finish, model_server, tool
if HAS_MCP:
    import local_agent as local


def pixels_result(eid="arbitrary-source", timestamps=None):
    header = {"evidence_id": eid, "media_path": "private.png" if timestamps is None else "private.mp4",
              "text": "SOURCE_NARRATIVE_MUST_NOT_ENTER_ISOLATED_REQUEST", "audio_processed": False,
              "date": "2044-09-17", "question": "PRIVATE_QUESTION_MUST_NOT_ENTER_ISOLATED_REQUEST"}
    if timestamps is not None:
        header["samples"] = [{"source_timestamp_seconds": value, "requested_seek_seconds": value + 0.1,
                              "description": "HEADER_NARRATIVE_MUST_NOT_ENTER_ISOLATED_REQUEST"} for value in timestamps]
    count = 1 if timestamps is None else len(timestamps)
    return {"content": [{"type": "text", "text": json.dumps(header)},
                        {"type": "text", "text": "EXTRACTION_LABEL_MUST_NOT_ENTER_ISOLATED_REQUEST"}]
                       + [{"type": "image", "mimeType": "image/png", "data": f"pixel-payload-{index}"} for index in range(count)]}


def observations(*pairs):
    return {"media_observations": [{**pair, "observation": f"Visible source content at {pair['locator']}."} for pair in pairs]}


def partial_report():
    report = abstention("riverwatch")
    report.update(status="insufficient_evidence", title="Partial source inspection",
                  summary="The selected attached media was inspected; the investigation stopped before complete coverage.",
                  limitations=["Further source coverage remains necessary."], follow_up=["Inspect other relevant sources."])
    return report


def constrained_report(schema, report):
    result = copy.deepcopy(report)
    for key in ("media_observations", "limitations", "follow_up"):
        if "const" in schema["properties"][key]:
            result[key] = copy.deepcopy(schema["properties"][key]["const"])
    return result


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class GroundedMediaUnitTests(unittest.TestCase):
    def test_request_uses_only_actual_pixels_exact_ids_and_actual_audited_timestamps(self):
        eid = "unfamiliar-video-729"
        source = pixels_result(eid, [1.0, 15.125])
        before = copy.deepcopy(source)
        messages, schema, pairs = local.grounded_media_request(eid, source, {1.0, 15.125, 27.0})
        self.assertEqual(pairs, [{"evidence_id": eid, "locator": "00:01"}, {"evidence_id": eid, "locator": "00:15.125"}])
        self.assertEqual(source, before)
        self.assertEqual(sum(message["role"] == "system" for message in messages), 1)
        image_blocks = [block for message in messages if isinstance(message["content"], list)
                        for block in message["content"] if block.get("type") == "image_url"]
        self.assertEqual([block["image_url"]["url"] for block in image_blocks],
                         ["data:image/png;base64,pixel-payload-0", "data:image/png;base64,pixel-payload-1"])
        for excluded in ("SOURCE_NARRATIVE", "HEADER_NARRATIVE", "EXTRACTION_LABEL", "PRIVATE_QUESTION", "2044-09-17", "private.mp4", "00:27", "15.225"):
            self.assertNotIn(excluded, json.dumps(messages))
        from jsonschema import validate
        validate(observations(*pairs), schema)
        self.assertEqual(local.validate_grounded_observations(observations(*pairs), pairs), observations(*pairs)["media_observations"])

    def test_image_pair_and_genuinely_repeated_frame_pairs_preserve_pixel_order(self):
        _, schema, pairs = local.grounded_media_request("still-arbitrary", pixels_result("still-arbitrary"), {"image"})
        self.assertEqual(pairs, [{"evidence_id": "still-arbitrary", "locator": "image"}])
        from jsonschema import validate
        validate(observations(*pairs), schema)
        _, _, repeated = local.grounded_media_request("same-pts", pixels_result("same-pts", [1.0, 1.0]), {1.0})
        self.assertEqual(repeated, [{"evidence_id": "same-pts", "locator": "00:01"}] * 2)
        self.assertEqual(len(local.validate_grounded_observations(observations(*repeated), repeated)), 2)

    def test_request_rejects_unverified_or_mismatched_media(self):
        good = pixels_result()
        no_pixels = {"content": good["content"][:2]}
        cases = [("arbitrary-source", no_pixels, {"image"}),
                 ("wrong-id", good, {"image"}), ("arbitrary-source", good, set()),
                 ("arbitrary-source", {**good, "isError": True}, {"image"}),
                 ("arbitrary-source", pixels_result(timestamps=[15.0]), {14.5}),
                 ("arbitrary-source", {"content": [{"type": "image", "mimeType": "image/png", "data": "pixels"}]}, {"image"})]
        for eid, result, audited in cases:
            with self.subTest(eid=eid, result=result), self.assertRaises(local.RunFailure) as caught:
                local.grounded_media_request(eid, result, audited)
            self.assertEqual(caught.exception.code, "invalid_media_observation")

    def test_output_requires_exact_pairs_order_count_shape_and_nonempty_observations(self):
        pairs = [{"evidence_id": "arbitrary", "locator": "00:01"}, {"evidence_id": "arbitrary", "locator": "00:15"}]
        valid = observations(*pairs)
        variants = [None, [], {}, {"media_observations": []}, {"media_observations": valid["media_observations"][:1]},
                    {"media_observations": valid["media_observations"] * 2},
                    {"media_observations": list(reversed(valid["media_observations"]))},
                    {"media_observations": [valid["media_observations"][0]] * 2}, {**valid, "extra": "field"}]
        for key, value in (("evidence_id", "invented"), ("locator", "00:99"), ("observation", "   "), ("observation", 42)):
            candidate = copy.deepcopy(valid)
            candidate["media_observations"][0][key] = value
            variants.append(candidate)
        extra_field = copy.deepcopy(valid)
        extra_field["media_observations"][0]["claim"] = "extra"
        variants.append(extra_field)
        for index, candidate in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(local.RunFailure) as caught:
                local.validate_grounded_observations(candidate, pairs)
            self.assertEqual(caught.exception.code, "invalid_media_observation")

    def test_host_constraints_are_exact_and_only_synthetic_followup_is_fixed_empty(self):
        facts = {"policy": "current-run-provenance-v1", "scope_entity_ids": ["org"], "inventoried_scope_entity_ids": ["org"],
                 "retrieved_source_ids": ["arbitrary", "missing"], "audio_processed": False,
                 "video_coverage": "sampled_frames_only", "media": [
                     {"evidence_id": "arbitrary", "attachment_declared": True, "inspected_available": True, "returned_pixel_locators": ["00:01"]},
                     {"evidence_id": "missing", "attachment_declared": False, "returned_pixel_locators": []}]}
        items = observations({"evidence_id": "arbitrary", "locator": "00:01"})["media_observations"]
        for kind in ("synthetic", "public", "unspecified"):
            with self.subTest(kind=kind):
                constraints = local.grounded_report_constraints(facts, {"kind": kind}, items)
                self.assertEqual(constraints["media_observations"], items)
                self.assertTrue(constraints["limitations"])
                self.assertTrue(all(isinstance(line, str) and line.strip() for line in constraints["limitations"]))
                if kind == "synthetic":
                    self.assertEqual(constraints["follow_up"], [])
                else:
                    self.assertNotIn("follow_up", constraints)
                report = {**partial_report(), **constraints}
                local.validate_grounded_report(report, constraints)
                schema = local.report_output_schema({"status": report["status"], "target": report["target"]}, {"arbitrary"},
                                                     media_reads={"arbitrary": {1.0}}, grounded_constraints=constraints)
                from jsonschema import ValidationError, validate
                validate(report, schema)
                for field, value in constraints.items():
                    self.assertEqual(schema["properties"][field]["const"], value)
                    changed = copy.deepcopy(report)
                    changed[field] = [] if value else ["invented"]
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        local.validate_grounded_report(changed, constraints)
                    with self.assertRaises(ValidationError):
                        validate(changed, schema)

    def test_host_media_gaps_distinguish_declaration_inspection_and_pixels(self):
        facts = {"scope_entity_ids": ["org"], "inventoried_scope_entity_ids": ["org"], "video_coverage": "none", "media": [
            {"evidence_id": "no-declaration", "attachment_declared": False, "returned_pixel_locators": []},
            {"evidence_id": "unavailable", "attachment_declared": True, "inspected_available": False, "returned_pixel_locators": []},
            {"evidence_id": "available-unread", "attachment_declared": True, "inspected_available": True, "returned_pixel_locators": []},
            {"evidence_id": "actual-pixels", "attachment_declared": True, "inspected_available": True,
             "returned_pixel_locators": ["image"], "text": "HISTORICAL_NO_RAW_MEDIA_LABEL"}]}
        constraints = local.grounded_report_constraints(facts, {"kind": "public"}, observations(
            {"evidence_id": "actual-pixels", "locator": "image"})["media_observations"])
        text = "\n".join(constraints["limitations"])
        gaps = next(line for line in constraints["limitations"] if "no-declaration" in line)
        undeclared = gaps.split('"no-declaration":', 1)[1].split('"unavailable":', 1)[0].lower()
        unavailable = gaps.split('"unavailable":', 1)[1].split('"available-unread":', 1)[0].lower()
        unread = gaps.split('"available-unread":', 1)[1].lower()
        self.assertIn("no attachment declared", undeclared)
        self.assertIn("not inspected", undeclared)
        self.assertNotIn("unavailable", undeclared)
        self.assertIn("attachment declared", unavailable)
        self.assertIn("unavailable", unavailable)
        self.assertIn("available", unread)
        self.assertIn("no pixels", unread)
        self.assertNotIn("actual-pixels", gaps)
        self.assertIn('"actual-pixels": image', text)
        self.assertNotIn("HISTORICAL_NO_RAW_MEDIA_LABEL", text)


@unittest.skipUnless(HAS_MCP, "Install requirements.txt to test the local runtime")
class GroundedMediaRunTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def image_steps(report):
        return [tool("search_evidence", entity_ids=["riverwatch"]), tool("inspect_media", evidence_id="img-note-001"),
                tool("read_media", evidence_id="img-note-001"), finish(report)]

    async def test_default_run_does_not_request_isolated_observations_or_change_model_report(self):
        report = partial_report()
        actions = self.image_steps(report) + [report]
        with tempfile.TemporaryDirectory() as directory, model_server(actions) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=len(actions))
            self.assertEqual(json.loads((output / "report.json").read_text()), report)
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * 4 + [3072])
            self.assertEqual(list(output.glob("media-observation-*.json")), [])
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertFalse(metadata["grounded_media"]["enabled"])
            self.assertFalse(any(entry["phase"] == "media_observation" for entry in metadata["model_responses"]))

    async def test_each_successful_raw_call_has_one_deferred_isolated_pass_with_hashes_and_retained_pixels(self):
        report = partial_report()
        image_pair = {"evidence_id": "img-note-001", "locator": "image"}
        video_pair = {"evidence_id": "video-tx-001", "locator": "00:00"}
        secret = "PRIVATE_REASONING_MUST_NEVER_BE_SAVED"

        def actions():
            yield from self.image_steps(report)[:-1]
            yield tool("inspect_media", evidence_id="video-tx-001")
            yield tool("read_media", evidence_id="video-tx-001", timestamps=[0])
            yield finish(report)
            yield RawModelOutput(json.dumps(observations(image_pair)), reasoning_content=secret)
            yield RawModelOutput(json.dumps(observations(video_pair)), reasoning_content=secret)
            yield constrained_report(calls[-1]["payload"]["response_format"]["schema"], report)

        with tempfile.TemporaryDirectory() as directory, model_server(actions()) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=9, grounded_media=True)
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * 6 + [1536, 1536, 3072])
            self.assertEqual([item["phase"] for item in metadata["model_responses"]], ["decision"] * 6 + ["media_observation"] * 2 + ["report"])
            grounding = metadata["grounded_media"]
            self.assertTrue(grounding["enabled"])
            self.assertEqual(grounding["policy"], "deferred-isolated-pixels-v1")
            self.assertEqual(len(grounding["observations"]), 2)
            trace = json.loads((output / "tool-trace.json").read_text())
            self.assertEqual([entry["name"] for entry in trace], ["search_evidence", "inspect_media", "read_media", "inspect_media", "read_media"])
            for index, (entry, inference) in enumerate(zip(grounding["observations"], calls[6:8]), 1):
                self.assertEqual(entry["status"], "observed")
                self.assertEqual(entry["call"], 3 if index == 1 else 5)
                self.assertEqual(entry["path"], f"media-observation-{index:02d}.json")
                self.assertEqual(len(entry["input_sha256"]), 64)
                int(entry["input_sha256"], 16)
                self.assertEqual(hashlib.sha256((output / entry["path"]).read_bytes()).hexdigest(), entry["output_sha256"])
                request = inference["payload"]
                fingerprint = {"messages": request["messages"], "schema": request["response_format"]["schema"],
                               "settings": {key: request[key] for key in ("temperature", "seed", "max_tokens", "chat_template_kwargs")}}
                self.assertEqual(entry["input_sha256"], hashlib.sha256(json.dumps(
                    fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest())
                self.assertEqual(request["temperature"], 0)
                self.assertEqual(request["chat_template_kwargs"], {"enable_thinking": False})
                self.assertNotIn("reasoning_budget_tokens", request)
                self.assertIn("image_url", json.dumps(request["messages"]))
                self.assertNotIn("UNTRUSTED TOOL RESULT", json.dumps(request["messages"]))
                self.assertNotIn("CURRENT_RUN_FACTS", json.dumps(request["messages"]))
            final = json.loads((output / "report.json").read_text())
            self.assertEqual(final["media_observations"], observations(image_pair, video_pair)["media_observations"])
            self.assertEqual(final["follow_up"], [])
            planner_sources = [message for message in calls[5]["payload"]["messages"]
                               if isinstance(message.get("content"), list) and "UNTRUSTED TOOL RESULT" in json.dumps(message["content"][0])]
            final_sources = [message for message in calls[-1]["payload"]["messages"]
                             if isinstance(message.get("content"), list) and "UNTRUSTED TOOL RESULT" in json.dumps(message["content"][0])]
            self.assertEqual([message["content"][1:] for message in final_sources], [message["content"][1:] for message in planner_sources])
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    content = artifact.read_text(encoding="utf-8")
                    self.assertNotIn(secret, content, artifact.name)
                    self.assertNotIn("data:image/", content, artifact.name)

    async def test_observation_and_final_report_budget_is_reserved_before_any_isolated_request(self):
        report = partial_report()
        for budget in (4, 5):
            with self.subTest(max_steps=budget), tempfile.TemporaryDirectory() as directory, model_server(self.image_steps(report)) as (url, calls):
                output = Path(directory) / "run"
                with self.assertRaises(local.RunFailure) as caught:
                    await local.run("riverwatch", output, base_url=url, max_steps=budget, grounded_media=True)
                self.assertEqual(caught.exception.code, "step_limit")
                self.assertEqual(len(calls), 4)
                self.assertTrue(all(call["payload"]["max_tokens"] == 512 for call in calls))
                self.assertFalse((output / "report.json").exists())
                self.assertFalse(list(output.glob("media-observation-*.json")))

    async def test_invalid_isolated_response_fails_without_report_generation_or_reasoning_leak(self):
        report = partial_report()
        secret = "PRIVATE_INVALID_OBSERVATION_REASONING"
        invalids = [RawModelOutput("{", reasoning_content=secret),
                    RawModelOutput(json.dumps(observations({"evidence_id": "invented", "locator": "image"})), reasoning_content=secret)]
        for invalid in invalids:
            with self.subTest(content=invalid.content), tempfile.TemporaryDirectory() as directory, model_server(self.image_steps(report) + [invalid]) as (url, calls):
                output = Path(directory) / "run"
                with self.assertRaises(local.RunFailure) as caught:
                    await local.run("riverwatch", output, base_url=url, max_steps=6, grounded_media=True)
                self.assertEqual(caught.exception.code, "invalid_media_observation")
                self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * 4 + [1536])
                self.assertFalse((output / "report.json").exists())
                metadata = json.loads((output / "run-metadata.json").read_text())
                self.assertEqual(metadata["status"], "failed")
                self.assertEqual(metadata["grounded_media"]["observations"][-1]["status"], "rejected")
                for artifact in output.rglob("*"):
                    if artifact.is_file():
                        self.assertNotIn(secret, artifact.read_text(encoding="utf-8"), artifact.name)

    async def test_constrained_report_rejection_preserves_draft_and_reuses_observation(self):
        report = partial_report()
        pair = {"evidence_id": "img-note-001", "locator": "image"}
        wrong = None

        def actions():
            nonlocal wrong
            yield from self.image_steps(report)
            yield observations(pair)
            wrong = constrained_report(calls[-1]["payload"]["response_format"]["schema"], report)
            wrong["media_observations"][0]["observation"] = "ALTERED_AFTER_ISOLATED_PASS"
            yield wrong
            yield finish(report)
            yield constrained_report(calls[-1]["payload"]["response_format"]["schema"], report)

        with tempfile.TemporaryDirectory() as directory, model_server(actions()) as (url, calls):
            output = await local.run("riverwatch", Path(directory) / "run", base_url=url, max_steps=8, grounded_media=True)
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["report_rejections"], 1)
            self.assertEqual(len(metadata["grounded_media"]["observations"]), 1)
            self.assertEqual([call["payload"]["max_tokens"] for call in calls], [512] * 4 + [1536, 3072, 512, 3072])
            self.assertEqual(json.loads((output / "rejected-report-01.json").read_text()), wrong)
            self.assertEqual(json.loads((output / "report.json").read_text())["media_observations"], observations(pair)["media_observations"])
            self.assertNotIn("ALTERED_AFTER_ISOLATED_PASS", json.dumps(calls[-1]["payload"]["messages"]))

    async def test_copied_input_pixels_are_rejected_without_saving_output_body(self):
        report = partial_report()
        encoded = None

        def actions():
            nonlocal encoded
            yield from self.image_steps(report)
            images = [block for message in calls[-1]["payload"]["messages"] if isinstance(message.get("content"), list)
                      for block in message["content"] if block.get("type") == "image_url"]
            encoded = images[0]["image_url"]["url"].split(",", 1)[1]
            candidate = {"media_observations": [{"evidence_id": "img-note-001", "locator": "image", "observation": encoded}]}
            # JSON-escaped base64 must not evade detection in the parsed answer.
            self.assertIn("/", encoded)
            yield RawModelOutput(json.dumps(candidate).replace("/", "\\/"))

        with tempfile.TemporaryDirectory() as directory, model_server(actions()) as (url, calls):
            output = Path(directory) / "run"
            with self.assertRaises(local.RunFailure) as caught:
                await local.run("riverwatch", output, base_url=url, max_steps=6, grounded_media=True)
            self.assertEqual(caught.exception.code, "invalid_media_observation")
            self.assertTrue(encoded)
            self.assertFalse((output / "report.json").exists())
            self.assertFalse(list(output.glob("media-observation-*.json")))
            metadata = json.loads((output / "run-metadata.json").read_text())
            observation = metadata["grounded_media"]["observations"][-1]
            self.assertEqual(observation["status"], "rejected")
            self.assertIsNone(observation["path"])
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(encoded, artifact.read_text(encoding="utf-8"), artifact.name)

    async def test_truncated_isolated_output_retains_safe_usage_and_never_becomes_report(self):
        report = partial_report()
        secret = "PRIVATE_TRUNCATED_REASONING"
        truncated = RawModelOutput("{" + secret, finish_reason="length", reasoning_content=secret,
                                   usage={"completion_tokens": 1536, "prompt_tokens": 100, "private": secret})
        with tempfile.TemporaryDirectory() as directory, model_server(self.image_steps(report) + [truncated]) as (url, calls):
            output = Path(directory) / "run"
            with self.assertRaises(local.RunFailure) as caught:
                await local.run("riverwatch", output, base_url=url, max_steps=6, grounded_media=True)
            self.assertEqual(caught.exception.code, "generation_limit")
            self.assertEqual(len(calls), 5)
            self.assertFalse((output / "report.json").exists())
            self.assertFalse(list(output.glob("media-observation-*.json")))
            metadata = json.loads((output / "run-metadata.json").read_text())
            self.assertEqual(metadata["grounded_media"]["observations"][-1]["status"], "rejected")
            self.assertEqual(metadata["model_responses"][-1], {"step": 5, "phase": "media_observation",
                             "usage": {"prompt_tokens": 100, "completion_tokens": 1536}, "reasoning_returned": True})
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(secret, artifact.read_text(encoding="utf-8"), artifact.name)


if __name__ == "__main__":
    unittest.main()
