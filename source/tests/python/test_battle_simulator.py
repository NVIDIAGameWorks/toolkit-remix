"""
Import IBattleSimulator bindings and plugin directly and test them.
"""

import unittest
import os

import carb
import carb.events
import carb.dictionary

import omni.kit.extensions

from omni.example.mixed_extension.bindings import _battle_simulator


class TestBattleSimulator(unittest.TestCase):
    def setUp(self):
        search_path = os.environ["CARB_APP_PATH"].replace("\\", "/")
        carb.get_framework().load_plugins(["carb.events.plugin", "carb.dictionary.plugin"], search_paths=[f"{search_path}/plugins"])

        ext_folder = os.path.normpath(os.path.dirname(os.path.abspath(omni.example.mixed_extension.__file__)))
        lib_path = omni.kit.extensions.build_plugin_path(ext_folder, "example.battle_simulator.plugin", config="debug")
        self._battle_simulator = _battle_simulator.acquire_battle_simulator_interface(library_path=lib_path)

    def test_create_warrior(self):
        w = self._battle_simulator.create_warrior(hp=100, damage=1)
        warriors = self._battle_simulator.get_warriors()
        self.assertEqual(len(warriors), 1)
        self.assertEqual(warriors[0], w)
        self.assertEqual(self._battle_simulator.get_warrior_hp(w), 100)
        self._battle_simulator.destroy_warrior(w)

    def test_events(self):
        w1 = self._battle_simulator.create_warrior(hp=100, damage=50)
        w2 = self._battle_simulator.create_warrior(hp=10, damage=10)

        dead = 0

        def on_die(e):
            nonlocal dead
            self.assertEqual(e.type, int(_battle_simulator.WarriorEventType.DIE))
            dead = dead + 1
            
        sub_holder = self._battle_simulator.get_warrior_event_stream().subscribe_to_pop(_battle_simulator.WarriorEventType.DIE, on_die)

        self.assertEqual(dead, 0)
        self._battle_simulator.fight(w1, w2)
        self.assertEqual(dead, 1)
        self._battle_simulator.destroy_warrior(w1)
        self._battle_simulator.destroy_warrior(w2)