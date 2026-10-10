from __future__ import annotations

from functools import lru_cache

from .config import get_settings
from .repository import get_repository
from .services.chat_service import ChatService
from .services.conversation_service import ConversationService
from .services.data_service import DataService
from .services.ecos_service import EcosSyncService


@lru_cache
def get_data_service() -> DataService:
    settings = get_settings()
    return DataService(get_repository(), settings.seed_csv)


@lru_cache
def get_conversation_service() -> ConversationService:
    return ConversationService(get_repository())


@lru_cache
def get_ecos_service() -> EcosSyncService:
    return EcosSyncService(get_repository(), get_settings().ecos_api_key)


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        get_settings(), get_data_service(), get_conversation_service()
    )

