"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Reset environment variables before each test."""
    # Clear any SYMPHONY_ prefixed env vars
    import os
    for key in list(os.environ.keys()):
        if key.startswith("SYMPHONY_"):
            monkeypatch.delenv(key, raising=False)
