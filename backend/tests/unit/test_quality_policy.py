import pytest

from app.services.parsing.quality_policy import QualityOverrides, resolve_quality_policy


def test_policy_applies_profile_then_override() -> None:
    policy = resolve_quality_policy(
        "hybrid", "invoice", {"min_completeness": 0.99, "max_repairs": 1}
    )
    assert policy.thresholds.min_extraction_accuracy == pytest.approx(0.91)
    assert policy.thresholds.min_completeness == 0.99
    assert policy.thresholds.max_repairs == 1


def test_scanned_maximum_policy_is_stricter() -> None:
    policy = resolve_quality_policy("maximum_accuracy", "general_scanned")
    assert policy.thresholds.min_region_confidence == pytest.approx(0.93)
    assert policy.thresholds.min_completeness == 1.0


def test_overrides_are_bounded() -> None:
    with pytest.raises(ValueError):
        QualityOverrides(min_overall=1.1)
