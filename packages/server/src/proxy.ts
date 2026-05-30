/**
 * Python backend proxy — Unix socket JSON-RPC 2.0 client with connection pooling.
 */
import { connect as netConnect, type Socket } from "node:net"
import { existsSync } from "node:fs"

export const PYTHON_SOCKET = "/tmp/sediman-python.sock"

function getSocketPath(): string {
  return process.env.SEDIMAN_PYTHON_SOCKET || PYTHON_SOCKET
}

export type NotifyFn = (method: string, params: Record<string, unknown>) => void

export interface ProxyOptions {
  timeout?: number
  signal?: AbortSignal
}

function checkSocket(): boolean {
  if (!existsSync(getSocketPath())) return false
  return true
}

// ── Connection pool ─────────────────────────────────────────────

interface PooledSocket {
  socket: Socket
  buf: string
  free: boolean
}

let _pool: PooledSocket[] = []
const MAX_POOL = 3
let _nextId = 1

function getPooledConnection(): Promise<Socket> {
  return new Promise((resolve, reject) => {
    const existing = _pool.find(p => p.free)
    if (existing) {
      existing.free = false
      existing.buf = ""
      resolve(existing.socket)
      return
    }

    if (_pool.length >= MAX_POOL) {
      const oldest = _pool[0]
      oldest.socket.destroy()
      _pool.splice(0, 1)
    }

    const sock = netConnect(getSocketPath())
    sock.on("connect", () => {
      const entry: PooledSocket = { socket: sock, buf: "", free: false }
      _pool.push(entry)
      resolve(sock)
    })
    sock.on("error", (err) => {
      _pool = _pool.filter(p => p.socket !== sock)
      reject(new Error(`Python socket: ${err.message}`))
    })
  })
}

function releaseConnection(sock: Socket): void {
  const entry = _pool.find(p => p.socket === sock)
  if (entry) {
    entry.free = true
    entry.buf = ""
  }
}

function removeConnection(sock: Socket): void {
  _pool = _pool.filter(p => p.socket !== sock)
}

// ── Request helpers ─────────────────────────────────────────────

function sendRequest(sock: Socket, method: string, params: Record<string, unknown>, id: number): void {
  sock.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n")
}

function readResponse(sock: Socket, id: number, onNotify: NotifyFn | null): {
  promise: Promise<unknown>
  done: (result: unknown) => void
  fail: (err: Error) => void
} {
  let resolveResult: (r: unknown) => void = () => {}
  let rejectResult: (e: Error) => void = () => {}
  const promise = new Promise<unknown>((resolve, reject) => {
    resolveResult = resolve
    rejectResult = reject
  })

  const poolEntry = _pool.find(p => p.socket === sock)
  let buf = ""

  const onData = (chunk: Buffer) => {
    buf += chunk.toString()
    const lines = buf.split("\n")
    buf = lines.pop() || ""

    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const msg = JSON.parse(line)
        if (msg.id === undefined || msg.id === null) {
          if (onNotify && msg.method && msg.params) {
            try { onNotify(String(msg.method), msg.params as Record<string, unknown>) } catch {}
          }
          continue
        }
        if (msg.id === id) {
          sock.removeListener("data", onData)
          sock.removeListener("error", onErr)
          sock.removeListener("end", onEnd)
          if (msg.error) {
            rejectResult(new Error(msg.error.message || "Python error"))
          } else {
            resolveResult(msg.result)
          }
          return
        }
      } catch { /* skip malformed */ }
    }
  }

  const onErr = (err: Error) => {
    sock.removeListener("data", onData)
    sock.removeListener("end", onEnd)
    removeConnection(sock)
    rejectResult(new Error(`Python socket: ${err.message}`))
  }

  const onEnd = () => {
    sock.removeListener("data", onData)
    sock.removeListener("error", onErr)
    removeConnection(sock)
    rejectResult(new Error("Python connection closed"))
  }

  sock.on("data", onData)
  sock.on("error", onErr)
  sock.on("end", onEnd)

  return { promise, done: resolveResult, fail: rejectResult }
}

// ── Public API ──────────────────────────────────────────────────

export function callPython(method: string, params: Record<string, unknown> = {}, opts: ProxyOptions = {}): Promise<unknown> {
  return new Promise(async (resolve, reject) => {
    if (!checkSocket()) {
      reject(new Error(`Python socket not found: ${getSocketPath()}`))
      return
    }

    const timeout = opts.timeout ?? 300_000
    let sock: Socket
    try {
      sock = await getPooledConnection()
    } catch (e) {
      reject(e)
      return
    }

    const id = _nextId++
    const timer = setTimeout(() => {
      removeConnection(sock)
      sock.destroy()
      reject(new Error(`Python RPC timeout: ${method} (${timeout}ms)`))
    }, timeout)

    const onAbort = () => {
      clearTimeout(timer)
      removeConnection(sock)
      sock.destroy()
      reject(new Error(`Python RPC aborted: ${method}`))
    }
    if (opts.signal) opts.signal.addEventListener("abort", onAbort, { once: true })

    const { promise: respPromise } = readResponse(sock, id, null)

    try {
      sendRequest(sock, method, params, id)
      const result = await respPromise
      clearTimeout(timer)
      if (opts.signal) opts.signal.removeEventListener("abort", onAbort)
      releaseConnection(sock)
      resolve(result)
    } catch (e) {
      clearTimeout(timer)
      if (opts.signal) opts.signal.removeEventListener("abort", onAbort)
      reject(e)
    }
  })
}

export function callPythonStreaming(method: string, params: Record<string, unknown>, onNotify: NotifyFn, opts: ProxyOptions = {}): Promise<unknown> {
  return new Promise(async (resolve, reject) => {
    if (!checkSocket()) {
      reject(new Error(`Python socket not found: ${getSocketPath()}`))
      return
    }

    const sock = netConnect(getSocketPath())

    const timeout = opts.timeout ?? 300_000
    const timer = setTimeout(() => {
      sock.destroy()
      reject(new Error(`Python timeout: ${method}`))
    }, timeout)

    const onAbort = () => {
      clearTimeout(timer)
      sock.destroy()
      reject(new Error(`Python RPC aborted: ${method}`))
    }
    if (opts.signal) opts.signal.addEventListener("abort", onAbort, { once: true })

    let done = false
    let buf = ""

    sock.on("connect", () => {
      sock.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) + "\n")
    })

    sock.on("data", (chunk: Buffer) => {
      if (done) return
      buf += chunk.toString()
      const lines = buf.split("\n")
      buf = lines.pop() || ""
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const msg = JSON.parse(line)
          if (msg.id === undefined || msg.id === null) {
            if (msg.method && msg.params) {
              try { onNotify(String(msg.method), msg.params as Record<string, unknown>) } catch {}
            }
            continue
          }
          done = true
          clearTimeout(timer)
          if (opts.signal) opts.signal.removeEventListener("abort", onAbort)
          sock.end()
          msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
          return
        } catch { /* skip */ }
      }
    })

    sock.on("error", (err: Error) => {
      if (!done) { done = true; clearTimeout(timer); if (opts.signal) opts.signal.removeEventListener("abort", onAbort); reject(new Error(`Python socket: ${err.message}`)) }
    })
    sock.on("end", () => {
      if (!done) { done = true; clearTimeout(timer); if (opts.signal) opts.signal.removeEventListener("abort", onAbort); reject(new Error("Python connection closed")) }
    })
  })
}
