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

__all__ = ("TestGateDefaults", "TestInstantiateServices", "TestRoutesPackage")

import importlib
import pkgutil
from unittest import mock

import carb.settings
import omni.kit.test
from omni.flux.factory.base import FactoryBase
from omni.flux.service.factory import ServiceBase

from lightspeed.trex.service.core import routes as _routes_package
from lightspeed.trex.service.core import service as _service_module
from lightspeed.trex.service.core.routes import ROUTE_SERVICES
from lightspeed.trex.service.core.service import CoreService

_SETTINGS_ROOT = "/exts/lightspeed.trex.service.core"


class _KnownService(ServiceBase):
    """Registrable stand-in that builds its router the way a real service does."""

    def __init__(self, context_name: str = ""):
        self.context_name = context_name
        # Real services call this; it is what creates `_router`, which CoreService then reads.
        # Omitting it would let this fixture pass tests that a real service would fail.
        super().__init__()

    def register_endpoints(self):
        """Declare no endpoints; the router only has to exist."""


def _config(name: str, context: str = "") -> dict:
    """Build one entry in the shape the `services` setting uses."""
    return {"name": name, "context": context, "title": name, "description": name}


class TestInstantiateServices(omni.kit.test.AsyncTestCase):
    """Cover the lookup that turns configured service names into instances."""

    async def setUp(self):
        self.factory = FactoryBase[ServiceBase]()
        self.factory.register_plugins([_KnownService])

    async def test_known_service_is_instantiated(self):
        # Arrange
        entries = [_config("_KnownService")]

        # Act
        resolved = CoreService._instantiate_services(self.factory, entries)

        # Assert
        self.assertEqual(len(resolved), 1)
        self.assertIsInstance(resolved[0][1], _KnownService)

    async def test_resolved_instance_exposes_the_router_core_service_reads(self):
        # A service that resolves but has no `router` kills startup at `main.register_router`,
        # well past the point this helper returns.
        # Arrange
        entries = [_config("_KnownService")]

        # Act
        resolved = CoreService._instantiate_services(self.factory, entries)

        # Assert
        self.assertIsNotNone(resolved[0][1].router)

    async def test_configured_context_reaches_the_instance(self):
        # Arrange
        entries = [_config("_KnownService", context="ingestcraft")]

        # Act
        resolved = CoreService._instantiate_services(self.factory, entries)

        # Assert
        self.assertEqual(resolved[0][1].context_name, "ingestcraft")

    async def test_unregistered_service_is_skipped_not_fatal(self):
        # Before the skip, this called the `None` the factory returns and killed startup.
        # Arrange
        entries = [_config("NotRegisteredService")]

        # Act
        with mock.patch.object(_service_module.carb, "log_error") as log_error:
            resolved = CoreService._instantiate_services(self.factory, entries)

        # Assert
        self.assertEqual(resolved, [])
        self.assertIn("NotRegisteredService", log_error.call_args[0][0])

    async def test_skip_is_logged_at_error_not_warning(self):
        # Nothing in `services` is gated today, so a skip is always a real failure. Logged below
        # error it would leave an app serving an empty REST surface while reporting healthy —
        # and Kit's stdoutFailPatterns would not catch it either.
        # Arrange
        entries = [_config("NotRegisteredService")]

        # Act
        with mock.patch.object(_service_module.carb, "log_error") as log_error:
            with mock.patch.object(_service_module.carb, "log_warn") as log_warn:
                CoreService._instantiate_services(self.factory, entries)

        # Assert
        self.assertEqual(log_error.call_count, 1)
        self.assertEqual(log_warn.call_count, 0)

    async def test_known_services_survive_an_unregistered_neighbour(self):
        # Arrange
        entries = [_config("NotRegisteredService"), _config("_KnownService")]

        # Act
        with mock.patch.object(_service_module.carb, "log_error"):
            resolved = CoreService._instantiate_services(self.factory, entries)

        # Assert
        self.assertEqual([entry["name"] for entry, _ in resolved], ["_KnownService"])

    async def test_setting_entry_is_paired_with_its_instance(self):
        # The caller reads `title` and `description` off the entry to build the OpenAPI tag, so
        # the pairing has to survive a skip earlier in the list.
        # Arrange
        entries = [_config("NotRegisteredService"), _config("_KnownService")]

        # Act
        with mock.patch.object(_service_module.carb, "log_error"):
            resolved = CoreService._instantiate_services(self.factory, entries)

        # Assert
        entry, instance = resolved[0]
        self.assertEqual(entry["title"], "_KnownService")
        self.assertIsInstance(instance, _KnownService)


class TestGateDefaults(omni.kit.test.AsyncTestCase):
    """Pin the agentic gate off."""

    async def test_the_agentic_gate_is_declared_and_false_by_default(self):
        # `get_as_bool` cannot tell false from absent — it returns False for a missing key — so a
        # deleted, renamed or misplaced setting would pass. `get` returns None when absent.
        # Arrange
        path = f"{_SETTINGS_ROOT}/agentic_enabled"

        # Act
        value = carb.settings.get_settings().get(path)

        # Assert
        self.assertIs(value, False, f"{path} must be declared and default to false")


class TestRoutesPackage(omni.kit.test.AsyncTestCase):
    """Cover the `routes/` package tree and the registry `TrexCoreServiceExtension` reads."""

    async def test_every_routes_package_imports(self):
        # Nothing else imports the nested packages, so without this a syntax error or a bad
        # license header anywhere under `routes/` ships undetected.
        # Arrange
        names = [
            name
            for _, name, _ in pkgutil.walk_packages(_routes_package.__path__, prefix=f"{_routes_package.__name__}.")
        ]

        # Act
        imported = [importlib.import_module(name) for name in names]

        # Assert
        self.assertEqual(len(imported), len(names))
        self.assertIn(f"{_routes_package.__name__}.stagecraft.assets.data_models", names)

    async def test_route_services_are_registrable(self):
        # A class the service factory cannot key by name would fail silently at registration,
        # so every entry in ROUTE_SERVICES is checked for the attribute the factory reads.
        for service in ROUTE_SERVICES:
            with self.subTest(title=f"service={service.__name__}"):
                # Arrange / Act
                name = getattr(service, "name", None)

                # Assert
                self.assertTrue(issubclass(service, ServiceBase), f"{service!r} is not a ServiceBase")
                self.assertEqual(name, service.__name__)
