"""Strict metadata release schema. Unknown fields are rejected, never stripped silently."""
from __future__ import annotations
import math
import re
from .io import digest

ATTRIBUTES = {
    "input_voltage": "V", "output_voltage": "V", "frequency": "Hz", "input_current": "A", "input_power": "W",
    "output_power": "W", "horsepower": "hp", "speed": "rpm", "weight": "kg",
    "blade_diameter": "mm", "displacement": "cm3", "capacity": "L", "pressure": "kPa",
}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
DOC_FIELDS = {"doc_id", "title", "manufacturer", "models", "category", "language", "revision", "request_ref", "processing_status"}
OPTIONAL_DOC_FIELDS = {"model_categories"}
ASSERTION_BASE = {"assertion_id", "doc_id", "model", "variant", "attribute", "qualifier", "status"}
VALUE_FIELDS = {"value", "value_max", "unit"}
OPTIONAL_VALUE_FIELDS = {"tolerance", "conditions"}
BUNDLE_FIELDS = {"schema_version", "catalog_id", "sequence", "profile", "policy", "documents", "assertions", "integrity"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(obj, required, optional=frozenset(), label="record"):
    require(isinstance(obj, dict), f"{label}: expected object")
    missing, extra = required - obj.keys(), obj.keys() - required - optional
    require(not missing, f"{label}: missing fields {sorted(missing)}")
    require(not extra, f"{label}: forbidden fields {sorted(extra)}")


def string(value, label, length=240, empty=False):
    require(isinstance(value, str) and len(value) <= length and (empty or bool(value.strip())), f"{label}: invalid string")
    require(not any(ord(ch) < 32 for ch in value), f"{label}: control characters forbidden")


def identifier(value, label):
    require(isinstance(value, str) and ID.fullmatch(value), f"{label}: invalid identifier")


def number(value, label, nonnegative=True):
    require(type(value) in (int, float), f"{label}: finite number required")
    require(-1e100 <= value <= 1e100 and math.isfinite(value), f"{label}: finite representable number required")
    require(not nonnegative or value >= 0, f"{label}: negative value")


def string_list(value, label, maximum=200):
    require(isinstance(value, list) and len(value) <= maximum, f"{label}: invalid list")
    for v in value:
        string(v, label)
    require(len(set(value)) == len(value), f"{label}: duplicates")


def seal_bundle(bundle):
    result = dict(bundle)
    result.pop("integrity", None)
    result["integrity"] = digest(result)
    return result


def validate_bundle(bundle):
    exact(bundle, BUNDLE_FIELDS, label="bundle")
    require(type(bundle["schema_version"]) is int and bundle["schema_version"] == 1, "Unsupported schema version")
    identifier(bundle["catalog_id"], "catalog_id")
    require(type(bundle["sequence"]) is int and bundle["sequence"] > 0, "sequence must be a positive integer")
    require(bundle["profile"] in ("coverage", "values"), "Unknown release profile")
    policy = bundle["policy"]
    exact(policy, {"version", "revoked_doc_ids", "revoked_assertion_ids"}, label="policy")
    require(type(policy["version"]) is int and policy["version"] > 0, "policy version must be a positive integer")
    for key in ("revoked_doc_ids", "revoked_assertion_ids"):
        string_list(policy[key], key, 100000)
        for v in policy[key]:
            identifier(v, key)
    require(isinstance(bundle["documents"], list) and len(bundle["documents"]) <= 100000, "Invalid document list")
    require(isinstance(bundle["assertions"], list) and len(bundle["assertions"]) <= 1000000, "Invalid assertion list")
    documents = {}
    for doc in bundle["documents"]:
        exact(doc, DOC_FIELDS, OPTIONAL_DOC_FIELDS, label="document")
        identifier(doc["doc_id"], "doc_id")
        require(doc["doc_id"] not in documents, "Duplicate document ID")
        require(doc["doc_id"] not in policy["revoked_doc_ids"], "Revoked document in bundle")
        for key in DOC_FIELDS - {"models", "processing_status", "doc_id"}:
            string(doc[key], key, length=500 if key == "title" else 240, empty=key in {"manufacturer", "revision"})
        string_list(doc["models"], "models")
        if "model_categories" in doc:
            require(isinstance(doc["model_categories"], dict), "model_categories: expected object")
            require(set(doc["model_categories"]) <= set(doc["models"]), "Category assigned to undeclared model")
            for category in doc["model_categories"].values():
                string(category, "model category", 80)
        require(doc["processing_status"] in ("complete", "partial"), "Invalid processing status")
        documents[doc["doc_id"]] = doc
    seen = set()
    for a in bundle["assertions"]:
        values = bundle["profile"] == "values"
        exact(a, ASSERTION_BASE | (VALUE_FIELDS if values else set()), OPTIONAL_VALUE_FIELDS if values else set(), "assertion")
        identifier(a["assertion_id"], "assertion_id")
        require(a["assertion_id"] not in seen, "Duplicate assertion ID")
        seen.add(a["assertion_id"])
        require(a["assertion_id"] not in policy["revoked_assertion_ids"], "Revoked assertion in bundle")
        identifier(a["doc_id"], "assertion doc_id")
        string(a["model"], "assertion model")
        string(a["attribute"], "attribute")
        require(a["doc_id"] in documents, "Assertion refers to absent document")
        require(a["model"] in documents[a["doc_id"]]["models"], "Assertion model not declared by document")
        require(a["attribute"] in ATTRIBUTES, "Unsupported attribute")
        require(a["qualifier"] in ("rated", "peak", "no_load", "unspecified"), "Unsupported qualifier")
        require(a["status"] == "reviewed", "Unreviewed assertion cannot be released")
        if a["variant"] is not None:
            string(a["variant"], "variant")
        if values:
            number(a["value"], "value")
            if a["value_max"] is not None:
                number(a["value_max"], "value_max")
                require(a["value_max"] >= a["value"], "Inverted value range")
            require(a["unit"] == ATTRIBUTES[a["attribute"]], "Unit does not match canonical attribute")
            if "conditions" in a:
                string_list(a["conditions"], "conditions", 10)
            if "tolerance" in a:
                t = a["tolerance"]
                exact(t, {"minus", "plus", "unit"}, label="tolerance")
                number(t["minus"], "minus")
                number(t["plus"], "plus")
                require(t["unit"] == a["unit"], "Tolerance unit mismatch")
                require(a["value"] - t["minus"] >= 0, "Tolerance yields negative quantity")
    require(isinstance(bundle["integrity"], str) and len(bundle["integrity"]) == 64, "Missing integrity hash")
    require(seal_bundle(bundle)["integrity"] == bundle["integrity"], "Bundle integrity mismatch")
    return bundle


def validate_review_candidate(assertion, document):
    """Validate the corrected structured claim before appending an approval."""
    # Observed presence can be reviewed even when discrete values still need variant resolution.
    discrete = isinstance(assertion.get("value"), str) and bool(re.fullmatch(r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)+", assertion["value"]))
    fields = ASSERTION_BASE if discrete else ASSERTION_BASE | VALUE_FIELDS | OPTIONAL_VALUE_FIELDS
    released = {key: assertion[key] for key in fields if key in assertion}
    released.update(status="reviewed")
    released.setdefault("variant", None)
    if not discrete:
        released.setdefault("value_max", None)
    doc = {"doc_id": document["doc_id"], "title": document["title"], "models": document.get("models", []),
        "manufacturer": document.get("manufacturer", ""), "category": document.get("category", "appliance"),
        "language": document.get("language", "en"), "revision": document.get("revision", ""),
        "request_ref": document["doc_id"], "processing_status": "partial"}
    validate_bundle(seal_bundle({"schema_version": 1, "catalog_id": "review-validation", "sequence": 1,
        "profile": "coverage" if discrete else "values", "policy": {"version": 1, "revoked_doc_ids": [], "revoked_assertion_ids": []},
        "documents": [doc], "assertions": [released]}))
