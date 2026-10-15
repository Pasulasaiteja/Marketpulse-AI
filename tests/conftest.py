import pytest

from marketpulse.mocks.context import MockContextBuilder
from marketpulse.mocks.explainer import MockExplainer
from marketpulse.mocks.extractor import MockExtractor
from marketpulse.mocks.fixtures import make_canonical_data
from marketpulse.mocks.forecaster import MockForecaster
from marketpulse.mocks.optimizer import MockOptimizer
from marketpulse.mocks.signals import MockSignalProvider

DESC = "Small shop near a school in Delhi, India. Paid on the 25th."


@pytest.fixture(scope="session")
def data():
    return make_canonical_data()


@pytest.fixture(scope="session")
def pipeline(data):
    """Run the whole mock pipeline once (pipeline order from the task file)."""
    sig = MockSignalProvider().get_signals(data, data.as_of)
    prof = MockExtractor().extract_profile(DESC)
    ctx = MockContextBuilder().build_context(prof, data.as_of, 14, sig)
    fc = MockForecaster().forecast(data, prof, ctx, 14, sig)
    plan = MockOptimizer().optimize(fc, data, 5000)
    exp = MockExplainer().explain(plan, fc, None, "en")
    return dict(signals=sig, profile=prof, context=ctx, forecast=fc, plan=plan, explanation=exp)
