#!/usr/bin/env bash
set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:?usage: render_480p_silent.sh RUN_ID [WORKERS]}"
WORKERS="${2:-6}"
RUN_ROOT="$PACKAGE_ROOT/runs/$RUN_ID"
ENTRY="$PACKAGE_ROOT/scripts/preview_entry_480p.py"

if [[ ! -d "$RUN_ROOT" ]]; then
  echo "run not found: $RUN_ROOT" >&2
  exit 2
fi

find "$RUN_ROOT" -mindepth 2 -maxdepth 2 -name candidate.py -print0 |
  xargs -0 -P "$WORKERS" -I{} bash -c '
    file="$1"
    entry="$2"
    dir="$(dirname "$file")"
    name="$(basename "$dir")"
    docker run --rm --entrypoint manim \
      -e COSYVOICE_ALLOW_TTS_FALLBACK=1 \
      -e COSYVOICE_DISABLE_WORD_TIMESTAMPS=1 \
      -v "$dir:/work" \
      -v "$entry:/work/preview_entry_480p.py:ro" \
      -w /work docker-manim-worker-tts:font-ready \
      -ql --media_dir /work/preview_480p preview_entry_480p.py Solution \
      >"$dir/render_480p.log" 2>&1
    video="$(find "$dir/preview_480p/videos" -type f -name Solution.mp4 -print -quit)"
    ffprobe -v error -select_streams v:0 \
      -show_entries stream=width,height,r_frame_rate,duration \
      -of json "$video" >"$dir/ffprobe.json"
    printf "%s: %s\n" "$name" "$video"
  ' bash {} "$ENTRY"

