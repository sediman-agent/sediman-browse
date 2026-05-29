<div align="center">

# Sediman

**The AI browser employee that works while you sleep.**

Teach it once. It repeats forever. 24/7.

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)]()
[![Discord](https://img.shields.io/discord/1376637192334123070?color=5865F2&label=Discord&logo=discord&logoColor=white)](https://discord.gg/yFbZ58eJ)

</div>

---

![Sediman Demo](demo.gif)

---

## It's not a scraper. It's not an API wrapper. It's a browser employee.

You click the same 10 things every morning. Copy-paste data into spreadsheets. Check the same sites every hour. Post the same kind of content every day.

**Sediman watches you do it once. Then does it forever.** Without you.

A real browser opens. It navigates, reads, thinks, types — just like a human. And it remembers how to do it again.

---

## What It Does

### Learn Skills by Showing

Sediman watches your browser actions and auto-creates reusable workflows. No code. No recording. Just do it once. The next time, replay it with a single command — or schedule it to run forever.

### Run 24/7 on Cron

Set it and forget it. Your agent works while you sleep. Daily reports, price monitoring, social posting — all automated on any schedule you define.

### Self-Healing

Pages change. UIs get redesigned. Sediman detects when a skill breaks, takes a screenshot, figures out what changed, and patches itself. No manual fixes.

### Hermes-Style Self-Learning

Sediman doesn't just repeat — it gets smarter. After every task, a background review agent evaluates whether the workflow is worth saving as a reusable skill. It uses a 3-question heuristic: was it complex enough? is it reusable? was something non-obvious discovered? Two out of three triggers an automatic save.

Skills accumulate `when_to use` triggers, `pitfalls` from failed attempts, and `verification` criteria. A periodic staleness auditor cleans up skills that haven't been used in 30 days. Every patch is versioned with full rollback.

### Skills Hub

Browse, install, and share community skills. One command to automate anything.

### Delegate & Parallelize

Complex task? Sediman spins up subagents that work in parallel, each handling one piece, then merges results.

### Persistent Memory

Remembers everything across sessions. Your preferences, your brand voice, your common workflows — all saved.

### Interactive Mode

Full terminal UI with streaming output, slash commands, mid-session model switching.

### API Server

REST + WebSocket. Build your own UI on top.

---

## How Is This Different?

| | Sediman | Browser Use | Scrapers | RPA Tools |
|---|---|---|---|---|
| **Real browser** | Yes | Yes | No | Yes |
| **AI-powered** | Yes | Yes | No | No |
| **Learn by showing** | Yes | No | No | No |
| **Self-healing** | Yes | No | No | No |
| **Self-learning** | Yes | No | No | No |
| **24/7 scheduling** | Yes | No | Manual | Paid add-on |
| **Skill sharing** | Yes (Hub) | No | No | Marketplace |
| **Memory** | Yes | No | No | No |
| **Subagents** | Yes | No | No | No |
| **Self-hosted** | Yes | Yes | N/A | Enterprise pricing |

**Browser Use is a great library.** Sediman is the product built on top of it — with skills, scheduling, memory, self-healing, self-learning, and a hub. It's the difference between an engine and a car.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/sediman/sediman-browse.git
cd sediman-browse

# Install dependencies with uv
uv sync

# Set your OpenAI API key
export OPENAI_API_KEY=sk-...

# Launch the interactive TUI
uv run sediman chat

# Or run a one-shot task
uv run sediman run "check Apple stock price on Yahoo Finance"
```

That's it. A browser opens. Sediman does the rest.

---

## Architecture

Sediman's agent loop follows a think-act-observe-reflect cycle:

```
Task → Manager (plan strategy)
     → Browser Agent (execute in real Chromium)
     → Observer (verify results)
     → Reflector (retry or move on)
     → Skill Learner (auto-extract reusable patterns)
     → Result
```

Key subsystems:

- **Manager Agent** — plans strategy (direct, delegate, use-skill, decompose)
- **Browser Subagent** — executes tasks in a real browser via Browser Use
- **Skill Engine** — CRUD, versioning, rollback, dedup, usage tracking
- **Skill Learner** — Hermes-style 3-question eval, auto-create/patch with pitfalls and verification
- **Skill Auditor** — periodic staleness review, auto-archive/delete
- **Skill Healer** — auto-fix broken skills when page layout changes
- **Memory Manager** — persistent facts, background review, compression
- **Cron Scheduler** — APScheduler-based 24/7 task scheduling

---
## License
[Business Source License 1.1 (BSL)](LICENSE).
---

<div align="center">

**If this project helps you, consider giving it a star.**

[Report Bug](https://github.com/sediman/sediman/issues) · [Request Feature](https://github.com/sediman/sediman/issues) · [Join Discord](https://discord.gg/yFbZ58eJ)

</div>
