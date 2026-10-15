"""Test settings: no artificial "Ryde Support is typing" pause."""
import os

os.environ.setdefault("DEMO_TYPING_DELAY", "0")
# Tests are offline: never follow a developer's .env into a real model call (python-dotenv does not override this).
os.environ["LLM_MODE"] = "deterministic"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_cases():
    """Each test starts with no open cases (a ride has one case, so cases must not leak between tests)."""
    from app import case_store
    case_store.CASES.clear()
    yield


@pytest.fixture(autouse=True)
def _no_real_model_calls(monkeypatch):
    """Protect the free model quota: a test that reaches the real LLM client fails instead of making a request.
    Tests that exercise the Live AI path replace the client with a fake."""
    from app.llm import llm_client

    async def refuse(*a, **kw):
        raise AssertionError("a test tried to call the real LLM")
    monkeypatch.setattr(llm_client, "chat", refuse)
    yield
