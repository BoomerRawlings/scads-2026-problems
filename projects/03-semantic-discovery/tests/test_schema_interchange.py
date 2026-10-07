import copy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, ValidationError
from test_lifecycle import bundle


@pytest.fixture
def validator():
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/catalog.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("profile", ["coverage", "values"])
def test_actual_exports_satisfy_external_interchange_schema(tmp_path, validator, profile):
    b = bundle(tmp_path, profile)
    b["documents"][0]["model_categories"] = {"G1": "generator"}
    if profile == "values":
        b["assertions"][0].update(conditions=["at rated load"], tolerance={"minus": 50, "plus": 50, "unit": "W"})
    validator.validate(b)


def test_schema_prevents_content_fields_and_cross_profile_values(tmp_path, validator):
    b = bundle(tmp_path, "coverage")
    b["assertions"][0]["value"] = 30000
    with pytest.raises(ValidationError):
        validator.validate(b)
    del b["assertions"][0]["value"]
    b["documents"][0]["ocr_text"] = "SOURCE CONTENT"
    with pytest.raises(ValidationError):
        validator.validate(b)
