import { Hono } from "hono"
import { callPython } from "../proxy.js"

const api = new Hono()

// ── Task Queue ─────────────────────────────────────────────────
const taskStore = new Map<string, Record<string, unknown>>()

api.post("/task", async (c) => {
  const body = await c.req.json<{ task: string }>()
  if (!body.task?.trim()) {
    return c.json({ error: { code: "VALIDATION_ERROR", message: "task is required" } }, 400)
  }
  const taskId = crypto.randomUUID()
  const entry: Record<string, unknown> = {
    task_id: taskId, task: body.task, status: "queued",
    created_at: Date.now() / 1000, started_at: null, completed_at: null,
    result: null, error: null,
  }
  taskStore.set(taskId, entry)

  callPython("agent.run", { task: body.task }, { timeout: 600_000 })
    .then((r) => { entry.status = "completed"; entry.completed_at = Date.now() / 1000; entry.result = r })
    .catch((e: Error) => { entry.status = "failed"; entry.completed_at = Date.now() / 1000; entry.error = { code: "EXECUTION_ERROR", message: e.message } })

  return c.json({ task_id: taskId, status: "queued" }, 202)
})

api.get("/task/:taskId", (c) => {
  const entry = taskStore.get(c.req.param("taskId"))
  if (!entry) return c.json({ error: { code: "NOT_FOUND", message: "Task not found" } }, 404)
  return c.json(entry)
})

// ── Skills (proxied to Python) ─────────────────────────────────
api.get("/skills", async (c) => c.json(await callPython("skills.list", {})))
api.get("/skills/:name", async (c) => {
  try { return c.json(await callPython("skills.get", { name: c.req.param("name") })) }
  catch { return c.json({ error: { code: "NOT_FOUND", message: "Skill not found" } }, 404) }
})
api.post("/skills", async (c) => {
  try { return c.json(await callPython("skills.create", await c.req.json()), 201) }
  catch (e: unknown) { return c.json({ error: { code: "CREATE_ERROR", message: String(e) } }, 400) }
})
api.post("/skills/:name/run", async (c) => {
  try { return c.json(await callPython("skills.run", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "EXECUTION_ERROR", message: String(e) } }, 500) }
})
api.delete("/skills/:name", async (c) => {
  try { return c.json(await callPython("skills.delete", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "DELETE_ERROR", message: String(e) } }, 500) }
})

// ── Recording (proxied) ────────────────────────────────────────
api.post("/skills/record/start", async (c) => {
  try { return c.json(await callPython("record.start", await c.req.json()), 201) }
  catch (e: unknown) { return c.json({ error: { code: "RECORD_START_FAILED", message: String(e) } }, 500) }
})
api.post("/skills/record/:id/stop", async (c) => {
  try { return c.json(await callPython("record.stop", { session_id: c.req.param("id") })) }
  catch (e: unknown) { return c.json({ error: { code: "RECORD_STOP_FAILED", message: String(e) } }, 500) }
})
api.get("/skills/record/active", async (c) => {
  try { return c.json(await callPython("record.active", {})) }
  catch (e: unknown) { return c.json({ error: { code: "QUERY_FAILED", message: String(e) } }, 500) }
})

// ── Hub (proxied to Python) ────────────────────────────────────
api.get("/hub/browse", async (c) => {
  try { return c.json(await callPython("hub.browse", { category: c.req.query("category") || undefined })) }
  catch (e: unknown) { return c.json({ error: { code: "BROWSE_ERROR", message: String(e) } }, 500) }
})
api.get("/hub/search", async (c) => {
  const q = c.req.query("q")
  if (!q) return c.json({ error: { code: "VALIDATION_ERROR", message: "query param 'q' required" } }, 400)
  try { return c.json(await callPython("hub.search", { query: q })) }
  catch (e: unknown) { return c.json({ error: { code: "SEARCH_ERROR", message: String(e) } }, 500) }
})
api.get("/hub/:name", async (c) => {
  try { return c.json(await callPython("hub.info", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "NOT_FOUND", message: String(e) } }, 404) }
})
api.post("/hub/install", async (c) => {
  try { return c.json(await callPython("hub.install", await c.req.json())) }
  catch (e: unknown) { return c.json({ error: { code: "INSTALL_ERROR", message: String(e) } }, 500) }
})
api.post("/hub/install-github", async (c) => {
  try { return c.json(await callPython("hub.install_github", await c.req.json())) }
  catch (e: unknown) { return c.json({ error: { code: "INSTALL_ERROR", message: String(e) } }, 500) }
})
api.get("/hub/check-update/:name", async (c) => {
  try { return c.json(await callPython("hub.check_update", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "CHECK_ERROR", message: String(e) } }, 500) }
})
api.post("/hub/update/:name", async (c) => {
  try { return c.json(await callPython("hub.update_skill", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "UPDATE_ERROR", message: String(e) } }, 500) }
})
api.delete("/hub/:name", async (c) => {
  try { return c.json(await callPython("hub.remove", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "REMOVE_ERROR", message: String(e) } }, 500) }
})
api.get("/hub/lock/:name", async (c) => {
  try { return c.json(await callPython("hub.get_lock_info", { name: c.req.param("name") })) }
  catch (e: unknown) { return c.json({ error: { code: "NOT_FOUND", message: String(e) } }, 404) }
})

// ── Schedule (proxied to Python) ────────────────────────────────
api.get("/schedule", async (c) => {
  try { return c.json(await callPython("schedule.list", {})) }
  catch (e: unknown) { return c.json({ error: { code: "LIST_ERROR", message: String(e) } }, 500) }
})
api.post("/schedule", async (c) => {
  try { return c.json(await callPython("schedule.add", await c.req.json()), 201) }
  catch (e: unknown) { return c.json({ error: { code: "VALIDATION_ERROR", message: String(e) } }, 400) }
})
api.get("/schedule/:jobId", async (c) => {
  try {
    const jobs = await callPython("schedule.list", {}) as Array<Record<string, unknown>>
    const job = jobs?.find(j => j.id === c.req.param("jobId"))
    return job ? c.json(job) : c.json({ error: { code: "NOT_FOUND", message: "Job not found" } }, 404)
  } catch (e: unknown) {
    return c.json({ error: { code: "LIST_ERROR", message: String(e) } }, 500)
  }
})
api.delete("/schedule/:jobId", async (c) => {
  try { return c.json(await callPython("schedule.remove", { job_id: c.req.param("jobId") })) }
  catch (e: unknown) { return c.json({ error: { code: "REMOVE_ERROR", message: String(e) } }, 500) }
})

// ── Memory (writes proxied, reads direct for speed) ─────────────
api.get("/memory", async (c) => {
  try { return c.json(await callPython("memory.get", {})) }
  catch (e: unknown) { return c.json({ error: { code: "MEMORY_ERROR", message: String(e) } }, 500) }
})
api.post("/memory", async (c) => {
  try { return c.json(await callPython("memory.add", await c.req.json()), 201) }
  catch (e: unknown) { return c.json({ error: { code: "MEMORY_ERROR", message: String(e) } }, 400) }
})

// ── Sessions (proxied to Python for SQLite backend) ─────────────
api.get("/sessions", async (c) => {
  try { return c.json(await callPython("sessions.list", {})) }
  catch (e: unknown) { return c.json({ error: { code: "SESSION_ERROR", message: String(e) } }, 500) }
})
api.post("/sessions", async (c) => {
  try { return c.json(await callPython("sessions.save", await c.req.json()), 201) }
  catch (e: unknown) { return c.json({ error: { code: "SESSION_ERROR", message: String(e) } }, 400) }
})
api.get("/sessions/:id", async (c) => {
  try { return c.json(await callPython("sessions.get", { session_id: c.req.param("id") })) }
  catch (e: unknown) { return c.json({ error: { code: "NOT_FOUND", message: String(e) } }, 404) }
})

// ── Screenshot (proxied) ──────────────────────────────────────
api.get("/screenshot", async (c) => {
  try { return c.json(await callPython("system.screenshot", {})) }
  catch (e: unknown) { return c.json({ error: { code: "NO_BROWSER", message: String(e) } }, 503) }
})

// ── Status (blended) ──────────────────────────────────────────
api.get("/status", async (c) => {
  let py: Record<string, unknown> = {}
  try { py = await callPython("system.status", {}) as Record<string, unknown> } catch {
    // Python backend not available — partial status
  }

  let currentTask: Record<string, unknown> | null = null
  let lastResult: Record<string, unknown> | null = null
  for (const entry of taskStore.values()) {
    if (entry.status === "queued" || entry.status === "running") {
      currentTask = { task_id: entry.task_id, task: entry.task, status: entry.status }
    }
  }
  const all = Array.from(taskStore.values()).reverse()
  for (const entry of all) {
    if (entry.status === "completed" && entry.result) {
      const r = entry.result as Record<string, unknown>
      lastResult = { task_id: entry.task_id, task: entry.task, result: String(r.result || "").slice(0, 200) }
      break
    }
  }

  return c.json({
    server: "sediman-ts", version: "0.1.0",
    python_available: Object.keys(py).length > 0,
    browser_open: py.browser_open || false,
    model: py.model || process.env.SEDIMAN_MODEL || null,
    provider: py.provider || process.env.SEDIMAN_PROVIDER || "openai",
    conversation_messages: py.conversation_messages || 0,
    current_task: currentTask,
    scheduler: py.scheduler || { active_jobs: 0, total_jobs: 0 },
    last_result: lastResult,
    queue_size: taskStore.size,
  })
})

export { api }
