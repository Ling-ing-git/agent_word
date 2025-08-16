from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Existing session identifier")
    message: str = Field(..., description="User message content")
    limit_history: int = Field(default=20)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    messages: List[Message]
    persona_name: str