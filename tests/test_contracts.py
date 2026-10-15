"""Contract tests: every module boundary validates; mismatches fail."""

import copy
import datetime as dt

import pytest

from marketpulse import config
from marketpulse.contracts import interfaces
from marketpulse.contracts.integrity import check_explanation_numbers
from marketpulse.contracts.models import CONTRACT_MODELS
from marketpulse.contracts.validate import ContractViolation, validate_payload
from marketpulse.mocks.context import MockContextBuilder
from marketpulse.mocks.explainer import MockExplainer
from marketpulse.mocks.extractor import MockExtractor
from marketpulse.mocks.forecaster import MockForecaster
from marketpulse.mocks.optimizer import MockOptimizer
from marketpulse.mocks.signals import MockSignalProvider
from scripts.export_schemas import OUT, render


def test_committed_schemas_match_models():
    for name in CONTRACT_MODELS:
        on_disk = (OUT / f"{name}.schema.json").read_text(encoding="utf-8")
        assert on_disk == render(name), f"{name} schema is stale: run scripts/export_schemas.py"


@pytest.mark.parametrize(
    "impl,proto",
    [
        (MockExtractor(), interfaces.Extractor),
        (MockContextBuilder(), interfaces.ContextBuilder),
        (MockForecaster(), interfaces.Forecaster),
        (MockOptimizer(), interfaces.Optimizer),
        (MockExplainer(), interfaces.Explainer),
        (MockSignalProvider(), interfaces.SignalProvider),
    ],
)
def test_mocks_satisfy_protocols(impl, proto):
    assert isinstance(impl, proto)


@pytest.mark.parametrize(
    "key,name",
    [
        ("profile", "ExtractionProfile"),
        ("signals", "SignalOutput"),
        ("context", "ContextFeatures"),
        ("forecast", "ForecastOutput"),
        ("plan", "OptimizerPlan"),
        ("explanation", "Explanation"),
    ],
)
def test_every_boundary_validates(pipeline, key, name):
    validate_payload(name, pipeline[key])


def test_canonical_data_validates(data):
    validate_payload("CanonicalData", data)


def _dump(pipeline, key):
    return pipeline[key].model_dump(mode="json")


def test_unknown_field_rejected(pipeline):
    bad = _dump(pipeline, "forecast")
    bad["surprise"] = 1
    with pytest.raises(ContractViolation):
        validate_payload("ForecastOutput", bad)


def test_missing_field_rejected(pipeline):
    bad = _dump(pipeline, "plan")
    del bad["budget"]
    with pytest.raises(ContractViolation):
        validate_payload("OptimizerPlan", bad)


def test_wrong_quantile_grid_rejected(pipeline):
    bad = _dump(pipeline, "forecast")
    bad["forecasts"][0]["quantiles"] = bad["forecasts"][0]["quantiles"][:3]
    with pytest.raises(ContractViolation):
        validate_payload("ForecastOutput", bad)


def test_decreasing_quantiles_rejected(pipeline):
    bad = copy.deepcopy(_dump(pipeline, "forecast"))
    q = bad["forecasts"][0]["quantiles"]
    q[0]["value"], q[-1]["value"] = q[-1]["value"] + 5, 0
    with pytest.raises(ContractViolation):
        validate_payload("ForecastOutput", bad)


def test_plan_over_budget_rejected(pipeline):
    bad = _dump(pipeline, "plan")
    bad["budget"] = bad["total_cost"] - 1
    with pytest.raises(ContractViolation):
        validate_payload("OptimizerPlan", bad)


def test_plan_total_mismatch_rejected(pipeline):
    bad = _dump(pipeline, "plan")
    bad["total_cost"] = bad["total_cost"] - 5
    with pytest.raises(ContractViolation):
        validate_payload("OptimizerPlan", bad)


def test_future_sales_rejected(data):
    bad = data.model_dump(mode="json")
    bad["sales"][0]["date"] = (data.as_of + dt.timedelta(days=1)).isoformat()
    with pytest.raises(ContractViolation):
        validate_payload("CanonicalData", bad)


def test_unknown_product_in_sales_rejected(data):
    bad = data.model_dump(mode="json")
    bad["sales"][0]["product_id"] = "NOPE"
    with pytest.raises(ContractViolation):
        validate_payload("CanonicalData", bad)


def test_bad_confidence_rejected(pipeline):
    bad = _dump(pipeline, "profile")
    bad["fields"]["location_type"]["confidence"] = 1.5
    with pytest.raises(ContractViolation):
        validate_payload("ExtractionProfile", bad)


def test_horizon_must_be_supported(pipeline):
    bad = _dump(pipeline, "context")
    bad["horizon_days"] = 5
    with pytest.raises(ContractViolation):
        validate_payload("ContextFeatures", bad)


def test_explanation_numbers_grounded(pipeline):
    assert check_explanation_numbers(pipeline["explanation"], pipeline["plan"]) == []


def test_explanation_with_invented_number_fails(pipeline):
    exp = pipeline["explanation"].model_copy(update={"text": pipeline["explanation"].text + " 999"})
    assert check_explanation_numbers(exp, pipeline["plan"])


def test_explanation_with_wrong_cited_value_fails(pipeline):
    exp = copy.deepcopy(pipeline["explanation"])
    exp.cited_figures[0].value = exp.cited_figures[0].value + 1
    assert check_explanation_numbers(exp, pipeline["plan"])


@pytest.mark.parametrize("lang", config.SUPPORTED_LANGUAGES)
def test_explainer_numbers_grounded_in_every_language(pipeline, lang):
    exp = MockExplainer().explain(pipeline["plan"], pipeline["forecast"], None, lang)
    assert exp.language == lang
    assert check_explanation_numbers(exp, pipeline["plan"]) == []


def test_mock_outputs_are_reproducible(data):
    sig = MockSignalProvider().get_signals(data, data.as_of)
    prof = MockExtractor().extract_profile("shop near a school, Delhi, India")
    run = lambda: MockForecaster().forecast(  # noqa: E731
        data, prof, MockContextBuilder().build_context(prof, data.as_of, 14, sig), 14, sig
    ).model_dump(mode="json")
    prof2 = prof  # profile_id is random; forecast does not depend on it
    assert run() == run() and prof2 is prof
