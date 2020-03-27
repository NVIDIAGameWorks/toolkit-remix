import os
from .. import _battle_simulator


class Battle:
    def __init__(self):
        self._battle_simulator = _battle_simulator.acquire_battle_simulator_interface()

    def fight(self, hp1: int, hp2: int, damage1: int, damage2: int):
        """Fight 2 warriors. Return tuple of 2: fight log and winner number"""
        w1 = self._battle_simulator.create_warrior(hp=hp1, damage=damage1)
        w2 = self._battle_simulator.create_warrior(hp=hp2, damage=damage2)

        log = ""
        winner = 0
        while True:
            hp1 = self._battle_simulator.get_warrior_hp(w1)
            hp2 = self._battle_simulator.get_warrior_hp(w2)
            log += f"Hp1: {hp1} Hp2: {hp2}\n"
            if hp1 <= 0:
                winner = 2
                break
            if hp2 <= 0:
                winner = 1
                break
            self._battle_simulator.fight(w1, w2)

        self._battle_simulator.destroy_warrior(w1)
        self._battle_simulator.destroy_warrior(w2)

        return winner, log

    def on_shutdown(self):
        _battle_simulator.release_battle_simulator_interface(self._battle_simulator)
