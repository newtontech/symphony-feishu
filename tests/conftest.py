"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def feishu_app_id():
    """Mock Feishu app ID."""
    return "cli_test_app_id"


@pytest.fixture
def feishu_app_secret():
    """Mock Feishu app secret."""
    return "test_app_secret"


@pytest.fixture
def feishu_bitable_token():
    """Mock Feishu Bitable token."""
    return "Fldxxxxx"


@pytest.fixture
def feishu_table_id():
    """Mock Feishu table ID."""
    return "tblxxxxx"