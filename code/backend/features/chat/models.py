"""Pydantic models for project-scoped ADK Chat."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


def _utc_now_iso() -> str:
    """Return ISO-formatted UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class ToolTrace(BaseModel):
    tool_name: str
    input_args: Dict[str, Any] = Field(default_factory=dict)
    output_result: Optional[str] = None
    status: Literal["success", "error", "running"] = "success"


class CitationTrace(BaseModel):
    doi: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    verified_in_graph: bool = True


class ChatMessage(BaseModel):
    id: str
    chat_id: str
    sender: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: str = Field(default_factory=_utc_now_iso)
    tool_traces: List[ToolTrace] = Field(default_factory=list)
    citations: List[CitationTrace] = Field(default_factory=list)
    steering_options: List[Dict[str, Any]] = Field(default_factory=list)
    appraisal: Optional[Dict[str, Any]] = None



class ChatSessionSummary(BaseModel):
    id: str
    project_id: str
    title: str
    message_count: int = 0
    last_message_preview: Optional[str] = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)


class CreateChatRequest(BaseModel):
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        return v.strip()


class ChatSessionListResponse(BaseModel):
    chats: List[ChatSessionSummary]


class ChatMessagesResponse(BaseModel):
    messages: List[ChatMessage]


class SendMessageResponse(BaseModel):
    user_message: ChatMessage
    assistant_message: ChatMessage

