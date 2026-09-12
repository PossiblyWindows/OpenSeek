import asyncio
import sys
import httpx

from core.config import load_config
from core.backend import DeepSeekBackend, DeepSeekAPIError


def setup_console():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


async def run_chat():
    setup_console()
    config = load_config()
    backend = DeepSeekBackend(config)

    async with httpx.AsyncClient(timeout=120.0) as http_client:
        session_id = await backend.create_chat_session(http_client)

        while True:
            try:
                user_message = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_message:
                continue

            if user_message.lower() in ("exit", "quit", "q"):
                break

            print("Ai: ", end="", flush=True)

            try:
                async for block_type, chunk in backend.stream_chat(user_message, session_id, http_client):
                    if block_type == "RESPONSE":
                        print(chunk, end="", flush=True)
                print()
            except DeepSeekAPIError as error:
                print(f"\n[Error]: {error}")


if __name__ == "__main__":
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        pass
