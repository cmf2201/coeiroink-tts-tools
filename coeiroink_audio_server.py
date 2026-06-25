#!/usr/bin/env python3
"""
Local audio server for Yomitan.
Generates Japanese TTS audio via COEIROINK on demand.

Usage:
  python3 coeiroink_audio_server.py [--port 5050] [--style 0]

Yomitan setup:
  Settings → Audio → Add custom source (type: Custom)
  URL: http://localhost:5050/?term={term}&reading={reading}
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

COEIROINK_API = "http://127.0.0.1:50032"
_cache: dict[str, bytes] = {}


def get_speakers() -> list[dict]:
    with urllib.request.urlopen(f"{COEIROINK_API}/v1/speakers") as r:
        return json.load(r)


def resolve_uuid(style_id: int, speakers: list[dict]) -> str:
    for s in speakers:
        if any(st["styleId"] == style_id for st in s["styles"]):
            return s["speakerUuid"]
    raise ValueError(f"styleId {style_id} not found in any loaded speaker")


def synthesize(text: str, speaker_uuid: str, style_id: int) -> bytes:
    def post(url: str, body: dict) -> bytes:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return r.read()

    prosody = json.loads(post(f"{COEIROINK_API}/v1/estimate_prosody", {"text": text}))
    audio = post(f"{COEIROINK_API}/v1/synthesis", {
        "speakerUuid": speaker_uuid,
        "styleId": style_id,
        "text": text,
        "prosodyDetail": prosody["detail"],
        "volumeScale": 1.0,
        "pitchScale": 0.0,
        "intonationScale": 1.0,
        "prePhonemeLength": 0.1,
        "postPhonemeLength": 0.1,
        "outputSamplingRate": 44100,
        "speedScale": 1.0,
    })
    return audio


def make_handler(style_id: int, speakers: list[dict]):
    speaker_uuid = resolve_uuid(style_id, speakers)
    speaker_name = next(s["speakerName"] for s in speakers
                        if s["speakerUuid"] == speaker_uuid)
    style_name = next(st["styleName"] for s in speakers
                      for st in s["styles"] if st["styleId"] == style_id)
    print(f"Using: {speaker_name} / {style_name} (styleId={style_id})")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print(f"  {self.address_string()} {fmt % args}")

        def do_GET(self):
            # http.server decodes the path as latin-1; re-encode to recover raw
            # UTF-8 bytes then decode properly (handles both encoded and raw Japanese)
            path = self.path.encode("latin-1").decode("utf-8", errors="replace")
            parsed = urllib.parse.urlparse(path)
            params = urllib.parse.parse_qs(parsed.query)

            # Support both ?term=... and ?expression=... (older Yomichan compat)
            term = (params.get("term") or params.get("expression") or [None])[0]
            if not term:
                self.send_error(400, "Missing ?term= parameter")
                return

            cache_key = f"{term}:{style_id}"
            if cache_key not in _cache:
                try:
                    _cache[cache_key] = synthesize(term, speaker_uuid, style_id)
                except urllib.error.URLError:
                    self.send_error(503, "COEIROINK engine not reachable")
                    return
                except Exception as e:
                    self.send_error(500, str(e))
                    return

            audio = _cache[cache_key]
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(audio)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="COEIROINK audio server for Yomitan")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--style", type=int, default=None,
                        help="styleId to use (default: first available)")
    args = parser.parse_args()

    try:
        speakers = get_speakers()
    except Exception:
        print("Error: cannot reach COEIROINK engine at", COEIROINK_API, file=sys.stderr)
        print("Make sure COEIROINK is running first.", file=sys.stderr)
        sys.exit(1)

    print("Available speakers:")
    for s in speakers:
        for st in s["styles"]:
            print(f"  styleId={st['styleId']:>12}  {s['speakerName']} / {st['styleName']}")

    if args.style is None:
        args.style = speakers[0]["styles"][0]["styleId"]
        print(f"\nNo --style specified, defaulting to styleId={args.style}")

    handler = make_handler(args.style, speakers)
    server = HTTPServer(("127.0.0.1", args.port), handler)
    print(f"\nListening on http://127.0.0.1:{args.port}/")
    print(f"Yomitan URL: http://localhost:{args.port}/?term={{term}}&reading={{reading}}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
