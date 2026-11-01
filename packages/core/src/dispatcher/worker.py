"""Separately deployable worker using shared application services."""

import argparse
import logging
import signal
import time
from threading import Event

from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings


def main() -> None:
    """Process idempotent health ticks until shutdown; fail visibly on database errors."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    if parser.parse_args().health:
        healthy = (
            settings.worker_health_file.exists()
            and time.time() - settings.worker_health_file.stat().st_mtime
            < settings.worker_health_ttl_seconds
        )
        raise SystemExit(0 if healthy else 1)
    ledger = Ledger(Database(settings))
    stopped = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            logging.info("Worker health tick: tenants=%s", ledger.tick())
            settings.worker_health_file.touch()
        except Exception:
            logging.exception("Worker health tick failed")
        stopped.wait(settings.worker_interval)


if __name__ == "__main__":
    main()
