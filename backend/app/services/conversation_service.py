from __future__ import annotations

import re
import uuid

from fastapi import HTTPException

from ..models import ConversationCreate, Message
from ..repository import Repository
from ..utils import utc_now


class ConversationService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    @staticmethod
    def make_title(question: str) -> str:
        title = re.sub(r"\s+", " ", question).strip()
        if len(title) > 34:
            title = f"{title[:34].rstrip()}…"
        return title or "새 경제 대화"

    @staticmethod
    def _enrich(record: dict) -> dict:
        messages = record.get("messages", [])
        assistants = [m["content"] for m in messages if m.get("role") == "assistant"]
        preview = assistants[-1] if assistants else "아직 답변이 없습니다."
        preview = re.sub(r"[#*_>`]", "", preview).replace("\n", " ").strip()
        if len(preview) > 110:
            preview = f"{preview[:110].rstrip()}…"
        return {
            **record,
            "preview": preview,
            "message_count": len(messages),
        }

    def create(self, payload: ConversationCreate) -> dict:
        now = utc_now()
        conversation_id = uuid.uuid4().hex
        record = {
            "id": conversation_id,
            "title": payload.title,
            "messages": [
                {
                    **message.model_dump(),
                    "created_at": message.created_at or now,
                }
                for message in payload.messages
            ],
            "created_at": now,
            "updated_at": now,
        }
        self.repository.set_conversation(conversation_id, record)
        return self._enrich(record)

    def get(self, conversation_id: str) -> dict:
        record = self.repository.get_conversation(conversation_id)
        if not record:
            raise HTTPException(status_code=404, detail="대화 기록을 찾을 수 없습니다.")
        return self._enrich(record)

    def list(self) -> list[dict]:
        records = [self._enrich(record) for record in self.repository.list_conversations()]
        records.sort(key=lambda item: item["updated_at"], reverse=True)
        return records

    def append(
        self,
        conversation_id: str | None,
        question: str,
        answer: str,
        assistant_metadata: dict | None = None,
    ) -> dict:
        now = utc_now()
        if conversation_id:
            record = self.repository.get_conversation(conversation_id)
            if not record:
                raise HTTPException(status_code=404, detail="대화 기록을 찾을 수 없습니다.")
        else:
            conversation_id = uuid.uuid4().hex
            record = {
                "id": conversation_id,
                "title": self.make_title(question),
                "messages": [],
                "created_at": now,
                "updated_at": now,
            }
        record["messages"].extend(
            [
                Message(role="user", content=question, created_at=now).model_dump(),
                Message(
                    role="assistant",
                    content=answer,
                    created_at=now,
                    metadata=assistant_metadata or {},
                ).model_dump(),
            ]
        )
        record["updated_at"] = now
        self.repository.set_conversation(conversation_id, record)
        return self._enrich(record)

    def delete(self, conversation_id: str) -> None:
        if not self.repository.delete_conversation(conversation_id):
            raise HTTPException(status_code=404, detail="대화 기록을 찾을 수 없습니다.")

