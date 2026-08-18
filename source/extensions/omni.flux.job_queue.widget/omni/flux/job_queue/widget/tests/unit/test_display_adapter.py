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

from unittest.mock import MagicMock, patch

import omni.kit.test
from omni.flux.factory.base import FactoryBase
from omni.flux.job_queue.core.job import Job, JobInputs, JobOutputs, JobProgressCallback
from omni.flux.job_queue.widget.display_adapter_base import (
    JobDetailDirectories,
    JobDetailField,
    JobDetailSection,
    JobDisplayAdapter,
    is_standalone,
)
from omni.flux.job_queue.widget.display_adapter_registry import DisplayAdapterRegistry
from omni.flux.job_queue.widget.enums import DisplayState, JobDetailSectionPlacement

__all__ = ("TestDisplayAdapter",)

_CONTEXT_NAME = "stagecraft"


class _MockJob(Job):
    """Concrete Job subclass for testing."""

    async def execute(self, _job_directory, _inputs: JobInputs, _progress_callback: JobProgressCallback) -> JobOutputs:
        """Complete a no-op test job.

        Args:
            _job_directory: Directory allocated for the job's output.
            _inputs: Resolved inputs supplied to the job.
            _progress_callback: Callback for reporting execution progress.

        Returns:
            Empty job outputs.
        """
        return JobOutputs()


class _DerivedMockJob(_MockJob):
    """Concrete subclass used to verify exact job-type matching."""


class _MockAdapterA(JobDisplayAdapter):
    """Test adapter that handles _MockJob."""

    name = "mock_a"
    job_type = _MockJob
    source_name = "TestA"
    display_name = "NameA"


class _MockAdapterB(JobDisplayAdapter):
    """Conflicting test adapter for _MockJob."""

    name = "mock_b"
    job_type = _MockJob
    source_name = "TestB"
    display_name = "NameB"


class _DerivedMockAdapter(JobDisplayAdapter):
    """Test adapter for the exact derived job type."""

    name = "derived_mock"
    job_type = _DerivedMockJob
    source_name = ""
    display_name = ""


class _DuplicateNameAdapter(_DerivedMockAdapter):
    """Adapter with a conflicting explicit stable name."""

    name = _MockAdapterA.name


class TestDisplayAdapter(omni.kit.test.AsyncTestCase):
    """Tests display adapter registration and default contracts."""

    async def setUp(self):
        """Create an isolated display-adapter registry."""
        self.registry = DisplayAdapterRegistry()

    async def tearDown(self):
        """Destroy the isolated display-adapter registry."""
        self.registry.destroy()

    async def test_register_adapter_makes_it_findable(self):
        """Registered adapter is returned by get_adapter for a matching job."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()

        # Act
        adapter = self.registry.get_adapter(job)

        # Assert
        self.assertIsNotNone(adapter)
        self.assertIsInstance(adapter, _MockAdapterA)

    async def test_registry_inherits_flux_factory_base(self):
        """Display adapter registry uses the shared Flux factory base."""
        # Arrange
        registry = self.registry

        # Act
        is_factory = isinstance(registry, FactoryBase)

        # Assert
        self.assertTrue(is_factory)

    async def test_get_adapter_returns_none_and_logs_error_when_no_match(self):
        """get_adapter returns None and logs a carb error when no adapter matches."""
        # Arrange
        job = _MockJob()

        # Act
        with patch("omni.flux.job_queue.widget.display_adapter_registry.carb") as mock_carb:
            adapter = self.registry.get_adapter(job)

        # Assert
        self.assertIsNone(adapter)
        mock_carb.log_warn.assert_called_once()

    async def test_register_conflicting_exact_job_type_raises_value_error(self):
        """A second adapter cannot make exact-type lookup load-order dependent."""
        # Arrange
        self.registry.register(_MockAdapterA)

        # Act
        with self.assertRaises(ValueError) as context:
            self.registry.register(_MockAdapterB)

        # Assert
        self.assertIn("_MockJob", str(context.exception))

    async def test_get_adapter_with_unregistered_subclass_returns_none(self):
        """An adapter registered for a base job does not handle its subclasses."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _DerivedMockJob()

        # Act
        with patch("omni.flux.job_queue.widget.display_adapter_registry.carb"):
            adapter = self.registry.get_adapter(job)

        # Assert
        self.assertIsNone(adapter)

    async def test_register_duplicate_name_for_different_type_raises_value_error(self):
        """Stable adapter names cannot silently overwrite another exact registration."""
        # Arrange
        self.registry.register(_MockAdapterA)

        # Act
        with self.assertRaises(ValueError) as context:
            self.registry.register(_DuplicateNameAdapter)

        # Assert
        self.assertIn(_MockAdapterA.name, str(context.exception))

    async def test_get_adapter_returns_adapter_registered_for_exact_subclass(self):
        """An exact subclass registration resolves independently of its base type."""
        # Arrange
        self.registry.register(_MockAdapterA)
        self.registry.register(_DerivedMockAdapter)
        job = _DerivedMockJob()

        # Act
        adapter = self.registry.get_adapter(job)

        # Assert
        self.assertIsInstance(adapter, _DerivedMockAdapter)

    async def test_get_adapter_caches_single_instance_per_class(self):
        """Same adapter class returns the same object identity on repeated calls."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()
        adapter1 = self.registry.get_adapter(job)

        # Act
        adapter2 = self.registry.get_adapter(job)

        # Assert
        self.assertIs(adapter1, adapter2)

    async def test_unregister_removes_adapter_from_lookup(self):
        """Unregister removes the adapter so it is no longer returned."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()
        self.registry.get_adapter(job)  # populate cache
        self.registry.unregister(_MockAdapterA)

        # Act
        with patch("omni.flux.job_queue.widget.display_adapter_registry.carb"):
            adapter = self.registry.get_adapter(job)

        # Assert
        self.assertIsNone(adapter)

    async def test_destroy_removes_all_adapters_from_lookup(self):
        """Destroy removes all registered adapters from lookup."""
        # Arrange
        self.registry.register(_MockAdapterA)
        self.registry.register(_DerivedMockAdapter)
        job = _MockJob()
        self.registry.get_adapter(job)  # populate cache
        self.registry.destroy()

        # Act
        with patch("omni.flux.job_queue.widget.display_adapter_registry.carb"):
            adapter = self.registry.get_adapter(job)

        # Assert
        self.assertIsNone(adapter)

    async def test_register_same_class_twice_is_idempotent(self):
        """Registering the same adapter class twice does not create duplicates."""
        # Arrange
        self.registry.register(_MockAdapterA)

        # Act
        self.registry.register(_MockAdapterA)

        # Assert
        self.assertEqual(len(self.registry.get_all_plugins()), 1)

    async def test_default_state_tooltip_returns_none(self):
        """Adapters opt into product-specific state help explicitly."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()
        adapter = self.registry.get_adapter(job)

        # Act
        tooltip = adapter.get_state_tooltip(job, DisplayState.IN_PROGRESS, "Running.")

        # Assert
        self.assertIsNone(tooltip)

    async def test_default_actions_and_action_event_subscription_are_empty(self):
        """Adapters opt into actions and action events explicitly."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()
        adapter = self.registry.get_adapter(job)

        # Act
        graph_actions = adapter.get_graph_actions(job, _CONTEXT_NAME)
        job_actions = adapter.get_job_actions(job, _CONTEXT_NAME)
        action_subscription = adapter.subscribe_action_events(MagicMock(context_name=_CONTEXT_NAME))

        # Assert
        self.assertEqual(graph_actions, ())
        self.assertEqual(job_actions, ())
        self.assertIsNone(action_subscription)

    async def test_default_detail_extensions_return_empty_values(self):
        """Adapters opt into safe product details and directories explicitly."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()
        adapter = self.registry.get_adapter(job)

        # Act
        sections = adapter.get_detail_sections(job, MagicMock(), _CONTEXT_NAME)
        directories = adapter.get_detail_directories(job, MagicMock(), _CONTEXT_NAME)

        # Assert
        self.assertEqual(sections, ())
        self.assertEqual(directories, JobDetailDirectories())

    async def test_unimplemented_advertised_action_fails_explicitly(self):
        """The base dispatcher never silently accepts an unknown action ID."""
        # Arrange
        self.registry.register(_MockAdapterA)
        job = _MockJob()
        adapter = self.registry.get_adapter(job)

        # Act
        with self.assertRaises(KeyError) as error:
            adapter.execute_action("retarget", job, _CONTEXT_NAME)

        # Assert
        self.assertEqual(error.exception.args, ("retarget",))

    async def test_detail_field_rejects_empty_stable_id(self):
        """Product detail fields require stable non-empty identifiers."""
        # Arrange
        stable_id = ""

        # Act
        with self.assertRaises(ValueError) as error:
            JobDetailField(stable_id, "Endpoint", "Local")

        # Assert
        self.assertIsInstance(error.exception, ValueError)

    async def test_detail_section_requires_identity_fields_and_typed_placement(self):
        """Product sections expose complete strongly typed presentation metadata."""
        # Arrange
        field = JobDetailField("server.endpoint", "Endpoint", "Local")
        invalid_sections = (
            ("", "Server", (field,), JobDetailSectionPlacement.BEFORE_INPUTS, ValueError),
            ("server", "", (field,), JobDetailSectionPlacement.BEFORE_INPUTS, ValueError),
            ("server", "Server", (), JobDetailSectionPlacement.BEFORE_INPUTS, ValueError),
            ("server", "Server", (field,), "after_outputs", TypeError),
        )

        # Act
        errors = []
        for stable_id, title, fields, placement, error_type in invalid_sections:
            with self.assertRaises(error_type) as error:
                JobDetailSection(stable_id, title, fields, placement=placement)
            errors.append(error.exception)

        # Assert
        self.assertEqual([type(error) for error in errors], [case[-1] for case in invalid_sections])
        self.assertEqual(
            JobDetailSection("server", "Server", (field,)).placement,
            JobDetailSectionPlacement.BEFORE_INPUTS,
        )

    async def test_is_standalone_returns_false_for_normal_app(self):
        """is_standalone returns False when app name is not a known standalone name."""
        # Arrange
        with patch("omni.flux.job_queue.widget.display_adapter_base.carb") as mock_carb:
            mock_settings = MagicMock()
            mock_settings.get.return_value = "sample.product.app"
            mock_carb.settings.get_settings.return_value = mock_settings

            # Act
            result = is_standalone()

        # Assert
        self.assertFalse(result)

    async def test_is_standalone_returns_true_for_standalone_app(self):
        """is_standalone returns True when app name matches a known standalone name."""
        # Arrange
        with patch("omni.flux.job_queue.widget.display_adapter_base.carb") as mock_carb:
            mock_settings = MagicMock()
            mock_settings.get.return_value = "rtx_remix_job_queue"
            mock_carb.settings.get_settings.return_value = mock_settings

            # Act
            result = is_standalone()

        # Assert
        self.assertTrue(result)

    async def test_is_standalone_returns_false_when_no_app_name(self):
        """is_standalone returns False when /app/name setting is not set."""
        # Arrange
        with patch("omni.flux.job_queue.widget.display_adapter_base.carb") as mock_carb:
            mock_settings = MagicMock()
            mock_settings.get.return_value = None
            mock_carb.settings.get_settings.return_value = mock_settings

            # Act
            result = is_standalone()

        # Assert
        self.assertFalse(result)
