<div align="center">

# Sediman

**Your AI browser employee that works while you sleep.**

Teach it once. It repeats forever. 24/7.

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)]()
[![Discord](https://img.shields.io/discord/1376637192334123070?color=5865F2&label=Discord&logo=discord&logoColor=white)](https://discord.gg/yFbZ58eJ)

</div>

---

<img width="1246" height="854" alt="Screenshot 2026-05-30 at 4 25 03 AM" src="https://github.com/user-attachments/assets/5ff49600-0002-42c5-b307-9ba4b0a1afef" />

---

## Install

### Quick install (recommended)

```bash
curl -fsSL https://get.sediman.ai | bash
```

The installer uses `uv` to install directly from GitHub — no PyPI needed.

### From GitHub

```bash
# Install the latest from main
uv tool install git+https://github.com/sediman-agent/sediman-agent.git

# Or a specific branch/tag
uv tool install git+https://github.com/sediman-agent/sediman-agent.git@feat/v1.0.3-hub-skill-browser
```

### From source

```bash
git clone https://github.com/sediman-agent/sediman-agent.git
cd sediman-agent
uv tool install --force .

# OR for development
uv sync
uv run sediman --help
```

### Install script options

```bash
curl -fsSL https://get.sediman.ai | bash -s -- --branch feat/some-branch
curl -fsSL https://get.sediman.ai | bash -s -- --from-source --force
```

Then:

```bash
sediman init          # set your API key
sediman run "..."     # headless one-shot
sediman chat          # interactive CLI
```

### TUI (Rust terminal UI)

```bash
bun run tui --provider openai --model gpt-4o
OPENAI_API_KEY=sk-... bun run tui --provider openai --model gpt-4o
```

| Command | Description |
|---------|-------------|
| `/provider` | Select LLM provider |
| `/model` | Search or switch models |
| `/memory` | View and edit agent memory |
| `/skills` | List learned skills |
| `/schedule` | List scheduled jobs |
| `/help` | Show all commands |

---

## What It Does

| | Sediman | Browser Use | Scrapers | RPA Tools |
|---|---|---|---|---|
| Real browser (Playwright/Chromium) | Yes | Yes | No | Yes |
| AI-powered | Yes | Yes | No | No |
| **Learn by showing** | Yes | No | No | No |
| **Self-healing** | Yes | No | No | No |
| **24/7 scheduling** | Yes | No | Manual | Paid add-on |
| Persistent memory | Yes | No | No | No |
| Self-learning skills | Yes | No | No | No |
| Self-hosted | Yes | Yes | N/A | Enterprise pricing |

**Key features:**

- **Learn by Showing** — watch your browser once, replay anytime
- **Self-Healing** — pages change? Sediman patches itself automatically
- **Self-Learning** — after each task, saves reusable skills automatically
- **24/7 Scheduling** — cron-based automation, runs while you sleep
- **Skills Hub** — browse and install 470+ community skills
- **Persistent Memory** — remembers preferences across sessions
- **Parallel Subagents** — split complex tasks across multiple agents

---


## License

[LICENSE](LICENSE).

---

<div align="center">

**If this project helps you, consider giving it a star.**

[Report Bug](https://github.com/sediman/sediman/issues) · [Request Feature](https://github.com/sediman/sediman/issues) · [Join Discord](https://discord.gg/yFbZ58eJ)

</div>
