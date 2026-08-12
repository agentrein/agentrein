"""Fakes connector responses in sandbox mode when the backend indicates an action was simulated."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


class SimulatedResponse:
    """A dynamic class that fakes any response structure for simulated sandbox requests."""

    def __getattr__(self, name: str) -> Any:
        # Guard python-specific dunder methods from infinite recursion
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)

        if name == "simulated":
            return True

        if name in ("to_dict", "json"):
            return lambda: {"simulated": True}

        if name == "id" or name.endswith("_id"):
            return f"sim_{name}_{int(time.time() * 1000)}"

        if name == "url" or name.endswith("_url"):
            return "https://sandbox.agentrein.com"

        if name == "number":
            return 0

        if name == "status":
            return "simulated"

        if name in ("created", "created_at"):
            return datetime.now(timezone.utc).isoformat()

        return SimulatedResponse()


def create_simulated_response() -> SimulatedResponse:
    """Factory function to create a new SimulatedResponse instance."""
    return SimulatedResponse()
