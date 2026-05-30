import { readFileSync, writeFileSync, existsSync, unlinkSync, mkdirSync } from "fs"
import { dirname, join } from "path"
import { getDataDir } from "./config.js"

function soulFile(): string { return join(getDataDir(), "SOUL.md") }

const DEFAULT_SOUL = `You are Sediman, a self-improving browser automation agent.

You are pragmatic, concise, and efficient. You complete browser tasks with minimal steps.

Communication style:
- Be brief but thorough
- When reporting results, lead with the answer
- If something fails, explain what went wrong and what you tried
- Proactively suggest improvements when you notice patterns
`

export function loadSoul(): string {
  try {
    if (existsSync(soulFile())) {
      return readFileSync(soulFile(), "utf-8")
    }
  } catch {
    // fall through to default
  }
  return DEFAULT_SOUL
}

export function saveSoul(content: string): void {
  mkdirSync(dirname(soulFile()), { recursive: true })
  writeFileSync(soulFile(), content, "utf-8")
}

export function resetSoul(): void {
  try {
    if (existsSync(soulFile())) {
      unlinkSync(soulFile())
    }
  } catch {
    // ignore
  }
}
