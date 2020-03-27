import os

import omni.ext

from .battle import Battle
from .battlewindow import BattleWindow

# Put object publicly to make it our API.
battleapi = None

# Enable test for discovery: put them in extension's namespace
from .test_fight import *


class Extension(omni.ext.IExt):
    def __init__(self):
        global battleapi
        battleapi = Battle()
        self._battlewindow = BattleWindow(battleapi)

    def on_shutdown(self):
        global battleapi
        battleapi.on_shutdown()
        battleapi = None
        self._battlewindow.on_shutdown()
