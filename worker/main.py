"""IRT Backtest Worker -- parallel orchestrator entry point.

Entry point: ``python -m worker.main``

The worker runs on the HOST machine (not inside Docker). It communicates
with the IRT API via HTTP to discover, claim, and execute backtest jobs
using N parallel slot threads.
"""

import signal
import logging

from worker.config import Config
from worker.orchestrator import Orchestrator

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("irt-worker")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    config = Config()
    orch = Orchestrator(config)

    signal.signal(signal.SIGTERM, lambda s, f: orch.stop())
    signal.signal(signal.SIGINT, lambda s, f: orch.stop())

    logger.info("Worker started | %s", config.log_summary())
    orch.run()
    logger.info("Worker shut down gracefully.")


if __name__ == "__main__":
    main()
