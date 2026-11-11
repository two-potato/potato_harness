"""Trusted isolation adapter boundary.

A protocol is not sandbox evidence: the production runner must select a vetted
implementation. An untrusted task, model, or project config cannot select one.
"""

from pathlib import Path
from typing import Protocol

from . import probe as bubblewrap_probe, run_private as bubblewrap_run_private


class IsolationBackend(Protocol):
    """Host-owned execution boundary for untrusted test processes."""

    def probe(self) -> dict:
        """Test whether the actual isolation profile is available."""
        ...

    def run(self, workspace: Path, argv: list[str], timeout: float = 10) -> dict:
        """Execute inside that profile, or fail without host fallback."""
        ...


class BubblewrapBackend:
    """Adapter for the existing fail-closed Linux Bubblewrap implementation."""

    name = 'bubblewrap'

    def probe(self) -> dict:
        return bubblewrap_probe()

    def run(self, workspace: Path, argv: list[str], timeout: float = 10) -> dict:
        return bubblewrap_run_private(workspace, argv, timeout=timeout)
