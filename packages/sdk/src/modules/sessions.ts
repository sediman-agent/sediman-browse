import { readFileSync, existsSync, mkdirSync, writeFileSync } from "fs"
import { join } from "path"
import { randomUUID } from "crypto"
import { getDataDir } from "../config.js"

function sessionsFile(): string { return join(getDataDir(), "sessions", "sessions.jsonl") }

export async function handleSessionsList(_params?: Record<string, unknown>): Promise<{ sessions: Record<string, unknown>[] }> {
  const f = sessionsFile()
  if (!existsSync(f)) return { sessions: [] }
  const lines = readFileSync(f, "utf-8").split("\n").filter(Boolean)
  const sessions = lines.reverse().slice(0, 50).map(l => { try { return JSON.parse(l) } catch { return null } }).filter(Boolean)
  return { sessions }
}

export async function handleSessionSave(params: { task: string; steps?: Record<string, unknown>[]; result?: string }): Promise<{ session_id: string }> {
  const f = sessionsFile()
  mkdirSync(join(getDataDir(), "sessions"), { recursive: true })
  const session = { id: randomUUID().slice(0, 8), task: params.task, steps: params.steps || [], result: params.result || "", created_at: new Date().toISOString() }
  writeFileSync(f, JSON.stringify(session) + "\n", { flag: "a" })
  return { session_id: session.id }
}
