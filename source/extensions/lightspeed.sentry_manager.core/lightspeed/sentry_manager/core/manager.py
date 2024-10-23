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

import time
from functools import wraps

import carb
import sentry_sdk
from lightspeed.trex.utils.common.user_utils import get_user_key as _get_user_key

ELAPSED_TIME_METRIC_TYPE = "app_elapsed_seconds"
METRICS_MESSAGE_TOPIC = "RemixMetrics"
TIMING_METRIC_TYPE = "timing"


class SentryManager:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()

    def app_closing(self):
        """Post the overall elapsed time"""
        carb.log_info("[omni.flux.entry.manager] Shutdown")
        elapsed = int(round(time.time() - self.start_time, 0))
        self.post_metric(ELAPSED_TIME_METRIC_TYPE, value=elapsed, tags=None)

    def post_metric(self, event_type: str, value: int | None = None, tags: dict | None = None) -> None:
        """Public interface for sending a metric value to Sentry for metric reporting"""
        # The context will be attached to all events captured within this scope
        with sentry_sdk.push_scope() as scope:
            scope.set_context(event_type, {"event_type": event_type, "value": value, "tags": tags})
            sentry_sdk.set_tag("user_key", _get_user_key())
            sentry_sdk.capture_message(METRICS_MESSAGE_TOPIC)

    def timeit(self, fnc):
        """Decorator to add timing metrics to a function"""

        @wraps(fnc)
        def wrapped(*args, **kwargs):
            start_time = time.time()
            ret = fnc(*args, **kwargs)
            self.post_metric(
                TIMING_METRIC_TYPE,
                value=time.time() - start_time,
                tags={"module": fnc.__module__, "name": fnc.__name__},
            )
            return ret

        return wrapped
