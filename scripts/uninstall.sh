#!/usr/bin/env bash
# Sediman uninstaller
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[32m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

info()  { echo -e "  ${GREEN}+${RESET} $*"; }
warn()  { echo -e "  ${RED}!${RESET} $*"; }

SEDIMAN_BIN_DIR="$HOME/.sediman/bin"
SEDIMAN_DATA_DIR="$HOME/.sediman"
REMOVE_DATA=false

for arg in "$@"; do
    case "$arg" in
        --remove-data) REMOVE_DATA=true ;;
        --help|-h)
            echo "Usage: bash uninstall.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --remove-data   Remove all Sediman data (skills, memory, sessions)"
            echo "  --help          Show this help"
            exit 0
            ;;
    esac
done

echo ""
echo -e "  ${BOLD}Sediman Uninstaller${RESET}"
echo ""

if command -v uv &>/dev/null; then
    info "Removing sediman-browse Python tool..."
    uv tool uninstall sediman-browse 2>/dev/null || true
fi

if [ -d "$SEDIMAN_BIN_DIR" ]; then
    info "Removing $SEDIMAN_BIN_DIR..."
    rm -rf "$SEDIMAN_BIN_DIR"
fi

if [ "$REMOVE_DATA" = "true" ]; then
    warn "Removing all Sediman data at $SEDIMAN_DATA_DIR..."
    rm -rf "$SEDIMAN_DATA_DIR"
else
    info "Keeping data at $SEDIMAN_DATA_DIR (use --remove-data to delete)"
fi

for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [ -f "$rc" ] && grep -qF ".sediman/bin" "$rc" 2>/dev/null; then
        info "Removing PATH entry from $rc..."
        sed -i.bak '/# Added by Sediman installer/d' "$rc"
        sed -i.bak '/.sediman\/bin/d' "$rc"
        rm -f "${rc}.bak" 2>/dev/null || true
    fi
done

echo ""
echo -e "  ${BOLD}Sediman uninstalled.${RESET}"
echo ""
