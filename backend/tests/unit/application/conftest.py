"""
Fixtures for the workflow engine unit tests.

The fakes themselves live in `workflow_fakes` so the test modules can import them
by name. `tests/` is not a package, so a relative import would fail; pytest's
prepend import mode puts this directory on `sys.path`, which makes the plain
module import work from any test file beside it.
"""

import pytest
from workflow_fakes import WorkflowScenario


@pytest.fixture
def scenario() -> WorkflowScenario:
    """The seeded compliance approval workflow, backed by in-memory fakes."""
    return WorkflowScenario()
