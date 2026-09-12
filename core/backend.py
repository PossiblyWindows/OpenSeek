import json
from typing import AsyncGenerator, Optional
import httpx

from core.config import AppConfig, get_default_headers
from core.pow_solver import solve_challenge


class DeepSeekAPIError(Exception):
    pass


class DeepSeekBackend:
    def __init__(self, config: AppConfig):
        self.config = config
        self.headers = get_default_headers(config.token)

    async def create_chat_session(self, http_client: httpx.AsyncClient) -> str:
        url = f"{self.config.base_url}/chat_session/create"
        response = await http_client.post(url, headers=self.headers, json={"character_id": None})

        if response.status_code == 401:
            raise DeepSeekAPIError("Invalid DeepSeek authorization token (401 Unauthorized).")
        if response.status_code != 200:
            raise DeepSeekAPIError(f"HTTP error {response.status_code}: {response.text}")

        try:
            payload = response.json()
        except json.JSONDecodeError as json_error:
            raise DeepSeekAPIError("Server returned invalid JSON while creating session.") from json_error

        if payload.get("code") != 0:
            raise DeepSeekAPIError(f"API error: {payload.get('msg', 'Unknown error')}")

        biz_data = payload.get("data", {}).get("biz_data", {})
        session_id = biz_data.get("id") or biz_data.get("chat_session", {}).get("id")
        if not session_id:
            raise DeepSeekAPIError("Server response missing session ID.")

        return str(session_id)

    async def get_pow_header(self, http_client: httpx.AsyncClient) -> str:
        url = f"{self.config.base_url}/chat/create_pow_challenge"
        response = await http_client.post(
            url,
            headers=self.headers,
            json={"target_path": "/api/v0/chat/completion"},
        )

        if response.status_code != 200:
            raise DeepSeekAPIError(f"Failed to fetch PoW challenge (HTTP {response.status_code}): {response.text}")

        try:
            payload = response.json()
        except json.JSONDecodeError as json_error:
            raise DeepSeekAPIError("Server returned invalid JSON for PoW challenge.") from json_error

        challenge_data = payload.get("data", {}).get("biz_data", {}).get("challenge")
        if not challenge_data:
            raise DeepSeekAPIError("PoW challenge data missing from server response.")

        return solve_challenge(challenge_data)

    async def stream_chat(
        self,
        prompt: str,
        session_id: str,
        http_client: httpx.AsyncClient,
        parent_message_id: Optional[int] = None,
        use_system_prompt: bool = True,
    ) -> AsyncGenerator[tuple[str, str], None]:
        pow_header = await self.get_pow_header(http_client)

        request_headers = dict(self.headers)
        request_headers["x-ds-pow-response"] = pow_header
        request_headers["referer"] = f"https://chat.deepseek.com/a/chat/s/{session_id}"

        full_prompt = prompt
        if use_system_prompt and self.config.system_prompt and parent_message_id is None:
            full_prompt = f"{self.config.system_prompt}\n\nUser: {prompt}"

        request_payload = {
            "chat_session_id": session_id,
            "parent_message_id": parent_message_id,
            "model_type": "default",
            "prompt": full_prompt,
            "ref_file_ids": [],
            "thinking_enabled": self.config.thinking_enabled,
            "search_enabled": self.config.search_enabled,
            "action": None,
            "preempt": False,
        }

        url = f"{self.config.base_url}/chat/completion"
        current_mode = "RESPONSE"

        async with http_client.stream(
            "POST",
            url,
            headers=request_headers,
            json=request_payload,
            timeout=120.0,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise DeepSeekAPIError(f"Generation error (HTTP {response.status_code}): {body.decode('utf-8', errors='replace')}")

            async for line in response.aiter_lines():
                if not line:
                    continue

                if line.startswith("{"):
                    try:
                        err_obj = json.loads(line)
                        if err_obj.get("code") != 0:
                            raise DeepSeekAPIError(f"Stream error: {err_obj.get('msg')}")
                    except json.JSONDecodeError:
                        pass
                    continue

                if not line.startswith("data:"):
                    continue

                raw_json = line[5:].strip()
                if raw_json == "[DONE]":
                    break

                try:
                    event_data = json.loads(raw_json)
                except json.JSONDecodeError:
                    continue

                if "v" in event_data and isinstance(event_data["v"], dict) and "response" in event_data["v"]:
                    fragments = event_data["v"]["response"].get("fragments", [])
                    for fragment in fragments:
                        frag_type = fragment.get("type", "RESPONSE")
                        frag_content = fragment.get("content", "")
                        current_mode = frag_type
                        if frag_content:
                            yield (current_mode, frag_content)
                    continue

                if "p" in event_data:
                    path = event_data.get("p", "")
                    value = event_data.get("v")
                    operation = event_data.get("o", "")

                    if path == "response/fragments" and operation == "APPEND" and isinstance(value, list):
                        for fragment in value:
                            frag_type = fragment.get("type", "RESPONSE")
                            frag_content = fragment.get("content", "")
                            current_mode = frag_type
                            if frag_content:
                                yield (current_mode, frag_content)

                    elif path == "response/fragments/-1/content" or operation == "APPEND":
                        if isinstance(value, str):
                            yield (current_mode, value)

                    elif path == "response/status" and value == "FINISHED":
                        break

                elif "v" in event_data and isinstance(event_data["v"], str):
                    chunk_text = event_data["v"]
                    if chunk_text != "FINISHED":
                        yield (current_mode, chunk_text)
