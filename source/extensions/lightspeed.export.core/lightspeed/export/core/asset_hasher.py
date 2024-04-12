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
import hashlib
import os
import pickle
from pathlib import Path
from threading import Lock

import carb


class LightspeedAssetHasher:
    def __init__(self, manifest_path: str):
        self._manifest_path = Path(manifest_path)
        try:
            with open(self._manifest_path, "rb") as manifest_file:
                self._old_hashes = pickle.load(manifest_file)
        except FileNotFoundError:
            carb.log_warn(f"LightspeedAssetHasher couldn't find {manifest_path}.  All assets will be re-processed.")
            self._old_hashes = {}
        except pickle.UnpicklingError:
            carb.log_error(f"Error parsing asset manifest file at {manifest_path}.  All assets will be re-processed.")
            self._old_hashes = {}
        self._new_hashes = {}
        self._mutex = Lock()

    def _hash_asset(self, relative_path: str, abs_source_path: str) -> str:
        new_hash = self._new_hashes.get(relative_path, None)
        if new_hash is None:
            # first time seeing this asset this session, hash the file
            try:
                with open(abs_source_path, "rb") as asset_file:
                    data = asset_file.read()
                    new_hash = hashlib.md5(data).hexdigest()
                    self._new_hashes[relative_path] = new_hash
            except FileNotFoundError:
                carb.log_error(f"Error opening asset file for hashing: {abs_source_path}.")
        return new_hash

    def should_process_asset(self, abs_source_path: str) -> bool:
        relative_path = os.path.relpath(abs_source_path, start=self._manifest_path)
        with self._mutex:
            new_hash = self._hash_asset(relative_path, abs_source_path)
            if new_hash is None:
                return False

            old_hash = self._old_hashes.get(relative_path, None)

        if old_hash is None:
            # previous hash for this file doesn't exist, so it needs processing
            return True

        return new_hash != old_hash

    def update_asset_hash(self, abs_source_path: str):
        relative_path = os.path.relpath(abs_source_path, start=self._manifest_path)
        with self._mutex:
            new_hash = self._hash_asset(relative_path, abs_source_path)
            self._old_hashes[relative_path] = new_hash

    def save_manifest(self):
        with open(self._manifest_path, "wb") as manifest_file:
            pickle.dump(self._old_hashes, manifest_file)
