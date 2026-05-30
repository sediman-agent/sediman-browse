#!/usr/bin/env bash
# Sediman installer — https://sediman.ai
#
# Usage:
#   curl -fsSL https://get.sediman.ai | bash
#   or
#   curl -fsSL https://get.sediman.ai | bash -s -- --skip-browser
#
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[32m'
RED='\033[31m'
CYAN='\033[36m'
DIM='\033[2m'
RESET='\033[0m'

SEDIMAN_BIN_DIR="$HOME/.sediman/bin"
SKIP_BROWSER=false
FORCE=false

for arg in "$@"; do
    case "$arg" in
        --skip-browser) SKIP_BROWSER=true ;;
        --force) FORCE=true ;;
        --help|-h)
            echo "Usage: curl -fsSL https://get.sediman.ai | bash -s -- [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-browser   Skip Playwright/CloakBrowser install"
            echo "  --force          Reinstall even if already installed"
            echo "  --help           Show this help"
            exit 0
            ;;
    esac
done

info()  { echo -e "  ${GREEN}+${RESET} $*"; }
warn()  { echo -e "  ${CYAN}!${RESET} $*"; }
error() { echo -e "  ${RED}X${RESET} $*" >&2; }

detect_platform() {
    local os arch
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    arch="$(uname -m)"

    case "$os" in
        darwin) os="macos" ;;
        linux)  os="linux" ;;
        *)
            error "Unsupported OS: $os. Sediman requires macOS or Linux."
            exit 1
            ;;
    esac

    case "$arch" in
        x86_64|amd64)   arch="x86_64" ;;
        aarch64|arm64)  arch="aarch64" ;;
        *)
            error "Unsupported architecture: $arch"
            exit 1
            ;;
    esac

    echo "${arch}-${os}"
}

command_exists() {
    command -v "$1" &>/dev/null
}

install_uv() {
    if command_exists uv && [ "$FORCE" != "true" ]; then
        info "uv already installed $(uv --version 2>/dev/null || true)"
        return 0
    fi

    info "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null

    if ! command_exists uv; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi

    if ! command_exists uv; then
        error "Failed to install uv. Please install manually: https://docs.astral.sh/uv/"
        exit 1
    fi

    info "uv installed $(uv --version)"
}

ensure_uv_in_path() {
    local uv_path
    uv_path="$(command -v uv 2>/dev/null || true)"
    if [ -z "$uv_path" ]; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
}

install_sediman() {
    if command_exists sediman && [ "$FORCE" != "true" ]; then
        local current_version
        current_version="$(sediman --version 2>/dev/null | head -1 || true)"
        info "Sediman already installed: $current_version"
        info "Use --force to reinstall, or 'sediman --version' to check."
        return 0
    fi

    info "Installing sediman-browse via uv..."
    uv tool install sediman-browse --force 2>/dev/null || {
        error "Failed to install sediman-browse via uv tool install."
        error "Try: uv tool install sediman-browse"
        exit 1
    }

    if ! command_exists sediman; then
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi

    if ! command_exists sediman; then
        warn "sediman not found in PATH. You may need to restart your shell."
        warn "Or add ~/.local/bin to your PATH."
    fi

    info "Sediman installed: $(sediman --version 2>/dev/null | head -1 || echo 'unknown')"
}

download_tui_binary() {
    local platform="$1"
    local tui_bin="$SEDIMAN_BIN_DIR/sediman-tui"
    local github_repo="sediman/sediman-browse"

    if [ -x "$tui_bin" ] && [ "$FORCE" != "true" ]; then
        info "sediman-tui already installed at $tui_bin"
        return 0
    fi

    local latest_tag
    latest_tag="$(curl -fsSL "https://api.github.com/repos/${github_repo}/releases/latest" 2>/dev/null | grep '"tag_name"' | head -1 | sed -E 's/.*"tag_name":\s*"([^"]+)".*/\1/' || true)"

    if [ -z "$latest_tag" ]; then
        warn "Could not determine latest release. Skipping TUI binary."
        warn "You can build it from source: cargo build -p sediman-tui"
        return 0
    fi

    local archive_name="sediman-${latest_tag}-${platform}.tar.gz"
    local download_url="https://github.com/${github_repo}/releases/download/${latest_tag}/${archive_name}"

    info "Downloading sediman-tui ${latest_tag} for ${platform}..."

    mkdir -p "$SEDIMAN_BIN_DIR"

    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' RETURN

    if ! curl -fsSL "$download_url" -o "$tmp_dir/$archive_name" 2>/dev/null; then
        warn "Pre-built TUI binary not available for ${platform}. Skipping."
        warn "You can build from source: cargo build -p sediman-tui"
        return 0
    fi

    tar xzf "$tmp_dir/$archive_name" -C "$tmp_dir" 2>/dev/null || true

    if [ -f "$tmp_dir/sediman-tui" ]; then
        cp "$tmp_dir/sediman-tui" "$tui_bin"
    elif [ -f "$tmp_dir/bin/sediman-tui" ]; then
        cp "$tmp_dir/bin/sediman-tui" "$tui_bin"
    else
        warn "TUI binary not found in archive. Skipping."
        return 0
    fi

    chmod +x "$tui_bin"
    info "sediman-tui installed to $tui_bin"
}

install_browser() {
    if [ "$SKIP_BROWSER" = "true" ]; then
        info "Skipping browser install (--skip-browser)"
        return 0
    fi

    info "Installing Playwright Chromium..."
    if python3 -m playwright install chromium 2>/dev/null; then
        info "Playwright Chromium installed"
    elif uv run playwright install chromium 2>/dev/null; then
        info "Playwright Chromium installed (via uv)"
    else
        warn "Could not install Playwright Chromium automatically."
        warn "Run 'sediman init' after installation to set up the browser."
    fi

    info "Installing CloakBrowser..."
    if python3 -m cloakbrowser install 2>/dev/null; then
        info "CloakBrowser installed"
    elif uv run python -m cloakbrowser install 2>/dev/null; then
        info "CloakBrowser installed (via uv)"
    else
        warn "Could not install CloakBrowser automatically."
        warn "Run 'sediman init' after installation."
    fi
}

add_to_path() {
    local shell_rc="$HOME/.zshrc"
    local shell_name="${SHELL##*/}"

    if [ "$shell_name" = "bash" ]; then
        shell_rc="$HOME/.bashrc"
    fi

    local path_line="export PATH=\"$SEDIMAN_BIN_DIR:\$PATH\""

    if [ -f "$shell_rc" ] && grep -qF "$SEDIMAN_BIN_DIR" "$shell_rc" 2>/dev/null; then
        return 0
    fi

    echo "" >> "$shell_rc"
    echo "# Added by Sediman installer" >> "$shell_rc"
    echo "$path_line" >> "$shell_rc"

    info "Added $SEDIMAN_BIN_DIR to PATH in $shell_rc"
}

main() {
    echo ""
    echo -e "  ${BOLD}Sediman Installer${RESET}"
    echo -e "  ${DIM}https://sediman.ai${RESET}"
    echo ""

    local platform
    platform="$(detect_platform)"
    info "Detected platform: $platform"

    ensure_uv_in_path
    install_uv
    install_sediman

    if [ "$FORCE" = "true" ] || [ ! -x "$SEDIMAN_BIN_DIR/sediman-tui" ]; then
        download_tui_binary "$platform"
        add_to_path
    fi

    install_browser

    echo ""
    echo -e "  ${BOLD}${GREEN}Installation complete!${RESET}"
    echo ""
    echo -e "  ${DIM}Next steps:${RESET}"
    echo -e "  1. Run ${CYAN}sediman init${RESET} to configure your API key"
    echo -e "  2. Run ${CYAN}sediman run \"your task\"${RESET} to start"
    echo ""

    if [ ! -x "$SEDIMAN_BIN_DIR/sediman-tui" ]; then
        echo -e "  ${DIM}For the TUI, build from source:${RESET}"
        echo -e "  ${CYAN}cargo build --release -p sediman-tui${RESET}"
        echo ""
    fi

    info "Restart your shell or run: source ~/.zshrc (or ~/.bashrc)"
    echo ""
}

main "$@"
