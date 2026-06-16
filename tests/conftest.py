"""Shared fixtures for the ElasticKernel test suite.

These tests pin the *current* behavior of the codebase as a safety net for
refactoring. They must not change production code.
"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def fake_shell():
    """A minimal stand-in for ZMQInteractiveShell.

    find_input_vars / migrate only ever touch ``shell.user_ns``, so a
    SimpleNamespace with a ``user_ns`` dict is sufficient.
    """

    def _make(user_ns=None):
        return SimpleNamespace(user_ns=dict(user_ns or {}))

    return _make


@pytest.fixture
def profile_dict():
    """The mutable profiling dict that fingerprint functions accumulate into."""
    return {"idgraph": 0.0, "representation": 0.0}
