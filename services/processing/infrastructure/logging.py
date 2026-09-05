from __future__ import annotations

import logging

import structlog


def configure_logging(env: str) -> None:
    renderer = structlog.dev.ConsoleRenderer() if env == "dev" else structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(level=logging.INFO)
