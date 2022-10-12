"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
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
