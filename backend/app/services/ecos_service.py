from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from ..models import DataStatus
from ..repository import Repository
from ..utils import utc_now
from .data_service import DataService


ECOS_BASE_URL = "https://ecos.bok.or.kr/api"
SERIES = {
    "exchange_rate": {
        "stat_code": "731Y004",
        "item_path": "0000001/0000100",
    },
    "base_rate": {"stat_code": "722Y001", "item_path": "0101000"},
    "cpi": {"stat_code": "901Y009", "item_path": "0"},
}


class EcosSyncService:
    def __init__(self, repository: Repository, api_key: str) -> None:
        self.repository = repository
        self.api_key = api_key
        self._lock = threading.Lock()

    def status(self) -> dict:
        return self.repository.get_meta("sync") or {
            "status": "not_started",
            "last_attempt_at": None,
            "last_success_at": None,
            "added": 0,
            "updated": 0,
        }

    def should_sync(self) -> bool:
        status = self.status()
        last_success = status.get("last_success_at")
        if not last_success:
            return True
        try:
            timestamp = datetime.fromisoformat(last_success)
        except ValueError:
            return True
        return datetime.now(timezone.utc) - timestamp >= timedelta(hours=24)

    @staticmethod
    def _subtract_months(period: str, months: int) -> str:
        year = int(period[:4])
        month = int(period[5:7])
        absolute = year * 12 + month - 1 - months
        return f"{absolute // 12:04d}{absolute % 12 + 1:02d}"

    def _fetch(self, indicator: str, start: str, end: str) -> list[dict[str, Any]]:
        spec = SERIES[indicator]
        page_size = 10 if self.api_key.lower() == "sample" else 1_000
        rows: list[dict[str, Any]] = []
        start_row = 1
        total: int | None = None
        session = requests.Session()
        while total is None or start_row <= total:
            end_row = start_row + page_size - 1
            url = (
                f"{ECOS_BASE_URL}/StatisticSearch/{self.api_key}/json/kr/"
                f"{start_row}/{end_row}/{spec['stat_code']}/M/{start}/{end}/"
                f"{spec['item_path']}/"
            )
            response = session.get(url, timeout=20)
            response.raise_for_status()
            payload = response.json()
            if "RESULT" in payload:
                result = payload["RESULT"]
                raise RuntimeError(
                    f"ECOS {result.get('CODE', 'error')}: "
                    f"{result.get('MESSAGE', 'unknown error')}"
                )
            search = payload.get("StatisticSearch")
            if not search:
                raise RuntimeError(f"ECOS response is missing StatisticSearch for {indicator}")
            total = int(search.get("list_total_count", 0))
            page = search.get("row", [])
            rows.extend(page)
            if not page:
                break
            start_row += len(page)
        return rows

    def sync(self, *, force: bool = False) -> dict:
        if not self.api_key:
            result = {
                **self.status(),
                "status": "skipped",
                "last_attempt_at": utc_now(),
                "message": "ECOS_API_KEY가 없어 저장된 데이터를 사용합니다.",
            }
            self.repository.set_meta("sync", result)
            return result
        if not force and not self.should_sync():
            return {**self.status(), "status": "fresh"}
        if not self._lock.acquire(blocking=False):
            return {**self.status(), "status": "running"}

        started = utc_now()
        current = datetime.now(timezone.utc)
        end = current.strftime("%Y%m")
        official = [
            record
            for record in self.repository.list_data()
            if record.get("source") == "ecos"
        ]
        latest = max((record["date"] for record in official), default="2015-01")
        start = self._subtract_months(latest, 3)
        added = 0
        updated = 0
        try:
            for indicator in SERIES:
                for row in self._fetch(indicator, start, end):
                    raw_date = str(row.get("TIME", ""))
                    raw_value = str(row.get("DATA_VALUE", "")).replace(",", "")
                    if len(raw_date) != 6 or not raw_value:
                        continue
                    date = f"{raw_date[:4]}-{raw_date[4:]}"
                    value = float(raw_value)
                    record_id = DataService.official_id(indicator, date)
                    existing = self.repository.get_data(record_id)
                    if existing:
                        existing["original_value"] = value
                        if existing["status"] == DataStatus.official.value:
                            existing["value"] = value
                        existing["updated_at"] = utc_now()
                        self.repository.set_data(record_id, existing)
                        updated += 1
                    else:
                        now = utc_now()
                        self.repository.set_data(
                            record_id,
                            {
                                "id": record_id,
                                "date": date,
                                "indicator": indicator,
                                "value": value,
                                "memo": "한국은행 ECOS 자동 갱신 데이터",
                                "source": "ecos",
                                "status": DataStatus.official.value,
                                "original_value": value,
                                "created_at": now,
                                "updated_at": now,
                                "deleted_from_status": None,
                            },
                        )
                        added += 1
            result = {
                "status": "success",
                "last_attempt_at": started,
                "last_success_at": utc_now(),
                "added": added,
                "updated": updated,
                "message": f"새 데이터 {added}개, 갱신 데이터 {updated}개를 확인했습니다.",
            }
            self.repository.set_meta("sync", result)
            return result
        except Exception as exc:
            previous = self.status()
            result = {
                **previous,
                "status": "failed",
                "last_attempt_at": started,
                "added": 0,
                "updated": 0,
                "message": f"최신 데이터 확인에 실패했습니다: {exc}",
            }
            self.repository.set_meta("sync", result)
            return result
        finally:
            self._lock.release()
