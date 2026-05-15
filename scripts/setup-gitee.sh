#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${SEEDANCE_PROMPT_OPTIMIZER_REPO:-https://gitee.com/bolecodex/seedance-prompt-optimizer.git}"
BRANCH="${SEEDANCE_PROMPT_OPTIMIZER_BRANCH:-main}"
SKILL_NAME="seedance-prompt-optimizer"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$OPENCLAW_HOME/skills}"
INSTALL_DIR="$SKILLS_DIR/$SKILL_NAME"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CLI_NAME="seedance-prompt-optimizer"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd git
require_cmd python3
require_cmd ffmpeg
require_cmd ffprobe

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "Installing $SKILL_NAME from $REPO_URL ($BRANCH)"
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR/repo" >/dev/null

mkdir -p "$SKILLS_DIR"
rm -rf "$INSTALL_DIR"
cp -R "$TMP_DIR/repo/skills/$SKILL_NAME" "$INSTALL_DIR"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/$CLI_NAME" <<EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/scripts/seedance_prompt_optimizer.py" "\$@"
EOF
chmod +x "$BIN_DIR/$CLI_NAME"

echo "Installed skill: $INSTALL_DIR"
echo "Installed CLI: $BIN_DIR/$CLI_NAME"
echo
echo "Try:"
echo "  $CLI_NAME template --task reference"
echo
echo "If the CLI is not found, add this to your shell profile:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
