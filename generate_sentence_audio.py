#!/usr/bin/env python3
"""
Finds Anki cards (Jouzu Vocab Japanese) where the Sentence field has text
but Sentence Audio is empty, generates audio via COEIROINK, and fills it in.

Usage:
  python3 generate_sentence_audio.py           # process pending cards once
  python3 generate_sentence_audio.py --watch   # keep running, check every 5s
  python3 generate_sentence_audio.py --style 986923110  # use a specific voice
"""

import argparse
import base64
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request

ANKI_URL = "http://127.0.0.1:8765"
COEIROINK_URL = "http://127.0.0.1:50032"

NOTE_TYPE = "Jouzu Vocab Japanese"
SENTENCE_FIELD = "Sentence"
AUDIO_FIELD = "Sentence Audio"


def anki(action: str, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        result = json.load(r)
    if result.get("error"):
        raise RuntimeError(f"AnkiConnect: {result['error']}")
    return result["result"]


def get_speakers():
    with urllib.request.urlopen(f"{COEIROINK_URL}/v1/speakers") as r:
        return json.load(r)


def resolve_uuid(style_id: int, speakers: list) -> str:
    for s in speakers:
        if any(st["styleId"] == style_id for st in s["styles"]):
            return s["speakerUuid"]
    raise ValueError(f"styleId {style_id} not found")


DEFAULT_SPEED = 0.85


def synthesize(text: str, speaker_uuid: str, style_id: int, speed: float) -> bytes:
    def post(url, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return r.read()

    prosody = json.loads(post(f"{COEIROINK_URL}/v1/estimate_prosody", {"text": text}))
    return post(f"{COEIROINK_URL}/v1/synthesis", {
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
        "speedScale": speed,
    })


def strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def process_pending(speaker_uuid: str, style_id: int, speed: float) -> int:
    query = f'note:"{NOTE_TYPE}" "{SENTENCE_FIELD}:_*" "{AUDIO_FIELD}:"'
    note_ids = anki("findNotes", query=query)
    if not note_ids:
        return 0

    notes = anki("notesInfo", notes=note_ids)
    count = 0

    for note in notes:
        raw_sentence = note["fields"][SENTENCE_FIELD]["value"]
        sentence = strip_html(raw_sentence).strip()
        if not sentence:
            continue

        print(f"Generating: {sentence[:60]}{'…' if len(sentence) > 60 else ''}")

        try:
            audio = synthesize(sentence, speaker_uuid, style_id, speed)
        except urllib.error.URLError:
            print("  Error: cannot reach COEIROINK. Is it running?", file=sys.stderr)
            return count
        except Exception as e:
            print(f"  Synthesis failed: {e}", file=sys.stderr)
            continue

        h = hashlib.md5(sentence.encode()).hexdigest()[:12]
        filename = f"coeiroink_sentence_{h}.wav"

        anki("storeMediaFile", filename=filename,
             data=base64.b64encode(audio).decode())
        anki("updateNoteFields", note={
            "id": note["noteId"],
            "fields": {AUDIO_FIELD: f"[sound:{filename}]"},
        })

        print(f"  Saved → {filename}")
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true",
                        help="Keep running and check every 5 seconds")
    parser.add_argument("--style", type=int, default=None,
                        help="COEIROINK styleId (default: first available)")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help=f"speech speed scale (default: {DEFAULT_SPEED})")
    args = parser.parse_args()

    try:
        speakers = get_speakers()
    except Exception:
        print("Error: cannot reach COEIROINK at", COEIROINK_URL, file=sys.stderr)
        print("Make sure COEIROINK is running first.", file=sys.stderr)
        sys.exit(1)

    style_id = args.style if args.style is not None else speakers[0]["styles"][0]["styleId"]

    try:
        speaker_uuid = resolve_uuid(style_id, speakers)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    speaker_name = next(s["speakerName"] for s in speakers
                        if s["speakerUuid"] == speaker_uuid)
    style_name = next(st["styleName"] for s in speakers
                      for st in s["styles"] if st["styleId"] == style_id)
    print(f"Voice: {speaker_name} / {style_name} (styleId={style_id}, speed={args.speed})")
    print(f"Note type: {NOTE_TYPE}")
    print(f"Fields: '{SENTENCE_FIELD}' → '{AUDIO_FIELD}'\n")

    if args.watch:
        print("Watching for new cards… (Ctrl+C to stop)\n")
        try:
            while True:
                count = process_pending(speaker_uuid, style_id, args.speed)
                if count:
                    print(f"Processed {count} card(s).\n")
                time.sleep(5)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        count = process_pending(speaker_uuid, style_id, args.speed)
        print(f"\nDone. Processed {count} card(s).")


if __name__ == "__main__":
    main()
