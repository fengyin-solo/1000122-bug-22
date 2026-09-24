"""温控监控业务规则：状态流转、字段校验与采集结果读写口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "temperature"
REQUIRED_FIELDS = ["记录编号", "关联运单", "测点编号"]
STATUS_ORDER = ["正常", "偏高", "偏低", "已离线"]
ACTION_RULES = {"确认记录", "标记超限", "重新采集"}
NEGATIVE_ACTIONS = []

TEMPERATURE_FIELD = "实时温度"
UPPER_LIMIT_FIELD = "温度上限"
LOWER_LIMIT_FIELD = "温度下限"
COLLECTED_AT_FIELD = "采集时间"
ONLINE_FIELD = "在线状态"
MANUAL_STATUS_FIELD = "状态覆盖"

_ALIASES = {
    "temperature": TEMPERATURE_FIELD,
    "value": TEMPERATURE_FIELD,
    "current": TEMPERATURE_FIELD,
    "实时温度": TEMPERATURE_FIELD,
    "upper": UPPER_LIMIT_FIELD,
    "upper_limit": UPPER_LIMIT_FIELD,
    "温度上限": UPPER_LIMIT_FIELD,
    "lower": LOWER_LIMIT_FIELD,
    "lower_limit": LOWER_LIMIT_FIELD,
    "温度下限": LOWER_LIMIT_FIELD,
    "collected_at": COLLECTED_AT_FIELD,
    "timestamp": COLLECTED_AT_FIELD,
    "采集时间": COLLECTED_AT_FIELD,
    "online": ONLINE_FIELD,
    "is_online": ONLINE_FIELD,
    "在线状态": ONLINE_FIELD,
}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_limits(values: dict[str, Any]) -> tuple[float, float]:
    upper = _as_float(values.get(UPPER_LIMIT_FIELD))
    lower = _as_float(values.get(LOWER_LIMIT_FIELD))
    if upper is None:
        upper = 8.0
    if lower is None:
        lower = 2.0
    if lower > upper:
        lower, upper = upper, lower
    return upper, lower


def _is_online(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "offline", "no", "否", "离线"}


def _status_for(
    temperature: float | None,
    upper: float,
    lower: float,
    online: bool,
    manual_status: str | None = None,
) -> str:
    if not online:
        return "已离线"
    if manual_status in {"偏高", "偏低"}:
        return manual_status
    if temperature is None:
        return "已离线"
    if temperature > upper:
        return "偏高"
    if temperature < lower:
        return "偏低"
    return "正常"


class TemperatureService:
    """列表和详情共用 _serialize_entry，确保所有页面读取同一份采集结果。"""

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if status:
            rows = [row for row in rows if self._serialize_entry(row)["status"] == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._serialize_entry(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._serialize_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry[ONLINE_FIELD] = False
        entry[TEMPERATURE_FIELD] = None
        entry[UPPER_LIMIT_FIELD], entry[LOWER_LIMIT_FIELD] = _normalize_limits(values)
        entry[COLLECTED_AT_FIELD] = None
        self._apply_reading(entry, temperature=None, online=False)
        rows.append(entry)
        return self._serialize_entry(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"温控记录 {entry_id} 不存在或已归档"
        action = action.strip()
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于温控监控可执行范围"

        values = values or {}
        if action == "重新采集":
            return self._recollect(entry, values)
        if action == "标记超限":
            return self._mark_excursion(entry, values)

        entry[MANUAL_STATUS_FIELD] = None
        self._refresh_status(entry)
        return self._serialize_entry(entry), "温控记录已确认记录"

    def _recollect(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        data = self._action_values(values)
        failure_flags = {
            str(data.get("read_failed", "")).strip().lower(),
            str(data.get("failed", "")).strip().lower(),
            str(data.get("读取失败", "")).strip().lower(),
            str(data.get("采集失败", "")).strip().lower(),
        }
        explicit_failure = bool(failure_flags & {"1", "true", "yes", "是", "失败"})
        success_flags = {
            str(data.get("success", "")).strip().lower(),
            str(data.get("ok", "")).strip().lower(),
            str(data.get("读取成功", "")).strip().lower(),
            str(data.get("采集成功", "")).strip().lower(),
        }
        explicit_unsuccessful = bool(success_flags & {"0", "false", "no", "否", "失败"})
        failed = explicit_failure or explicit_unsuccessful
        online = _is_online(data.get(ONLINE_FIELD, True))
        temperature = _as_float(data.get(TEMPERATURE_FIELD))

        # 读取失败时保留上一次成功结果，不能顺手把在线测点改成离线。
        if failed:
            self._refresh_status(entry)
            return self._serialize_entry(entry), "读取失败，已保留上一次成功的采集结果"

        # 设备仍离线时同样只保留上一次成功的温度与采集时间。
        if not online:
            entry[ONLINE_FIELD] = False
            self._refresh_status(entry)
            return self._serialize_entry(entry), "测点仍处于离线状态"

        if temperature is None:
            temperature = self._sample_temperature(entry)

        entry[ONLINE_FIELD] = True
        entry[MANUAL_STATUS_FIELD] = None
        entry[TEMPERATURE_FIELD] = temperature
        entry[UPPER_LIMIT_FIELD], entry[LOWER_LIMIT_FIELD] = _normalize_limits(
            {
                UPPER_LIMIT_FIELD: data.get(UPPER_LIMIT_FIELD, entry.get(UPPER_LIMIT_FIELD)),
                LOWER_LIMIT_FIELD: data.get(LOWER_LIMIT_FIELD, entry.get(LOWER_LIMIT_FIELD)),
            }
        )
        entry[COLLECTED_AT_FIELD] = self._reading_time(data)
        self._apply_reading(entry, temperature=temperature, online=True)
        return self._serialize_entry(entry), "温控记录已重新采集"

    def _mark_excursion(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        data = self._action_values(values)
        if UPPER_LIMIT_FIELD in data or LOWER_LIMIT_FIELD in data:
            entry[UPPER_LIMIT_FIELD], entry[LOWER_LIMIT_FIELD] = _normalize_limits(
                {
                    UPPER_LIMIT_FIELD: data.get(UPPER_LIMIT_FIELD, entry.get(UPPER_LIMIT_FIELD)),
                    LOWER_LIMIT_FIELD: data.get(LOWER_LIMIT_FIELD, entry.get(LOWER_LIMIT_FIELD)),
                }
            )

        temperature = _as_float(data.get(TEMPERATURE_FIELD))
        if temperature is not None:
            entry[TEMPERATURE_FIELD] = temperature
            entry[COLLECTED_AT_FIELD] = self._reading_time(data)
            entry[ONLINE_FIELD] = _is_online(data.get(ONLINE_FIELD, True))

        target_status = str(data.get("target_status", data.get("异常方向", "偏高"))).strip()
        if target_status not in {"偏高", "偏低"}:
            target_status = "偏高"
        entry[MANUAL_STATUS_FIELD] = target_status
        self._refresh_status(entry)
        return self._serialize_entry(entry), "温控记录已标记超限"

    def _action_values(self, values: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in values.items():
            data[_ALIASES.get(str(key).strip().lower(), str(key).strip())] = value
        return data

    def _sample_temperature(self, entry: dict[str, Any]) -> float:
        upper, lower = _normalize_limits(entry)
        if upper == lower:
            return upper
        round_index = int(entry.get("采集轮次", 0))
        entry["采集轮次"] = round_index + 1
        span = max(round((upper - lower) * 10), 1)
        offset = ((int(entry["id"]) * 7 + round_index * 3) % span) / 10
        return round(lower + offset, 1)

    def _reading_time(self, data: dict[str, Any]) -> str:
        value = data.get(COLLECTED_AT_FIELD)
        if value is not None and str(value).strip():
            return str(value).strip()
        return datetime.now().replace(microsecond=0).isoformat()

    def _apply_reading(
        self,
        entry: dict[str, Any],
        *,
        temperature: float | None,
        online: bool,
        manual_status: str | None = None,
    ) -> None:
        upper, lower = _normalize_limits(entry)
        status = _status_for(temperature, upper, lower, online, manual_status)
        entry["status"] = status
        entry["pending"] = status in {"偏高", "偏低", "已离线"}
        entry["abnormal"] = status in {"偏高", "偏低"}

    def _refresh_status(self, entry: dict[str, Any]) -> None:
        upper, lower = _normalize_limits(entry)
        entry[UPPER_LIMIT_FIELD] = upper
        entry[LOWER_LIMIT_FIELD] = lower
        online = bool(entry.get(ONLINE_FIELD, False))
        temperature = _as_float(entry.get(TEMPERATURE_FIELD))
        manual_status = entry.get(MANUAL_STATUS_FIELD)
        self._apply_reading(
            entry,
            temperature=temperature,
            online=online,
            manual_status=manual_status if manual_status in {"偏高", "偏低"} else None,
        )

    def _serialize_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        upper, lower = _normalize_limits(entry)
        online = bool(entry.get(ONLINE_FIELD, False))
        temperature = _as_float(entry.get(TEMPERATURE_FIELD))
        collected_at = entry.get(COLLECTED_AT_FIELD)
        manual_status = entry.get(MANUAL_STATUS_FIELD)
        item = {
            "id": int(entry.get("id", 0)),
            "记录编号": entry.get("记录编号"),
            "关联运单": entry.get("关联运单"),
            "测点编号": entry.get("测点编号"),
            TEMPERATURE_FIELD: temperature,
            UPPER_LIMIT_FIELD: upper,
            LOWER_LIMIT_FIELD: lower,
            COLLECTED_AT_FIELD: collected_at,
            ONLINE_FIELD: online,
            "status": _status_for(
                temperature,
                upper,
                lower,
                online,
                manual_status if manual_status in {"偏高", "偏低"} else None,
            ),
        }
        return item
