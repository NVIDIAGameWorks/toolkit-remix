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

import abc
from typing import ClassVar, Generic, TypeVar

from omni.flux.factory.base import PluginBase

from .enums import ApplyOperation, ApplyPolicy

__all__ = ("ApplyHandler",)

ApplyInputT = TypeVar("ApplyInputT")
ApplyTargetT = TypeVar("ApplyTargetT")
ApplyReceiptT = TypeVar("ApplyReceiptT")


class ApplyHandler(PluginBase, Generic[ApplyInputT, ApplyTargetT, ApplyReceiptT], abc.ABC):
    """Apply and revert one exact typed job output against one exact target."""

    name: ClassVar[str]
    input_type: ClassVar[type]
    target_type: ClassVar[type]
    receipt_type: ClassVar[type]
    apply_policy: ClassVar[ApplyPolicy] = ApplyPolicy.FOLLOW_GLOBAL

    def get_apply_block_reason(self, target: ApplyTargetT, operation: ApplyOperation) -> str | None:
        """Return why the current environment cannot safely run an Apply operation.

        Handlers use this preflight only for transient external requirements such as the exact project being open.
        Apply and Revert must still validate their targets immediately before mutation.

        Args:
            target: Exact typed product target.
            operation: Exact Apply, Reapply, or Revert operation being considered.

        Returns:
            User-facing recovery guidance, or ``None`` when Apply can run.
        """
        del target, operation
        return None

    @abc.abstractmethod
    async def capture_receipt(self, value: ApplyInputT, target: ApplyTargetT) -> ApplyReceiptT:
        """Capture durable pre-mutation state without changing the target.

        Args:
            value: Exact typed job output.
            target: Exact typed product target.

        Returns:
            Exact typed durable receipt.

        Raises:
            NotImplementedError: Until a concrete product handler implements receipt capture.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def apply(self, value: ApplyInputT, target: ApplyTargetT, receipt: ApplyReceiptT) -> None:
        """Idempotently apply an output using its durable pre-mutation receipt.

        Args:
            value: Exact typed job output.
            target: Exact typed product target.
            receipt: Receipt durably stored before the first Apply attempt.

        Raises:
            NotImplementedError: Until a concrete product handler implements Apply.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def revert(self, value: ApplyInputT, target: ApplyTargetT, receipt: ApplyReceiptT) -> None:
        """Idempotently restore the pre-Apply target using its durable receipt.

        Implementations must also restore any partial mutation left by a failed Apply attempt.

        Args:
            value: Exact typed job output.
            target: Exact typed product target.
            receipt: Receipt durably stored before the first Apply attempt.

        Raises:
            NotImplementedError: Until a concrete product handler implements Revert.
        """
        raise NotImplementedError
