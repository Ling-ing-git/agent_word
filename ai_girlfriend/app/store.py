from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings

SESSIONS_DIR: Path = settings.data_dir / "sessions"


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_session(session_id: str) -> Dict[str, Any]:
    path = _session_file(session_id)
    if not path.exists():
        data = {
            "session_id": session_id,
            "created_at": _now_iso(),
            "messages": [],
            "memories": [],
            "persona_key": "default",
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(session: Dict[str, Any]) -> None:
    path = _session_file(session["session_id"])
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def append_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    session = ensure_session(session_id)
    message = {"role": role, "content": content, "created_at": _now_iso()}
    session.setdefault("messages", []).append(message)
    save_session(session)
    return message


def list_messages(session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    session = ensure_session(session_id)
    messages = session.get("messages", [])
    if limit is None:
        return messages
    return messages[-limit:]


def add_memory(session_id: str, content: str, importance: int = 1) -> Dict[str, Any]:
    session = ensure_session(session_id)
    memory = {
        "content": content,
        "importance": int(importance),
        "created_at": _now_iso(),
    }
    session.setdefault("memories", []).append(memory)
    save_session(session)
    return memory


def load_persona(key: str = "default") -> Dict[str, Any]:
    path = settings.personas_dir / f"{key}.json"
    if not path.exists():
        # Fallback very simple persona if file missing
        return {
            "key": key,
            "name": "悠然",
            "archetype": "温柔体贴、理性、喜欢读书与旅行",
            "speaking_style": "轻松、亲切，适度使用emoji",
            "boundaries": "仅提供健康、合法的对话，避免露骨、不当内容。",
        }
    return json.loads(path.read_text(encoding="utf-8"))