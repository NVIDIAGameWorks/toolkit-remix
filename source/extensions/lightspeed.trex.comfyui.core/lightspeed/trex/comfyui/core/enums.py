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

__all__ = ["ComfyUIState"]

from enum import Enum


class ComfyUIState(Enum):
    NOT_FOUND = "No installation found"
    FOUND = "Found existing installation"
    DOWNLOADING = "Downloading ComfyUI..."
    VENV = "Creating virtual environment..."
    DEPENDENCIES = "Installing dependencies... (This may take a while)"
    MODELS = "Downloading models... (This may take a while)"
    READY = "Ready"
    STARTING = "Starting..."
    RUNNING = "Running"
    STOPPING = "Stopping..."
    UPDATING = "Updating..."
    UNINSTALLING = "Uninstalling..."
    ERROR = "An error occurred. See logs for details"
