"""Test defaults: no real model or Laya calls unless a test sets them up itself."""

import pytest


@pytest.fixture(autouse=True)
def _no_live_models(monkeypatch):
    from argus.llm.free_models import reset_free_model_service

    for var in ("HEIMDALLR_LLM", "HEIMDALLR_FREE_MODELS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HEIMDALLR_LOCAL_MODEL", "")
    monkeypatch.setenv("HEIMDALLR_LAYA", "0")
    reset_free_model_service()
    yield
    reset_free_model_service()
