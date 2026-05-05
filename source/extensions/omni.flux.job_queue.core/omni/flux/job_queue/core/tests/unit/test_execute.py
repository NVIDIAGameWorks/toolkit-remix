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
import pathlib
from unittest import mock

import omni.kit.test
from omni.flux.job_queue.core.execute import FileTextIO, JobExecutor, JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import CallableJob, JobGraph
from omni.flux.job_queue.core.tests.unit.helpers import temp_db_path


def return_42():
    return 42


def raise_error():
    raise ValueError("fail")


class CustomError(Exception):
    pass


def raise_custom_error():
    raise CustomError("custom error")


def return_abc():
    return "abc"


def return_none():
    return None


class TestExecute(omni.kit.test.AsyncTestCase):
    async def test_filetextio_closes_stdout_file_if_stderr_open_fails(self):
        stdout_file = mock.MagicMock()
        with mock.patch("builtins.open", side_effect=[stdout_file, OSError("stderr failed")]):
            with self.assertRaises(OSError):
                FileTextIO(pathlib.Path("stdout.log"), pathlib.Path("stderr.log")).__enter__()

        stdout_file.close.assert_called_once()

    async def test_jobexecutor_del_uses_nonblocking_shutdown(self):
        executor = mock.MagicMock()
        job_executor = JobExecutor(interface=mock.MagicMock(), executor=executor)
        job_executor.__del__()

        executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        self.assertTrue(job_executor._shutdown)

    async def test_jobexecutor_shutdown_is_idempotent(self):
        executor = mock.MagicMock()
        job_executor = JobExecutor(interface=mock.MagicMock(), executor=executor)
        job_executor.shutdown()
        job_executor.shutdown()

        executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)

    async def test_execute_jobexecutor(self):
        tests = [
            (return_42, 42),
            (return_abc, "abc"),
            (return_none, None),
        ]
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            executor = JobExecutor(interface=interface, executor=concurrent.futures.ThreadPoolExecutor())
            for func, expected in tests:
                with self.subTest(name=func.__name__):
                    graph = JobGraph(interface=interface)
                    job = CallableJob(func=func)
                    graph.add_job(job)
                    graph.submit()
                    future = executor.execute(job.job_id)
                    result = future.result(timeout=2)
                    self.assertEqual(result, expected)

    async def test_execute_jobexecutor_error(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            executor = JobExecutor(interface=interface, executor=concurrent.futures.ThreadPoolExecutor())
            graph = JobGraph(interface=interface)
            job = CallableJob(func=raise_error)
            graph.add_job(job)
            graph.submit()
            future = executor.execute(job.job_id)
            with self.assertRaises(ValueError):
                future.result(timeout=2)

    async def test_execute_jobexecutor_customerror(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            executor = JobExecutor(interface=interface, executor=concurrent.futures.ThreadPoolExecutor())
            graph = JobGraph(interface=interface)
            job = CallableJob(func=raise_custom_error)
            graph.add_job(job)
            graph.submit()
            future = executor.execute(job.job_id)
            with self.assertRaises(CustomError):
                future.result(timeout=2)

    async def test_execute_jobscheduler_wait_timeout(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            executor = JobExecutor(interface=interface, executor=concurrent.futures.ThreadPoolExecutor())
            scheduler = JobScheduler(interface=interface, executor=executor)
            with self.assertRaises(TimeoutError):
                scheduler.wait_for_next_queued_job_id(timeout=0.1, poll_interval=0.05)

    async def test_execute_jobscheduler_run(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)

            graph = JobGraph(interface=interface)
            job = CallableJob(func=return_42)
            graph.add_job(job)
            qjobs = graph.submit()
            self.assertEqual(len(qjobs), 1)
            qjob = qjobs[0]

            executor = JobExecutor(interface=interface, executor=concurrent.futures.ThreadPoolExecutor())
            scheduler = JobScheduler(interface=interface, executor=executor)
            scheduler.run(num_jobs=1, timeout=0.1, poll_interval=0.05)

            self.assertEqual(qjob.result(), 42)

    async def test_execute_jobscheduler_run_failure(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)

            graph = JobGraph(interface=interface)
            job = CallableJob(func=raise_custom_error)
            graph.add_job(job)
            qjobs = graph.submit()
            self.assertEqual(len(qjobs), 1)
            qjob = qjobs[0]

            executor = JobExecutor(interface=interface, executor=concurrent.futures.ThreadPoolExecutor())
            scheduler = JobScheduler(interface=interface, executor=executor)
            scheduler.run(num_jobs=1, timeout=0.1, poll_interval=0.05)

            with self.assertRaises(CustomError):
                qjob.result()
