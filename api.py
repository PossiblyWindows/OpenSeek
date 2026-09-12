import json
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.backend import DeepSeekBackend, DeepSeekAPIError
from core.config import load_config
from core.dsml import format_messages, parse_dsml_tool_calls


class ChatMessage(BaseModel):
    role: str
    content: Any = ""
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    class Config:
        extra = "allow"


class ChatCompletionRequest(BaseModel):
    model: str = "deepseek-chat"
    messages: List[ChatMessage]
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None

    class Config:
        extra = "allow"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    app.state.config = config
    app.state.backend = DeepSeekBackend(config)
    app.state.http_client = httpx.AsyncClient(timeout=120.0)
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="DeepSeek OpenAI Compatible API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _make_chunk(completion_id: str, created: int, model: str, delta: dict, finish: str | None = None) -> str:
    return json.dumps({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }, ensure_ascii=False)


async def _collect_response(backend: DeepSeekBackend, prompt: str, session_id: str, http_client: httpx.AsyncClient) -> str:
    parts: List[str] = []
    async for block_type, chunk in backend.stream_chat(prompt, session_id, http_client, use_system_prompt=False):
        if block_type == "RESPONSE" and chunk:
            parts.append(chunk)
    return "".join(parts)


async def _stream_plain(
    backend: DeepSeekBackend,
    prompt: str,
    session_id: str,
    http_client: httpx.AsyncClient,
    model: str,
) -> AsyncGenerator[str, None]:
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    ts = int(time.time())

    yield f"data: {_make_chunk(cid, ts, model, {'role': 'assistant'})}\n\n"

    try:
        async for block_type, chunk in backend.stream_chat(prompt, session_id, http_client, use_system_prompt=False):
            if block_type == "RESPONSE" and chunk:
                yield f"data: {_make_chunk(cid, ts, model, {'content': chunk})}\n\n"
    except DeepSeekAPIError as err:
        yield f"data: {json.dumps({'error': {'message': str(err), 'type': 'server_error', 'code': 500}}, ensure_ascii=False)}\n\n"
        return

    yield f"data: {_make_chunk(cid, ts, model, {}, 'stop')}\n\n"
    yield "data: [DONE]\n\n"


async def _stream_with_tools(
    backend: DeepSeekBackend,
    prompt: str,
    session_id: str,
    http_client: httpx.AsyncClient,
    model: str,
) -> AsyncGenerator[str, None]:
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    ts = int(time.time())

    yield f"data: {_make_chunk(cid, ts, model, {'role': 'assistant'})}\n\n"

    try:
        raw = await _collect_response(backend, prompt, session_id, http_client)
    except DeepSeekAPIError as err:
        yield f"data: {json.dumps({'error': {'message': str(err), 'type': 'server_error', 'code': 500}}, ensure_ascii=False)}\n\n"
        return

    tool_calls, cleaned = parse_dsml_tool_calls(raw)

    if cleaned:
        yield f"data: {_make_chunk(cid, ts, model, {'content': cleaned})}\n\n"

    if tool_calls:
        for idx, tc in enumerate(tool_calls):
            yield f"data: {_make_chunk(cid, ts, model, {'tool_calls': [{'index': idx, 'id': tc['id'], 'type': 'function', 'function': tc['function']}]})}\n\n"
        yield f"data: {_make_chunk(cid, ts, model, {}, 'tool_calls')}\n\n"
    else:
        yield f"data: {_make_chunk(cid, ts, model, {}, 'stop')}\n\n"

    yield "data: [DONE]\n\n"


@app.get("/v1/models")
@app.get("/models")
async def list_models():
    ts = int(time.time())
    names = ["deepseek-chat", "deepseek-reasoning"]
    return {
        "object": "list",
        "data": [
            {"id": n, "object": "model", "created": ts, "owned_by": "deepseek", "permission": [], "root": n, "parent": None}
            for n in names
        ],
    }


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    backend: DeepSeekBackend = raw_request.app.state.backend
    http_client: httpx.AsyncClient = raw_request.app.state.http_client

    prompt = format_messages(request.messages, request.tools)
    if not prompt:
        raise HTTPException(status_code=400, detail="Empty messages.")

    try:
        session_id = await backend.create_chat_session(http_client)
    except DeepSeekAPIError as err:
        raise HTTPException(status_code=500, detail=str(err))

    has_tools = bool(request.tools)

    if request.stream:
        gen = _stream_with_tools(backend, prompt, session_id, http_client, request.model) if has_tools else _stream_plain(backend, prompt, session_id, http_client, request.model)
        return StreamingResponse(
            gen,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    try:
        raw = await _collect_response(backend, prompt, session_id, http_client)
    except DeepSeekAPIError as err:
        raise HTTPException(status_code=500, detail=str(err))

    cid = f"chatcmpl-{uuid.uuid4().hex}"
    ts = int(time.time())

    if has_tools:
        tool_calls, cleaned = parse_dsml_tool_calls(raw)
        if tool_calls:
            return {
                "id": cid, "object": "chat.completion", "created": ts, "model": request.model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": cleaned or None, "tool_calls": tool_calls}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": len(prompt), "completion_tokens": len(raw), "total_tokens": len(prompt) + len(raw)},
            }

    return {
        "id": cid, "object": "chat.completion", "created": ts, "model": request.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": raw}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": len(prompt), "completion_tokens": len(raw), "total_tokens": len(prompt) + len(raw)},
    }


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=2666, reload=False)
