"""Conservative, reproducible communication baseline; raw scores are not probabilities.

Only entities and messages enter inference. Labels and source/human assertions are
deliberately outside this module; the service combines those in its projection.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import math
import random
import re
from typing import Any

import networkx as nx


MODEL_ID = "communication-self-report-v1"
MAX_RECIPIENTS = 20
MAX_CANDIDATES = 8


def _id(prefix: str, *parts: Any) -> str:
    value = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def _day(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _normal(value: str) -> str:
    return " ".join(value.casefold().split())


def _aliases(people: dict[str, dict]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = defaultdict(set)
    for entity_id, entity in people.items():
        for alias in [entity.get("name", ""), entity.get("email", ""), *entity.get("aliases", [])]:
            if isinstance(alias, str) and alias.strip():
                lookup[_normal(alias)].add(entity_id)
    return lookup


def _leading_person(text: str, aliases: dict[str, set[str]]) -> tuple[str, int] | None:
    """Resolve only a unique explicit name/alias, never a fuzzy first-name guess."""
    longest = None
    for end in range(1, min(len(text), 160) + 1):
        if end < len(text) and text[end] not in " \t.,;:!?\r\n":
            continue
        found = aliases.get(_normal(text[:end]))
        if found and len(found) == 1:
            longest = (next(iter(found)), end)
    if longest is None:
        return None
    remainder = text[longest[1]:].strip()
    # A longer unresolved name ("Alex Smith" when only "Alex" is known) must
    # never be silently truncated. Clauses after a complete sentence are fine.
    if remainder and remainder[0] not in ".;!?":
        return None
    return longest


def _original_lines(body: str):
    offset = 0
    quoted_block = False
    for line in body.splitlines(keepends=True):
        stripped = line.strip()
        if re.match(r"(?:-+\s*(?:Original|Forwarded) Message|On .+ wrote:|Begin forwarded message:)", stripped, re.I):
            quoted_block = True
        if re.match(r"^(?:From|Sent):\s", stripped, re.I):
            quoted_block = True
        if not quoted_block and not stripped.startswith((">", "|")):
            yield offset, line
        offset += len(line)


def _unquoted_statement(line: str, start: int) -> bool:
    prefix = line[:start]
    # Quotation and attribution are intentionally conservative: false negatives
    # are preferable to treating someone else's first-person words as the sender.
    if any(mark in line for mark in ('"', "“", "”", "‘", "’")):
        return False
    if "'" in prefix or re.search(r"\b(?:said|wrote|says|quote|example|suppose|imagine|if|whether|wish)\b", prefix, re.I):
        return False
    sentence_prefix = re.split(r"[.!?]", prefix)[-1].strip()
    return not sentence_prefix or sentence_prefix.casefold() in ("for the record,", "for your records,", "to clarify,")


_REPORT = re.compile(r"\bI\s+(?P<neg>do not\s+|don't\s+|no longer\s+)?report\s+(?:directly\s+)?to\s+", re.I)
_MANAGER = re.compile(r"(?P<name>[^\n.!?]{1,160}?)\s+is\s+my\s+(?:line\s+|direct\s+)?manager\b", re.I)
_APPROVAL = re.compile(r"\b(?:please\s+(?:review\s+and\s+)?approve|(?:I|we)\s+need\s+your\s+approval|could\s+you\s+approve)\b", re.I)


def _text_signals(message: dict, aliases: dict[str, set[str]]) -> list[dict]:
    body = message.get("body") or ""
    if not isinstance(body, str):
        return []
    signals = []
    for offset, line in _original_lines(body):
        for match in _REPORT.finditer(line):
            if not _unquoted_statement(line, match.start()):
                continue
            target = _leading_person(line[match.end():], aliases)
            if target:
                signals.append({"kind": "negative_report" if match.group("neg") else "direct_report", "target": target[0], "start": offset + match.start(), "end": offset + match.end() + target[1]})
        for match in _MANAGER.finditer(line):
            name = match.group("name").strip()
            targets = aliases.get(_normal(name), set())
            start = match.start() + len(match.group("name")) - len(match.group("name").lstrip())
            if len(targets) == 1 and _unquoted_statement(line, start):
                signals.append({"kind": "direct_report", "target": next(iter(targets)), "start": offset + start, "end": offset + match.end()})
        for match in _APPROVAL.finditer(line):
            if _unquoted_statement(line, match.start()):
                signals.append({"kind": "approval_request", "start": offset + match.start(), "end": offset + match.end()})
    return signals


def _assertion(corpus_id: str, subject: str, relation: str, target: str, score: float, evidence_ids: list[str], observation: str | None, reason: str) -> dict:
    return {
        "id": _id("model", MODEL_ID, corpus_id, subject, relation, target),
        "subject": subject, "relation": relation, "object": target,
        "origin": "model", "valid_from": observation, "valid_to": None,
        "temporal_basis": "observed_statement" if observation else "undated_evidence",
        "reporting_type": "primary", "raw_score": round(score, 6),
        "candidate_probability": None, "selected_probability": None,
        "calibration_status": "uncalibrated", "evidence_ids": sorted(set(evidence_ids)),
        "review_status": "unreviewed", "reason": reason,
        "selection_hint": False, "selection_reason": "not_selected",
    }


def _partition(graph: nx.Graph, seed: int) -> list[set[str]]:
    if not graph.number_of_edges():
        return []
    return sorted((set(group) for group in nx.community.louvain_communities(graph, weight="weight", seed=seed)), key=lambda group: tuple(sorted(group)))


def _communities(undirected: Counter, corpus_id: str, window: dict) -> list[dict]:
    graph = nx.Graph()
    ordered_edges = sorted(undirected.items())
    for (a, b), weight in ordered_edges:
        graph.add_edge(a, b, weight=weight)
    partitions = _partition(graph, 17)
    if not partitions:
        return []
    samples = []
    for sample in range(3):
        rng = random.Random(101 + sample)
        sampled = nx.Graph()
        sampled.add_nodes_from(sorted(graph.nodes))
        sampled.add_edges_from((a, b, {"weight": weight}) for (a, b), weight in ordered_edges if rng.random() < 0.8)
        # Include singleton components when resampling removes all their edges.
        groups = _partition(sampled, 17) if sampled.number_of_edges() else [{node} for node in sampled.nodes]
        samples.append(({node: idx for idx, group in enumerate(groups) for node in group}, [len(group) for group in groups]))
    results = []
    for members in partitions:
        if len(members) < 2:
            continue
        scores = []
        for membership, sizes in samples:
            overlaps = Counter(membership[node] for node in members if node in membership)
            scores.append(max((count / (len(members) + sizes[idx] - count) for idx, count in overlaps.items()), default=0))
        results.append({
            "id": _id("group", corpus_id, sorted(members)),
            "name": f"Communication group {len(results) + 1}", "kind": "inferred",
            "members": sorted(members), "method": "weighted_louvain",
            "parameters": {"resolution": 1, "seed": 17, "max_recipients": MAX_RECIPIENTS},
            "window": window, "formal_unit": False,
            "interpretation": "Observed communication community; not a verified team or reporting unit.",
            "stability": {"method": "edge_dropout", "repeats": 3, "keep_probability": 0.8, "mean_best_jaccard": round(sum(scores) / len(scores), 4), "interpretation": "Structural sensitivity only; not membership confidence."},
        })
    return results


def infer(dataset: dict, *, threshold: float = 0.55, margin: float = 0.08, as_of: str | None = None) -> dict:
    """Rank sparse direct-manager candidates and expose descriptive communication.

    Explicit self-report text is a claim, not ground truth. Approval language is
    represented as relative authority and never adds a direct-manager score.
    No scorer fit or calibration occurs; labels cannot influence any output.
    """
    if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
        raise ValueError("threshold and margin must be between 0 and 1")
    if as_of is not None and (_day(as_of) != as_of):
        raise ValueError("as_of must be an ISO date (YYYY-MM-DD)")
    corpus_id = str(dataset.get("corpus", {}).get("id", "unknown"))
    people = {str(entity["id"]): entity for entity in dataset.get("entities", []) if entity.get("type", "person") == "person"}
    aliases = _aliases(people)
    metrics = {person: {"breadth": 0, "sent": 0, "received": 0, "cross_unit": 0, "cross_unit_eligible": 0} for person in people}
    contacts = defaultdict(set)
    outgoing: Counter = Counter()
    undirected: Counter = Counter()
    pair_messages: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    positive: dict[tuple[str, str], list[dict]] = defaultdict(list)
    negative: dict[tuple[str, str], list[dict]] = defaultdict(list)
    approval: dict[tuple[str, str], list[dict]] = defaultdict(list)
    evidence: dict[str, dict] = {}
    seen = set()
    observed_dates = []
    coverage = Counter()
    for index, message in enumerate(dataset.get("messages", [])):
        message_id = str(message.get("id", f"input-{index}"))
        if message_id in seen:
            coverage["duplicate_message_ids"] += 1
            continue
        seen.add(message_id)
        day = _day(message.get("timestamp"))
        if as_of and day and day > as_of:
            coverage["future_messages_excluded"] += 1
            continue
        sender = message.get("sender")
        if sender not in people:
            coverage["nonperson_or_unknown_sender_excluded"] += 1
            continue
        recipients = sorted({recipient for recipient in [*message.get("to", []), *message.get("cc", [])] if recipient in people and recipient != sender})
        all_recipients = set([*message.get("to", []), *message.get("cc", [])]) - {sender}
        if len(all_recipients) > MAX_RECIPIENTS:
            coverage["broadcast_messages_excluded"] += 1
            continue
        coverage["messages_in_window"] += 1
        if day:
            observed_dates.append(day)
        else:
            coverage["undated_messages"] += 1
        if message.get("body"):
            coverage["messages_with_body"] += 1
        if recipients:
            metrics[sender]["sent"] += 1
        for recipient in recipients:
            metrics[recipient]["received"] += 1
            contacts[sender].add(recipient)
            contacts[recipient].add(sender)
            outgoing[sender, recipient] += 1
            pair = tuple(sorted((sender, recipient)))
            undirected[pair] += 1
            pair_messages[pair][message_id] = {"id": message_id, "timestamp": message.get("timestamp"), "date": day, "source_ref": message.get("source_ref", f"message:{message_id}"), "sender": sender}
            if people[sender].get("unit_id") and people[recipient].get("unit_id"):
                for person in (sender, recipient):
                    metrics[person]["cross_unit_eligible"] += 1
                    if people[sender]["unit_id"] != people[recipient]["unit_id"]:
                        metrics[person]["cross_unit"] += 1
        for signal in _text_signals(message, aliases):
            if signal["kind"] == "approval_request":
                # Inspect the small message recipient list, not a copy of the
                # entire roster for every approval statement.
                direct_recipients = {recipient for recipient in message.get("to", []) if recipient in people and recipient != sender}
                if len(direct_recipients) != 1:
                    continue
                target = next(iter(direct_recipients))
            else:
                target = signal["target"]
                if target == sender:
                    continue
            text = message["body"][signal["start"]:signal["end"]]
            eid = _id("span", corpus_id, message_id, signal["start"], signal["end"], text)
            item = {"id": eid, "kind": "message_span", "source_ref": message.get("source_ref", f"message:{message_id}"), "text": text, "available": True, "message_ids": [message_id], "start": signal["start"], "end": signal["end"], "details": {"speaker": sender, "signal": signal["kind"], "observed_at": message.get("timestamp"), "date": day, "attribution": "unquoted sender text", "target": target}}
            evidence[eid] = item
            bucket = approval if signal["kind"] == "approval_request" else negative if signal["kind"] == "negative_report" else positive
            bucket[sender, target].append(item)
    for person in people:
        metrics[person]["breadth"] = len(contacts[person])
    window = {"as_of": as_of, "observed_from": min(observed_dates, default=None), "observed_to": max(observed_dates, default=None), "undated_messages_included": coverage["undated_messages"]}
    candidates: dict[str, set[str]] = defaultdict(set)
    for person, neighbors in contacts.items():
        candidates[person].update(sorted(neighbors, key=lambda other: (-(outgoing[person, other] + outgoing[other, person]), other))[:MAX_CANDIDATES])
    for person, target in positive.keys() | negative.keys():
        candidates[person].add(target)
    assertions = []
    by_person = defaultdict(list)
    for person in sorted(candidates):
        total_out = sum(outgoing[person, neighbor] for neighbor in contacts[person])
        for target in sorted(candidates[person]):
            fwd, rev = outgoing[person, target], outgoing[target, person]
            pair = tuple(sorted((person, target)))
            records = sorted(pair_messages[pair].values(), key=lambda item: item["id"])
            support, contradict = positive[person, target], negative[person, target]
            evidence_ids = [item["id"] for item in support + contradict]
            share = fwd / max(1, total_out)
            reciprocity = min(fwd, rev) / max(1, fwd, rev)
            behavior = min(0.52, 0.08 + 0.20 * share + 0.14 * reciprocity + 0.10 * min(1, math.log1p(fwd + rev) / math.log(11))) if records else 0
            if records:
                eid = _id("aggregate", corpus_id, person, target, as_of, records)
                evidence[eid] = {"id": eid, "kind": "communication_aggregate", "source_ref": f"corpus:{corpus_id}", "available": True, "message_ids": [item["id"] for item in records], "details": {"subject": person, "candidate": target, "sent_to_candidate": fwd, "received_from_candidate": rev, "total_outgoing_interactions": total_out, "outgoing_share": round(share, 6), "reciprocity": round(reciprocity, 6), "window": window, "max_recipients": MAX_RECIPIENTS, "query": "Unique messages with known person sender; union(to,cc), remove self; exclude messages with >20 distinct recipients. Count each sender-recipient pair once. Reciprocal pair IDs listed.", "scoring": "min(0.52, 0.08 + 0.20*outgoing_share + 0.14*reciprocity + 0.10*min(1, log1p(pair_count)/log(11)))", "source_refs": sorted({record["source_ref"] for record in records}), "interpretation": "Communication is not proof of supervision."}}
                evidence_ids.append(eid)
            unique_claims = {item["text"].casefold() for item in support}
            score = min(0.96, 0.88 + 0.02 * min(2, len(unique_claims) - 1) + 0.04 * min(1, (fwd + rev) / 4)) if support else behavior
            if contradict:
                score = min(score, 0.30)
            direct_dates = [item["details"]["date"] for item in support if item["details"]["date"]]
            record_dates = [record["date"] for record in records if record["date"]]
            observation = max(direct_dates, default=None) if support else max(record_dates, default=None)
            reason = "Explicit sender self-report claim; requires verification." if support else "Communication pattern only; supervision unverified."
            if contradict:
                reason += " Explicit negated reporting statement conflicts with this candidate."
            assertion = _assertion(corpus_id, person, "reports_to", target, score, evidence_ids, observation, reason)
            assertion["temporal_basis"] = "observed_statement" if support and observation else "communication_window" if observation else "undated_evidence"
            assertion["signals"] = {"direct_statement_count": len(unique_claims), "contradicting_statement_count": len(contradict), "communication_score": round(behavior, 6)}
            assertions.append(assertion)
            by_person[person].append(assertion)
    unresolved = {}
    for person in sorted(people):
        ranked = sorted(by_person[person], key=lambda item: (-item["raw_score"], item["object"]))
        reason = "empty_candidate_set"
        if ranked:
            first = ranked[0]
            gap = first["raw_score"] - (ranked[1]["raw_score"] if len(ranked) > 1 else 0)
            if first["signals"]["contradicting_statement_count"]:
                reason = "conflicting_evidence"
            elif first["raw_score"] < threshold:
                reason = "weak_evidence"
            elif gap + 1e-12 < margin:
                reason = "close_alternatives"
            elif as_of and not first["valid_from"]:
                reason = "unknown_dates"
            else:
                first["selection_hint"] = True
                first["selection_reason"] = "threshold_and_margin_met"
                continue
            first["selection_reason"] = reason
        unresolved[person] = reason
    for (requester, authority), items in sorted(approval.items()):
        dates = [item["details"]["date"] for item in items if item["details"]["date"]]
        assertion = _assertion(corpus_id, authority, "higher_authority_than", requester, 0.35, [item["id"] for item in items], max(dates, default=None), "Approval request suggests contextual authority; it does not establish direct reporting.")
        assertion["reporting_type"] = None
        assertion["selection_reason"] = "not_a_direct_reporting_relation"
        assertions.append(assertion)
    return {
        "assertions": sorted(assertions, key=lambda item: (item["subject"], item["relation"], -item["raw_score"], item["object"])),
        "evidence": sorted(evidence.values(), key=lambda item: item["id"]),
        "groups": _communities(undirected, corpus_id, window), "metrics": metrics,
        "unresolved": unresolved,
        "model": {"id": MODEL_ID, "name": "Conservative communication and self-report baseline", "calibration_status": "uncalibrated", "validation_scope": None, "probabilities_available": False, "threshold": threshold, "margin": margin, "max_candidates": MAX_CANDIDATES, "max_recipients": MAX_RECIPIENTS, "window": window, "coverage": dict(coverage), "metric_definitions": {"breadth": "Distinct observed person counterparties, to/cc deduplicated; excludes broadcasts and shared mailboxes.", "sent": "Distinct eligible messages sent with at least one known person recipient.", "received": "Distinct eligible messages addressed to this person in to or cc.", "cross_unit": "Incident sender-recipient interactions between people with different known unit_id values.", "cross_unit_eligible": "Incident sender-recipient interactions where both unit_id values are known."}, "limitations": ["Raw heuristic scores are not calibrated probabilities.", "Message dates are observation dates, not verified employment start dates.", "Explicit sender claims can be wrong; quotations are conservatively excluded.", "No trained model, real-data accuracy, or target calibration has been established.", "Communication groups and breadth do not establish teams, authority, or influence."]},
    }
