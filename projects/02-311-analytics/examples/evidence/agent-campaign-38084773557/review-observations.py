"""Read-only review cards; no scores, judgments, model calls or trial mutations."""
import argparse
import json
from pathlib import Path
from tools import agent_evaluation as e

parser = argparse.ArgumentParser()
parser.add_argument("root")
parser.add_argument("output")
args = parser.parse_args()
root, output = Path(args.root), Path(args.output)
output.mkdir(exist_ok=False)
freeze = e.load(root / "real-v1/agent-freeze.json")
freeze_hash = e.sha_file(root / "real-v1/agent-freeze.json")
observations = []
for path in sorted((root / "agent-v1").glob("Q*-r*.json")):
    trial = e.load(path)
    assert trial["freeze_sha256"] == freeze_hash
    trace = trial["trace"]
    events = []
    for event in trace.get("events", []):
        if event.get("kind") == "tool":
            context = event.get("model_context")
            actual_output = json.loads(context["content"]) if context else event.get("output")
            events.append({"kind": "tool", "name": event.get("name"), "arguments": event.get("arguments"),
                           "initiated_by": event.get("initiated_by"), "output_seen_by_model": actual_output,
                           "elapsed_seconds": event.get("elapsed_seconds")})
        elif event.get("kind") == "model":
            events.append({"kind": "model", "message": event.get("message"), "usage": event.get("usage"),
                           "server_timings": event.get("server_timings"), "elapsed_seconds": event.get("elapsed_seconds")})
        else:
            events.append(event)
    card = {"evidence_kind": "unscored_review_view", "question_id": trial["question_id"],
            "repeat": trial["repeat"], "freeze_sha256": freeze_hash, "trial_sha256": e.sha_file(path),
            "question": trace["question"], "status": trace.get("status"), "final": trace.get("final"),
            "error": trace.get("error"), "events": events,
            "source_trial": "agent-v1/" + path.name,
            "limitations": "No automatic grade or semantic judgment included. Full original trial remains authoritative."}
    e.write_new(output / path.name, card)
    observations.append({"question_id": trial["question_id"], "repeat": trial["repeat"],
                         "status": trace.get("status"), "final_status": (trace.get("final") or {}).get("status"),
                         "error": trace.get("error"), "elapsed_seconds": trace.get("elapsed_seconds"),
                         "model_response_count": sum(event.get("kind") == "model" for event in trace.get("events", [])),
                         "calls": trace.get("calls"), "trial_sha256": card["trial_sha256"]})
e.write_new(output / "observations.json", {"freeze_sha256": freeze_hash, "trials": observations,
                                         "judgments": "not_performed", "source_trials_unchanged": True})
print(json.dumps({"review_cards": len(observations), "output": str(output)}))
