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
from functools import partial
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.stage_manager.plugin.filter.usd.base import StageManagerUSDFilterPlugin

from ... import search
from ...search import SearchFilterPlugin

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
    prim.GetName.return_value = name
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

    async def test_build_filter_predicate_with_empty_term_returns_true_without_item_access(self):
        """Keep every item without reading it when the prepared search term is empty."""
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("HeroMesh")
        predicate = plugin.build_filter_predicate()

        # Act
        result = predicate(item)

        # Assert
        self.assertTrue(result)
        item.data.GetPath.assert_not_called()
        item.data.GetName.assert_not_called()
        item.data.GetAttribute.assert_not_called()

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
        """Match a literal prim name without regex or attribute access."""
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("HeroMesh")

        with patch.object(search.re, "compile", wraps=re.compile) as compile_mock:
            _set_search_term(plugin, "mesh")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(0, compile_mock.call_count)
        item.data.GetPath.assert_not_called()
        item.data.GetAttribute.assert_not_called()

    async def test_filter_predicate_literal_term_should_match_nickname_without_regex(self):
        """Match a literal nickname without compiling a regex."""
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("Mesh_001", nickname="HeroMesh")

        with patch.object(search.re, "compile", wraps=re.compile) as compile_mock:
            _set_search_term(plugin, "hero")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(0, compile_mock.call_count)

    async def test_filter_predicate_path_term_should_match_prim_path(self):
        """Match a full prim path without reading nickname attributes."""
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "/RootNode/Props")
        item = _make_item("HeroMesh", path="/RootNode/Props/HeroMesh")

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertTrue(plugin.filter_active)
        item.data.GetName.assert_not_called()
        item.data.GetAttribute.assert_not_called()

    async def test_filter_predicate_nonmatching_path_returns_false_without_name_or_attribute_access(self):
        """Reject a nonmatching path without reading the prim name or attributes."""
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "/RootNode/Props")
        item = _make_item("HeroMesh", path="/RootNode/Characters/HeroMesh")

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
        item.data.GetPath.assert_called_once()
        item.data.GetName.assert_not_called()
        item.data.GetAttribute.assert_not_called()

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
        """Treat path terms containing regex metacharacters as literal text."""
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("HeroMesh", path="/RootNode/Props[HeroMesh")

        with patch.object(search.re, "compile", wraps=re.compile) as compile_mock:
            _set_search_term(plugin, "/RootNode/Props[HeroMesh")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(0, compile_mock.call_count)

    async def test_filter_predicate_backslash_term_should_match_name_as_regex(self):
        """Compile a backslash search term as a regular expression."""
        # Arrange
        plugin = SearchFilterPlugin()
        item = _make_item("Mesh_001")

        with patch.object(search.re, "compile", wraps=re.compile) as compile_mock:
            _set_search_term(plugin, r"\d")

            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        self.assertEqual(1, compile_mock.call_count)

    async def test_filter_predicate_without_prepared_state_builds_current_search_state(self):
        """Build matching state when the predicate is called directly."""
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "mesh")
        item = _make_item("HeroMesh")

        with patch.object(plugin, "_get_search_state", wraps=plugin._get_search_state) as get_search_state_mock:
            # Act
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)
        get_search_state_mock.assert_called_once_with("mesh")

    async def test_on_edit_regex_term_should_activate_without_compiling(self):
        """Activate an edited regex term without preparing worker state."""
        # Arrange
        plugin = SearchFilterPlugin()

        with patch.object(search.re, "compile", wraps=re.compile) as compile_mock:
            # Act
            _set_search_term(plugin, "Hero.*01")

            # Assert
            self.assertTrue(plugin.filter_active)
            compile_mock.assert_not_called()

    async def test_filter_predicate_invalid_regex_should_return_false_without_searching_items(self):
        """Reject an invalid regex before reading item data."""
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "[")
        item = _make_item("HeroMesh")

        # Act
        result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
        item.data.GetPath.assert_not_called()
        item.data.GetName.assert_not_called()
        item.data.GetAttribute.assert_not_called()

    async def test_filter_predicate_regex_name_miss_matches_only_valued_matching_nickname(self):
        """Match regex nicknames only when their attributes hold matching values."""
        test_cases = (
            ("HeroMesh", "Hero.*", True, True),
            ("HeroMesh", "Villain.*", True, False),
            ("HeroMesh", "Hero.*", False, False),
        )

        for nickname, search_term, has_value, expected_result in test_cases:
            with self.subTest(search_term=search_term, has_value=has_value):
                # Arrange
                plugin = SearchFilterPlugin()
                item = _make_item("Mesh_001", nickname=nickname)
                nickname_attr = item.data.GetAttribute("nickname")
                item.data.GetAttribute.reset_mock()
                nickname_attr.HasValue.return_value = has_value
                _set_search_term(plugin, search_term)

                # Act
                result = plugin.filter_predicate(item)

                # Assert
                self.assertEqual(expected_result, result)
                item.data.GetName.assert_called_once()
                item.data.GetAttribute.assert_called_once_with("nickname")
                if has_value:
                    nickname_attr.Get.assert_called_once()
                else:
                    nickname_attr.Get.assert_not_called()

    async def test_build_filter_predicate_with_regex_term_compiles_once_for_multiple_items(self):
        """Compile refresh-local regex state once before evaluating multiple items."""
        # Arrange
        plugin = SearchFilterPlugin()
        _set_search_term(plugin, "Hero.*")
        hero_item = _make_item("HeroMesh")
        villain_item = _make_item("VillainMesh")

        with patch.object(search.re, "compile", wraps=re.compile) as compile_mock:
            predicate = plugin.build_filter_predicate()

            # Act
            results = [predicate(hero_item), predicate(villain_item)]

        # Assert
        self.assertIsInstance(predicate, partial)
        self.assertEqual(plugin.filter_predicate, predicate.func)
        self.assertEqual([True, False], results)
        compile_mock.assert_called_once_with("Hero.*", re.IGNORECASE)
