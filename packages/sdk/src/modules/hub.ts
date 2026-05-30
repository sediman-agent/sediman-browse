/**
 * Hub module — browse, search, install skills from the central registry
 * and from arbitrary GitHub repos. Fully self-contained in TS.
 */
import { mkdirSync, readdirSync, unlinkSync, rmdirSync, existsSync, readFileSync, writeFileSync } from "fs"
import { join, resolve } from "path"
import { homedir } from "os"
import { randomUUID } from "crypto"
import { getDataDir } from "../config.js"

function skillsDir(): string { return join(getDataDir(), "skills") }

const DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/sediman/skills-hub/main"
const LOCK_FILE = join(homedir(), ".sediman", "skills-lock.json")

// ── Helpers ─────────────────────────────────────────────────────

function safeName(name: string): string {
  const re = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/
  if (!name || !re.test(name) || name.length > 64) throw new Error(`Invalid skill name: ${JSON.stringify(name)}`)
  return name
}

function skillDirPath(name: string): string {
  safeName(name)
  const resolved = resolve(join(skillsDir(), name))
  const base = resolve(skillsDir())
  if (!resolved.startsWith(base + "/") && resolved !== base) throw new Error(`Path traversal: ${name}`)
  return resolved
}

function atomicWrite(path: string, content: string): void {
  mkdirSync(path.substring(0, path.lastIndexOf("/")), { recursive: true })
  writeFileSync(path, content, "utf-8")
}

function loadSkillFromDir(path: string): Record<string, unknown> | null {
  const jsonPath = join(path, "skill.json")
  if (!existsSync(jsonPath)) return null
  try { return JSON.parse(readFileSync(jsonPath, "utf-8")) }
  catch { return null }
}

// ── Lock file ───────────────────────────────────────────────────

interface LockEntry {
  source: string; sourceType: string; sourceUrl: string; skillPath: string
  skillFolderHash?: string; installedAt?: string; updatedAt?: string
}

function readLock(): Record<string, unknown> {
  try { if (existsSync(LOCK_FILE)) return JSON.parse(readFileSync(LOCK_FILE, "utf-8")) } catch {}
  return { version: 1, skills: {} }
}

function writeLock(data: Record<string, unknown>): void {
  mkdirSync(join(homedir(), ".sediman"), { recursive: true })
  atomicWrite(LOCK_FILE, JSON.stringify(data, null, 2))
}

function lockSet(name: string, entry: LockEntry): void {
  const data = readLock()
  const skills = data.skills as Record<string, unknown> || {}
  skills[name] = entry
  data.skills = skills
  writeLock(data)
}

// ── Validator ────────────────────────────────────────────────────

const NAME_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/
const INJECTION_RE = [/ignore\s+(all\s+)?previous\s+instructions/i, /you\s+are\s+now\s+/i, /system\s*:\s*/i, /<\s*script/i]
const EXFIL_RE = [/(api[_-]?key|token|secret|password|credential)\s*[:=]/i, /(send|post|upload|exfil|fetch)\s+.*to\s+(https?:\/\/|ftp:\/\/)/i]
const DESTRUCT_RE = [/rm\s+-rf\s+\//i, /delete\s+all/i, /drop\s+table/i]

function validate(s: Record<string, unknown>): { valid: boolean; errors: string[]; warnings: string[]; trustLevel: string } {
  const errors: string[] = [], warnings: string[] = []
  const name = String(s.name || ""), description = String(s.description || ""), steps = (s.steps as string[]) || []
  if (!name) errors.push("name is required")
  else if (!NAME_RE.test(name)) errors.push(`invalid name: ${name}`)
  else if (name.length > 64) errors.push("name too long")
  if (!description) errors.push("description is required")
  else if (description.length > 1024) errors.push("description too long")
  if (!steps.length) warnings.push("no steps defined")
  const allText = `${name} ${description} ${steps.join(" ")}`
  for (const r of INJECTION_RE) { if (r.test(allText)) { errors.push("prompt injection detected"); break } }
  for (const r of EXFIL_RE) { if (r.test(allText)) { warnings.push("data exfiltration pattern detected"); break } }
  for (const r of DESTRUCT_RE) { if (r.test(allText)) { errors.push("destructive pattern detected"); break } }
  const trustLevel = errors.length ? "dangerous" : (String(s.source || "") === "verified" ? "trusted" : (warnings.length ? "caution" : "community"))
  return { valid: errors.length === 0, errors, warnings, trustLevel }
}

// ── Install ─────────────────────────────────────────────────────

function installSkill(skill: Record<string, unknown>, source: string, sourceUrl: string): void {
  const dir = skillDirPath(String(skill.name))
  mkdirSync(skillsDir(), { recursive: true }); mkdirSync(dir, { recursive: true })
  const now = new Date().toISOString()
  const skillData = { ...skill, version: (skill.version as number) || 1, created_at: skill.created_at || now, updated_at: now, source: skill.source || "hub" }
  atomicWrite(join(dir, "skill.json"), JSON.stringify(skillData, null, 2))
  writeFileSync(join(dir, "SKILL.md"), `# ${skill.name}\n\n${skill.description}\n`, "utf-8")
  lockSet(String(skill.name), { source, sourceType: source.includes("/") ? "github" : "hub", sourceUrl, skillPath: "SKILL.md", installedAt: now, updatedAt: now })
}

// ── Fetch ───────────────────────────────────────────────────────

async function fetchJson(url: string): Promise<unknown | null> {
  try { const r = await fetch(url, { signal: AbortSignal.timeout(15000) }); if (r.ok) return r.json() } catch {}
  return null
}

async function fetchText(url: string): Promise<string | null> {
  try { const r = await fetch(url, { signal: AbortSignal.timeout(15000) }); if (r.ok) return r.text() } catch {}
  return null
}

function parseRef(ref: string): { owner: string; repo: string; skill: string; branch: string } {
  let repoPart: string, skillName: string
  if (ref.includes("@")) { [repoPart, skillName] = ref.split("@", 2) }
  else { repoPart = ref; skillName = ref.split("/").pop() || ref }
  const parts = repoPart.split("/")
  if (parts.length < 2) throw new Error(`Invalid reference: ${ref}. Expected owner/repo[@skill]`)
  return { owner: parts[0], repo: parts[1], skill: skillName, branch: "main" }
}

function extractStepsFromMd(md: string): string[] {
  return md.split("\n").filter(l => /^\d+\.\s+/.test(l)).map(l => l.replace(/^\d+\.\s+/, ""))
}

// ── Public API ──────────────────────────────────────────────────

export async function handleHubBrowse(params: { category?: string }): Promise<{ skills: Record<string, unknown>[] }> {
  const data = await fetchJson(`${DEFAULT_REGISTRY_URL}/index.json`) as { skills?: Record<string, unknown>[] }
  let skills = (data?.skills || []).filter(s => !params.category || String(s.category || "") === params.category)
  return { skills }
}

export async function handleHubSearch(params: { query: string }): Promise<{ skills: Record<string, unknown>[] }> {
  const data = await fetchJson(`${DEFAULT_REGISTRY_URL}/index.json`) as { skills?: Record<string, unknown>[] }
  const q = params.query.toLowerCase()
  return { skills: (data?.skills || []).filter(s => String(s.name || "").toLowerCase().includes(q) || String(s.description || "").toLowerCase().includes(q)) }
}

export async function handleHubInfo(params: { name: string }): Promise<Record<string, unknown> | null> {
  const s = await fetchJson(`${DEFAULT_REGISTRY_URL}/skills/${encodeURIComponent(params.name)}/index.json`) as Record<string, unknown> | null
  if (!s) return null
  const v = validate(s)
  return { ...s, trust: v.trustLevel, warnings: v.warnings, valid: v.valid }
}

export async function handleHubInstall(params: { name: string; force?: boolean }): Promise<{ installed: string; message: string }> {
  const skill = await fetchJson(`${DEFAULT_REGISTRY_URL}/skills/${encodeURIComponent(params.name)}/index.json`) as Record<string, unknown> | null
  if (!skill) throw new Error(`Skill '${params.name}' not found in hub`)

  const v = validate(skill)
  if (!v.valid) throw new Error(`Validation failed: ${v.errors.join("; ")}`)

  const dir = skillDirPath(params.name)
  if (existsSync(dir)) {
    if (!params.force) throw new Error(`Skill '${params.name}' already exists. Use force=true to overwrite.`)
    for (const f of readdirSync(dir)) unlinkSync(join(dir, f))
    rmdirSync(dir)
  }

  installSkill(skill, `hub:${params.name}`, DEFAULT_REGISTRY_URL)
  return { installed: params.name, message: `Installed ${params.name} (v${(skill.version as number) || 1}, ${v.trustLevel})` }
}

export async function handleHubInstallGithub(params: { ref: string; force?: boolean }): Promise<{ installed: string; message: string }> {
  const { owner, repo, skill: skillName, branch } = parseRef(params.ref)
  const base = `https://raw.githubusercontent.com/${owner}/${repo}/${branch}`

  let skill: Record<string, unknown> | null = null
  const paths = [`skills/${skillName}/skill.json`, `${skillName}/skill.json`, "skill.json"]
  for (const p of paths) {
    const d = await fetchJson(`${base}/${p}`)
    if (d && typeof d === "object" && (d as Record<string, unknown>).name) { skill = d as Record<string, unknown>; break }
  }
  if (!skill) {
    for (const p of paths.map(p => p.replace("skill.json", "SKILL.md"))) {
      const m = await fetchText(`${base}/${p}`)
      if (m) { skill = { name: skillName, description: `Installed from ${owner}/${repo}`, steps: extractStepsFromMd(m) }; break }
    }
  }
  if (!skill) throw new Error(`Skill not found in ${owner}/${repo} (branch: ${branch})`)

  const v = validate(skill)
  if (!v.valid) throw new Error(`Validation failed: ${v.errors.join("; ")}`)

  const dir = skillDirPath(skillName)
  if (existsSync(dir)) {
    if (!params.force) throw new Error(`Skill '${skillName}' already exists. Use force=true to overwrite.`)
    for (const f of readdirSync(dir)) unlinkSync(join(dir, f))
    rmdirSync(dir)
  }

  installSkill(skill, `${owner}/${repo}`, `https://github.com/${owner}/${repo}`)
  return { installed: skillName, message: `Installed ${skillName} from ${owner}/${repo} (v${(skill.version as number) || 1}, ${v.trustLevel})` }
}

export async function handleHubCheckUpdate(params: { name: string }): Promise<{ hasUpdate: boolean; message: string }> {
  const lock = readLock()
  const entry = (lock.skills as Record<string, unknown>)?.[params.name] as LockEntry | undefined
  if (!entry || entry.sourceType !== "github") return { hasUpdate: false, message: "No GitHub source tracked" }
  const { owner, repo, skill: skillName, branch } = parseRef(String(entry.source))
  const remote = await fetchJson(`https://raw.githubusercontent.com/${owner}/${repo}/${branch}/skills/${skillName}/skill.json`) as Record<string, unknown> | null
  if (!remote) return { hasUpdate: false, message: "Could not fetch remote skill" }
  const local = loadSkillFromDir(join(skillsDir(), params.name))
  const rv = (remote.version as number) || 1, lv = (local?.version as number) || 1
  if (rv > lv) return { hasUpdate: true, message: `v${rv} available` }
  return { hasUpdate: false, message: "Up to date" }
}

export async function handleHubUpdateSkill(params: { name: string }): Promise<{ updated: boolean; message: string }> {
  const lock = readLock()
  const entry = (lock.skills as Record<string, unknown>)?.[params.name] as LockEntry | undefined
  if (!entry || entry.sourceType !== "github") return { updated: false, message: `Skill '${params.name}' is not tracked from GitHub` }
  try {
    await handleHubInstallGithub({ ref: String(entry.source), force: true })
    return { updated: true, message: `Updated ${params.name}` }
  } catch (e: unknown) {
    return { updated: false, message: `${params.name}: update failed — ${(e as Error).message}` }
  }
}

export async function handleHubGetLockInfo(params: { name: string }): Promise<Record<string, unknown> | null> {
  const skills = readLock().skills as Record<string, unknown>
  const entry = skills?.[params.name]
  return entry ? entry as Record<string, unknown> : null
}
