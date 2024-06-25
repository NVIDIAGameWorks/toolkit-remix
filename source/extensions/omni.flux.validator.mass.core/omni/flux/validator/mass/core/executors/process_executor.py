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

import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import carb
import carb.settings
import carb.tokens
import omni.client
import omni.kit.app
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.validator.manager.core import EXTS_MASS_VALIDATOR_SERVICE_PREFIX as _EXTS_MASS_VALIDATOR_SERVICE_PREFIX
from omni.flux.validator.manager.core import (
    EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_HOST as _EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_HOST,
)
from omni.flux.validator.manager.core import (
    EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_PORT as _EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_PORT,
)
from omni.flux.validator.manager.core import validation_schema_json_encoder as _validation_schema_json_encoder

from .base_executor import BaseExecutor as _BaseExecutor

if TYPE_CHECKING:
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore


OVERRIDE_EXPERIENCE = (
    "/exts/omni.flux.validator.mass.core/override_process_experience"  # list of paths of schema separated by a coma
)


class ProcessExecutor(_BaseExecutor):

    _EXECUTOR = None

    def __init__(self, max_concurrent=None):
        """
        Executor that will run job in async locally.

        Args:
            max_concurrent: number of job(s) we would want to run concurrently
        """
        super().__init__(max_concurrent=max_concurrent)
        self.__settings = carb.settings.get_settings()
        if self._EXECUTOR is None:
            self._EXECUTOR = _ThreadPoolExecutor(max_workers=self._max_concurrent)

    def _worker(
        self,
        core: "_ManagerCore",
        print_result: bool = False,
        silent: bool = False,
        timeout: Optional[int] = None,
        standalone: Optional[bool] = False,
        queue_id: str | None = None,
    ):
        exe_ext = carb.tokens.get_tokens_interface().resolve("${exe_ext}")
        kit_folder = carb.tokens.get_tokens_interface().resolve("${kit}")
        kit_path = Path(kit_folder) / f"kit{exe_ext}"
        app_filename = carb.tokens.get_tokens_interface().resolve("${app_filename}")

        override_experience = carb.settings.get_settings().get(OVERRIDE_EXPERIENCE)
        if override_experience:
            experience_path = carb.tokens.get_tokens_interface().resolve(override_experience)
        else:
            # grab the default experience
            app = carb.tokens.get_tokens_interface().resolve("${omni.flux.validator.mass.core}")
            experience_path = Path(app) / "apps" / "omni.flux.app.validator.mass_cli.kit"

        validator_cli_root_ext = carb.tokens.get_tokens_interface().resolve("${omni.flux.validator.manager.core}")
        exec_cmd = f"{Path(validator_cli_root_ext).joinpath('omni', 'flux', 'validator', 'manager', 'core', 'cli.py')}"

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp_file:
            jsonfile = tmp_file.name
        try:  # noqa PLR1702
            # for standalone, we don't need to send a request to a micro service
            core.model.send_request = not standalone
            _path_utils.write_file(
                jsonfile,
                core.model.json(indent=4, encoder=_validation_schema_json_encoder).encode("utf-8"),
                raise_if_error=True,
            )
            cmd = [f'"{str(kit_path)}"', f'"{str(experience_path)}"', "--no-window"]
            extra_args = sys.argv[2:] if len(sys.argv) >= 2 else []
            ignore_arg = False
            for extra_arg in extra_args:
                # if this is the standalone, we delete args between --start-future-args-remove and
                # --end-future-args-remove
                if app_filename == "omni.flux.app.validator.mass_cli":
                    if extra_arg == "--start-future-args-remove":
                        ignore_arg = True
                    if extra_arg == "--end-future-args-remove":
                        ignore_arg = False
                        continue
                    if ignore_arg:
                        continue
                cmd.append(f'"{extra_arg}"')
            sub_cmd = [f'\\"{exec_cmd}\\"']
            sub_cmd.extend(["-s", rf"\"{Path(jsonfile).resolve()}\""])
            if print_result:
                sub_cmd.append("-p")
            if queue_id:
                sub_cmd.extend(["-q", queue_id])

            sub_cmd_str = " ".join(sub_cmd)

            # remove error: <_overlapped.Overlapped object at 0x000002694A2C4B70> still has pending operation at
            # deallocation, the process may crash
            cmd.append("--/exts/omni.kit.async_engine/event_loop_windows=SelectorEventLoop")

            host = self.__settings.get(_EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_HOST)
            port = self.__settings.get(_EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_PORT)

            cmd.append(f"--{_EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_HOST}={host}")
            cmd.append(f"--{_EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_PORT}={port}")

            prefix = self.__settings.get(_EXTS_MASS_VALIDATOR_SERVICE_PREFIX)

            if prefix:
                cmd.append(f"--{_EXTS_MASS_VALIDATOR_SERVICE_PREFIX}={prefix}")

            cmd.extend(["--exec", f'"{sub_cmd_str}"'])

            print(f"Run {' '.join(cmd)}")

            try:
                prev_stdout = None
                p = subprocess.run(  # noqa PLW1510
                    " ".join(cmd),
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout,
                    input=prev_stdout,
                )
                prev_stdout = p.stdout
                if not silent:
                    for line in prev_stdout.split("\n"):
                        print(line)

                message = "Ok"
                if p.stderr:
                    message = ""
                    for line in p.stderr.split("\n"):
                        message += f"{line}\n"  # noqa PLR1713
                result = p.returncode == 0
                if not silent:
                    # Use print to print the stderr if the result is good (carb.log_info doesn't show in the
                    # stdout anymore). If not, we use carb.log_error
                    if result:
                        print(message)
                    else:
                        carb.log_error(message)
            except subprocess.TimeoutExpired:
                result = False
                message = f"Time out expired ({timeout}sc)"
                carb.log_error(message)
        except Exception:  # noqa PLW0718
            result = False
            message = str(traceback.format_exc())
            carb.log_error(message)
        finally:
            omni.client.delete(jsonfile)

        return result, message

    def submit(
        self,
        core: "_ManagerCore",
        print_result: bool = False,
        silent: bool = False,
        timeout: Optional[int] = None,
        standalone: Optional[bool] = False,
        queue_id: str | None = None,
    ):
        return self._EXECUTOR.submit(
            self._worker,
            core,
            print_result=print_result,
            silent=silent,
            timeout=timeout,
            standalone=standalone,
            queue_id=queue_id,
        )
