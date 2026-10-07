"""Offline retrieval over released metadata, with no source-store access.

Both rankers execute the same strict query plan. FTS5/BM25 is the lexical
baseline. The semantic comparator is ontology-normalized TF-IDF cosine; it is
deliberately labeled and must not be described as pretrained dense embeddings.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
import sqlite3

from .ontology import ATTRIBUTES, normalize, semantic_tokens, tokens, unit_value
from .query import parse_query


METHODS = {"lexical": "SQLite FTS5 BM25 over released metadata", "semantic": "local ontology-normalized TF-IDF cosine (not pretrained embeddings)"}
_DOC_FIELDS = {"doc_id", "title", "manufacturer", "models", "model_categories", "category", "language", "revision", "request_ref", "processing_status"}
_ASSERT_FIELDS = {"assertion_id", "doc_id", "model", "variant", "attribute", "qualifier", "status", "value", "value_max", "unit", "tolerance", "conditions"}


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _profile(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT value FROM catalog_meta WHERE key = ?", ("profile",)).fetchone()
    if not row:
        return "coverage"  # Fail closed when no profile is declared.
    try:
        value = json.loads(row[0])
    except (ValueError, TypeError):
        value = row[0]
    return value if value in {"coverage", "values"} else "coverage"


def _scope_assertions(assertions: list[dict], model: str, variant: str | None) -> list[dict]:
    # Unqualified model assertions apply to a model's variants. A fact explicitly
    # scoped to another variant never fills a missing constraint.
    return [a for a in assertions if normalize(a["model"]) == normalize(model)
            and (a.get("variant") is None or normalize(a["variant"]) == normalize(variant or ""))]


def _entry_text(document: dict, model: str, variant: str | None, assertions: list[dict]) -> str:
    parts = [str(document.get(field) or "") for field in ("title", "manufacturer", "category", "language", "revision")]
    parts += [model, variant or ""]
    parts.append(document.get("model_categories", {}).get(model, document.get("category", "")))
    for assertion in assertions:
        parts += [assertion["attribute"].replace("_", " "), assertion.get("qualifier", "").replace("_", " ")]
        parts += assertion.get("conditions", [])
        # Released values may be indexed; a coverage rebuild has none. Raw
        # snippets, paths, source URIs, and private evidence are never read here.
        if "value" in assertion:
            parts += [str(assertion["value"]), str(assertion.get("value_max") or ""), str(assertion.get("unit") or "")]
    return " ".join(parts)


def build_index(connection: sqlite3.Connection, documents: list[dict], assertions: list[dict]) -> None:
    """Replace all derived indexes inside the caller's existing transaction.

    No commit, executescript, source lookup, network access, or persistent cache.
    The allowlist is checked again so direct callers cannot index private fields.
    """
    documents = list(documents)
    assertions = list(assertions)
    for document in documents:
        if set(document) - _DOC_FIELDS:
            raise ValueError("Search index accepts released document fields only.")
    for assertion in assertions:
        if set(assertion) - _ASSERT_FIELDS or assertion.get("status") != "reviewed":
            raise ValueError("Search index accepts reviewed released assertions only.")
        if assertion["attribute"] not in ATTRIBUTES:
            raise ValueError(f"Unsupported released attribute: {assertion['attribute']}")
    connection.execute("CREATE TABLE IF NOT EXISTS search_entries (entry_id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, model TEXT NOT NULL, variant TEXT, text TEXT NOT NULL, semantic TEXT NOT NULL)")
    # FTS5 DELETE can retain old tokens in shadow-table segment blocks. Rebuild
    # the virtual table under secure_delete so withdrawn text does not survive
    # in the active database's derived index, including after profile downgrade.
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute("DROP TABLE IF EXISTS search_fts")
    try:
        connection.execute("CREATE VIRTUAL TABLE search_fts USING fts5(text, tokenize='unicode61')")
    except sqlite3.OperationalError as error:
        raise RuntimeError("This offline Python SQLite build needs FTS5 enabled.") from error
    connection.execute("DELETE FROM search_entries")
    by_document: dict[str, list[dict]] = defaultdict(list)
    for assertion in assertions:
        by_document[assertion["doc_id"]].append(assertion)
    entry_id = 0
    for document in sorted(documents, key=lambda d: d["doc_id"]):
        doc_assertions = by_document[document["doc_id"]]
        for model in sorted(set(document["models"]), key=normalize) or [""]:
            model_assertions = [a for a in doc_assertions if normalize(a["model"]) == normalize(model)]
            variants = sorted({a["variant"] for a in model_assertions if a.get("variant")}, key=normalize) or [None]
            for variant in variants:
                entry_id += 1
                applicable = _scope_assertions(model_assertions, model, variant)
                body = _entry_text(document, model, variant, applicable)
                connection.execute("INSERT INTO search_entries(entry_id,doc_id,model,variant,text,semantic) VALUES (?,?,?,?,?,?)",
                                   (entry_id, document["doc_id"], model, variant, body, _json(dict(Counter(semantic_tokens(body))))))
                connection.execute("INSERT INTO search_fts(rowid,text) VALUES (?,?)", (entry_id, body))


def _interval(assertion: dict) -> tuple[float, float] | None:
    unresolved = ("approximate value; tolerance unspecified", "unresolved footnote marker")
    if any(normalize(condition).startswith(unresolved) for condition in assertion.get("conditions", [])):
        # Selecting a condition label cannot manufacture a numerical error bound
        # or resolve a missing footnote. This requires upstream evidence review.
        return None
    value = assertion.get("value")
    high = assertion.get("value_max")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    high = value if high is None else high
    if isinstance(high, bool) or not isinstance(high, (int, float)):
        return None
    try:
        low, _ = unit_value(value, assertion["unit"], assertion["attribute"])
        upper, _ = unit_value(high, assertion["unit"], assertion["attribute"])
        tolerance = assertion.get("tolerance")
        if tolerance:
            minus, _ = unit_value(tolerance["minus"], tolerance["unit"], assertion["attribute"])
            plus, _ = unit_value(tolerance["plus"], tolerance["unit"], assertion["attribute"])
            if minus < 0 or plus < 0:
                return None
            low -= minus
            upper += plus
        if not math.isfinite(low) or not math.isfinite(upper) or low > upper:
            return None
        return low, upper
    except (KeyError, ValueError, TypeError):
        return None


def _satisfies(interval: tuple[float, float], constraint: dict) -> bool:
    low, high = interval
    value = constraint["value"]
    close_low = math.isclose(low, value, rel_tol=1e-12, abs_tol=1e-12)
    close_high = math.isclose(high, value, rel_tol=1e-12, abs_tol=1e-12)
    op = constraint["op"]
    if op == "gt":
        return low > value and not close_low
    if op == "ge":
        return low > value or close_low
    if op == "lt":
        return high < value and not close_high
    if op == "le":
        return high < value or close_high
    if op == "eq":
        return close_low and close_high
    if op == "ne":
        return (high < value and not close_high) or (low > value and not close_low)
    if op == "range":
        return (low > value or close_low) and (high < constraint["value_max"] or math.isclose(high, constraint["value_max"], rel_tol=1e-12, abs_tol=1e-12))
    return False


def _same_interval(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(left, right))


def _evaluate(clause: dict, document: dict, model: str, variant: str | None,
              assertions: list[dict], body: str, method: str) -> tuple[str, list[str], list[str]]:
    category = normalize(document.get("model_categories", {}).get(model, document.get("category", "")))
    model_key = normalize(model)
    # Lists in a clause are conjunctions, including exact identifiers.
    if any(category != value for value in clause["categories"]) or category in clause["excluded_categories"]:
        return "false", [], []
    if any(model_key != value for value in clause["models"]) or model_key in clause["excluded_models"]:
        return "false", [], []
    if any(normalize(variant or "") != value for value in clause["variants"]):
        return "false", [], []
    if any(normalize(document.get("manufacturer", "")) != value for value in clause["manufacturers"]):
        return "false", [], []
    for field, key in (("title", "titles"), ("revision", "revisions"), ("language", "languages"), ("doc_id", "doc_ids")):
        if any(normalize(document.get(field) or "") != value for value in clause[key]):
            return "false", [], []
    if clause["terms"]:
        tokenize = semantic_tokens if method == "semantic" else tokens
        body_terms = set(tokenize(body))
        if not set(tokenize(" ".join(clause["terms"]))).issubset(body_terms):
            return "false", [], []
    selected_conditions = set(clause["conditions"])
    known_conditions = {normalize(condition) for a in assertions for condition in a.get("conditions", [])}
    if not selected_conditions.issubset(known_conditions):
        return "unknown", [], ["Requested operating condition is not represented by released metadata."]
    ids: list[str] = []
    unknown: list[str] = []
    conflicts: list[str] = []
    false = False
    for presence in clause["attributes"]:
        facts = [a for a in assertions if a["attribute"] == presence["attribute"] and (not presence.get("qualifier") or a["qualifier"] == presence["qualifier"])]
        if facts:
            ids.extend(a["assertion_id"] for a in facts)
        else:
            unknown.append(f"No released observation of {presence['attribute']} for this model and qualifier; absence is unknown.")
    for constraint in clause["constraints"]:
        facts = [a for a in assertions if a["attribute"] == constraint["attribute"] and (not constraint.get("qualifier") or a["qualifier"] == constraint["qualifier"])]
        applicable = [a for a in facts if {normalize(c) for c in a.get("conditions", [])}.issubset(selected_conditions)]
        if not applicable:
            if facts:
                unknown.append(f"{constraint['attribute']} has unresolved operating conditions; specify condition \"...\" exactly.")
            else:
                unknown.append(f"No released {constraint['attribute']} observation for this model and qualifier.")
            continue
        intervals = [_interval(a) for a in applicable]
        if any(interval is None for interval in intervals):
            unknown.append(f"{constraint['attribute']} lacks a defensible numeric interval; unresolved approximation/footnote conditions require upstream review.")
            continue
        by_qualifier: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for assertion, interval in zip(applicable, intervals):
            by_qualifier[assertion["qualifier"]].append(interval)
        conflict = any(any(not _same_interval(values[0], value) for value in values[1:]) for values in by_qualifier.values())
        if conflict:
            conflicts.append(f"Conflicting {constraint['attribute']} observations within the same model, variant, and qualifier.")
            continue
        outcomes = [_satisfies(interval, constraint) for interval in intervals]
        if len(by_qualifier) > 1 and any(outcomes) and not all(outcomes):
            unknown.append(f"{constraint['attribute']} depends on rating qualifier; specify rated, peak, or no-load.")
            continue
        if not all(outcomes):
            false = True
        else:
            ids.extend(a["assertion_id"] for a in applicable)
    # A false conjunct is definitely false even if another conjunct is unknown.
    if false:
        return "false", [], []
    if conflicts:
        return "conflict", [], conflicts + unknown
    if unknown:
        return "unknown", [], unknown
    return "true", sorted(set(ids)), []


def _scores(connection: sqlite3.Connection, entries: list[tuple], query: str, method: str) -> dict[int, float]:
    if method == "lexical":
        query_tokens = tokens(query)
        if not query_tokens:
            return {}
        # FTS query syntax is generated from literal escaped tokens only; user
        # MATCH operators never reach SQLite. SQL itself is parameterized.
        match = " OR ".join('"' + token.replace('"', '""') + '"' for token in sorted(set(query_tokens)))
        return {row[0]: -float(row[1]) for row in connection.execute("SELECT rowid,bm25(search_fts) FROM search_fts WHERE search_fts MATCH ?", (match,))}
    corpus = {entry[0]: json.loads(entry[5]) for entry in entries}
    frequency: Counter = Counter()
    for bag in corpus.values():
        frequency.update(bag.keys())
    count = len(corpus)
    query_bag = Counter(semantic_tokens(query))

    def vector(bag: dict) -> dict[str, float]:
        return {term: (1.0 + math.log(tf)) * (1.0 + math.log((count + 1.0) / (frequency[term] + 1.0))) for term, tf in bag.items()}

    q = vector(query_bag)
    qnorm = math.sqrt(sum(value * value for value in q.values()))
    scores = {}
    for entry_id, bag in corpus.items():
        document = vector(bag)
        norm = math.sqrt(sum(value * value for value in document.values()))
        scores[entry_id] = sum(value * document.get(term, 0.0) for term, value in q.items()) / (qnorm * norm) if qnorm and norm else 0.0
    return scores


def _revision_warnings(documents: dict[str, dict], all_assertions: list[dict], document: dict, model: str,
                       variant: str | None, assertions: list[dict], attributes: list[str]) -> list[str]:
    warnings = []
    if not attributes:
        return warnings
    own = {(a["attribute"], a["qualifier"]): _interval(a) for a in assertions if a["attribute"] in attributes}
    for other in all_assertions:
        other_doc = documents.get(other["doc_id"], {})
        if other["doc_id"] == document["doc_id"] or normalize(other.get("model", "")) != normalize(model):
            continue
        if normalize(other_doc.get("manufacturer", "")) != normalize(document.get("manufacturer", "")):
            continue
        if other.get("variant") is not None and normalize(other["variant"]) != normalize(variant or ""):
            continue
        key = (other["attribute"], other["qualifier"])
        interval = _interval(other)
        if key in own and own[key] is not None and interval is not None and not _same_interval(interval, own[key]):
            warnings.append(f"Released document {other['doc_id']} (revision {other_doc.get('revision') or 'unspecified'}) reports different {other['attribute']}; this match applies only to the returned document revision.")
    return sorted(set(warnings))


def search(connection: sqlite3.Connection, query: str, limit: int = 10, method: str = "lexical") -> dict:
    """Search without fetching originals; results are document requests, not answers."""
    if method not in METHODS:
        raise ValueError("method must be 'lexical' or 'semantic'")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    documents = {row[0]: json.loads(row[1]) for row in connection.execute("SELECT doc_id,data FROM documents")}
    plan = parse_query(query, list(documents.values()))
    response = {"status": plan["status"], "plan": plan, "results": [], "message": plan["message"], "method": method,
                "scoring": METHODS[method], "diagnostics": {"unknown_scopes": 0, "conflicting_scopes": 0, "partial_documents": 0, "details": []}}
    if plan["status"] != "ready":
        return response
    if plan["constraints"] and _profile(connection) != "values":
        response.update(status="unsupported", message="Coverage-only metadata contains observed attribute presence, not approved values. Numeric filtering is unavailable; request attribute coverage or import a values profile.")
        return response
    entries = list(connection.execute("SELECT entry_id,doc_id,model,variant,text,semantic FROM search_entries"))
    all_assertions = [json.loads(row[0]) for row in connection.execute("SELECT data FROM assertions")]
    by_document: dict[str, list[dict]] = defaultdict(list)
    by_product: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for assertion in all_assertions:
        by_document[assertion["doc_id"]].append(assertion)
        document = documents[assertion["doc_id"]]
        by_product[(normalize(document.get("manufacturer", "")), normalize(assertion["model"]))].append(assertion)
    scores = _scores(connection, entries, query, method)
    partial = set()
    for entry_id, doc_id, model, variant, body, _ in entries:
        document = documents[doc_id]
        assertions = _scope_assertions(by_document[doc_id], model, variant)
        evaluations = [_evaluate(clause, document, model, variant, assertions, body, method) for clause in plan["clauses"]]
        matches = [evaluation for evaluation in evaluations if evaluation[0] == "true"]
        if not matches:
            problems = [evaluation for evaluation in evaluations if evaluation[0] in {"unknown", "conflict"}]
            if problems:
                has_conflict = any(evaluation[0] == "conflict" for evaluation in problems)
                key = "conflicting_scopes" if has_conflict else "unknown_scopes"
                response["diagnostics"][key] += 1
                if document.get("processing_status") == "partial":
                    partial.add(doc_id)
                if len(response["diagnostics"]["details"]) < 20:
                    response["diagnostics"]["details"].append({"doc_id": doc_id, "model": model, "variant": variant,
                        "title": document["title"], "revision": document.get("revision"), "request_ref": document["request_ref"],
                        "status": "conflict" if has_conflict else "unknown", "reasons": sorted({reason for p in problems for reason in p[2]}),
                        "available_conditions": sorted({condition for assertion in assertions for condition in assertion.get("conditions", [])}),
                        "available_qualifiers": sorted({assertion["qualifier"] for assertion in assertions})})
            continue
        matched_ids = sorted({assertion_id for _, ids, _ in matches for assertion_id in ids})
        revision_candidates = by_product[(normalize(document.get("manufacturer", "")), normalize(model))]
        warnings = _revision_warnings(documents, revision_candidates, document, model, variant, assertions, plan["attributes"])
        if document.get("processing_status") == "partial":
            partial.add(doc_id)
            warnings.append("Document processing is partial; unobserved attributes remain unknown.")
        explanation = ("Matched released metadata for the same model" + (f" and variant {variant}" if variant else "") + "."
                       if model else "Matched released document metadata; no model identity is released for this document.")
        if matched_ids:
            explanation += " Supporting released assertions: " + ", ".join(matched_ids) + "."
        if plan["constraints"]:
            explanation += " Every requested numeric bound holds over the entire recorded interval, including tolerance."
        response["results"].append({"doc_id": doc_id, "title": document["title"], "model": model, "variant": variant,
                                    "revision": document.get("revision"), "request_ref": document["request_ref"],
                                    "score": round(scores.get(entry_id, 0.0), 10), "matched_assertions": matched_ids,
                                    "explanation": explanation, "warnings": warnings, "processing_status": document["processing_status"]})
    response["diagnostics"]["partial_documents"] = len(partial)
    response["results"].sort(key=lambda result: (-result["score"], result["doc_id"], result["model"], result["variant"] or ""))
    response["total_matches"] = len(response["results"])
    response["results"] = response["results"][:limit]
    if response["results"]:
        response.update(status="ready", message=f"{response['total_matches']} matching document/model scopes. Results cite released metadata only.")
    elif response["diagnostics"]["conflicting_scopes"]:
        response.update(status="conflict", message="Released assertions conflict for otherwise relevant models. Resolve the conflicting revision/qualifier evidence before using numeric predicates.")
    elif response["diagnostics"]["unknown_scopes"]:
        response.update(status="unknown", message="Relevant released records lack sufficient unambiguous metadata. Unobserved attributes and unresolved operating conditions are unknown, not absent.")
    else:
        response.update(status="no_match", message="No released document/model scope satisfies every requested predicate. This does not establish that no matching source document exists.")
    return response


def __getattr__(name: str):
    # Preserve the documented vopt.search.Catalog import without a module cycle.
    if name == "Catalog":
        from .catalog import Catalog
        return Catalog
    raise AttributeError(name)
