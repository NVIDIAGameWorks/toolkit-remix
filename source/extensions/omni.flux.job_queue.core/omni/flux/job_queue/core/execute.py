"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import concurrent.futures
import datetime
import logging
import pathlib
import sys
import threading
import time
import traceback
import uuid
from typing import Any, Literal

import carb
import omni.flux.job_queue.core.events
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job
import omni.flux.job_queue.core.serializer
import omni.flux.job_queue.core.utils
from omni.flux.job_queue.core.constants import job_queue_config


_LOGGER = logging.getLogger(__name__)


def _log_info(message: str) -> None:
    try:
        carb.log_info(message)
    except Exception:  # noqa: BLE001
        _LOGGER.info(message)


def _log_warn(message: str) -> None:
    try:
        carb.log_warn(message)
    except Exception:  # noqa: BLE001
        _LOGGER.warning(message)


class FileTextIO:
    """
    Context manager that redirects stdout/stderr to files.
    """

    def __init__(self, stdout_path: pathlib.Path, stderr_path: pathlib.Path) -> None:
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
        self.original_stdout = None
        self.original_stderr = None
        self.stdout_file = None
        self.stderr_file = None

    def __enter__(self) -> "FileTextIO":
        self.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        self.stderr_path.parent.mkdir(parents=True, exist_ok=True)

        self.stdout_file = open(self.stdout_path, "w", encoding="utf-8", buffering=1)
        try:
            self.stderr_file = open(self.stderr_path, "w", encoding="utf-8", buffering=1)
        except OSError:
            self.stdout_file.close()
            self.stdout_file = None
            raise

        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

        sys.stdout = self.stdout_file
        sys.stderr = self.stderr_file

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

        if self.stdout_file:
            self.stdout_file.close()
        if self.stderr_file:
            self.stderr_file.close()

        return False

    def log_info(self, message: str) -> None:
        if self.stdout_file:
            self.stdout_file.write(f"[{datetime.datetime.now().isoformat()}] {message}\n")
            self.stdout_file.flush()

    def log_error(self, message: str) -> None:
        if self.stderr_file:
            self.stderr_file.write(f"[{datetime.datetime.now().isoformat()}] {message}\n")
            self.stderr_file.flush()


def get_default_job_directory(
    interface: omni.flux.job_queue.core.interface.QueueInterface, job_id: uuid.UUID | str
) -> pathlib.Path:
    """
    Get the default directory path for a job's data.
    """
    return pathlib.Path(interface.db_path).parent / "job_data" / str(job_id)


class JobExecutor:
    """
    Executes jobs using a concurrent.futures.Executor
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface | None = None,
        executor: concurrent.futures.Executor | None = None,
    ) -> None:
        if interface is None:
            interface = omni.flux.job_queue.core.interface.QueueInterface()
        self.interface = interface

        if executor is None:
            if interface.db_path.startswith(":memory:"):
                raise ValueError(
                    "In-memory SQLite databases will not work correctly with the default "
                    "ProcessPoolExecutor. You can provide a ThreadPoolExecutor instead."
                )
            executor = concurrent.futures.ProcessPoolExecutor()
        self.executor = executor
        self._shutdown = False

    def __del__(self) -> None:
        try:  # noqa: SIM105
            self.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        executor = self.executor
        self.executor = None
        if executor:
            executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    @staticmethod
    def _sandboxed_execute(db_path: str, job_id: uuid.UUID) -> str:
        """
        Execute a job in a sandboxed process and record events.
        """

        interface = omni.flux.job_queue.core.interface.QueueInterface(db_path=db_path)

        job_dir = get_default_job_directory(interface, job_id)

        stdout_path = job_dir / "logs" / "stdout.log"
        stderr_path = job_dir / "logs" / "stderr.log"

        with FileTextIO(stdout_path, stderr_path) as fio:
            fio.log_info(f"Starting {job_id}")
            job = interface.get_job_by_id(job_id)
            if job is None:
                fio.log_error(f"Job {job_id} not found with the interface at {db_path}")
                raise RuntimeError(f"Job {job_id} not found with the interface at {db_path}")

            fio.log_info(f"Updating job state to {omni.flux.job_queue.core.interface.JobState.IN_PROGRESS}")
            interface.append_event(
                job.job_id,
                omni.flux.job_queue.core.events.StateChange(omni.flux.job_queue.core.interface.JobState.IN_PROGRESS),
            )
            try:
                fio.log_info("Running pre_execute")
                job.pre_execute(interface)
                fio.log_info("Running execute")
                result = job.execute()
                fio.log_info("Job execute completed successfully")
                fio.log_info(f"Result: {result!r}")
                fio.log_info("Running post_execute")
                job.post_execute(interface)
                fio.log_info("Adding Result event into db")
                interface.append_event(job.job_id, omni.flux.job_queue.core.events.Result(result))
                fio.log_info(f"Updating job state to {omni.flux.job_queue.core.interface.JobState.DONE}")
                interface.append_event(
                    job.job_id,
                    omni.flux.job_queue.core.events.StateChange(omni.flux.job_queue.core.interface.JobState.DONE),
                )
                fio.log_info("Serializing result for Future")
                serialized_result = omni.flux.job_queue.core.serializer.serialize(result)
                fio.log_info(f"Complete {job_id}")
                return serialized_result
            except Exception as e:
                fio.log_error(f"Error executing {job_id}")
                traceback.print_exc(file=sys.stderr)
                fio.log_error("Adding Error event to db")
                error_event = omni.flux.job_queue.core.events.Error.from_exception(e)
                interface.append_event(job.job_id, error_event)
                interface.append_event(
                    job.job_id,
                    omni.flux.job_queue.core.events.StateChange(omni.flux.job_queue.core.interface.JobState.FAILED),
                )
                fio.log_error(f"Error {job_id}")
                raise

    def execute(self, job_id: uuid.UUID) -> concurrent.futures.Future:
        """
        Submit a job for execution in a separate process.
        """
        if self._shutdown or self.executor is None:
            raise RuntimeError("JobExecutor has been shut down")

        # Set the state to SCHEDULED before adding it to the executor
        self.interface.append_event(
            job_id,
            omni.flux.job_queue.core.events.StateChange(omni.flux.job_queue.core.interface.JobState.SCHEDULED),
        )

        raw_future = self.executor.submit(
            self._sandboxed_execute,
            self.interface.db_path,
            job_id,
        )

        def _deserialize_callback(fut: concurrent.futures.Future) -> Any:
            result = fut.result()
            return omni.flux.job_queue.core.serializer.deserialize(result)

        deserialized_future = concurrent.futures.Future()

        def _set_result(fut: concurrent.futures.Future) -> None:
            try:
                deserialized_future.set_result(_deserialize_callback(fut))
            except Exception as e:  # noqa: BLE001
                deserialized_future.set_exception(e)

        raw_future.add_done_callback(_set_result)
        return deserialized_future


class JobScheduler:
    """
    Schedules jobs from the queue for execution.
    """

    def __init__(
        self,
        interface: omni.flux.job_queue.core.interface.QueueInterface | None = None,
        executor: JobExecutor | None = None,
    ) -> None:
        if interface is None:
            interface = omni.flux.job_queue.core.interface.QueueInterface()
        if executor is None:
            executor = JobExecutor(interface=interface)
        self.interface = interface
        self.executor = executor
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def wait_for_next_queued_job_id(self, poll_interval: float = 5.0, timeout: float | None = None) -> uuid.UUID:
        """
        Poll the queue for a job_id to execute.

        Continuously polls the queue until a job in QUEUED state is found.

        Args:
            poll_interval: How often to poll in seconds.
            timeout: Maximum time to wait. None means wait indefinitely.

        Returns:
            The job_id of the next job to execute.

        Raises:
            TimeoutError: If timeout is reached before finding a job.
            InterruptedError: If the scheduler was stopped.
        """
        start_time = time.time()
        try:
            while not (self._stop_event and self._stop_event.is_set()):
                for job_row in self.interface.get_snapshot():
                    if job_row.state == omni.flux.job_queue.core.interface.JobState.QUEUED:
                        return job_row.job_id
                if timeout is not None and (time.time() - start_time) > timeout:
                    raise TimeoutError("No job found within the specified timeout")
                time.sleep(poll_interval)
            raise InterruptedError("Job scheduling stopped")
        except KeyboardInterrupt:
            _log_info("[JobScheduler] Job scheduling interrupted.")
            raise

    def run(
        self,
        num_jobs: int | None = None,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> None:
        """
        Run the job scheduler loop. This is a blocking call.

        Jobs are submitted to the executor one at a time, waiting for each to complete
        before submitting the next. This ensures that when the scheduler is stopped,
        only the currently executing job continues - no jobs are left waiting in the
        executor's queue.
        """
        _log_info("[JobScheduler] Starting...")
        count = 0
        try:
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    job_id = self.wait_for_next_queued_job_id(poll_interval=poll_interval, timeout=timeout)
                    job = self.interface.get_job_by_id(job_id)
                    if job is None:
                        raise RuntimeError(f"Job {job_id} not found with the interface at {self.interface.db_path}")
                    job.pre_schedule(self.interface)

                    # Submit the job and wait for it to complete before processing the next one
                    # This ensures only one job is in the executor at a time
                    future = self.executor.execute(job_id)

                    job.post_schedule(self.interface)

                    # Wait for the job to complete, but check the stop event periodically
                    while not future.done():
                        if self._stop_event and self._stop_event.is_set():
                            # Stop requested - let the current job finish but don't start new ones
                            _log_info("[JobScheduler] Stop requested, waiting for current job to finish...")
                            future.result()  # Wait for completion
                            break
                        time.sleep(0.5)  # Check every 500ms

                    count += 1
                    if num_jobs is not None and count >= num_jobs:
                        _log_info(f"[JobScheduler] Processed {count} jobs, exiting.")
                        break
                except InterruptedError:
                    _log_info("[JobScheduler] Stopping as requested.")
                    break
        except KeyboardInterrupt:
            _log_info("[JobScheduler] shutting down.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        num_jobs: int | None = None,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> None:
        """
        Start the scheduler in a separate thread.
        """
        if self._thread is not None and self._thread.is_alive():
            _log_warn("[JobScheduler] Scheduler is already running.")
            return

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self.run,
            kwargs={
                "num_jobs": num_jobs,
                "poll_interval": poll_interval,
                "timeout": timeout,
            },
            daemon=True,
        )
        self._thread.start()
        _log_info("[JobScheduler] Started in background thread.")

    def stop(self, wait: bool = True) -> None:
        """
        Stop the scheduler thread.
        """
        if self._stop_event is None:
            _log_warn("[JobScheduler] Scheduler is not running.")
            return

        _log_info("[JobScheduler] Stopping...")
        self._stop_event.set()

        if wait and self._thread is not None:
            self._thread.join()
            _log_info("[JobScheduler] Stopped.")

        self._thread = None
        self._stop_event = None


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=job_queue_config.db_path)
    parser.add_argument(
        "--num_jobs",
        type=int,
        help="Number of jobs to execute. If not set, runs indefinitely.",
    )
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument(
        "--timeout",
        type=float,
        default=float("inf"),
        help="Timeout in seconds to wait for a job.",
    )

    _args = parser.parse_args()

    _interface = omni.flux.job_queue.core.interface.QueueInterface(db_path=_args.db_path)
    _executor = JobExecutor(interface=_interface)

    _scheduler = JobScheduler(interface=_interface, executor=_executor)

    _scheduler.run(
        num_jobs=_args.num_jobs,
        poll_interval=_args.poll_interval,
        timeout=_args.timeout,
    )
