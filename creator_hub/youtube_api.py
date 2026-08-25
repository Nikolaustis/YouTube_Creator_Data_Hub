from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .db import connect
from .util import now_utc, today_utc


class YouTubeAPIError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status = status
        self.reason = reason


class QuotaBudgetExceeded(RuntimeError):
    pass


@dataclass
class APIUsage:
    units: int = 0
    calls: int = 0


def read_api_key(env_name: str) -> str:
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    # On Windows, a key saved to the current-user Environment registry can be read
    # immediately even if the parent Codex process was launched before the variable was set.
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                value, _ = winreg.QueryValueEx(key, env_name)
                return str(value).strip()
        except Exception:
            pass
    return ""


class YouTubeAPI:
    def __init__(self, db_path: str, settings: dict[str, Any], unit_budget: int | None = None):
        api_cfg = settings["api"]
        env_name = api_cfg.get("api_key_env", "YOUTUBE_API_KEY")
        self.api_key = read_api_key(env_name)
        if not self.api_key:
            raise YouTubeAPIError(f"缺少环境变量 {env_name}。请先配置 YouTube Data API Key。")
        self.db_path = db_path
        self.base_url = api_cfg.get("base_url", "https://www.googleapis.com/youtube/v3").rstrip("/")
        self.timeout = int(api_cfg.get("timeout_seconds", 30))
        self.retries = int(api_cfg.get("retries", 4))
        self.costs = dict(api_cfg.get("estimated_costs", {}))
        self.soft_limit = int(api_cfg.get("daily_quota_soft_limit", 9500))
        self.unit_budget = unit_budget
        self.usage = APIUsage()

    def _record_units(self, units: int) -> None:
        if self.unit_budget is not None and self.usage.units + units > self.unit_budget:
            raise QuotaBudgetExceeded(f"本次运行的 unit budget={self.unit_budget} 已达到。")
        with connect(self.db_path) as conn:
            day = today_utc()
            row = conn.execute("SELECT estimated_units FROM quota_daily WHERE quota_date=?", (day,)).fetchone()
            current = int(row[0]) if row else 0
            if current + units > self.soft_limit:
                raise QuotaBudgetExceeded(
                    f"今日估算 quota 将超过软上限 {self.soft_limit}（当前 {current}，本次调用预计 {units}）。"
                )
            conn.execute(
                "INSERT INTO quota_daily(quota_date, estimated_units, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(quota_date) DO UPDATE SET estimated_units=estimated_units+excluded.estimated_units, updated_at=excluded.updated_at",
                (day, units, now_utc()),
            )
            conn.commit()
        self.usage.units += units
        self.usage.calls += 1

    def call(self, endpoint: str, **params: Any) -> dict[str, Any]:
        units = int(self.costs.get(endpoint, 1))
        self._record_units(units)
        query = {k: v for k, v in params.items() if v is not None and v != ""}
        query["key"] = self.api_key
        url = f"{self.base_url}/{endpoint}?" + urllib.parse.urlencode(query, doseq=True)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, headers={"User-Agent": "youtube-creator-data-hub/3.10.3"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                reason = None
                message = body
                try:
                    obj = json.loads(body)
                    err = obj.get("error", {})
                    message = err.get("message", body)
                    reasons = err.get("errors", [])
                    if reasons:
                        reason = reasons[0].get("reason")
                except Exception:
                    pass
                if e.code in {403, 429} and reason in {"quotaExceeded", "dailyLimitExceeded"}:
                    raise YouTubeAPIError(message, status=e.code, reason=reason)
                if e.code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(min(8.0, (2 ** attempt) + random.random()))
                    last_error = e
                    continue
                raise YouTubeAPIError(message, status=e.code, reason=reason)
            except (urllib.error.URLError, TimeoutError) as e:
                last_error = e
                if attempt < self.retries:
                    time.sleep(min(8.0, (2 ** attempt) + random.random()))
                    continue
                break
        raise YouTubeAPIError(f"YouTube API 请求失败：{last_error}")
