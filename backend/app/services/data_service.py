from __future__ import annotations

import csv
import io
import statistics
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException

from ..models import DataCreate, DataStatus, DataUpdate, Indicator
from ..repository import Repository
from ..utils import INDICATOR_META, utc_now


SEED_COLUMNS = {
    Indicator.exchange_rate: "exchange_rate",
    Indicator.base_rate: "base_rate",
    Indicator.cpi: "cpi",
}


class DataService:
    def __init__(self, repository: Repository, seed_csv: Path) -> None:
        self.repository = repository
        self.seed_csv = seed_csv

    @staticmethod
    def official_id(indicator: str, date: str) -> str:
        return f"{indicator}_{date}"

    def ensure_seed_data(self) -> int:
        if not self.seed_csv.exists():
            raise RuntimeError(f"Seed data not found: {self.seed_csv}")
        now = utc_now()
        created = 0
        with self.seed_csv.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                date = row["date"][:7]
                for indicator, column in SEED_COLUMNS.items():
                    if not row.get(column):
                        continue
                    record_id = self.official_id(indicator.value, date)
                    if self.repository.get_data(record_id):
                        continue
                    value = float(row[column])
                    record = {
                        "id": record_id,
                        "date": date,
                        "indicator": indicator.value,
                        "value": value,
                        "memo": "한국은행 ECOS 초기 데이터",
                        "source": "ecos",
                        "status": DataStatus.official.value,
                        "original_value": value,
                        "created_at": now,
                        "updated_at": now,
                        "deleted_from_status": None,
                    }
                    self.repository.set_data(record_id, record)
                    created += 1
        self.repository.set_meta(
            "seed",
            {
                "seeded_at": now,
                "seed_file": self.seed_csv.name,
                "created": created,
            },
        )
        return created

    def list_records(
        self,
        *,
        indicator: Indicator | None = None,
        start: str | None = None,
        end: str | None = None,
        include_deleted: bool = False,
        limit: int = 1_000,
    ) -> list[dict]:
        records = self.repository.list_data()
        result = []
        for record in records:
            if not include_deleted and record["status"] == DataStatus.deleted.value:
                continue
            if indicator and record["indicator"] != indicator.value:
                continue
            if start and record["date"] < start:
                continue
            if end and record["date"] > end:
                continue
            result.append(record)
        result.sort(key=lambda item: (item["date"], item["indicator"]), reverse=True)
        return result[:limit]

    def get_record(self, record_id: str) -> dict:
        record = self.repository.get_data(record_id)
        if not record:
            raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
        return record

    def create_record(self, payload: DataCreate) -> dict:
        active_duplicate = next(
            (
                record
                for record in self.repository.list_data()
                if record["date"] == payload.date
                and record["indicator"] == payload.indicator.value
                and record["status"] != DataStatus.deleted.value
            ),
            None,
        )
        if active_duplicate:
            raise HTTPException(
                status_code=409,
                detail="같은 월과 지표의 데이터가 이미 존재합니다.",
            )
        now = utc_now()
        record_id = f"user_{uuid.uuid4().hex}"
        record = {
            "id": record_id,
            "date": payload.date,
            "indicator": payload.indicator.value,
            "value": payload.value,
            "memo": payload.memo,
            "source": "user",
            "status": DataStatus.user.value,
            "original_value": payload.value,
            "created_at": now,
            "updated_at": now,
            "deleted_from_status": None,
        }
        self.repository.set_data(record_id, record)
        return record

    def update_record(self, record_id: str, payload: DataUpdate) -> dict:
        record = self.get_record(record_id)
        if record["status"] == DataStatus.deleted.value:
            raise HTTPException(status_code=409, detail="삭제된 데이터는 먼저 복원해주세요.")
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=422, detail="수정할 값을 입력해주세요.")
        if "value" in updates and updates["value"] is not None:
            record["value"] = updates["value"]
        if "memo" in updates and updates["memo"] is not None:
            record["memo"] = updates["memo"]
        if record["source"] == "ecos":
            record["status"] = DataStatus.modified.value
        record["updated_at"] = utc_now()
        self.repository.set_data(record_id, record)
        return record

    def soft_delete(self, record_id: str) -> dict:
        record = self.get_record(record_id)
        if record["status"] == DataStatus.deleted.value:
            return record
        record["deleted_from_status"] = record["status"]
        record["status"] = DataStatus.deleted.value
        record["updated_at"] = utc_now()
        self.repository.set_data(record_id, record)
        return record

    def restore_record(self, record_id: str) -> dict:
        record = self.get_record(record_id)
        if record["source"] == "ecos":
            record["value"] = record.get("original_value", record["value"])
            record["status"] = DataStatus.official.value
            record["memo"] = "한국은행 ECOS 원본 데이터"
        else:
            record["status"] = DataStatus.user.value
        record["deleted_from_status"] = None
        record["updated_at"] = utc_now()
        self.repository.set_data(record_id, record)
        return record

    def restore_all(self) -> dict:
        restored = 0
        for record in self.repository.list_data():
            if record["source"] == "ecos" and (
                record["status"] != DataStatus.official.value
                or record["value"] != record.get("original_value")
            ):
                self.restore_record(record["id"])
                restored += 1
            elif record["source"] == "user" and record["status"] == DataStatus.deleted.value:
                self.restore_record(record["id"])
                restored += 1
        return {"restored": restored, "restored_at": utc_now()}

    def active_records(self) -> list[dict]:
        return [
            record
            for record in self.repository.list_data()
            if record["status"] != DataStatus.deleted.value
        ]

    @staticmethod
    def _change(first: float, last: float, indicator: str) -> dict:
        absolute = last - first
        if indicator == Indicator.base_rate.value:
            percent = None
            threshold = 0.01
        else:
            percent = (absolute / first * 100) if first else None
            threshold = abs(first) * 0.001
        if absolute > threshold:
            direction = "상승"
        elif absolute < -threshold:
            direction = "하락"
        else:
            direction = "유지"
        return {"absolute": absolute, "percent": percent, "direction": direction}

    def summary(self) -> dict:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for record in self.active_records():
            grouped[record["indicator"]].append(record)

        indicators: dict[str, dict] = {}
        periods: list[str] = []
        for indicator in Indicator:
            records = sorted(grouped[indicator.value], key=lambda item: item["date"])
            if not records:
                indicators[indicator.value] = {
                    **INDICATOR_META[indicator.value],
                    "count": 0,
                    "latest": None,
                }
                continue
            periods.extend(record["date"] for record in records)
            values = [float(record["value"]) for record in records]
            latest = records[-1]
            previous_year = next(
                (
                    record
                    for record in records
                    if record["date"]
                    == f"{int(latest['date'][:4]) - 1:04d}-{latest['date'][5:7]}"
                ),
                None,
            )
            if previous_year:
                year_change = self._change(
                    float(previous_year["value"]), float(latest["value"]), indicator.value
                )
            else:
                year_change = None

            recent = records[-3:]
            recent_six = records[-6:]
            minimum = min(records, key=lambda item: float(item["value"]))
            maximum = max(records, key=lambda item: float(item["value"]))
            indicators[indicator.value] = {
                **INDICATOR_META[indicator.value],
                "count": len(records),
                "period": {"start": records[0]["date"], "end": latest["date"]},
                "latest": {"date": latest["date"], "value": latest["value"]},
                "average": statistics.fmean(values),
                "minimum": {"date": minimum["date"], "value": minimum["value"]},
                "maximum": {"date": maximum["date"], "value": maximum["value"]},
                "year_over_year": year_change,
                "recent_3": {
                    "start": recent[0]["date"],
                    "end": recent[-1]["date"],
                    "change": self._change(
                        float(recent[0]["value"]),
                        float(recent[-1]["value"]),
                        indicator.value,
                    ),
                    "values": [
                        {"date": row["date"], "value": row["value"]} for row in recent
                    ],
                },
                "recent_6": {
                    "start": recent_six[0]["date"],
                    "end": recent_six[-1]["date"],
                    "change": self._change(
                        float(recent_six[0]["value"]),
                        float(recent_six[-1]["value"]),
                        indicator.value,
                    ),
                    "values": [
                        {"date": row["date"], "value": row["value"]}
                        for row in recent_six
                    ],
                },
            }

        return {
            "period": {
                "start": min(periods) if periods else None,
                "end": max(periods) if periods else None,
            },
            "total_records": len(self.active_records()),
            "indicators": indicators,
            "last_sync": self.repository.get_meta("sync"),
            "interpretation_warning": (
                "데이터의 상관관계는 인과관계를 의미하지 않으며, 전망은 가능한 "
                "시나리오에 대한 설명입니다."
            ),
        }

    def compare(
        self,
        period_a_start: str,
        period_a_end: str,
        period_b_start: str,
        period_b_end: str,
        indicators: Iterable[Indicator],
    ) -> dict:
        selected = {indicator.value for indicator in indicators}
        grouped: dict[str, list[dict]] = defaultdict(list)
        for record in self.active_records():
            if record["indicator"] in selected:
                grouped[record["indicator"]].append(record)

        def describe(rows: list[dict], start: str, end: str, indicator: str) -> dict:
            chosen = sorted(
                [row for row in rows if start <= row["date"] <= end],
                key=lambda row: row["date"],
            )
            if not chosen:
                return {"start": start, "end": end, "count": 0, "values": []}
            values = [float(row["value"]) for row in chosen]
            minimum = min(chosen, key=lambda row: float(row["value"]))
            maximum = max(chosen, key=lambda row: float(row["value"]))
            largest_change = None
            if len(chosen) > 1:
                pairs = [
                    {
                        "date": chosen[index]["date"],
                        "change": float(chosen[index]["value"])
                        - float(chosen[index - 1]["value"]),
                    }
                    for index in range(1, len(chosen))
                ]
                largest_change = max(pairs, key=lambda item: abs(item["change"]))
            return {
                "start": start,
                "end": end,
                "count": len(chosen),
                "average": statistics.fmean(values),
                "minimum": {"date": minimum["date"], "value": minimum["value"]},
                "maximum": {"date": maximum["date"], "value": maximum["value"]},
                "change": self._change(values[0], values[-1], indicator),
                "largest_monthly_change": largest_change,
                "values": [
                    {"date": row["date"], "value": row["value"]} for row in chosen
                ],
            }

        result = {}
        for indicator in selected:
            rows = grouped[indicator]
            result[indicator] = {
                **INDICATOR_META[indicator],
                "period_a": describe(rows, period_a_start, period_a_end, indicator),
                "period_b": describe(rows, period_b_start, period_b_end, indicator),
            }
        return {
            "period_a": {"start": period_a_start, "end": period_a_end},
            "period_b": {"start": period_b_start, "end": period_b_end},
            "indicators": result,
        }

    def export_csv(self) -> str:
        output = io.StringIO()
        columns = [
            "id",
            "date",
            "indicator",
            "value",
            "memo",
            "source",
            "status",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in self.list_records(include_deleted=True, limit=100_000):
            writer.writerow(record)
        return output.getvalue()


def validate_period(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="기간은 YYYY-MM 형식이어야 합니다.") from exc
    return value
