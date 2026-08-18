"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
import pathlib
import uuid

import omni.kit.test
import omni.flux.job_queue.core.persistence as persistence
from omni.flux.job_queue.core.job import JobOutputPort, JobOutputs
from omni.flux.job_queue.core.persistence import PersistenceCodec, PersistenceRegistry
from omni.flux.job_queue.core.serializer import deserialize, serialize


@dataclasses.dataclass(frozen=True, slots=True)
class _Record:
    """Represent one explicit custom persistence payload."""

    value: int


@dataclasses.dataclass(frozen=True, slots=True)
class _UnknownRecord:
    """Represent an intentionally unregistered dataclass."""

    value: int


_RECORD_CODEC = PersistenceCodec(
    "test.Record",
    _Record,
    lambda value: (value.value,),
    lambda value: _Record(*value),
)


class TestPersistenceRuntime(omni.kit.test.AsyncTestCase):
    """Validate intentionally narrow explicit persistence contracts."""

    async def setUp(self):
        """Register the exact custom record codec used by round-trip tests."""
        persistence.get_registry().register_codecs([_RECORD_CODEC])

    async def tearDown(self):
        """Remove the exact custom record codec."""
        persistence.get_registry().unregister_codecs([_RECORD_CODEC])

    async def test_explicit_slotted_record_round_trips(self):
        """A custom record is serialized only through its explicit codec pair."""
        # Arrange
        record = _Record(7)

        # Act
        restored = deserialize(serialize(record))

        # Assert
        self.assertEqual(restored, record)
        self.assertIs(type(restored), _Record)

    async def test_unregistered_dataclass_is_rejected(self):
        """Persistence never falls back to generic dataclass introspection."""
        # Arrange
        record = _UnknownRecord(7)

        # Act
        with self.assertRaisesRegex(TypeError, "No serializer"):
            serialize(record)

        # Assert
        self.assertIsNone(persistence.get_registry().get_name(_UnknownRecord))

    async def test_legacy_pickle_tag_is_rejected_without_decoding(self):
        """Executable legacy payload tags are not part of the explicit JSON schema."""
        # Arrange
        payload = '{"__type__": "pickle", "value": "gASVBQAAAAAAAABLAi4="}'

        # Act
        with self.assertRaisesRegex(ValueError, "Unknown serialized type: pickle"):
            deserialize(payload)

        # Assert
        self.assertIsNone(persistence.get_registry().get_codec("pickle"))

    async def test_codec_pair_validation_is_atomic(self):
        """One-sided codecs reject the whole registration batch."""
        # Arrange
        encoder = _RECORD_CODEC.encoder

        # Act
        with self.assertRaisesRegex(TypeError, "both encoder and decoder") as error:
            PersistenceCodec("test.OneSided", _UnknownRecord, encoder)

        # Assert
        self.assertIsInstance(error.exception, TypeError)

    async def test_non_callable_codec_pair_is_rejected(self):
        """Both custom codecs must be callable before registration mutates the registry."""
        # Arrange
        encoder = 1
        decoder = 2

        # Act
        with self.assertRaisesRegex(TypeError, "encoder and decoder must be callable") as error:
            PersistenceCodec("test.InvalidCodec", _UnknownRecord, encoder, decoder)

        # Assert
        self.assertIsInstance(error.exception, TypeError)

    async def test_conflicting_codec_batch_does_not_mutate_registry(self):
        """A conflicting batch leaves all previous registrations unchanged."""
        # Arrange
        registry = PersistenceRegistry()
        original = PersistenceCodec("test.Record", _Record)
        conflict = PersistenceCodec("test.Record", _UnknownRecord)
        registry.register_codecs([original])

        # Act
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register_codecs([conflict])

        # Assert
        self.assertIs(registry.get_codec("test.Record"), original)

    async def test_supported_native_port_type_identities_are_registered(self):
        """Every serializer-supported native typed-port boundary has an exact identity."""
        # Arrange
        native_types = (list, dict, tuple, set, frozenset, bytes, uuid.UUID, pathlib.Path, bool, int, float, str)

        # Act
        names = [persistence.get_registry().get_name(value_type) for value_type in native_types]

        # Assert
        self.assertTrue(all(names))
        self.assertIsNone(persistence.get_registry().get_name(type(None)))

    async def test_path_port_accepts_platform_concrete_path_and_round_trips(self):
        """The central Path family boundary accepts and restores the platform-specific subclass."""
        # Arrange
        port = JobOutputPort("path", pathlib.Path)
        path = pathlib.Path("folder") / "artifact.png"
        outputs = JobOutputs({port: path})

        # Act
        restored = deserialize(serialize(outputs[port]))

        # Assert
        self.assertEqual(restored, path)
        self.assertIsInstance(restored, pathlib.Path)

    async def test_serialize_non_finite_float_rejects_non_standard_json(self):
        """Queue persistence rejects every non-finite floating-point value."""
        # Arrange
        values = (float("nan"), float("inf"), float("-inf"))

        # Act
        errors = []
        for value in values:
            with self.subTest(value=value), self.assertRaises(TypeError) as error:
                serialize(value)
            errors.append(error.exception)

        # Assert
        self.assertEqual(len(errors), len(values))
        for error in errors:
            self.assertRegex(str(error), "Non-finite")

    async def test_deserialize_non_finite_float_rejects_non_standard_json(self):
        """Queue persistence rejects non-standard constants from external JSON."""
        # Arrange
        payloads = ("NaN", "Infinity", "-Infinity")

        # Act
        errors = []
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(ValueError) as error:
                deserialize(payload)
            errors.append(error.exception)

        # Assert
        self.assertEqual(len(errors), len(payloads))
        for error in errors:
            self.assertRegex(str(error), "Non-standard JSON number")

    async def test_deserialize_exponent_overflow_rejects_non_finite_float(self):
        """A standard JSON exponent cannot overflow into a persisted infinity."""
        # Arrange
        payload = "1e400"

        # Act
        with self.assertRaisesRegex(ValueError, "Non-finite") as error:
            deserialize(payload)

        # Assert
        self.assertIsInstance(error.exception, ValueError)

    async def test_serialize_cyclic_container_raises_documented_type_error(self):
        """Recursive containers fail deterministically instead of exhausting recursion."""
        # Arrange
        value = []
        value.append(value)

        # Act
        with self.assertRaisesRegex(TypeError, "Cyclic") as error:
            serialize(value)

        # Assert
        self.assertIsInstance(error.exception, TypeError)

    async def test_deserialize_rejects_duplicate_json_members(self):
        """Ambiguous JSON object members never use last-value-wins semantics."""
        # Arrange
        payload = '{"__type__": "path", "value": "first", "value": "second"}'

        # Act
        with self.assertRaisesRegex(ValueError, "duplicate member") as error:
            deserialize(payload)

        # Assert
        self.assertIsInstance(error.exception, ValueError)
