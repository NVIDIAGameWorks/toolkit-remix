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

import asyncio
import uuid

import omni.kit.test
from omni.flux.job_queue.core.interface import JobState, QueueInterface
from omni.flux.job_queue.core.job import CallableJob, Job, JobGraph
from omni.flux.job_queue.core.tests.unit.helpers import temp_db_path


def job_one():
    return 1


class TestInterface(omni.kit.test.AsyncTestCase):
    async def test_interface_init(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            with interface.connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT *
                    FROM sqlite_schema
                """
                )
                schemas = cursor.fetchall()

            tables = []
            for schema in schemas:
                if schema["type"] == "table" and not schema["name"].startswith("sqlite_"):
                    tables.append(schema["name"])
            self.assertEqual(tables, ["job_graphs", "jobs", "job_dependencies", "job_events"])

    async def test_interface_submit_and_get_jobs(self):
        tests = [Job, CallableJob]
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            for job_cls in tests:
                with self.subTest(name=job_cls.__name__):
                    graph = JobGraph(interface=interface)
                    job = job_cls() if job_cls is Job else job_cls(func=job_one)
                    graph.add_job(job)
                    graph.submit()
                    jobs = interface.get_jobs_by_graph_id(graph.graph_id)
                    self.assertEqual(graph.jobs, jobs)

    async def test_interface_get_jobs_by_invalid_graph_id(self):
        tests = [uuid.uuid4(), "None"]
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            for graph_id in tests:
                with self.subTest(name=graph_id):
                    jobs = interface.get_jobs_by_graph_id(graph_id)
                    self.assertEqual(jobs, [])

    async def test_interface_get_job_by_id_none(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            job = interface.get_job_by_id(uuid.uuid4())
            self.assertIsNone(job)

    async def test_interface_get_snapshot_ordering_with_equal_priority(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            graph = JobGraph(interface=interface)
            # Create jobs with the same priority but different timestamps
            job1 = CallableJob(name="job1", priority=5, func=job_one)
            graph.add_job(job1)
            graph.submit()
            # Wait a bit to ensure a different timestamp
            await asyncio.sleep(0.01)
            graph = JobGraph(interface=interface)
            job2 = CallableJob(name="job2", priority=5, func=job_one)
            graph.add_job(job2)
            graph.submit()
            rows = interface.get_snapshot()
            # Both jobs have the same priority, so ordering should be by timestamp. FIFO order.
            job_names = [row.job_name for row in rows if row.priority == 5]
            self.assertEqual(job_names, ["job1", "job2"])

    async def test_interface_rows_get_job_rows_ordering_and_state(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            graph = JobGraph(interface=interface)
            job1 = CallableJob(name="job1", priority=8, func=job_one)
            job2 = CallableJob(name="job2", priority=9, func=job_one)
            job2.add_dependency(job1)
            job3 = CallableJob(name="job3", priority=10, func=job_one)
            graph.add_job(job1)
            graph.add_job(job2)
            graph.add_job(job3)
            graph.submit()
            rows = interface.get_snapshot()
            priorities = [row.priority for row in rows]
            self.assertEqual(priorities, [10, 9, 8])
            for row in rows:
                if row.job_id == job2.job_id:
                    self.assertEqual(row.state, JobState.PENDING)
                else:
                    self.assertEqual(row.state, JobState.QUEUED)

    async def test_interface_cascade_delete(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            # Create a job graph and jobs with dependencies
            graph = JobGraph(interface=interface)
            job1 = CallableJob(name="job1", func=job_one)
            job2 = CallableJob(name="job2", func=job_one)
            job2.add_dependency(job1)
            graph.add_job(job1)
            graph.add_job(job2)
            graph.submit()
            # Confirm jobs exist
            jobs = interface.get_jobs_by_graph_id(graph.graph_id)
            self.assertEqual(len(jobs), 2)
            # Delete the job graph using the interface
            interface.delete_job_graph(str(graph.graph_id))
            # Assert jobs are deleted
            jobs_after = interface.get_jobs_by_graph_id(graph.graph_id)
            self.assertEqual(len(jobs_after), 0)
            # Optionally, check job states return None
            self.assertIsNone(interface.get_job_by_id(job1.job_id))
            self.assertIsNone(interface.get_job_by_id(job2.job_id))

    async def test_queue_job_wait_timeout_reports_target_and_current_states(self):
        async with temp_db_path() as db_path:
            interface = QueueInterface(db_path=db_path)
            graph = JobGraph(interface=interface)
            job = CallableJob(func=job_one)
            graph.add_job(job)
            queue_job = graph.submit()[0]

            with self.assertRaisesRegex(
                TimeoutError,
                "to reach one of DONE.*current state is QUEUED",
            ):
                queue_job.wait(states=(JobState.DONE,), timeout=0.01, poll_interval=0.01)
