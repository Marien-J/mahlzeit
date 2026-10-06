"""Keep connector tokens out of logs. They are part of the URL path, which access logs print."""

from __future__ import annotations

import logging
import re

_TOKEN_PATH = re.compile(r"(/mcp/)[^/\s?\"]+")


def redact(text: str) -> str:
    return _TOKEN_PATH.sub(r"\1[redacted]", text)


class RedactConnectorTokens(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def install() -> None:
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn", "mahlzeit"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactConnectorTokens) for f in logger.filters):
            logger.addFilter(RedactConnectorTokens())
