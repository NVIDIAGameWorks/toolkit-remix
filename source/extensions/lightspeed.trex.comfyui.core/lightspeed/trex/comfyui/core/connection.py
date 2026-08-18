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

__all__ = ["get_connected_endpoint", "set_connected_endpoint"]

import threading

from omni.flux.job_queue.core import get_job_queue

from .url import Endpoint, canonical_endpoint

_CONNECTED_ENDPOINTS: dict[str, Endpoint] = {}
_CONNECTED_ENDPOINTS_LOCK = threading.Lock()


def get_connected_endpoint(context_name: str) -> Endpoint | None:
    """Return the verified ComfyUI endpoint for a USD context.

    Args:
        context_name: USD context whose connection is queried.

    Returns:
        Canonical connected endpoint, or None if the context is disconnected.
    """
    with _CONNECTED_ENDPOINTS_LOCK:
        return _CONNECTED_ENDPOINTS.get(context_name)


def set_connected_endpoint(context_name: str, endpoint: Endpoint | None) -> None:
    """Store or clear the verified ComfyUI endpoint for a USD context.

    Args:
        context_name: USD context whose connection is updated.
        endpoint: Verified endpoint to store, or None to clear it.
    """
    connected_endpoint = canonical_endpoint(*endpoint) if endpoint is not None else None
    with _CONNECTED_ENDPOINTS_LOCK:
        previous_endpoint = _CONNECTED_ENDPOINTS.get(context_name)
        if connected_endpoint is None:
            _CONNECTED_ENDPOINTS.pop(context_name, None)
        else:
            _CONNECTED_ENDPOINTS[context_name] = connected_endpoint

    if connected_endpoint != previous_endpoint:
        get_job_queue().notify_schedule_conditions_changed()
