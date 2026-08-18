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

from __future__ import annotations

import abc
import dataclasses
import datetime
import graphlib
import inspect
import pathlib
import types
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any, ClassVar, Generic, TypeVar

from .apply_handler_base import ApplyHandler

__all__ = (
    "ApplyBinding",
    "Job",
    "JobConnection",
    "JobControlDependency",
    "JobGraph",
    "JobInputEndpoint",
    "JobInputPort",
    "JobInputs",
    "JobLiteralInput",
    "JobOutputEndpoint",
    "JobOutputPort",
    "JobOutputs",
    "JobProgress",
    "JobProgressCallback",
)

PortValueT = TypeVar("PortValueT")


def value_matches_type(value: Any, value_type: type[Any]) -> bool:
    """Return whether a value satisfies the queue's central concrete-type boundary.

    ``pathlib.Path`` is the single intentional family boundary because construction
    returns the platform-specific concrete subclass.

    Args:
        value: Value to validate.
        value_type: Declared persisted type.

    Returns:
        Whether the value is accepted for the declared type.
    """
    if value_type is pathlib.Path:
        return isinstance(value, pathlib.Path)
    return type(value) is value_type


@dataclasses.dataclass(frozen=True, slots=True)
class JobInputPort(Generic[PortValueT]):
    """Name one exact typed input accepted by a job.

    Attributes:
        name: Stable name unique within one job type.
        value_type: Exact Python type accepted by the port.
    """

    name: str
    value_type: type[PortValueT]

    def __post_init__(self) -> None:
        """Validate the stable port name and exact Python type.

        Raises:
            TypeError: If the name or value type is invalid.
        """
        if not isinstance(self.name, str) or not self.name:
            raise TypeError("Job input port name must be a non-empty string")
        if not isinstance(self.value_type, type):
            raise TypeError("Job input port value_type must be a type")


@dataclasses.dataclass(frozen=True, slots=True)
class JobOutputPort(Generic[PortValueT]):
    """Name one exact typed output produced by a job.

    Attributes:
        name: Stable name unique within one job type.
        value_type: Exact Python type produced by the port.
    """

    name: str
    value_type: type[PortValueT]

    def __post_init__(self) -> None:
        """Validate the stable port name and exact Python type.

        Raises:
            TypeError: If the name or value type is invalid.
        """
        if not isinstance(self.name, str) or not self.name:
            raise TypeError("Job output port name must be a non-empty string")
        if not isinstance(self.value_type, type):
            raise TypeError("Job output port value_type must be a type")


class JobInputs(Mapping[JobInputPort[Any], Any]):
    """Expose an immutable exact typed input mapping to a running job."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[JobInputPort[Any], Any] | None = None) -> None:
        """Copy and validate typed input values.

        Args:
            values: Input values keyed by their declared ports.

        Raises:
            TypeError: If a key is not an input port or a value has the wrong exact type.
        """
        if values is None:
            copied = {}
        elif not isinstance(values, Mapping):
            raise TypeError("JobInputs values must be a mapping")
        else:
            copied = dict(values)
        for port, value in copied.items():
            if type(port) is not JobInputPort:
                raise TypeError("JobInputs keys must be JobInputPort values")
            if not value_matches_type(value, port.value_type):
                raise TypeError(f"Input {port.name} must be exactly {port.value_type.__name__}")
        self._values = types.MappingProxyType(copied)

    def __getitem__(self, port: JobInputPort[PortValueT]) -> PortValueT:
        """Return the value bound to one typed input port.

        Args:
            port: Input port to resolve.

        Returns:
            Exact typed input value.
        """
        return self._values[port]

    def __iter__(self) -> Iterator[JobInputPort[Any]]:
        """Iterate input ports in insertion order.

        Yields:
            Bound input ports.
        """
        return iter(self._values)

    def __len__(self) -> int:
        """Return the number of bound inputs.

        Returns:
            Bound input count.
        """
        return len(self._values)


class JobOutputs(Mapping[JobOutputPort[Any], Any]):
    """Expose an immutable exact typed output mapping from a completed job."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[JobOutputPort[Any], Any] | None = None) -> None:
        """Copy and validate typed output values.

        Args:
            values: Output values keyed by their declared ports.

        Raises:
            TypeError: If a key is not an output port or a value has the wrong exact type.
        """
        if values is None:
            copied = {}
        elif not isinstance(values, Mapping):
            raise TypeError("JobOutputs values must be a mapping")
        else:
            copied = dict(values)
        for port, value in copied.items():
            if type(port) is not JobOutputPort:
                raise TypeError("JobOutputs keys must be JobOutputPort values")
            if not value_matches_type(value, port.value_type):
                raise TypeError(f"Output {port.name} must be exactly {port.value_type.__name__}")
        self._values = types.MappingProxyType(copied)

    def __getitem__(self, port: JobOutputPort[PortValueT]) -> PortValueT:
        """Return the value produced for one typed output port.

        Args:
            port: Output port to resolve.

        Returns:
            Exact typed output value.
        """
        return self._values[port]

    def __iter__(self) -> Iterator[JobOutputPort[Any]]:
        """Iterate output ports in insertion order.

        Yields:
            Produced output ports.
        """
        return iter(self._values)

    def __len__(self) -> int:
        """Return the number of produced outputs.

        Returns:
            Produced output count.
        """
        return len(self._values)


@dataclasses.dataclass(frozen=True, slots=True)
class JobProgress:
    """Describe current structured progress for a running job.

    Attributes:
        completed: Completed work units when measurable.
        total: Total work units when measurable.
        detail: Human-readable detail for the current work.
    """

    completed: int | None = None
    total: int | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        """Validate optional structured progress fields.

        Raises:
            TypeError: If a populated field has the wrong type.
            ValueError: If counts are negative or completed exceeds total.
        """
        if self.completed is not None and type(self.completed) is not int:
            raise TypeError("completed must be an int or None")
        if self.total is not None and type(self.total) is not int:
            raise TypeError("total must be an int or None")
        if self.detail is not None and not isinstance(self.detail, str):
            raise TypeError("detail must be a str or None")
        if self.completed is not None and self.completed < 0:
            raise ValueError("completed must not be negative")
        if self.total is not None and self.total < 0:
            raise ValueError("total must not be negative")
        if self.completed is not None and self.total is not None and self.completed > self.total:
            raise ValueError("completed must not exceed total")


JobProgressCallback = Callable[[JobProgress], Awaitable[None]]


@dataclasses.dataclass(frozen=True, slots=True)
class ApplyBinding:
    """Bind one job output to an explicit typed Apply handler and target.

    Attributes:
        output_port: Job output consumed by the handler.
        handler_type: Exact registered handler type.
        target: Exact typed product target persisted with the job.
    """

    output_port: JobOutputPort[Any]
    handler_type: type[ApplyHandler]
    target: Any

    def __post_init__(self) -> None:
        """Validate exact handler input and target types.

        Raises:
            TypeError: If the handler or exact input and target types are incompatible.
        """
        if type(self.output_port) is not JobOutputPort:
            raise TypeError("output_port must be a JobOutputPort")
        if not isinstance(self.handler_type, type) or not issubclass(self.handler_type, ApplyHandler):
            raise TypeError("handler_type must be an ApplyHandler subclass")
        if self.output_port.value_type is not self.handler_type.input_type:
            raise TypeError("Apply output and handler input types must exactly match")
        if not value_matches_type(self.target, self.handler_type.target_type):
            raise TypeError(f"Apply target must be exactly {self.handler_type.target_type.__name__}")


def _default_job_name() -> str:
    """Return a readable default name for a newly constructed job or graph.

    Returns:
        Local construction time formatted for display.
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclasses.dataclass
class Job(abc.ABC):
    """Define persisted data and asynchronous execution for one queue job.

    Attributes:
        job_id: Stable identifier used for persistence and dependencies.
        name: Human-readable job name.
        skip_reason: Reason to persist the job as skipped instead of scheduling it.
    """

    job_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
    name: str = dataclasses.field(default_factory=_default_job_name)
    skip_reason: str | None = None
    apply_binding: ApplyBinding | None = None
    input_ports: ClassVar[tuple[JobInputPort[Any], ...]] = ()
    output_ports: ClassVar[tuple[JobOutputPort[Any], ...]] = ()
    max_concurrency: ClassVar[int] = 1

    def __post_init__(self) -> None:
        """Validate persisted job fields after construction.

        Raises:
            TypeError: If a persisted field or asynchronous hook has an invalid type.
            ValueError: If the skip reason is blank.
        """
        self.validate()

    def validate(self) -> None:
        """Validate fields shared by persisted job types.

        Raises:
            TypeError: If a persisted field has an invalid type.
            ValueError: If the skip reason is blank.
        """
        if type(self.job_id) is not uuid.UUID:
            raise TypeError("job_id must be a uuid.UUID")
        if type(self.name) is not str or not self.name.strip():
            raise TypeError("name must be a non-empty string")
        if self.skip_reason is not None and not isinstance(self.skip_reason, str):
            raise TypeError("skip_reason must be a str or None")
        if self.skip_reason is not None and not self.skip_reason.strip():
            raise ValueError("skip_reason must not be blank")
        job_type = type(self)
        persisted_fields = {field.name for field in dataclasses.fields(self)}
        for declaration in ("input_ports", "output_ports", "max_concurrency"):
            if declaration in persisted_fields:
                raise TypeError(f"{declaration} must be declared on the job type")
        if not inspect.iscoroutinefunction(job_type.execute):
            raise TypeError(f"{job_type.__name__}.execute must be async")
        if type(job_type.max_concurrency) is not int or job_type.max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive int")
        self._validate_ports(job_type.input_ports, JobInputPort, "input")
        self._validate_ports(job_type.output_ports, JobOutputPort, "output")
        if self.apply_binding is not None:
            if type(self.apply_binding) is not ApplyBinding:
                raise TypeError("apply_binding must be an ApplyBinding or None")
            if self.apply_binding.output_port not in job_type.output_ports:
                raise ValueError("apply_binding output port must be declared by the job")

    def get_schedule_block_reason(self) -> str | None:
        """Return why this queued job is not runnable yet.

        Implementations must be fast and free of side effects. Product code calls
        :meth:`QueueInterface.notify_schedule_conditions_changed` when the condition changes.

        Returns:
            Temporary block detail, or ``None`` when the scheduler may claim the job.
        """
        return None

    def input(self, port: JobInputPort[PortValueT]) -> JobInputEndpoint[PortValueT]:
        """Bind this job instance to one declared input port.

        Args:
            port: Input port declared by this job's concrete type.

        Returns:
            Typed endpoint identifying this job and input port.

        Raises:
            TypeError: If the value is not an input port.
            ValueError: If this job does not declare the input port.
        """
        if type(port) is not JobInputPort:
            raise TypeError("port must be a JobInputPort")
        if port not in type(self).input_ports:
            raise ValueError(f"Input port {port.name} is not declared by {type(self).__name__}")
        return JobInputEndpoint(self, port)

    def output(self, port: JobOutputPort[PortValueT]) -> JobOutputEndpoint[PortValueT]:
        """Bind this job instance to one declared output port.

        Args:
            port: Output port declared by this job's concrete type.

        Returns:
            Typed endpoint identifying this job and output port.

        Raises:
            TypeError: If the value is not an output port.
            ValueError: If this job does not declare the output port.
        """
        if type(port) is not JobOutputPort:
            raise TypeError("port must be a JobOutputPort")
        if port not in type(self).output_ports:
            raise ValueError(f"Output port {port.name} is not declared by {type(self).__name__}")
        return JobOutputEndpoint(self, port)

    @staticmethod
    def _validate_ports(ports: tuple, port_type: type, direction: str) -> None:
        """Validate one immutable collection of named exact typed ports.

        Args:
            ports: Port collection declared by a concrete job type.
            port_type: Required port descriptor type.
            direction: Direction used in validation messages.

        Raises:
            TypeError: If a port collection, descriptor, name, or value type is invalid.
            ValueError: If port names are duplicated.
        """
        if type(ports) is not tuple or not all(type(port) is port_type for port in ports):
            raise TypeError(f"{direction}_ports must be a tuple of {port_type.__name__} values")
        if any(not port.name or not isinstance(port.name, str) for port in ports):
            raise TypeError(f"{direction} port names must be non-empty strings")
        if any(not isinstance(port.value_type, type) for port in ports):
            raise TypeError(f"{direction} port value_type must be a type")
        names = [port.name for port in ports]
        if len(names) != len(set(names)):
            raise ValueError(f"{direction} port names must be unique")

    @abc.abstractmethod
    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        """Execute typed work and return exact outputs for durable completion.

        Args:
            job_directory: Queue-owned directory for intermediate files and execution artifacts.
            inputs: Exact typed input values resolved from the owning graph.
            progress_callback: Callback that persists structured progress.

        Returns:
            Exact typed output values to persist.

        Raises:
            NotImplementedError: Until a concrete job implements execution.
        """
        raise NotImplementedError


@dataclasses.dataclass(frozen=True, slots=True)
class JobInputEndpoint(Generic[PortValueT]):
    """Identify one typed input on one concrete job instance.

    Attributes:
        job: Consumer job instance.
        port: Input port declared by the consumer's concrete type.
    """

    job: Job
    port: JobInputPort[PortValueT]


@dataclasses.dataclass(frozen=True, slots=True)
class JobOutputEndpoint(Generic[PortValueT]):
    """Identify one typed output on one concrete job instance.

    Attributes:
        job: Producer job instance.
        port: Output port declared by the producer's concrete type.
    """

    job: Job
    port: JobOutputPort[PortValueT]


@dataclasses.dataclass(frozen=True)
class JobConnection:
    """Connect one job output to one exact typed input.

    Attributes:
        source_job_id: Producer job identifier.
        source_port: Producer output port.
        target_job_id: Consumer job identifier.
        target_port: Consumer input port.
    """

    source_job_id: uuid.UUID
    source_port: JobOutputPort[Any]
    target_job_id: uuid.UUID
    target_port: JobInputPort[Any]


@dataclasses.dataclass(frozen=True)
class JobLiteralInput:
    """Bind one exact typed literal value to a job input.

    Attributes:
        job_id: Consumer job identifier.
        port: Consumer input port.
        value: Exact typed literal value.
    """

    job_id: uuid.UUID
    port: JobInputPort[Any]
    value: Any


@dataclasses.dataclass(frozen=True)
class JobControlDependency:
    """Require one prerequisite job to finish before another starts.

    Attributes:
        target_job_id: Dependent job identifier.
        prerequisite_job_id: Prerequisite job identifier.
    """

    target_job_id: uuid.UUID
    prerequisite_job_id: uuid.UUID


@dataclasses.dataclass
class JobGraph:
    """Own jobs and their typed data and control edges.

    Attributes:
        graph_id: Unique identifier for the graph. Auto-generated if not provided.
        name: Human-readable name for the graph. Defaults to current timestamp.
        jobs: List of jobs in the graph.
        connections: Typed output-to-input connections.
        literal_inputs: Exact typed literal input bindings.
        control_dependencies: Ordering edges without data transfer.
    """

    graph_id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
    name: str = dataclasses.field(default_factory=_default_job_name)
    jobs: list[Job] = dataclasses.field(default_factory=list)
    connections: list[JobConnection] = dataclasses.field(default_factory=list)
    literal_inputs: list[JobLiteralInput] = dataclasses.field(default_factory=list)
    control_dependencies: list[JobControlDependency] = dataclasses.field(default_factory=list)

    def add_job(self, job: Job) -> None:
        """Add one uniquely identified job to the graph.

        Args:
            job: Job owned by this graph after the call.

        Raises:
            TypeError: If the value is not a job.
            ValueError: If the job or its identifier is already present.
        """
        if not isinstance(job, Job):
            raise TypeError("job must be a Job")
        if any(existing is job or existing.job_id == job.job_id for existing in self.jobs):
            raise ValueError(f"Job {job.job_id} already belongs to the graph")
        self.jobs.append(job)

    def connect(
        self,
        source: JobOutputEndpoint[PortValueT],
        target: JobInputEndpoint[PortValueT],
    ) -> None:
        """Connect one output to one exact typed input.

        Args:
            source: Producer job and its declared output port.
            target: Consumer job and its declared input port.

        Raises:
            TypeError: If port value types do not exactly match.
            ValueError: If a job or port is foreign, the input is bound, or the edge creates a cycle.
        """
        if type(source) is not JobOutputEndpoint or type(target) is not JobInputEndpoint:
            raise TypeError("source and target must be output and input endpoints")
        if source.port.value_type is not target.port.value_type:
            raise TypeError("Connected output and input types must exactly match")
        self._require_job(source.job)
        self._require_job(target.job)
        if source.port not in type(source.job).output_ports:
            raise ValueError(f"Output port {source.port.name} is not declared by {type(source.job).__name__}")
        if target.port not in type(target.job).input_ports:
            raise ValueError(f"Input port {target.port.name} is not declared by {type(target.job).__name__}")
        self._require_unbound(target.job.job_id, target.port)
        connection = JobConnection(source.job.job_id, source.port, target.job.job_id, target.port)
        self.connections.append(connection)
        self._reject_cycle(self.connections.pop)

    def bind(self, target_job: Job, target_port: JobInputPort[Any], literal_value: Any) -> None:
        """Bind one literal value to an exact typed input.

        Args:
            target_job: Consumer owned by this graph.
            target_port: Declared consumer input port.
            literal_value: Value whose concrete type must exactly match the port.

        Raises:
            TypeError: If the literal type does not exactly match.
            ValueError: If the job or port is foreign or the input is already bound.
        """
        if not isinstance(target_job, Job):
            raise TypeError("target_job must be a Job")
        if type(target_port) is not JobInputPort:
            raise TypeError("target_port must be a JobInputPort")
        self._require_job(target_job)
        if target_port not in type(target_job).input_ports:
            raise ValueError(f"Input port {target_port.name} is not declared by {type(target_job).__name__}")
        if not value_matches_type(literal_value, target_port.value_type):
            raise TypeError(f"Literal for {target_port.name} must be exactly {target_port.value_type.__name__}")
        self._require_unbound(target_job.job_id, target_port)
        self.literal_inputs.append(JobLiteralInput(target_job.job_id, target_port, literal_value))

    def depends_on(self, target_job: Job, prerequisite_job: Job) -> None:
        """Add one control dependency between jobs owned by this graph.

        Args:
            target_job: Job that must wait.
            prerequisite_job: Job that must finish first.

        Raises:
            ValueError: If either job is foreign, the edge exists, or the edge creates a cycle.
        """
        if not isinstance(target_job, Job) or not isinstance(prerequisite_job, Job):
            raise TypeError("target_job and prerequisite_job must be Job values")
        self._require_job(target_job)
        self._require_job(prerequisite_job)
        dependency = JobControlDependency(target_job.job_id, prerequisite_job.job_id)
        if dependency in self.control_dependencies:
            raise ValueError("Control dependency already exists")
        self.control_dependencies.append(dependency)
        self._reject_cycle(self.control_dependencies.pop)

    def iter_jobs(self) -> Iterator[Job]:
        """Yield jobs in topological order based on dependencies.

        Jobs with no dependencies come first, followed by jobs whose dependencies
        have all been yielded. This ensures that when jobs are submitted to the
        queue in this order, dependencies are always available.

        Yields:
            Jobs in execution-safe order.

        Raises:
            RuntimeError: If identifiers are duplicated, a dependency is missing, or a cycle is detected.
        """
        self.validate()
        job_map = {job.job_id: job for job in self.jobs}
        if len(job_map) != len(self.jobs):
            raise RuntimeError("JobGraph contains duplicate job IDs")

        job_positions = {job.job_id: position for position, job in enumerate(self.jobs)}
        sorter = graphlib.TopologicalSorter(self._predecessors())
        try:
            sorter.prepare()
            while sorter.is_active():
                ready_job_ids = tuple(sorted(sorter.get_ready(), key=lambda job_id: job_positions[job_id]))
                for job_id in ready_job_ids:
                    yield job_map[job_id]
                sorter.done(*ready_job_ids)
        except graphlib.CycleError as error:
            raise RuntimeError("Cycle detected in job dependencies") from error

    def validate(self) -> None:
        """Validate graph ownership, bindings, and combined edge acyclicity.

        Raises:
            RuntimeError: If jobs are duplicated, inputs are unbound, or an edge is invalid.
        """
        if type(self.graph_id) is not uuid.UUID:
            raise RuntimeError("graph_id must be a uuid.UUID")
        if type(self.name) is not str or not self.name.strip():
            raise RuntimeError("name must be a non-empty string")
        collections = (
            (self.jobs, Job, "jobs"),
            (self.connections, JobConnection, "connections"),
            (self.literal_inputs, JobLiteralInput, "literal_inputs"),
            (self.control_dependencies, JobControlDependency, "control_dependencies"),
        )
        for values, value_type, field_name in collections:
            if type(values) is not list or not all(isinstance(value, value_type) for value in values):
                raise RuntimeError(f"{field_name} must be a list of {value_type.__name__} values")
        for job in self.jobs:
            try:
                job.validate()
            except (TypeError, ValueError) as error:
                raise RuntimeError(str(error)) from error
        job_map = {job.job_id: job for job in self.jobs}
        if len(job_map) != len(self.jobs):
            raise RuntimeError("JobGraph contains duplicate job IDs")
        if len(self.control_dependencies) != len(set(self.control_dependencies)):
            raise RuntimeError("JobGraph contains duplicate control dependencies")
        try:
            bindings_by_job: dict[uuid.UUID, list[JobInputPort[Any]]] = {job_id: [] for job_id in job_map}
            for connection in self.connections:
                source = job_map[connection.source_job_id]
                target = job_map[connection.target_job_id]
                if (
                    connection.source_port not in type(source).output_ports
                    or connection.target_port not in type(target).input_ports
                ):
                    raise ValueError("Connection uses an undeclared port")
                if connection.source_port.value_type is not connection.target_port.value_type:
                    raise TypeError("Connected output and input types must exactly match")
                bindings_by_job[connection.target_job_id].append(connection.target_port)
            for binding in self.literal_inputs:
                target = job_map[binding.job_id]
                if binding.port not in type(target).input_ports:
                    raise ValueError("Literal binding uses an undeclared port")
                if not value_matches_type(binding.value, binding.port.value_type):
                    raise TypeError("Literal binding has the wrong concrete type")
                bindings_by_job[binding.job_id].append(binding.port)
            for dependency in self.control_dependencies:
                if dependency.target_job_id not in job_map or dependency.prerequisite_job_id not in job_map:
                    raise KeyError("Control dependency references a job outside this graph")
            for job in self.jobs:
                bindings = bindings_by_job[job.job_id]
                if len(bindings) != len(set(bindings)):
                    raise ValueError(f"Job {job.job_id} has an input bound more than once")
                missing = [port.name for port in type(job).input_ports if port not in bindings]
                if missing:
                    raise ValueError(f"Job {job.job_id} has unbound inputs: {', '.join(missing)}")
            graphlib.TopologicalSorter(self._predecessors()).prepare()
        except (graphlib.CycleError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError(str(error)) from error

    def _require_job(self, job: Job) -> None:
        """Require an exact job object owned by this graph.

        Args:
            job: Candidate owned job.

        Raises:
            ValueError: If the exact object does not belong to this graph.
        """
        if not isinstance(job, Job):
            raise TypeError("job must be a Job")
        if not any(owned is job for owned in self.jobs):
            raise ValueError(f"Job {job.job_id} does not belong to this graph")

    def _job_by_id(self, job_id: uuid.UUID) -> Job:
        """Return one owned job by identifier.

        Args:
            job_id: Identifier to resolve.

        Returns:
            Owned job.

        Raises:
            KeyError: If no owned job has the identifier.
        """
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        raise KeyError(f"Job {job_id} does not belong to this graph")

    def _require_unbound(self, job_id: uuid.UUID, port: JobInputPort[Any]) -> None:
        """Require one input to have no existing literal or connection.

        Args:
            job_id: Consumer job identifier.
            port: Consumer input port.

        Raises:
            ValueError: If the input already has a binding.
        """
        if any(
            connection.target_job_id == job_id and connection.target_port == port for connection in self.connections
        ) or any(binding.job_id == job_id and binding.port == port for binding in self.literal_inputs):
            raise ValueError(f"Input {port.name} is already bound")

    def _predecessors(self) -> dict[uuid.UUID, set[uuid.UUID]]:
        """Return combined data and control predecessors for all jobs.

        Returns:
            Predecessor identifiers keyed by dependent job identifier.
        """
        predecessors = {job.job_id: set() for job in self.jobs}
        for connection in self.connections:
            predecessors[connection.target_job_id].add(connection.source_job_id)
        for dependency in self.control_dependencies:
            predecessors[dependency.target_job_id].add(dependency.prerequisite_job_id)
        return predecessors

    def _reject_cycle(self, undo: Callable[[], Any]) -> None:
        """Undo the latest edge and reject it when it creates a cycle.

        Args:
            undo: Callback that removes the latest tentative edge.

        Raises:
            ValueError: If the latest edge creates a cycle.
        """
        try:
            graphlib.TopologicalSorter(self._predecessors()).prepare()
        except graphlib.CycleError as error:
            undo()
            raise ValueError("Graph edge creates a cycle") from error
