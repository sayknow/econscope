from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_chat_service
from ..models import ChatRequest, ChatResponse
from ..services.chat_service import ChatService


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> dict:
    """데이터 요약을 시스템 문맥에 주입해 AI 답변을 생성하고 대화를 저장한다."""
    return service.chat(payload)

