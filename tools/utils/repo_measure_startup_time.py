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
import email
import os
import statistics
import subprocess
import sys
import time

import requests


CRASH_RETURN_CODE = -1
TIMEOUT_RETURN_CODE = -2


def _send_alert(body, webhook_url):
    """Post the results to the specified Slack channel's webhook"""
    response = requests.post(webhook_url, json={"text": body})
    if response.status_code >= 300:
        print("Webhook post failed")
        print(f"Got response: {response.status_code}")
        print(f"Content: {response.content}")
        sys.exit(2)


def _run_app_timer(app_command, time_limit):
    """
    Measure the time it takes to start up the application.

    If the app takes much longer than `time_limit`, return TIMEOUT_RETURN_CODE.

    If the app crashes, kill the process and return CRASH_RETURN_CODE.

    Otherwise, return the startup time in seconds.
    """
    start = time.time()
    # Add to the time limit so we can record times that are slightly over. They will still show up as failures.
    timeout_time = start + (4 * time_limit)
    proc = subprocess.Popen(app_command)
    try:
        proc.wait(timeout=time_limit)
    except subprocess.TimeoutExpired:
        print(f"Subprocess timeout exceeded; killinig PID={proc.pid}")
        os.system(f"taskkill /F /PID {proc.pid}")
        return TIMEOUT_RETURN_CODE
    if proc.returncode != 0:
        return CRASH_RETURN_CODE
    return round(time.time() - start, 2)


def setup_repo_tool(parser, _):
    parser.prog = "measure_startup_time"
    parser.description = (
        "Build the app, then run in a loop to measure the startup times."
    )
    parser.add_argument(
        "-t",
        "--time_limit",
        dest="time_limit",
        required=False,
        help="Maximum number of seconds to start the app without generating a warning",
    )
    parser.add_argument(
        "-c",
        "--count",
        dest="count",
        required=False,
        help="Number of times to run the app",
    )
    parser.add_argument(
        "-w",
        "--webhook_url",
        dest="webhook_url",
        required=True,
        help="URL to post results to Slack",
    )

    def run_repo_tool(options, config):
        settings = config["repo_measure_startup_time"]
        app_command = settings["app_command"]
        time_limit = settings["time_limit"]
        number = settings["number"]

        timings = [_run_app_timer(app_command, time_limit) for _ in range(number)]
        num_timeouts = len([tm for tm in timings if tm == TIMEOUT_RETURN_CODE])
        num_crashes = len([tm for tm in timings if tm == CRASH_RETURN_CODE])
        good_timings = [round(tm, 2) for tm in timings if tm > 0] or [-1]
        print("          Run  Time")
        for i, tm in enumerate(timings):
            run_number = i + 1
            if tm < 0:
                print(
                    f"{str(run_number).rjust(12)}: <{'timed out' if tm == TIMEOUT_RETURN_CODE else 'crashed'}>"
                )
                continue
            strtm = "%00.2f" % tm
            print(f"{str(run_number).rjust(12)}: {strtm.rjust(6)}")

        average_time = round(statistics.fmean(good_timings), 2)
        max_time = max(good_timings)
        min_time = min(good_timings)
        too_slow = (average_time > time_limit) or (num_timeouts > number / 4)
        results = f"""
      Average time: {average_time}
           Longest: {round(max(good_timings) ,2)}
          Shortest: {round(min(good_timings), 2)}
    Number of runs: {number}
Number of timeouts: {num_timeouts}
 Number of crashes: {num_crashes}
"""
        print(results)

        if too_slow:
            body = f"```{results}```"
            _send_alert(body=body, webhook_url=options.webhook_url)

        sys.exit(1 if too_slow else 0)

    return run_repo_tool
