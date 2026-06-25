#!/usr/bin/bash
# Usage: ./coeiroink_tts.sh <japanese_text> [output.wav] [styleId]
#        ./coeiroink_tts.sh --list   (show available speakers and styleIds)
#
# Override speaker/speed via env vars:
#   COEIROINK_UUID=<uuid> COEIROINK_STYLE=<styleId> COEIROINK_SPEED=0.85 ./coeiroink_tts.sh <text>

API="http://127.0.0.1:50032"
SPEAKER_UUID="${COEIROINK_UUID:-3c37646f-3881-5374-2a83-149267990abc}"
STYLE_ID="${3:-${COEIROINK_STYLE:-0}}"
SPEED="${4:-${COEIROINK_SPEED:-0.85}}"

if [[ "$1" == "--list" ]]; then
  curl -s "$API/v1/speakers" | python3 -c "
import sys, json
for s in json.load(sys.stdin):
    print(f\"{s['speakerName']}  (uuid: {s['speakerUuid']})\")
    for st in s['styles']:
        print(f\"  styleId={st['styleId']}  {st['styleName']}\")
"
  exit 0
fi

if [[ -z "$1" ]]; then
  echo "Usage: $0 <japanese_text> [output.wav] [styleId]" >&2
  echo "       $0 --list" >&2
  exit 1
fi

TEXT="$1"
OUTPUT="${2:-$(echo "$TEXT" | tr -d '[:space:]').wav}"

python3 - "$TEXT" "$OUTPUT" "$SPEAKER_UUID" "$STYLE_ID" "$API" "$SPEED" <<'PYEOF'
import json, sys, urllib.request, urllib.error

text, output, default_uuid, style_id, api, speed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5], float(sys.argv[6])

def post_json(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"API error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError:
        print(f"Error: cannot connect to COEIROINK at {api}. Is COEIROINK running?", file=sys.stderr)
        sys.exit(1)

# Resolve speaker UUID from styleId (auto-detect if not overridden)
with urllib.request.urlopen(f"{api}/v1/speakers") as resp:
    speakers = json.load(resp)

speaker_uuid = default_uuid
for s in speakers:
    if any(st["styleId"] == style_id for st in s["styles"]):
        speaker_uuid = s["speakerUuid"]
        break

# Step 1: estimate prosody
prosody_raw = post_json(f"{api}/v1/estimate_prosody", {"text": text})
prosody = json.loads(prosody_raw)

# Step 2: synthesise
audio = post_json(f"{api}/v1/synthesis", {
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

with open(output, "wb") as f:
    f.write(audio)

print(f"Saved: {output} ({len(audio)} bytes)")
PYEOF
