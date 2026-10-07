"""Search choices projected only from an active released-catalog snapshot."""
from __future__ import annotations

import json

from .ontology import ATTRIBUTES


def attribute_option(key):
    # These units are public vocabulary, not values inferred from source pages.
    return {"key": key, "label": key.replace("_", " "), "unit": ATTRIBUTES[key][0]}


def search_options(db, meta):
    """The caller holds a read transaction for metadata, documents and claims.

    Explicit projections avoid accidentally exposing future catalog fields.
    Options describe observed coverage; their absence is not proof that a
    document or model lacks a physical feature.
    """
    documents = [json.loads(row["data"]) for row in db.execute("SELECT data FROM documents ORDER BY doc_id")]
    grouped = {}
    for row in db.execute("SELECT data FROM assertions ORDER BY assertion_id"):
        assertion = json.loads(row["data"])
        identity = (assertion["doc_id"], assertion["model"], assertion["attribute"])
        entry = grouped.setdefault(identity, {"conditions": set(), "qualifiers": set(), "variants": set()})
        if meta["profile"] == "values":
            entry["conditions"].update(assertion.get("conditions", []))
        entry["qualifiers"].add(assertion["qualifier"])
        if assertion["variant"] is not None:
            entry["variants"].add(assertion["variant"])

    scopes = []
    for document in documents:
        for model in sorted(document["models"] or [""], key=lambda value: (value.casefold(), value)):
            attributes = []
            for key in sorted(ATTRIBUTES):
                entry = grouped.get((document["doc_id"], model, key))
                if entry is None:
                    continue
                attributes.append({**attribute_option(key), **{
                    name: sorted(values, key=lambda value: (value.casefold(), value))
                    for name, values in entry.items()
                }})
            scopes.append({
                "doc_id": document["doc_id"], "title": document["title"], "model": model,
                "category": document.get("model_categories", {}).get(model, document["category"]),
                "manufacturer": document["manufacturer"], "attributes": attributes,
            })
    return {
        "catalog_id": meta["catalog_id"], "sequence": meta["active_sequence"],
        "integrity": meta["integrity"], "profile": meta["profile"],
        "numeric_filters": meta["profile"] == "values", "scopes": scopes,
        # Supported fields remain searchable when the catalog has no observed
        # claim. The UI must distinguish support from scoped coverage.
        "attributes": [attribute_option(key) for key in sorted(ATTRIBUTES)],
    }
