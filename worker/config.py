"""Worker configuration loaded from environment / .env file."""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv


class Config:
    """Configuration for the IRT backtest worker.

    Reads from environment variables, falling back to a .env file
    located in the worker directory.
    """

    def __init__(self) -> None:
        # Load .env from the worker/ directory
        env_path = Path(__file__).resolve().parent / ".env"
        load_dotenv(env_path)

        self.api_url: str = os.environ.get("IRT_API_URL", "http://localhost:8000").rstrip("/")
        self.api_key: str = os.environ.get("IRT_API_KEY", "")
        self.poll_interval: int = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))
        self.job_timeout: int = int(os.environ.get("WORKER_JOB_TIMEOUT", "300"))
        self.num_slots: int = int(os.environ.get("WORKER_NUM_SLOTS", "3"))
        self.hist_data_path: str = os.environ.get("HIST_DATA_PATH", "")
        self.engine_path: str = os.environ.get("ENGINE_PATH", "")
        self.mc_runner_path: str = os.environ.get(
            "MC_RUNNER_PATH", "packages/montecarlo/runner/main_mc.py"
        )
        self.worker_debug: bool = os.environ.get("WORKER_DEBUG", "").lower() in ("1", "true", "yes")

        # Shared HTTP session with API key header pre-configured
        self.session: requests.Session = requests.Session()
        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key

    def log_summary(self) -> str:
        """Return a human-readable summary of the configuration."""
        return (
            f"api_url={self.api_url}, "
            f"api_key={'***' + self.api_key[-4:] if self.api_key else '(not set)'}, "
            f"poll_interval={self.poll_interval}s, "
            f"job_timeout={self.job_timeout}s, "
            f"num_slots={self.num_slots}, "
            f"hist_data_path={self.hist_data_path}, "
            f"engine_path={self.engine_path}, "
            f"mc_runner_path={self.mc_runner_path}"
        )
