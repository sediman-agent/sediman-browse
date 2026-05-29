---
name: find-skills
description: "Helps users discover and install skills from GitHub or the Sediman hub when they ask questions like 'how do I do X', 'find a skill for X', or express interest in extending capabilities."
metadata:
  category: meta
  source: bundled
---

# Find Skills

This skill helps you discover and install skills for Sediman.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might have an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows

## How to Help Users Find Skills

### Step 1: Understand What They Need

Identify:
1. The domain (e.g., web scraping, email, social media, finance)
2. The specific task (e.g., post to Twitter, check stock prices)
3. Whether this is common enough that a skill likely exists

### Step 2: Search the Hub

```bash
sediman skill search "<query>"
```

### Step 3: Check GitHub

Many skills live in GitHub repos. Search for common patterns:

- `anthropics/skills` — Anthropic's official skills
- `vercel-labs/agent-skills` — Vercel's skills collection
- `sediman/skills-hub` — Official Sediman hub

Install from any GitHub repo:

```bash
sediman skill install owner/repo@skill-name
```

### Step 4: Present Options to the User

When you find relevant skills, present them with:
1. The skill name and what it does
2. The install command
3. Any usage notes

Example response:

```
I found a skill that might help! The "frontend-design" skill provides
UI/UX design guidelines from Anthropic.

To install it:
sediman skill install anthropics/skills@frontend-design
```

### Step 5: Offer to Install

If the user wants to proceed, install for them:

```bash
sediman skill install <owner/repo@skill> --force
```

## Install Command Reference

| Command | Description |
|---|---|
| `sediman skill install owner/repo@name` | Install from GitHub |
| `sediman skill install name` | Install from Sediman hub |
| `sediman skill search "query"` | Search the hub |
| `sediman skill update --all` | Update all skills |
| `sediman skill outdated` | Check for updates |
| `sediman skill list` | List installed skills |

## When No Skills Are Found

If no relevant skills exist:

1. Acknowledge that no existing skill was found
2. Offer to help with the task directly
3. Suggest recording a new skill:

```bash
sediman skill record <name> --desc "Description of the task"
```
