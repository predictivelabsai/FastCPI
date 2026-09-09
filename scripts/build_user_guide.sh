#!/usr/bin/env bash
# Build dated FastCPI user-guide PDF and PPTX artifacts from one Markdown source.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/docs"

SRC="${1:-fastcpi_user_guide.md}"
SRC="$(basename "$SRC")"
test -f "$SRC" || { echo "Guide source not found: docs/$SRC" >&2; exit 1; }

GUIDE_DATE="${GUIDE_DATE:-$(date +%Y-%m-%d)}"
GUIDE_DATE_LONG="${GUIDE_DATE_LONG:-$(date '+%-d %B %Y')}"
GUIDE_VERSION="${GUIDE_VERSION:-$(head -n 1 "$ROOT/VERSION" 2>/dev/null || echo 1.0.0)}"
BASE="fastcpi_user_guide_${GUIDE_DATE}"
SNAPSHOT="${BASE}.md"
HTML="${BASE}.html"

sed -e "s/{{GUIDE_VERSION}}/${GUIDE_VERSION}/g" \
    -e "s/{{GUIDE_DATE_LONG}}/${GUIDE_DATE_LONG}/g" \
    -e "s/{{GUIDE_DATE}}/${GUIDE_DATE}/g" "$SRC" > "$SNAPSHOT"

pandoc "$SNAPSHOT" -s --from=markdown-implicit_figures \
  --css assets/guide.css --metadata pagetitle="FastCPI User Guide" -o "$HTML"
weasyprint "$HTML" "${BASE}.pdf"
pandoc "$SNAPSHOT" --from=markdown --to=pptx -o "${BASE}.pptx"
rm -f "$HTML"

echo "Wrote docs/${BASE}.md"
echo "Wrote docs/${BASE}.pdf ($(du -h "${BASE}.pdf" | cut -f1))"
echo "Wrote docs/${BASE}.pptx ($(du -h "${BASE}.pptx" | cut -f1))"
