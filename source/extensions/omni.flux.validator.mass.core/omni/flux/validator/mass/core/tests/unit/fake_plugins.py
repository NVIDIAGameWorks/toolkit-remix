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

from typing import Any, Awaitable, Callable, List, Optional, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.validator.factory import CheckBase as _CheckBase
from omni.flux.validator.factory import ContextBase as _ContextBase
from omni.flux.validator.factory import SelectorBase as _SelectorBase
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import get_instance as _get_factory_instance


class FakeContext(_ContextBase):
    class Data(_ContextBase.Data):
        fake_data: Optional[str] = None

    name = "FakeContext"
    display_name = "Fake Context"
    tooltip = "Fake Context plugin"
    data_type = Data

    @omni.usd.handle_exception
    async def _check(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> Tuple[bool, str]:
        """
        Function that will be called to execute the data.

        Args:
            schema_data: the USD file path to check
            parent_context: context data from the parent context

        Returns: True if the check passed, False if not
        """
        return True, "Fake data"

    async def _setup(
        self,
        schema_data: Data,
        run_callback: Callable[[_SetupDataTypeVar], Awaitable[None]],
        parent_context: _SetupDataTypeVar,
    ) -> Tuple[bool, str, _SetupDataTypeVar]:
        """
        Function that will be executed to set the data. Here we will open the file path and give the stage

        Args:
            schema_data: the data that we should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns: True if ok + message + data that need to be passed into another plugin
        """
        await run_callback("fake_context_data")
        return (
            True,
            "Fake message",
            "Fake data",
        )

    async def _on_exit(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> Tuple[bool, str]:
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the on exit passed, False if not.
            str: the message you want to show, like "Succeeded to exit this context"
        """
        return True, "Exit ok"

    @omni.usd.handle_exception
    async def _mass_cook_template(self, schema_data_template: Data) -> Tuple[bool, Optional[str], List[Data]]:
        """
        Take a template as an input and the (previous) result, and edit the result for mass processing.
        Here, for each file input, we generate a list of schema

        Args:
            schema_data_template: the data of the plugin from the schema

        Returns:
            A tuple of the shape `(TemplateCookingSuccess, ErrorMessage, CookingData)`
        """
        # for mass ingestion, from the template, we want to generate multiple schema from the template by input file
        result = []
        for i in range(3):
            schema = self.Data(**schema_data_template.dict())
            schema.display_name_mass_template = f"Job display name {i}"
            schema.display_name_mass_template_tooltip = f"Job display tooltip {i}"
            result.append(schema)
        return True, None, result

    def _mass_build_queue_action_ui(
        self, schema_data: Data, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> None:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """

        def __print_text():
            print("Fake action clicked")
            callback("show_in_viewport")

        # for mass, we only have one input.
        with ui.VStack(width=ui.Pixel(28), height=ui.Pixel(28)):
            ui.Spacer(height=ui.Pixel(2))
            with ui.ZStack():
                ui.Rectangle(name="BackgroundWithWhiteBorder")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(2))
                    ui.Button("Fake context action", clicked_fn=__print_text)
                    ui.Spacer(width=ui.Pixel(2))
            ui.Spacer(height=ui.Pixel(2))

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Data) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        ui.Label("Fake context mass UI")

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("Fake context label", alignment=ui.Alignment.CENTER)

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass


class FakeSelector(_SelectorBase):
    class Data(_SelectorBase.Data):
        fake_data: Optional[str] = None

    name = "FakeSelector"
    tooltip = "Fake selector plugin"
    data_type = Data

    @omni.usd.handle_exception
    async def _select(
        self, schema_data: Data, context_plugin_data: Any, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to select the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the previous selector plugin

        Returns: True if ok + message + the selected data
        """
        return True, "Ok", "Fake selection data"

    @omni.usd.handle_exception
    async def _mass_cook_template(self, schema_data_template: Data) -> Tuple[bool, Optional[str], List[Data]]:
        """
        Take a template as an input and the (previous) result, and edit the result for mass processing.
        Here, for each file input, we generate a list of schema

        Args:
            schema_data_template: the data of the plugin from the schema

        Returns:
            A tuple of the shape `(TemplateCookingSuccess, ErrorMessage, CookingData)`
        """
        # for mass ingestion, from the template, we want to generate multiple schema from the template by input file
        result = []
        for i in range(3):
            schema = self.Data(**schema_data_template.dict())
            schema.display_name_mass_template = f"Job display name {i}"
            schema.display_name_mass_template_tooltip = f"Job display tooltip {i}"
            result.append(schema)
        return True, None, result

    def _mass_build_queue_action_ui(
        self, schema_data: Data, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> None:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """

        def __print_text():
            print("Fake action clicked")
            callback("show_in_viewport")

        # for mass, we only have one input.
        with ui.VStack(width=ui.Pixel(28), height=ui.Pixel(28)):
            ui.Spacer(height=ui.Pixel(2))
            with ui.ZStack():
                ui.Rectangle(name="BackgroundWithWhiteBorder")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(2))
                    ui.Button("Fake selector action", clicked_fn=__print_text)
                    ui.Spacer(width=ui.Pixel(2))
            ui.Spacer(height=ui.Pixel(2))

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Data) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        ui.Label("Fake selector mass UI")

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("Fake selector label", alignment=ui.Alignment.CENTER)

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass


class FakeCheck(_CheckBase):
    class Data(_CheckBase.Data):
        fake_data: Optional[str] = None

    name = "FakeCheck"
    tooltip = "Fake check plugin"
    data_type = Data

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the check passed, False if not
        """
        return True, "Ok", "Fake check data"

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        return True, "Ok", "Fake check data"

    @omni.usd.handle_exception
    async def _mass_cook_template(self, schema_data_template: Data) -> Tuple[bool, Optional[str], List[Data]]:
        """
        Take a template as an input and the (previous) result, and edit the result for mass processing.
        Here, for each file input, we generate a list of schema

        Args:
            schema_data_template: the data of the plugin from the schema

        Returns:
            A tuple of the shape `(TemplateCookingSuccess, ErrorMessage, CookingData)`
        """
        # for mass ingestion, from the template, we want to generate multiple schema from the template by input file
        result = []
        for i in range(3):
            schema = self.Data(**schema_data_template.dict())
            schema.display_name_mass_template = f"Job display name {i}"
            schema.display_name_mass_template_tooltip = f"Job display tooltip {i}"
            result.append(schema)
        return True, None, result

    def _mass_build_queue_action_ui(
        self, schema_data: Data, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> None:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """

        def __print_text():
            print("Fake action clicked")
            callback("show_in_viewport")

        # for mass, we only have one input.
        with ui.VStack(width=ui.Pixel(28), height=ui.Pixel(28)):
            ui.Spacer(height=ui.Pixel(2))
            with ui.ZStack():
                ui.Rectangle(name="BackgroundWithWhiteBorder")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(2))
                    ui.Button("Fake check action", clicked_fn=__print_text)
                    ui.Spacer(width=ui.Pixel(2))
            ui.Spacer(height=ui.Pixel(2))

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Data) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        ui.Label("Fake check mass UI")

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI for the plugin
        """
        ui.Label("Fake check label", alignment=ui.Alignment.CENTER)

    @omni.usd.handle_exception
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        pass


def register_fake_plugins():
    _get_factory_instance().register_plugins([FakeContext, FakeSelector, FakeCheck])


def unregister_fake_plugins():
    _get_factory_instance().unregister_plugins([FakeContext, FakeSelector, FakeCheck])
