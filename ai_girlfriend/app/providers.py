from __future__ import annotations

from typing import Any, Dict, List

from .config import settings


def build_system_prompt(persona: Dict[str, Any]) -> str:
    name = persona.get("name", "你的AI伴侣")
    archetype = persona.get("archetype", "温柔体贴、理性")
    speaking_style = persona.get("speaking_style", "轻松亲切")
    boundaries = persona.get("boundaries", "遵守法律法规，避免不当内容")

    parts = [
        f"你的名字是{name}。你是一位{archetype}的虚拟伴侣。",
        "目标：为用户提供温暖、支持与积极的陪伴，尊重用户边界并鼓励健康生活方式。",
        f"说话风格：{speaking_style}。",
        f"边界：{boundaries}。始终保持成年人的语境，并避免露骨或不当内容。",
        "在回应时使用自然、简洁的中文，保持真诚与共情。",
    ]
    return "\n".join(parts)


def _openai_reply(messages: List[Dict[str, str]], temperature: float = 0.8) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        raise RuntimeError("openai package not available")

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    client = OpenAI(api_key=settings.openai_api_key)

    completion = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
    )
    return (completion.choices[0].message.content or "").strip()


def _local_rule_based_reply(messages: List[Dict[str, str]], persona: Dict[str, Any]) -> str:
    # Very simple, friendly fallback when no API key is present
    user_text = ""
    for m in reversed(messages):
        if m["role"] == "user":
            user_text = m["content"]
            break
    name = persona.get("name", "悠然")
    style = persona.get("speaking_style", "温柔亲切")

    # Heuristics
    if "?" in user_text or "？" in user_text:
        prefix = "这是个好问题"
    elif any(k in user_text for k in ["难过", "焦虑", "累", "疲惫", "压力"]):
        prefix = "我能理解你的感受"
    else:
        prefix = "明白啦"

    return (
        f"{prefix}，我在呢。作为{name}（{style}），我会认真倾听你的想法。"
        f"\n\n你刚刚说到：“{user_text}”。如果愿意，可以多分享一些细节，我会给到更贴合的建议或陪伴。"
    )


def generate_reply(persona: Dict[str, Any], history: List[Dict[str, str]]) -> str:
    system_prompt = build_system_prompt(persona)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    # Try OpenAI first, fall back to local
    try:
        return _openai_reply(messages)
    except Exception:
        return _local_rule_based_reply(messages, persona)