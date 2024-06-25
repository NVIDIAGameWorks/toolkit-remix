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

import re
from enum import Enum
from pathlib import Path
from typing import List, Optional

import omni.client
from lightspeed.common import constants as _constants
from lightspeed.common.constants import REGEX_RESERVED_FILENAME as _REGEX_RESERVED_FILENAME
from lightspeed.common.constants import REGEX_VALID_PATH as _REGEX_VALID_PATH
from lightspeed.trex.capture.core.shared import Setup as _CaptureCore
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCore
from pydantic import BaseModel, validator


class ProjectWizardKeys(Enum):
    EXISTING_PROJECT = "existing_project"
    PROJECT_FILE = "project_file"
    REMIX_DIRECTORY = "remix_directory"
    EXISTING_MODS = "existing_mods"
    MOD_FILE = "mod_file"
    CAPTURE_FILE = "capture_file"


class ProjectWizardSchema(BaseModel):
    existing_project: bool
    project_file: Path
    remix_directory: Optional[Path]
    existing_mods: Optional[List[Path]]
    mod_file: Optional[Path]
    capture_file: Optional[Path]

    @classmethod
    def are_project_symlinks_valid(cls, project_path: Path) -> bool:
        # TODO Feature OM-72437 - Should use omni.client when symlinks become supported
        # Invalid /deps directory means we need to select the 'rtx-remix' directory
        deps_symlink = project_path.parent / _constants.REMIX_DEPENDENCIES_FOLDER
        if not deps_symlink.exists():
            return False
        # Make sure the project is also symlinked in the 'rtx-remix/mods/' directory
        mod_symlink = deps_symlink / _constants.REMIX_MODS_FOLDER / project_path.parent.name
        if not mod_symlink.exists():
            return False
        return True

    @validator(ProjectWizardKeys.PROJECT_FILE.value, allow_reuse=True)
    def is_project_file_valid(cls, v, values):  # noqa
        """Check that the path is a valid project file"""

        # Make sure there are no invalid characters in the filename
        if re.search(r'[<>"\\():*?|]', Path(str(v)).name):
            raise ValueError(f"'{Path(str(v)).name}' has an invalid character in filename.")
        # Make sure there are no whitespaces in the path
        if " " in str(v).strip():
            raise ValueError(f"'{str(v)}' has a whitespace in file path.")
        # Making sure there are no Windows reserved words
        if not re.search(_REGEX_VALID_PATH, Path(str(v)).name):
            raise ValueError(f"'{Path(str(v)).name}' has a Windows reserved word in filename.")
        # Making sure no reserved words are in the filename
        if re.search(_REGEX_RESERVED_FILENAME, Path(str(v)).name):
            raise ValueError(f"'{Path(str(v)).name}' has a reserved name in filename.")
        # Make sure we have a path
        if not v or not str(v).strip():
            raise ValueError(f"'{str(v)}' is not valid")
        # Make sure the path points to a USD file
        if v.suffix not in _constants.USD_EXTENSIONS:
            raise ValueError(f"The path '{str(v)}' is not a USD file")
        # If we are opening a project:
        if values.get(ProjectWizardKeys.EXISTING_PROJECT.value, False):
            _, entry = omni.client.stat(str(v))
            # Make sure the project is not read-only
            if not (entry.flags & omni.client.ItemFlags.WRITEABLE_FILE):  # noqa PLC0325
                raise ValueError(f"The path '{str(v)}' is not a writable file")
            # Make sure the project is not a replacement file
            if _ReplacementCore.is_mod_file(str(v)):
                raise ValueError(f"The path '{str(v)}' is a mod file")
            # Make sure the project is not a capture file
            if _CaptureCore.is_capture_file(str(v)):
                raise ValueError(f"The path '{str(v)}' is a capture file")
        # If we are creating a project:
        else:
            # Make sure the project is not in the root of the rtx-remix directory
            if v.parent.name == _constants.REMIX_FOLDER:
                raise ValueError(f"The project should not be created in the '{_constants.REMIX_FOLDER}' root directory")
            # Make sure the project is not in the capture directory
            if str(Path(_constants.REMIX_FOLDER) / _constants.REMIX_CAPTURE_FOLDER) in str(v):
                raise ValueError(
                    f"The project should not be created in the '{_constants.REMIX_CAPTURE_FOLDER}' directory"
                )
            # Make sure the project is in a subdirectory if it is in the mods directory
            if str(Path(_constants.REMIX_FOLDER) / _constants.REMIX_MODS_FOLDER) in str(v) and not re.search(
                rf"{_constants.REMIX_FOLDER}/{_constants.REMIX_MODS_FOLDER}/.*?/.*\.usd\w?$",
                v.as_posix(),
                re.IGNORECASE,
            ):
                raise ValueError(
                    f"The project should not be created directly in the '{_constants.REMIX_MODS_FOLDER}' directory. "
                    f"It should be created in a unique subdirectory."
                )
            # Make sure the parent directory is not read-only
            result, entry = omni.client.stat(str(v.parent))
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                raise ValueError(f"The path's parent directory '{str(v.parent)}' is not writable")
            # Make sure the project directory is empty
            result, entries = omni.client.list(str(v.parent))
            if result != omni.client.Result.OK or entries:
                raise ValueError("The project should be created in a valid empty directory")
            # Try to validate the project doesn't already exist in rtx-remix if possible
            remix_dir = values.get(ProjectWizardKeys.REMIX_DIRECTORY.value, None)
            if remix_dir:
                project_path = Path(remix_dir) / _constants.REMIX_MODS_FOLDER / v.parent.name
                result, _ = omni.client.stat(str(project_path))
                if result != omni.client.Result.ERROR_NOT_FOUND:
                    raise ValueError(f"A project with the same name already exists: '{project_path}'")
        return v

    @validator(ProjectWizardKeys.REMIX_DIRECTORY.value, allow_reuse=True)
    def is_remix_directory_valid(cls, v, values):  # noqa
        """Check that the path is a valid capture directory"""
        if not v:
            if not values.get(ProjectWizardKeys.EXISTING_PROJECT.value, False):
                raise ValueError("The is mandatory for new projects")
            if not cls.are_project_symlinks_valid(values.get(ProjectWizardKeys.PROJECT_FILE.value, None)):
                raise ValueError("The project path symlinks are invalid. A Remix directory is required to fix them.")

        if v.stem != _constants.REMIX_FOLDER:
            raise ValueError(f"The path must point to a directory with the name: '{_constants.REMIX_FOLDER}'")

        result, entry = omni.client.stat(str(v))
        if result != omni.client.Result.OK:
            raise ValueError("The remix directory invalid")
        if not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
            raise ValueError("The remix directory is not writable")

        has_capture_dir = False
        _, entries = omni.client.list(str(v))
        for entry in entries:
            if entry.relative_path == _constants.REMIX_CAPTURE_FOLDER:
                has_capture_dir = True
        if not has_capture_dir:
            raise ValueError(f"The remix directory is missing a {_constants.REMIX_CAPTURE_FOLDER} subdirectory")

        return v

    @validator(ProjectWizardKeys.EXISTING_MODS.value, each_item=True, allow_reuse=True)
    def are_all_mod_files_valid(cls, v, values):  # noqa
        """Check that the paths are valid mod layers"""
        mod_directory = values.get(ProjectWizardKeys.REMIX_DIRECTORY.value, Path("")) / _constants.REMIX_MODS_FOLDER
        if str(v.parent.parent) != str(mod_directory):
            raise ValueError(
                f"The mod should be in the '{_constants.REMIX_MODS_FOLDER}' subdirectory of the Remix Directory"
            )
        if not _ReplacementCore.is_mod_file(str(v)):
            raise ValueError("The path is not a valid mod file")
        return v

    @validator(ProjectWizardKeys.MOD_FILE.value, allow_reuse=True)
    def is_mod_file_valid(cls, v, values):  # noqa
        """Check that the file is a valid mod file or None"""
        if v:
            if v not in values.get(ProjectWizardKeys.EXISTING_MODS.value, []):
                raise ValueError("The path must also be present in the `existing_mods` list")
            if not _ReplacementCore.is_mod_file(str(v)):
                raise ValueError("The path is not a valid mod file")
        return v

    @validator(ProjectWizardKeys.CAPTURE_FILE.value, allow_reuse=True)
    def is_capture_file_valid(cls, v, values):  # noqa
        """Check that the file is a valid capture file or None"""
        if not v:
            if not values.get(ProjectWizardKeys.EXISTING_PROJECT.value, False):
                raise ValueError("A capture must be selected when creating a project")
        else:
            captures_directory = (
                values.get(ProjectWizardKeys.REMIX_DIRECTORY.value, Path("")) / _constants.REMIX_CAPTURE_FOLDER
            )
            if str(v.parent) != str(captures_directory):
                raise ValueError(
                    f"The capture should be in the '{_constants.REMIX_CAPTURE_FOLDER}' subdirectory "
                    f"of the {_constants.REMIX_FOLDER} Directory"
                )
            if not _CaptureCore.is_capture_file(str(v)):
                raise ValueError("The path is not a valid capture file")
        return v
