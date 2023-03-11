"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from enum import Enum
from pathlib import Path
from typing import List, Optional

import omni.client
from lightspeed.common import constants as _constants
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
        # Invalid /deps directory means we need to select the 'rtx_remix' directory
        deps_symlink = project_path.parent / _constants.REMIX_DEPENDENCIES_FOLDER
        if not deps_symlink.exists():
            return False
        # Make sure the project is also symlinked in the 'rtx_remix/mods/' directory
        mod_symlink = deps_symlink / _constants.REMIX_MODS_FOLDER / project_path.parent.name
        if not mod_symlink.exists():
            return False
        return True

    @validator(ProjectWizardKeys.PROJECT_FILE.value, allow_reuse=True)
    def is_project_file_valid(cls, v, values):  # noqa
        """Check that the path is a valid project file"""
        if not v or not str(v).strip():
            raise ValueError(f"'{str(v)}' is not valid")
        if v.suffix not in _constants.USD_EXTENSIONS:
            raise ValueError(f"The path '{str(v)}' is not a USD file")
        if values.get(ProjectWizardKeys.EXISTING_PROJECT.value, False):
            _, entry = omni.client.stat(str(v))
            if not (entry.flags & omni.client.ItemFlags.WRITEABLE_FILE):  # noqa PLC0325
                raise ValueError(f"The path '{str(v)}' is not a writable file")
            if _ReplacementCore.is_mod_file(str(v)):
                raise ValueError(f"The path '{str(v)}' is a mod file")
            if _CaptureCore.is_capture_file(str(v)):
                raise ValueError(f"The path '{str(v)}' is a capture file")
        else:
            if str(Path(_constants.REMIX_FOLDER) / _constants.REMIX_MODS_FOLDER) in str(v):
                raise ValueError(f"The project should not be created in the '{_constants.REMIX_FOLDER}' directory")
            result, entry = omni.client.stat(str(v.parent))
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                raise ValueError(f"The path's parent directory '{str(v.parent)}' is not writable")
            result, entries = omni.client.list(str(v.parent))
            if result != omni.client.Result.OK or entries:
                raise ValueError("The project should be created in a valid empty directory")
            # Try to validate the project doesn't exist if possible
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
        has_mods_dir = False
        _, entries = omni.client.list(str(v))
        for entry in entries:
            if entry.relative_path == _constants.REMIX_CAPTURE_FOLDER:
                has_capture_dir = True
            if entry.relative_path == _constants.REMIX_MODS_FOLDER:
                has_mods_dir = True
        if not has_capture_dir:
            raise ValueError(f"The remix directory is missing a {_constants.REMIX_CAPTURE_FOLDER} subdirectory")
        if not has_mods_dir:
            raise ValueError(f"The remix directory is missing a {_constants.REMIX_MODS_FOLDER} subdirectory")

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
        if v:
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