#!/usr/bin/env bash
# Build the FastCPI landing-page walkthrough from the reviewed screenshots.
set -euo pipefail
cd "$(dirname "$0")/.."

FRAMES=(
  screenshots/01-english-landing.png
  screenshots/09-french-signup.png
  screenshots/02-english-conversation.png
  screenshots/04-french-landing.png
  screenshots/03-french-conversation.png
  screenshots/05-french-daily-scan.png
  screenshots/06-french-market-overview.png
  screenshots/13-french-watchlist-management.png
  screenshots/12-english-watchlist-run-history.png
  screenshots/14-french-daily-scan-runs.png
  screenshots/10-french-account-api.png
  screenshots/08-developers-api.png
)
OUT="docs/demo/fastcpi-walkthrough.gif"
LANDING_OUT="static/product-demo.gif"
DELAY="${DELAY:-170}"
QA_DELAY="${QA_DELAY:-300}"
WIDTH="${WIDTH:-1100}"

for frame in "${FRAMES[@]}"; do
  test -f "$frame" || { echo "Missing frame: $frame" >&2; exit 1; }
done
mkdir -p "$(dirname "$OUT")"

if command -v convert >/dev/null 2>&1; then
  args=(-loop 0)
  for frame in "${FRAMES[@]}"; do
    frame_delay="$DELAY"
    case "$frame" in *conversation*) frame_delay="$QA_DELAY" ;; esac
    args+=(-delay "$frame_delay" "$frame")
  done
  convert "${args[@]}" -resize "${WIDTH}x" -layers Optimize "$OUT"
elif command -v ffmpeg >/dev/null 2>&1; then
  list_file="$(mktemp)"
  trap 'rm -f "$list_file"' EXIT
  for frame in "${FRAMES[@]}"; do
    printf "file '%s/%s'\nduration %s\n" "$PWD" "$frame" "$(awk "BEGIN{print $DELAY/100}")" >> "$list_file"
  done
  ffmpeg -y -f concat -safe 0 -i "$list_file" -vf "scale=${WIDTH}:-1:flags=lanczos" "$OUT"
else
  echo "ImageMagick or ffmpeg is required." >&2
  exit 1
fi

cp "$OUT" "$LANDING_OUT"
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"
echo "Wrote $LANDING_OUT ($(du -h "$LANDING_OUT" | cut -f1))"
