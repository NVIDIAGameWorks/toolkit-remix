"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin
from omni.flux.stage_manager.plugin.filter.usd.search import SearchFilterPlugin

__all__ = ["TestSearchFilterPluginUnit"]


class _Model:
    """Minimal string model used to trigger search edit handling."""

    def __init__(self, value: str):
        self._value = value

    def get_value_as_string(self):
        """Return the edited field text."""
        return self._value


class _PrimPath:
    """Minimal prim path test double with USD path string behavior."""

    def __init__(self, name: str, path: str | None = None):
        self.name = name
        self._path = path or f"/RootNode/{name}"

    def __str__(self) -> str:
        """Return the full prim path."""
        return self._path


def _make_item(name: str, nickname: str | None = None, path: str | None = None) -> StageManagerItem:
    """Build a Stage Manager item with fake USD prim data."""
    nickname_attr = Mock()
    nickname_attr.IsValid.return_value = nickname is not None
    nickname_attr.HasValue.return_value = nickname is not None
    nickname_attr.Get.return_value = nickname

    empty_attr = Mock()
    empty_attr.IsValid.return_value = False
    empty_attr.HasValue.return_value = False
    empty_attr.Get.return_value = None

    prim = Mock()
    prim.GetPath.return_value = _PrimPath(name, path)
    prim.GetAttribute.side_effect = lambda attr_name: nickname_attr if attr_name == "nickname" else empty_attr

    return StageManagerItem(name, data=prim)


def _set_search_term(plugin: SearchFilterPlugin, value: str):
    """Apply a search term through the same path used by the UI."""
    plugin._on_edit(_Model(value))


class TestSearchFilterPluginUnit(omni.kit.test.AsyncTestCase):
    async def test_filter_active_empty_search_term_should_return_false(self):
        # Arrange
        plugin = SearchFilterPlugin()

        # Assert
        self.assertFalse(plugin.filter_active)

    async def test_filter_active_search_term_should_return_true(self):
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "mesh")

        # Assert
        self.assertTrue(plugin.filter_active)

    async def test_model_post_init_should_call_usd_base_model_post_init(self):
        # Arrange
        with patch.object(StageManagerUSDFilterPlugin, "model_post_init", autospec=True) as post_init_mock:
            # Act
            SearchFilterPlugin()

        # Assert
        post_init_mock.assert_called_once()

    async def test_filter_predicate_literal_term_should_match_name_without_regex(self):
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "mesh")
        item = _make_item("HeroMesh")

        with patch("omni.flux.stage_manager.plugin.filter.usd.search.re.search") as search_mock:
            search_mock.side_effect = AssertionError("literal search should not use regex")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_literal_term_should_match_nickname_without_regex(self):
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "hero")
        item = _make_item("Mesh_001", nickname="HeroMesh")

        with patch("omni.flux.stage_manager.plugin.filter.usd.search.re.search") as search_mock:
            search_mock.side_effect = AssertionError("literal search should not use regex")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_path_term_should_match_prim_path(self):
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "/RootNode/Props")
        item = _make_item("HeroMesh", path="/RootNode/Props/HeroMesh")

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertTrue(plugin.filter_active)

    async def test_filter_predicate_relative_path_term_should_match_prim_path(self):
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "Props/HeroMesh")
        item = _make_item("HeroMesh", path="/RootNode/Props/HeroMesh")

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_path_term_with_regex_meta_should_match_prim_path_without_regex(self):
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("HeroMesh", path="/RootNode/Props[HeroMesh")

        with patch("omni.flux.stage_manager.plugin.filter.usd.search.re.compile", wraps=re.compile) as compile_mock:
            _set_search_term(plugin, "/RootNode/Props[HeroMesh")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(0, compile_mock.call_count)

    async def test_filter_predicate_backslash_term_should_match_name_as_regex(self):
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("Mesh_001")

        with patch("omni.flux.stage_manager.plugin.filter.usd.search.re.compile", wraps=re.compile) as compile_mock:
            _set_search_term(plugin, r"\d")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(1, compile_mock.call_count)

    async def test_filter_predicate_direct_search_term_assignment_should_prepare_search_state(self):
        # Arrange
        plugin = SearchFilterPlugin()
        plugin.search_term = "mesh"
        item = _make_item("HeroMesh")

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_direct_search_term_assignment_should_update_filter_active(self):
        # Arrange
        plugin = SearchFilterPlugin()
        plugin.search_term = "mesh"
        item = _make_item("HeroMesh")

        # Assert
        self.assertFalse(plugin.filter_active)

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertTrue(plugin.filter_active)

    async def test_on_edit_regex_term_should_compile_once(self):
        # Arrange
        plugin = SearchFilterPlugin()

        with patch("omni.flux.stage_manager.plugin.filter.usd.search.re.compile", wraps=re.compile) as compile_mock:
            # Act
            _set_search_term(plugin, "Hero.*01")

            # Assert
            self.assertEqual(1, compile_mock.call_count)

        self.assertTrue(plugin.filter_predicate(_make_item("HeroMesh01")))

    async def test_filter_predicate_invalid_regex_should_return_false_without_searching_items(self):
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "[")
        item = _make_item("HeroMesh")

        with patch("omni.flux.stage_manager.plugin.filter.usd.search.re.search") as search_mock:
            search_mock.side_effect = AssertionError("invalid regex should be rejected on edit")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
