from pathlib import Path

from app.config import Settings
from app.models import ChatRequest
from app.repository import MemoryRepository
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.data_service import DataService


SEED = Path(__file__).resolve().parents[1] / "data" / "economic_indicators_monthly.csv"


def build_chat() -> tuple[ChatService, ConversationService]:
    repository = MemoryRepository()
    data_service = DataService(repository, SEED)
    data_service.ensure_seed_data()
    conversations = ConversationService(repository)
    settings = Settings(
        ai_provider="gemini",
        gemini_api_key="",
        gemini_model="gemini-3.5-flash-lite",
        openai_api_key="",
        openai_model="gpt-4.1-mini",
        enable_web_search=False,
        ecos_api_key="",
        firebase_service_account_json="",
        firebase_service_account_path="",
        allowed_origins=("http://localhost:3000",),
        use_local_db=True,
        auto_sync=False,
        seed_csv=SEED,
    )
    return ChatService(settings, data_service, conversations), conversations


def test_chat_uses_local_data_and_saves_conversation():
    service, conversations = build_chat()
    result = service.chat(ChatRequest(question="최근 물가 흐름을 설명해줘"))

    assert result["generated_by"] == "local-analysis"
    assert "2025-12" in result["answer"]
    assert len(conversations.list()) == 1
    assert conversations.list()[0]["message_count"] == 2


def test_outlook_is_directional_and_not_numeric_forecast():
    service, _ = build_chat()
    result = service.chat(ChatRequest(question="앞으로 3개월 물가를 예측할 수 있어?"))

    assert result["outlook"] is not None
    assert result["outlook"].months == 3
    assert result["outlook"].confidence in {"낮음", "보통", "높음"}
    assert "정확한 미래 수치" in result["answer"]


def test_investment_recommendation_is_refused():
    service, _ = build_chat()
    result = service.chat(ChatRequest(question="지금 달러를 매수해야 해?"))

    assert "매수·매도" in result["answer"]
    assert "투자 조언이 아닙니다" in result["answer"]


def test_chat_uses_configured_gemini_provider(monkeypatch):
    service, _ = build_chat()
    object.__setattr__(service.settings, "gemini_api_key", "test-key")

    monkeypatch.setattr(
        service,
        "_gemini_answer",
        lambda request, summary, history: ("## 결론\nGemini 테스트 답변", []),
    )

    result = service.chat(ChatRequest(question="최근 물가 흐름은?"))

    assert result["generated_by"] == "gemini"
    assert "Gemini 테스트 답변" in result["answer"]
