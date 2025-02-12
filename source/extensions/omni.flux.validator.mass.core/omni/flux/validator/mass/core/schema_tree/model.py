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

from typing import Any, Callable, Dict, List, Optional

import omni.ui as ui
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema

HEADER_DICT = {0: "Items"}


class Item(ui.AbstractItem):
    """Item of the model"""

    def __init__(self, data):
        super().__init__()
        self._data = data
        self._title = data["name"]
        self.title_model = ui.SimpleStringModel(self.title)
        # for each schema, we create a default Pydantic model
        self._model = _ManagerCore(data)

        self.__on_mouse_released = _Event()
        self.__on_mass_cook_template = _Event()

        self.__sub_mass_cook_template = None  # noqa PLW0238

    def can_item_have_children(self, item: "Item") -> bool:
        """
        Define if the item can have children or not

        Args:
            item: the item itself

        Returns:
            If the item can has a children or not
        """
        return False

    @omni.usd.handle_exception
    async def cook_template(self) -> List[Dict[Any, Any]]:
        return await self.cook_template_no_exception()

    async def cook_template_no_exception(self) -> List[Dict[Any, Any]]:
        """
        Cook template: meaning that from some input template(s), we can generate others templates.
        The idea of "cooking" is that a plugin can "edit" template(s) and give back edited template(s).

        The algo is: if a plugin return a list of templates during the cooking, the input template will be replaced
        by this list like: [template01] -> [cooked_template01_01, cooked_template01_02, cooked_template01_03...].

        For example, imagine a template where a plugin has a list of files as a data attribute. Cooking can be that the
        plugin generates 1 new template for each file. From here, the Validator can process each template one by one,
        and not all files in one process.

        Returns:
            List of new/cooked template
        """

        async def _cook_mass_template(cooked_plugins, _cooked_schemas: List[_ValidationSchema]):
            result_schema = []
            if cooked_plugins[0].data.cook_mass_template:
                self.__sub_mass_cook_template = cooked_plugins[0].instance.subscribe_mass_cook_template(  # noqa PLW0238
                    self.on_mass_cook_template
                )
                for cooked_schema in _cooked_schemas:
                    success, message, result = (
                        await cooked_plugins[0].instance.mass_cook_template(cooked_plugins[0].data) or []
                    )
                    if not success:
                        raise ValueError(message)
                    for data in result:
                        for cooked_plugin in cooked_plugins:
                            cooked_plugin.data = data
                        if data.display_name_mass_template:
                            cooked_schema.name = data.display_name_mass_template
                        if data.uuid:
                            cooked_schema.uuid = data.uuid
                        if data.display_name_mass_template_tooltip:
                            current_data = cooked_schema.data
                            if current_data is None:
                                current_data = {}
                            current_data.update({"name_tooltip": data.display_name_mass_template_tooltip})
                            cooked_schema.data = current_data
                        result_schema.append(_ValidationSchema(**cooked_schema.dict()))
            if not result_schema:
                result_schema = list(_cooked_schemas)
            return result_schema

        model_clone = _ManagerCore(self._model.model.dict())
        final_result = await _cook_mass_template([model_clone.model.context_plugin], [model_clone.model])

        cooked_schemas5 = []
        for i, schema in enumerate(final_result):  # noqa
            cooked_schemas = [schema]
            for i2, _cooked_check_plugin_model in enumerate(cooked_schemas[-1].check_plugins):
                # sub context
                cooked_schemas = await _cook_mass_template(
                    [cooked_schema.check_plugins[i2].context_plugin for cooked_schema in cooked_schemas], cooked_schemas
                )

                # selector
                cooked_schemas2 = list(cooked_schemas)
                for i3, _cooked_select_plugins_model in enumerate(
                    cooked_schemas2[0].check_plugins[i2].selector_plugins
                ):
                    cooked_select_plugins_models = []
                    for cooked_schema2 in cooked_schemas2:
                        cooked_select_plugins_models.append(cooked_schema2.check_plugins[i2].selector_plugins[i3])
                    cooked_schemas2 = await _cook_mass_template(cooked_select_plugins_models, cooked_schemas2)

                # check
                cooked_schemas3 = list(cooked_schemas2)
                cooked_schemas3 = await _cook_mass_template(
                    [cooked_schema3.check_plugins[i2] for cooked_schema3 in cooked_schemas3], cooked_schemas3
                )

                # resultors
                cooked_schemas4 = list(cooked_schemas3)
                if cooked_schemas4[0].check_plugins[i2].resultor_plugins:
                    for i4, _cooked_resultor_plugins_model in enumerate(
                        cooked_schemas4[0].check_plugins[i2].resultor_plugins
                    ):
                        cooked_resultor_plugins_models = []
                        for cooked_schema4 in cooked_schemas4:
                            cooked_resultor_plugins_models.append(cooked_schema4.check_plugins[i2].resultor_plugins[i4])
                        cooked_schemas4 = await _cook_mass_template(cooked_resultor_plugins_models, cooked_schemas4)

                cooked_schemas = list(cooked_schemas4)

            # resultor
            if cooked_schemas[-1].resultor_plugins:
                cooked_resultor_plugins = []
                for i4, _cooked_resultor_plugin in enumerate(cooked_schemas[-1].resultor_plugins):
                    for cooked_schema in cooked_schemas:
                        cooked_resultor_plugins.append(cooked_schema.resultor_plugins[i4])
                cooked_schemas5 = await _cook_mass_template(cooked_resultor_plugins, cooked_schemas5)
            cooked_schemas5.extend(cooked_schemas)

        return [cooked_schemas.dict() for cooked_schemas in cooked_schemas5]

    @omni.usd.handle_exception
    async def build_ui(self):
        """
        Build the Mass UI.
        For each plugin, run the mass_build_ui() function if the plugin exposes it.
        """
        was_build = False
        with ui.VStack():
            if self._model.model.context_plugin.data.expose_mass_ui:
                was_build = True
                with ui.Frame():
                    await self._model.model.context_plugin.instance.mass_build_ui(self._model.model.context_plugin.data)
                ui.Spacer(height=ui.Pixel(8))
            for check_plugin_model in self._model.model.check_plugins:
                if check_plugin_model.context_plugin.data.expose_mass_ui:
                    was_build = True
                    ui.Line(
                        height=ui.Pixel(2),
                        tooltip=f"Sub context plugin {check_plugin_model.context_plugin.name}",
                        name="PropertiesPaneSectionTitle",
                    )
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.Frame():
                        await check_plugin_model.context_plugin.instance.mass_build_ui(check_plugin_model.data)
                    ui.Spacer(height=ui.Pixel(8))

                for select_plugin_model in check_plugin_model.selector_plugins:
                    if select_plugin_model.data.expose_mass_ui:
                        was_build = True
                        ui.Line(
                            height=ui.Pixel(2),
                            tooltip=f"Selector plugin {select_plugin_model.name}",
                            name="PropertiesPaneSectionTitle",
                        )
                        ui.Spacer(height=ui.Pixel(8))
                        with ui.Frame():
                            await select_plugin_model.instance.mass_build_ui(select_plugin_model.data)
                        ui.Spacer(height=ui.Pixel(8))

                if check_plugin_model.data.expose_mass_ui:
                    was_build = True
                    ui.Line(
                        height=ui.Pixel(2),
                        tooltip=f"Check plugin {check_plugin_model.name}",
                        name="PropertiesPaneSectionTitle",
                    )
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.Frame():
                        await check_plugin_model.instance.mass_build_ui(check_plugin_model.data)
                    ui.Spacer(height=ui.Pixel(8))
            if self._model.model.resultor_plugins:
                for resultor_plugin in self._model.model.resultor_plugins:  # noqa
                    if resultor_plugin.data.expose_mass_ui:
                        was_build = True
                        ui.Line(
                            height=ui.Pixel(2),
                            tooltip=f"Resultor plugin {resultor_plugin.name}",
                            name="PropertiesPaneSectionTitle",
                        )
                        ui.Spacer(height=ui.Pixel(8))
                        with ui.Frame():
                            await resultor_plugin.instance.mass_build_ui(resultor_plugin.data)
                        ui.Spacer(height=ui.Pixel(8))
        return was_build

    def show(self, value: bool):
        """
        Called whenever the item is show or hidden in the UI.
        """
        self._model.model.context_plugin.instance.show(value, self._model.model.context_plugin.data)

        for check_plugin_model in self._model.model.check_plugins:
            check_plugin_model.context_plugin.instance.show(value, check_plugin_model.data)

            for select_plugin_model in check_plugin_model.selector_plugins:
                select_plugin_model.instance.show(value, select_plugin_model.data)

            check_plugin_model.instance.show(value, check_plugin_model.data)

        for resultor_plugin in self._model.model.resultor_plugins:
            resultor_plugin.instance.show(value, resultor_plugin.data)

    def on_mouse_released(self):
        self.__on_mouse_released(self)

    def subscribe_mouse_released(self, function: Callable[["Item"], Any]):
        """
        Subscribe to the *on_value_changed_callback* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mouse_released, function)

    def on_mass_cook_template(self, success: bool, message: Optional[str], data: Any):
        self.__on_mass_cook_template(success, message, data)

    def subscribe_mass_cook_template(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_cook_template, callback)

    @property
    def model(self) -> _ManagerCore:
        """The model"""
        return self._model

    @property
    def title(self) -> str:
        """The title that will be showed on the tree"""
        return self._title

    def __repr__(self):
        return self.title


class Model(ui.AbstractItemModel):
    """Basic list model"""

    def __init__(self):
        super().__init__()
        self.__items: List[Item] = []
        self.__sub_mouse_pressed = []
        self.__subs_mass_cook_template = []

        self.__on_mass_cook_template = _Event()

    def add_schemas(self, datas: List[Dict[Any, Any]]):
        """Set the items to show"""
        for data in datas:
            item = Item(data)
            self.__subs_mass_cook_template.append(item.subscribe_mass_cook_template(self.on_mass_cook_template))
            self.__items.append(item)
        self._item_changed(None)

    def subscribe_item_mouse_released(self, function: Callable[["Item"], Any]):
        for item in self.__items:
            self.__sub_mouse_pressed.append(item.subscribe_mouse_released(function))

    def on_mass_cook_template(self, success: bool, message: Optional[str], data: Any):
        self.__on_mass_cook_template(success, message, data)

    def subscribe_mass_cook_template(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_cook_template, callback)

    def get_item_children(self, item: Optional[Item]):
        """Returns all the children when the widget asks it."""
        if item is None:
            return self.__items
        return []

    def get_item_value_model_count(self, item: Item):
        """The number of columns"""
        return len(HEADER_DICT.keys())

    def get_item_value_model(self, item, column_id):
        """
        Return value model.
        It's the object that tracks the specific value.
        In our case we use ui.SimpleStringModel.
        """
        if item is None:
            return self.__items
        if column_id == 0:
            return item.title_model
        return None

    def destroy(self):
        self.__items = []
        self.__sub_mouse_pressed = []
