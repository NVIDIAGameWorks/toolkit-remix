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

__all__ = ["get_test_data_path", "open_test_project"]

import contextlib
import tempfile

import carb
import omni.client
import omni.usd
from omni.flux.utils.common.omni_url import OmniUrl

_DEFAULT_TEST_DATA_EXT_SETTING = "/exts/omni.flux.utils.tests/default_test_data_ext"


def _get_test_data_ext(ext_name: str | None) -> str:
    if ext_name is None:
        ext_name = carb.settings.get_settings().get(_DEFAULT_TEST_DATA_EXT_SETTING)
        if not ext_name:
            raise ValueError(
                f"Test data helpers require ext_name when '{_DEFAULT_TEST_DATA_EXT_SETTING}' is not configured"
            )

    # When using `__name__` we get the unit/e2e test module. Try to get the base extension name.
    try:
        parts = ext_name.split(".")
        index = parts.index("tests")
        return ".".join(parts[:index])
    except ValueError:
        return ext_name


@contextlib.asynccontextmanager
async def open_test_project(project_data_path: str, ext_name: str | None = None, context_name: str = "") -> OmniUrl:
    """Open a temporary copy of a test project.

    Args:
        project_data_path: Project path relative to the test-data extension's ``data/tests`` directory.
        ext_name: Extension that owns the test data. If omitted, the configured default test-data extension is used.
        context_name: Optional USD context name.

    Yields:
        The copied project URL.

    Raises:
        OSError: If the project directory cannot be copied.
        ValueError: If no explicit or default test-data extension is available.
    """
    temp_dir = tempfile.TemporaryDirectory()
    project_path = get_test_data_path(project_data_path, ext_name)
    temp_path = OmniUrl(temp_dir.name) / OmniUrl(project_path.parent_url).stem
    temp_project = temp_path / project_path.name

    result = await omni.client.copy_async(project_path.parent_url, temp_path.path)

    if result != omni.client.Result.OK:
        raise OSError(f"Can't copy the project path to the temporary directory: {result}")

    usd_context = omni.usd.get_context(context_name)
    if not usd_context:
        usd_context = omni.usd.create_context(context_name)
    await usd_context.open_stage_async(temp_project.path)

    try:
        yield temp_project
    finally:
        if omni.usd.get_context(context_name).can_close_stage():
            await omni.usd.get_context(context_name).close_stage_async()
        temp_dir.cleanup()


def get_test_data_path(project_data_path: str, ext_name: str | None = None) -> OmniUrl:
    """Resolve a path inside an extension's ``data/tests`` directory.

    Args:
        project_data_path: Path relative to the test-data extension's ``data/tests`` directory.
        ext_name: Extension that owns the test data. If omitted, the configured default test-data extension is used.

    Returns:
        The resolved test data URL.

    Raises:
        ValueError: If no explicit or default test-data extension is available.
    """
    short_ext_name = _get_test_data_ext(ext_name)
    return OmniUrl(carb.tokens.get_tokens_interface().resolve(f"${{{short_ext_name}}}/data/tests/{project_data_path}"))
