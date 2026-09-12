import base64
import json
import os
import sys
import time
import dotenv
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

dotenv.load_dotenv()


def check_jwt_expiration(token: str) -> bool:
    parts = token.split(".")
    if len(parts) < 2:
        return False

    try:
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))
    except Exception:
        return False

    exp_timestamp = payload.get("exp")
    if exp_timestamp:
        remaining_seconds = exp_timestamp - time.time()
        if remaining_seconds > 0:
            hours = remaining_seconds / 3600
            print(f"[JWT] Token is valid. Remaining time: {hours:.1f} hours")
        else:
            print("[JWT] Token has expired.")
    else:
        print("[JWT] Token does not contain an 'exp' field.")
    return True


def check_deepseek_session(token: str) -> None:
    url = "https://chat.deepseek.com/api/v0/users/current"
    headers = {
        "authorization": f"Bearer {token}",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)

        if response.status_code == 401:
            print("[API] Token is invalid or expired (401 Unauthorized).")
            return

        if response.status_code != 200:
            print(f"[API] Token validation failed (HTTP {response.status_code}).")
            return

        payload = response.json()
        if payload.get("code") != 0:
            print(f"[API] API response error: {payload.get('msg', 'Unknown error')}")
            return

        user_info = payload.get("data", {}).get("biz_data", {})
        email = user_info.get("email") or "Not provided"
        user_id = user_info.get("id") or "Not provided"
        raw_status = user_info.get("status")
        status_text = "Active" if raw_status in (0, "0", None) else str(raw_status)

        print("[API] Token is valid and active.")
        print(f"      Email: {email}")
        print(f"      User ID: {user_id}")
        print(f"      Account Status: {status_text}")

    except httpx.RequestError as exc:
        print(f"[API] Network request error: {exc}")


def main() -> None:
    token = os.getenv("token", "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if not token or token in ("YOUR_TOKEN", "YOUR_DEEPSEEK_TOKEN_HERE", "ВАШ_ТОКЕН"):
        print("Error: Token not found in .env or contains placeholder value.")
        sys.exit(1)

    is_jwt = check_jwt_expiration(token)
    if not is_jwt:
        print("[Info] Token is not in JWT format (using DeepSeek web session token).")

    print("Verifying token activity via DeepSeek API...")
    check_deepseek_session(token)


if __name__ == "__main__":
    main()