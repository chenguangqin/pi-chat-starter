from __future__ import annotations

import json


def format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def text_delta_event(delta: str) -> str:
    return format_sse({"type": "text_delta", "delta": delta})


def status_event(message: str) -> str:
    return format_sse({"type": "status", "message": message})


def error_event(message: str) -> str:
    return format_sse({"type": "error", "message": message})


def done_event(message_id: str) -> str:
    return format_sse({"type": "done", "message_id": message_id})
