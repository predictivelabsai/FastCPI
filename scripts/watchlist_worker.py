#!/usr/bin/env python3
"""Standalone durable watchlist worker for FastCPI deployments."""

from __future__ import annotations

import logging
import os
import socket
import time

from monitoring.jobs import queue_and_work


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    from db import init_db
    from monitoring.health import record_worker_heartbeat
    init_db()
    interval = max(15, int(os.environ.get("WATCHLIST_SCAN_INTERVAL_SECONDS", "60")))
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    record_worker_heartbeat(worker_id, "starting")
    while True:
        try:
            results = queue_and_work()
            record_worker_heartbeat(worker_id, "ready", {"last_batch_size": len(results)})
        except Exception as exc:
            logging.exception("worker iteration failed")
            record_worker_heartbeat(worker_id, "degraded", {"error": type(exc).__name__})
        time.sleep(interval)


if __name__ == "__main__":
    main()
