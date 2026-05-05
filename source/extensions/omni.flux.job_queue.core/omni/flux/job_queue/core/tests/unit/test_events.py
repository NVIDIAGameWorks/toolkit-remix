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

import dataclasses

import omni.flux.job_queue.core.events
import omni.flux.job_queue.core.interface
import omni.flux.job_queue.core.job
import omni.flux.job_queue.core.utils
import omni.kit.test
from omni.flux.job_queue.core.tests.unit.helpers import temp_db_path


def return_42():
    return 42


@dataclasses.dataclass
class CustomEvent(omni.flux.job_queue.core.events.JobEvent):
    value: int


class TestEvents(omni.kit.test.AsyncTestCase):
    async def test_event_name(self):
        """
        Simple test to ensure we don't break the name class property. This class property is used frequently.
        """
        tests = [
            (omni.flux.job_queue.core.events.JobEvent, "JobEvent"),
            (omni.flux.job_queue.core.events.StateChange, "StateChange"),
            (omni.flux.job_queue.core.events.Error, "Error"),
            (omni.flux.job_queue.core.events.Result, "Result"),
        ]
        for event_cls, expected_name in tests:
            with self.subTest(name=expected_name):
                self.assertEqual(event_cls.name, expected_name)

    async def test_event_insert_fetch(self):
        async with temp_db_path() as db_path:
            interface = omni.flux.job_queue.core.interface.QueueInterface(db_path=db_path)
            job = omni.flux.job_queue.core.job.CallableJob(func=return_42)
            graph = omni.flux.job_queue.core.job.JobGraph(interface=interface)
            graph.add_job(job)
            graph.submit()

            state_event1 = omni.flux.job_queue.core.events.StateChange(
                value=omni.flux.job_queue.core.interface.JobState.QUEUED
            )
            interface.append_event(job.job_id, state_event1)
            state_event2 = omni.flux.job_queue.core.events.StateChange(
                value=omni.flux.job_queue.core.interface.JobState.IN_PROGRESS
            )
            interface.append_event(job.job_id, state_event2)
            result_event = omni.flux.job_queue.core.events.Result(value=42)
            interface.append_event(job.job_id, result_event)

            latest_state_event = interface.get_latest_event(job.job_id, omni.flux.job_queue.core.events.StateChange)
            self.assertEqual(latest_state_event, state_event2)

            latest_result_event = interface.get_latest_event(job.job_id, omni.flux.job_queue.core.events.Result)
            self.assertEqual(latest_result_event, result_event)

    async def test_event_custom(self):
        async with temp_db_path() as db_path:
            interface = omni.flux.job_queue.core.interface.QueueInterface(db_path=db_path)
            job = omni.flux.job_queue.core.job.CallableJob(func=return_42)
            graph = omni.flux.job_queue.core.job.JobGraph(interface=interface)
            graph.add_job(job)
            graph.submit()

            custom_event = CustomEvent(value=123)
            interface.append_event(job.job_id, custom_event)
            fetched_event = interface.get_latest_event(job.job_id, CustomEvent)
            self.assertEqual(fetched_event, custom_event)
