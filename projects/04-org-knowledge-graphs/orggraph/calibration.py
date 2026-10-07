"""Explicit offline calibration utilities; never invoked by inference automatically.

A fitted mapping is not a validation claim. Independent evaluation returns
diagnostics, and does not decide whether a predeclared research gate passed.
"""
from __future__ import annotations

import hashlib
import json
import math


_SCOPE_FIELDS = ("corpus_id", "model_id", "relation", "population", "policy_id", "window", "label_provenance")


def _scope(scope: dict) -> dict:
    missing = [field for field in _SCOPE_FIELDS if field not in scope]
    if missing:
        raise ValueError(f"Calibration scope missing: {', '.join(missing)}")
    if scope["population"] not in ("candidate", "selected"):
        raise ValueError("population must be candidate or selected")
    if any(not scope[field] for field in _SCOPE_FIELDS if field != "window"):
        raise ValueError("Calibration scope identifiers and label provenance cannot be empty")
    # Copy through JSON ensures artifacts contain ordinary serializable values.
    return json.loads(json.dumps({field: scope[field] for field in _SCOPE_FIELDS}, sort_keys=True))


def _samples(records: list[dict]) -> tuple[list[float], list[int], list[str]]:
    scores, labels, keys = [], [], []
    for record in records:
        if "label" not in record or record["label"] not in (0, 1):
            raise ValueError("Each record requires an explicit binary label; missing labels are not negatives")
        if not record.get("subject") or not record.get("object"):
            raise ValueError("Each record requires subject and object IDs")
        score = float(record["raw_score"])
        if not math.isfinite(score):
            raise ValueError("raw_score must be finite")
        # Identity-based overlap detection cannot be bypassed by changing row IDs.
        key = hashlib.sha256(json.dumps([record["subject"], record["object"], record.get("valid_from"), record.get("valid_to")], separators=(",", ":")).encode()).hexdigest()
        scores.append(score)
        labels.append(int(record["label"]))
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate labeled relationship in split")
    return scores, labels, keys


def fit_calibrator(records: list[dict], *, scope: dict, split_id: str, training_relationship_keys: list[str] | None = None) -> dict:
    """Fit a regularized sigmoid on an explicitly supplied calibration split.

    Caller is responsible for an independently constructed split and audited
    label semantics. Supply training keys when available for overlap checking.
    """
    from sklearn.linear_model import LogisticRegression

    normalized_scope = _scope(scope)
    scores, labels, keys = _samples(records)
    if not split_id:
        raise ValueError("A named calibration split is required")
    if len(records) < 20 or len(set(labels)) < 2:
        raise ValueError("At least 20 explicitly labeled relationships and both classes are required")
    if set(keys) & set(training_relationship_keys or []):
        raise ValueError("Calibration split overlaps model training relationships")
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=17)
    model.fit([[score] for score in scores], labels)
    artifact = {
        "method": "regularized_sigmoid", "version": 1,
        "coefficient": float(model.coef_[0][0]), "intercept": float(model.intercept_[0]),
        "scope": normalized_scope, "split_id": split_id,
        "relationship_keys": sorted(keys), "fit_count": len(records), "fit_positives": sum(labels),
        "status": "fitted_unvalidated", "regularization_C": 1.0,
        "training_overlap_checked": training_relationship_keys is not None,
        "limitations": ["Fitting does not establish calibration quality.", "Population, window, model, or selection policy changes invalidate applicability.", "Unlabeled relationships were not treated as negatives.", "Real-world validity requires independently audited real labels and predeclared acceptance criteria."],
    }
    digest = hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    artifact["id"] = f"calibrator_{digest[:20]}"
    return artifact


def _probability(artifact: dict, score: float) -> float:
    z = float(artifact["coefficient"]) * score + float(artifact["intercept"])
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def apply_calibrator(artifact: dict, records: list[dict], *, scope: dict) -> list[dict]:
    """Return new probability fields only for an exactly matching source scope.

    Candidate mappings never fill selected_probability; human/source assertions
    never inherit model probability. Cross-corpus estimates stay unavailable.
    """
    same_scope = _scope(scope) == artifact["scope"]
    result = []
    for record in records:
        item = {**record, "candidate_probability": None, "selected_probability": None}
        if record.get("origin", "model") != "model":
            item["calibration_status"] = "not_a_model_assertion"
        elif not same_scope:
            item["calibration_status"] = "outside_calibration_scope"
        elif record.get("relation", artifact["scope"]["relation"]) != artifact["scope"]["relation"]:
            item["calibration_status"] = "outside_calibration_scope"
        elif record.get("raw_score") is None:
            item["calibration_status"] = "score_unavailable"
        else:
            score = float(record["raw_score"])
            if not math.isfinite(score):
                raise ValueError("raw_score must be finite")
            field = f"{artifact['scope']['population']}_probability"
            item[field] = _probability(artifact, score)
            item["calibration_status"] = "fitted_unvalidated"
            item["calibration_scope"] = artifact["scope"]
            item["calibrator_id"] = artifact["id"]
        result.append(item)
    return result


def evaluate_calibrator(artifact: dict, records: list[dict], *, scope: dict, split_id: str, bins: int = 10) -> dict:
    """Evaluate untouched labeled edges; reject overlap with the fitting split."""
    if _scope(scope) != artifact["scope"]:
        raise ValueError("Evaluation scope must match the fitted calibration scope")
    if not split_id or split_id == artifact["split_id"]:
        raise ValueError("Evaluation requires a separate named split")
    scores, labels, keys = _samples(records)
    if not records or not isinstance(bins, int) or not 1 <= bins <= 100:
        raise ValueError("Evaluation needs records and between 1 and 100 bins")
    if set(keys) & set(artifact["relationship_keys"]):
        raise ValueError("Evaluation relationships overlap calibration fitting data")
    probabilities = [_probability(artifact, score) for score in scores]
    reliability = []
    for index in range(bins):
        indices = [idx for idx, probability in enumerate(probabilities) if min(bins - 1, int(probability * bins)) == index]
        count = len(indices)
        observed = sum(labels[idx] for idx in indices) / count if count else None
        predicted = sum(probabilities[idx] for idx in indices) / count if count else None
        # Wilson interval describes observed bin accuracy, not the model's edge uncertainty.
        interval = None
        if count:
            z = 1.96
            divisor = 1 + z * z / count
            center = (observed + z * z / (2 * count)) / divisor
            half = z * math.sqrt(observed * (1 - observed) / count + z * z / (4 * count * count)) / divisor
            interval = [max(0, center - half), min(1, center + half)]
        reliability.append({"lower": index / bins, "upper": (index + 1) / bins, "count": count, "mean_estimate": predicted, "observed_fraction": observed, "observed_fraction_wilson_95": interval})
    epsilon = 1e-15
    clipped = [max(epsilon, min(1 - epsilon, probability)) for probability in probabilities]
    return {
        "calibrator_id": artifact["id"], "split_id": split_id, "scope": artifact["scope"],
        "count": len(records), "positive_count": sum(labels),
        "brier_score": sum((p - y) ** 2 for p, y in zip(probabilities, labels)) / len(labels),
        "log_loss": -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(clipped, labels)) / len(labels),
        "expected_calibration_error": sum(item["count"] * abs(item["mean_estimate"] - item["observed_fraction"]) for item in reliability if item["count"]) / len(labels),
        "reliability": reliability, "acceptance": "not_assessed", "independent_relationships_verified": True,
        "limitations": ["Shared people, units, and time may still violate the intended independence design.", "Passing requires predeclared criteria and adequate real-data counts; diagnostics do not certify calibration.", "No target-domain or selected-population guarantee follows from candidate calibration."],
    }
