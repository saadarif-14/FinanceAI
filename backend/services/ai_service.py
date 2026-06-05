"""
AI service: GPT-4o with tool use for personal finance queries.

Routing strategy:
- Images (receipts) → gpt-4o with vision
- Complex queries → gpt-4o with tools (pre-computed data keeps costs low)
- Conversation history capped at 40 messages

Uses ANTHROPIC_API_KEY → Claude claude-sonnet-4-6 if set.
Falls back to OPENAI_API_KEY → GPT-4o.
"""
import json
import os
from datetime import date
from sqlalchemy.orm import Session
import models
from services.finance_tools import TOOLS, execute_tool

_openai_client = None
_anthropic_client = None


def _use_anthropic() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


SYSTEM_PROMPT = """You are a personal finance assistant. Today is {today}. You are helping {email}.

You have tools to query the user's financial data. Use them to give accurate, data-backed answers.

WORKFLOW:
1. Always call get_user_context first to apply the user's known preferences.
2. For spending questions → get_spending_summary (uses pre-computed data, fast).
3. For specific transactions → get_transactions with filters.
4. For trend questions ("am I spending more?") → get_monthly_trend.
5. For unknown merchant charges → lookup_merchant.
6. When user shares context ("I get paid on the 1st") → remember_user_fact.

PRINCIPLES:
- Lead with the number or answer, then context.
- Be specific — users trust data-backed advice.
- Suggest actionable next steps when relevant.
- If you cannot answer from available data, say so clearly — never fabricate numbers.
- For ambiguous questions, ask a single clarifying question.
- Keep responses concise. Use markdown formatting (bold, bullets) for clarity."""


def _build_system(user: models.User) -> str:
    return SYSTEM_PROMPT.format(today=date.today().isoformat(), email=user.email)


# ── OpenAI tool format conversion ─────────────────────────────────────────────

def _to_openai_tools(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _run_openai_loop(user: models.User, messages: list, db: Session) -> str:
    client = _get_openai()
    oai_tools = _to_openai_tools(TOOLS)
    max_iterations = 6

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=oai_tools,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = response.choices[0]
        msg = choice.message

        if choice.finish_reason == "stop":
            messages.append({"role": "assistant", "content": msg.content or ""})
            return msg.content or "I couldn't generate a response."

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each tool and add results
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                    result = execute_tool(tc.function.name, args, user.id, db)
                except Exception as exc:
                    result = {"error": str(exc)}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })
        else:
            break

    return "I had trouble processing that request. Please try again."


# ── Anthropic tool loop (used when ANTHROPIC_API_KEY is set) ──────────────────

def _serialize_content(content) -> list:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    result = []
    for block in content:
        if hasattr(block, "type"):
            if block.type == "text":
                result.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                result.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
        elif isinstance(block, dict):
            result.append(block)
    return result


def _run_anthropic_loop(user: models.User, messages: list, db: Session) -> str:
    client = _get_anthropic()
    max_iterations = 6

    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_build_system(user),
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "I couldn't generate a response.")
            messages.append({"role": "assistant", "content": _serialize_content(response.content)})
            return text

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": _serialize_content(response.content)})
            tool_results = []
            for block in response.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    try:
                        result = execute_tool(block.name, block.input, user.id, db)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "I had trouble processing that request. Please try again."


# ── Public interface ──────────────────────────────────────────────────────────

def chat(user: models.User, message: str, db: Session, image_data: str = None, image_type: str = None) -> str:
    conv = db.query(models.Conversation).filter(models.Conversation.user_id == user.id).first()
    if not conv:
        conv = models.Conversation(user_id=user.id, messages=[])
        db.add(conv)
        db.commit()

    messages: list = list(conv.messages) if conv.messages else []

    if _use_anthropic():
        # Anthropic message format
        if image_data:
            content = [
                {"type": "image", "source": {"type": "base64", "media_type": image_type or "image/jpeg", "data": image_data}},
                {"type": "text", "text": message or "Analyze this receipt and extract merchant, date, total, and items."},
            ]
        else:
            content = message
        messages.append({"role": "user", "content": content})
        response_text = _run_anthropic_loop(user, messages, db)
    else:
        # OpenAI message format
        if not messages:
            messages.insert(0, {"role": "system", "content": _build_system(user)})

        if image_data:
            content = [
                {"type": "text", "text": message or "Analyze this receipt and extract merchant, date, total, and items."},
                {"type": "image_url", "image_url": {"url": f"data:{image_type or 'image/jpeg'};base64,{image_data}"}},
            ]
        else:
            content = message
        messages.append({"role": "user", "content": content})
        response_text = _run_openai_loop(user, messages, db)

    # Cap history to 40 messages
    if len(messages) > 40:
        # Always keep system message if present
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        messages = system_msgs + other_msgs[-38:]

    conv.messages = messages
    db.add(conv)
    db.commit()

    return response_text
