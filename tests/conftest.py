# conftest.py — project-wide pytest fixtures
#
# centry_loki (provided by loki_logger) is a runtime dependency that ships
# inside the Docker image via a GitHub install. It is NOT installed in the CI
# virtualenv because its PyPI package (loki-logger 1.1.1) requires
# requests>=2.31.0, which conflicts with arbiter==1.0.0 pinning
# requests==2.25.0.
#
# Tests never exercise Loki logging — they mock requests through
# requests_mock. Installing the real package just to satisfy the bare import
# at the top of run.py would break the pip dependency graph.
#
# Solution: install a sys.modules stub before any test file imports
# control_tower.run so the module-level `from centry_loki import log_loki`
# resolves to a MagicMock instead of raising ImportError.

import sys
from unittest import mock

# Register the stub before any test module imports control_tower.run
if "centry_loki" not in sys.modules:
    centry_loki_stub = mock.MagicMock()
    # make `from centry_loki import log_loki` work
    centry_loki_stub.log_loki = mock.MagicMock()
    sys.modules["centry_loki"] = centry_loki_stub
