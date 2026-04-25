#!/usr/bin/env bash
# Demo recording for promptc launch materials.
#
# Produces a ~45-second asciinema cast + a GIF that fits in a Twitter card
# (under 5MB) showing the bloated-demo grade D+ flow.
#
# Required tools (install once, both Homebrew / apt available):
#   - asciinema  (records the terminal session into a .cast JSON)
#   - agg        (asciinema gif generator; the SVG-based svg-term-cli does
#                 NOT animate on Twitter / GitHub README — use agg)
#
# Output:
#   demo/promptc-demo.cast   raw asciinema recording
#   demo/promptc-demo.gif    animated GIF for README + tweet
#
# Re-record when:
#   - Hero copy changes
#   - You re-seed examples/bloated-demo
#   - Terminal width / colour palette becomes part of the brand

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${REPO_ROOT}/demo"
CAST="${DEMO_DIR}/promptc-demo.cast"
GIF="${DEMO_DIR}/promptc-demo.gif"

mkdir -p "${DEMO_DIR}"

# --- Pre-flight check ---------------------------------------------------------
for tool in asciinema agg; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    case "$tool" in
      asciinema)
        echo "  Install:  brew install asciinema       (macOS)" >&2
        echo "            apt install asciinema        (Debian / Ubuntu)" >&2
        echo "            pip install asciinema        (cross-platform)" >&2
        ;;
      agg)
        echo "  Install:  brew install agg             (macOS)" >&2
        echo "            cargo install --git https://github.com/asciinema/agg" >&2
        echo "  See https://github.com/asciinema/agg for binaries." >&2
        ;;
    esac
    exit 1
  fi
done

# --- Build the demo session ---------------------------------------------------
# We script the demo into a small shell file that asciinema will record.
# Using a script (rather than typing live) makes the cast deterministic and
# re-recordable.

DEMO_SCRIPT="$(mktemp)"
cleanup() { rm -f "$DEMO_SCRIPT"; }
trap cleanup EXIT

cat > "$DEMO_SCRIPT" <<'EOF'
#!/usr/bin/env bash
clear
# Pause briefly so the recording starts on a clean frame.
sleep 1
echo "$ promptc analyze examples/bloated-demo --no-html"
sleep 0.7
promptc analyze examples/bloated-demo --no-html
sleep 4
echo
echo "$ promptc analyze examples/bloated-demo --open"
sleep 0.7
promptc analyze examples/bloated-demo > /dev/null
echo "Full report: ./promptc-report.html"
sleep 3
EOF

chmod +x "$DEMO_SCRIPT"

# --- Record -------------------------------------------------------------------
echo "Recording asciinema session ..."
cd "${REPO_ROOT}"
asciinema rec \
  --overwrite \
  --idle-time-limit 2 \
  --command "$DEMO_SCRIPT" \
  --rows 36 --cols 96 \
  "$CAST"

# --- Convert to GIF -----------------------------------------------------------
echo "Rendering GIF with agg ..."
agg \
  --theme monokai \
  --font-size 14 \
  --line-height 1.3 \
  --speed 1.0 \
  "$CAST" "$GIF"

echo
echo "Done."
echo "  Cast: $CAST"
echo "  GIF : $GIF"
echo
echo "Embed in README.md:"
echo "  ![promptc demo](demo/promptc-demo.gif)"
