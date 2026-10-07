"""Project reviewed private assertions into a strict, content-free catalog."""
from .schema import ASSERTION_BASE, VALUE_FIELDS, OPTIONAL_VALUE_FIELDS, seal_bundle, validate_bundle, require


def export_bundle(records, reviews, catalog_id, sequence, profile="coverage", policy=None, required_kind="human", require_all_reviewed=True):
    require(profile in ("coverage", "values"), "Unknown profile")
    policy = policy or {"version": 1, "revoked_doc_ids": [], "revoked_assertion_ids": []}
    documents, assertions = [], []
    for record in records:
        doc = record["document"]
        if doc["doc_id"] in policy["revoked_doc_ids"]:
            continue
        require(record.get("processing_status") != "rejected", f"{doc['doc_id']}: rejected source cannot be released")
        rights = doc.get("rights", {})
        require(rights.get("basis") in ("public-domain", "CC0", "CC-BY-4.0", "CC-BY-3.0", "permission"), f"{doc['doc_id']}: unsupported or unverified rights basis")
        require(bool(rights.get("evidence_url")), f"{doc['doc_id']}: rights evidence missing")
        status = reviews.status(record)
        if require_all_reviewed:
            unfinished = [item for item in status["items"] if item["review_status"] in ("pending", "stale")]
            require(not unfinished, f"{doc['doc_id']}: {len(unfinished)} pending or stale assertions")
            wrong_kind = [item for item in status["items"] if item["review_status"] != "reject" and required_kind and item["event"]["actor_kind"] != required_kind]
            require(not wrong_kind, f"{doc['doc_id']}: required {required_kind} review missing")
        pages = record.get("pages", [])
        complete = bool(pages) and all(p.get("status") == "ok" for p in pages) and record.get("processing_status", "complete") == "complete"
        documents.append({
            "doc_id": doc["doc_id"], "title": doc["title"], "manufacturer": doc.get("manufacturer", ""),
            "models": doc.get("models", []), "category": doc.get("category", "appliance"),
            "language": doc.get("language", "en"), "revision": doc.get("revision", ""),
            "request_ref": f"{doc['doc_id']}@{doc.get('revision') or record['sha256'][:12]}",
            "processing_status": "complete" if complete else "partial",
        })
        if "model_categories" in doc:
            documents[-1]["model_categories"] = dict(doc["model_categories"])
        for a in reviews.approved(record, required_kind=required_kind):
            if a["assertion_id"] in policy["revoked_assertion_ids"]:
                continue
            evidence = a.get("evidence", {})
            page = next((p for p in pages if p.get("page_number") == evidence.get("page")), None)
            require(page is not None and page.get("status") == "ok" and evidence.get("text"), "Approved assertion lacks successful source-page evidence")
            for context in evidence.get("context", []):
                context_page = next((p for p in pages if p.get("page_number") == context.get("page")), None)
                require(context_page is not None and context_page.get("status") == "ok" and context.get("text"), "Approved assertion depends on unavailable context-page evidence")
            fields = ASSERTION_BASE | (VALUE_FIELDS | OPTIONAL_VALUE_FIELDS if profile == "values" else set())
            released = {key: a[key] for key in fields if key in a}
            released.setdefault("variant", None)
            if profile == "values":
                require(type(a.get("value")) in (int, float), f"{a['assertion_id']}: unresolved discrete or categorical value; resolve model/variant values before value release, or use coverage profile")
                released.setdefault("value_max", None)
            assertions.append(released)
    bundle = {"schema_version": 1, "catalog_id": catalog_id, "sequence": sequence, "profile": profile, "policy": policy,
              "documents": sorted(documents, key=lambda d: d["doc_id"]), "assertions": sorted(assertions, key=lambda a: a["assertion_id"])}
    return validate_bundle(seal_bundle(bundle))
