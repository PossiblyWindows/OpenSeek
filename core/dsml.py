import json
import re
import uuid
from typing import Any, Dict, List, Tuple

_PIPE = r"[|\uff5c]"
_DSML_PREFIX = rf"(?:\s*{_PIPE}\s*{_PIPE}\s*DSML\s*{_PIPE}\s*{_PIPE}\s*|\s*{_PIPE}\s*DSML\s*{_PIPE}\s*)"
_TAG_OPEN = rf"<{_DSML_PREFIX}"
_TAG_CLOSE = rf"</{_DSML_PREFIX}"

_CALLS_BLOCK_RE = re.compile(
    rf"{_TAG_OPEN}calls\s*>(.+?){_TAG_CLOSE}calls\s*>",
    re.DOTALL | re.IGNORECASE,
)
_CALLS_BLOCK_FALLBACK_RE = re.compile(
    r"</?tool_calls?\s*>",
    re.IGNORECASE,
)
_INVOKE_RE = re.compile(
    rf"(?:{_TAG_OPEN}|<\s*)invoke\s+name=[\"']([^\"']+)[\"']\s*>(.*?)(?:{_TAG_CLOSE}|</\s*)invoke\s*>",
    re.DOTALL | re.IGNORECASE,
)
_PARAM_RE = re.compile(
    rf"(?:{_TAG_OPEN}|<\s*)parameter\s+([^>]*?)>(.*?)(?:{_TAG_CLOSE}|</\s*)parameter\s*>",
    re.DOTALL | re.IGNORECASE,
)
_FULL_DSML_STRIP_RE = re.compile(
    rf"(?:{_TAG_OPEN}|<\s*/?)\s*(?:calls|invoke|parameter)[^>]*>",
    re.DOTALL | re.IGNORECASE,
)

DSML_DETECT_RE = re.compile(
    rf"<\s*(?:{_PIPE}\s*{_PIPE}\s*DSML|{_PIPE}\s*DSML|tool_calls?|invoke\s+name)",
    re.IGNORECASE,
)


def _auto_type(val: str, force_string: bool = False) -> Any:
    val = val.strip()
    if val.startswith("<![CDATA[") and val.endswith("]]>"):
        val = val[9:-3]
    if force_string:
        return val
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _parse_params(inner: str) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    for m in _PARAM_RE.finditer(inner):
        attrs_str = m.group(1)
        raw_val = m.group(2)
        name_m = re.search(r'name=["\']([^"\']+)["\']', attrs_str)
        if not name_m:
            continue
        is_str = bool(re.search(r'string=["\']true["\']', attrs_str, re.IGNORECASE))
        args[name_m.group(1).strip()] = _auto_type(raw_val, force_string=is_str)
    return args


def parse_dsml_tool_calls(text: str) -> Tuple[List[Dict[str, Any]], str]:
    if not text:
        return [], ""

    tool_calls: List[Dict[str, Any]] = []

    for m in _INVOKE_RE.finditer(text):
        func_name = m.group(1).strip()
        parsed_args = _parse_params(m.group(2))
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {
                "name": func_name,
                "arguments": json.dumps(parsed_args, ensure_ascii=False),
            },
        })

    cleaned = _CALLS_BLOCK_RE.sub("", text)
    cleaned = _CALLS_BLOCK_FALLBACK_RE.sub("", cleaned)
    cleaned = _INVOKE_RE.sub("", cleaned)
    cleaned = _PARAM_RE.sub("", cleaned)
    cleaned = _FULL_DSML_STRIP_RE.sub("", cleaned)
    cleaned = re.sub(r"<!\[CDATA\[.*?\]\]>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\[citation:\d+\]", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()

    return tool_calls, cleaned


def build_tool_prompt(tools: List[Dict[str, Any]]) -> str:
    if not tools:
        return ""
    lines = [
        "You have access to tools. When you need to call a tool, respond with EXACTLY this XML format. Do NOT wrap it in markdown code fences. Do NOT add any text after the closing tag.",
        "",
        "<tool_calls>",
        '<invoke name="TOOL_NAME">',
        '<parameter name="PARAM_NAME">VALUE</parameter>',
        "</invoke>",
        "</tool_calls>",
        "",
        "RULES:",
        "- Wrap ALL tool calls in <tool_calls>...</tool_calls>",
        "- Each call uses <invoke name=\"...\">...</invoke>",
        "- Parameters go inside <parameter name=\"...\">VALUE</parameter>",
        "- String values: plain text (no quotes needed)",
        "- JSON values: valid JSON",
        "- You may call multiple tools in one <tool_calls> block",
        "- First non-whitespace character of a tool-calling response MUST be <",
        "- Do NOT output any text after </tool_calls>",
        "",
        "Available tools:",
    ]
    for tool in tools:
        fn = tool.get("function", {})
        name = fn.get("name") or tool.get("name", "")
        desc = fn.get("description") or tool.get("description", "")
        params = fn.get("parameters") or tool.get("parameters", {})
        param_str = json.dumps(params, ensure_ascii=False) if params else "{}"
        lines.append(f"- {name}: {desc}")
        lines.append(f"  Parameters: {param_str}")
    return "\n".join(lines)


def format_tool_calls_for_context(tool_calls: Any) -> str:
    if isinstance(tool_calls, str):
        try:
            tool_calls = json.loads(tool_calls)
        except (json.JSONDecodeError, ValueError):
            return ""
    if not isinstance(tool_calls, list):
        return ""
    blocks = ["<tool_calls>"]
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function", {})
        name = fn.get("name") or tc.get("name", "")
        if not name:
            continue
        args = fn.get("arguments") or tc.get("arguments") or "{}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {"content": args}
        blocks.append(f'<invoke name="{name}">')
        if isinstance(args, dict):
            for k, v in args.items():
                if isinstance(v, str):
                    blocks.append(f'<parameter name="{k}">{v}</parameter>')
                else:
                    blocks.append(f'<parameter name="{k}">{json.dumps(v, ensure_ascii=False)}</parameter>')
        blocks.append("</invoke>")
    blocks.append("</tool_calls>")
    return "\n".join(blocks)


def format_messages(messages: List[Any], tools: List[Dict[str, Any]] | None = None) -> str:
    parts: List[str] = []

    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content")
            msg_tool_calls = msg.get("tool_calls")
            name = msg.get("name", "")
            tool_call_id = msg.get("tool_call_id", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", None)
            msg_tool_calls = getattr(msg, "tool_calls", None)
            name = getattr(msg, "name", "")
            tool_call_id = getattr(msg, "tool_call_id", "")

        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
            content = " ".join(text_parts)

        content_str = str(content) if content is not None else ""

        if role == "system":
            system_text = content_str
            if tools:
                system_text += "\n\n" + build_tool_prompt(tools)
                tools = None
            parts.append(system_text)
        elif role == "user":
            parts.append(f"User: {content_str}")
        elif role == "assistant":
            assistant_parts = []
            if content_str:
                assistant_parts.append(content_str)
            if msg_tool_calls:
                assistant_parts.append(format_tool_calls_for_context(msg_tool_calls))
            parts.append(f"Assistant: " + "\n".join(assistant_parts))
        elif role == "tool":
            label = name or tool_call_id or "tool"
            parts.append(f"Tool result ({label}):\n{content_str}")
        else:
            parts.append(f"{role.capitalize()}: {content_str}")

    if tools:
        parts.insert(0, build_tool_prompt(tools))

    return "\n\n".join(parts)
