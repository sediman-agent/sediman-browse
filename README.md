<div align="center">

# Sediman

**Your AI browser employee that works while you sleep.**

Teach it once. It repeats forever. 24/7.

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)]()

</div>

---

![Sediman Demo](demo.gif)

---

## Stop doing the same tasks. Every day. Forever.

You click the same 10 things every morning. Copy data into spreadsheets. Check the same sites. Post the same content.

**Sediman watches you once. Then does it forever.** A real browser. Real actions. No scripts. No configuration.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Learn by Showing** | Watch your browser once → replay anytime with one command |
| **24/7 Automation** | Schedule tasks with cron — runs while you sleep |
| **Self-Healing** | Pages change? Sediman detects it and patches itself automatically |
| **Self-Learning** | After each task, it decides: "Should I save this as a reusable skill?" |
| **Persistent Memory** | Remembers your preferences, brand voice, workflows — across sessions |
| **Skills Hub** | Browse and install community skills with one command |
| **Subagent Parallelization** | Split complex tasks across multiple agents working in parallel |

---

## Architecture

```mermaid
flowchart TB
    subgraph Entry["Entry Points"]
        CLI([sediman CLI<br/>run, chat, skill, schedule])
        API([FastAPI Server<br/>REST WebSocket])
        TUI([Rust TUI<br/>sediman-tui])
    end

    subgraph Bridge["IPC Bridge"]
        RPC([Unix Socket<br/>JSON-RPC Server])
        BridgeRust([sediman-tui-bridge])
    end

    subgraph AgentCore["Agent Core"]
        Loop([AgentLoop<br/>think-act-observe-reflect])
        Manager([Manager Agent<br/>plan strategy])
        Delegate([Delegate Agent<br/>parallel subagents])
        Planner([Planner<br/>task decomposition])
        Compressor([Context Compressor<br/>token reduction])
        Guardrails([Guardrails<br/>safety checks])
    end

    subgraph Subagents["Subagents"]
        BrowserAgent([Browser Subagent<br/>Chromium via Playwright])
        SkillAuditor([Skill Auditor<br/>staleness review])
        SkillLearner([Skill Learner<br/>3-question heuristic])
        Recorder([Recording Manager<br/>frame capture])
        TraceToSkill([Trace to Skill<br/>recording converter])
    end

    subgraph SkillsSys["Skills System"]
        Engine([SkillEngine<br/>CRUD, versioning, rollback])
        Executor([SkillExecutor<br/>execute with auto-healing])
        Healer([SkillHealer<br/>auto-repair broken skills])
        Hub([Skills Hub<br/>browse, install, publish])
        Lock([SkillLockFile<br/>external source tracking])
    end

    subgraph Mem["Memory System"]
        Store([MemoryStore<br/>dual-file bounded storage])
        Entries([MemoryEntry<br/>structured facts])
        Trajectories([Trajectories<br/>action history])
        Embeddings([Embeddings<br/>vector storage])
        Vector([VectorStore<br/>similarity search])
        Consolidator([Consolidator<br/>LLM background review])
        Scrubber([Scrubber<br/>prompt injection scan])
        Security([Security<br/>invisible unicode, exfiltration])
        Changelog([Changelog<br/>session history])
        Sessions([SessionStore<br/>SQLite FTS5])
        Preferences([Preferences<br/>user profile])
    end

    subgraph Browser["Browser Layer"]
        BrowserSession([BrowserSession<br/>headless/headed])
        Controller([BrowserController<br/>playwright controller])
        OpenBrowser([OpenBrowser<br/>Rust sidecar])
    end

    subgraph Scheduler["Scheduler"]
        Cron([CronManager<br/>APScheduler 24/7])
    end

    subgraph Integrations["Integrations"]
        Discord([Discord Bot])
        Telegram([Telegram Bot])
    end

    subgraph Storage["Storage"]
        DB[(SQLite FTS5)]
    end

    Entry --> Bridge
    CLI --> RPC
    API --> RPC
    TUI --> BridgeRust --> RPC
    RPC --> Loop
    Loop --> Manager
    Manager --> Delegate
    Manager --> Planner
    Planner --> BrowserAgent
    Loop --> Compressor
    Loop --> Guardrails
    BrowserAgent --> Recorder
    Recorder --> TraceToSkill
    TraceToSkill --> SkillLearner
    SkillLearner --> Engine
    Engine --> Executor
    Engine --> Hub
    Engine --> Lock
    Executor --> Healer
    Healer --> BrowserSession
    BrowserSession --> Controller
    Controller --> OpenBrowser
    Loop --> Store
    Store --> Entries
    Store --> Trajectories
    Store --> Sessions
    Store --> Preferences
    Store --> Consolidator
    Consolidator --> Embeddings --> Vector
    Store --> Security
    Store --> Scrubber
    Store --> Changelog
    Scheduler --> Cron
    Cron --> Executor
    Integrations --> Discord
    Integrations --> Telegram
    Storage --> DB

    style Entry fill:#1a1a2e,color:#eee
    style Bridge fill:#16213e,color:#eee
    style AgentCore fill:#0f3460,color:#eee
    style Subagents fill:#533483,color:#eee
    style SkillsSys fill:#533483,color:#eee
    style Mem fill:#e94560,color:#eee
    style Browser fill:#0f3460,color:#eee
    style Scheduler fill:#1a1a2e,color:#eee
    style Integrations fill:#16213e,color:#eee
    style Storage fill:#16213e,color:#eee
```

---

## Quick Start

```bash
# Install
git clone https://github.com/sediman/sediman-browse.git
cd sediman-browse && uv sync

# Set your API key
export OPENAI_API_KEY=sk-...

# Run a task
uv run sediman run "check Apple stock price on Yahoo Finance"

# Or start interactive mode
uv run sediman chat
```

---

## Why Sediman?

| | Sediman | Browser Use | Scrapers | RPA Tools |
|---|---|---|---|---|
| **Real browser** | Yes | Yes | No | Yes |
| **AI-powered** | Yes | Yes | No | No |
| **Learn by showing** | Yes | No | No | No |
| **Self-healing** | Yes | No | No | No |
| **24/7 scheduling** | Yes | No | Manual | Paid add-on |
| **Memory** | Yes | No | No | No |
| **Self-hosted** | Yes | Yes | N/A | Enterprise pricing |

---

## Coming Soon: Sediman Cloud

**Don't want to manage your own server?** We're building Sediman Cloud — fully managed hosting with:

- Instant browser sessions — no infrastructure to maintain
- Always-on automation — 24/7 uptime without your machine running
- Enterprise-grade security — isolated containers, no data leakage
- Dashboard & monitoring — track your automations at a glance
- One-click deploy — turn any skill into a hosted service

Join the waitlist at **[sediman.ai](https://sediman.ai)** and get early access pricing.

---

## License

[Business Source License 1.1 (BSL)](LICENSE).

---

<div align="center">

**If this project helps you, consider giving it a star.**

[Report Bug](https://github.com/sediman/sediman/issues) · [Request Feature](https://github.com/sediman/sediman/issues)

</div>