import { readFileSync, existsSync, mkdirSync, writeFileSync, renameSync } from "fs"
import { join } from "path"
import { getDataDir, MEMORY_LIMIT, USER_LIMIT } from "../config.js"

function getDir(): string { return join(getDataDir(), "memories") }
function memFile(): string { return join(getDir(), "MEMORY.md") }
function userFile(): string { return join(getDir(), "USER.md") }

function getFile(target: string): string {
  if (target === "user") return userFile()
  return memFile()
}

function getLimit(target: string): number {
  if (target === "user") return USER_LIMIT
  return MEMORY_LIMIT
}

function parseEntries(target: string): string[] {
  const p = getFile(target)
  if (!existsSync(p)) return []
  const content = readFileSync(p, "utf-8").trim()
  return content ? content.split("\n§\n").filter(Boolean) : []
}

function writeEntries(target: string, entries: string[]): void {
  const p = getFile(target)
  mkdirSync(getDir(), { recursive: true })
  writeFileSync(p, entries.join("\n§\n") + "\n", "utf-8")
}

function sanitize(content: string): string {
  if (/ignore\s+(all\s+)?previous/i.test(content)) throw new Error("Content rejected: potential injection")
  if (/<\|im_end\|>|<\|\s*[a-z]+\s*\|>/.test(content)) throw new Error("Content rejected: context boundary markers detected")
  return content
}

export async function handleMemoryGet(): Promise<Record<string, unknown>> {
  const memEntries = parseEntries("memory")
  const userEntries = parseEntries("user")
  const memLimit = getLimit("memory"), userLimit = getLimit("user")
  return {
    entries: {
      memory: memEntries.map(c => ({ content: c, created_at: null })),
      user: userEntries.map(c => ({ content: c, created_at: null })),
    },
    usage: {
      memory: { chars: memEntries.join("").length, limit: memLimit, pct: Math.round((memEntries.join("").length / memLimit) * 100) },
      user: { chars: userEntries.join("").length, limit: userLimit, pct: Math.round((userEntries.join("").length / userLimit) * 100) },
    },
  }
}

export async function handleMemoryAdd(params: { target: string; content: string }): Promise<Record<string, unknown>> {
  sanitize(params.content)
  const entries = parseEntries(params.target)
  const limit = getLimit(params.target)
  if (entries.join("\n§\n").length + params.content.length > limit) {
    throw new Error(`Memory target '${params.target}' is full (limit: ${limit} chars)`)
  }
  if (entries.some(e => e.trim() === params.content.trim())) {
    return { success: true, message: "duplicate (skipped)" }
  }
  entries.push(params.content.trim())
  writeEntries(params.target, entries)
  return { success: true, message: "added" }
}
