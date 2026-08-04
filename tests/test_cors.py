"""
CORS origins.

Putting the app on a public domain must not take localhost development with
it — that failure looks like a broken pipeline (every asset fails to load),
not like a CORS policy, and costs an afternoon to diagnose.
"""
from __future__ import annotations

import importlib

import pytest


def _origins_with(env_value: str | None, monkeypatch) -> list[str]:
    if env_value is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", env_value)
    import backend.api.main as main
    importlib.reload(main)
    return main._origins


class TestCorsOrigins:
    def test_defaults_to_local_development(self, monkeypatch):
        assert _origins_with(None, monkeypatch) == [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    def test_public_domain_is_added_not_substituted(self, monkeypatch):
        origins = _origins_with("https://paint.example.com", monkeypatch)
        assert "https://paint.example.com" in origins
        assert "http://localhost:3000" in origins, "sharing the app broke local dev"

    def test_accepts_several_and_ignores_blanks(self, monkeypatch):
        origins = _origins_with("https://a.example.com, ,https://b.example.com", monkeypatch)
        assert "https://a.example.com" in origins
        assert "https://b.example.com" in origins
        assert "" not in origins

    def test_no_duplicates(self, monkeypatch):
        origins = _origins_with("http://localhost:3000,https://paint.example.com", monkeypatch)
        assert origins.count("http://localhost:3000") == 1


@pytest.fixture(autouse=True)
def _restore_module(monkeypatch):
    """Leave the imported app in its default state for other test modules."""
    yield
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    import backend.api.main as main
    importlib.reload(main)
