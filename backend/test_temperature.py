import unittest

from app.services.temperature import TemperatureService


class TemperatureServiceTest(unittest.TestCase):
    def setUp(self):
        from app.store import store

        for name in list(store._tables):
            store._tables[name] = []
        seed = [
            {
                "id": 1,
                "记录编号": "TEMP-0001",
                "关联运单": "WB-001",
                "测点编号": "POINT-001",
                "在线状态": True,
                "实时温度": 4.5,
                "温度上限": 8.0,
                "温度下限": 2.0,
                "采集时间": "2026-09-24T08:00:00",
            },
            {
                "id": 2,
                "记录编号": "TEMP-0002",
                "关联运单": "WB-002",
                "测点编号": "POINT-002",
                "在线状态": False,
                "实时温度": 5.1,
                "温度上限": 8.0,
                "温度下限": 2.0,
                "采集时间": "2026-09-24T07:30:00",
            },
        ]
        store._tables["temperature"] = seed
        self.service = TemperatureService()

    def test_list_and_detail_share_same_reading_contract(self):
        listed = self.service.list_entries()[0][0]
        detail = self.service.get_entry(1)

        self.assertEqual(listed, detail)
        self.assertEqual(detail["温度上限"], 8.0)
        self.assertEqual(detail["温度下限"], 2.0)

    def test_recollect_writes_new_value_and_time_before_reading(self):
        entry, _ = self.service.run_action(
            1,
            "重新采集",
            {"实时温度": 6.2, "采集时间": "2026-09-24T09:05:00"},
        )

        self.assertEqual(entry["实时温度"], 6.2)
        self.assertEqual(entry["采集时间"], "2026-09-24T09:05:00")
        self.assertEqual(self.service.get_entry(1), entry)

    def test_failed_read_keeps_last_successful_result(self):
        before = self.service.get_entry(1)
        entry, _ = self.service.run_action(1, "重新采集", {"read_failed": True})

        self.assertEqual(entry["实时温度"], before["实时温度"])
        self.assertEqual(entry["采集时间"], before["采集时间"])
        self.assertTrue(entry["在线状态"])

    def test_offline_point_becomes_online_after_successful_recollect(self):
        entry, _ = self.service.run_action(2, "重新采集", {"实时温度": 4.8})

        self.assertEqual(entry["status"], "正常")
        self.assertTrue(entry["在线状态"])
        self.assertIsNotNone(entry["采集时间"])
        normal_items, _ = self.service.list_entries(status="正常")
        self.assertEqual([item["id"] for item in normal_items], [1, 2])


if __name__ == "__main__":
    unittest.main()
