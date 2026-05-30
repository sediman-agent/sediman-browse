import { describe, it, expect, beforeEach } from "bun:test";
import { handlers, resetState } from "../src/rpc-handlers.js";

const TMP_SOCKET = "/tmp/sediman-test-nonexistent.sock";

describe("rpc-handlers", () => {

  beforeEach(() => {
    resetState();
    process.env.SEDIMAN_PYTHON_SOCKET = TMP_SOCKET;
  });

  // ── System (proxied to Python) ──────────────────────────────────
  it("system.btw fails without API key", async () => {
    const key = process.env.OPENAI_API_KEY;
    delete process.env.OPENAI_API_KEY;
    try {
      await handlers["system.btw"]({ question: "hello" });
      expect.unreachable("should have thrown");
    } catch (e: unknown) {
      expect((e as Error).message).toContain("OPENAI_API_KEY");
    }
    if (key) process.env.OPENAI_API_KEY = key;
  });

  it("system.btw rejects empty question", async () => {
    const result = await handlers["system.btw"]({ question: "" }) as { answer: string };
    expect(result.answer).toBe("");
  });

  it("system.set_soul handles set and reset", async () => {
    const result1 = await handlers["system.set_soul"]({ text: "hello" }) as { content: string };
    expect(result1.content).toBe("hello");
    const result2 = await handlers["system.set_soul"]({ reset: true }) as { content: string };
    expect(typeof result2.content).toBe("string");
  });

  it("system.status fails gracefully without Python", async () => {
    try {
      await handlers["system.status"]({});
    } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  it("system.screenshot fails gracefully without Python", async () => {
    try {
      await handlers["system.screenshot"]({});
    } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  it("system.doctor returns checks object", async () => {
    const result = await handlers["system.doctor"]({}) as { checks: Record<string, unknown> };
    expect(result.checks).toBeDefined();
  });

  // ── Agent (proxied to Python) ────────────────────────────────────
  it("agent.run fails gracefully without Python", async () => {
    try {
      await handlers["agent.run"]({ task: "test" });
    } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  it("agent.run rejects empty task", async () => {
    try {
      await handlers["agent.run"]({ task: "" });
      expect.unreachable("should have thrown");
    } catch (e: unknown) {
      expect((e as Error).message).toContain("task is required");
    }
  });

  // ── Proxied ops fail gracefully without Python ──────────────────
  it("skills.list fails gracefully without Python", async () => {
    try { await handlers["skills.list"]({}); } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  it("hub.browse fails gracefully without Python", async () => {
    try { await handlers["hub.browse"]({}); } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  it("memory.add fails gracefully without Python", async () => {
    try { await handlers["memory.add"]({ target: "memory", content: "test" }); } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  it("model.switch fails gracefully without Python", async () => {
    try { await handlers["model.switch"]({ provider: "openai" }); } catch (e: unknown) {
      expect((e as Error).message).toContain("socket");
    }
  });

  // ── Terminal (native TS) ────────────────────────────────────────
  it("terminal.status returns false by default", async () => {
    const result = await handlers["terminal.status"]({}) as { allowed: boolean };
    expect(result.allowed).toBe(false);
  });

  it("terminal.set enables and disables", async () => {
    await handlers["terminal.set"]({ allowed: true });
    const on = await handlers["terminal.status"]({}) as { allowed: boolean };
    expect(on.allowed).toBe(true);

    await handlers["terminal.set"]({ allowed: false });
    const off = await handlers["terminal.status"]({}) as { allowed: boolean };
    expect(off.allowed).toBe(false);
  });

  // ── Method enumeration ──────────────────────────────────────────
  it("has all expected method handlers", () => {
    const expected = [
      "system.status", "system.screenshot", "system.btw", "system.doctor",
      "system.set_soul",
      "agent.run", "agent.cancel",
      "skills.list", "skills.get", "skills.run", "skills.create", "skills.delete",
      "hub.browse", "hub.search", "hub.info", "hub.install",
      "hub.install_github", "hub.check_update", "hub.update_skill",
      "hub.remove", "hub.get_lock_info",
      "memory.get", "memory.add", "memory.replace", "memory.remove",
      "memory.search", "memory.changelog",
      "sessions.list", "sessions.search", "sessions.save", "sessions.get",
      "schedule.list", "schedule.add", "schedule.remove",
      "model.switch", "model.list_providers",
      "terminal.set", "terminal.status",
      "record.start", "record.stop", "record.active",
    ];
    for (const m of expected) {
      expect(handlers[m]).toBeDefined();
    }
    expect(Object.keys(handlers).length).toBe(expected.length);
  });
});
