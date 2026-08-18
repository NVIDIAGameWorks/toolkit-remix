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
from omni.flux.job_queue.core.job import (
    Job,
    JobConnection,
    JobControlDependency,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobLiteralInput,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)

VALUE = JobInputPort("value", int)
RESULT = JobOutputPort("result", int)
TEXT_RESULT = JobOutputPort("text_result", str)


@dataclasses.dataclass
class _TypedJob(Job):
    """Expose one integer input and output for graph validation tests."""

    input_ports = (VALUE,)
    output_ports = (RESULT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return the bound input and report one structured progress update.

        Args:
            job_directory: Queue-owned job directory.
            inputs: Exact typed input values resolved by the graph.
            progress_callback: Callback that persists structured progress.

        Returns:
            Exact typed output values.
        """
        await progress_callback(JobProgress(completed=1, total=1, detail=job_directory.name))
        return JobOutputs({RESULT: inputs[VALUE]})


@dataclasses.dataclass
class _TextOutputJob(Job):
    """Expose one text output for connection-type validation tests."""

    output_ports = (TEXT_RESULT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Return one text output.

        Args:
            job_directory: Queue-owned job directory.
            inputs: Exact typed input values resolved by the graph.
            progress_callback: Callback that persists structured progress.

        Returns:
            One text output.
        """
        return JobOutputs({TEXT_RESULT: job_directory.name})


@dataclasses.dataclass
class _InstanceInputPortsJob(_TypedJob):
    """Deliberately persist a type-owned input declaration as an instance field."""

    input_ports: tuple[JobInputPort, ...] = ()


@dataclasses.dataclass
class _InstanceOutputPortsJob(_TypedJob):
    """Deliberately persist a type-owned output declaration as an instance field."""

    output_ports: tuple[JobOutputPort, ...] = ()


@dataclasses.dataclass
class _InstanceConcurrencyJob(_TypedJob):
    """Deliberately persist type-owned concurrency as an instance field."""

    max_concurrency: int = 4


class TestTypedGraph(omni.kit.test.AsyncTestCase):
    """Validate the public typed graph construction contract."""

    async def test_bind_exact_type_retains_literal_input(self):
        """A literal with the exact input type is retained by the graph."""
        # Arrange
        job = _TypedJob()
        graph = JobGraph()
        graph.add_job(job)

        # Act
        graph.bind(job, VALUE, 7)

        # Assert
        self.assertEqual(graph.literal_inputs, [JobLiteralInput(job.job_id, VALUE, 7)])

    async def test_job_inputs_reject_falsy_non_mapping(self):
        """A falsy value cannot masquerade as an empty typed input mapping."""
        # Arrange
        invalid_values = False

        # Act
        with self.assertRaisesRegex(TypeError, "must be a mapping") as error:
            JobInputs(invalid_values)

        # Assert
        self.assertIsInstance(error.exception, TypeError)

    async def test_job_outputs_reject_iterable_pairs(self):
        """Typed outputs accept mappings rather than values merely accepted by dict."""
        # Arrange
        invalid_values = [(RESULT, 1)]

        # Act
        with self.assertRaisesRegex(TypeError, "must be a mapping") as error:
            JobOutputs(invalid_values)

        # Assert
        self.assertIsInstance(error.exception, TypeError)

    async def test_validate_rejects_instance_input_port_shadowing(self):
        """Persisted instances cannot replace their type's input-port declaration."""
        # Arrange
        regular_fields = {field.name for field in dataclasses.fields(_TypedJob)}

        # Act
        with self.assertRaisesRegex(TypeError, "input_ports must be declared on the job type"):
            _InstanceInputPortsJob()

        # Assert
        self.assertNotIn("input_ports", regular_fields)

    async def test_validate_rejects_instance_output_port_shadowing(self):
        """Persisted instances cannot replace their type's output-port declaration."""
        # Arrange
        regular_fields = {field.name for field in dataclasses.fields(_TypedJob)}

        # Act
        with self.assertRaisesRegex(TypeError, "output_ports must be declared on the job type"):
            _InstanceOutputPortsJob()

        # Assert
        self.assertNotIn("output_ports", regular_fields)

    async def test_validate_rejects_instance_concurrency_shadowing(self):
        """Persisted instances cannot replace their type's concurrency declaration."""
        # Arrange
        regular_fields = {field.name for field in dataclasses.fields(_TypedJob)}

        # Act
        with self.assertRaisesRegex(TypeError, "max_concurrency must be declared on the job type"):
            _InstanceConcurrencyJob()

        # Assert
        self.assertNotIn("max_concurrency", regular_fields)

    async def test_connect_exact_type_fans_output_to_multiple_inputs(self):
        """One output may feed multiple compatible input ports."""
        # Arrange
        source = _TypedJob()
        first = _TypedJob()
        second = _TypedJob()
        graph = JobGraph(jobs=[source, first, second])
        output = source.output(RESULT)
        graph.connect(output, first.input(VALUE))

        # Act
        graph.connect(output, second.input(VALUE))

        # Assert
        self.assertEqual(
            graph.connections,
            [
                JobConnection(source.job_id, RESULT, first.job_id, VALUE),
                JobConnection(source.job_id, RESULT, second.job_id, VALUE),
            ],
        )

    async def test_connect_different_port_types_rejects_connection(self):
        """Assignable subclasses do not weaken exact port compatibility."""
        # Arrange
        source = _TextOutputJob()
        target = _TypedJob()
        graph = JobGraph(jobs=[source, target])

        # Act
        with self.assertRaisesRegex(TypeError, "exactly match"):
            graph.connect(source.output(TEXT_RESULT), target.input(VALUE))

        # Assert
        self.assertEqual(graph.connections, [])

    async def test_second_binding_for_input_rejects_duplicate(self):
        """An input accepts exactly one literal or connection binding."""
        # Arrange
        source = _TypedJob()
        target = _TypedJob()
        graph = JobGraph(jobs=[source, target])
        graph.bind(target, VALUE, 2)

        # Act
        with self.assertRaisesRegex(ValueError, "already bound"):
            graph.connect(source.output(RESULT), target.input(VALUE))

        # Assert
        self.assertEqual(len(graph.literal_inputs), 1)
        self.assertEqual(graph.connections, [])

    async def test_edges_across_connection_and_control_reject_cycle(self):
        """Data and control edges participate in one cycle check."""
        # Arrange
        first = _TypedJob()
        second = _TypedJob()
        graph = JobGraph(jobs=[first, second])
        graph.connect(first.output(RESULT), second.input(VALUE))

        # Act
        with self.assertRaisesRegex(ValueError, "cycle"):
            graph.depends_on(first, second)

        # Assert
        self.assertEqual(graph.control_dependencies, [])

    async def test_connection_to_job_outside_graph_rejects_cross_graph_edge(self):
        """A graph cannot connect to a child it does not own."""
        # Arrange
        owned = _TypedJob()
        external = _TypedJob()
        graph = JobGraph(jobs=[owned])

        # Act
        with self.assertRaisesRegex(ValueError, "does not belong"):
            graph.connect(owned.output(RESULT), external.input(VALUE))

        # Assert
        self.assertEqual(graph.connections, [])

    async def test_graph_validation_rechecks_mutated_job_fields(self):
        """Post-construction mutation cannot bypass the job contract at submission time."""
        # Arrange
        job = _TypedJob()
        graph = JobGraph(jobs=[job])
        graph.bind(job, VALUE, 1)
        job.name = ""

        # Act
        with self.assertRaisesRegex(RuntimeError, "name must be a non-empty string"):
            graph.validate()

        # Assert
        self.assertEqual(graph.jobs, [job])

    async def test_graph_validation_rejects_mutated_duplicate_control_dependency(self):
        """Submission validation rejects duplicate control edges added after construction."""
        # Arrange
        prerequisite = _TextOutputJob()
        dependent = _TextOutputJob()
        graph = JobGraph(jobs=[prerequisite, dependent])
        dependency = JobControlDependency(dependent.job_id, prerequisite.job_id)
        graph.control_dependencies.extend((dependency, dependency))

        # Act
        with self.assertRaisesRegex(RuntimeError, "duplicate control dependencies") as error:
            graph.validate()

        # Assert
        self.assertIsInstance(error.exception, RuntimeError)

    async def test_graph_validation_rejects_mutated_collection_shape(self):
        """Graph collection containers are validated again before persistence."""
        # Arrange
        graph = JobGraph()
        graph.jobs = ()

        # Act
        with self.assertRaisesRegex(RuntimeError, "jobs must be a list"):
            graph.validate()

        # Assert
        self.assertIsInstance(graph.graph_id, uuid.UUID)

    async def test_graph_validation_rejects_mutated_identity(self):
        """A malformed graph identifier cannot reach persistence."""
        # Arrange
        graph = JobGraph()
        graph.graph_id = "not-a-uuid"

        # Act
        with self.assertRaisesRegex(RuntimeError, "graph_id must be a uuid.UUID"):
            graph.validate()

        # Assert
        self.assertEqual(graph.graph_id, "not-a-uuid")

    async def test_graph_validation_rejects_mutated_name(self):
        """A blank graph name cannot reach persistence."""
        # Arrange
        graph = JobGraph()
        graph.name = " "

        # Act
        with self.assertRaisesRegex(RuntimeError, "name must be a non-empty string"):
            graph.validate()

        # Assert
        self.assertEqual(graph.name, " ")

    async def test_connect_rejects_wrong_endpoint_type_deliberately(self):
        """Malformed caller values raise the public contract error instead of AttributeError."""
        # Arrange
        source = _TypedJob()
        target = _TypedJob()
        graph = JobGraph(jobs=[source, target])

        # Act
        with self.assertRaisesRegex(TypeError, "output and input endpoints"):
            graph.connect(source.output(RESULT), object())

        # Assert
        self.assertEqual(graph.connections, [])

    async def test_depends_on_rejects_wrong_job_type_deliberately(self):
        """Control-edge construction validates caller job objects before member access."""
        # Arrange
        target = _TypedJob()
        graph = JobGraph(jobs=[target])

        # Act
        with self.assertRaisesRegex(TypeError, "must be Job values"):
            graph.depends_on(target, object())

        # Assert
        self.assertEqual(graph.control_dependencies, [])
