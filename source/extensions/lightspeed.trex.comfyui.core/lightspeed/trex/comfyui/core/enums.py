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

__all__ = ["ComfyUIState", "ComfyUIQueueType"]

from enum import Enum


class ComfyUIState(Enum):
    NOT_FOUND = "No ComfyUI installation found. Install ComfyUI to get started."
    FOUND = "Starting the initialization process..."
    DOWNLOADING = "Downloading the latest version of ComfyUI..."
    VENV = "Creating a virtual environment..."
    DEPENDENCIES = "Installing dependencies... (This may take a while)"
    MODELS = "Downloading models... (This may take a while)"
    READY = "ComfyUI is ready to start"
    STARTING = "Starting ComfyUI..."
    RUNNING = "ComfyUI is running"
    STOPPING = "Stopping ComfyUI..."
    UPDATING = "Updating ComfyUI to the latest version..."
    UNINSTALLING = "Deleting the ComfyUI installation..."
    ERROR = "An error occurred. See logs for details. Refresh the installation state to try again."


class ComfyUIQueueType(Enum):
    TEXTURE = "texture"
    MESH = "mesh"
