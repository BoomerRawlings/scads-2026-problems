"""Local, dependency-free adapters for auditable organizational records.

No display-name based identity merge occurs here. Explicit IDs and normalized
email addresses identify records; ambiguous directory aliases remain ambiguous.
Every source record has exactly one terminal import outcome.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import mailbox
import re
from datetime import date, datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

PARSER_VERSION = "local-adapters-1.0"
ENTITY_TYPES = {"person", "unit", "shared_mailbox"}
EVIDENCE_KINDS = {"message_span", "communication_aggregate", "source_assertion", "analyst_reference"}
OUTCOMES = ("accepted", "duplicate", "quarantined", "unsupported")


def _stable(prefix: str, value: Any) -> str:
    material = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return prefix + "_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _empty(corpus_id: str, filename: str) -> dict:
    return {"schema_version": 1, "corpus": {"id": corpus_id, "name": Path(filename).stem or "Imported organization", "synthetic": False},
            "entities": [], "messages": [], "assertions": [], "evidence": [], "labels": []}


def _report(filename: str) -> dict:
    return {"read": 0, **{key: 0 for key in OUTCOMES}, "issues": [], "parser_version": PARSER_VERSION,
            "source": Path(filename).name, "quality": {"missing_timestamp": 0, "missing_body": 0, "missing_recipients": 0, "ambiguous_aliases": 0}}


def _issue(report: dict, source_ref: str, code: str, reason: str, *, outcome: str | None = None) -> None:
    report["issues"].append({"source_ref": source_ref, "code": code, "reason": reason, "outcome": outcome or "warning"})
    if outcome:
        report["read"] += 1
        report[outcome] += 1


def _accept(report: dict) -> None:
    report["read"] += 1
    report["accepted"] += 1


def _address(value: str) -> str | None:
    value = value.strip().removeprefix("mailto:").strip("<>").strip()
    if re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+", value):
        return value.casefold()
    return None


def _addresses(value: str) -> list[tuple[str, str]]:
    # Semicolon-separated lists are common in exported spreadsheets.
    return [(name.strip(), address) for name, raw in getaddresses([value.replace(";", ",")])
            if (address := _address(raw))]


def _timestamp(value: Any) -> tuple[str | None, str | None]:
    if value is None or value == "":
        return None, "missing_timestamp"
    if not isinstance(value, str):
        return None, "invalid_timestamp"
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None, "invalid_timestamp"
    if parsed.tzinfo is None:
        return parsed.isoformat(), "timezone_unknown"
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), None


def _day(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Validity must be an ISO date or null.")
    return date.fromisoformat(value).isoformat()


def _finish(dataset: dict, report: dict, **extras: Any) -> dict:
    times = [m["timestamp"] for m in dataset["messages"] if m.get("timestamp")]
    report["coverage"] = {"entities": len(dataset["entities"]), "messages": len(dataset["messages"]),
                          "assertions": len(dataset["assertions"]), "timestamp_start": min(times) if times else None,
                          "timestamp_end": max(times) if times else None}
    assert report["read"] == sum(report[key] for key in OUTCOMES)
    return {"dataset": dataset, "report": report, **extras}


def _register_alias_issues(dataset: dict, report: dict) -> None:
    owners: dict[str, set[str]] = {}
    for entity in dataset["entities"]:
        for alias in [entity.get("email", ""), *entity.get("aliases", [])]:
            if isinstance(alias, str) and alias.strip():
                owners.setdefault(alias.strip().casefold(), set()).add(entity["id"])
    for alias, ids in sorted(owners.items()):
        if len(ids) > 1:
            report["quality"]["ambiguous_aliases"] += 1
            _issue(report, "entities", "ambiguous_alias", f"Alias {alias!r} belongs to {len(ids)} entities; identities remain separate.")


def _validate_json(value: Any, filename: str, corpus_id: str) -> dict:
    report = _report(filename)
    extras: dict[str, Any] = {}
    if isinstance(value, dict) and isinstance(value.get("dataset"), dict):
        extras["package"] = copy.deepcopy(value)
        value = value["dataset"]
    if not isinstance(value, dict):
        _issue(report, filename, "invalid_json_shape", "Expected a canonical JSON object.", outcome="quarantined")
        return _finish(_empty(corpus_id, filename), report)
    if value.get("schema_version", 1) != 1:
        _issue(report, filename, "unsupported_schema", "Only schema_version 1 is supported.", outcome="unsupported")
        return _finish(_empty(corpus_id, filename), report)
    dataset = copy.deepcopy(value)
    dataset["schema_version"] = 1
    corpus = dataset.get("corpus")
    if not isinstance(corpus, dict):
        corpus = _empty(corpus_id, filename)["corpus"]
    corpus.setdefault("id", corpus_id)
    corpus.setdefault("name", Path(filename).stem)
    corpus.setdefault("synthetic", False)
    dataset["corpus"] = corpus
    for key in ("entities", "messages", "assertions", "evidence", "labels"):
        dataset[key] = []
    seen: dict[str, dict[str, dict]] = {key: {} for key in ("entities", "messages", "assertions", "evidence", "labels")}

    def records(key: str):
        items = value.get(key, [])
        if not isinstance(items, list):
            _issue(report, key, "invalid_collection", f"{key} must be an array.", outcome="quarantined")
            return []
        return enumerate(items)

    def save(key: str, record: dict, ref: str) -> None:
        previous = seen[key].get(record["id"])
        if previous is not None:
            if previous == record:
                _issue(report, ref, "duplicate_id", "Identical record already imported.", outcome="duplicate")
            else:
                _issue(report, ref, "conflicting_id", "ID already identifies a different record.", outcome="quarantined")
            return
        seen[key][record["id"]] = record
        dataset[key].append(record)
        _accept(report)

    def base(raw: Any) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("Record must be an object.")
        if not isinstance(raw.get("id"), str) or not raw["id"].strip():
            raise ValueError("Record requires a nonempty string ID.")
        return copy.deepcopy(raw)

    for index, raw in records("entities"):
        ref = f"{Path(filename).name}#entities/{index}"
        try:
            item = base(raw)
            if not isinstance(item.get("name"), str) or not item["name"].strip():
                raise ValueError("Entity requires a name.")
            item.setdefault("type", "person")
            if item["type"] not in ENTITY_TYPES:
                raise ValueError("Entity type must be person, unit, or shared_mailbox.")
            item.setdefault("aliases", [])
            if not isinstance(item["aliases"], list) or any(not isinstance(a, str) for a in item["aliases"]):
                raise ValueError("Entity aliases must be strings.")
            if item.get("unit_id") is not None and not isinstance(item["unit_id"], str):
                raise ValueError("Entity unit_id must be a string or null.")
            if item.get("email"):
                item["source_email"] = item.get("source_email", item["email"])
                normalized = _address(item["email"]) if isinstance(item["email"], str) else None
                if not normalized:
                    raise ValueError("Invalid entity email address.")
                item["email"] = normalized
            save("entities", item, ref)
        except (ValueError, TypeError) as exc:
            _issue(report, ref, "invalid_entity", str(exc), outcome="quarantined")
    ids = set(seen["entities"])
    for entity in dataset["entities"]:
        if entity.get("unit_id") and (entity["unit_id"] not in ids or seen["entities"][entity["unit_id"]]["type"] != "unit"):
            _issue(report, entity["id"], "unknown_unit", "Unknown/non-unit unit_id retained for review.")
    for index, raw in records("messages"):
        ref = f"{Path(filename).name}#messages/{index}"
        try:
            item = base(raw)
            if item.get("sender") not in ids:
                raise ValueError("Message sender is missing or does not reference an imported entity.")
            for field in ("to", "cc"):
                item.setdefault(field, [])
                if not isinstance(item[field], list) or any(not isinstance(p, str) or p not in ids for p in item[field]):
                    raise ValueError(f"Message {field} must reference imported entities.")
                item[field] = list(dict.fromkeys(item[field]))
            for field in ("body", "subject"):
                item.setdefault(field, "")
                if not isinstance(item[field], str):
                    raise ValueError(f"Message {field} must be a string.")
            timestamp, flag = _timestamp(item.get("timestamp"))
            if flag:
                item["source_timestamp"] = item.get("source_timestamp", item.get("timestamp"))
                item["timestamp_quality"] = flag
                _issue(report, ref, flag, "Timestamp missing/invalid or timezone unknown; no timezone was invented.")
            item["timestamp"] = timestamp
            item.setdefault("source_ref", ref)
            _quality(item, report)
            save("messages", item, ref)
        except (ValueError, TypeError) as exc:
            _issue(report, ref, "invalid_message", str(exc), outcome="quarantined")
    for index, raw in records("evidence"):
        ref = f"{Path(filename).name}#evidence/{index}"
        try:
            item = base(raw)
            if item.get("kind") not in EVIDENCE_KINDS:
                raise ValueError("Unknown evidence kind.")
            item.setdefault("source_ref", ref)
            item.setdefault("available", True)
            if not isinstance(item["available"], bool):
                raise ValueError("Evidence availability must be boolean.")
            message_ids = item.get("message_ids", [])
            if not isinstance(message_ids, list) or any(not isinstance(m, str) for m in message_ids):
                raise ValueError("Evidence message_ids must be an array of strings.")
            if item["available"] and any(m not in seen["messages"] for m in message_ids):
                raise ValueError("Available evidence references missing messages.")
            if item["kind"] == "message_span" and item["available"]:
                if len(message_ids) != 1:
                    raise ValueError("Available message span requires one message ID.")
                body = seen["messages"][message_ids[0]]["body"]
                start, end = item.get("start"), item.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(body):
                    raise ValueError("Evidence span falls outside the stored message body.")
                if item.get("text", body[start:end]) != body[start:end]:
                    raise ValueError("Evidence text does not match its message offsets.")
                item["text"] = body[start:end]
            save("evidence", item, ref)
        except (ValueError, TypeError) as exc:
            _issue(report, ref, "invalid_evidence", str(exc), outcome="quarantined")
    for index, raw in records("assertions"):
        ref = f"{Path(filename).name}#assertions/{index}"
        try:
            item = base(raw)
            if item.get("subject") not in ids or item.get("object") not in ids:
                raise ValueError("Assertion endpoints must reference imported entities.")
            if not isinstance(item.get("relation"), str) or not item["relation"]:
                raise ValueError("Assertion requires a relation.")
            if item["relation"] == "reports_to" and item["subject"] == item["object"]:
                raise ValueError("Self-reporting assertion is invalid.")
            item.setdefault("origin", "source")
            if item["origin"] not in {"source", "model", "analyst"}:
                raise ValueError("Invalid assertion origin.")
            item["valid_from"], item["valid_to"] = _day(item.get("valid_from")), _day(item.get("valid_to"))
            if item["valid_from"] and item["valid_to"] and item["valid_from"] >= item["valid_to"]:
                raise ValueError("Validity interval must have positive duration.")
            item.setdefault("reporting_type", "primary" if item["relation"] == "reports_to" else None)
            allowed_reporting_types = {"primary", "matrix"} if item["relation"] == "reports_to" else {None, "primary", "matrix"}
            if item["reporting_type"] not in allowed_reporting_types:
                raise ValueError("Invalid reporting type.")
            item.setdefault("evidence_ids", [])
            if not isinstance(item["evidence_ids"], list) or any(e not in seen["evidence"] for e in item["evidence_ids"]):
                raise ValueError("Assertion references unknown evidence.")
            item.setdefault("review_status", "unreviewed")
            if item["review_status"] not in {"unreviewed", "accepted", "rejected"}:
                raise ValueError("Invalid review status.")
            item.setdefault("calibration_status", "not_applicable" if item["origin"] != "model" else "uncalibrated")
            for field in ("raw_score", "candidate_probability", "selected_probability"):
                item.setdefault(field, None)
                if item[field] is not None and (isinstance(item[field], bool) or not isinstance(item[field], (int, float)) or not 0 <= item[field] <= 1):
                    raise ValueError(f"{field} must be null or a finite number in [0, 1].")
            save("assertions", item, ref)
        except (ValueError, TypeError) as exc:
            _issue(report, ref, "invalid_assertion", str(exc), outcome="quarantined")
    for index, raw in records("labels"):
        ref = f"{Path(filename).name}#labels/{index}"
        if not isinstance(raw, dict):
            _issue(report, ref, "invalid_label", "Label must be an object.", outcome="quarantined")
            continue
        item = copy.deepcopy(raw)
        item.setdefault("id", _stable("label", item))
        if not isinstance(item["id"], str):
            _issue(report, ref, "invalid_label", "Label ID must be a string.", outcome="quarantined")
            continue
        save("labels", item, ref)
    _register_alias_issues(dataset, report)
    return _finish(dataset, report, **extras)


def _quality(message: dict, report: dict) -> None:
    for condition, field in ((not message.get("timestamp"), "missing_timestamp"),
                             (not message.get("body", "").strip(), "missing_body"),
                             (not message.get("to") and not message.get("cc"), "missing_recipients")):
        if condition:
            report["quality"][field] += 1


class _Importer:
    def __init__(self, filename: str, corpus_id: str):
        self.filename = Path(filename).name
        self.dataset = _empty(corpus_id, filename)
        self.report = _report(filename)
        self.people: dict[str, dict] = {}
        self.messages: dict[str, dict] = {}

    def person(self, name: str, address: str) -> str:
        if address not in self.people:
            entity = {"id": _stable("person", address), "name": name or address.split("@")[0],
                      "type": "person", "email": address, "aliases": [], "identity_basis": "email_address"}
            self.people[address] = entity
            self.dataset["entities"].append(entity)
        elif name and self.people[address]["name"] == address.split("@")[0]:
            self.people[address]["name"] = name
        return self.people[address]["id"]

    def message(self, raw: dict, ref: str) -> None:
        sender = _addresses(str(raw.get("sender") or ""))
        if len(sender) != 1:
            _issue(self.report, ref, "missing_or_ambiguous_sender", "One valid sender email address is required.", outcome="quarantined")
            return
        timestamp, flag = _timestamp(raw.get("timestamp"))
        to_pairs, cc_pairs = _addresses(str(raw.get("to") or "")), _addresses(str(raw.get("cc") or ""))
        body, subject = raw.get("body") or "", raw.get("subject") or ""
        source_id = str(raw.get("id") or "").strip()
        payload = {"sender": sender[0][1], "to": sorted(set(a for _, a in to_pairs)), "cc": sorted(set(a for _, a in cc_pairs)),
                   "timestamp": timestamp, "subject": subject, "body": body}
        key = _stable("message", ["source-id", source_id]) if source_id else _stable("message", payload)
        previous = self.messages.get(key)
        if previous:
            if previous["_fingerprint"] == _stable("content", payload):
                if ref not in previous["source_refs"]:
                    previous["source_refs"].append(ref)
                _issue(self.report, ref, "duplicate_message", "Duplicate message; source location retained.", outcome="duplicate")
            else:
                _issue(self.report, ref, "conflicting_message_id", "Same source message ID has different content.", outcome="quarantined")
            return
        item = {"id": key, "sender": self.person(*sender[0]),
                "to": list(dict.fromkeys(self.person(*p) for p in to_pairs)), "cc": list(dict.fromkeys(self.person(*p) for p in cc_pairs)),
                "timestamp": timestamp, "subject": subject, "body": body, "source_ref": ref, "source_refs": [ref],
                "source_message_id": source_id or None, "source_timestamp": raw.get("timestamp"),
                "source_sender": raw.get("sender"), "source_to": raw.get("to"), "source_cc": raw.get("cc"),
                "_fingerprint": _stable("content", payload)}
        if raw.get("in_reply_to"):
            item["in_reply_to"] = raw["in_reply_to"]
        if raw.get("references"):
            item["references"] = raw["references"]
        if flag:
            item["timestamp_quality"] = flag
            _issue(self.report, ref, flag, "Timestamp missing/invalid or timezone unknown; no timezone was invented.")
        if raw.get("body_format"):
            item["body_format"] = raw["body_format"]
        _quality(item, self.report)
        self.messages[key] = item
        self.dataset["messages"].append(item)
        _accept(self.report)

    def finish(self) -> dict:
        for message in self.dataset["messages"]:
            message.pop("_fingerprint", None)
        return _finish(self.dataset, self.report)


def _header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _get(row: dict, *names: str) -> str:
    for name in names:
        value = row.get(_header(name))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _source_assertion(subject: str, relation: str, object_id: str, evidence_id: str, *, valid_from=None, valid_to=None, reporting_type="primary") -> dict:
    return {"id": _stable("source", [subject, relation, object_id, evidence_id, valid_from, valid_to]),
            "subject": subject, "relation": relation, "object": object_id, "origin": "source", "valid_from": valid_from,
            "valid_to": valid_to, "reporting_type": reporting_type, "raw_score": None,
            "candidate_probability": None, "selected_probability": None, "calibration_status": "not_applicable",
            "evidence_ids": [evidence_id], "review_status": "unreviewed"}


def _csv(data: bytes, filename: str, corpus_id: str) -> dict:
    importer = _Importer(filename, corpus_id)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        _issue(importer.report, filename, "invalid_encoding", "CSV must use UTF-8 encoding.", outcome="quarantined")
        return importer.finish()
    try:
        delimiter = "\t" if Path(filename).suffix.lower() == ".tsv" else ","
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = [_header(h) for h in (reader.fieldnames or [])]
        if len(headers) != len(set(headers)):
            raise ValueError("Headers contain ambiguous duplicate columns after normalization.")
        is_messages = bool(set(headers) & {"sender", "from", "senderemail", "fromemail", "fromaddress"})
        is_roster = bool(set(headers) & {"name", "fullname", "displayname", "employeename", "email", "emailaddress", "employeeid", "personid", "entityid"})
        if not is_messages and not is_roster:
            _issue(importer.report, filename, "unknown_csv_mapping", "Expected sender/from or roster name/email columns.", outcome="unsupported")
            return importer.finish()
        rows = []
        for line, source_row in enumerate(reader, start=2):
            ref = f"{Path(filename).name}#row={line}"
            if None in source_row or any(v is None for v in source_row.values()):
                _issue(importer.report, ref, "malformed_csv_row", "Column count differs from header.", outcome="quarantined")
                continue
            row = {_header(k): v for k, v in source_row.items()}
            if is_messages:
                importer.message({"id": _get(row, "message_id", "id", "email_id"),
                                  "sender": _get(row, "sender", "from", "sender_email", "from_email", "from_address"),
                                  "to": _get(row, "to", "recipients", "recipient", "to_email", "to_address"),
                                  "cc": _get(row, "cc", "cc_recipients"),
                                  "timestamp": _get(row, "timestamp", "date", "sent_at", "sent_date", "datetime"),
                                  "subject": _get(row, "subject", "title"), "body": _get(row, "body", "content", "text", "message"),
                                  "in_reply_to": _get(row, "in_reply_to"), "references": _get(row, "references")}, ref)
            else:
                rows.append((row, ref))
        if not is_messages:
            _roster(rows, importer)
    except (csv.Error, ValueError) as exc:
        _issue(importer.report, filename, "malformed_csv", str(exc), outcome="quarantined")
    return importer.finish()


def _roster(rows: list, importer: _Importer) -> None:
    entities: dict[str, dict] = {}
    source_rows: dict[str, dict] = {}
    lookup: dict[str, set[str]] = {}
    pending: list[tuple[dict, str, dict, str | None, str | None]] = []
    units: dict[str, dict] = {}
    for row, ref in rows:
        try:
            raw_email = _get(row, "email", "email_address", "primary_email")
            email = _address(raw_email) if raw_email else None
            if raw_email and not email:
                raise ValueError("Invalid roster email address.")
            name = _get(row, "name", "full_name", "display_name", "employee_name") or email
            if not name:
                raise ValueError("Roster row requires a name or email.")
            explicit_id = _get(row, "id", "employee_id", "person_id", "entity_id")
            entity_id = explicit_id or (_stable("person", email) if email else _stable("person", [ref, name]))
            kind = _get(row, "type", "entity_type") or "person"
            if kind not in ENTITY_TYPES:
                raise ValueError("Unknown entity type.")
            valid_from, valid_to = _day(_get(row, "valid_from", "start_date")), _day(_get(row, "valid_to", "end_date"))
            if valid_from and valid_to and valid_from >= valid_to:
                raise ValueError("Validity end must be after start.")
            aliases = [a.strip() for a in re.split(r"[;|]", _get(row, "aliases", "alternate_emails")) if a.strip()]
            entity = {"id": entity_id, "name": name, "type": kind, "aliases": aliases,
                      "identity_basis": "explicit_id" if explicit_id else "email_address" if email else "source_row",
                      "source_ref": ref}
            if email:
                entity["email"], entity["source_email"] = email, raw_email
            if role := _get(row, "role", "title", "job_title"):
                entity["role"] = role
            unit_name = _get(row, "unit", "team", "department", "unit_name")
            unit_id = _get(row, "unit_id", "team_id", "department_id") or (_stable("unit", unit_name) if unit_name else "")
            if unit_id:
                if unit_id == entity_id:
                    raise ValueError("Entity ID conflicts with its organizational unit ID.")
                entity["unit_id"] = unit_id
            previous = entities.get(entity_id)
            if previous:
                identical = source_rows[entity_id] == row
                _issue(importer.report, ref, "duplicate_entity" if identical else "conflicting_entity_id",
                       "Repeated roster identity." if identical else "Same ID has incompatible roster records.",
                       outcome="duplicate" if identical else "quarantined")
                continue
            entities[entity_id] = entity
            source_rows[entity_id] = row
            if unit_id:
                units.setdefault(unit_id, {"id": unit_id, "name": unit_name or unit_id, "type": "unit", "aliases": [], "source_ref": ref})
            for key in [entity_id, email, *aliases]:
                if key:
                    lookup.setdefault(key.casefold(), set()).add(entity_id)
            pending.append((row, ref, entity, valid_from, valid_to))
            _accept(importer.report)
        except (ValueError, TypeError) as exc:
            _issue(importer.report, ref, "invalid_roster_row", str(exc), outcome="quarantined")
    importer.dataset["entities"] = list(entities.values())
    for unit_id, unit in units.items():
        if unit_id not in entities:
            importer.dataset["entities"].append(unit)
        elif entities[unit_id]["type"] != "unit":
            _issue(importer.report, unit_id, "unit_id_collision", "Unit ID identifies a non-unit entity; memberships omitted.")
    for row, ref, entity, valid_from, valid_to in pending:
        manager = _get(row, "manager_id", "supervisor_id", "reports_to_id", "manager_email", "reports_to_email", "manager", "manager_name", "reports_to")
        evidence = {"id": _stable("evidence", [ref, row]), "kind": "source_assertion", "source_ref": ref,
                    "available": True, "text": json.dumps(row, ensure_ascii=False, sort_keys=True),
                    "details": {"adapter": "roster_csv", "authored_source": True, "valid_from": valid_from, "valid_to": valid_to}}
        importer.dataset["evidence"].append(evidence)
        unit_id = entity.get("unit_id")
        if unit_id and (unit_id not in entities or entities[unit_id]["type"] == "unit"):
            importer.dataset["assertions"].append(_source_assertion(entity["id"], "member_of", unit_id, evidence["id"], valid_from=valid_from, valid_to=valid_to))
        if not manager:
            continue
        candidates = lookup.get(manager.casefold(), set())
        if not candidates:
            # Exact names are useful references but never grounds for merging.
            candidates = {e["id"] for e in entities.values() if e["name"].casefold() == manager.casefold()}
        if len(candidates) != 1:
            _issue(importer.report, ref, "ambiguous_manager" if candidates else "unknown_manager",
                   "Manager reference is ambiguous or absent; no reporting assertion created.")
            continue
        manager_id = next(iter(candidates))
        if manager_id == entity["id"]:
            _issue(importer.report, ref, "self_reporting", "Self-reporting source row retained as evidence; invalid edge omitted.")
            continue
        reporting_type = _get(row, "reporting_type") or "primary"
        if reporting_type not in {"primary", "matrix"}:
            _issue(importer.report, ref, "invalid_reporting_type", "Invalid reporting type; edge omitted.")
            continue
        importer.dataset["assertions"].append(_source_assertion(entity["id"], "reports_to", manager_id, evidence["id"], valid_from=valid_from, valid_to=valid_to, reporting_type=reporting_type))
    _register_alias_issues(importer.dataset, importer.report)


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"br", "p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        elif tag in {"p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _email(data: bytes, importer: _Importer, ref: str) -> None:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
        if message.defects:
            _issue(importer.report, ref, "email_parser_defect", ", ".join(type(d).__name__ for d in message.defects))
        if len(message.get_all("From", [])) != 1:
            _issue(importer.report, ref, "missing_or_ambiguous_sender", "Exactly one From header is required.", outcome="quarantined")
            return
        plain, html = [], []

        def body_parts(part):
            # A forwarded email attachment is another speaker's message, not the
            # current sender's body. Do not quietly concatenate it as authored text.
            if part.get_content_disposition() == "attachment" or part.get_content_type() == "message/rfc822":
                return
            if part.is_multipart():
                for child in part.iter_parts():
                    yield from body_parts(child)
            else:
                yield part

        for part in body_parts(message):
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            try:
                text = part.get_content()
            except (LookupError, UnicodeError):
                text = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
                _issue(importer.report, ref, "replacement_decoding", "Unrecognized text encoding decoded with replacement characters.")
            (plain if content_type == "text/plain" else html).append(text)
        body, body_format = "\n".join(plain), "text/plain"
        if not plain and html:
            parser = _PlainHTML()
            parser.feed("\n".join(html))
            body, body_format = unescape("".join(parser.parts)), "html_to_text"
        importer.message({"id": str(message.get("Message-ID", "")), "sender": str(message.get("From", "")),
                          "to": str(message.get("To", "")), "cc": str(message.get("Cc", "")),
                          "timestamp": str(message.get("Date", "")), "subject": str(message.get("Subject", "")),
                          "body": body, "body_format": body_format, "in_reply_to": str(message.get("In-Reply-To", "")),
                          "references": str(message.get("References", ""))}, ref)
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        _issue(importer.report, ref, "malformed_email", str(exc), outcome="quarantined")


def parse_bytes(data: bytes, filename: str, corpus_id: str = "imported") -> dict:
    """Parse one local source. Errors are accounted for in a quarantine report."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        try:
            value = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            report = _report(filename)
            _issue(report, Path(filename).name, "malformed_json", str(exc), outcome="quarantined")
            return _finish(_empty(corpus_id, filename), report)
        return _validate_json(value, filename, corpus_id)
    if suffix in {".csv", ".tsv"}:
        return _csv(data, filename, corpus_id)
    importer = _Importer(filename, corpus_id)
    if suffix == ".eml":
        _email(data, importer, f"{Path(filename).name}#message=1")
    elif suffix in {".mbox", ".mbx"} or (not suffix and data.startswith(b"From ")):
        separators = list(re.finditer(rb"(?m)^From [^\r\n]*\r?\n", data))
        if not separators or separators[0].start() != 0:
            _issue(importer.report, filename, "malformed_mbox", "Expected mbox envelope separators.", outcome="quarantined")
        else:
            for index, separator in enumerate(separators):
                end = separators[index + 1].start() if index + 1 < len(separators) else len(data)
                chunk = re.sub(rb"(?m)^>From ", b"From ", data[separator.end():end])
                _email(chunk, importer, f"{Path(filename).name}#message={index + 1}")
    else:
        _issue(importer.report, Path(filename).name, "unsupported_format", "Supported: canonical JSON, CSV/TSV, EML, mbox, and Maildir paths.", outcome="unsupported")
    return importer.finish()


def parse_path(path: str | Path, corpus_id: str = "imported") -> dict:
    """Read a source or Maildir without modifying it."""
    source = Path(path)
    if source.is_file():
        return parse_bytes(source.read_bytes(), source.name, corpus_id)
    importer = _Importer(source.name, corpus_id)
    if source.is_dir() and (source / "cur").is_dir() and (source / "new").is_dir():
        box = mailbox.Maildir(str(source), create=False)
        try:
            for key in sorted(box.keys()):
                try:
                    _email(box.get_bytes(key), importer, f"{source.name}#maildir={key}")
                except (KeyError, OSError) as exc:
                    _issue(importer.report, f"{source.name}#maildir={key}", "unreadable_message", str(exc), outcome="quarantined")
        finally:
            box.close()
    else:
        _issue(importer.report, source.name, "unsupported_path", "Expected a readable file or Maildir containing cur/ and new/.", outcome="unsupported")
    return importer.finish()
