from pathlib import Path

from app.models import DataCreate, DataStatus, DataUpdate, Indicator
from app.repository import MemoryRepository
from app.services.data_service import DataService


SEED = Path(__file__).resolve().parents[1] / "data" / "economic_indicators_monthly.csv"


def make_service() -> DataService:
    service = DataService(MemoryRepository(), SEED)
    service.ensure_seed_data()
    return service


def test_seed_and_summary_cover_all_three_series():
    service = make_service()
    summary = service.summary()

    assert summary["total_records"] == 396
    assert summary["period"] == {"start": "2015-01", "end": "2025-12"}
    assert summary["indicators"]["exchange_rate"]["count"] == 132
    assert summary["indicators"]["base_rate"]["latest"]["value"] == 2.5
    assert summary["indicators"]["cpi"]["latest"]["value"] == 117.57


def test_create_modify_delete_and_restore():
    service = make_service()
    created = service.create_record(
        DataCreate(
            date="2026-01",
            indicator=Indicator.cpi,
            value=118.2,
            memo="테스트 입력",
        )
    )
    assert created["status"] == DataStatus.user.value

    official_id = service.official_id("cpi", "2025-12")
    changed = service.update_record(official_id, DataUpdate(value=999.0))
    assert changed["status"] == DataStatus.modified.value
    assert changed["value"] == 999.0

    deleted = service.soft_delete(official_id)
    assert deleted["status"] == DataStatus.deleted.value
    assert official_id not in {record["id"] for record in service.active_records()}

    restored = service.restore_record(official_id)
    assert restored["status"] == DataStatus.official.value
    assert restored["value"] == 117.57


def test_compare_returns_period_statistics():
    service = make_service()
    comparison = service.compare(
        "2025-10",
        "2025-12",
        "2025-07",
        "2025-09",
        [Indicator.exchange_rate, Indicator.cpi],
    )

    assert comparison["indicators"]["exchange_rate"]["period_a"]["count"] == 3
    assert comparison["indicators"]["cpi"]["period_b"]["count"] == 3
    assert comparison["indicators"]["cpi"]["period_a"]["maximum"]["date"] == "2025-12"

