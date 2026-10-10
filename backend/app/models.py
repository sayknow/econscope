from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Indicator(str, Enum):
    exchange_rate = "exchange_rate"
    base_rate = "base_rate"
    cpi = "cpi"


class DataStatus(str, Enum):
    official = "official"
    user = "user"
    modified = "modified"
    deleted = "deleted"


class DataCreate(BaseModel):
    date: str = Field(description="관측 월, YYYY-MM 형식")
    indicator: Indicator
    value: float
    memo: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def validate_month(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m")
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM format") from exc
        if not 2000 <= parsed.year <= 2100:
            raise ValueError("date must be between 2000-01 and 2100-12")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: float) -> float:
        if not -1_000_000 < value < 1_000_000:
            raise ValueError("value is outside the supported range")
        return value


class DataUpdate(BaseModel):
    value: float | None = None
    memo: str | None = Field(default=None, max_length=500)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: float | None) -> float | None:
        if value is not None and not -1_000_000 < value < 1_000_000:
            raise ValueError("value is outside the supported range")
        return value


class DataRecord(BaseModel):
    id: str
    date: str
    indicator: Indicator
    value: float
    memo: str = ""
    source: Literal["ecos", "user"]
    status: DataStatus
    original_value: float | None = None
    created_at: str
    updated_at: str
    deleted_from_status: DataStatus | None = None


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=30_000)
    created_at: str | None = None
    metadata: dict = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    messages: list[Message] = Field(default_factory=list)


class ConversationRecord(BaseModel):
    id: str
    title: str
    messages: list[Message]
    preview: str
    message_count: int
    created_at: str
    updated_at: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    conversation_id: str | None = None
    detailed: bool = False
    outlook_months: int = Field(default=3, ge=1, le=12)
    comparison_context: dict | None = None


class SourceItem(BaseModel):
    title: str
    organization: str = ""
    date: str = ""
    url: str


class OutlookScenario(BaseModel):
    title: str
    content: str


class Outlook(BaseModel):
    direction: Literal["상승", "유지", "하락"]
    confidence: Literal["낮음", "보통", "높음"]
    confidence_reason: str
    months: int
    watch_items: list[str]
    scenarios: list[OutlookScenario]


class ChatResponse(BaseModel):
    conversation_id: str
    title: str
    answer: str
    sources: list[SourceItem] = Field(default_factory=list)
    source_notice: str | None = None
    outlook: Outlook | None = None
    generated_by: Literal["gemini", "openai", "local-analysis"]
