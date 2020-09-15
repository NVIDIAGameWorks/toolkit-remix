import omni.ext
from .._example_battle_simulator import *

# Put interface object publicly to use in our API.
_battle_simulator = None


# public API
def fight(hp1: int, hp2: int, damage1: int, damage2: int):
    """Fight 2 warriors. Return tuple of 2: fight log and winner number"""
    w1 = _battle_simulator.create_warrior(hp=hp1, damage=damage1)
    w2 = _battle_simulator.create_warrior(hp=hp2, damage=damage2)

    log = ""
    winner = 0
    while True:
        hp1 = _battle_simulator.get_warrior_hp(w1)
        hp2 = _battle_simulator.get_warrior_hp(w2)
        log += f"Hp1: {hp1} Hp2: {hp2}\n"
        if hp1 <= 0:
            winner = 2
            break
        if hp2 <= 0:
            winner = 1
            break
        _battle_simulator.fight(w1, w2)

    _battle_simulator.destroy_warrior(w1)
    _battle_simulator.destroy_warrior(w2)

    return winner, log


def get_battle_interface() -> IBattleSimulator:
    return _battle_simulator


# Use extension entry points to acquire and release interface.
class Extension(omni.ext.IExt):
    def __init__(self):
        global _battle_simulator
        _battle_simulator = acquire_battle_simulator_interface()
        print(f"[example.battle_simulator] _battle_simulator interface: {_battle_simulator}")

    def on_shutdown(self):
        global _battle_simulator
        release_battle_simulator_interface(_battle_simulator)
        _battle_simulator = None
