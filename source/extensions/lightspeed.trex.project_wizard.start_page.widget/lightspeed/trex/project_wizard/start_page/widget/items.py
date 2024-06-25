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

from enum import Enum


class StartOption(Enum):
    """
    UI Options for the wizard start page.

    TEXT, Primary description, Detailed description, Example description
    """

    OPEN = (
        "OPEN",
        "Open an existing project.",
        "Opening an existing projects can be used when a project was already created by another author.",
        "A multi-member team wants to share a project hosted on a SVC tool between members.",
    )
    CREATE = (
        "CREATE",
        "Create a project to author a new mod.",
        "Creating a project will initialize a vanilla project with no existing dependencies.",
        "Create a new mod for which you do not need existing RTX Remix mod dependencies.",
    )
    EDIT = (
        "EDIT",
        "Create a project to edit an existing mod.",
        "Editing will create a project with existing mod file(s) as the replacements layers in the project.",
        "Update an existing mod for which you don't have the project files for.",
    )
    REMASTER = (
        "REMASTER",
        "Create a project to author a new mod with dependencies.",
        "Remaster will create a project with a new mod file and add existing mod files as weaker sublayers.",
        "Create a self-contained mod that modifies one or more existing RTX Remix mod(s).",
    )
