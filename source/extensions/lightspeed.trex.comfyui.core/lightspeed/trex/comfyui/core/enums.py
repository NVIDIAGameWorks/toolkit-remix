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

__all__ = [
    "WORKFLOW_TYPES_BY_CATEGORY",
    "ComfyUIEventType",
    "ComfyUIOperation",
    "ComfyUIProtocol",
    "ComfyUIRetargetResult",
    "ComfyUIState",
    "IntroducingLayer",
    "RemixType",
    "WorkflowCategory",
    "WorkflowSourceType",
    "WorkflowType",
]

from enum import Enum, StrEnum


class ComfyUIEventType(Enum):
    """Identify state, workflow, and settings notifications from the event stream."""

    STATE_CHANGED = "state_changed"
    WORKFLOW_CHANGED = "workflow_changed"
    WORKFLOWS_LOADED = "workflows_loaded"
    SETTINGS_CHANGED = "settings_changed"
    STAGE_VISIBILITY_CHANGED = "stage_visibility_changed"


class ComfyUIOperation(StrEnum):
    """Identify mutually exclusive ComfyUI preparation and submission work."""

    JOB_PREPARATION = "job preparation"
    QUEUE_SUBMISSION = "queue submission"


class ComfyUIRetargetResult(Enum):
    """Identify the result of one atomic queued-job retarget request."""

    UPDATED = "updated"
    CONNECTION_CHANGED = "connection_changed"
    JOB_STARTED = "job_started"


class ComfyUIState(StrEnum):
    """Identify connection lifecycle states published by the ComfyUI runtime."""

    STARTING = "starting"
    RUNNING = "running"
    READY = "ready"
    ERROR = "error"


class ComfyUIProtocol(Enum):
    """Define supported protocols and their standard ports.

    Each value is a tuple of (scheme, standard_port).
    """

    HTTP = ("http", 80)
    HTTPS = ("https", 443)

    def __init__(self, scheme: str, standard_port: int):
        """Initialize a protocol with its URL scheme and standard port.

        Args:
            scheme: URL scheme represented by this protocol.
            standard_port: Conventional TCP port for the protocol.
        """
        self._scheme = scheme
        self._standard_port = standard_port

    @property
    def scheme(self) -> str:
        """Return the URL scheme component.

        Returns:
            Lowercase ``http`` or ``https`` scheme.
        """
        return self._scheme

    @property
    def standard_port(self) -> int:
        """Return the standard port number for this protocol.

        Returns:
            Conventional TCP port for the protocol.
        """
        return self._standard_port


class IntroducingLayer(Enum):
    """Identify which Remix layer introduced a texture selected for processing."""

    CAPTURE = "Capture"
    MOD = "Mod"
    ANY = "Any"


class RemixType(StrEnum):
    """Canonical Remix port tags emitted by the ComfyUI node pack."""

    TEXTURE_FILE_PATH = "texture_file_path"


class WorkflowCategory(Enum):
    """Distinguish executable prompt data from full workflow graph data."""

    API = "api"
    FULL = "full"


class WorkflowSourceType(Enum):
    """Identify whether a workflow comes from RTX Remix or user storage."""

    RTX_REMIX = "rtx-remix"
    USER = "user"


class WorkflowType(Enum):
    """Workflow types that the RTX Remix ComfyUI node pack publishes."""

    ASSET_GENERATION = "Asset Generation"
    MATERIAL_GENERATION = "Material Generation"
    ASSET_UPSCALING = "Asset Upscaling"
    MESH_UPSCALING = "Mesh Upscaling"
    TEXTURE_UPSCALING = "Texture Upscaling"
    ASSET_TAGGING = "Asset Tagging"
    OTHER = "Other"


# Display order of the picker, and the category of every type. Mirrors the node pack vocabulary.
# The picker uses this map as a fallback only, for a server that does not publish the
# workflows/types endpoint. A published category carries a description for each type; this
# fallback map does not, because the description text lives only on the server.
WORKFLOW_TYPES_BY_CATEGORY: dict[str, tuple[WorkflowType, ...]] = {
    "Generation": (WorkflowType.ASSET_GENERATION, WorkflowType.MATERIAL_GENERATION),
    "Upscaling": (WorkflowType.ASSET_UPSCALING, WorkflowType.MESH_UPSCALING, WorkflowType.TEXTURE_UPSCALING),
    "Miscellaneous": (WorkflowType.ASSET_TAGGING,),
    "Other": (WorkflowType.OTHER,),
}
