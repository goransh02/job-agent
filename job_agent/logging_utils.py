from __future__ import annotations

import logging


def trace(logger: logging.Logger, message: str, *args) -> None:
    logger.info(message, *args)

    try:
        rendered = message % args if args else message
    except Exception:
        rendered = f"{message} {args}"

    print(rendered, flush=True)
