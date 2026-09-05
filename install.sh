#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_ROOT="${TECOLOTE_INSTALL_ROOT:-$HOME/.local/share/tecolote}"
VENV_DIR="$INSTALL_ROOT/venv"
BIN_DIR="${TECOLOTE_BIN_DIR:-$HOME/.local/bin}"
COMMAND_PATH="$BIN_DIR/tecolote"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. On Ubuntu 24.04 run:" >&2
  echo "  sudo apt-get update && sudo apt-get install -y python3 python3-venv" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Tecolote requires Python 3.11 or newer." >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install --upgrade .

if [[ -e "$COMMAND_PATH" && ! -L "$COMMAND_PATH" ]]; then
  echo "Refusing to replace the existing non-symlink: $COMMAND_PATH" >&2
  echo "The installed command is available at $VENV_DIR/bin/tecolote" >&2
  exit 1
fi
ln -sfn "$VENV_DIR/bin/tecolote" "$COMMAND_PATH"

echo "Tecolote CLI installed: $COMMAND_PATH"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "Add this directory to PATH: $BIN_DIR"
fi
echo "Next: tecolote config init"
echo "Then: tecolote doctor"
