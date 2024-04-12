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
from lightspeed.common.constants import INGESTION_SCHEMA_PATHS as _INGESTION_SCHEMA_PATHS
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared.mass_ingestion import SetupUI as _IngestionLayout


class SetupUI(_IngestionLayout):
    def __init__(self, ext_id):
        super().__init__(ext_id, _INGESTION_SCHEMA_PATHS, context=TrexContexts.INGEST_CRAFT)

    @property
    def button_name(self) -> str:
        return "Ingestion"

    @property
    def button_priority(self) -> int:
        return 15
