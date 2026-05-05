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

import collections
import dataclasses
import datetime
import uuid
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from collections.abc import Callable, Iterator

import omni.flux.job_queue.core.events
import omni.flux.job_queue.core.utils

if TYPE_CHECKING:
    import omni.flux.job_queue.core.interface

T = TypeVar("T")


def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclasses.dataclass
class Job(Generic[T]):
    """
    Represents a generic job with dependencies and priority.
    """

    job_id: uuid.UUID = dataclasses.field(default_factory=omni.flux.job_queue.core.utils.uuid7)
    name: str = dataclasses.field(default_factory=now)
    dependencies: set[uuid.UUID] = dataclasses.field(default_factory=set)
    queue: str = "default"
    priority: int = 50

    def __post_init__(self):
        self.validate()

    def add_dependency(self, job_or_job_id: Job | uuid.UUID) -> None:
        """
        Add another job as a dependency to this job.
        """
        if isinstance(job_or_job_id, Job):
            self.dependencies.add(job_or_job_id.job_id)
        elif isinstance(job_or_job_id, uuid.UUID):
            self.dependencies.add(job_or_job_id)
        else:
            raise TypeError("job must be a Job or uuid.UUID")

    def validate(self) -> None:
        # Ensures users don't accidentally pass arguments and override these fields on subclass types.
        assert isinstance(self.job_id, uuid.UUID)
        assert all(isinstance(x, uuid.UUID) for x in self.dependencies)
        assert isinstance(self.priority, int)

    def pre_schedule(self, interface: omni.flux.job_queue.core.interface.QueueInterface) -> None:
        """
        Hook called by JobScheduler before the job is sent to the JobExecutor.
        """
        pass

    def post_schedule(self, interface: omni.flux.job_queue.core.interface.QueueInterface) -> None:
        """
        Hook called by JobScheduler after the job is sent to the JobExecutor.
        """
        pass

    def pre_execute(self, interface: omni.flux.job_queue.core.interface.QueueInterface) -> None:
        """
        Hook called by JobExecutor before the job is executed.
        """
        pass

    def execute(self) -> T:
        """
        Execute the job and return its result.
        """
        raise NotImplementedError

    def post_execute(self, interface: omni.flux.job_queue.core.interface.QueueInterface) -> None:
        """
        Hook called by JobExecutor after the job is executed.
        """
        pass


@dataclasses.dataclass
class CallableJob(Job[T]):
    """
    Job that wraps a callable function.
    """

    func: Callable[..., T] | None = dataclasses.field(default=None)
    args: tuple[Any, ...] = dataclasses.field(default_factory=tuple)
    kwargs: dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self):
        super().validate()
        assert callable(self.func), "func must be callable"
        assert isinstance(self.args, tuple)
        assert isinstance(self.kwargs, dict)

    def execute(self) -> T:
        """
        Execute the wrapped function with provided arguments.
        """
        if not self.func:
            raise ValueError("No function provided for CallableJob.")
        return self.func(*self.args, **self.kwargs)


@dataclasses.dataclass
class JobGraph:
    """
    A collection of Job instances with an interface to submit to a queue.

    Jobs within a graph can have dependencies on each other. The graph ensures
    jobs are submitted in topological order and validates for cycles.

    Attributes:
        interface: The queue interface to submit jobs to.
        graph_id: Unique identifier for the graph. Auto-generated if not provided.
        name: Human-readable name for the graph. Defaults to current timestamp.
        jobs: List of jobs in the graph.
        submitted: Whether the graph has been submitted to the queue.
    """

    interface: omni.flux.job_queue.core.interface.QueueInterface
    graph_id: uuid.UUID = dataclasses.field(default_factory=omni.flux.job_queue.core.utils.uuid7)
    name: str = dataclasses.field(default_factory=now)
    jobs: list[Job] = dataclasses.field(default_factory=list)
    submitted: bool = dataclasses.field(default=False)

    def add_job(self, job: Job) -> None:
        if self.submitted:
            raise RuntimeError("Cannot add jobs to a submitted JobGraph.")
        jobs_ids = {j.job_id for j in self.jobs}
        if job.job_id in jobs_ids:
            raise ValueError(f"Job with id {job.job_id} already exists in the graph.")
        self.jobs.append(job)

    def submit(self) -> list[omni.flux.job_queue.core.interface.QueueJob]:
        """
        Add all jobs in this graph to the queue.
        """
        # Scoped import to avoid circular dependencies
        import omni.flux.job_queue.core.interface  # noqa: PLC0415

        if self.submitted:
            raise RuntimeError("JobGraph has already been submitted.")
        if not self.jobs:
            raise RuntimeError("JobGraph has no jobs to submit.")

        self.validate()
        self.interface.submit(self)
        self.submitted = True

        results: list[omni.flux.job_queue.core.interface.QueueJob] = []
        for job in self.iter_jobs():
            results.append(
                omni.flux.job_queue.core.interface.QueueJob(
                    interface=self.interface,
                    graph_id=self.graph_id,
                    graph_name=self.name,
                    job_id=job.job_id,
                )
            )
        return results

    def iter_jobs(self) -> Iterator[Job]:
        """
        Yield jobs in topological order based on dependencies.

        Jobs with no dependencies come first, followed by jobs whose dependencies
        have all been yielded. This ensures that when jobs are submitted to the
        queue in this order, dependencies are always available.

        Yields:
            Jobs in execution-safe order.

        Raises:
            RuntimeError: If a cycle is detected or a dependency is missing.
        """
        # Map job_id to Job
        job_map = {job.job_id: job for job in self.jobs}
        # Build dependency graph and in-degree count
        graph: collections.defaultdict[uuid.UUID, list[uuid.UUID]] = collections.defaultdict(list)
        in_degree = {job.job_id: 0 for job in self.jobs}
        for job in self.jobs:
            for dep_id in job.dependencies:
                if dep_id not in job_map:
                    # We could support this in the future allowing for submitting jobs that depend on jobs
                    # already submitted to the queue.
                    raise RuntimeError(f"Job {job.job_id} depends on missing job {dep_id}")
                graph[dep_id].append(job.job_id)
                in_degree[job.job_id] += 1
        queue = collections.deque([job_id for job_id, deg in in_degree.items() if deg == 0])
        visited = 0
        while queue:
            job_id = queue.popleft()
            yield job_map[job_id]
            visited += 1
            for dependent_id in graph[job_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)
        if visited != len(self.jobs):
            raise RuntimeError("Cycle detected in job dependencies")

    def validate(self):
        """
        Validate the job graph for missing dependencies and circular dependencies.
        Raises RuntimeError if a cycle is detected or a dependency is missing.
        """
        for _ in self.iter_jobs():
            pass
