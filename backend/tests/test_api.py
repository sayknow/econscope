from fastapi.testclient import TestClient

from app.main import app


def test_health_and_required_routes():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        summary = client.get("/api/data/summary")
        assert summary.status_code == 200
        assert summary.json()["period"]["end"] == "2025-12"

        chat = client.post("/api/chat", json={"question": "최근 물가 흐름을 설명해줘"})
        assert chat.status_code == 200
        conversation_id = chat.json()["conversation_id"]

        conversation = client.get(f"/api/conversations/{conversation_id}")
        assert conversation.status_code == 200
        assert conversation.json()["message_count"] == 2
        assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204


def test_data_crud_and_restore():
    with TestClient(app) as client:
        created = client.post(
            "/api/data",
            json={
                "date": "2099-01",
                "indicator": "exchange_rate",
                "value": 1400.0,
                "memo": "API 테스트",
            },
        )
        assert created.status_code in {201, 409}
        if created.status_code == 201:
            record_id = created.json()["id"]
            updated = client.put(
                f"/api/data/{record_id}", json={"value": 1410.0, "memo": "수정"}
            )
            assert updated.status_code == 200
            assert updated.json()["value"] == 1410.0
            assert client.delete(f"/api/data/{record_id}").status_code == 200
            assert client.post(f"/api/data/{record_id}/restore").status_code == 200
            # Keep the shared local-development repository clean after this API test.
            assert client.delete(f"/api/data/{record_id}").status_code == 200
