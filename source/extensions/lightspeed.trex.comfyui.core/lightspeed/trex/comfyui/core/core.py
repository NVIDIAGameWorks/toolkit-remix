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

__all__ = ["ComfyUICore"]

import asyncio
import concurrent.futures
import shutil
import stat
import subprocess
import time
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Callable

import carb
import omni.usd
import requests
import toml
from huggingface_hub import hf_hub_download
from omni.flux.utils.common import Event, EventSubscription
from omni.flux.utils.common.git import (
    GitError,
    clone_repository,
    get_remote_ahead_behind,
    initialize_submodules,
    open_repository,
    pull_repository,
)
from omni.services.transport.server.base import utils

from .enums import ComfyUIState


class ComfyUICore:
    """
    Core class to control a ComfyUI instance.

    **IMPORTANT:** The core must be initialized before it can be used.

    - Initializing the core will also ensure a virtual environment is available.
    - The core can automatically install the dependencies for the ComfyUI Installation and all custom nodes on
      initialization.
    """

    _GIT_URL_SETTING = "/exts/lightspeed.trex.comfyui.core/git/repository"
    _GIT_BRANCH_SETTING = "/exts/lightspeed.trex.comfyui.core/git/branch"
    _TORCH_INDEX_SETTING = "/exts/lightspeed.trex.comfyui.core/pip/torch_index"
    _MODELS_FILE_SETTING = "/exts/lightspeed.trex.comfyui.core/models/requirements_file"
    _MODELS_CACHE_SETTING = "/exts/lightspeed.trex.comfyui.core/models/cache_dir"

    INSTANCE_ADDRESS_SETTING = "/exts/lightspeed.trex.comfyui.core/instance/address"
    INSTANCE_PORT_SETTING = "/exts/lightspeed.trex.comfyui.core/instance/port"
    INSTANCE_START_TIMEOUT_SETTING = "/exts/lightspeed.trex.comfyui.core/instance/start_timeout_s"
    INSTANCE_POLL_INTERVAL_SETTING = "/exts/lightspeed.trex.comfyui.core/instance/poll_interval_s"

    _INSTALL_DIRECTORY_SETTING = "/persistent/exts/lightspeed.trex.comfyui.core/install_directory"

    _VENV_DIRECTORY = ".venv"

    def __init__(self):
        tokens = carb.tokens.get_tokens_interface()

        self._platform = tokens.resolve("${platform}")
        self._exe_ext = tokens.resolve("${exe_ext}")

        self._settings = carb.settings.get_settings()

        self._state = ComfyUIState.NOT_FOUND
        self._update_available = False

        self._run_process = None
        self._repo = None
        self._venv_python = None

        self.__state_changed_event = Event()

    def __del__(self):
        # Stop the running ComfyUI process if active
        self._stop()

        # Close the repository to release any file handles
        if self._repo is not None:
            self._repo.free()

    @property
    def state(self) -> ComfyUIState:
        """
        Get the current state of the ComfyUI Installation.
        """
        return self._state

    @property
    def update_available(self) -> bool:
        """
        Get whether the ComfyUI Installation has an update available.
        """
        return self._update_available

    @omni.usd.handle_exception
    async def initialize(self, repository_directory: str | Path | None = None, open_or_install: bool = True):
        """
        Initialize the ComfyUI Installation in a non-blocking thread.

        Args:
            repository_directory: The directory where ComfyUI should be installed if it doesn't exist.
                                  Leave None to find the previously set repository directory in the settings.
            open_or_install: If True, will attempt to open the repository.
                             If False, will clone the repository if it doesn't exist locally and install all
                             dependencies and download the models.
        """
        origin_url = self._settings.get_as_string(self._GIT_URL_SETTING)
        branch = self._settings.get_as_string(self._GIT_BRANCH_SETTING)
        torch_index = self._settings.get_as_string(self._TORCH_INDEX_SETTING)
        models_file = self._settings.get_as_string(self._MODELS_FILE_SETTING)
        models_cache = self._settings.get_as_string(self._MODELS_CACHE_SETTING)

        install_directory = repository_directory or self._settings.get_as_string(self._INSTALL_DIRECTORY_SETTING)
        if not install_directory:
            carb.log_info(
                "No repository directory found and no repository directory was provided. Aborting initialization."
            )
            return

        if not Path(install_directory).exists():
            carb.log_info(
                f"Repository directory {install_directory} does not exist. Cleaning the repository directory."
            )
            self._settings.set(self._INSTALL_DIRECTORY_SETTING, "")
            return

        if open_or_install:
            initialization_method = partial(self._open_repository, str(install_directory))
        else:
            initialization_method = partial(
                self._clone_repository,
                str(install_directory),
                origin_url,
                branch,
                torch_index,
                models_file,
                models_cache,
            )

        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                await loop.run_in_executor(pool, initialization_method)
        except Exception as e:  # noqa PLW0718
            self._repo = None
            carb.log_error(e)

        if self._repo is None:
            carb.log_error("Failed to initialize the ComfyUI Installation. Cleaning the installation directory.")
            self._settings.set(self._INSTALL_DIRECTORY_SETTING, "")
            self._update_state(ComfyUIState.NOT_FOUND)
            return

        self._settings.set(self._INSTALL_DIRECTORY_SETTING, str(self._repo.workdir))
        self._update_state(ComfyUIState.READY)

    @omni.usd.handle_exception
    async def cleanup(self):
        """
        Cleanup the ComfyUI Installation in a non-blocking thread.
        """
        if self._repo is None:
            carb.log_warn("No ComfyUI Installation found. Aborting cleanup.")
            return

        self._update_state(ComfyUIState.UNINSTALLING)

        repository_path = self._repo.workdir

        self._repo.free()

        self._venv_python = None
        self._repo = None

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                success = await asyncio.get_event_loop().run_in_executor(pool, partial(self._cleanup, repository_path))
        except Exception:  # noqa PLW0718
            success = False

        if not success:
            carb.log_error(f"Failed to cleanup the ComfyUI Installation: {repository_path}")
            self._update_state(ComfyUIState.ERROR)
            return

        self._settings.set(self._INSTALL_DIRECTORY_SETTING, "")

        self._update_state(ComfyUIState.NOT_FOUND)

    @omni.usd.handle_exception
    async def update(self, force: bool = False) -> bool | None:
        """
        Update the ComfyUI Installation in a non-blocking thread.

        Args:
            force: Whether to force the update even if local changes are detected.

        Returns:
            True if the update was successful, False if the update was aborted, or None if the update was not attempted.
        """

        if self._repo is None:
            carb.log_warn("No ComfyUI Installation found. Aborting update.")
            return None

        if not self._update_available:
            carb.log_warn("No update available for ComfyUI. Aborting update.")
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            # The update will return True if the update was successful, False otherwise
            success = await asyncio.get_event_loop().run_in_executor(pool, partial(self._update, force=force))
            if success:
                # Install dependencies and download the models
                await self.initialize(repository_directory=self._repo.workdir, open_or_install=False)
            self._update_available = not success
            self._update_state(ComfyUIState.READY)

        return success

    @omni.usd.handle_exception
    async def refresh(self):
        """
        Refresh the ComfyUI Installation.
        """
        if self._repo is not None:
            self._repo.free()
            self._repo = None

        await self.initialize()

    @omni.usd.handle_exception
    async def run(self, headless: bool = True):
        """
        Run an instance of ComfyUI in a non-blocking thread.

        Args:
            headless: Whether to run the instance in headless mode.
        """
        if self._repo is None:
            raise FileNotFoundError("ComfyUI Installation not found")

        port = self._settings.get_as_int(self.INSTANCE_PORT_SETTING)
        address = self._settings.get_as_string(self.INSTANCE_ADDRESS_SETTING)
        timeout_s = self._settings.get_as_float(self.INSTANCE_START_TIMEOUT_SETTING)
        poll_interval_s = self._settings.get_as_float(self.INSTANCE_POLL_INTERVAL_SETTING)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                await asyncio.get_event_loop().run_in_executor(
                    pool,
                    partial(
                        self._run,
                        headless=headless,
                        address=address,
                        port=port,
                        timeout_s=timeout_s,
                        poll_interval_s=poll_interval_s,
                    ),
                )
        except Exception:
            carb.log_error("An error occurred while running ComfyUI")
            self._update_state(ComfyUIState.ERROR)
            raise

    @omni.usd.handle_exception
    async def stop(self, timeout: float | None = 10.0):
        """
        Stop the running ComfyUI process if active in a non-blocking thread.

        Args:
            timeout: Seconds to wait for graceful termination before killing the process
        """
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                await asyncio.get_event_loop().run_in_executor(pool, partial(self._stop, timeout=timeout))
        except Exception:
            carb.log_error("An error occurred while stopping ComfyUI")
            self._update_state(ComfyUIState.ERROR)
            raise

    @omni.usd.handle_exception
    async def restart(self, headless: bool = True, timeout: float | None = 10.0):
        """
        Restart the running ComfyUI process if active.

        Args:
            headless: Whether to run the instance in headless mode.
            timeout: Seconds to wait for graceful termination before killing the process
        """
        try:
            await self.stop(timeout=timeout)
            await self.run(headless=headless)
        except Exception:
            carb.log_error("An error occurred while restarting ComfyUI")
            self._update_state(ComfyUIState.ERROR)
            raise

    def get_comfyui_directory(self, dirname: str, filename: str) -> str | None:
        """
        Get the ComfyUI directory from a given directory.

        This method also looks at immediate children directories.

        Args:
            dirname: The directory name
            filename: The selected filename (ignored)

        Returns:
            The ComfyUI directory, or None if it is not a ComfyUI directory.
        """
        repository_name = self._settings.get_as_string(self._GIT_URL_SETTING).split("/")[-1][:-4]
        directory = Path(dirname)

        # Check if the directory is a repository or contains the repository
        if directory.name == repository_name and (directory / ".git").exists():
            repository = directory
        else:
            repository = directory / repository_name
            if not repository.exists() or not (repository / ".git").exists():
                return None

        project_file = repository / "pyproject.toml"
        if not project_file.exists():
            return None

        # Read the repository's pyproject.toml file to check if it is a ComfyUI repository
        with open(project_file, "r", encoding="utf-8") as f:
            project_config = toml.load(f)

        return str(repository) if (project_config.get("project", {}).get("name") == "ComfyUI") else None

    def subscribe_state_changed(self, callback: Callable[[ComfyUIState], None]) -> EventSubscription:
        """
        Subscribe to state changes.

        Args:
            callback: The callback to call when the state changes.

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return EventSubscription(self.__state_changed_event, callback)

    def _update_state(self, value: ComfyUIState):
        """
        Update the current state of the ComfyUI Installation.

        This method will trigger the `subscribe_state_changed` callback.

        Args:
            value: The new state of the ComfyUI Installation.
        """
        self._state = value
        self.__state_changed_event(value)

    def _open_repository(self, repository_directory: str | Path):
        """
        Initialize the ComfyUI Installation.

        Args:
            repository_directory: The directory where the ComfyUI Installation is located.
        """
        self._update_state(ComfyUIState.NOT_FOUND)

        # Try to find an existing ComfyUI Installation
        comfyui_directory = self.get_comfyui_directory(str(repository_directory), "")

        # If no existing ComfyUI Installation is found and no origin URL is provided, return None
        if comfyui_directory is None:
            carb.log_error("No existing ComfyUI Installation found")
            self._update_state(ComfyUIState.ERROR)
            return

        # Open existing ComfyUI Installation
        self._update_state(ComfyUIState.FOUND)
        self._repo = open_repository(repo_root=str(comfyui_directory), validation_callback=self._validate_repo)
        if self._repo is None:
            return

        # Setup virtual environment for the new ComfyUI Installation
        self._venv_python = self._setup_venv()
        if self._venv_python is None:
            return

        # Check if the ComfyUI Installation has an update available
        try:
            _, behind = get_remote_ahead_behind(self._repo)
        except (ValueError, GitError) as e:
            carb.log_error(f"Error checking for update: {e}")
            self._update_available = False
        else:
            self._update_available = behind > 0

    def _clone_repository(
        self,
        install_directory: str | Path,
        origin_url: str,
        branch: str,
        torch_index: str,
        models_file: str,
        models_cache: str,
    ):
        """
        Initialize the ComfyUI Installation.

        Args:
            install_directory: The directory where the ComfyUI Installation is located or should be cloned.
            origin_url: The URL of the ComfyUI repository that should be cloned.
            branch: The branch of the ComfyUI repository that should be cloned.
            torch_index: The PIP index to use for the PyTorch installation.
            models_file: The requirements file to use to get the requested models.
            models_cache: The directory to use for the models cache.
        """
        self._update_state(ComfyUIState.NOT_FOUND)

        # Try to find an existing ComfyUI Installation
        comfyui_directory = self.get_comfyui_directory(str(install_directory), "")

        # If no existing ComfyUI Installation is found and no origin URL is provided, return None
        if not comfyui_directory and not origin_url:
            carb.log_error("No existing ComfyUI Installation found and no origin URL was provided")
            self._update_state(ComfyUIState.ERROR)
            return

        if not comfyui_directory:
            # Clone new ComfyUI Installation
            self._update_state(ComfyUIState.DOWNLOADING)
            self._repo = clone_repository(
                origin_url,
                str(install_directory),
                branch=branch,
                depth=1,
                recurse_submodules=True,
                validation_callback=self._validate_repo,
            )
        else:
            self._open_repository(install_directory)

            if self._repo is None:
                return

            initialize_submodules(self._repo)

        if self._repo is None:
            return

        # Setup virtual environment for the new ComfyUI Installation
        self._venv_python = self._setup_venv()
        if self._venv_python is None:
            return

        # Install dependencies for the new ComfyUI Installation
        self._install_dependencies(torch_index=torch_index)

        # Download the models requested by the ComfyUI Installation
        self._download_models(models_file=models_file, models_cache=models_cache)

    def _download_models(self, models_file: str | None = None, models_cache: str | None = None):
        """
        Download the models for the ComfyUI Installation.

        Args:
            models_file: The requirements file to use to get the requested models.
            models_cache: The directory to use for the models cache.
        """
        if not models_file or not models_cache:
            carb.log_warn("No models requirements file or models cache directory provided. Skipping model download.")
            return

        if self._repo is None:
            carb.log_error("No ComfyUI Installation found. Cannot download models.")
            self._update_state(ComfyUIState.ERROR)
            return

        base_path = Path(self._repo.workdir)
        cache_path = base_path / models_cache

        # Ready the remix-models.toml file in the repository
        remix_models_file = base_path / models_file
        if not remix_models_file.exists():
            carb.log_error('No "remix-models.toml" file found. Cannot download models.')
            self._update_state(ComfyUIState.ERROR)
            return

        # Read the remix-models.toml file
        with open(remix_models_file, "r", encoding="utf-8") as f:
            remix_models = toml.load(f)

        self._update_state(ComfyUIState.MODELS)

        # Download the huggingface models
        for model in remix_models.get("huggingface", []):
            if "repo_id" not in model or "filename" not in model or "revision" not in model or "local_dir" not in model:
                carb.log_error(
                    f"Invalid HuggingFace model entry: {model}. "
                    "Every model entry must have the following keys: repo_id, filename, revision, local_dir"
                )
                self._update_state(ComfyUIState.ERROR)
                return

            model_path = base_path / model["local_dir"] / Path(model["filename"]).name
            if model_path.exists():
                carb.log_warn(f'Model "{model_path}" already exists. Skipping download.')
                continue

            hf_hub_download(
                repo_id=model["repo_id"],
                filename=model["filename"],
                revision=model["revision"],
                local_dir=str(cache_path),
            )

            # Move the model to the correct location
            (cache_path / model["filename"]).rename(model_path)

    def _setup_venv(self) -> str | None:
        """
        Setup the installation's virtual environment.

        Returns:
            The path to the virtual environment python executable, or None if setup fails.
        """
        if self._repo is None:
            carb.log_error("No ComfyUI Installation found. Cannot setup virtual environment.")
            self._update_state(ComfyUIState.ERROR)
            return None

        self._update_state(ComfyUIState.VENV)

        venv_dir = Path(self._repo.workdir) / self._VENV_DIRECTORY
        executable_path = (
            venv_dir / ("Scripts" if self._platform == "windows-x86_64" else "bin") / f"python{self._exe_ext}"
        )

        if executable_path.exists():
            return str(executable_path)

        venv_cmd = [
            carb.tokens.get_tokens_interface().resolve("${python}"),
            "-s",
            "-m",
            "venv",
            str(venv_dir),
        ]

        return_code = self._execute_cmd(venv_cmd, self._repo.workdir).wait()
        if return_code != 0:
            self._update_state(ComfyUIState.ERROR)
            carb.log_error(f"Virtual environment creation failed with code {return_code}")
            return None

        return str(executable_path)

    def _install_dependencies(self, torch_index: str | None = None):
        """
        Install the ComfyUI Installation Dependencies.

        Args:
            torch_index: The index to use for the torch installation.
        """
        if self._repo is None:
            carb.log_error("No ComfyUI Installation found. Cannot install dependencies.")
            self._update_state(ComfyUIState.ERROR)
            return

        if self._venv_python is None:
            carb.log_error("No virtual environment python found. Cannot install dependencies.")
            self._update_state(ComfyUIState.ERROR)
            return

        self._update_state(ComfyUIState.DEPENDENCIES)

        requirements_file = Path(self._repo.workdir) / "requirements.txt"

        # Look for custom node requirements.txt files
        custom_requirements = [
            p.as_posix() for p in Path(self._repo.workdir).glob("custom_nodes/*/requirements.txt") if p.is_file()
        ]

        # Install pip dependencies for ComfyUI and all custom nodes
        pip_cmd = [
            self._venv_python,
            "-s",
            "-m",
            "pip",
            "install",
            "--upgrade",
            "torch",
            "torchvision",
            "torchaudio",
        ]

        # Add the torch index if provided
        if torch_index:
            pip_cmd.extend(["--extra-index-url", torch_index])

        # Add all requirements files to the pip command
        all_requirements = [requirements_file] + custom_requirements
        for req in all_requirements:
            pip_cmd.extend(["-r", str(req)])

        return_code = self._execute_cmd(pip_cmd, self._repo.workdir).wait()
        if return_code != 0:
            self._update_state(ComfyUIState.ERROR)
            carb.log_error(f"Dependencies installation failed with code {return_code}")

    def _cleanup(self, repository_directory: str, attempts: int = 5, delay_s: float = 0.25) -> bool:
        """
        Try to delete the repository directory; on PermissionError, fix permissions and retry recursively.

        Args:
            repository_directory: Directory of the repository to cleanup
            attempts: Number of attempts before giving up
            delay_s: Sleep between attempts (seconds)

        Returns:
            True on success, False otherwise.
        """

        if attempts <= 0:
            return False

        path = Path(repository_directory)
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except PermissionError as e:
            carb.log_warn(f"Permission error cleaning up repository directory: {e}")

            # Repository directory was already cleaned up
            if not path.exists():
                return True

            # Fix permissions and retry
            for child in path.rglob("*"):
                with suppress(Exception):
                    child.chmod(stat.S_IWRITE)
        except Exception as e:  # noqa PLW0718
            carb.log_error(f"Exception cleaning up repository directory: {e}")
            if attempts > 1:
                carb.log_error(f"Trying again in {delay_s} seconds ({attempts - 1} attempts left)")

        time.sleep(max(0.0, delay_s))
        return self._cleanup(repository_directory, attempts - 1, delay_s)

    def _update(self, force: bool = False) -> bool:
        """
        Update the ComfyUI Installation.

        Args:
            force: Whether to hard reset the repository to the remote or attempt to pull and preserve local changes.

        Raises:
            ValueError: If the pull failed.

        Returns:
            True if the update was successful, False otherwise.
        """
        if self._repo is None:
            carb.log_error("No ComfyUI Installation found. Cannot update.")
            return False

        self._update_state(ComfyUIState.UPDATING)

        return pull_repository(self._repo, force=force)

    def _run(
        self,
        headless: bool = True,
        address: str = "127.0.0.1",
        port: int = 7860,
        timeout_s: float = 120.0,
        poll_interval_s: float = 0.5,
    ):
        """
        Run an instance of ComfyUI.

        Args:
            headless: Whether to run the instance in headless mode.
            address: The address to start the ComfyUI instance at.
            port: The port to start the ComfyUI instance on.
            timeout_s: The timeout in seconds to wait for ComfyUI to become ready.
            poll_interval_s: The interval in seconds to poll for ComfyUI to become ready.
        """
        if self._run_process is not None:
            self._update_state(ComfyUIState.RUNNING)
            carb.log_warn("ComfyUI is already running")
            return

        self._update_state(ComfyUIState.STARTING)

        validated_port = utils.validate_port(port)
        if validated_port != port:
            carb.log_warn(f"Port {port} is taken, using {validated_port} instead")
            self._settings.set(self.INSTANCE_PORT_SETTING, validated_port)

        script_path = Path(self._repo.workdir) / "main.py"

        run_cmd = [
            self._venv_python,
            "-s",
            str(script_path),
            "--windows-standalone-build",
            "--listen",
            str(address),
            "--port",
            str(validated_port),
        ]
        if headless:
            run_cmd.append("--disable-auto-launch")

        try:
            self._run_process = subprocess.Popen(run_cmd, cwd=self._repo.workdir)  # noqa PLR1732
        except Exception as e:  # noqa: PLW0718
            self._update_state(ComfyUIState.ERROR)
            carb.log_error(f"Failed to start ComfyUI: {e}")
            return

        try:
            ready = self._wait_for_server(address, validated_port, timeout_s, poll_interval_s)
        except (RuntimeError, TimeoutError) as e:
            self._stop()
            self._update_state(ComfyUIState.ERROR)
            carb.log_error(f"The ComfyUI process failed to startup: {e}")
            return

        # The startup process was cancelled, early return
        if not ready:
            return

        self._update_state(ComfyUIState.RUNNING)

        self._run_process.wait()
        self._run_process = None

        self._update_state(ComfyUIState.READY)

    def _stop(self, timeout: float | None = 10.0):
        """
        Stop the running ComfyUI process if active.

        Args:
            timeout: Seconds to wait for graceful termination before killing the process
        """
        self._update_state(ComfyUIState.STOPPING)

        process = self._run_process
        if process is None:
            self._update_state(ComfyUIState.READY)
            return

        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    if process is not None:
                        process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
            process = None
            self._update_state(ComfyUIState.READY)
        except Exception as e:  # noqa: PLW0718
            self._update_state(ComfyUIState.ERROR)
            carb.log_error(e)

        self._run_process = None

    def _validate_repo(self, repo_root: str) -> bool:
        """
        Validate the repository is a ComfyUI Installation.

        Args:
            repo_root: The root directory of the repository to validate

        Returns:
            True if the repository is a ComfyUI Installation, False otherwise.
        """
        if not repo_root:
            return False

        project_file = Path(repo_root) / "pyproject.toml"
        if not project_file.exists():
            return False
        with open(project_file, "r", encoding="utf-8") as f:
            project_config = toml.load(f)

        return project_config.get("project", {}).get("name") == "ComfyUI"

    def _execute_cmd(self, cmd: list[str], cwd: str | Path, stream_output: bool = True) -> subprocess.Popen:
        """
        Run a command while streaming output line-by-line to stdout.

        Args:
            cmd: Command list to execute
            cwd: Working directory for the process
            stream_output: Whether to print the output of the command to stdout

        Returns:
            The subprocess.Popen object
        """
        proc = subprocess.Popen(  # noqa PLR1732
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    if stream_output:
                        carb.log_info(line.rstrip())
        except Exception:
            proc.kill()
            raise

        return proc

    def _wait_for_server(
        self,
        address: str,
        port: int,
        timeout_s: float,
        poll_interval_s: float,
    ) -> bool:
        """
        Wait for the ComfyUI process to become ready.

        Args:
            address: The address to start the ComfyUI instance at.
            port: The port to start the ComfyUI instance on.
            timeout_s: The timeout in seconds to wait for ComfyUI to become ready.
            poll_interval_s: The interval in seconds to poll for ComfyUI to become ready.

        Raises:
            RuntimeError: If the ComfyUI process exits with a non-zero code
            TimeoutError: If the ComfyUI startup process timed out

        Returns:
            True if the ComfyUI process is ready, False otherwise.
        """
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout_s:
            if not self._run_process:
                return False

            return_code = self._run_process.poll() if self._run_process is not None else None
            if return_code is not None and return_code != 0:
                self._run_process = None
                raise RuntimeError(f"ComfyUI exited early with code {return_code}")

            try:
                response = requests.get(f"http://{address}:{port}/system_stats", timeout=1.0)
                if response.status_code == 200:
                    return True
            except requests.RequestException:
                pass

            time.sleep(poll_interval_s)

        raise TimeoutError("ComfyUI startup process timed out")
