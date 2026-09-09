#!/usr/bin/env python3
"""Standalone durable watchlist worker for FastCPI deployments."""

from __future__ import annotations

import logging
import os
import time

from monitoring.jobs import queue_and_work


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    interval = max(15, int(os.environ.get("WATCHLIST_SCAN_INTERVAL_SECONDS", "60")))
    while True:
        queue_and_work()
        time.sleep(interval)


if __name__ == "__main__":
    main()
