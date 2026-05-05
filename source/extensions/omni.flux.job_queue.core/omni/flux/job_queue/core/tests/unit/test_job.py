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

import uuid

import omni.kit.test
from omni.flux.job_queue.core.interface import JobState, QueueInterface
from omni.flux.job_queue.core.job import CallableJob, Job, JobGraph
from omni.flux.job_queue.core.tests.unit.helpers import temp_db_path


def always_42():
    return 42


def add(a=0, b=0):
    return a + b


def error_func():
    return 1 / 0


class TestJob(omni.kit.test.AsyncTestCase):
    async def test_job_execute_not_implemented(self):
        job = Job()
        with self.assertRaises(NotImplementedError):
            job.execute()

    async def test_job_callablejob_execute_param(self):
        tests = [
            ("args", (2, 3), {}, 5),
            ("kwargs", (), {"a": 1, "b": 2}, 3),
            ("no_args_or_kwargs", (), {}, 0),
        ]
        for name, args, kwargs, expected in tests:
            with self.subTest(name=name):
                job = CallableJob(func=add, args=args, kwargs=kwargs)
                self.assertEqual(job.execute(), expected)

    async def test_job_callablejob_execute_error(self):
        job = CallableJob(func=error_func)
        with self.assertRaises(ZeroDivisionError):
            job.execute()

    async def test_job_jobstate_enum_eq(self):
        tests = [
            (JobState.QUEUED, "QUEUED"),
            (JobState.DONE, "DONE"),
            (JobState.FAILED, "FAILED"),
        ]

        for state, value in tests:
            with self.subTest(name=value):
                self.assertEqual(state.value, value)

    async def test_job_graph_with_no_jobs_fails(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            graph = JobGraph(interface=interface)
            with self.assertRaises(RuntimeError):
                graph.submit()

    async def test_job_graph_submit_twice_fails(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            graph = JobGraph(interface=interface)
            job = CallableJob(func=always_42)
            graph.add_job(job)
            graph.submit()
            with self.assertRaises(RuntimeError):
                graph.submit()

    async def test_job_missing_dependency(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)

            job1 = CallableJob(func=always_42)
            job1.add_dependency(uuid.uuid4())

            graph = JobGraph(interface=interface)
            graph.add_job(job1)

            with self.assertRaises(RuntimeError):
                graph.validate()

    async def test_job_circular_dependency(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            graph = JobGraph(interface=interface)
            job1 = CallableJob(func=always_42)
            job2 = CallableJob(func=always_42)
            graph.add_job(job1)
            graph.add_job(job2)
            job1.add_dependency(job2)
            job2.add_dependency(job1)
            with self.assertRaises(RuntimeError):
                graph.validate()
