import os

import pytest


def pytest_addoption(parser):
    parser.addoption("--aws", action="store_true", help="run integration tests against the deployed pilot")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--aws") or os.environ.get("EQH_AWS_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="needs --aws (deployed pilot)")
    for item in items:
        if "aws" in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "aws: integration test against the deployed pilot")
    config.addinivalue_line("markers", "slow: regenerates the full synthetic dataset (~30 s)")
