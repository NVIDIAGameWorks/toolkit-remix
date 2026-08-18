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

from __future__ import annotations

import dataclasses
import traceback

__all__ = ("ApplyExecutionError", "JobError", "JobExecutionError", "QueueSubmissionError")


class _ExecutionError(Exception):
    """Carry explicit user-facing text beside an underlying diagnostic."""

    def __init__(self, reason: str, diagnostic: Exception) -> None:
        """Create one domain failure.

        Args:
            reason: Safe, actionable text suitable for queue UI.
            diagnostic: Underlying exception retained in durable diagnostic fields.

        Raises:
            TypeError: If either value has the wrong type.
            ValueError: If the user-facing reason is blank.
        """
        if type(reason) is not str:
            raise TypeError("reason must be a string")
        if not reason.strip():
            raise ValueError("reason must not be blank")
        if not isinstance(diagnostic, Exception):
            raise TypeError("diagnostic must be an Exception")
        super().__init__(reason)
        self.reason = reason
        self.diagnostic = diagnostic


class ApplyExecutionError(_ExecutionError):
    """Carry explicit user-facing Apply text beside an underlying diagnostic."""


class JobExecutionError(_ExecutionError):
    """Carry explicit user-facing execution text beside an underlying diagnostic."""


class QueueSubmissionError(RuntimeError):
    """Raised when a job graph cannot be validated or persisted atomically."""


@dataclasses.dataclass(frozen=True)
class JobError:
    """Store one execution or Apply failure for later inspection."""

    exception_type: str
    message: str
    traceback: str

    @classmethod
    def from_exception(cls, error: BaseException) -> JobError:
        """Capture serializable details from an exception.

        Args:
            error: Exception whose type, message, and traceback should be captured.

        Returns:
            Durable failure details safe to read after restart.
        """
        return cls(
            exception_type=type(error).__name__,
            message=str(error),
            traceback="".join(traceback.format_exception(error)),
        )

    def reraise(self) -> None:
        """Raise a runtime error containing the stored failure details.

        Raises:
            RuntimeError: Always, with the original type name, message, and traceback.
        """
        raise RuntimeError(f"{self.exception_type}: {self.message}\nTraceback:\n{self.traceback}")
