import { callPython, callPythonStreaming } from "./proxy.js";

export type NotifyFn = (method: string, params: Record<string, unknown>) => void;

export type RpcHandler = (
  params: Record<string, unknown>,
  notify?: NotifyFn,
) => Promise<unknown>;

let terminalAllowed = false;

export function resetState(): void {
  terminalAllowed = false;
}

export const handlers: Record<string, RpcHandler> = {

  // ── System ─────────────────────────────────────────────────────
  "system.status": async () => callPython("system.status", {}),

  "system.screenshot": async () => callPython("system.screenshot", {}),

  "system.btw": async (params) => {
    const question = String(params.question || "");
    if (!question) return { answer: "" };
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) throw new Error("OPENAI_API_KEY not set");

    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "gpt-4o",
        messages: [
          { role: "system", content: "You are a helpful assistant. Answer concisely." },
          { role: "user", content: question },
        ],
      }),
    });
    if (!res.ok) throw new Error(`OpenAI error: ${res.status}`);

    const data = await res.json() as { choices: Array<{ message: { content: string | null } }> };
    return { answer: data.choices?.[0]?.message?.content || "" };
  },

  "system.doctor": async () => {
    const checks: Record<string, boolean> = {};
    const bins = ["google-chrome", "chromium", "python3", "bun"];
    for (const bin of bins) {
      const { spawnSync } = await import("node:child_process");
      const result = spawnSync("which", [bin]);
      checks[bin] = result.status === 0;
    }
    checks.browser_running = false;
    checks.llm_configured = !!process.env.OPENAI_API_KEY;
    return { checks };
  },

  // ── Agent (proxied to Python) ──────────────────────────────────
  "agent.run": async (params, notify) => {
    const task = String(params.task || "");
    if (!task.trim()) throw new Error("task is required");

    return callPythonStreaming(
      "agent.run",
      { task },
      (method, p) => {
        try { notify?.(method, p); } catch { /* client gone */ }
      },
      { timeout: 600_000 },
    );
  },

  "agent.cancel": async () => callPython("agent.cancel", {}),

  // ── Skills (proxied to Python) ───────────────────────────────────
  "skills.list": async () => callPython("skills.list", {}),
  "skills.get": async (params) => callPython("skills.get", { name: String(params.name || "") }),
  "skills.run": async (params) => callPython("skills.run", params),
  "skills.create": async (params) => callPython("skills.create", params),
  "skills.delete": async (params) => callPython("skills.delete", { name: String(params.name || "") }),

  // ── Hub (proxied to Python) ──────────────────────────────────────
  "hub.browse": async (params) => callPython("hub.browse", { category: params.category ? String(params.category) : undefined }),
  "hub.search": async (params) => callPython("hub.search", { query: String(params.query || "") }),
  "hub.info": async (params) => callPython("hub.info", { name: String(params.name || "") }),
  "hub.install": async (params) => callPython("hub.install", { name: String(params.name || ""), force: Boolean(params.force) }),
  "hub.install_github": async (params) => callPython("hub.install_github", { ref: String(params.ref || ""), force: Boolean(params.force) }),
  "hub.check_update": async (params) => callPython("hub.check_update", { name: String(params.name || "") }),
  "hub.update_skill": async (params) => callPython("hub.update_skill", { name: String(params.name || "") }),
  "hub.remove": async (params) => callPython("hub.remove", { name: String(params.name || "") }),
  "hub.get_lock_info": async (params) => callPython("hub.get_lock_info", { name: String(params.name || "") }),

  // ── Memory (proxied to Python) ────────────────────────────────────
  "memory.get": async () => callPython("memory.get", {}),
  "memory.add": async (params) => callPython("memory.add", { target: String(params.target || "memory"), content: String(params.content || "") }),
  "memory.replace": async (params) => callPython("memory.replace", params),
  "memory.remove": async (params) => callPython("memory.remove", params),
  "memory.search": async (params) => callPython("memory.search", params),
  "memory.changelog": async (params) => callPython("memory.changelog", params),

  // ── Sessions (proxied to Python for SQLite backend) ──────────────
  "sessions.list": async () => callPython("sessions.list", {}),
  "sessions.search": async (params) => callPython("sessions.search", params),
  "sessions.save": async (params) => callPython("sessions.save", params),
  "sessions.get": async (params) => callPython("sessions.get", params),

  // ── Schedule (proxied to Python) ─────────────────────────────────
  "schedule.list": async () => callPython("schedule.list", {}),
  "schedule.add": async (params) => callPython("schedule.add", {
    cron: String(params.cron || ""),
    task: String(params.task || ""),
    skill: params.skill ? String(params.skill) : undefined,
  }),
  "schedule.remove": async (params) => callPython("schedule.remove", { job_id: String(params.job_id || "") }),

  // ── Model (proxied to Python) ──────────────────────────────────
  "model.switch": async (params) => callPython("model.switch", params),
  "model.list_providers": async () => callPython("model.list_providers", {}),

  // ── Terminal (native TS) ────────────────────────────────────────
  "terminal.set": async (params) => {
    terminalAllowed = Boolean(params.allowed);
    process.env.SEDIMAN_TERMINAL_ALLOWED = terminalAllowed ? "1" : "0";
    return { allowed: terminalAllowed };
  },

  "terminal.status": async () => {
    const env = process.env.SEDIMAN_TERMINAL_ALLOWED;
    return { allowed: env ? env === "1" || env === "true" : terminalAllowed };
  },

  // ── Soul (native TS) ────────────────────────────────────────────
  "system.set_soul": async (params) => {
    const { loadSoul, saveSoul, resetSoul } = await import("../../sdk/src/soul.js");
    const text = String(params.text || "");
    const reset = Boolean(params.reset);
    if (reset) {
      resetSoul();
    } else if (text) {
      saveSoul(text);
    }
    return { content: reset ? loadSoul() : (text || loadSoul()) };
  },

  // ── Recording (proxied to Python) ───────────────────────────────
  "record.start": async (params) => callPython("record.start", params),
  "record.stop": async (params) => callPython("record.stop", params),
  "record.active": async () => callPython("record.active", {}),
};
