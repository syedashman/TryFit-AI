from __future__ import annotations

import concurrent.futures
import logging
import threading
from typing import Any

from app.core.config import Settings
from app.services.job_service import process_job

logger = logging.getLogger(__name__)


class JobScheduler:
    """Dedicated executor for queued Try Fit jobs so task submission is explicit and observable."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._started = False

    def configure(self, *, max_workers: int) -> None:
        with self._lock:
            if self._executor is not None:
                if self._executor._max_workers == max_workers:
                    return
                self.shutdown()
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
            self._started = True
            logger.info("[JOB] scheduler configured workers=%s", max_workers)

    def submit(
        self,
        job_id: str,
        settings: Settings,
        *,
        num_inference_steps: int,
        guidance_scale: float,
        seed: int,
    ) -> None:
        with self._lock:
            if self._executor is None:
                self.configure(max_workers=max(1, min(settings.max_concurrent_jobs, 3)))
            executor = self._executor

        if executor is None:
            raise RuntimeError("Job scheduler executor is not initialized.")

        logger.info("[JOB] scheduling job=%s via executor", job_id)
        future = executor.submit(
            process_job,
            job_id,
            settings,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )
        future.add_done_callback(
            lambda completed, job_id=job_id: self._log_future_result(job_id, completed)
        )

    def _log_future_result(self, job_id: str, future: concurrent.futures.Future[Any]) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("[JOB] background task crashed for job=%s", job_id)
        else:
            logger.info("[JOB] background task finished job=%s", job_id)

    def shutdown(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
            self._started = False
        if executor is not None:
            logger.info("[JOB] scheduler shutting down")
            executor.shutdown(wait=True, cancel_futures=False)


job_scheduler = JobScheduler()
