import json
import mailbox
from email.message import EmailMessage

from orggraph.demo import demo_dataset
from orggraph.ingest import parse_bytes, parse_path


def eml(sender="Taylor Reed <taylor@example.org>", message_id="<one@example.org>", body="I report directly to Morgan Bell."):
    message = EmailMessage()
    if sender:
        message["From"] = sender
    message["To"] = "Morgan Bell <morgan@example.org>"
    message["Message-ID"] = message_id
    message["Date"] = "Mon, 05 Jan 2026 09:00:00 -0800"
    message["Subject"] = "Reporting update"
    message.set_content(body)
    return message


def balanced(result):
    report = result["report"]
    assert report["read"] == sum(report[k] for k in ("accepted", "duplicate", "quarantined", "unsupported"))


def test_message_csv_accounts_for_duplicates_and_missing_sender():
    source = b'From,To,Sent At,Message ID,Body\n"Taylor <TAYLOR@example.org>",morgan@example.org,2026-01-05T09:00:00-08:00,one,hello\n"Taylor <taylor@example.org>",morgan@example.org,2026-01-05T17:00:00Z,one,hello\n,morgan@example.org,,two,bad sender\n'
    parsed = parse_bytes(source, "mail.csv")
    balanced(parsed)
    assert parsed["report"]["read"] == 3
    assert parsed["report"]["accepted"] == parsed["report"]["duplicate"] == parsed["report"]["quarantined"] == 1
    message = parsed["dataset"]["messages"][0]
    assert message["timestamp"] == "2026-01-05T17:00:00Z"
    assert message["source_message_id"] == "one"
    assert len(message["source_refs"]) == 2
    assert parse_bytes(source, "mail.csv")["dataset"] == parsed["dataset"]


def test_email_same_display_names_are_distinct():
    data = b"From,To,Body\nAlex Morgan <alex.one@example.org>,Alex Morgan <alex.two@example.org>,hello\n"
    result = parse_bytes(data, "messages.csv")
    assert len(result["dataset"]["entities"]) == 2
    assert len({e["id"] for e in result["dataset"]["entities"]}) == 2


def test_roster_alias_ambiguity_does_not_create_manager():
    data = b"Employee ID,Full Name,Email,Aliases,Manager,Department,Start Date\na,Alex Morgan,alex.one@example.org,alex@example.org,,Research,2026-01-01\nb,Alex Morgan,alex.two@example.org,alex@example.org,,Operations,2026-01-01\nc,Casey Reed,casey@example.org,,alex@example.org,Research,2026-01-01\n"
    result = parse_bytes(data, "roster.csv")
    balanced(result)
    assert len([e for e in result["dataset"]["entities"] if e["type"] == "person"]) == 3
    assert not any(a["relation"] == "reports_to" for a in result["dataset"]["assertions"])
    assert result["report"]["quality"]["ambiguous_aliases"] == 1
    assert any(i["code"] == "ambiguous_manager" for i in result["report"]["issues"])


def test_roster_reporting_is_attributed_source_not_model():
    data = b"id,name,email,manager_id,valid_from\na,Alex,a@example.org,,2026-01-01\nb,Blair,b@example.org,a,2026-01-01\n"
    result = parse_bytes(data, "roster.csv")
    edge, = result["dataset"]["assertions"]
    assert edge["subject"] == "b" and edge["object"] == "a"
    assert edge["origin"] == "source" and edge["candidate_probability"] is None
    evidence = next(e for e in result["dataset"]["evidence"] if e["id"] in edge["evidence_ids"])
    assert evidence["details"]["authored_source"] is True


def test_eml_preserves_source_and_normalizes_time():
    result = parse_bytes(eml().as_bytes(), "letter.eml")
    message, = result["dataset"]["messages"]
    assert message["timestamp"] == "2026-01-05T17:00:00Z"
    assert message["source_message_id"] == "<one@example.org>"
    assert "I report directly to Morgan Bell." in message["body"]
    assert result["report"]["accepted"] == 1
    invalid = parse_bytes(eml(sender=None).as_bytes(), "bad.eml")
    assert invalid["report"]["quarantined"] == 1
    balanced(invalid)


def test_mbox_and_maildir_are_read_only_and_deduplicate(tmp_path):
    path = tmp_path / "mail.mbox"
    box = mailbox.mbox(str(path), create=True)
    box.add(eml())
    box.add(eml())
    box.add(eml(message_id="<two@example.org>", body="Different content."))
    box.flush()
    box.close()
    before = path.read_bytes()
    result = parse_path(path)
    assert result["report"]["accepted"] == 2
    assert result["report"]["duplicate"] == 1
    assert path.read_bytes() == before
    maildir = mailbox.Maildir(str(tmp_path / "maildir"), create=True)
    maildir.add(eml())
    maildir.add(eml())
    maildir.close()
    result = parse_path(tmp_path / "maildir")
    assert result["report"]["accepted"] == 1 and result["report"]["duplicate"] == 1


def test_canonical_validation_quarantines_invalid_span_and_references():
    data = {"schema_version": 1, "entities": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "messages": [{"id": "m", "sender": "a", "to": ["b"], "timestamp": "2026-01-01", "body": "Hello"},
                         {"id": "bad", "sender": "absent", "to": []}],
            "evidence": [{"id": "e", "kind": "message_span", "message_ids": ["m"], "start": 0, "end": 4, "text": "wrong"}],
            "assertions": [{"id": "edge", "subject": "a", "object": "b", "relation": "reports_to", "evidence_ids": ["e"]}]}
    result = parse_bytes(json.dumps(data).encode(), "data.json")
    assert result["report"]["quarantined"] == 3
    assert len(result["dataset"]["messages"]) == 1
    assert result["dataset"]["messages"][0]["timestamp_quality"] == "timezone_unknown"
    balanced(result)


def test_export_wrapper_retains_history_and_unavailable_evidence():
    dataset = {"schema_version": 1, "entities": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
               "evidence": [{"id": "e", "kind": "message_span", "source_ref": "withdrawn", "available": False, "message_ids": ["not-exported"]}],
               "assertions": [{"id": "a1", "subject": "a", "object": "b", "relation": "reports_to", "origin": "analyst", "evidence_ids": ["e"]}]}
    package = {"schema_version": 1, "format": "orggraph-package", "dataset": dataset, "history": {"reviews": [{"id": "event-1"}]}}
    result = parse_bytes(json.dumps(package).encode(), "export.json")
    assert result["report"]["quarantined"] == 0
    assert result["package"]["history"] == package["history"]
    assert result["dataset"]["assertions"][0]["origin"] == "analyst"


def test_conflicting_source_id_is_quarantined():
    data = b"from,to,message_id,body\na@example.org,b@example.org,same,first\na@example.org,b@example.org,same,changed\n"
    result = parse_bytes(data, "mail.csv")
    assert result["report"]["accepted"] == 1 and result["report"]["quarantined"] == 1
    assert result["dataset"]["messages"][0]["body"] == "first"


def test_conflicting_roster_manager_is_not_a_duplicate():
    data = b"id,name,email,manager_id\na,Alex,a@example.org,\nb,Blair,b@example.org,a\nb,Blair,b@example.org,c\nc,Casey,c@example.org,\n"
    result = parse_bytes(data, "roster.csv")
    assert result["report"]["quarantined"] == 1
    assert result["report"]["duplicate"] == 0
    assert result["dataset"]["assertions"][0]["object"] == "a"


def test_forwarded_attachment_not_treated_as_sender_body():
    message = eml(body="Here is an attached historical message.")
    message.add_attachment(eml(sender="Other Person <other@example.org>", body="I report directly to Avery Stone."))
    result = parse_bytes(message.as_bytes(), "forward.eml")
    body = result["dataset"]["messages"][0]["body"]
    assert "historical message" in body
    assert "Avery Stone" not in body


def test_malformed_unit_reference_is_quarantined_without_crashing():
    result = parse_bytes(json.dumps({"entities": [{"id": "a", "name": "A", "unit_id": {"bad": True}}]}).encode(), "data.json")
    assert result["report"]["quarantined"] == 1


def test_nonreporting_authority_allows_null_reporting_type():
    data = {"entities": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            "assertions": [{"id": "authority", "subject": "a", "object": "b", "relation": "higher_authority_than", "reporting_type": None},
                           {"id": "reporting", "subject": "a", "object": "b", "relation": "reports_to", "reporting_type": None}]}
    parsed = parse_bytes(json.dumps(data).encode(), "graph.json")
    assert parsed["report"]["quarantined"] == 1
    assert parsed["dataset"]["assertions"][0]["id"] == "authority"
    assert parsed["dataset"]["assertions"][0]["reporting_type"] is None


def test_malformed_and_unsupported_files_accounted():
    for data, filename, outcome in ((b"{", "bad.json", "quarantined"), (b"x", "archive.pst", "unsupported"),
                                    (b"from,to\na@example.org", "bad.csv", "quarantined")):
        result = parse_bytes(data, filename)
        assert result["report"][outcome] == 1
        balanced(result)


def test_demo_is_deterministic_fictional_and_canonical():
    data = demo_dataset()
    assert data == demo_dataset()
    assert data["corpus"]["synthetic"] is True
    assert 60 <= len([e for e in data["entities"] if e["type"] == "person"]) <= 120
    assert 250 <= len(data["messages"]) <= 600
    assert len([e for e in data["entities"] if e["type"] == "unit"]) == 5
    assert data["labels"] and all(label["source_role"] == "fixture_validation_only" for label in data["labels"])
    result = parse_bytes(json.dumps(data).encode(), "meridian.json")
    assert result["report"]["quarantined"] == 0
    assert result["report"]["duplicate"] == 0
    balanced(result)
