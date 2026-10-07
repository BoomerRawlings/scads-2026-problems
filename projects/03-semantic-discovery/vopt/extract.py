"""Conservative, auditable technical-assertion extraction from local page data.

The rule baseline reads each line independently. The layout method groups
geometric rows, resolves explicit model columns and retains localized footnotes.
Neither mode guesses electrical-input versus mechanical-output power, unitless
dimensions, or unassigned specifications in multi-model documents.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import copy
from pathlib import Path
from statistics import median

EXTRACTION_VERSION = "layout-rules-2"


def extraction_signature() -> str:
    return EXTRACTION_VERSION + ":" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:20]


def reextract_record(record: dict) -> dict:
    """Reinterpret preserved pages without rereading a PDF or initializing OCR.

    Original page-processing provenance remains fixed. The new extractor's
    source hash changes the record fingerprint, invalidating bound approvals.
    Caller may explicitly correct document metadata before invoking this helper.
    """
    result = copy.deepcopy(record)
    if not isinstance(result.get("document"), dict) or not isinstance(result.get("pages"), list):
        raise ValueError("A private ingestion record with document and pages is required")
    result["page_processing_version"] = result.get("page_processing_version", result.get("processing_version", "legacy-unknown"))
    result["extraction_version"] = extraction_signature()
    result["processing_version"] = result["page_processing_version"] + "+" + result["extraction_version"]
    result["assertions"] = [] if result.get("processing_status") == "rejected" else extract_assertions(result["pages"], result["document"])
    result["warnings"] = [warning for warning in result.get("warnings", []) if not warning.startswith("identity_required:")]
    if not result["document"].get("models"):
        result["warnings"].append("identity_required: supply verified product model identities before technical extraction.")
    return result

_LABELS = {
    "output_voltage": r"(?:rated\s+|generator\s+)?output\s+voltage|voltage\s+output",
    "input_voltage": r"(?:rated\s+|supply\s+|input\s+|operating\s+|mains\s+)?voltage|(?:power\s+)?supply(?=\s*[:=(]?\s*\d)",
    "frequency": r"(?:supply\s+|input\s+|rated\s+)?frequency",
    "input_current": r"(?:rated\s+|input\s+|supply\s+|operating\s+)?current|amperage|amps(?=\s*[:=(]?\s*\d)",
    "input_power": r"power\s+(?:input|consumption)|(?:rated\s+)?(?:input|consumed)\s+(?:power|wattage)|(?:rated\s+)?(?:power\s+)?consumption",
    "output_power": r"power\s+output|(?:rated\s+|mechanical\s+)?output\s+(?:power|wattage)|mechanical\s+power|(?:rated\s+)?generator\s+output",
    "horsepower": r"(?:engine\s+|motor\s+|rated\s+|peak\s+|brake\s+)?horse\s*power|(?:engine|motor)\s+(?:hp|bhp)",
    "speed": r"(?:no[ -]?load\s+|idle\s+|rated\s+|rotational\s+|motor\s+|spindle\s+|maximum\s+)?speed|revolutions(?:\s+per\s+minute)?",
    "weight": r"(?:net\s+|gross\s+|shipping\s+|dry\s+|operating\s+)?weight|(?:net\s+|dry\s+)?mass",
    "blade_diameter": r"(?:saw\s+)?blade\s+(?:diameter|size)|diameter\s+of\s+(?:the\s+)?(?:saw\s+)?blade",
    "displacement": r"(?:engine\s+|cylinder\s+|piston\s+)?displacement|(?:engine|cylinder)\s+(?:capacity|volume)",
    "capacity": r"(?:(?:fuel|oil|tank|water|air\s+tank|reservoir)\s+)?capacity|(?:fuel|oil|tank|water|reservoir)\s+volume",
    "pressure": r"(?:(?:working|operating|maximum|max\.?|rated|air|discharge)\s+)?pressure",
}
_LABEL = re.compile(r"\b(?:" + "|".join(f"(?P<{name}>{pattern})" for name, pattern in _LABELS.items()) + r")\b", re.I)
_NUM = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,]\d+)?"
_UNIT = r"(?:r\s*/\s*min|min\s*(?:\^?\s*-\s*1|⁻¹)|revs?\s*/\s*min|rpm|kPa|MPa|psi|bars?|kHz|Hz|cycles?|kW|watts?|W|kV|volts?|V|mA|amps?|amperes?|A|bhp|hp|kg|lbs?|pounds?|oz|grams?|g|cm\s*(?:\^?3|³)|cc|mm|cm|inches|inch|in\b|[\"″]|litres?|liters?|mL|L\b)(?![a-zA-Z])"
_VALUE = re.compile(rf"(?<![\w.])(?P<first>{_NUM})(?:\s*-?\s*(?P<unit1>{_UNIT}))?(?:\s*(?P<sep>±|\+\s*/\s*-|\bto\b|[–—-]|/)\s*(?P<second>{_NUM})(?:\s*-?\s*(?P<unit2>{_UNIT}))?)?(?P<marker>[*†‡]{{1,2}})?", re.I)
_PAREN_UNIT = re.compile(rf"[\[(]\s*(?P<unit>{_UNIT})\s*[\])]", re.I)
_UNIT_MAP = {
    "v": ("input_voltage", "V", 1), "volt": ("input_voltage", "V", 1), "volts": ("input_voltage", "V", 1), "kv": ("input_voltage", "V", 1000),
    "hz": ("frequency", "Hz", 1), "khz": ("frequency", "Hz", 1000),
    "cycle": ("frequency", "Hz", 1), "cycles": ("frequency", "Hz", 1),
    "a": ("input_current", "A", 1), "amp": ("input_current", "A", 1), "amps": ("input_current", "A", 1), "ampere": ("input_current", "A", 1), "amperes": ("input_current", "A", 1), "ma": ("input_current", "A", .001),
    "w": ("power", "W", 1), "watt": ("power", "W", 1), "watts": ("power", "W", 1), "kw": ("power", "W", 1000),
    "hp": ("horsepower", "hp", 1), "bhp": ("horsepower", "hp", 1),
    "rpm": ("speed", "rpm", 1), "r/min": ("speed", "rpm", 1), "rev/min": ("speed", "rpm", 1), "revs/min": ("speed", "rpm", 1), "min-1": ("speed", "rpm", 1), "min^-1": ("speed", "rpm", 1), "min⁻¹": ("speed", "rpm", 1),
    "kg": ("weight", "kg", 1), "g": ("weight", "kg", .001), "gram": ("weight", "kg", .001), "grams": ("weight", "kg", .001), "lb": ("weight", "kg", .45359237), "lbs": ("weight", "kg", .45359237), "pound": ("weight", "kg", .45359237), "pounds": ("weight", "kg", .45359237), "oz": ("weight", "kg", .028349523125),
    "mm": ("blade_diameter", "mm", 1), "cm": ("blade_diameter", "mm", 10), "in": ("blade_diameter", "mm", 25.4), "inch": ("blade_diameter", "mm", 25.4), "inches": ("blade_diameter", "mm", 25.4), '"': ("blade_diameter", "mm", 25.4), "″": ("blade_diameter", "mm", 25.4),
    "cm3": ("displacement", "cm3", 1), "cm^3": ("displacement", "cm3", 1), "cm³": ("displacement", "cm3", 1), "cc": ("displacement", "cm3", 1),
    "l": ("capacity", "L", 1), "ml": ("capacity", "L", .001), "litre": ("capacity", "L", 1), "litres": ("capacity", "L", 1), "liter": ("capacity", "L", 1), "liters": ("capacity", "L", 1),
    "kpa": ("pressure", "kPa", 1), "mpa": ("pressure", "kPa", 1000), "bar": ("pressure", "kPa", 100), "bars": ("pressure", "kPa", 100), "psi": ("pressure", "kPa", 6.894757293168),
}


def _normal(text: str) -> str:
    result = str(text).replace("\u00a0", " ").replace("−", "-").replace("‐", "-").replace("‑", "-")
    for glyph, fraction in {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}.items():
        result = result.replace(glyph, " " + fraction)
    return result


def _number(text: str) -> float:
    text = text.strip().replace(" ", "")
    if "," in text:
        text = text.replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text) else text.replace(",", ".")
    return float(text)


def _tidy(value: float) -> int | float:
    rounded = round(value, 9)
    return int(rounded) if rounded == int(rounded) else rounded


def _union(boxes: list[list[float]]) -> list[float]:
    return [round(min(box[0] for box in boxes), 3), round(min(box[1] for box in boxes), 3),
            round(max(box[2] for box in boxes), 3), round(max(box[3] for box in boxes), 3)]


def _valid_box(box) -> bool:
    return isinstance(box, (tuple, list)) and len(box) == 4 and all(isinstance(value, (float, int)) and math.isfinite(value) for value in box) and box[2] >= box[0] and box[3] >= box[1]


def _rows(lines: list[dict], layout: bool) -> list[dict]:
    cells = [dict(line, text=_normal(line["text"])) for line in lines if isinstance(line, dict) and isinstance(line.get("text"), str) and line["text"].strip() and _valid_box(line.get("bbox"))]
    for cell in cells:
        cell["display_bbox"] = cell["bbox"]
        cell["bbox"] = cell.get("reading_bbox", cell["bbox"])
        cell["words"] = [dict(word, display_bbox=word["bbox"], bbox=word.get("reading_bbox", word["bbox"])) for word in cell.get("words", [])]
    cells.sort(key=lambda line: ((line["bbox"][1] + line["bbox"][3]) / 2, line["bbox"][0]))
    groups: list[list[dict]] = []
    for cell in cells:
        if layout and groups:
            previous = groups[-1]
            center = (cell["bbox"][1] + cell["bbox"][3]) / 2
            reference = median((item["bbox"][1] + item["bbox"][3]) / 2 for item in previous)
            tolerance = max(2.0, min(cell["bbox"][3] - cell["bbox"][1], median(item["bbox"][3] - item["bbox"][1] for item in previous)) * .4)
            if abs(center - reference) <= tolerance:
                previous.append(cell)
                continue
        groups.append([cell])
    result = []
    for group in groups:
        group.sort(key=lambda cell: cell["bbox"][0])
        offset = 0
        text = ""
        for cell in group:
            cell["start"] = offset
            text += (" " if text else "") + cell["text"]
            cell["start"] = len(text) - len(cell["text"])
            cell["end"] = len(text)
            offset = len(text) + 1
        result.append({"text": text, "bbox": _union([cell["bbox"] for cell in group]), "display_bbox": _union([cell["display_bbox"] for cell in group]), "cells": group})
    return result


def _span_box(row: dict, start: int, end: int, display=False) -> list[float]:
    boxes = []
    for cell in row["cells"]:
        if start >= cell["end"] or end <= cell["start"]:
            continue
        local_start, local_end = max(0, start - cell["start"]), min(len(cell["text"]), end - cell["start"])
        word_boxes = []
        # Native word positions improve header/column association over a text
        # width estimate. OCR has polygon geometry at the detected-line level.
        cursor = 0
        for word in cell.get("words", []):
            at = cell["text"].find(word["text"], cursor)
            if at >= 0:
                if at < local_end and at + len(word["text"]) > local_start and _valid_box(word.get("bbox")):
                    word_boxes.append(word.get("display_bbox", word["bbox"]) if display else word["bbox"])
                cursor = at + len(word["text"])
        if word_boxes:
            boxes.append(_union(word_boxes))
        else:
            box = cell.get("display_bbox", cell["bbox"]) if display else cell["bbox"]
            if display and box != cell["bbox"]:
                boxes.append(box)
                continue
            width = box[2] - box[0]
            denominator = max(1, len(cell["text"]))
            boxes.append([box[0] + width * local_start / denominator, box[1], box[0] + width * local_end / denominator, box[3]])
    return _union(boxes) if boxes else row["bbox"]


def _model_mentions(row: dict, models: list[str]) -> list[dict]:
    found = []
    for model in models:
        for match in re.finditer(r"(?<![\w-])" + re.escape(_normal(model)) + r"(?![\w-])", row["text"], re.I):
            if model.isdigit() and _LABEL.search(row["text"]) and not re.search(r"\bmodel\s*(?:no\.?\s*)?[:#]?\s*$", row["text"][:match.start()], re.I):
                continue
            bbox = _span_box(row, match.start(), match.end())
            found.append({"model": model, "start": match.start(), "end": match.end(), "bbox": bbox, "x": (bbox[0] + bbox[2]) / 2})
    return sorted(found, key=lambda item: item["x"])


def _qualifier(text: str) -> str:
    if re.search(r"\bno[ -]?load\b|\bidle\b", text, re.I):
        return "no_load"
    if re.search(r"\bpeak\b", text, re.I):
        return "peak"
    if re.search(r"\brated\b|\brating\b|\bnominal\b|\bcontinuous\b", text, re.I):
        return "rated"
    return "unspecified"


def _unit(raw: str | None):
    return _UNIT_MAP.get(re.sub(r"\s+", "", raw).lower()) if raw else None


def _compatible(attribute: str, unit: tuple | None) -> bool:
    return unit is not None and (unit[0] == attribute or unit[0] == "power" and attribute in {"input_power", "output_power"} or unit[0] == "input_voltage" and attribute == "output_voltage")


def _conditions(label: str, text: str) -> list[str]:
    conditions = []
    # These are not interchangeable facts. Preserve the restriction for release.
    for pattern in (r"\b(?:net|gross|shipping|dry|operating)\s+(?:weight|mass)\b", r"\b(?:fuel|oil|water|air\s+tank|tank|reservoir)\s+(?:capacity|volume)\b", r"\b(?:maximum|max\.?)\s+(?:speed|pressure)\b"):
        match = re.search(pattern, label, re.I)
        if match:
            conditions.append(match.group(0))
    match = re.search(r"\b(?:at\s+\d|when\b|with\b|without\b|less\s+(?:fuel|oil|water)|under\b|for\s+(?:\d|[A-Za-z]+\s+(?:operation|mode)))", text, re.I)
    if match:
        condition = text[match.start():].strip(" ;,.")
        condition = re.split(r"(?:\.{2,}|(?:\.\s+){2,})", condition)[0].strip()
        if re.match(r"less\s+(?:fuel|oil|water)", condition, re.I):
            condition = re.match(r"less\s+(?:fuel|oil|water)(?:\s*(?:,|and)\s*(?:fuel|oil|water))*", condition, re.I).group()
        conditions.append(condition[:240])
    if re.search(r"\bapprox(?:imately)?\b|\b(?:about|circa|around)\s*\d|[~≈]\s*\d", text, re.I):
        conditions.append("approximate value; tolerance unspecified")
    if re.search(r"\bspeed\b", label, re.I) and re.search(r"\bgoverned\b", text, re.I):
        conditions.append("governed speed")
    for match in re.finditer(r"\b\d+(?:\.\d+)?\s*(?:percent\s+power\s+factor|[%-]\s*power\s+factor|[ -]phase)\b", text, re.I):
        conditions.append(match.group()[:240])
    return list(dict.fromkeys(conditions))


def _continued_rows(rows: list[dict]) -> list[dict]:
    """Join visibly indented wrapped specification values, at most four rows."""
    result = []
    index = 0
    while index < len(rows):
        row = rows[index]
        index += 1
        if _LABEL.search(row["text"]):
            original_left = row["bbox"][0]
            for _ in range(3):
                if index >= len(rows):
                    break
                following = rows[index]
                gap = following["bbox"][1] - row["bbox"][3]
                height = following["bbox"][3] - following["bbox"][1]
                wrapped = row["text"].rstrip().endswith((",", "or", "percent", "(")) or re.search(r"generator\s+output", row["text"], re.I)
                if not wrapped or _LABEL.search(following["text"]) or following["bbox"][0] < original_left + 30 or gap > max(4, height * .65) or gap < -height * .5:
                    break
                shift = len(row["text"]) + 1
                row = {"text": row["text"] + " " + following["text"], "bbox": _union([row["bbox"], following["bbox"]]),
                       "display_bbox": _union([row["display_bbox"], following["display_bbox"]]),
                       "cells": row["cells"] + [dict(cell, start=cell["start"] + shift, end=cell["end"] + shift) for cell in following["cells"]]}
                index += 1
        result.append(row)
    return result


def _footnotes(rows: list[dict]) -> dict[str, dict]:
    notes = {}
    for row in rows:
        match = re.match(r"^\s*([*†‡]{1,2})\s*(\S.+)$", row["text"])
        if match:
            # Repeated markers are ambiguous, not globally interchangeable.
            marker = match.group(1)
            notes[marker] = None if marker in notes else row
    return {key: row for key, row in notes.items() if row is not None}


def _value_candidates(row: dict, label_match, segment_end: int, models: list[str]) -> list[dict]:
    attribute = label_match.lastgroup
    segment_start = label_match.end()
    segment = row["text"][segment_start:segment_end]
    masked = segment
    for model in models:
        masked = re.sub(r"(?<!\w)" + re.escape(_normal(model)) + r"(?!\w)", lambda match: " " * len(match.group()), masked, flags=re.I)
    unit_match = _PAREN_UNIT.search(segment[:24])
    default = _unit(unit_match.group("unit")) if unit_match else ("horsepower", "hp", 1) if attribute == "horsepower" else None
    result = []
    for match in _VALUE.finditer(masked):
        if re.search(r"(?:\bat|@)\s*$", masked[:match.start()], re.I):
            continue
        if re.search(r"\d\s*/\s*$", masked[:match.start()]) or re.match(r"\s*/\s*\d", masked[match.end():]):
            continue
        first_unit, second_unit = _unit(match.group("unit1")), _unit(match.group("unit2"))
        chosen = second_unit or first_unit or default
        value_attribute = attribute
        if chosen and attribute == "output_power" and re.search(r"generator\s+output", label_match.group(), re.I):
            if chosen[0] == "input_voltage":
                value_attribute = "output_voltage"
            elif chosen[0] == "frequency":
                value_attribute = "frequency"
        if not _compatible(value_attribute, chosen):
            continue
        if first_unit and second_unit and first_unit[1] != second_unit[1]:
            continue
        if not first_unit and not second_unit:
            remainder = masked[match.end():].lstrip()
            # Never silently replace an unknown explicit unit by header units.
            if remainder and (re.match(r"^[°%a-zA-Z]", remainder) and not re.match(r"^(?:at|when|with|without|under|for|and|to)\b", remainder, re.I)):
                continue
        try:
            first = _number(match.group("first")) * (first_unit or chosen)[2]
            second = _number(match.group("second")) * (second_unit or chosen)[2] if match.group("second") else None
        except ValueError:
            continue
        if not math.isfinite(first) or second is not None and not math.isfinite(second):
            continue
        separator = match.group("sep")
        tolerance = None
        value_max = None
        value = _tidy(first)
        if second is not None:
            if separator in {"±", "+/-", "+ / -"} or separator and "+" in separator:
                if second < 0:
                    continue
                if re.match(r"\s*%", masked[match.end():]):
                    if second_unit:
                        continue
                    second = abs(first) * _number(match.group("second")) / 100
                tolerance = {"minus": _tidy(second), "plus": _tidy(second), "unit": chosen[1]}
            elif separator == "/":
                # A discrete dual rating is not a continuous range.
                value = f"{_tidy(first)}/{_tidy(second)}"
            else:
                if second < first:
                    continue
                value_max = _tidy(second)
        start, end = segment_start + match.start(), segment_start + match.end()
        bbox = _span_box(row, start, end)
        result.append({"attribute": value_attribute, "value": value, "value_max": value_max, "unit": chosen[1], "tolerance": tolerance,
                       "raw_value": row["text"][start:end].strip(), "bbox": bbox,
                       "display_bbox": _span_box(row, start, end, display=True),
                       "x": (bbox[0] + bbox[2]) / 2, "marker": match.group("marker"), "start": start, "end": end})
    # Prose often puts a dimensional word after its value: '5.25 horsepower'.
    # Recognize only that immediately adjacent number; never the later rpm in
    # 'horsepower at 2200 revolutions per minute'.
    if attribute == "horsepower":
        prefix = row["text"][:label_match.start()]
        preceding = re.search(rf"(?<![\w.])(?P<number>(?:\d+\s+)?\d+/\d+|{_NUM})\s*-?\s*$", prefix)
        if preceding:
            raw = preceding.group("number")
            if "/" in raw:
                pieces = raw.split()
                numerator, denominator = pieces[-1].split("/")
                if float(denominator) == 0:
                    return result
                value = (float(pieces[0]) if len(pieces) > 1 else 0) + float(numerator) / float(denominator)
            else:
                value = _number(raw)
            start, end = preceding.start("number"), label_match.end()
            box = _span_box(row, start, end)
            ambiguous = "/" in raw and len(raw.split()) == 1 and float(numerator) >= float(denominator)
            result.append({"attribute": attribute, "value": raw if ambiguous else _tidy(value), "value_max": None, "unit": "hp", "tolerance": None,
                           "raw_value": row["text"][start:end], "bbox": box, "display_bbox": _span_box(row, start, end, display=True),
                           "ambiguous_fraction": ambiguous,
                           "x": (box[0] + box[2]) / 2, "marker": None, "start": start, "end": end})
    if len(models) == 1 and len(result) > 1 and all(not re.search(_UNIT, item["raw_value"], re.I) for item in result):
        return []  # e.g. 'Weight (kg): 1 234' is ambiguous, not two weights.
    return result


def _explicit_model_prose(page: dict, rows: list[dict], document: dict, models: list[str], method: str) -> list[dict]:
    """Resolve unit-bearing prose only with an exact local model and subject.

    No fuzzy identifier repair: corrupted HE/HR identifiers must be re-OCRed or
    reviewed against pixels. Bounded wrapped sentences retain original geometry.
    """
    assertions = []
    for index, initial in enumerate(rows):
        if not re.search(r"\bmodel\b", initial["text"], re.I):
            continue
        row = initial
        if method == "layout":
            for following in rows[index + 1:index + 7]:
                # Stop at a completed sentence after the model designation.
                model_at = re.search(r"\bmodel\b", row["text"], re.I).end()
                if re.search(r"[.!?]\s*$", row["text"][model_at:]):
                    break
                height = following["bbox"][3] - following["bbox"][1]
                if following["bbox"][1] - row["bbox"][3] > height or re.match(r"^\s*\(\d+\)", following["text"]):
                    break
                separator = "" if row["text"].endswith("-") else " "
                shift = len(row["text"]) + len(separator)
                row = {"text": row["text"] + separator + following["text"], "bbox": _union([row["bbox"], following["bbox"]]),
                       "display_bbox": _union([row["display_bbox"], following["display_bbox"]]),
                       "cells": row["cells"] + [dict(cell, start=cell["start"] + shift, end=cell["end"] + shift) for cell in following["cells"]]}
        mentions = _model_mentions(row, models)
        if len({item["model"] for item in mentions}) != 1 or _LABEL.search(row["text"]):
            continue
        mention = mentions[0]
        before = row["text"][:mention["start"]]
        if not re.search(r"\bmodel\s*(?:no\.?\s*)?$", before, re.I):
            continue
        subjects = list(re.finditer(r"\b(generator|engine)\b", before, re.I))
        role = subjects[-1].group(1).lower() if subjects else document.get("model_categories", {}).get(mention["model"])
        if role not in {"generator", "engine"}:
            continue
        attribute = "output_power" if role == "generator" else "speed"
        class ProseLabel:
            lastgroup = attribute
            def end(self):
                return mention["end"]
            def group(self):
                return "generator output" if role == "generator" else "speed"
        for candidate in _value_candidates(row, ProseLabel(), len(row["text"]), models):
            conditions = []
            if role == "generator" and re.search(r"\bd[ -]?c\b|\bdirect.current\b", row["text"], re.I):
                conditions.append("direct-current output")
            evidence = {"page": page["page_number"], "bbox": _union([_span_box(row, mention["start"], mention["end"], display=True), candidate["display_bbox"]]), "text": row["text"]}
            assertion = {"doc_id": document["doc_id"], "model": mention["model"], "variant": None, "attribute": candidate["attribute"],
                         "value": candidate["value"], "value_max": candidate["value_max"], "unit": candidate["unit"], "qualifier": _qualifier(row["text"]),
                         "evidence": evidence, "status": "candidate", "confidence": .75, "method": (EXTRACTION_VERSION if method == "layout" else "line-rules-2") + "-explicit-model-prose", "raw_value": candidate["raw_value"]}
            if conditions:
                assertion["conditions"] = conditions
            assertion["assertion_id"] = "a-" + hashlib.sha256(json.dumps(assertion, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()[:24]
            assertions.append(assertion)
    return assertions


def extract_assertions(pages: list[dict], document: dict, method: str = "layout") -> list[dict]:
    """Extract candidates, never approved facts. ``method='baseline'`` is the
    independently measurable line-only comparator; default uses row geometry.
    Unresolved identity or column association results in abstention.
    """
    if method not in {"layout", "baseline"}:
        raise ValueError("extraction method must be layout or baseline")
    models = list(dict.fromkeys(str(model).strip() for model in document.get("models", []) if str(model).strip()))
    if not models:
        return []
    assertions = []
    prior_header = None
    prior_page_model = None
    for page in pages:
        if page.get("status") != "ok":
            continue
        rows = _rows(page.get("lines", []), method == "layout")
        if method == "layout":
            rows = _continued_rows(rows)
        notes = _footnotes(rows)
        header = None
        section_model = None
        section_bottom = None
        unknown_component = False
        page_model = None
        page_model_row = None
        page_model_number = page["page_number"]
        observed_product_header = False
        for heading in rows[:6]:
            mentions = _model_mentions(heading, models)
            if len(mentions) == 1 and re.fullmatch(r"\s*(?:GENERATING\s+UNITS?|GENERATOR|ENGINE|SAW|DRILL|COMPRESSOR|APPLIANCE)\s+" + re.escape(_normal(mentions[0]["model"])) + r"\s*", heading["text"], re.I):
                page_model, page_model_row = mentions[0]["model"], heading
                observed_product_header = True
        if not page_model and prior_page_model and prior_page_model[2] == page["page_number"] - 1:
            page_model, page_model_row, page_model_number = prior_page_model
        # Reuse only an explicitly continued table at matching page width.
        if method == "layout" and prior_header and page.get("width") == prior_header.get("width") and any(re.search(r"\b(?:specifications?|technical\s+data|table)\b.*\bcontinued\b", row["text"], re.I) for row in rows[:3]):
            header = prior_header
        for row in rows:
            if re.match(r"^\s*[*†‡]", row["text"]):
                continue
            mentions = _model_mentions(row, models)
            labels = list(_LABEL.finditer(row["text"]))
            unique = list(dict.fromkeys(item["model"] for item in mentions))
            unknown_mentions = [match.group(1) for match in re.finditer(r"\bmodel(?:\s+no\.?)?[\s.:#]*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*|\d{3,})\b", row["text"], re.I)
                                if match.group(1).upper() not in {model.upper() for model in models} and re.search(r"\d", match.group(1))]
            if unknown_mentions:
                unknown_component = True
                header = None
                section_model = None
                continue
            header_remainder = row["text"]
            for mention in sorted(mentions, key=lambda item: item["start"], reverse=True):
                header_remainder = header_remainder[:mention["start"]] + " " * (mention["end"] - mention["start"]) + header_remainder[mention["end"]:]
            header_remainder = re.sub(r"\b(?:models?|types?|no|specifications?|technical|data)\b", "", header_remainder, flags=re.I)
            header_only = sum(character.isalnum() for character in header_remainder) <= 3
            if method == "layout" and len(unique) >= 2 and not labels and len(mentions) == len(unique) and header_only:
                centers = [item["x"] for item in mentions]
                if all(right - left >= 12 for left, right in zip(centers, centers[1:])):
                    header = {"columns": mentions, "row": row, "page": page["page_number"], "width": page.get("width")}
                    section_model = None
                    unknown_component = False
                continue
            explicit_section = re.search(r"^\s*make\s+and\s+model\b", row["text"], re.I) or re.match(r"^\s*\([^)]*\bmodel\b[^)]*\)\s*$", row["text"], re.I)
            if len(unique) == 1 and not labels and (re.fullmatch(r"\s*(?:model\s*[:#]?\s*)?" + re.escape(_normal(unique[0])) + r"\s*", row["text"], re.I) or len(row["text"]) < 160 and explicit_section):
                section_model, section_bottom = unique[0], row["bbox"][3]
                unknown_component = False
                header = None
                continue
            for position, label in enumerate(labels):
                preceding = row["text"][max(0, label.start() - 30):label.start()]
                if label.lastgroup in {"input_voltage", "input_current"} and re.search(r"\b(?:output|secondary)\s*$", preceding, re.I):
                    continue
                if label.lastgroup == "input_current" and not re.search(r"\b(?:input|supply)\b", label.group(), re.I):
                    continue
                if label.lastgroup == "input_voltage" and document.get("category", "").lower() in {"generator", "generator set", "power supply"} and not re.search(r"\b(?:input|supply|mains)\b", label.group(), re.I):
                    continue
                end = labels[position + 1].start() if position + 1 < len(labels) else len(row["text"])
                candidates = _value_candidates(row, label, end, models)
                if not candidates:
                    continue
                # A vertical label->value pair is supported only when the next
                # line is explicitly paired in the same geometric row. Broad
                # nearest-neighbor guessing would cross unrelated columns.
                for candidate in candidates:
                    selected = None
                    context = []
                    page_scope = False
                    if len(unique) == 1:
                        selected = unique[0]
                    elif len(models) == 1:
                        if not unknown_component:
                            selected = models[0]
                    elif method == "layout" and header and not unique:
                        columns = header["columns"]
                        nearest = sorted(columns, key=lambda column: abs(column["x"] - candidate["x"]))
                        distances = [abs(column["x"] - candidate["x"]) for column in nearest]
                        spacing = min(abs(nearest[0]["x"] - column["x"]) for column in columns if column is not nearest[0])
                        if distances[0] <= spacing * .42 and (len(distances) < 2 or distances[1] - distances[0] >= spacing * .2):
                            selected = nearest[0]["model"]
                            context = [{"page": header["page"], "bbox": header["row"]["display_bbox"], "text": header["row"]["text"]}]
                    elif section_model and row["bbox"][1] - section_bottom <= 220:
                        selected = section_model
                    elif page_model and not unknown_component:
                        selected = page_model
                        page_scope = True
                        context = [{"page": page_model_number, "bbox": page_model_row["display_bbox"], "text": page_model_row["text"]}]
                    if selected is None:
                        continue
                    model_category = document.get("model_categories", {}).get(selected, document.get("category", "")).lower()
                    # A single-model document also contains procedures, shipping
                    # examples and components. Only a direct specification label
                    # or an explicit model association justifies fallback scope.
                    if (len(models) == 1 and not unique) or page_scope:
                        prefix = row["text"][:label.start()].strip()
                        direct_field = bool(re.fullmatch(r"(?:(?:[a-z]|\d+)[.)]\s*)?(?:(?:total|rated|nominal|maximum|minimum|approximate)\s*)?", prefix, re.I))
                        engine_prose = candidate["attribute"] == "horsepower" and model_category == "engine" and bool(re.search(r"\bengine\b", row["text"], re.I))
                        if not direct_field and not engine_prose:
                            continue
                        if re.search(r"\bare\s+indicated\b|\bis\s+indicated\b|\b(?:keep|adjust|disconnect|reconnect)\b", row["text"], re.I):
                            continue
                    if candidate["attribute"] == "weight":
                        subject = re.match(r"\s+of\s+(?:the\s+)?([a-z]+)", row["text"][label.end():], re.I)
                        if subject and subject.group(1).lower() not in {"unit", "machine", "tool", "product", model_category.split(" ")[0]}:
                            continue
                    if candidate["attribute"] == "speed" and re.search(r"\b(?:vary|variation|difference|fluctuation|increase\s+by|decrease\s+by)\b", row["text"], re.I):
                        continue
                    # Two value cells mapped to the same column usually denote
                    # ambiguous layout, unless explicitly separated ratings.
                    if header and len(candidates) > len(header["columns"]) and len(models) > 1:
                        continue
                    label_text = label.group()
                    segment = row["text"][label.start():end]
                    conditions = _conditions(label_text, segment)
                    marker = candidate["marker"]
                    label_marker = re.match(r"\s*([*†‡]{1,2})", row["text"][label.end():])
                    if not marker and label_marker:
                        marker = label_marker.group(1)
                    qualifier_text = segment
                    if marker:
                        if marker in notes:
                            note = notes[marker]
                            note_text = note["text"].lstrip("*†‡ ")[:240]
                            conditions.append(note_text)
                            qualifier_text += " " + note_text
                            context.append({"page": page["page_number"], "bbox": note["display_bbox"], "text": note["text"]})
                        else:
                            conditions.append(f"Unresolved footnote marker {marker}")
                    evidence = {"page": page["page_number"], "bbox": _union([_span_box(row, label.start(), label.end(), display=True), candidate["display_bbox"]]), "text": row["text"]}
                    if context:
                        evidence["context"] = context
                    assertion = {"doc_id": document["doc_id"], "model": selected, "variant": None,
                                 "attribute": candidate["attribute"], "value": candidate["value"], "value_max": candidate["value_max"],
                                 "unit": candidate["unit"], "qualifier": _qualifier(qualifier_text), "evidence": evidence,
                                 "status": "candidate", "confidence": .90 if method == "layout" else .80,
                                 "method": EXTRACTION_VERSION if method == "layout" else "line-rules-2",
                                 "raw_value": candidate["raw_value"]}
                    if label.lastgroup == "output_power" and re.search(r"generator\s+output", label.group(), re.I):
                        separators = list(re.finditer(r"\bor\b", row["text"][label.end():end], re.I))
                        voltages = [value for value in candidates if value["attribute"] == "output_voltage"]
                        if separators and len({str(value["value"]) for value in voltages}) > 1:
                            boundaries = [label.end()] + [label.end() + separator.start() for separator in separators] + [end + 1]
                            for left, right in zip(boundaries, boundaries[1:]):
                                branch_voltages = [value for value in voltages if left <= value["start"] < right]
                                if left <= candidate["start"] < right and len(branch_voltages) == 1:
                                    assertion["variant"] = f"output configuration: {branch_voltages[0]['value']} V"
                    if conditions:
                        assertion["conditions"] = list(dict.fromkeys(conditions))
                    if candidate["tolerance"]:
                        assertion["tolerance"] = candidate["tolerance"]
                    if candidate.get("ambiguous_fraction"):
                        assertion.setdefault("conditions", []).append("unresolved compact fraction; confirm mixed-number spacing against source")
                        assertion["confidence"] = .50
                    if any(cell.get("confidence", 1) < .8 for cell in row["cells"]):
                        assertion["confidence"] = .60
                    # Stable against ordering, and bound to source evidence and
                    # complete interpretation. Review decisions live elsewhere.
                    digest = hashlib.sha256(json.dumps(assertion, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()[:24]
                    assertion["assertion_id"] = "a-" + digest
                    assertions.append(assertion)
        assertions.extend(_explicit_model_prose(page, _rows(page.get("lines", []), method == "layout"), document, models, method))
        prior_header = header if method == "layout" else None
        prior_page_model = (page_model, page_model_row, page["page_number"]) if observed_product_header else None
    unique_assertions = {assertion["assertion_id"]: assertion for assertion in assertions}
    return list(unique_assertions.values())
