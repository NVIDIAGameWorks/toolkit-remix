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

import dataclasses
import traceback
from typing import TYPE_CHECKING, Any, TypeVar

import omni.flux.job_queue.core.utils

if TYPE_CHECKING:
    import omni.flux.job_queue.core.interface


ErrorT = TypeVar("ErrorT", bound="Error")


@dataclasses.dataclass
class JobEvent:
    """
    Base class for all job events.
    """

    @omni.flux.job_queue.core.utils.classproperty
    def name(cls) -> str:  # noqa: N805
        return cls.__name__


@dataclasses.dataclass
class StateChange(JobEvent):
    """
    Event representing a change in job state.
    """

    value: omni.flux.job_queue.core.interface.JobState


@dataclasses.dataclass
class Result(JobEvent):
    """
    Event representing a job result.
    """

    value: Any


@dataclasses.dataclass
class Error(JobEvent):
    """
    Event representing an error in job execution.

    Attributes:
        exc_type: Fully-qualified class name of the exception (e.g., "builtins.ValueError").
        exc_value: String representation of the exception message.
        traceback_str: Full traceback formatted as a string.
    """

    exc_type: str
    exc_value: str
    traceback_str: str

    @classmethod
    def from_exception(cls, e: Exception) -> ErrorT:
        """
        Alternate constructor to create an Error event from an exception.
        """
        return cls(
            exc_type=omni.flux.job_queue.core.utils.get_dotted_import_path(e),
            exc_value=str(e),
            traceback_str="".join(traceback.format_exception(type(e), e, e.__traceback__)),
        )

    def reraise(self) -> None:
        """
        Reraise the exception represented by this Error event.
        """
        exc_class = omni.flux.job_queue.core.utils.import_type_from_path(self.exc_type)
        if not callable(exc_class):
            raise TypeError(f"Exception class {self.exc_type} is not callable")
        try:
            exc = exc_class(f"{self.exc_value}\nTraceback:\n{self.traceback_str}")
        except Exception:  # noqa: BLE001
            # If we can't instantiate the original exception class, raise a RuntimeError instead.
            raise RuntimeError(f"{self.exc_value}\nTraceback:\n{self.traceback_str}")  # noqa: B904
        raise exc
