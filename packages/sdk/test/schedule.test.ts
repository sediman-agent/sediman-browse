import { describe, test, expect, beforeEach, afterEach } from "bun:test"
import { mkdirSync, rmSync } from "fs"
import { join } from "path"
import { tmpdir } from "os"

const TMP = join(tmpdir(), `sediman-test-schedule-${process.pid}`)

beforeEach(() => { mkdirSync(TMP, { recursive: true }) })
afterEach(() => { rmSync(TMP, { recursive: true, force: true }) })

describe("schedule module", () => {
  test("handleScheduleList returns empty when no cron dir", async () => {
    process.env.SEDIMAN_DATA_DIR = TMP
    const { handleScheduleList } = await import("../src/modules/schedule.js")
    const result = await handleScheduleList()
    expect(result.jobs).toBeInstanceOf(Array)
    expect(result.jobs.length).toBe(0)
  })

  test("handleScheduleAdd creates a job", async () => {
    process.env.SEDIMAN_DATA_DIR = TMP
    const { handleScheduleAdd, handleScheduleList } = await import("../src/modules/schedule.js")

    const result = await handleScheduleAdd({ cron: "0 * * * *", task: "test task" })
    expect(result.job_id).toBeDefined()
    expect(result.job_id.length).toBeGreaterThan(0)

    const { jobs } = await handleScheduleList()
    expect(jobs.length).toBe(1)
    expect(jobs[0].cron).toBe("0 * * * *")
  })

  test("handleScheduleAdd rejects invalid cron", async () => {
    process.env.SEDIMAN_DATA_DIR = TMP
    const { handleScheduleAdd } = await import("../src/modules/schedule.js")
    expect(() => handleScheduleAdd({ cron: "not-cron", task: "x" })).toThrow(/Invalid cron/)
  })

  test("handleScheduleRemove removes a job", async () => {
    process.env.SEDIMAN_DATA_DIR = TMP
    const { handleScheduleAdd, handleScheduleRemove, handleScheduleList } = await import("../src/modules/schedule.js")

    const { job_id } = await handleScheduleAdd({ cron: "0 0 * * *", task: "daily" })
    const { jobs: before } = await handleScheduleList()
    expect(before.length).toBeGreaterThanOrEqual(1)

    await handleScheduleRemove({ job_id })
    const { jobs: after } = await handleScheduleList()
    expect(after.find((j: any) => j.job_id === job_id)).toBeUndefined()
  })
})
