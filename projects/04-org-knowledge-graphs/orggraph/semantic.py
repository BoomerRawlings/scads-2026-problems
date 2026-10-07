"""Snapshot-scoped semantic chart views; no corpus bodies or fixture labels.

Departments and communication communities are containers, not reporting edges.
Large containers collapse selected reporting subtrees into presentation branches.
Every person, including unresolved people, remains reachable through paging.
"""
from __future__ import annotations

import base64
from collections import defaultdict, deque
import json

from .store import eligible


DETAIL_THRESHOLD = 60


def team_id(container, head):
    payload = json.dumps([container, head], separators=(",", ":")).encode()
    return "team:" + base64.urlsafe_b64encode(payload).decode().rstrip("=")


def unpack_team(value):
    try:
        encoded = value.removeprefix("team:")
        result = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True))
        if not isinstance(result, list) or len(result) != 2 or not all(isinstance(v, str) for v in result):
            raise ValueError
        return result
    except (ValueError, TypeError, UnicodeError) as exc:
        raise KeyError("Chart branch not found in this snapshot.") from exc


class Forest:
    def __init__(self, members, people):
        self.members = members
        self.children = defaultdict(list)
        self.parent = {}
        for ident in members:
            parent = people[ident].get("manager_id")
            self.parent[ident] = parent if parent in members else None
            self.children[self.parent[ident]].append(ident)
        order = []
        queue = deque(self.children[None])
        while queue:
            ident = queue.popleft()
            order.append(ident)
            queue.extend(self.children[ident])
        self.counts = dict.fromkeys(members, 1)
        self.unresolved = {ident: int(people[ident]["status"] == "unresolved") for ident in members}
        for ident in reversed(order):
            parent = self.parent[ident]
            if parent:
                self.counts[parent] += self.counts[ident]
                self.unresolved[parent] += self.unresolved[ident]

    def descendants(self, head):
        result, queue = [], deque([head])
        while queue:
            ident = queue.popleft()
            result.append(ident)
            queue.extend(self.children[ident])
        return result

    def is_team(self, head):
        if head not in self.members or len(self.members) <= DETAIL_THRESHOLD or self.counts[head] < 2:
            return False
        parent = self.parent[head]
        return parent is None or self.counts[parent] > DETAIL_THRESHOLD


class ChartIndex:
    """Small in-memory metadata index keyed to one immutable snapshot."""

    def __init__(self, db, snap):
        self.snapshot = snap
        rows = db.execute("SELECT e.data,p.manager_id,p.assertion_id,p.status,p.children_count,p.unresolved_reason FROM entities e JOIN projections p ON p.entity_id=e.id AND p.snapshot_id=? WHERE e.import_id=?", (snap["id"], snap["import_id"]))
        self.people, self.units = {}, {}
        for row in rows:
            entity = json.loads(row["data"])
            if entity.get("type", "person") == "person":
                self.people[entity["id"]] = {**entity, **{k: row[k] for k in ("manager_id", "assertion_id", "status", "children_count", "unresolved_reason")}}
            elif entity.get("type") == "unit":
                self.units[entity["id"]] = entity
        self.unit_parent = {ident: value.get("unit_id") if value.get("unit_id") in self.units and value.get("unit_id") != ident else None for ident, value in self.units.items()}
        # Malformed unit cycles must never make a department unreachable. Break
        # one presentation parent per cycle; never manufacture reporting edges.
        completed = set()
        for ident in sorted(self.units):
            seen, cursor = set(), ident
            while cursor is not None and cursor not in completed:
                if cursor in seen:
                    self.unit_parent[cursor] = None
                    break
                seen.add(cursor)
                cursor = self.unit_parent[cursor]
            completed.update(seen)
        self.unit_children = defaultdict(list)
        for ident, parent in self.unit_parent.items():
            self.unit_children[parent].append(ident)
        direct = {ident: set() for ident in self.units}
        documented = set()
        for row in db.execute("SELECT data FROM assertions WHERE snapshot_id=? AND relation='member_of'", (snap["id"],)):
            a = json.loads(row[0])
            if a["subject"] in self.people:
                documented.add(a["subject"])
                if a["object"] in direct and eligible(a, snap.get("as_of")) and not a.get("stale") and a.get("review_status") != "rejected":
                    direct[a["object"]].add(a["subject"])
        # A roster's unit_id is usable when no dated membership assertion exists.
        for ident, person in self.people.items():
            if ident not in documented and person.get("unit_id") in direct:
                direct[person["unit_id"]].add(ident)
        self.unit_members = {ident: set(members) for ident, members in direct.items()}
        order, queue = [], deque(self.unit_children[None])
        while queue:
            ident = queue.popleft()
            order.append(ident)
            queue.extend(self.unit_children[ident])
        for ident in reversed(order):
            parent = self.unit_parent[ident]
            if parent:
                self.unit_members[parent].update(self.unit_members[ident])
        self.unit_direct = {}
        for ident, members in direct.items():
            nested = set().union(*(self.unit_members[child] for child in self.unit_children[ident]))
            self.unit_direct[ident] = members - nested
        self.groups = {}
        for row in db.execute("SELECT data FROM groups_data WHERE snapshot_id=?", (snap["id"],)):
            group = json.loads(row[0])
            # Metadata is the full stored group, not the truncated /api/groups view.
            self.groups[group["id"]] = {"id": group["id"], "name": group.get("name", f"Communication group {group['id']}"), "members": set(group.get("members", [])) & self.people.keys()}
        self.unassigned = {
            "formal": self.people.keys() - set().union(*self.unit_members.values()),
            "inferred": self.people.keys() - set().union(*(g["members"] for g in self.groups.values())),
        }

    def person_node(self, ident):
        person = self.people[ident]
        return {"id": "person:" + ident, "name": person["name"], "kind": "person", "entity_id": ident,
                "role": person.get("role", ""), "status": person["status"], "manager_id": person["manager_id"],
                "children_count": person["children_count"], "unresolved_reason": person.get("unresolved_reason"),
                "person_count": 1, "unresolved_count": int(person["status"] == "unresolved"), "expandable": False}

    def container_node(self, ident, name, kind, members, **extra):
        return {"id": ident, "name": name, "kind": kind, "person_count": len(members),
                "unresolved_count": sum(self.people[p]["status"] == "unresolved" for p in members), "expandable": True, **extra}

    def base_context(self, scope, lens):
        root = [{"id": None, "name": "Departments" if lens == "formal" else "Communication groups"}]
        if scope == "unassigned:" + lens:
            label = "No assigned department" if lens == "formal" else "Outside communication groups"
            return self.unassigned[lens], root + [{"id": scope, "name": label}], []
        if lens == "formal" and scope.startswith("unit:") and scope[5:] in self.units:
            ident, ancestors = scope[5:], []
            cursor = ident
            while cursor is not None:
                ancestors.append({"id": "unit:" + cursor, "name": self.units[cursor]["name"]})
                cursor = self.unit_parent[cursor]
            child_nodes = [self.container_node("unit:" + c, self.units[c]["name"], "unit", self.unit_members[c]) for c in self.unit_children[ident]]
            return self.unit_direct[ident], root + list(reversed(ancestors)), child_nodes
        if lens == "inferred" and scope.startswith("group:") and scope[6:] in self.groups:
            group = self.groups[scope[6:]]
            return group["members"], root + [{"id": scope, "name": group["name"]}], []
        raise KeyError("Chart container not found in this snapshot or lens.")

    def team_node(self, base, head, forest):
        person = self.people[head]
        return {"id": team_id(base, head), "name": person["name"] + " · reporting branch", "kind": "team",
                "entity_id": head, "person_count": forest.counts[head], "unresolved_count": forest.unresolved[head],
                "role": person.get("role", ""), "status": person["status"], "expandable": True,
                "description": "Presentation group from selected reporting links; not an asserted organizational unit."}

    def context(self, scope, lens):
        base, head = unpack_team(scope) if scope.startswith("team:") else (scope, None)
        members, breadcrumbs, nodes = self.base_context(base, lens)
        forest = Forest(members, self.people)
        if head is not None:
            if not forest.is_team(head):
                raise KeyError("Chart branch not found in this snapshot.")
            ancestors, cursor = [], head
            while cursor is not None:
                if forest.is_team(cursor):
                    ancestors.append({"id": team_id(base, cursor), "name": self.people[cursor]["name"] + " · reporting branch"})
                cursor = forest.parent[cursor]
            breadcrumbs += list(reversed(ancestors))
            nodes = []
            if forest.counts[head] <= DETAIL_THRESHOLD:
                nodes.extend(self.person_node(p) for p in forest.descendants(head))
            else:
                nodes.append(self.person_node(head))
                nodes.extend(self.team_node(base, p, forest) if forest.counts[p] > 1 else self.person_node(p) for p in forest.children[head])
        elif len(members) <= DETAIL_THRESHOLD:
            nodes.extend(self.person_node(p) for p in members)
        else:
            nodes.extend(self.team_node(base, p, forest) if forest.counts[p] > 1 else self.person_node(p) for p in forest.children[None])
        return nodes, breadcrumbs, forest, base

    def locate(self, person, lens):
        if person not in self.people:
            raise KeyError("Person not found in this snapshot.")
        if lens == "formal":
            scopes = [(len(self.unit_members[ident]), "unit:" + ident) for ident, members in self.unit_direct.items() if person in members]
        else:
            scopes = [(len(group["members"]), "group:" + ident) for ident, group in self.groups.items() if person in group["members"]]
        base = min(scopes)[1] if scopes else "unassigned:" + lens
        members, _, _ = self.base_context(base, lens)
        forest = Forest(members, self.people)
        ancestors, cursor = [], person
        while cursor is not None:
            ancestors.append(cursor)
            cursor = forest.parent[cursor]
        # The deepest reachable collapsed branch opens into actual person cards.
        for head in ancestors:
            if forest.is_team(head):
                return team_id(base, head)
        return base

    def view(self, *, lens, scope, person, offset, limit):
        if lens not in ("formal", "inferred"):
            raise ValueError("Chart lens must be formal or inferred.")
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Use offset >= 0 and limit from 1 to 200.")
        if person is not None:
            scope = self.locate(person, lens)
        if scope:
            nodes, breadcrumbs, _, _ = self.context(scope, lens)
        else:
            breadcrumbs = [{"id": None, "name": "Departments" if lens == "formal" else "Communication groups"}]
            if lens == "formal":
                nodes = [self.container_node("unit:" + ident, self.units[ident]["name"], "unit", self.unit_members[ident]) for ident in self.unit_children[None]]
            else:
                nodes = [self.container_node("group:" + ident, group["name"], "group", group["members"]) for ident, group in self.groups.items()]
            if self.unassigned[lens]:
                nodes.append(self.container_node("unassigned:" + lens, "No assigned department" if lens == "formal" else "Outside communication groups", "unassigned", self.unassigned[lens]))
        nodes.sort(key=lambda n: (n["kind"] == "person", n["name"].casefold(), n["id"]))
        if person is not None:
            position = next(i for i, node in enumerate(nodes) if node.get("entity_id") == person and node["kind"] == "person")
            offset = position // limit * limit
        description = "Source departments and roster memberships." if lens == "formal" else "Observed communication communities; not verified teams or reporting authority. Memberships may overlap."
        description += " Reporting branches group selected links for navigation. Unresolved people remain visible."
        return {"snapshot": self.snapshot["id"], "total_people": len(self.people), "breadcrumbs": breadcrumbs,
                "nodes": nodes[offset:offset + limit], "edges": [], "total": len(nodes), "offset": offset,
                "limit": limit, "scope": scope or None, "lens": lens, "description": description}


def chart(store, *, lens="formal", scope=None, person=None, offset=0, limit=60, snapshot=None):
    with store.connection() as db:
        snap = store._snapshot(db, snapshot)
        # Immutable metadata is safe to reuse; bound memory to the latest two
        # requested snapshots. Never load the import blob containing messages.
        with store.lock:
            cache = store._chart_indexes
            index = cache.pop(snap["id"], None) or ChartIndex(db, snap)
            cache[snap["id"]] = index
            while len(cache) > 2:
                del cache[next(iter(cache))]
        response = index.view(lens=lens, scope=scope, person=person, offset=offset, limit=limit)
        displayed = {n["entity_id"] for n in response["nodes"] if n["kind"] == "person"}
        for ident in displayed:
            p = index.people[ident]
            if p["manager_id"] not in displayed or not p["assertion_id"]:
                continue
            row = db.execute("SELECT data FROM assertions WHERE snapshot_id=? AND id=?", (snap["id"], p["assertion_id"])).fetchone()
            if row:
                a = json.loads(row[0])
                response["edges"].append({"id": a["id"], "assertion_id": a["id"], "source": "person:" + a["object"],
                    "target": "person:" + a["subject"], "origin": a.get("origin", "model"), "review_status": a.get("review_status", "unreviewed"),
                    "raw_score": a.get("raw_score"), "calibration_status": a.get("calibration_status", "unavailable"),
                    "candidate_probability": a.get("candidate_probability"), "selected_probability": a.get("selected_probability"),
                    "evidence_ids": a.get("evidence_ids", []), "relation": "reports_to"})
        response["edges"].sort(key=lambda e: e["id"])
        return response
