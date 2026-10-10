from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import BACKEND_DIR, get_settings


class Repository(ABC):
    @abstractmethod
    def list_data(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_data(self, record_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set_data(self, record_id: str, record: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_conversations(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set_conversation(self, conversation_id: str, record: dict[str, Any]) -> None: ...

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool: ...

    @abstractmethod
    def get_meta(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def set_meta(self, key: str, value: dict[str, Any]) -> None: ...


class JsonRepository(Repository):
    """Small durable local repository used when Firebase credentials are absent."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or BACKEND_DIR / ".local_data" / "db.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"data": {}, "conversations": {}, "meta": {}})

    def _read(self) -> dict[str, Any]:
        with self._lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, FileNotFoundError):
                return {"data": {}, "conversations": {}, "meta": {}}

    def _write(self, payload: dict[str, Any]) -> None:
        with self._lock:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp.replace(self.path)

    def list_data(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._read()["data"].values()]

    def get_data(self, record_id: str) -> dict[str, Any] | None:
        item = self._read()["data"].get(record_id)
        return deepcopy(item) if item else None

    def set_data(self, record_id: str, record: dict[str, Any]) -> None:
        payload = self._read()
        payload["data"][record_id] = deepcopy(record)
        self._write(payload)

    def list_conversations(self) -> list[dict[str, Any]]:
        return [deepcopy(item) for item in self._read()["conversations"].values()]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        item = self._read()["conversations"].get(conversation_id)
        return deepcopy(item) if item else None

    def set_conversation(self, conversation_id: str, record: dict[str, Any]) -> None:
        payload = self._read()
        payload["conversations"][conversation_id] = deepcopy(record)
        self._write(payload)

    def delete_conversation(self, conversation_id: str) -> bool:
        payload = self._read()
        existed = conversation_id in payload["conversations"]
        payload["conversations"].pop(conversation_id, None)
        if existed:
            self._write(payload)
        return existed

    def get_meta(self, key: str) -> dict[str, Any] | None:
        item = self._read()["meta"].get(key)
        return deepcopy(item) if item else None

    def set_meta(self, key: str, value: dict[str, Any]) -> None:
        payload = self._read()
        payload["meta"][key] = deepcopy(value)
        self._write(payload)


class MemoryRepository(Repository):
    """Fast isolated repository for tests."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.conversations: dict[str, dict[str, Any]] = {}
        self.meta: dict[str, dict[str, Any]] = {}

    def list_data(self) -> list[dict[str, Any]]:
        return deepcopy(list(self.data.values()))

    def get_data(self, record_id: str) -> dict[str, Any] | None:
        return deepcopy(self.data.get(record_id))

    def set_data(self, record_id: str, record: dict[str, Any]) -> None:
        self.data[record_id] = deepcopy(record)

    def list_conversations(self) -> list[dict[str, Any]]:
        return deepcopy(list(self.conversations.values()))

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        return deepcopy(self.conversations.get(conversation_id))

    def set_conversation(self, conversation_id: str, record: dict[str, Any]) -> None:
        self.conversations[conversation_id] = deepcopy(record)

    def delete_conversation(self, conversation_id: str) -> bool:
        return self.conversations.pop(conversation_id, None) is not None

    def get_meta(self, key: str) -> dict[str, Any] | None:
        return deepcopy(self.meta.get(key))

    def set_meta(self, key: str, value: dict[str, Any]) -> None:
        self.meta[key] = deepcopy(value)


class FirestoreRepository(Repository):
    def __init__(self, credentials_info: dict[str, Any]) -> None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(credentials_info))
        self.client = firestore.client()

    @staticmethod
    def _snapshot(snapshot: Any) -> dict[str, Any] | None:
        if not snapshot.exists:
            return None
        value = snapshot.to_dict()
        value["id"] = snapshot.id
        return value

    def list_data(self) -> list[dict[str, Any]]:
        return [self._snapshot(doc) for doc in self.client.collection("data").stream()]

    def get_data(self, record_id: str) -> dict[str, Any] | None:
        return self._snapshot(self.client.collection("data").document(record_id).get())

    def set_data(self, record_id: str, record: dict[str, Any]) -> None:
        payload = dict(record)
        payload.pop("id", None)
        self.client.collection("data").document(record_id).set(payload)

    def list_conversations(self) -> list[dict[str, Any]]:
        return [
            self._snapshot(doc) for doc in self.client.collection("conversations").stream()
        ]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        return self._snapshot(
            self.client.collection("conversations").document(conversation_id).get()
        )

    def set_conversation(self, conversation_id: str, record: dict[str, Any]) -> None:
        payload = dict(record)
        payload.pop("id", None)
        self.client.collection("conversations").document(conversation_id).set(payload)

    def delete_conversation(self, conversation_id: str) -> bool:
        ref = self.client.collection("conversations").document(conversation_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def get_meta(self, key: str) -> dict[str, Any] | None:
        return self._snapshot(self.client.collection("meta").document(key).get())

    def set_meta(self, key: str, value: dict[str, Any]) -> None:
        payload = dict(value)
        payload.pop("id", None)
        self.client.collection("meta").document(key).set(payload)


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    credentials_info = settings.firebase_credentials
    if not settings.use_local_db and credentials_info:
        return FirestoreRepository(credentials_info)
    return JsonRepository()
