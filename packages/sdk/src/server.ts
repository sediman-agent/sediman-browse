#!/usr/bin/env bun
import { unlinkSync, existsSync } from "node:fs"
import { createServer as createTCPServer, type Socket } from "node:net"
import { MAIN_SOCKET } from "./config.js"
import { registerAll, dispatch } from "./transport.js"
import { loadSoul, saveSoul, resetSoul } from "./soul.js"

registerAll({
  "system.btw": async () => {
    throw new Error("BTW requires Python backend")
  },
  "system.doctor": async () => {
    const { execSync } = await import("node:child_process")
    const bins = ["google-chrome", "chromium", "python3", "bun"]
    const binaries = bins.map((binary) => {
      try {
        return { name: binary, path: execSync(`which ${binary}`, { stdio: "pipe" }).toString().trim() }
      } catch {
        return { name: binary, path: "" }
      }
    })
    return { provider_ok: true, browser_ok: false, binaries }
  },
  "soul.load": async () => ({ content: loadSoul() }),
  "soul.save": async (params) => { saveSoul(String(params.content)); return {} },
  "soul.reset": async () => { resetSoul(); return {} },

  // Hub/memory/sessions/schedule/skills are now proxied to Python backend.
  // This standalone server does not support them without Python running.
  "hub.browse": async () => { throw new Error("Hub requires Python backend") },
  "hub.search": async () => { throw new Error("Hub requires Python backend") },
  "hub.info": async () => { throw new Error("Hub requires Python backend") },
  "hub.install": async () => { throw new Error("Hub requires Python backend") },
  "skills.list": async () => { throw new Error("Skills require Python backend") },
  "skills.get": async () => { throw new Error("Skills require Python backend") },
  "skills.create": async () => { throw new Error("Skills require Python backend") },
  "skills.delete": async () => { throw new Error("Skills require Python backend") },
  "schedule.list": async () => { throw new Error("Schedule requires Python backend") },
  "schedule.add": async () => { throw new Error("Schedule requires Python backend") },
  "schedule.remove": async () => { throw new Error("Schedule requires Python backend") },
  "memory.get": async () => { throw new Error("Memory requires Python backend") },
  "memory.add": async () => { throw new Error("Memory requires Python backend") },
  "sessions.list": async () => { throw new Error("Sessions require Python backend") },
})

const SOCKET = process.env.SEDIMAN_MAIN_SOCKET || MAIN_SOCKET

function cleanupSocket(): void {
  try { if (existsSync(SOCKET)) unlinkSync(SOCKET) } catch { /* ignore */ }
}
cleanupSocket()

const server = createTCPServer((stream: Socket) => {
  let buffer = ""
  stream.on("data", (chunk: Buffer) => {
    buffer += chunk.toString()
    const lines = buffer.split("\n")
    buffer = lines.pop() || ""
    for (const line of lines) {
      if (!line.trim()) continue
      processRequest(line.trim(), stream)
    }
  })
  stream.on("error", () => {})
})

async function processRequest(line: string, stream: Socket): Promise<void> {
  let msg: { id?: string | number | null; method?: string; params?: Record<string, unknown> }
  try { msg = JSON.parse(line) }
  catch { writeError(stream, null, -32700, "Parse error"); return }

  if (!msg.method) {
    writeError(stream, msg.id ?? null, -32600, "Invalid Request: no method")
    return
  }

  const writer = (data: string) => { try { stream.write(data) } catch {} }
  const notify = async (method: string, params: Record<string, unknown>) => {
    writer(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n")
  }

  await dispatch(msg.method, msg.params || {}, msg.id ?? null, notify, writer)
}

function writeError(stream: Socket, id: string | number | null, code: number, message: string): void {
  const resp = JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + "\n"
  try { stream.write(resp) } catch {}
}

server.listen(SOCKET, () => {
  console.error(`Sediman TS RPC server listening on ${SOCKET}`)
  console.error(`Python proxy: ${process.env.SEDIMAN_PYTHON_SOCKET || "/tmp/sediman-python.sock"}`)
})

process.on("SIGINT", () => { cleanupSocket(); process.exit(0) })
process.on("SIGTERM", () => { cleanupSocket(); process.exit(0) })
