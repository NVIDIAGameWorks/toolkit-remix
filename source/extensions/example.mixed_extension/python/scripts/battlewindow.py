import omni.kit.ui


class BattleWindow:
    """
    Window to show battles!
    """
    def _on_fight(self):
        winner, log = self._battleapi.fight(hp1=self._hp1.value, hp2=self._hp2.value, damage1=self._damage1.value, damage2=self._damage2.value)
        print(log)
        self._text.text = f"Winner: {winner}\n{log}"


    def __init__(self, battleapi):
        self._window = omni.kit.ui.Window("Battle Window", 300, 150)
        self._battleapi = battleapi
        layout = self._window.layout

        self._hp1 = layout.add_child(omni.kit.ui.DragInt("Hp1", 100))
        self._damage1 = layout.add_child(omni.kit.ui.DragInt("Damage1", 2))
        self._hp2 = layout.add_child(omni.kit.ui.DragInt("Hp2", 30))
        self._damage2 = layout.add_child(omni.kit.ui.DragInt("Damage2", 28))

        self._button = layout.add_child(omni.kit.ui.Button("Fight"))
        self._button.set_clicked_fn(lambda *_: self._on_fight())

        self._text = layout.add_child(omni.kit.ui.Label(""))



    def on_shutdown(self):
        self.__dict__.clear()
