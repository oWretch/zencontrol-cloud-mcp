"""Shared fixtures for ZenControl MCP tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zencontrol_cloud_mcp.api.rest import ZenControlAPI
from zencontrol_cloud_mcp.scope import ScopeConstraint


@pytest.fixture
def mock_client():
    """Create a mock ZenControlClient with async get/post methods."""
    client = MagicMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_api(mock_client):
    """Create a ZenControlAPI backed by a mocked client."""
    return ZenControlAPI(mock_client)


@pytest.fixture
def scope():
    """Create an unconstrained ScopeConstraint."""
    return ScopeConstraint()


@pytest.fixture
def mock_context(mock_api, scope):
    """Create a mock MCP Context with the API in lifespan_context."""
    ctx = MagicMock()
    ctx.lifespan_context = {"api": mock_api, "scope": scope}
    return ctx


@pytest.fixture
def sample_site():
    """Sample site data matching ZenControl API response format."""
    return {
        "siteId": "3b5b2c02-0e43-423f-9719-758ab3fcb456",
        "tag": "hq",
        "name": "HQ Office",
        "buildingSize": 350.1,
        "address": {
            "country": "AU",
            "adminArea": "QLD",
            "locality": "Brisbane",
            "postCode": "4000",
            "street": "123 Main St",
        },
        "geographicLocation": {
            "latitude": -27.47,
            "longitude": 153.02,
        },
    }


@pytest.fixture
def sample_group():
    """Sample group data."""
    return {
        "groupId": {
            "gatewayId": {"gtin": 565343546, "serial": "AABBCCDD"},
            "groupNumber": 5,
        },
        "label": {"value": "Office 3.02", "state": "OK", "error": None},
        "type": {"value": "STANDARD", "state": "OK", "error": None},
        "status": {"value": "ACTIVE", "state": "OK", "error": None},
    }


@pytest.fixture
def sample_device():
    """Sample device data."""
    return {
        "deviceId": {
            "gatewayId": {"gtin": 565343546, "serial": "AABBCCDD"},
            "busUnitId": {"gtin": 12345678, "serial": "11223344"},
        },
        "deviceLocationId": "758ab3fc-423f-0e43-9719-b4563b5b2c02",
        "label": {"value": "End of hallway", "state": "OK", "error": None},
        "identifier": {"value": 1, "state": "OK", "error": None},
        "status": {"value": "ACTIVE", "state": "OK", "error": None},
    }
