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
        "This option will allow you to open a project that has already been created.",
        "You join a multi-member team and want to open the shared project hosted on a SVC tool.",
    )
    CREATE = (
        "CREATE",
        "Create a project to author a new mod.",
        "This option will create a blank project with no dependencies.",
        "You want to start building a new mod from scratch.",
    )
    EDIT = (
        "EDIT",
        "Create a project to edit an existing mod.",
        "This option will create a project around a copy of an existing mod.",
        "You want to build on top of a packaged mod and you don't have access to their project files.",
    )
    REMASTER = (
        "REMASTER",
        "Create a project to author a new mod with dependencies.",
        "This option will create a project which references existing mod files as weaker sublayers.",
        "You want to make specific changes and keep the live connection to one or more existing RTX Remix mod(s).",
    )
