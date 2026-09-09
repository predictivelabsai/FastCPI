"""Server-sent-event helpers for the chat streaming endpoint."""

from __future__ import annotations

import json
from typing import Any


def event(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


AGENT_ROUTE = "agent_route"
TOKEN       = "token"
TOOL_START  = "tool_start"
TOOL_END    = "tool_end"
ARTIFACT    = "artifact_show"
DONE        = "done"
ERROR       = "error"
