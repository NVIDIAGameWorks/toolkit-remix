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
import functools
import pathlib
import uuid

import omni.kit.test
from omni.flux.job_queue.core.events import StateChange
from omni.flux.job_queue.core.interface import JobState
from omni.flux.job_queue.core.job import Job
from omni.flux.job_queue.core.serializer import deserialize, serialize


def my_callable():
    pass


def add(a, b):
    return a + b


def callback(interface, job):
    pass


@dataclasses.dataclass
class DataclassWithNonInitField:
    value: int
    derived: int = dataclasses.field(init=False)

    def __post_init__(self):
        self.derived = self.value * 2


class TestSerializer(omni.kit.test.AsyncTestCase):
    async def test_serialize_deserialize_various(self):
        tests = [
            ("JobInstance", Job()),
            ("UUID", uuid.uuid4()),
            ("posix pathlib", pathlib.Path("/tmp/test")),
            # Technically I've set it up so that both posix and windows paths are serialized using as_posix() just to
            # standardize how things are stored, but pathlib.Path.__eq__ considers them equal so this test passes.
            ("win pathlib", pathlib.Path(r"\tmp\test")),
            ("Callable", my_callable),
            ("str", "hello"),
            ("int", 123),
            ("float", 3.14),
            ("list", [1, 2, 3]),
            ("tuple", (1, 2, 3)),
            ("set", {1, 2, 3}),
            ("dict", {"a": 1}),
            ("None", None),
        ]

        for name, obj in tests:
            with self.subTest(name=name):
                data = serialize(obj)
                obj2 = deserialize(data)
                self.assertEqual(obj, obj2)

    async def test_serialize_partial(self):
        original = functools.partial(add, 2)
        data = serialize(original)
        restored = deserialize(data)
        self.assertEqual(restored(2), 4)

    async def test_serialize_statechange_value_is_enum_after_roundtrip(self):
        original = StateChange(value=JobState.UNKNOWN)
        data = serialize(original)
        restored = deserialize(data)
        self.assertIsInstance(restored.value, JobState)
        self.assertEqual(restored.value, JobState.UNKNOWN)

    async def test_serialize_dataclass_ignores_non_init_fields(self):
        original = DataclassWithNonInitField(value=3)
        data = serialize(original)
        restored = deserialize(data)
        self.assertEqual(restored, original)
