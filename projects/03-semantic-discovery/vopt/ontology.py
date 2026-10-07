"""Small, inspectable technical vocabulary; no downloads or learned model assets.

Conversions preserve the attribute's physical meaning. In particular electrical
input watts are never converted into motor horsepower or mechanical output.
"""
from __future__ import annotations

import re
import unicodedata


ATTRIBUTES = {
    "input_voltage": ("V", ("input voltage", "operating voltage", "supply voltage")),
    "output_voltage": ("V", ("output voltage", "generated voltage", "generator voltage")),
    "frequency": ("Hz", ("line frequency", "frequency", "hertz")),
    "input_current": ("A", ("input current", "current draw", "amperage", "current", "amps")),
    "input_power": ("W", ("electrical input power", "electrical input", "power consumption", "power draw", "input power", "wattage")),
    "output_power": ("W", ("mechanical output power", "mechanical power", "shaft power", "output power")),
    "horsepower": ("hp", ("engine horsepower", "motor horsepower", "horse power", "horsepower", "hp")),
    "speed": ("rpm", ("rotational speed", "rotation speed", "rotations per minute", "revolutions per minute", "speed", "rpm")),
    "weight": ("kg", ("tool weight", "machine weight", "weight", "mass", "weighs", "weighing")),
    "blade_diameter": ("mm", ("blade diameter", "blade size")),
    "displacement": ("cm3", ("engine displacement", "displacement", "cubic capacity")),
    "capacity": ("L", ("tank capacity", "tank volume", "capacity", "volume")),
    "pressure": ("kPa", ("working pressure", "operating pressure", "air pressure", "pressure")),
}

CATEGORIES = {
    "drill": ("drill", "drills", "drilling machine", "drilling machines"),
    "saw": ("saw", "saws", "sawing machine", "sawing machines"),
    "compressor": ("compressor", "compressors", "air compressor", "air compressors"),
    "sewing machine": ("sewing machine", "sewing machines"),
    "appliance": ("appliance", "appliances"),
    "grinder": ("grinder", "grinders", "grinding machine", "grinding machines"),
    "sander": ("sander", "sanders"),
    "lathe": ("lathe", "lathes"),
    "vacuum": ("vacuum", "vacuums", "vacuum cleaner", "vacuum cleaners"),
    "washer": ("washer", "washers", "washing machine", "washing machines"),
    "refrigerator": ("refrigerator", "refrigerators", "fridge", "fridges"),
    "mixer": ("mixer", "mixers"),
    "generator": ("generator", "generators", "generating set", "generating sets"),
    "engine": ("engine", "engines", "motor", "motors"),
    "welder": ("welder", "welders", "welding machine", "welding machines"),
    "battery charger": ("battery charger", "battery chargers"),
    "pump": ("pump", "pumps"),
}

# alias: (canonical physical unit, multiplier). Context resolves cm3/L only
# through explicit attribute compatibility, never a guessed meaning of power.
UNITS = {
    "v": ("V", 1.0), "volt": ("V", 1.0), "volts": ("V", 1.0), "kv": ("V", 1000.0),
    "hz": ("Hz", 1.0), "hertz": ("Hz", 1.0), "khz": ("Hz", 1000.0),
    "a": ("A", 1.0), "amp": ("A", 1.0), "amps": ("A", 1.0), "ampere": ("A", 1.0), "amperes": ("A", 1.0), "ma": ("A", 0.001),
    "w": ("W", 1.0), "watt": ("W", 1.0), "watts": ("W", 1.0), "kw": ("W", 1000.0), "kilowatt": ("W", 1000.0), "kilowatts": ("W", 1000.0),
    "hp": ("hp", 1.0), "horsepower": ("hp", 1.0),
    "rpm": ("rpm", 1.0), "r/min": ("rpm", 1.0), "rev/min": ("rpm", 1.0),
    "kg": ("kg", 1.0), "kilogram": ("kg", 1.0), "kilograms": ("kg", 1.0),
    "g": ("kg", 0.001), "gram": ("kg", 0.001), "grams": ("kg", 0.001),
    "lb": ("kg", 0.45359237), "lbs": ("kg", 0.45359237), "pound": ("kg", 0.45359237), "pounds": ("kg", 0.45359237), "oz": ("kg", 0.028349523125),
    "mm": ("mm", 1.0), "millimeter": ("mm", 1.0), "millimeters": ("mm", 1.0), "cm": ("mm", 10.0), "m": ("mm", 1000.0),
    "in": ("mm", 25.4), "inch": ("mm", 25.4), "inches": ("mm", 25.4),
    "cc": ("cm3", 1.0), "cm3": ("cm3", 1.0), "cm^3": ("cm3", 1.0), "ml": ("cm3", 1.0),
    "l": ("L", 1.0), "liter": ("L", 1.0), "liters": ("L", 1.0), "litre": ("L", 1.0), "litres": ("L", 1.0),
    "pa": ("kPa", 0.001), "kpa": ("kPa", 1.0), "mpa": ("kPa", 1000.0), "bar": ("kPa", 100.0), "psi": ("kPa", 6.894757293168),
}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).casefold().replace("\u2011", "-").replace("\u2013", "-").strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+(?:[-.][\w]+)*", normalize(text))


def phrase_pattern(phrase: str) -> str:
    return r"(?<!\w)" + re.escape(normalize(phrase)).replace(r"\ ", r"\s+") + r"(?!\w)"


def unit_value(value: float, unit: str, attribute: str | None = None) -> tuple[float, str]:
    canonical, multiplier = UNITS[normalize(unit)]
    if attribute is not None:
        expected = ATTRIBUTES[attribute][0]
        # Volume units are interchangeable only when the requested attribute is explicit.
        if canonical == "cm3" and expected == "L":
            multiplier /= 1000.0
            canonical = "L"
        elif canonical == "L" and expected == "cm3":
            multiplier *= 1000.0
            canonical = "cm3"
        if expected != canonical:
            raise ValueError(f"Unit {unit!r} is incompatible with {attribute}; use {expected}.")
    return float(value) * multiplier, canonical


def attributes_for_unit(unit: str) -> list[str]:
    canonical = UNITS[normalize(unit)][0]
    return [key for key, (target, _) in ATTRIBUTES.items() if canonical == target]


def semantic_tokens(text: str) -> list[str]:
    """Replace longest known phrases by concepts before ordinary tokenization.

    This is an ontology expansion baseline, not pretrained embeddings, a language
    model, or a claim of unconstrained natural-language understanding.
    """
    value = normalize(text)
    phrases = [(alias, "attribute_" + key) for key, (_, aliases) in ATTRIBUTES.items() for alias in aliases]
    phrases += [(alias, "category_" + key.replace(" ", "_")) for key, aliases in CATEGORIES.items() for alias in aliases]
    for alias, concept in sorted(phrases, key=lambda pair: len(pair[0]), reverse=True):
        value = re.sub(phrase_pattern(alias), concept, value)
    return tokens(value)
