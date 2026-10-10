from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_conversation_service
from ..models import ConversationCreate, ConversationRecord
from ..services.conversation_service import ConversationService


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRecord, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    return service.create(payload)


@router.get("")
def list_conversations(
    service: ConversationService = Depends(get_conversation_service),
) -> list[dict]:
    return service.list()


@router.get("/{conversation_id}", response_model=ConversationRecord)
def get_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> dict:
    return service.get(conversation_id)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    service: ConversationService = Depends(get_conversation_service),
) -> Response:
    service.delete(conversation_id)
    return Response(status_code=204)

