from __future__ import annotations

import uuid
from pathlib import Path
from typing import List, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import ChatRequest, ChatResponse, Message
from .store import append_message, ensure_session, list_messages, load_persona
from .providers import generate_reply


app = FastAPI(title="AI Girlfriend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    ensure_session(session_id)

    # Record user message
    append_message(session_id, role="user", content=request.message)

    # Load persona and build limited history
    persona = load_persona("default")
    history_raw: List[Dict[str, str]] = [
        {"role": m["role"], "content": m["content"]}
        for m in list_messages(session_id, limit=request.limit_history)
    ]

    # Ask provider
    reply_text = generate_reply(persona=persona, history=history_raw)

    # Record assistant message
    append_message(session_id, role="assistant", content=reply_text)

    # Return last few messages for UI convenience
    messages_model: List[Message] = [
        Message(role=m["role"], content=m["content"], created_at=m.get("created_at"))
        for m in list_messages(session_id, limit=request.limit_history)
    ]

    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        messages=messages_model,
        persona_name=persona.get("name", "AI伴侣"),
    )


# Mount static front-end
static_dir: Path = settings.static_dir
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")