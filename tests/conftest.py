import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(REPO_ROOT, "examples", "customer-api")


@pytest.fixture
def example_dir():
    return EXAMPLE


@pytest.fixture
def example_ir():
    from sdc_parser import load_project

    return load_project(EXAMPLE).ir
