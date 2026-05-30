import { readdirSync, readFileSync, existsSync, mkdirSync, writeFileSync, unlinkSync, rmdirSync } from "fs"
import { join, resolve } from "path"
import { getDataDir } from "../config.js"

function skillsDir(): string { return join(getDataDir(), "skills") }

const SAFE_NAME_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/

function validateName(name: string): void {
  if (!name || !SAFE_NAME_RE.test(name) || name.length > 64) throw new Error(`Invalid skill name: ${JSON.stringify(name)}`)
}

function skillPath(name: string): string {
  validateName(name)
  const resolved = resolve(join(skillsDir(), name))
  const base = resolve(skillsDir())
  if (!resolved.startsWith(base + "/") && resolved !== base) throw new Error(`Path traversal: ${name}`)
  return resolved
}

function atomicWrite(path: string, content: string): void {
  const dir = path.substring(0, path.lastIndexOf("/"))
  mkdirSync(dir, { recursive: true })
  writeFileSync(path, content, "utf-8")
}

function loadSkill(dir: string): Record<string, unknown> | null {
  const jsonPath = join(dir, "skill.json")
  if (!existsSync(jsonPath)) return null
  try { return JSON.parse(readFileSync(jsonPath, "utf-8")) }
  catch { return null }
}

export interface CreateSkillParams {
  name: string; description: string; steps: string[]; category?: string
  when_to_use?: string; pitfalls?: string[]; verification?: string
}

export async function handleSkillsList(): Promise<{ skills: Record<string, unknown>[] }> {
  if (!existsSync(skillsDir())) return { skills: [] }
  const skills: Record<string, unknown>[] = []
  const entries = readdirSync(skillsDir(), { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const data = loadSkill(join(skillsDir(), entry.name))
    if (data) skills.push({ name: data.name, description: data.description, category: data.category || null, version: data.version || 1, use_count: data.use_count || 0, last_used_at: data.last_used_at || null, updated_at: data.updated_at || null })
  }
  return { skills }
}

export async function handleSkillsGet(params: { name: string }): Promise<Record<string, unknown> | null> {
  const dir = skillPath(params.name)
  return existsSync(dir) ? loadSkill(dir) : null
}

export async function handleSkillsCreate(params: CreateSkillParams): Promise<Record<string, unknown>> {
  mkdirSync(skillsDir(), { recursive: true })
  const dir = skillPath(params.name)
  mkdirSync(dir, { recursive: true })
  const now = new Date().toISOString()
  const skill = { name: params.name, description: params.description, steps: params.steps, category: params.category || "general", version: 1, created_at: now, updated_at: now, when_to_use: params.when_to_use || null, pitfalls: params.pitfalls || [], verification: params.verification || null, structured_steps: [], variables: [], use_count: 0, last_used_at: null, source: "local" }
  atomicWrite(join(dir, "skill.json"), JSON.stringify(skill, null, 2))
  atomicWrite(join(dir, "SKILL.md"), `# ${params.name}\n\n${params.description}\n`)
  return skill
}

export async function handleSkillsDelete(params: { name: string }): Promise<{ deleted: string }> {
  const dir = skillPath(params.name)
  if (!existsSync(dir)) return { deleted: "" }
  for (const f of readdirSync(dir)) unlinkSync(join(dir, f))
  rmdirSync(dir)
  return { deleted: params.name }
}
