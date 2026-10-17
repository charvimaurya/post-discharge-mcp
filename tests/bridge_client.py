"""Explicit authenticated client for existing bridge behavior tests."""
from starlette.testclient import TestClient

BRIDGE_TEST_KEY = "bridge-test-key-for-mocked-tests-only"


class BridgeClient(TestClient):
    def __init__(self, app, **kwargs):
        headers = {"X-Bridge-Key": BRIDGE_TEST_KEY, **kwargs.pop("headers", {})}
        super().__init__(app, headers=headers, **kwargs)
