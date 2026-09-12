# OpenSeek API

<p align="center">
  <a href="https://openseek.eleferia.xyz"><img src="https://img.shields.io/badge/Website-openseek.eleferia.xyz-blue?style=flat-square&logo=googlechrome&logoColor=white" alt="Website"></a>
  <a href="https://t.me/eleferia"><img src="https://img.shields.io/badge/Telegram-@eleferia-2CA5E0?style=flat-square&logo=telegram&logoColor=white" alt="Telegram"></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/OpenAI-Compatible-412991?style=flat-square&logo=openai&logoColor=white" alt="OpenAI Compatible">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="MIT License">
</p>

High-performance reverse proxy that bridges DeepSeek's Web Chat API into a 1:1 OpenAI-compatible endpoint. Features an accelerated JIT x86_64 Proof-of-Work solver and native DSML tool-calling parser for AI coding agents (OpenCode, Claude Code, Cursor, Roo Code).

---

## Features

- **OpenAI Compatible**: Drop-in replacement for `/v1/chat/completions` and `/v1/models`.
- **Tool Calling Support**: Automatic bi-directional parsing between OpenAI function calls and DeepSeek's DSML format.
- **Hardware-Accelerated PoW**: Fast JIT x86_64 assembly solver with pure-Python fallback.
- **Full Streaming**: Real-time SSE streaming for chat completions.
- **Lightweight**: Zero telemetry, silent background server mode with automatic port cleanup.

---

## Quickstart

### 1. Installation

```bash
git clone https://github.com/your-repo/openseek-api.git
cd openseek-api
pip install -r requirements.txt
```

### 2. Configuration

Create `.env` by copying the example:

```bash
cp .env.example .env
```

Add your DeepSeek web session token in `.env`:

```env
token=YOUR_DEEPSEEK_TOKEN
```

> **How to get your token**: Open [chat.deepseek.com](https://chat.deepseek.com), log in, press `F12` -> Application -> Local Storage -> find `userToken` (or inspect the `authorization: Bearer ...` header in network requests).

Verify that your token is active:

```bash
python tooken-check.py
```

---

## Usage

### Run OpenAI API Server (Silent Background)

```bash
python main.py
```
- **Base URL**: `http://localhost:2666/v1`
- **API Key**: Any dummy string (e.g. `sk-dummy`)
- **Supported Models**: `deepseek-chat`, `deepseek-reasoner`

### Interactive Terminal Chat

```bash
python client.py
```

---

## AI Agent Integration

Use OpenSeek with any OpenAI-compatible tool or coding agent:

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:2666/v1",
    api_key="sk-dummy"
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### cURL

```bash
curl http://localhost:2666/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-dummy" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Write hello world in Python"}]
  }'
```

---

## Community & Links

- 🌐 **Official Website**: [openseek.eleferia.xyz](https://openseek.eleferia.xyz)
- 📢 **Telegram Channel**: [@eleferia](https://t.me/eleferia)

---

## License

[MIT](LICENSE)
