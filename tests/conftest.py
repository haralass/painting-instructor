import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests that download ML models or run the full pipeline (deselect with -m 'not slow')",
    )
