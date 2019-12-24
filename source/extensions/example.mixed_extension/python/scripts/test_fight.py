import omni.kit.test


class TestFight(omni.kit.test.AsyncTestCaseFailOnLogError):
    async def test_fight(self):
        from .extension import battleapi

        winner, _ = battleapi.fight(10, 20, 5, 1)
        self.assertEqual(winner, 1)
