"""
AI service: GPT-4o with tool use for personal finance queries.
Uses Supabase client for conversation persistence.
"""
import json
import os
from datetime import date, datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI
from supabase import Client
from services.finance_tools import TOOLS, execute_tool

load_dotenv()

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


SYSTEM_PROMPT = """You are a personal finance assistant for Pakistan. Today is {today}. You are helping {email}.
All amounts are in Pakistani Rupees (PKR). Always display amounts as "Rs X,XXX" — never use $ or USD.

You have tools to query AND write the user's financial data.

WORKFLOW:
1. Always call get_user_context first to apply the user's known preferences.
2. For spending questions → get_spending_summary (uses pre-computed data, fast).
3. For specific transactions → get_transactions with filters.
4. For trend questions ("am I spending more?") → get_monthly_trend.
5. For unknown merchant charges → lookup_merchant.
6. When user shares context ("I get paid on the 1st") → remember_user_fact.

RECEIPT IMAGE WORKFLOW (critical):
When the user uploads a receipt image:
1. Read it carefully — extract merchant name, date, total amount, and item list.
2. If the image is blurry, cut off, rotated, or in another language and you cannot read a field with confidence, explicitly say so: "I can't clearly read the [field] — could you confirm it?"
3. Never guess or invent an amount you cannot read. If the total is unreadable, ask the user to type it.
4. Show a clear summary of what you DID extract, marking uncertain fields with "(?)" so the user knows to verify.
5. ALWAYS end with: "Shall I record this as a [Category] expense of Rs [amount]?"
6. When the user says yes / confirm / ok / sure → immediately call create_transaction with the confirmed details.
7. Confirm with: "Done! Recorded Rs [amount] at [merchant] under [category]."

RECORDING TRANSACTIONS:
- Use create_transaction whenever a user confirms saving a receipt OR verbally mentions a purchase.
- Amount must be NEGATIVE for expenses, POSITIVE for income.
- Pick the most specific category from the enum.

PRINCIPLES:
- Lead with the number or answer, then context.
- Be specific — users trust data-backed advice.
- Suggest actionable next steps when relevant.
- Never fabricate numbers — if data is unavailable, say so.
- Keep responses concise. Use markdown (bold, bullets) for clarity."""


def _build_system(user) -> str:
    return SYSTEM_PROMPT.format(today=date.today().isoformat(), email=user.email)


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


CHAT_MODEL = "gpt-4o-mini"  # 15× cheaper than gpt-4o; handles finance Q&A + tool calls well


def _execute_tool_calls(tool_calls_raw: dict, user_id: str, db: Client) -> list:
    """Execute a batch of tool calls and return tool-role messages."""
    result_msgs = []
    for idx in sorted(tool_calls_raw):
        tc = tool_calls_raw[idx]
        try:
            args = json.loads(tc["arguments"] or "{}")
            result = execute_tool(tc["name"], args, user_id, db)
        except Exception as exc:
            result = {"error": str(exc)}
        result_msgs.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(result, default=str),
        })
    return result_msgs


def _run_tool_loop(user, messages: list, db: Client) -> str:
    """Non-streaming fallback (kept for internal use)."""
    client = _get_client()
    oai_tools = _to_openai_tools(TOOLS)
    user_id = str(user.id)

    for _ in range(6):
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=oai_tools,
            tool_choice="auto",
            max_tokens=2048,
        )
        choice = response.choices[0]
        msg = choice.message

        if choice.finish_reason == "stop":
            messages.append({"role": "assistant", "content": msg.content or ""})
            return msg.content or "I couldn't generate a response."

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            raw = {i: {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                   for i, tc in enumerate(msg.tool_calls)}
            messages.extend(_execute_tool_calls(raw, user_id, db))
        else:
            break

    return "I had trouble processing that request. Please try again."


def chat_stream(user, message: str, db: Client,
                conversation_id: int = None,
                image_data: str = None, image_type: str = None):
    """
    Generator that yields str chunks as the model writes them,
    then finally yields a dict with metadata (conversation_id, title).

    Tool calls are executed synchronously between streaming rounds;
    the user sees the first token of the final answer as soon as tools finish.
    """
    uid = str(user.id)
    client = _get_client()
    oai_tools = _to_openai_tools(TOOLS)

    # ── Load / create conversation ────────────────────────────────────────
    conv = None
    if conversation_id:
        res = db.table("conversations").select("*").eq("id", conversation_id).eq("user_id", uid).execute()
        if res.data:
            conv = res.data[0]
    if not conv:
        res = db.table("conversations").insert(
            {"user_id": uid, "title": "New Chat", "messages": []}
        ).execute()
        conv = res.data[0]

    messages: list = list(conv.get("messages") or [])
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _build_system(user)})

    user_content = (
        [
            {"type": "text", "text": message or "Analyze this receipt."},
            {"type": "image_url", "image_url": {"url": f"data:{image_type or 'image/jpeg'};base64,{image_data}"}},
        ]
        if image_data
        else message
    )
    messages.append({"role": "user", "content": user_content})

    # ── Streaming tool loop ───────────────────────────────────────────────
    full_response = ""

    for _ in range(6):
        stream = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            tools=oai_tools,
            tool_choice="auto",
            max_tokens=2048,
            stream=True,
        )

        content_chunks: list[str] = []
        tool_calls_map: dict[int, dict] = {}
        finish_reason = None

        for chunk in stream:
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            delta = choice.delta

            if delta.content:
                content_chunks.append(delta.content)
                full_response += delta.content
                yield delta.content          # ← user sees this immediately

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tool_calls_map[idx]["id"] = tc_delta.id
                    fn = tc_delta.function
                    if fn:
                        if fn.name:
                            tool_calls_map[idx]["name"] += fn.name
                        if fn.arguments:
                            tool_calls_map[idx]["arguments"] += fn.arguments

        content_text = "".join(content_chunks)

        if finish_reason == "stop":
            messages.append({"role": "assistant", "content": content_text})
            break

        if finish_reason == "tool_calls" and tool_calls_map:
            tool_calls_list = [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in (tool_calls_map[i] for i in sorted(tool_calls_map))
            ]
            messages.append({
                "role": "assistant",
                "content": content_text or None,
                "tool_calls": tool_calls_list,
            })
            messages.extend(_execute_tool_calls(tool_calls_map, uid, db))
        else:
            break

    # ── Persist conversation ──────────────────────────────────────────────
    if len(messages) > 41:
        messages = messages[:1] + messages[-40:]

    title = conv.get("title", "New Chat")
    if title == "New Chat" and message:
        title = _generate_title(message)

    db.table("conversations").update({
        "messages": messages,
        "title": title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conv["id"]).execute()

    yield {"conversation_id": conv["id"], "title": title}


def _generate_title(message: str) -> str:
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a short 3–6 word title that captures the user's intent. "
                        "No quotes, no punctuation at the end. Just the title words."
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_tokens=20,
            temperature=0.3,
        )
        title = resp.choices[0].message.content.strip().strip('"').strip("'")
        return title if title else message[:40]
    except Exception:
        text = message.strip()
        return text[:40] if len(text) <= 40 else text[:37].rsplit(" ", 1)[0] + "..."


def chat(
    user,
    message: str,
    db: Client,
    conversation_id: int = None,
    image_data: str = None,
    image_type: str = None,
) -> tuple:
    """Returns (response_text, conversation_id, title)."""
    uid = str(user.id)

    # Load or create conversation
    conv = None
    if conversation_id:
        result = db.table("conversations").select("*").eq("id", conversation_id).eq("user_id", uid).execute()
        if result.data:
            conv = result.data[0]

    if not conv:
        result = db.table("conversations").insert({"user_id": uid, "title": "New Chat", "messages": []}).execute()
        conv = result.data[0]

    messages: list = list(conv.get("messages") or [])

    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _build_system(user)})

    if image_data:
        content = [
            {"type": "text", "text": message or "Analyze this receipt and extract merchant, date, total, and items."},
            {"type": "image_url", "image_url": {"url": f"data:{image_type or 'image/jpeg'};base64,{image_data}"}},
        ]
    else:
        content = message

    messages.append({"role": "user", "content": content})

    response_text = _run_tool_loop(user, messages, db)

    if len(messages) > 41:
        messages = messages[:1] + messages[-40:]

    title = conv.get("title", "New Chat")
    if title == "New Chat" and message:
        title = _generate_title(message)

    db.table("conversations").update({
        "messages": messages,
        "title": title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conv["id"]).execute()

    return response_text, conv["id"], title
