# coeiroink-tts-tools

Two small tools for generating Japanese TTS audio from [COEIROINK v2](https://coeiroink.com/) on Linux, with Yomitan/AnkiConnect integration.

## Prerequisites

- **COEIROINK v2 (Linux)** installed and running — its engine listens on `http://127.0.0.1:50032`
- Python 3.x (stdlib only, no pip installs needed)
- `bash`, `curl`

---

## Files

### `coeiroink_tts.sh` — CLI audio generator

Generate a WAV file from the command line.

```bash
# Basic usage (outputs <word>.wav in current directory)
./coeiroink_tts.sh "猫"

# Specify output file
./coeiroink_tts.sh "猫" cat.wav

# Use a specific voice by styleId
./coeiroink_tts.sh "猫" cat.wav 986923110

# List available speakers and styleIds
./coeiroink_tts.sh --list
```

Override speaker via environment variables:
```bash
COEIROINK_UUID=<uuid> COEIROINK_STYLE=<styleId> ./coeiroink_tts.sh "猫"
```

Batch generation from a word list:
```bash
while IFS= read -r word; do
  ./coeiroink_tts.sh "$word" "${word}.wav"
done < wordlist.txt
```

---

### `coeiroink_audio_server.py` — Local audio server for Yomitan

A small HTTP server that generates audio on demand. Yomitan queries it when looking up words, and the audio gets attached to new Anki cards automatically.

**Start the server** (COEIROINK must already be running):
```bash
python3 coeiroink_audio_server.py
```

Options:
```
--port  PORT     Port to listen on (default: 5050)
--style STYLEID  Speaker styleId to use (default: first available)
```

Example using 火野業華:
```bash
python3 coeiroink_audio_server.py --style 986923110
```

**Yomitan setup:**

1. Open Yomitan settings → **Audio** tab
2. Under "Configure audio playback sources", click **Add**
3. Set type to **Custom**
4. Set URL to:
   ```
   http://localhost:5050/?term={term}&reading={reading}
   ```
5. Move it above other sources so it's used first

Audio is cached in memory for the session, so repeated lookups of the same word don't re-synthesize.

---

## Adding voices to COEIROINK

Speaker packs go in `speaker_info/` inside your COEIROINK installation. Each pack must sit **directly** inside that folder (not nested in subdirectories from a zip):

```
speaker_info/
└── speaker-name-x.x.x/
    ├── metas.json
    ├── portrait.png
    ├── policy.md
    ├── icons/        ← one .png per styleId
    ├── voice_samples/ ← three .wav per styleId
    └── model/
        └── <styleId>/
            ├── 100epoch.pth
            └── config.yaml
```

Restart COEIROINK after adding a new speaker pack.

---

## Auto-start

To have both COEIROINK and the audio server start together, create a launcher script:

```bash
#!/usr/bin/bash
/path/to/COEIROINK_LINUX_CPU_v.2.13.0/COEIROINKv2 &
sleep 5  # wait for the engine to be ready
python3 /path/to/coeiroink-tts-tools/coeiroink_audio_server.py
```
