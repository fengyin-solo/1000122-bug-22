"""温控监控业务规则：采集结果写回、状态流转与读取口径统一收在这里。"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Callable

from app.store import store

MODULE = "temperature"
REQUIRED_FIELDS = ["记录编号", "关联运单", "测点编号"]
READ_FIELDS = ["记录编号", "关联运单", "测点编号", "实时温度", "温度上限", "温度下限", "采集时间"]
STATUS_ORDER = ["正常", "偏高", "偏低", "已离线"]
ABNORMAL_STATUSES = {"偏高", "偏低"}
MANUAL_ACTIONS = {"确认记录": "正常", "标记超限": "偏高"}
DEFAULT_UPPER_LIMIT = 8.0
DEFAULT_LOWER_LIMIT = 2.0

SAMPLE_TEMPERATURES = {
    "POINT-001": 4.8,
    "POINT-002": 8.9,
    "POINT-003": 4.2,
    "POINT-004": 5.4,
}


class CollectionError(RuntimeError):
    """采集设备读取失败；调用方应保留上一次成功写回的数据。"""


def _mock_read_temperature(point_id: str) -> float:
    """演示环境的稳定读数。接真实网关时在这里替换为设备适配器即可。"""
    return SAMPLE_TEMPERATURES.get(point_id, 5.0)


# 可在测试或真实部署中替换，避免业务代码直接依赖某一种设备网关。
temperature_reader: Callable[[str], float] = _mock_read_temperature


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _is_online(entry: dict[str, Any]) -> bool:
    if "在线" in entry:
        return bool(entry["在线"])
    return entry.get("status") != "已离线"


def _status_from_temperature(temperature: float | None, upper: float | None, lower: float | None) -> str:
    if temperature is None:
        return "已离线"
    if upper is not None and temperature > upper:
        return "偏高"
    if lower is not None and temperature < lower:
        return "偏低"
    return "正常"


def serialize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """列表、详情、动作响应和导出共用的唯一读取口径。"""
    online = _is_online(entry)
    temperature = _to_float(entry.get("实时温度"))
    upper = _to_float(entry.get("温度上限"))
    lower = _to_float(entry.get("温度下限"))

    if online:
        status = entry.get("status")
        if status not in STATUS_ORDER or status == "已离线":
            status = _status_from_temperature(temperature, upper, lower)
    else:
        status = "已离线"

    result: dict[str, Any] = {
        "id": int(entry.get("id", 0)),
        "status": status,
        "在线": online,
        "pending": status != "已离线",
        "abnormal": status in ABNORMAL_STATUSES,
    }
    for field in READ_FIELDS[:3]:
        result[field] = entry.get(field)
    result["实时温度"] = temperature
    result["温度上限"] = upper
    result["温度下限"] = lower
    result["采集时间"] = entry.get("采集时间")
    result["上次成功采集时间"] = entry.get("上次成功采集时间", entry.get("采集时间"))
    return result


class TemperatureService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [serialize_entry(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return serialize_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = "正常"
        entry["在线"] = False
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return serialize_entry(entry), []

    def collect_entry(
        self,
        entry_id: int,
        values: dict[str, Any] | None = None,
        *,
        read_time: datetime | None = None,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        """执行一次采集；只有完整读数校验通过后才整体写回，失败时原样保留快照。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, False, f"温控记录 {entry_id} 不存在或已归档"

        values = values or {}
        if values.get("模拟读取失败") or values.get("读取失败"):
            return serialize_entry(entry), False, "采集读取失败，已保留上一次成功结果"

        point_id = str(entry.get("测点编号") or "").strip()
        if not point_id:
            return serialize_entry(entry), False, "测点编号缺失，无法采集"

        upper = _to_float(values.get("温度上限", entry.get("温度上限")))
        lower = _to_float(values.get("温度下限", entry.get("温度下限")))
        if upper is None:
            upper = DEFAULT_UPPER_LIMIT
        if lower is None:
            lower = DEFAULT_LOWER_LIMIT
        if lower >= upper:
            return serialize_entry(entry), False, "温度下限必须小于上限，本次采集结果未写回"

        try:
            if "实时温度" in values and values.get("实时温度") not in (None, ""):
                temperature = _to_float(values.get("实时温度"))
                if temperature is None:
                    raise ValueError("实时温度不是有效数字")
            else:
                temperature = float(temperature_reader(point_id))
        except Exception as exc:
            # 单次读取失败不等于测点离线：只返回并保留最近一次成功快照。
            return serialize_entry(entry), False, f"采集读取失败：{exc}，已保留上一次成功结果"

        collected_at = str(values.get("采集时间") or (read_time or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"))
        status = _status_from_temperature(temperature, upper, lower)

        # 完整快照一次性写回，避免刷新或返回列表时读到半更新数据。
        entry["实时温度"] = temperature
        entry["温度上限"] = upper
        entry["温度下限"] = lower
        entry["采集时间"] = collected_at
        entry["上次成功采集时间"] = collected_at
        entry["status"] = status
        entry["在线"] = True
        entry["pending"] = True
        entry["abnormal"] = status in ABNORMAL_STATUSES
        return serialize_entry(entry), True, "温控记录已重新采集"

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, False, f"温控记录 {entry_id} 不存在或已归档"

        if action == "重新采集":
            return self.collect_entry(entry_id, values)

        if action not in MANUAL_ACTIONS:
            return None, False, f"动作「{action}」不属于温控监控可执行范围"

        target = MANUAL_ACTIONS[action]
        entry["status"] = target
        entry["在线"] = True
        entry["pending"] = target != "已离线"
        entry["abnormal"] = target in ABNORMAL_STATUSES
        return serialize_entry(entry), True, f"温控记录已{action}"
