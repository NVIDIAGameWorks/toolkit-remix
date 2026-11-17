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

__all__ = ("JobResultNotifier", "post_submission_notification")

import asyncio
from collections.abc import Callable, Sequence
from uuid import UUID

from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.enums import TERMINAL_JOB_STATES, JobState
from omni.flux.job_queue.core.job import JobGraph
from omni.flux.job_queue.core.models import QueueJobSnapshot
from omni.kit.notification_manager import NotificationButtonInfo, NotificationStatus, post_notification
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager


def post_submission_notification(
    submitted_count: int,
    skip_reasons: Sequence[str],
    button_infos: list[NotificationButtonInfo] | None = None,
) -> None:
    """Report the submitted job count and the first skip reason.

    A submission without jobs is an error, so it shows a modal dialog. Kit notifications have no error status.
    """
    skipped = f"{len(skip_reasons)} item(s) were skipped: {skip_reasons[0]}" if skip_reasons else ""
    if not submitted_count:
        PromptManager.post_simple_prompt(
            "No Jobs Created",
            f"No jobs were added to the job queue.\n\n{skipped}".strip(),
            ok_button_info=PromptButtonInfo("Okay", None),
            cancel_button_info=None,
            modal=True,
        )
        return
    post_notification(
        f"Submitted {submitted_count} job(s) to the job queue. {skipped}".strip(),
        status=NotificationStatus.WARNING if skip_reasons else NotificationStatus.INFO,
        button_infos=button_infos,
    )


class JobResultNotifier:
    """Post one terminal result for each job registered during this extension's lifetime."""

    def __init__(self) -> None:
        """Subscribe to the shared queue and deliver results on the current event loop."""
        self._queue = get_job_queue()
        self._loop = asyncio.get_event_loop()
        self._jobs: dict[UUID, tuple[str, Callable[[UUID], str | None] | None, Callable[[str], None] | None]] = {}
        self._destroyed = False
        self._subscription = self._queue.subscribe_job_changed(self._on_job_changed)
        self._mutation_subscription = self._queue.subscribe_mutation(self._on_queue_mutation)

    def register(
        self,
        job_id: UUID,
        graph_name: str,
        summarize: Callable[[UUID], str | None] | None = None,
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        """Track a job until its result, deletion, or notifier destruction.

        An already-terminal job reports synchronously before this method returns.

        Args:
            job_id: Submitted job whose execution result to report.
            graph_name: Display name used when no summary is available.
            summarize: Callback retained until release and called only for DONE jobs to obtain result text.
            on_result: Callback retained until release and called after the notification with its message.
        """
        if self._destroyed:
            return
        self._jobs[job_id] = (graph_name, summarize, on_result)
        self._report_result(job_id)

    def register_graphs(
        self,
        graphs: Sequence[JobGraph],
        summarize: Callable[[UUID], str | None] | None = None,
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        """Track each graph's first job and ignore graphs that the queue did not accept."""
        for graph in graphs:
            self.register(graph.jobs[0].job_id, graph.name, summarize, on_result)

    def destroy(self) -> None:
        """Release the queue subscriptions and all result callbacks."""
        self._destroyed = True
        self._subscription = None
        self._mutation_subscription = None
        self._jobs.clear()

    def _on_job_changed(self, job_id: UUID) -> None:
        """Move queue events from worker threads to the main loop."""
        if not self._destroyed:
            self._loop.call_soon_threadsafe(self._report_result, job_id)

    def _on_queue_mutation(self) -> None:
        """Move structural queue events from worker threads to the main loop."""
        if not self._destroyed:
            self._loop.call_soon_threadsafe(self._report_pending_results)

    def _report_pending_results(self) -> None:
        """Report completed registrations and release registrations for deleted jobs."""
        if self._destroyed or not self._jobs:
            return
        snapshots = {
            snapshot.job_id: snapshot for snapshot in self._queue.iter_snapshot() if snapshot.job_id in self._jobs
        }
        for job_id in tuple(self._jobs):
            if (snapshot := snapshots.get(job_id)) is None:
                self._jobs.pop(job_id, None)
            else:
                self._report_snapshot(snapshot)

    def _report_result(self, job_id: UUID) -> None:
        """Remove a terminal job before it posts its result."""
        if self._destroyed or job_id not in self._jobs:
            return
        try:
            snapshot = self._queue.get_job_snapshot(job_id)
        except KeyError:
            self._jobs.pop(job_id)
            return
        self._report_snapshot(snapshot)

    def _report_snapshot(self, snapshot: QueueJobSnapshot) -> None:
        """Release a registered terminal job and deliver its result."""
        job_id = snapshot.job_id
        if self._destroyed or job_id not in self._jobs or snapshot.state not in TERMINAL_JOB_STATES:
            return
        graph_name, summarize, on_result = self._jobs.pop(job_id)
        summary = summarize(job_id) if summarize is not None and snapshot.state is JobState.DONE else None
        message = summary or f"{graph_name}: {snapshot.state}"
        post_notification(
            message, status=NotificationStatus.WARNING if snapshot.state is JobState.FAILED else NotificationStatus.INFO
        )
        if on_result is not None:
            on_result(message)
