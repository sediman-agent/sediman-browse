import { describe, test, expect, beforeEach, afterEach, mock } from "bun:test"
import { mkdirSync, rmSync, existsSync, writeFileSync, readFileSync } from "fs"
import { join } from "path"
import { tmpdir } from "os"

describe("config", () => {
  test("exports getDataDir as function", async () => {
    const mod = await import("../src/config.js")
    expect(typeof mod.getDataDir).toBe("function")
    expect(typeof mod.getDataDir()).toBe("string")
  })

  test("exports all path functions", async () => {
    const mod = await import("../src/config.js")
    for (const key of ["SKILLS_DIR", "MEMORY_DIR", "SESSIONS_DIR", "CRON_DIR", "SOUL_FILE"]) {
      expect(typeof (mod as Record<string, unknown>)[key]).toBe("function")
    }
  })

  test("exports numeric limits", async () => {
    const mod = await import("../src/config.js")
    expect(typeof mod.MEMORY_LIMIT).toBe("number")
    expect(mod.MEMORY_LIMIT).toBeGreaterThan(0)
    expect(typeof mod.MAX_TASK_LENGTH).toBe("number")
  })
})
