"""Fixtures shared by the integration test suite.

Integration tests boot real services (Postgres, Redis) via Testcontainers.
They are slower than unit tests (~10s for the container alone) and require
a Docker daemon, so they are gated behind the ``integration`` marker.

Run them explicitly:

    pytest -m integration
    make test-integration

The default ``pytest`` invocation excludes them (see ``pyproject.toml``).
"""

from __future__ import annotations

import socket
from collections.abc import Generator

import pytest


def _docker_available() -> bool:
    """Best-effort probe for a reachable Docker daemon.

    Looks (in order) at: ``DOCKER_HOST=unix://...``, ``DOCKER_HOST=tcp://...``,
    ``/var/run/docker.sock`` (Linux/macOS default), and the rootless podman
    socket at ``$XDG_RUNTIME_DIR/podman/podman.sock``. If none answer we
    skip the integration tests instead of erroring out.
    """
    import os
    from pathlib import Path
    from urllib.parse import urlparse

    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host:
        parsed = urlparse(docker_host)
        if parsed.scheme == "unix":
            sock_path = parsed.path
            if Path(sock_path).exists() and _ping_unix(sock_path):
                return True
        elif parsed.scheme == "tcp":
            try:
                with socket.create_connection((parsed.hostname, parsed.port or 2375), timeout=0.5):
                    return True
            except OSError:
                pass

    if Path("/var/run/docker.sock").exists() and _ping_unix("/var/run/docker.sock"):
        return True

    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if xdg_runtime:
        podman_sock = Path(xdg_runtime) / "podman" / "podman.sock"
        if podman_sock.exists() and _ping_unix(str(podman_sock)):
            return True

    return False


def _ping_unix(path: str) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(path)
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def _require_docker() -> Generator[None, None, None]:
    """Skip every integration test in this package when Docker is not reachable."""
    if not _docker_available():
        pytest.skip(
            "Docker daemon not reachable; integration tests skipped. "
            "Install Docker or set DOCKER_HOST to enable them.",
            allow_module_level=True,
        )
    return
