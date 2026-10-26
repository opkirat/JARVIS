"""Local token server for the JARVIS browser voice client.

Run: .venv/bin/python examples/llm_example.py
"""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL = "gpt-realtime-2.1"
ALLOWED_ORIGINS = {
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (5173, 4173, 8765)
}
INSTRUCTIONS = (
    "You are JARVIS, a concise, helpful personal voice assistant. "
    "Speak naturally and keep most responses to one or two sentences. "
    "You do not currently have tools or access to the user's email, calendar, "
    "grades, weather, or SQLite database. Never claim to have accessed them."
)


class VoiceSetupError(Exception):
    """An actionable error safe to show in the browser."""


def create_client_secret():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise VoiceSetupError("OPENAI_API_KEY is missing from the root .env file.")

    payload = {
        "expires_after": {"anchor": "created_at", "seconds": 60},
        "session": {
            "type": "realtime",
            "model": MODEL,
            "instructions": INSTRUCTIONS,
            "max_output_tokens": 512,
            "audio": {
                "input": {"turn_detection": {"type": "server_vad"}},
                "output": {"voice": "marin"},
            },
        },
    }
    request = Request(
        "https://api.openai.com/v1/realtime/client_secrets",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except HTTPError as error:
        messages = {
            401: "OpenAI rejected the API key. Check the server's OPENAI_API_KEY.",
            403: "This OpenAI project does not have access to the realtime model.",
            429: "OpenAI quota or rate limit reached. Check project billing and limits.",
        }
        raise VoiceSetupError(
            messages.get(error.code, f"OpenAI session setup failed (HTTP {error.code}).")
        ) from None
    except (URLError, TimeoutError, OSError):
        raise VoiceSetupError("Cannot reach OpenAI. Check the server's network connection.") from None

    if not isinstance(data.get("value"), str) or not data["value"]:
        raise VoiceSetupError("OpenAI did not return a usable voice session token.")
    # Return only the short-lived token, never the project's API key.
    return {"value": data["value"], "expires_at": data.get("expires_at"), "model": MODEL}


class VoiceHandler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"status": "ok", "model": MODEL})
        else:
            self.respond(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/api/realtime/token":
            self.respond(404, {"error": "Not found."})
            return
        # Browser clients use a same-origin Vite proxy and a custom header.
        # No CORS permissions are granted to third-party origins.
        origin = self.headers.get("Origin")
        if self.headers.get("X-Jarvis-Voice") != "1" or (
            origin is not None and origin not in ALLOWED_ORIGINS
        ):
            self.respond(403, {"error": "Voice requests must come from the local JARVIS app."})
            return
        try:
            self.respond(200, create_client_secret())
        except VoiceSetupError as error:
            self.respond(502, {"error": str(error)})
        except Exception:
            # Do not expose request headers, tokens, or upstream response bodies.
            self.respond(502, {"error": "Voice session setup failed. Try again."})


def main():
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), VoiceHandler) as server:
        print(f"JARVIS voice server: http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
