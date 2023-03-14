import tempfile
from pathlib import Path

import omni.kit.test
from lightspeed.trex.project_wizard.existing_mods_page.widget.selection_tree.items import ModSelectionItem


class TestSelectionTreeItems(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_path_returns_path(self):
        # Arrange
        mod_dir = "ModDir"
        mod_file = "mod_file.usda"
        path = Path(self.temp_dir.name) / mod_dir / mod_file

        item = ModSelectionItem(path)

        # Act
        pass

        # Assert
        self.assertEqual(path, item.path)

    async def test_title_returns_parent_folder_and_mod_name_string(self):
        # Arrange
        mod_dir = "ModDir"
        mod_file = "mod_file.usda"
        path = Path(self.temp_dir.name) / mod_dir / mod_file

        item = ModSelectionItem(path)

        # Act
        pass

        # Assert
        self.assertEqual(str(Path(mod_dir) / mod_file), item.title)

    async def test_repr_returns_path_string(self):
        # Arrange
        mod_dir = "ModDir"
        mod_file = "mod_file.usda"
        path = Path(self.temp_dir.name) / mod_dir / mod_file

        item = ModSelectionItem(path)

        # Act
        pass

        # Assert
        self.assertEqual(str(path), str(item))
