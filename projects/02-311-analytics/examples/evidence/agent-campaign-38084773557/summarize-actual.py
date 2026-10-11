"""Derive diagnostics from original completed trials; no inference or grading changes."""
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def frequencies(values):
    return dict(sorted(Counter(values).items()))

def summarize(trials):
    elapsed = [t["trace"]["elapsed_seconds"] for t in trials]
    events = [e for t in trials for e in t["trace"]["events"]]
    tools = [e for e in events if e.get("kind") == "tool" and e.get("initiated_by") != "adapter"]
    finals = [t for t in trials if t["trace"].get("final") is not None]
    return {
        "trials": len(trials),
        "automatic_passes": sum(t["grade"]["automatic_pass"] for t in trials),
        "automatic_pass_trials": [[t["question_id"],t["repeat"]] for t in trials if t["grade"]["automatic_pass"]],
        "driver_status": frequencies(t["trace"].get("status", "missing") for t in trials),
        "driver_errors": frequencies(json.dumps(t["trace"]["error"],sort_keys=True) for t in trials if t["trace"].get("error")),
        "terminal_response_count": len(finals),
        "terminal_status": frequencies(t["trace"]["final"].get("status", "missing") for t in finals),
        "without_terminal_response": len(trials)-len(finals),
        "automatic_hard_failures": frequencies(code for t in trials for code in t["grade"].get("hard_failures", [])),
        "failed_automatic_checks": frequencies(key for t in trials for key,value in t["grade"].get("checks", {}).items() if value is False),
        "model_response_events": sum(e.get("kind") == "model" for e in events),
        "model_selected_tool_events": frequencies(e["name"] for e in tools),
        "trial_elapsed_seconds": {"samples":len(elapsed), "minimum":min(elapsed), "median":statistics.median(elapsed), "maximum":max(elapsed), "sum":sum(elapsed)},
        "observed_model_server_memory": {
            "samples": sum(t.get("runtime_memory",{}).get("available") is True for t in trials),
            "maximum_sampled_rss_bytes": max(t.get("runtime_memory",{}).get("rss_bytes",0) for t in trials),
            "maximum_observed_process_lifetime_hwm_bytes": max(t.get("runtime_memory",{}).get("process_lifetime_hwm_bytes",0) for t in trials),
        },
    }

all_trials, replicas, files = [], [], {}
for repeat in (1,2,3):
    directory=HERE/f"replica-{repeat}"
    paths=sorted((directory/"agent-v1").glob("Q*-r*.json"))
    assert len(paths)==40 and {p.name for p in paths} == {f"Q{n:02d}-r{repeat}.json" for n in range(1,41)}
    trials=[load(p) for p in paths]
    proof=load(directory/f"runtime/replica-execution-r{repeat}.json")
    assert proof["execution_complete"] is True
    host=load(directory/"runtime/host.json")
    cpu_lines=(directory/"runtime/cpu.txt").read_text(encoding="utf-8").splitlines()
    replicas.append({"repetition":repeat,"host":{k:host[k] for k in ("python","platform","logical_cpus","total_memory_bytes")},
                     "cpu_model":next((line.strip() for line in cpu_lines if "Model name:" in line),None),
                     "freeze_sha256":sha(directory/"real-v1/agent-freeze.json"), **summarize(trials)})
    all_trials.extend(trials)
    files.update({p.relative_to(HERE).as_posix():sha(p) for p in paths})
cases=load(HERE/"replica-1/real-v1/agent-freeze.json")["cases"]
category={case["id"]:case["category"] for case in cases}
automatic=load(HERE/"automatic/automatic-review.json")
report={"schema_version":1,"evidence_kind":"actual_agent_trial_diagnostics", "derived_at":datetime.now(timezone.utc).isoformat(),
        "workflow_run_id":38084773557, "source_commit":"d3be88e72cf5e7920f2861eaa7c21f6dd26abdb3",
        "method_sha256":sha(Path(__file__)),"automatic_report_sha256":sha(HERE/"automatic/automatic-review.json"),
        "new_trials_executed":False,"original_grades_modified":False,"semantic_judgments": "pending_separate_review",
        "all_trials":summarize(all_trials),"replicas":replicas,
        "by_category":{name:summarize([t for t in all_trials if category[t["question_id"]]==name]) for name in sorted(set(category.values()))},
        "warmup_by_replica":[{"repetition":r["repetition"],"seconds":r["prefix_warmup"]["startup_seconds_total"]} for r in automatic["replicas"]],
        "trial_sha256":files,
        "limitations":["Trial elapsed includes model, tools and adapter work; it is not model-generation-only latency. Startup/download/build are excluded.",
          "Timeouts and failed answers remain timing samples. These are bounded unsuccessful/successful attempts, not successful-answer latency or an SLA.",
          "Three seeds on three hosts confound seed and machine effects; repeats are not independent questions or datasets.",
          "RSS is sampled; Linux process HWM spans the owned model process lifetime, not an individual trial or total host memory.",
          "The final semantic review can fail an automatic pass; diagnostic classifications do not change frozen grading."]}
assert report["all_trials"]["automatic_passes"]==automatic["automatic_passes"]
assert report["all_trials"]["trial_elapsed_seconds"]["median"]==automatic["model_latency_seconds"]["median"]
destination=HERE/"actual-diagnostics.json"
with destination.open("x",encoding="utf-8",newline="\n") as stream:
    json.dump(report,stream,indent=2,ensure_ascii=False)
    stream.write("\n")
print(json.dumps({"path":destination.name,"sha256":sha(destination),"overall":report["all_trials"]},indent=2))
