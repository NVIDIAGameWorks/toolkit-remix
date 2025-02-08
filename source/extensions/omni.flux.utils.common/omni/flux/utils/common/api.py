"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["send_request"]

from functools import partial

import carb
import requests
from omni.flux.utils.common import async_wrap


async def send_request(method: str, endpoint: str, **kwargs) -> dict:
    """
    Send an HTTP request to a server.

    The server's address will be taken from the `omni.services.transport.server.http` settings.

    Args:
        method: HTTP method to use
        endpoint: HTTP endpoint to send the request to
        **kwargs: Additional keyword arguments to pass to the `requests.request` function

    Raises:
        RuntimeError: If the request fails

    Returns:
        The JSON response from the server
    """

    try:
        host = carb.settings.get_settings().get("/exts/omni.services.transport.server.http/host")
        port = carb.settings.get_settings().get("/exts/omni.services.transport.server.http/port")

        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        response = await async_wrap(partial(requests.request, method, f"http://{host}:{port}{endpoint}", **kwargs))()

        response.raise_for_status()
        return response.json()
    except (
        requests.RequestException,
        requests.ConnectionError,
        requests.HTTPError,
        requests.URLRequired,
        requests.TooManyRedirects,
        requests.ConnectTimeout,
        requests.ReadTimeout,
        requests.Timeout,
        requests.JSONDecodeError,
    ) as e:
        raise RuntimeError from e
