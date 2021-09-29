import omni.kit.test
import omni.kit.app
import example.battle_simulator

import carb
import carb.events
import carb.dictionary


class TestBattle(omni.kit.test.AsyncTestCaseFailOnLogError):
    async def setUp(self):
        self._iface = example.battle_simulator.get_battle_interface()

    async def test_fight(self):
        winner, _ = example.battle_simulator.fight(10, 20, 5, 1)
        self.assertEqual(winner, 1)

    async def test_pip_prebundle(self):
        import watchdog

        self.assertIsNotNone(watchdog)

    def test_create_warrior(self):
        w = self._iface.create_warrior(hp=100, damage=1)
        warriors = self._iface.get_warriors()
        self.assertEqual(len(warriors), 1)
        self.assertEqual(warriors[0], w)
        self.assertEqual(self._iface.get_warrior_hp(w), 100)
        self._iface.destroy_warrior(w)

    def test_events(self):
        w1 = self._iface.create_warrior(hp=100, damage=50)
        w2 = self._iface.create_warrior(hp=10, damage=10)

        dead = 0

        def on_die(e):
            nonlocal dead
            self.assertEqual(e.type, int(example.battle_simulator.WarriorEventType.DIE))
            dead = dead + 1

        sub_holder = self._iface.get_warrior_event_stream().create_subscription_to_pop_by_type(
            example.battle_simulator.WarriorEventType.DIE, on_die
        )

        self.assertEqual(dead, 0)
        self._iface.fight(w1, w2)
        self.assertEqual(dead, 1)
        self._iface.destroy_warrior(w1)
        self._iface.destroy_warrior(w2)
