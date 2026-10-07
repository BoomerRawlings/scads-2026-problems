"""Deterministic fictional corpus. Synthetic labels are held apart from evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .ingest import _source_assertion

FIRST = ["Maya", "Jonah", "Priya", "Elias", "Nadia", "Theo", "Sofia", "Owen", "Iris", "Leo", "Amara", "Finn", "Leila",
         "Caleb", "Mina", "Hugo", "Zara", "Miles", "Elena", "Arjun", "Cora", "Noah", "Lina", "Felix", "Asha", "Remy"]
LAST = ["Chen", "Patel", "Brooks", "Rivera", "Okafor", "Kim", "Shah", "Bennett", "Park", "Hassan", "Silva", "Nguyen", "Ellis"]
UNITS = [("research", "Research", "Scientific Researcher"), ("platform", "Data Platform", "Data Engineer"),
         ("intelligence", "Product Intelligence", "Research Analyst"), ("operations", "Operations", "Operations Specialist"),
         ("partnerships", "Client Partnerships", "Partnerships Associate")]


def demo_dataset(person_count: int = 72) -> dict:
    """Return a fresh fictional organization with strong, weak and absent evidence.

    This fixture exercises software behavior only. It supplies no accuracy or
    calibration evidence for real organizations; gold labels never enter models.
    """
    if isinstance(person_count, bool) or not isinstance(person_count, int) or not 72 <= person_count <= 100_000:
        raise ValueError("person_count must be an integer between 72 and 100000")
    dataset = {"schema_version": 1,
               "corpus": {"id": "meridian-research-demo-v1", "name": "Meridian Research", "synthetic": True,
                          "description": "Fictional organization for exploring evidence, uncertainty, corrections, and export.",
                          "source_role": "synthetic_model_evidence", "date_start": "2026-01-05", "date_end": "2026-03-31",
                          "limitations": ["Synthetic fixture; no real-world accuracy or calibration claim.",
                                          "Shared accounts and external correspondents are explicitly identified.",
                                          "Ground-truth fixture labels are separate from all model inputs."]},
               "entities": [], "messages": [], "assertions": [], "evidence": [], "labels": []}
    entities = dataset["entities"]
    people: dict[str, dict] = {}
    true_managers: dict[str, str] = {}
    units: dict[str, list[str]] = {}

    def person(entity_id, name, role, unit_id=None, **extra):
        item = {"id": entity_id, "name": name, "type": "person", "email": f"{entity_id}@meridian.example", "aliases": [], "role": role, **extra}
        if unit_id:
            item["unit_id"] = unit_id
        entities.append(item)
        people[entity_id] = item
        return item

    person("avery-stone", "Avery Stone", "Chief Executive")
    counter = 0
    for unit_slug, unit_name, specialist_role in UNITS:
        unit_id = "unit-" + unit_slug
        entities.append({"id": unit_id, "name": unit_name, "type": "unit", "aliases": [], "description": "Formal source directory unit"})
        members = []
        for position in range(13):
            counter += 1
            entity_id = f"{unit_slug}-{position:02d}"
            name = f"{FIRST[(counter - 1) % len(FIRST)]} {LAST[((counter - 1) // len(FIRST) + (counter - 1) % len(LAST)) % len(LAST)]}"
            if entity_id in {"research-12", "operations-12"}:
                name = "Alex Morgan"
            role = f"Director of {unit_name}" if position == 0 else f"{unit_name} Team Lead" if position in {1, 7} else specialist_role
            person(entity_id, name, role, unit_id)
            members.append(entity_id)
            true_managers[entity_id] = "avery-stone" if position == 0 else f"{unit_slug}-00" if position in {1, 7} else f"{unit_slug}-{1 if position < 7 else 7:02d}"
        units[unit_id] = members

    for index, name in enumerate(("Robin Vale", "Sam Ellis", "Noor Wells", "Kit Harper"), start=1):
        person(f"sparse-{index}", name, "Recently joined; source coverage incomplete", "unit-research" if index < 3 else "unit-operations", coverage="sparse")
    for entity_id, name in (("partner-sam", "Sam Kline"), ("partner-ren", "Ren Calder")):
        person(entity_id, name, "External collaborator", external=True)
        people[entity_id]["email"] = f"{entity_id}@partner.example"
    for entity_id, name, unit_id in (("shared-help", "Research Help Desk", "unit-operations"), ("shared-lab", "Lab Scheduling", "unit-research")):
        item = {"id": entity_id, "name": name, "type": "shared_mailbox", "email": f"{entity_id}@meridian.example", "aliases": [], "unit_id": unit_id}
        entities.append(item)
        people[entity_id] = item

    directory = {"id": "source-directory-2026", "kind": "source_assertion", "source_ref": "fictional://meridian/directory/2026-01-05",
                 "available": True, "text": "Authored fictional directory: unit memberships as of 5 January 2026. Reporting lines for directors separately supplied.",
                 "details": {"synthetic": True, "authored_source": True, "valid_from": "2026-01-05", "source_role": "analyst_reference"}}
    dataset["evidence"].append(directory)
    for entity in entities:
        if entity.get("unit_id") and entity["type"] == "person" and not entity.get("external"):
            dataset["assertions"].append(_source_assertion(entity["id"], "member_of", entity["unit_id"], directory["id"], valid_from="2026-01-05"))
    for unit_slug, _, _ in UNITS:
        entity_id = f"{unit_slug}-00"
        source = {"id": f"source-leadership-{unit_slug}", "kind": "source_assertion",
                  "source_ref": f"fictional://meridian/leadership-register/2026-01-05#{entity_id}", "available": True,
                  "text": f"{people[entity_id]['name']} reports to Avery Stone, effective 2026-01-05.",
                  "details": {"synthetic": True, "authored_source": True, "source_role": "analyst_reference"}}
        dataset["evidence"].append(source)
        dataset["assertions"].append(_source_assertion(entity_id, "reports_to", "avery-stone", source["id"], valid_from="2026-01-05"))

    base = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)

    def message(sender, to, subject, body, *, cc=(), timestamp=True):
        number = len(dataset["messages"]) + 1
        stamp = (base + timedelta(days=(number * 7) % 82, minutes=(number * 23) % 420)).isoformat().replace("+00:00", "Z") if timestamp else None
        dataset["messages"].append({"id": f"meridian-msg-{number:04d}", "sender": sender, "to": list(to), "cc": list(cc),
                                    "timestamp": stamp, "subject": subject, "body": body,
                                    "source_ref": f"fictional://meridian/messages/{number:04d}",
                                    "source_message_id": f"<meridian-{number:04d}@meridian.example>"})

    for index, (employee, manager) in enumerate(true_managers.items()):
        unit_members = units[people[employee]["unit_id"]]
        colleague = next(p for p in unit_members if p not in {employee, manager})
        manager_name = people[manager]["name"]
        # Some employees have repeated direct statements; others only ordinary traffic.
        if index % 5 not in {3, 4} and people[employee]["name"] != "Alex Morgan":
            message(employee, [manager], "Reporting line confirmation", f"Hi {manager_name},\n\nI report directly to {manager_name}. Please include that reporting line in the onboarding directory.\n\nThanks,\n{people[employee]['name']}")
            message(employee, [colleague], "Coverage for this week", f"{manager_name} is my line manager. I will discuss my objectives with them this week. The shared analysis notes are ready.")
        message(employee, [manager], "Weekly work update", "The assigned analysis is complete. The remaining validation work is scheduled for Thursday. Please share any feedback before the next check-in.")
        message(manager, [employee], "Re: Weekly work update", "Thanks for the update. Please check the references and bring the revised notes to our next discussion.")
        message(employee, [colleague], "Methods handoff", "Here are the methods notes for our next joint review. Let me know which sections need further evidence.")
        message(colleague, [employee], "Re: Methods handoff", "I reviewed the methods notes and added the open questions. We can compare results tomorrow.")
        dataset["labels"].append({"id": f"gold-{employee}", "subject": employee, "relation": "reports_to", "object": manager,
                                  "valid_from": "2026-01-05", "valid_to": None, "synthetic": True,
                                  "source_role": "fixture_validation_only", "independent_of_model_input": True})

    # A cross-functional coordinator is highly connected without being a manager.
    coordinator = "intelligence-05"
    people[coordinator]["role"] = "Program Coordinator"
    cross_team = [f"{slug}-{position:02d}" for slug, _, _ in UNITS for position in (3, 5, 9, 11)]
    for index, member in enumerate(cross_team):
        if member == coordinator:
            continue
        message(coordinator, [member], "Atlas project review", "For the Atlas project, please send me your status by Friday. I coordinate this temporary project and approve the meeting agenda; your formal reporting line is unchanged.")
        message(member, [coordinator], "Re: Atlas project review", "Here is the requested project status. Our team will attend the cross-functional review and share the open questions.")
        if index % 3 == 0:
            message(member, [cross_team[(index + 4) % len(cross_team)]], "Atlas working session", "Let's compare the research and operations notes at the project working session.")

    for index in range(8):
        employee = cross_team[index]
        message(employee, ["shared-help"], "Access request", "Please restore access to the research workspace. This is a service request.")
        message("shared-help", [employee], "Re: Access request", "Your access request is complete. Reply to this shared mailbox if you need help.")
    message("shared-lab", ["research-02", "research-03"], "Instrument availability", "The lab calendar has been updated. This is an automated scheduling notice.")
    message("partner-sam", ["partnerships-04"], "Joint workshop", "Please send our joint workshop agenda. We are external collaborators, and this does not describe an internal reporting relationship.")
    message("partnerships-04", ["partner-sam", "partner-ren"], "Re: Joint workshop", "The agenda is ready for review. Thanks for coordinating from your organization.")
    message("sparse-1", ["shared-help"], "New account", "My account has just been activated. I have not received the current reporting directory.")
    message("sparse-2", ["shared-lab"], "Schedule", "Please add me to the lab calendar.", timestamp=False)
    message("research-12", ["operations-12"], "Name collision", "We both appear as Alex Morgan in the directory. Please keep our email identities separate.")
    # Quoted and conflicting language exercises uncertainty, not synthetic certainty.
    message("operations-06", ["operations-01"], "Forwarded planning note", "> I report directly to Avery Stone.\n\nThe sentence above came from a forwarded message; it does not describe my manager.")
    message("platform-11", ["platform-07"], "Unconfirmed transition", "I report directly to " + people["platform-07"]["name"] + ". The transition date is still under discussion.")
    message("platform-11", ["platform-01"], "Conflicting directory note", "I report directly to " + people["platform-01"]["name"] + ". Please resolve the conflicting directory entries before using them.")
    # A header-only record exercises descriptive behavior without fabricated text.
    message("sparse-3", ["operations-01"], "No retained message body", "")
    return _expand_dataset(dataset, person_count) if person_count != 72 else dataset


_SCALE_FIRST = FIRST + [
    "Ada", "Adrian", "Alina", "Anika", "Anya", "Asher", "Audrey", "Beatrice", "Blake", "Camila",
    "Celine", "Dalia", "Dante", "Daria", "Edwin", "Emil", "Esme", "Eva", "Farah", "Flora",
    "Gabriel", "Gemma", "Grace", "Hana", "Idris", "Imani", "Isaac", "Jasper", "Jules", "Kiran",
    "Lara", "Luca", "Lucia", "Malik", "Marco", "Nico", "Nora", "Oscar", "Petra", "Quinn",
    "Rafael", "Rhea", "Rohan", "Rosa", "Rowan", "Sana", "Sara", "Soren", "Talia", "Tomas",
    "Vera", "Victor", "Yara", "Zane",
]
_SCALE_LAST = LAST + [
    "Adams", "Alvarez", "Andersen", "Baker", "Bell", "Brown", "Campbell", "Castillo", "Clarke", "Cole",
    "Costa", "Davis", "Diaz", "Duarte", "Evans", "Fernandez", "Fischer", "Flores", "Foster", "Garcia",
    "Gomez", "Grant", "Green", "Gupta", "Hayes", "Huang", "Ito", "Jackson", "Jensen", "Kaur",
    "Khan", "Kowalski", "Lee", "Lewis", "Liu", "Lopez", "Martin",
]
_DEPARTMENTS = {
    "research": ("Applied Statistics", "Materials Science", "Field Research", "Simulation", "Methods", "Discovery", "Measurement", "Research Systems"),
    "platform": ("Data Infrastructure", "Developer Tools", "Data Quality", "Compute Services", "Integrations", "Reliability", "Storage", "Data Products"),
    "intelligence": ("Market Research", "Product Analytics", "Decision Science", "Customer Insights", "Forecasting", "Experimentation", "Insights Delivery", "Knowledge Systems"),
    "operations": ("People Services", "Finance Operations", "Facilities", "Procurement", "Service Operations", "Business Systems", "Planning", "Workplace Services"),
    "partnerships": ("Academic Partnerships", "Industry Partnerships", "Public Programs", "Partner Success", "Regional Programs", "Joint Research", "Community Programs", "Alliance Operations"),
}


def _expand_dataset(dataset: dict, person_count: int) -> dict:
    """Extend one organization in O(people + messages), retaining the small fixture.

    Each existing division grows an eight-way reporting tree below its director.
    The first eight added people head formal departments; later staff report to
    an earlier person. Metadata records the authored scenario mix, not confidence.
    """
    added_count = person_count - 72
    people = {item["id"]: item for item in dataset["entities"] if item["type"] == "person"}
    by_division: dict[str, list[str]] = {slug: [] for slug, _, _ in UNITS}
    managers: dict[str, str] = {}
    departments: dict[str, str] = {}
    children: dict[str, list[str]] = {}
    added: list[tuple[str, str, int, int]] = []
    start = "2026-01-05"
    directory = {"id": "source-scale-directory-v1", "kind": "source_assertion",
                 "source_ref": "fictional://meridian/expanded-directory/2026-01-05", "available": True,
                 "text": "Authored fictional department directory. Memberships are supplied; reporting lines are supplied only for selected leadership anchors.",
                 "details": {"synthetic": True, "authored_source": True, "source_role": "analyst_reference", "valid_from": start}}
    dataset["evidence"].append(directory)

    for index in range(added_count):
        slug, division_name, specialist_role = UNITS[index % len(UNITS)]
        local_index = index // len(UNITS)
        entity_id = f"{slug}-scale-{local_index:05d}"
        members = by_division[slug]
        if local_index < 8:
            manager = f"{slug}-00"
            department = f"unit-{slug}-department-{local_index:02d}"
            department_name = _DEPARTMENTS[slug][local_index]
            dataset["entities"].append({"id": department, "name": department_name, "type": "unit", "aliases": [],
                                        "unit_id": f"unit-{slug}", "description": f"Formal department within {division_name}; synthetic directory."})
            role = f"Head of {department_name}"
        else:
            manager = members[(local_index - 8) // 8]
            department = departments[manager]
            # Future children are known from the requested size, without scanning.
            next_child_global = (8 + local_index * 8) * len(UNITS) + index % len(UNITS)
            role = f"{division_name} Team Lead" if next_child_global < added_count else specialist_role
        first = _SCALE_FIRST[index % len(_SCALE_FIRST)]
        middle = FIRST[(index // len(_SCALE_FIRST)) % len(FIRST)]
        last = _SCALE_LAST[index // (len(_SCALE_FIRST) * len(FIRST))]
        item = {"id": entity_id, "name": f"{first} {middle} {last}", "type": "person",
                "email": f"{entity_id}@meridian.example", "aliases": [], "role": role, "unit_id": department}
        if (index + index // 20) % 20 == 0:
            item["coverage"] = "sparse"
        dataset["entities"].append(item)
        people[entity_id] = item
        members.append(entity_id)
        departments[entity_id] = department
        managers[entity_id] = manager
        children.setdefault(manager, []).append(entity_id)
        added.append((entity_id, slug, local_index, index))
        dataset["assertions"].append(_source_assertion(entity_id, "member_of", department, directory["id"], valid_from=start))
        dataset["labels"].append({"id": f"gold-{entity_id}", "subject": entity_id, "relation": "reports_to", "object": manager,
                                  "valid_from": start, "valid_to": None, "synthetic": True,
                                  "source_role": "fixture_validation_only", "independent_of_model_input": True})

    base = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)

    def message(sender, recipients, subject, body, *, timestamp=True):
        number = len(dataset["messages"]) + 1
        stamp = (base + timedelta(days=(number * 7) % 82, minutes=(number * 23) % 420)).isoformat().replace("+00:00", "Z") if timestamp else None
        dataset["messages"].append({"id": f"meridian-msg-{number:04d}", "sender": sender, "to": list(recipients), "cc": [],
                                    "timestamp": stamp, "subject": subject, "body": body,
                                    "source_ref": f"fictional://meridian/messages/{number:04d}",
                                    "source_message_id": f"<meridian-{number:04d}@meridian.example>"})

    profiles = {"explicit_self_report": 0, "sparse_header_only": 0, "behavior_only": 0,
                "conflicting_self_reports": 0, "quoted_claim_only": 0, "approval_only": 0}
    source_anchors = 0
    for employee, slug, local_index, index in added:
        manager = managers[employee]
        manager_name = people[manager]["name"]
        siblings = children[manager]
        # Sibling lists have at most eight entries; this lookup remains bounded.
        peer = siblings[(siblings.index(employee) + 1) % len(siblings)] if len(siblings) > 1 else f"{slug}-03"
        next_slug = UNITS[(index + 1) % len(UNITS)][0]
        other_division = by_division[next_slug]
        cross_peer = other_division[local_index % len(other_division)] if other_division else f"{next_slug}-03"
        # Rotate each block so coverage patterns are not tied to one division.
        profile = (index + index // 20) % 20
        if (local_index < 8 or (local_index % 257 == 0 and employee in children)) and profile not in {0, 2}:
            eid = f"source-leadership-{employee}"
            dataset["evidence"].append({"id": eid, "kind": "source_assertion",
                                        "source_ref": f"fictional://meridian/expanded-leadership/2026-01-05#{employee}",
                                        "available": True, "text": f"{people[employee]['name']} reports to {manager_name}, effective {start}.",
                                        "details": {"synthetic": True, "authored_source": True, "source_role": "analyst_reference"}})
            dataset["assertions"].append(_source_assertion(employee, "reports_to", manager, eid, valid_from=start))
            source_anchors += 1
        if profile == 0:
            profiles["sparse_header_only"] += 1
            message(employee, ["shared-help"], "Account activation — body unavailable", "", timestamp=False)
            continue
        message(employee, [manager], "Weekly delivery update", "The scheduled work is ready for review. The remaining validation tasks are due Thursday. Please send any feedback before our check-in.")
        message(manager, [employee], "Re: Weekly delivery update", "Thank you. Please check the references and bring the remaining questions to our next discussion.")
        message(employee, [peer], "Methods review", "The methods notes are ready for a joint review. Can we compare the open questions and the evidence we still need?")
        message(peer, [employee], "Re: Methods review", "I added comments to the shared notes. Let us compare results at tomorrow's working session.")
        message(employee, [cross_peer], "Cross-department handoff", "Our departments are coordinating the next delivery. Here are the handoff questions for the shared working session.")
        message(cross_peer, [employee], "Re: Cross-department handoff", "Thanks for the handoff. The working-session agenda now includes your department's questions.")
        if profile == 1:
            profiles["behavior_only"] += 1
        elif profile == 2:
            profiles["conflicting_self_reports"] += 1
            alternate = f"{slug}-07"  # Existing team lead, never this new person's true manager.
            message(employee, [manager], "Directory entry requiring review", f"I report directly to {manager_name}. The directory entry needs a review before use.")
            message(employee, [alternate], "Conflicting directory entry", f"I report directly to {people[alternate]['name']}. Please resolve the conflicting directory entries before using them.")
        elif profile == 3:
            profiles["quoted_claim_only"] += 1
            message(employee, [manager], "Forwarded historical note", "> I report directly to Avery Stone.\n\nThe quoted text belongs to a forwarded message. It does not describe my reporting relationship.")
        elif profile == 4:
            profiles["approval_only"] += 1
            message(employee, ["intelligence-05"], "Project agenda approval", "Please approve the shared meeting agenda. This request concerns project coordination, and our formal reporting lines are unchanged.")
        else:
            profiles["explicit_self_report"] += 1
            message(employee, [manager], "Reporting line confirmation", f"I report directly to {manager_name}. Please record that line in the onboarding directory.")
            message(employee, [peer], "Objectives and coverage", f"{manager_name} is my line manager. We will discuss my objectives this week; the shared analysis notes are ready.")
        if index % 12 == 7:
            message("intelligence-05", [employee], "Atlas delivery coordination", "Please share your Atlas project status. I coordinate the working session; this does not change your formal manager.")
            message(employee, ["intelligence-05"], "Re: Atlas delivery coordination", "Our team's project status is ready for the cross-functional working session.")
        if index % 25 == 6:
            message(employee, ["shared-help"], "Research workspace access", "Please renew access to the shared research workspace. This is a service request.")
            message("shared-help", [employee], "Re: Research workspace access", "Your service request is complete. This shared mailbox handles workspace access.")

    dataset["corpus"].update({
        "id": f"meridian-research-demo-{person_count}-v1",
        "description": f"Fictional {person_count:,}-person Meridian organization with communication evidence, partial source reporting anchors, and separate validation labels.",
        "generator": {"version": "meridian-expansion-v1", "seed": 17, "randomized": False,
                      "algorithm": "Deterministic index-based eight-way division hierarchy and communication scenario schedule.",
                      "person_count": person_count, "internal_people": person_count - 2, "external_people": 2,
                      "base_people": 72, "added_people": added_count, "maximum_added_reports_per_manager": 8,
                      "message_count": len(dataset["messages"]), "formal_unit_count": sum(item["type"] == "unit" for item in dataset["entities"]),
                      "added_reporting_anchors": source_anchors, "added_evidence_profiles": profiles,
                      "label_count": len(dataset["labels"]),
                      "limits": ["Authored language patterns are intentionally simple; this is a workflow and scale fixture, not an accuracy benchmark.",
                                 "Counts include two external people; units and shared mailboxes are additional entities.",
                                 "Base sparse people and external correspondents have no asserted gold manager; added sparse people have gold labels withheld from model input."]},
    })
    return dataset
