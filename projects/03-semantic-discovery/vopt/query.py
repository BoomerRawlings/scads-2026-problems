"""Bounded offline query compiler with inspectable Boolean query plans.

Hard predicates never become optional ranking features. Unsupported numeric
units, comparative language, ambiguous disjunctions and absent-attribute queries
produce a useful abstention instead of a broadened query.
"""
from __future__ import annotations

import itertools
import math
import re

from .ontology import ATTRIBUTES, CATEGORIES, UNITS, attributes_for_unit, normalize, phrase_pattern, tokens, unit_value


class QueryProblem(ValueError):
    def __init__(self, message: str, status: str = "clarify"):
        super().__init__(message)
        self.status = status


_NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
_UNIT = "(?:" + "|".join(re.escape(k) for k in sorted(UNITS, key=len, reverse=True)) + r")(?!\w|-[a-z]|\s*[/^*·×])"
_COMPARATORS = {
    "not greater than": "le", "not more than": "le", "not above": "le", "not over": "le",
    "no more than": "le", "at most": "le", "up to": "le", "less than or equal to": "le", "<=": "le", "≤": "le",
    "not less than": "ge", "not below": "ge", "not under": "ge", "no less than": "ge",
    "at least": "ge", "minimum": "ge", "greater than or equal to": "ge", ">=": "ge", "≥": "ge",
    "less than": "lt", "lower than": "lt", "below": "lt", "under": "lt", "lighter than": "lt", "slower than": "lt", "<": "lt",
    "greater than": "gt", "higher than": "gt", "more than": "gt", "above": "gt", "over": "gt", "heavier than": "gt", "faster than": "gt", ">": "gt",
    "not equal to": "ne", "not": "ne", "!=": "ne", "≠": "ne",
    "equal to": "eq", "equals": "eq", "exactly": "eq", "=": "eq",
}
_CMP = "(?:" + "|".join(re.escape(k) for k in sorted(_COMPARATORS, key=len, reverse=True)) + ")"
_RANGE = re.compile(rf"(?<![\w.])(?:between\s+(?P<a>{_NUMBER})\s*(?P<ua>{_UNIT})?\s+and\s+(?P<b>{_NUMBER})\s*(?P<ub>{_UNIT})?|(?P<c>{_NUMBER})\s*(?P<uc>{_UNIT})?\s*(?:to|through|-)\s*(?P<d>{_NUMBER})\s*(?P<ud>{_UNIT})?)(?!\w|\.\d)")
_SINGLE = re.compile(rf"(?<![\w.])(?:(?P<cmp>{_CMP})\s*)?(?P<a>{_NUMBER})\s*(?P<ua>{_UNIT})?(?!\w|\.\d)")
_STOP = set("a an the find show list search locate discover get give me please all any manuals manual documents document documentation technical specs specifications specification information info about for on of that which with having has have contains containing contain cover covering covers details detail need needs i want to is are be at by and from whose tools tool machines machine either both as rated peak no load operates operating runs run uses use weighing weighs weighing include including includes their its it can available".split())
_BAD_PREDICATES = re.compile(r"\b(?:waterproof|water-resistant|cordless|battery-powered|compatible|compatibility|decibels?|noise|quiet|quietest|loudest|cheapest|price|cost|efficient|efficiency|fastest|lightest|heaviest|strongest|most powerful|least powerful|newest|oldest|around|approximately|roughly|about\s+\d|approximately|within\s+\d|tolerance|nominal|ac|dc|alternating current|direct current)\b")


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    output = list(text)
    for start, end in spans:
        output[start:end] = " " * (end - start)
    return "".join(output)


def _unique(values: list) -> list:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _empty_clause() -> dict:
    return {"terms": [], "categories": [], "excluded_categories": [], "models": [], "excluded_models": [],
            "variants": [], "manufacturers": [], "titles": [], "revisions": [], "languages": [], "doc_ids": [],
            "conditions": [], "constraints": [], "attributes": [], "qualifier": None}


def _merge(left: dict, right: dict) -> dict:
    result = _empty_clause()
    for key in result:
        if key == "qualifier":
            if left[key] and right[key] and left[key] != right[key]:
                # Qualifiers are attached to their own numeric/presence predicates.
                result[key] = None
            else:
                result[key] = left[key] or right[key]
        else:
            result[key] = _unique(left[key] + right[key])
    return result


def _matches(text: str, choices: list[tuple[str, str]]) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for alias, canonical in sorted(set(choices), key=lambda item: (-len(item[0]), item[0], item[1])):
        for match in re.finditer(phrase_pattern(alias), text):
            if not any(match.start() < end and match.end() > start for start, end, _ in found):
                found.append((match.start(), match.end(), canonical))
    return sorted(found)


def _atom(text: str, documents: list[dict]) -> dict:
    text = text.replace("\x01", "and").replace("\x02", "or").replace("\x03", "(").replace("\x04", ")")
    clause = _empty_clause()
    consumed: list[tuple[int, int]] = []
    # Explicit identity selectors preserve unknown identifiers as exact constraints.
    for match in re.finditer(r'\b(?P<kind>model|variant|manufacturer|category|condition|title|revision|language|doc_id)\s+(?:"(?P<quoted>[^"\n]+)"|(?P<bare>[\w][\w.-]*))', text):
        if any(match.start() < end and match.end() > start for start, end in consumed):
            continue
        kind = match["kind"]
        value = normalize(match["quoted"] or match["bare"])
        selector_end = match.end()
        if kind == "model" and match["bare"]:
            # Catalog-known identifiers may contain spaces. Explicit `model`
            # should not truncate VG-959 QMC to the nonexistent model VG-959.
            known = {normalize(model) for doc in documents for model in doc.get("models", [])}
            for model in sorted(known, key=lambda candidate: (-len(candidate), candidate)):
                if model.startswith(value) and (full := re.match(phrase_pattern(model), text[match.start("bare"):])):
                    value = model
                    selector_end = match.start("bare") + full.end()
                    break
        field = {"model": "models", "variant": "variants", "manufacturer": "manufacturers", "category": "categories", "condition": "conditions",
                 "title": "titles", "revision": "revisions", "language": "languages", "doc_id": "doc_ids"}[kind]
        before = text[max(0, match.start() - 12):match.start()]
        negative = re.search(r"\b(?:not|excluding|except)\s*$", before)
        if negative and kind not in {"model", "category"}:
            raise QueryProblem(f"Negation of {kind} is unsupported; use positive exact selectors.", "unsupported")
        if negative:
            field = "excluded_" + field
            consumed.append((max(0, match.start() - 12) + negative.start(), match.start()))
        clause[field].append(value)
        consumed.append((match.start(), selector_end))

    work = _blank(text, consumed)
    ambiguous_identifiers = set(UNITS) | {alias for aliases in CATEGORIES.values() for alias in aliases} | {alias for _, aliases in ATTRIBUTES.values() for alias in aliases}
    model_choices = [(model, normalize(model)) for doc in documents for model in doc.get("models", [])
                     if not normalize(model).isdigit() and normalize(model) not in ambiguous_identifiers and normalize(model) in work]
    # Hyphenated/alphanumeric model names in the catalog win over number parsing.
    for start, end, value in _matches(work, model_choices):
        before = work[max(0, start - 12):start]
        negative = re.search(r"\b(?:not|excluding|except)\s*$", before)
        clause["excluded_models" if negative else "models"].append(value)
        consumed.append((start, end))
        if negative:
            consumed.append((max(0, start - 12) + negative.start(), start))
    work = _blank(text, consumed)
    categories = [(alias, canonical) for canonical, aliases in CATEGORIES.items() for alias in aliases]
    categories += [(doc["category"], normalize(doc["category"])) for doc in documents if doc.get("category")]
    categories += [(category, normalize(category)) for doc in documents for category in doc.get("model_categories", {}).values()]
    attribute_mentions = _matches(work, [(alias, key) for key, (_, aliases) in ATTRIBUTES.items() for alias in aliases])
    # Attribute phrases such as 'engine horsepower' and 'generator voltage'
    # must not accidentally become an equipment-category restriction first.
    category_text = _blank(work, [(start, end) for start, end, _ in attribute_mentions])
    for start, end, value in _matches(category_text, categories):
        before = work[max(0, start - 12):start]
        negative = re.search(r"\b(?:not|excluding|except)\s*$", before)
        clause["excluded_categories" if negative else "categories"].append(value)
        consumed.append((start, end))
        if negative:
            consumed.append((max(0, start - 12) + negative.start(), start))

    work = _blank(text, consumed)
    if re.search(r"(?<!\w)[-\u2212]\s*\d", work):
        raise QueryProblem("Negative technical quantities are outside this query schema.", "unsupported")
    bad = _BAD_PREDICATES.search(work)
    if bad:
        raise QueryProblem(f"The released schema cannot enforce '{bad.group()}'. Use a supported attribute or exact released identity.", "unsupported")
    qualifiers = _matches(work, [("no load", "no_load"), ("no-load", "no_load"), ("no_load", "no_load"), ("rated", "rated"), ("peak", "peak"), ("unspecified", "unspecified")])
    qualifier_names = _unique([item[2] for item in qualifiers])
    if len(qualifier_names) > 1:
        raise QueryProblem("Separate rated, peak, and no-load predicates with 'and' and repeat each attribute.")
    if qualifier_names:
        clause["qualifier"] = qualifier_names[0]
    consumed += [(start, end) for start, end, _ in qualifiers]
    work = _blank(text, consumed)
    attribute_spans = _matches(work, [(alias, key) for key, (_, aliases) in ATTRIBUTES.items() for alias in aliases])
    # Canonical field names are useful in reproducible, machine-authored queries.
    attribute_spans += _matches(_blank(work, [(a, b) for a, b, _ in attribute_spans]), [(key, key) for key in ATTRIBUTES])
    for start, end, attribute in attribute_spans:
        before = work[max(0, start - 22):start]
        if re.search(r"\b(?:without|missing|lacking|not having|does not have|no)\s*$", before):
            raise QueryProblem("Missing metadata is unknown, not proof an attribute is absent. Search for observed coverage instead.", "unsupported")
        clause["attributes"].append({"attribute": attribute, "qualifier": clause["qualifier"]})

    # Numerical patterns are parsed before erasing attributes, because 'hp' and
    # 'rpm' can be both attribute names and unit suffixes.
    number_spans: list[tuple[int, int]] = []
    numerical = [(match, True) for match in _RANGE.finditer(work)]
    single_work = _blank(work, [match.span() for match, _ in numerical])
    numerical += [(match, False) for match in _SINGLE.finditer(single_work)]
    for match, is_range in sorted(numerical, key=lambda pair: pair[0].start()):
        if is_range:
            first = match["a"] or match["c"]
            second = match["b"] or match["d"]
            u1 = match["ua"] or match["uc"]
            u2 = match["ub"] or match["ud"]
            u1, u2 = u1 or u2, u2 or u1
            op = "range"
        else:
            first, second, u1, u2 = match["a"], None, match["ua"], None
            op = _COMPARATORS.get(match["cmp"], "eq")
        if not u1:
            raise QueryProblem("Specify a supported unit for every numeric predicate (for example 120 V or weight below 5 kg).")
        # Prefer an explicit attribute before the quantity. Unit aliases inside
        # the quantity do not override an explicit conflicting attribute.
        preceding = [(a, b, attr) for a, b, attr in attribute_spans if b <= match.start() and match.start() - b < 65]
        following = [(a, b, attr) for a, b, attr in attribute_spans if a >= match.end() and a - match.end() < 25]
        if preceding:
            attribute = max(preceding, key=lambda item: item[1])[2]
        elif following:
            attribute = min(following, key=lambda item: item[0])[2]
        else:
            inferred = attributes_for_unit(u1)
            if len(inferred) != 1:
                raise QueryProblem("The unit has multiple technical roles. Specify input/output voltage or input/output power explicitly; horsepower is separate.")
            attribute = inferred[0]
        try:
            value, unit = unit_value(float(first.replace(",", "")), u1, attribute)
            high = unit_value(float(second.replace(",", "")), u2, attribute)[0] if second else None
        except (KeyError, ValueError) as error:
            raise QueryProblem(str(error), "unsupported") from error
        if not math.isfinite(value) or (high is not None and not math.isfinite(high)):
            raise QueryProblem("Numeric values must be finite.", "unsupported")
        if high is not None and value > high:
            raise QueryProblem("Range lower bound exceeds its upper bound.")
        constraint = {"attribute": attribute, "op": op, "value": value, "unit": unit}
        if high is not None:
            constraint["value_max"] = high
        if clause["qualifier"]:
            constraint["qualifier"] = clause["qualifier"]
        clause["constraints"].append(constraint)
        number_spans.append(match.span())
    consumed += number_spans + [(start, end) for start, end, _ in attribute_spans]
    remainder = _blank(text, consumed)
    if re.search(r"[\d<>=±~]|\b(?:above|below|under|over|between|greater|less|minimum|maximum|at least|at most|without|not|except|excluding|missing|lacking)\b", remainder):
        raise QueryProblem("Unresolved numeric, comparison, or negation expression. Use explicit attributes, units, and supported operators.", "unsupported")
    if re.search(r"\bpower\b", remainder):
        raise QueryProblem("Specify input power, output power, or horsepower; 'power' has multiple technical meanings.")
    if re.search(r"\b(?:voltage|volts)\b", remainder):
        raise QueryProblem("Specify input voltage or output voltage; their technical roles are distinct.")
    bad = _BAD_PREDICATES.search(remainder)
    if bad:
        raise QueryProblem(f"The released schema cannot enforce '{bad.group()}'. Use a supported attribute or exact released identity.", "unsupported")
    clause["terms"] = [token for token in tokens(remainder) if token not in _STOP]
    for key in clause:
        if isinstance(clause[key], list):
            clause[key] = _unique(clause[key])
    return clause


def _protect(text: str) -> str:
    # Boolean words inside a quoted identity or a between-range are not operators.
    text = re.sub(r'"[^"\n]*"', lambda m: re.sub(r"\band\b", "\x01", re.sub(r"\bor\b", "\x02", m[0])).replace("(", "\x03").replace(")", "\x04"), text)
    text = re.sub(rf"\bbetween\s+{_NUMBER}\s*(?:{_UNIT})?\s+and\s+{_NUMBER}", lambda m: m[0].replace("and", "\x01"), text)
    # 'or equal to' is a comparator, not Boolean disjunction.
    text = text.replace("or equal to", "\x02 equal to")
    return text


def parse_query(text: str, documents: list[dict] | None = None) -> dict:
    """Compile the documented safe subset of natural language into DNF clauses.

    List fields at the top level are summaries only. `clauses` contains the
    executable OR-of-AND plan. Equality/ranges use conservative full-interval
    semantics, not an assumption that one operating point represents a range.
    """
    plan = {"status": "ready", "text": text, "terms": [], "categories": [], "models": [], "constraints": [],
            "attributes": [], "message": "", "mode": "discovery", "clauses": [],
            "numeric_semantics": "entire recorded interval including tolerance must satisfy predicate"}
    if not isinstance(text, str):
        return {**plan, "status": "unsupported", "message": "Query must be text."}
    if not text.strip():
        return {**plan, "status": "clarify", "message": "Enter a document, model, category, or technical attribute query."}
    if len(text) > 2000:
        return {**plan, "status": "unsupported", "message": "Query exceeds the 2,000-character limit."}
    clean = normalize(text)
    clean = re.sub(r"\s+", " ", clean)
    if re.search(r"\b(?:what is|what's|tell me)\s+(?:the\s+)?(?:voltage|weight|speed|horsepower|pressure|capacity|input power|output power)\b", clean):
        return {**plan, "status": "unsupported", "message": "Direct specification answers are deferred. Ask which manuals cover the attribute instead."}
    if clean.count('"') % 2:
        return {**plan, "status": "clarify", "message": "Close the quoted identity or condition."}
    pieces = [part.strip() for part in re.split(r"(\(|\)|\band\b|\bor\b)", _protect(clean)) if part.strip()]
    position = 0
    depth = 0

    def factor() -> list[dict]:
        nonlocal position, depth
        if position >= len(pieces) or pieces[position] in {"and", "or", ")"}:
            raise QueryProblem("Every Boolean operator needs predicates on both sides.")
        if pieces[position] == "(":
            depth += 1
            if depth > 8:
                raise QueryProblem("Query nesting exceeds eight levels.", "unsupported")
            position += 1
            result = expression()
            if position >= len(pieces) or pieces[position] != ")":
                raise QueryProblem("Unbalanced query parentheses.")
            position += 1
            depth -= 1
            return result
        value = pieces[position]
        position += 1
        return [_atom(value, documents or [])]

    def conjunction() -> list[dict]:
        nonlocal position
        result = factor()
        while position < len(pieces) and pieces[position] not in {"or", ")"}:
            if pieces[position] == "and":
                position += 1
            other = factor()
            if len(result) * len(other) > 32:
                raise QueryProblem("Query expands beyond 32 alternatives.", "unsupported")
            result = [_merge(a, b) for a, b in itertools.product(result, other)]
        return result

    def expression() -> list[dict]:
        nonlocal position
        result = conjunction()
        while position < len(pieces) and pieces[position] == "or":
            position += 1
            result += conjunction()
            if len(result) > 32:
                raise QueryProblem("Query expands beyond 32 alternatives.", "unsupported")
        return result

    try:
        clauses = expression()
        if position != len(pieces):
            raise QueryProblem("Unbalanced query parentheses.")
        if "or" in pieces and "(" not in pieces and any(c["constraints"] for c in clauses) and any(not c["constraints"] for c in clauses):
            raise QueryProblem("Disjunction scope is ambiguous. Use '(drills or saws) and weight below 5 kg', or repeat full predicates in each branch.")
        # Numeric predicates already imply attribute coverage; retaining both is
        # useful for transparent plans and coverage-profile rejection.
        plan["clauses"] = clauses
        for field in ("terms", "categories", "models", "constraints"):
            plan[field] = _unique([value for clause in clauses for value in clause[field]])
        plan["attributes"] = _unique([value["attribute"] for clause in clauses for value in clause["attributes"]] + [value["attribute"] for value in plan["constraints"]])
        plan["message"] = "All predicates in a branch must hold for the same document, model, and compatible variant. Alternatives use OR."
    except QueryProblem as error:
        plan["status"] = error.status
        plan["message"] = str(error)
    return plan
