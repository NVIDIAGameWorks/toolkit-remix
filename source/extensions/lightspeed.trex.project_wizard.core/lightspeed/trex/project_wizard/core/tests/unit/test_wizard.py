"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import stat
from pathlib import Path
from typing import List, Optional
from unittest.mock import Mock, call

import omni.usd
from lightspeed.common import constants
from lightspeed.layer_manager.core import LayerType
from lightspeed.trex.project_wizard.core import ProjectWizardCore

from .mocks import ProjectWizardSchemaMock, WizardMockContext  # noqa PLE0402


class TestWizard(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.base_dir = Path.cwd()
        self.core = ProjectWizardCore()

    # After running each test
    async def tearDown(self):
        self.base_dir = None
        self.core = None

    async def test_setup_project_existing_project_should_quick_return_success(self):
        # Arrange
        project_file = self.base_dir / "projects" / "MyProject" / "my_project.usda"

        schema = ProjectWizardSchemaMock(
            existing_project=True,
            project_file=project_file,
        )

        with WizardMockContext(schema_mock=schema, mock_wizard_methods=True) as mock:
            # Act
            await self.core.setup_project_async_with_exceptions({})

        # Assert
        self.assertEqual(1, mock.setup_usd_mock.call_count)
        self.assertEqual(1, mock.create_symlinks_mock.call_count)
        self.assertEqual(0, mock.create_project_mock.call_count)

        self.assertEqual(5, mock.progress_mock.call_count)
        self.assertEqual(1, mock.finished_mock.call_count)

        self.assertEqual([call(0), call(10), call(20), call(30), call(100)], mock.progress_mock.call_args_list)

        self.assertEqual(call(True), mock.finished_mock.call_args)

    async def test_setup_project_symlink_error_should_quick_return_error(self):
        # Arrange
        project_file = self.base_dir / "projects" / "MyProject" / "my_project.usda"

        schema = ProjectWizardSchemaMock(
            existing_project=True,
            project_file=project_file,
        )

        symlink_error = "Test Error"

        with WizardMockContext(schema_mock=schema, mock_wizard_methods=True) as mock:
            future = asyncio.Future()
            future.set_result(symlink_error)
            mock.create_symlinks_mock.return_value = future

            # Act
            await self.core.setup_project_async_with_exceptions({})

        # Assert
        self.assertEqual(1, mock.setup_usd_mock.call_count)
        self.assertEqual(1, mock.create_symlinks_mock.call_count)
        self.assertEqual(0, mock.create_project_mock.call_count)

        self.assertEqual(3, mock.progress_mock.call_count)
        self.assertEqual(1, mock.finished_mock.call_count)

        self.assertEqual([call(0), call(10), call(20)], mock.progress_mock.call_args_list)

        self.assertEqual(call(False, error=symlink_error), mock.finished_mock.call_args)

    async def test_setup_project_mod_file_should_setup_existing_mod_project(self):
        await self.__run_test_setup_project_should_setup_project(True)

    async def test_setup_project_no_mod_file_should_setup_new_mod_project(self):
        await self.__run_test_setup_project_should_setup_project(False)

    async def test_setup_project_no_stage_should_quick_return_fail(self):
        # Arrange
        project_file = self.base_dir / "project.usda"

        schema = ProjectWizardSchemaMock(
            existing_project=False,
            project_file=project_file,
        )

        with WizardMockContext(schema_mock=schema, mock_wizard_methods=True) as mock:
            future = asyncio.Future()
            future.set_result((Mock(), None))
            mock.create_project_mock.return_value = future

            # Act
            await self.core.setup_project_async_with_exceptions({})

        # Assert
        self.assertEqual(1, mock.setup_usd_mock.call_count)
        self.assertEqual(1, mock.create_symlinks_mock.call_count)
        self.assertEqual(1, mock.create_project_mock.call_count)
        self.assertEqual(0, mock.setup_existing_mod_mock.call_count)
        self.assertEqual(0, mock.setup_new_mod_mock.call_count)

        self.assertEqual(5, mock.progress_mock.call_count)
        self.assertEqual(1, mock.log_error_mock.call_count)
        self.assertEqual(1, mock.finished_mock.call_count)

        self.assertEqual([call(0), call(10), call(20), call(30), call(40)], mock.progress_mock.call_args_list)

        error_message = f"Could not open stage for the project file ({project_file})."

        self.assertEqual(call(error_message), mock.log_error_mock.call_args)
        self.assertEqual(call(False, error=error_message), mock.finished_mock.call_args)

    async def test_setup_project_no_project_layer_should_quick_return_fail(self):
        # Arrange
        project_file = self.base_dir / "project.usda"

        schema = ProjectWizardSchemaMock(
            existing_project=False,
            project_file=project_file,
        )

        with WizardMockContext(schema_mock=schema, mock_wizard_methods=True) as mock:
            future = asyncio.Future()
            future.set_result((None, Mock()))
            mock.create_project_mock.return_value = future

            # Act
            await self.core.setup_project_async_with_exceptions({})

        # Assert
        self.assertEqual(1, mock.setup_usd_mock.call_count)
        self.assertEqual(1, mock.create_symlinks_mock.call_count)
        self.assertEqual(1, mock.create_project_mock.call_count)
        self.assertEqual(0, mock.setup_existing_mod_mock.call_count)
        self.assertEqual(0, mock.setup_new_mod_mock.call_count)

        self.assertEqual(5, mock.progress_mock.call_count)
        self.assertEqual(1, mock.log_error_mock.call_count)
        self.assertEqual(1, mock.finished_mock.call_count)

        self.assertEqual([call(0), call(10), call(20), call(30), call(40)], mock.progress_mock.call_args_list)

        error_message = f"The project file ({project_file}) was not found."

        self.assertEqual(call(error_message), mock.log_error_mock.call_args)
        self.assertEqual(call(False, error=error_message), mock.finished_mock.call_args)

    async def test_setup_project_dry_run_should_not_call_io_functions(self):
        # Arrange
        project_file = self.base_dir / "projects" / "MyProject" / "my_project.usda"
        remix_dir = self.base_dir / "rtx_remix"
        captures_dir = remix_dir / constants.REMIX_CAPTURE_FOLDER
        existing_mod_dir = remix_dir / constants.REMIX_MODS_FOLDER / "ExistingMod"

        mod_file = existing_mod_dir / "mod.usda"
        capture_file = captures_dir / "capture.usda"

        schema = ProjectWizardSchemaMock(
            existing_project=False,
            project_file=project_file,
            remix_directory=remix_dir,
            existing_mods=[mod_file],
            mod_file=mod_file,
            capture_file=capture_file,
        )

        with WizardMockContext(schema_mock=schema) as mock:
            mock.path_exists_mock.return_value = False

            # Act
            await self.core.setup_project_async_with_exceptions({}, dry_run=True)

        # Assert
        self.assertEqual(0, mock.check_call_mock.call_count)
        self.assertEqual(0, mock.path_chmod_mock.call_count)
        self.assertEqual(0, mock.save_custom_data_mock.call_count)
        self.assertEqual(0, mock.core_mock.return_value.save_layer.call_count)
        self.assertEqual(0, mock.core_mock.return_value.create_new_sublayer.call_count)
        self.assertEqual(0, mock.core_mock.return_value.insert_sublayer.call_count)

        _, kwargs = mock.copy_tree_mock.call_args
        self.assertEqual(1, mock.copy_tree_mock.call_count)
        self.assertEqual({"dry_run": True}, kwargs)

        self.assertEqual(1, mock.finished_mock.call_count)
        self.assertEqual(call(True), mock.finished_mock.call_args)

    async def test_setup_usd_stage_should_setup_usd_context_and_stage(self):
        # Arrange
        pass

        with WizardMockContext() as mock:
            # Act
            await self.core._setup_usd_stage()  # noqa PLW0212

        # Assert
        self.assertEqual(2, mock.get_context_mock.call_count)
        self.assertEqual(1, mock.get_context_mock.return_value.new_stage_async.call_count)
        self.assertEqual(1, mock.get_context_mock.return_value.get_stage.call_count)

        self.assertIsNotNone(self.core.CONTEXT_NAME)
        self.assertIsInstance(self.core.CONTEXT_NAME, str)
        self.assertEqual(
            [call(self.core.CONTEXT_NAME), call(self.core.CONTEXT_NAME)], mock.get_context_mock.call_args_list
        )

    async def test_create_symlinks_no_deps_dir_should_quick_return(self):
        await self.__run_test_create_symlinks_should_quick_return(True)

    async def test_create_symlinks_no_remix_dir_should_quick_return(self):
        await self.__run_test_create_symlinks_should_quick_return(False)

    async def test_create_symlinks_deps_symlink_exists_should_not_symlink(self):
        await self.__run_test_create_symlinks_exists_should_not_symlink(True)

    async def test_create_symlinks_remix_symlink_exists_should_not_symlink(self):
        await self.__run_test_create_symlinks_exists_should_not_symlink(True)

    async def test_create_project_layer_should_create_new_sublayer_open_stage_and_return_layer_and_stage(self):
        # Arrange
        project_file = self.base_dir / "projects" / "MyProject" / "my_project.usda"

        core_mock = Mock()
        context_mock = Mock()
        stage_mock = Mock()
        project_mock = Mock()
        context_stage_mock = Mock()

        create_sublayer_mock = core_mock.create_new_sublayer
        create_sublayer_mock.return_value = project_mock

        open_stage_mock = context_mock.open_stage_async
        future = asyncio.Future()
        future.set_result(None)
        open_stage_mock.return_value = future

        context_mock.get_stage.return_value = context_stage_mock

        # Act
        project_layer, stage = await self.core._create_project_layer(  # noqa PLW0212
            project_file, core_mock, context_mock, stage_mock, False
        )

        # Assert
        self.assertEqual(1, create_sublayer_mock.call_count)
        self.assertEqual(1, open_stage_mock.call_count)

        args, kwargs = create_sublayer_mock.call_args
        self.assertEqual((LayerType.workfile, str(project_file)), args)
        self.assertEqual({"do_undo": False}, kwargs)

        self.assertEqual(call(str(project_file)), open_stage_mock.call_args)

        self.assertEqual(project_mock, project_layer)
        self.assertEqual(context_stage_mock, stage)

    async def test_setup_existing_mod_project_should_copy_chmod_insert_and_return_file(self):
        # Arrange
        project_file = self.base_dir / "MyProject" / "project.usda"
        mod_file = self.base_dir / constants.REMIX_FOLDER / constants.REMIX_MODS_FOLDER / "ExistingMod" / "mod.usda"

        project_dir = project_file.parent
        project_mod_file = project_dir / mod_file.name

        project_mock = Mock()

        with WizardMockContext() as mock:
            insert_sublayer_mock = mock.core_mock.insert_sublayer

            # Act
            value = await self.core._setup_existing_mod_project(  # noqa PLW0212
                mock.core_mock, mod_file, project_dir, project_mock, False
            )

        # Assert
        self.assertEqual(1, mock.copy_tree_mock.call_count)
        copy_args, copy_kwargs = mock.copy_tree_mock.call_args
        self.assertEqual((str(mod_file.parent), str(project_dir)), copy_args)
        self.assertEqual({"dry_run": False}, copy_kwargs)

        self.assertEqual(1, insert_sublayer_mock.call_count)
        insert_args, insert_kwargs = insert_sublayer_mock.call_args
        self.assertEqual((str(project_mod_file), LayerType.replacement), insert_args)
        self.assertEqual({"set_as_edit_target": True, "parent_layer": project_mock, "do_undo": False}, insert_kwargs)

        self.assertEqual(1, mock.path_chmod_mock.call_count)
        self.assertEqual(call(stat.S_IREAD | stat.S_IWRITE), mock.path_chmod_mock.call_args)

        self.assertEqual(project_mod_file, value)

    async def test_setup_new_mod_project_should_create_new_sublayer_and_return_file(self):
        # Arrange
        project_file = self.base_dir / "MyProject" / "project.usda"
        project_dir = project_file.parent
        mod_file = project_dir / constants.REMIX_MOD_FILE

        project_mock = Mock()

        with WizardMockContext() as mock:
            create_sublayer_mock = mock.core_mock.create_new_sublayer

            # Act
            value = await self.core._setup_new_mod_project(  # noqa PLW0212
                mock.core_mock, project_dir, project_mock, False
            )

        # Assert
        self.assertEqual(1, create_sublayer_mock.call_count)

        args, kwargs = create_sublayer_mock.call_args
        self.assertEqual((LayerType.replacement, str(mod_file)), args)
        self.assertEqual({"set_as_edit_target": True, "parent_layer": project_mock, "do_undo": False}, kwargs)

        self.assertEqual(mod_file, value)

    async def test_insert_existing_mods_no_existing_mods_should_quick_return(self):
        await self.__run_test_insert_existing_mods_should_quick_return(None, Mock())
        await self.__run_test_insert_existing_mods_should_quick_return([], Mock())

    async def test_insert_existing_mods_no_project_layer_should_quick_return(self):
        await self.__run_test_insert_existing_mods_should_quick_return([self.base_dir], None)

    async def test_insert_existing_mods_should_insert_all_existing_mod_except_mod_file(self):
        # Arrange
        project_file = self.base_dir / "MyProject" / "project.usda"
        project_dir = project_file.parent
        project_mods_dir = project_dir / constants.REMIX_DEPENDENCIES_FOLDER / constants.REMIX_MODS_FOLDER

        existing_mods_dir = self.base_dir / constants.REMIX_FOLDER / constants.REMIX_MODS_FOLDER
        mod_1 = existing_mods_dir / "Mod1" / "mod.usda"
        mod_2 = existing_mods_dir / "Mod2" / "mod.usda"
        mod_3 = existing_mods_dir / "Mod3" / "mod.usda"
        existing_mods = [mod_1, mod_2, mod_3]

        mod_file = mod_1

        project_mock = Mock()

        with WizardMockContext() as mock:
            insert_mock = mock.core_mock.insert_sublayer

            # Act
            await self.core._insert_existing_mods(  # noqa PLW0212
                mock.core_mock, existing_mods, mod_file, project_mods_dir, project_mock
            )

        # Assert
        self.assertEqual(2, insert_mock.call_count)

        args_0, kwargs_0 = insert_mock.call_args_list[0]
        self.assertEqual((str(project_mods_dir / mod_2.parent.stem / mod_2.name), LayerType.replacement), args_0)
        self.assertEqual({"set_as_edit_target": False, "parent_layer": project_mock, "do_undo": False}, kwargs_0)

        args_1, kwargs_1 = insert_mock.call_args_list[1]
        self.assertEqual((str(project_mods_dir / mod_3.parent.stem / mod_3.name), LayerType.replacement), args_1)
        self.assertEqual({"set_as_edit_target": False, "parent_layer": project_mock, "do_undo": False}, kwargs_1)

    async def test_insert_capture_layer_should_insert_sublayer_and_lock(self):
        # Arrange
        project_dir = self.base_dir / "MyProject"
        project_capture_dir = project_dir / constants.REMIX_DEPENDENCIES_FOLDER / constants.REMIX_CAPTURE_FOLDER

        capture_file = project_capture_dir / "capture.usd"

        project_mock = Mock()

        with WizardMockContext() as mock:
            insert_mock = mock.core_mock.insert_sublayer
            lock_mock = mock.core_mock.lock_layer

            # Act
            await self.core._insert_capture_layer(  # noqa PLW0212
                mock.core_mock, project_capture_dir, capture_file, project_mock
            )

        # Assert
        self.assertEqual(1, insert_mock.call_count)
        self.assertEqual(1, lock_mock.call_count)

        insert_args, insert_kwargs = insert_mock.call_args
        self.assertEqual((str(project_capture_dir / capture_file.name), LayerType.capture), insert_args)
        self.assertEqual({"set_as_edit_target": False, "parent_layer": project_mock, "do_undo": False}, insert_kwargs)

        lock_args, lock_kwargs = lock_mock.call_args
        self.assertEqual((LayerType.capture,), lock_args)
        self.assertEqual({"do_undo": False}, lock_kwargs)

    async def test_save_authoring_layer_no_stage_quick_return(self):
        # Arrange
        pass

        with WizardMockContext() as mock:
            # Act
            await self.core._save_authoring_layer(self.base_dir, None, False)  # noqa PLW0212

        # Assert
        self.assertEqual(0, mock.save_custom_data_mock.call_count)

    async def test_save_authoring_layer_should_save_authoring_layer_to_custom_data(self):
        # Arrange
        stage_mock = Mock()

        with WizardMockContext() as mock:
            # Act
            await self.core._save_authoring_layer(self.base_dir, stage_mock, False)  # noqa PLW0212

        # Assert
        self.assertEqual(1, mock.save_custom_data_mock.call_count)
        self.assertEqual(call(stage_mock), mock.save_custom_data_mock.call_args)

    async def test_save_project_layer_should_save_workfile(self):
        # Arrange

        with WizardMockContext() as mock:
            save_mock = mock.core_mock.save_layer

            # Act
            await self.core._save_project_layer(mock.core_mock, False)  # noqa PLW0212

        # Assert
        self.assertEqual(1, save_mock.call_count)
        self.assertEqual(call(LayerType.workfile), save_mock.call_args)

    async def __run_test_setup_project_should_setup_project(self, existing_or_new: bool):
        # Arrange
        project_file = self.base_dir / "projects" / "MyProject" / "my_project.usda"
        remix_dir = self.base_dir / "rtx_remix"
        captures_dir = remix_dir / constants.REMIX_CAPTURE_FOLDER
        mods_dir = remix_dir / constants.REMIX_MODS_FOLDER
        project_dir = project_file.parent
        deps_dir = project_dir / constants.REMIX_DEPENDENCIES_FOLDER
        deps_mods_dir = deps_dir / constants.REMIX_MODS_FOLDER
        deps_captures_dir = deps_dir / constants.REMIX_CAPTURE_FOLDER

        mod_file = mods_dir / "ExistingMod" / "mod.usda"
        capture_file = captures_dir / "capture.usda"
        existing_mods = [mod_file]

        schema = ProjectWizardSchemaMock(
            existing_project=False,
            project_file=project_file,
            remix_directory=remix_dir,
            existing_mods=existing_mods,
            mod_file=mod_file if existing_or_new else None,
            capture_file=capture_file,
        )

        core_mock = Mock()
        context_mock = Mock()
        stage_mock = Mock()
        project_mock = Mock()
        project_stage_mock = Mock()

        if existing_or_new:
            final_mod_file = project_dir / mod_file.name
        else:
            final_mod_file = project_dir / constants.REMIX_MOD_FILE

        with WizardMockContext(schema_mock=schema, mock_wizard_methods=True) as mock:
            mock.core_mock.return_value = core_mock

            setup_usd_future = asyncio.Future()
            setup_usd_future.set_result((context_mock, stage_mock))
            mock.setup_usd_mock.return_value = setup_usd_future

            create_project_future = asyncio.Future()
            create_project_future.set_result((project_mock, project_stage_mock))
            mock.create_project_mock.return_value = create_project_future

            setup_existing_future = asyncio.Future()
            setup_existing_future.set_result(final_mod_file)
            mock.setup_existing_mod_mock.return_value = setup_existing_future

            setup_new_future = asyncio.Future()
            setup_new_future.set_result(final_mod_file)
            mock.setup_new_mod_mock.return_value = setup_new_future

            # Act
            await self.core.setup_project_async_with_exceptions({})

        # Assert
        self.assertEqual(1, mock.setup_usd_mock.call_count)
        self.assertEqual(call(), mock.setup_usd_mock.call_args)

        self.assertEqual(1, mock.create_symlinks_mock.call_count)
        self.assertEqual(call(project_dir, deps_dir, remix_dir, False), mock.create_symlinks_mock.call_args)

        self.assertEqual(1, mock.create_project_mock.call_count)
        self.assertEqual(
            call(project_file, core_mock, context_mock, stage_mock, False), mock.create_project_mock.call_args
        )

        self.assertEqual(1, mock.insert_existing_mods_mock.call_count)
        self.assertEqual(
            call(core_mock, existing_mods, mod_file if existing_or_new else None, deps_mods_dir, project_mock),
            mock.insert_existing_mods_mock.call_args,
        )

        self.assertEqual(1, mock.insert_capture_layer_mock.call_count)
        self.assertEqual(
            call(core_mock, deps_captures_dir, capture_file, project_mock), mock.insert_capture_layer_mock.call_args
        )

        self.assertEqual(1, mock.save_authoring_layer_mock.call_count)
        self.assertEqual(call(final_mod_file, project_stage_mock, False), mock.save_authoring_layer_mock.call_args)

        self.assertEqual(1, mock.save_project_layer_mock.call_count)
        self.assertEqual(call(core_mock, False), mock.save_project_layer_mock.call_args)

        if existing_or_new:
            self.assertEqual(1, mock.setup_existing_mod_mock.call_count)
            self.assertEqual(0, mock.setup_new_mod_mock.call_count)
            self.assertEqual(
                call(core_mock, mod_file, project_dir, project_mock, False), mock.setup_existing_mod_mock.call_args
            )
        else:
            self.assertEqual(0, mock.setup_existing_mod_mock.call_count)
            self.assertEqual(1, mock.setup_new_mod_mock.call_count)
            self.assertEqual(call(core_mock, project_dir, project_mock, False), mock.setup_new_mod_mock.call_args)

        self.assertEqual(11, mock.progress_mock.call_count)
        self.assertEqual(
            [
                call(0),
                call(10),
                call(20),
                call(30),
                call(40),
                call(50),
                call(60),
                call(70),
                call(80),
                call(90),
                call(100),
            ],
            mock.progress_mock.call_args_list,
        )

        self.assertEqual(1, mock.finished_mock.call_count)
        self.assertEqual(call(True), mock.finished_mock.call_args)

        self.assertEqual(0, mock.log_error_mock.call_count)

    async def __run_test_create_symlinks_should_quick_return(self, deps_or_remix: bool):
        # Arrange
        project_file = self.base_dir / "MyProject" / "project.usda"
        remix_dir = self.base_dir / constants.REMIX_FOLDER
        deps_dir = project_file.parent / constants.REMIX_DEPENDENCIES_FOLDER

        with WizardMockContext() as mock:
            # Act
            value = await self.core._create_symlinks(  # noqa PLW0212
                project_file.parent, deps_dir if deps_or_remix else None, None if deps_or_remix else remix_dir, False
            )

        # Assert
        self.assertEqual(0, mock.path_exists_mock.call_count)
        self.assertEqual(None if deps_or_remix else "Unable to find the path to the project dependencies", value)

    async def __run_test_create_symlinks_exists_should_not_symlink(self, deps_or_remix: bool):
        # Arrange
        project_file_base = Path("MyProject") / "project.usda"
        project_file = self.base_dir / project_file_base
        remix_dir = self.base_dir / constants.REMIX_FOLDER
        deps_dir = project_file.parent / constants.REMIX_DEPENDENCIES_FOLDER

        with WizardMockContext() as mock:
            mock.path_exists_mock.side_effect = [True, False] if deps_or_remix else [False, True]

            # Act
            value = await self.core._create_symlinks(project_file.parent, deps_dir, remix_dir, False)  # noqa PLW0212

        # Assert
        self.assertEqual(2, mock.path_exists_mock.call_count)
        self.assertEqual(1, mock.check_call_mock.call_count)

        remix_project_dir = remix_dir / constants.REMIX_MODS_FOLDER / project_file_base
        self.assertEqual(
            None if deps_or_remix else f"A project with the same name already exists: '{remix_project_dir}'",
            value,
        )

        project_dir = project_file.parent
        mod_link_dir = remix_dir / constants.REMIX_MODS_FOLDER / project_dir.stem

        args, kwargs = mock.check_call_mock.call_args
        if deps_or_remix:
            self.assertEqual(f'mklink /J "{mod_link_dir}" "{project_dir}"', args[0])
        else:
            self.assertEqual(f'mklink /J "{deps_dir}" "{remix_dir}"', args[0])
        self.assertEqual({"shell": True}, kwargs)

    async def __run_test_insert_existing_mods_should_quick_return(
        self, existing_mods: Optional[List[Path]], project_layer: Optional[Mock]
    ):
        # Arrange

        with WizardMockContext() as mock:
            insert_mock = mock.core_mock.insert_sublayer

            # Act
            await self.core._insert_existing_mods(  # noqa PLW0212
                mock.core_mock, existing_mods, self.base_dir, self.base_dir, project_layer
            )

        # Assert
        self.assertEqual(0, insert_mock.call_count)
