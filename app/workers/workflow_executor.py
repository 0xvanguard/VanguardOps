"""Pure workflow execution stubs (no I/O, no DB, no Celery)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class WorkflowExecutor:
    """Registry of executable workflows keyed by ``name``.

    In a real deployment these would shell out to remote runners or call
    vendor APIs. For demo purposes they return deterministic payloads so
    the rest of the system can be exercised end-to-end.
    """

    @staticmethod
    def execute_wf_auto_reset(_config: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "action": "password_reset",
            "details": "Temporary password issued via secure channel.",
        }

    @staticmethod
    def execute_wf_connectivity_triage(_config: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "action": "connectivity_check",
            "packet_loss_pct": 0,
            "latency_ms": 12,
            "route_hops": 4,
        }

    @staticmethod
    def execute_wf_system_diag(_config: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "action": "system_diagnostics",
            "cpu_usage_pct": 14,
            "disk_free_gb": 200,
        }

    _REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]]

    @classmethod
    def run_workflow(cls, name: str, config: dict[str, Any]) -> dict[str, Any]:
        registry = cls._registry()
        impl = registry.get(name)
        if impl is None:
            raise ValueError(f"Unknown workflow: {name!r}")
        return impl(config)

    @classmethod
    def _registry(cls) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        return {
            "wf_auto_reset": cls.execute_wf_auto_reset,
            "wf_connectivity_triage": cls.execute_wf_connectivity_triage,
            "wf_ping_trace": cls.execute_wf_connectivity_triage,
            "wf_system_diag": cls.execute_wf_system_diag,
        }
