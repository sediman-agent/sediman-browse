from __future__ import annotations

from typing import Any

from sediman.agent.tool_dispatch import ToolResult

from .skills import _TodoStore
from . import get_memory_manager as _get_memory_manager


def _memory_manager():
    return _get_memory_manager()


async def _handle_web_extract(
    url: str | None = None,
    query: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not url or not url.strip():
        return ToolResult(success=False, output="url is required.")

    try:
        from sediman.web.extract import web_extract

        result = await web_extract(url=url.strip(), query=query)
        content = result.get("content", "")
        stats = result.get("stats", {})
        truncated = result.get("truncated", False)
        summarized = result.get("summarized", False)
        title = stats.get("title", "")

        if stats.get("method") == "failed":
            return ToolResult(
                success=False,
                output=content or f"Web extraction failed for {url}",
                data={
                    "url": url,
                    "chars": len(content),
                    "truncated": False,
                    "summarized": False,
                    "stats": stats,
                },
            )

        output = f"Extracted from {url}"
        if title:
            display_title = title if len(title) <= 50 else title[:50] + "..."
            output += f" (title={display_title})"
        output += f" [{len(content)} chars, method={stats.get('method', 'unknown')}]"
        if truncated:
            output += " [truncated]"
        if summarized:
            output += " [summarized]"

        max_output = 50000
        if len(content) > max_output:
            content = content[:max_output] + "\n\n... (output truncated)"

        output += f"\n\n{content}"

        return ToolResult(
            success=True,
            output=output,
            data={
                "url": url,
                "chars": len(result.get("content", "")),
                "truncated": truncated,
                "summarized": summarized,
                "stats": stats,
            },
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Web extraction failed: {e}")


async def _handle_session_search(
    query: str | None = None,
    session_id: str | None = None,
    limit: int = 5,
    **kwargs: Any,
) -> ToolResult:
    try:
        from sediman.memory.sessions import search_sessions, get_recent_sessions, get_session_by_id

        if session_id:
            session = await get_session_by_id(session_id)
            if not session:
                return ToolResult(success=False, output=f"Session {session_id} not found.")
            output = f"Session {session_id}\n"
            output += f"Task: {session.get('task', '')}\n"
            steps = session.get("steps", [])
            if steps:
                output += "Steps:\n"
                for s in steps:
                    output += f"  - {s.get('action', '')}: {s.get('observation', '')}\n"
            output += f"Result: {session.get('result', '')}"
            return ToolResult(
                success=True,
                output=output,
                data={"session": session, "results": [session], "count": 1},
            )

        if query:
            results = await search_sessions(query, limit=limit)
            if not results:
                return ToolResult(
                    success=True,
                    output="No sessions found matching query.",
                    data={"results": [], "count": 0},
                )
            lines = [f"Found {len(results)} session(s):"]
            for r in results:
                lines.append(f"  [{r.get('id', '?')}] {r.get('task', '')[:80]}")
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"results": results, "count": len(results)},
            )

        results = await get_recent_sessions(limit=limit)
        if not results:
            return ToolResult(
                success=True,
                output="No sessions found.",
                data={"results": [], "count": 0},
            )
        lines = ["Recent sessions:"]
        for r in results:
            lines.append(f"  [{r.get('id', '?')}] {r.get('task', '')[:80]}")
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"results": results, "count": len(results)},
        )
    except Exception as e:
        return ToolResult(success=False, output=str(e))


async def _handle_memory(
    action: str | None = None,
    target: str = "memory",
    content: str = "",
    old_entry: str = "",
    **kwargs: Any,
) -> ToolResult:
    mgr = _memory_manager()
    if not mgr:
        return ToolResult(success=False, output="Memory not available.")

    try:
        result_text = await mgr.handle_tool_call(target, {
            "action": action,
            "target": target,
            "content": content,
            "old_entry": old_entry,
        })
        return ToolResult(success=True, output=result_text)
    except Exception as e:
        return ToolResult(success=False, output=str(e))


async def _handle_cronjob(
    action: str | None = None,
    cron: str | None = None,
    task: str | None = None,
    skill_name: str | None = None,
    job_id: str | None = None,
    enabled: bool | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        from sediman.scheduler.cron import CronManager, validate_cron_expr

        cron_mgr = CronManager()

        if action == "create":
            if not cron or not task:
                return ToolResult(success=False, output="Both cron and task are required for create.")
            if not validate_cron_expr(cron):
                return ToolResult(success=False, output=f"Invalid cron expression: {cron}")
            jid = cron_mgr.add_job(cron_expr=cron, task=task, skill_name=skill_name)
            return ToolResult(
                success=True,
                output=f"Created job {jid}: {cron} -> {task}",
                data={"job_id": jid},
            )

        elif action == "list":
            jobs = cron_mgr.list_jobs()
            if not jobs:
                return ToolResult(
                    success=True,
                    output="No scheduled jobs.",
                    data={"jobs": []},
                )
            lines = ["Scheduled jobs:"]
            for j in jobs:
                status = "enabled" if j.get("enabled", True) else "disabled"
                lines.append(f"  [{j['id'][:8]}] ({status}) {j['cron']} -> {j['task'][:80]}")
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"jobs": jobs},
            )

        elif action == "view":
            if not job_id:
                return ToolResult(success=False, output="job_id is required for view.")
            job = cron_mgr.get_job(job_id)
            if not job:
                return ToolResult(success=False, output=f"Job {job_id} not found.")
            output = f"Job {job['id']}\n"
            output += f"  Cron: {job['cron']}\n"
            output += f"  Task: {job['task']}\n"
            output += f"  Enabled: {job.get('enabled', True)}\n"
            output += f"  Last run: {job.get('last_run', 'never')}"
            return ToolResult(success=True, output=output, data={"job": job})

        elif action == "update":
            if not job_id:
                return ToolResult(success=False, output="job_id is required for update.")
            job = cron_mgr.get_job(job_id)
            if not job:
                return ToolResult(success=False, output=f"Job {job_id} not found.")
            if cron is None and task is None and enabled is None:
                return ToolResult(success=False, output="Nothing to update.")
            if cron is not None:
                if not validate_cron_expr(cron):
                    return ToolResult(success=False, output=f"Invalid cron expression: {cron}")
                job["cron"] = cron
            if task is not None:
                job["task"] = task
            if enabled is not None:
                job["enabled"] = enabled
            import json as _json
            cron_mgr._job_path(job["id"]).write_text(_json.dumps(job, indent=2))
            return ToolResult(success=True, output=f"Updated job {job_id}", data={"job": job})

        elif action == "remove":
            if not job_id:
                return ToolResult(success=False, output="job_id is required for remove.")
            removed = cron_mgr.remove_job(job_id)
            if not removed:
                return ToolResult(success=False, output=f"Job {job_id} not found.")
            return ToolResult(success=True, output=f"Removed job {job_id}")

        else:
            return ToolResult(success=False, output=f"Unknown action: {action}")

    except Exception as e:
        return ToolResult(success=False, output=str(e))


async def _handle_clarify(
    question: str | None = None,
    choices: list[str] | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not question or not question.strip():
        return ToolResult(success=False, output="question is required.")
    if choices:
        if len(choices) > 4:
            return ToolResult(success=False, output="Maximum 4 choices allowed.")
        lines = [f"  {i}. {c}" for i, c in enumerate(choices, 1)]
        lines.append(f"  {len(choices) + 1}. Other (type your own answer)")
        choices_text = "\n".join(lines)
        output = f"{question}\n\n{choices_text}\n\nWaiting for user response."
    else:
        output = f"{question}\n\nWaiting for user response."
    return ToolResult(
        success=True,
        output=output,
        data={"question": question, "choices": choices or []},
    )


async def _handle_todo(
    todos: list[dict[str, str]] | None = None,
    merge: bool = False,
    **kwargs: Any,
) -> ToolResult:
    store = _TodoStore.get()

    if todos is None:
        return ToolResult(
            success=True,
            output=store.format_items(),
            data={"todos": store.list_items()},
        )

    for item in todos:
        if "content" not in item or not item["content"].strip():
            return ToolResult(
                success=False,
                output="Each todo item must have a 'content' field.",
            )
        status = item.get("status", "pending")
        if status not in ("pending", "in_progress", "completed"):
            return ToolResult(
                success=False,
                output=f"Invalid status '{status}'. Use: pending, in_progress, or completed.",
            )

    cleaned = [
        {"content": it["content"].strip(), "status": it.get("status", "pending")}
        for it in todos
    ]

    if merge:
        store.merge_items(cleaned)
    else:
        store.set_items(cleaned)

    return ToolResult(
        success=True,
        output=f"Todo list updated.\n{store.format_items()}",
        data={"todos": store.list_items()},
    )


async def _handle_web_search(query: str, **kwargs: Any) -> ToolResult:
    return ToolResult(
        success=True,
        output=f"Web search delegated to browser subagent for: {query}",
        data={"query": query, "delegated": True},
    )


async def _handle_delegate_task(task: str, **kwargs: Any) -> ToolResult:
    return ToolResult(
        success=True,
        output=f"Task delegation queued: {task[:100]}",
        data={"task": task, "delegated": True},
    )


async def _handle_get_schedule_results(
    job_id: str | None = None,
    task_filter: str | None = None,
    limit: int = 5,
    **kwargs: Any,
) -> ToolResult:
    try:
        from sediman.scheduler.cron import CronManager

        cron = CronManager()
        results = cron.get_results(job_id=job_id, task_filter=task_filter, limit=limit)
        if not results:
            return ToolResult(
                success=True,
                output="No scheduled task results found.",
                data={"results": []},
            )
        lines = []
        for r in results:
            lines.append(
                f"[{r['timestamp']}] Job {r['job_id']}: {r.get('task', 'N/A')}\n{r['result'][:500]}"
            )
        output = "\n\n---\n\n".join(lines)
        return ToolResult(
            success=True,
            output=output,
            data={"results": results, "count": len(results)},
        )
    except (KeyError, ValueError, OSError) as e:
        return ToolResult(
            success=False, output=f"Failed to query schedule results: {e}"
        )


async def _handle_list_schedules(**kwargs: Any) -> ToolResult:
    try:
        from sediman.scheduler.cron import CronManager

        cron = CronManager()
        jobs = cron.list_jobs()
        if not jobs:
            return ToolResult(
                success=True, output="No scheduled tasks.", data={"jobs": []}
            )
        lines = []
        for j in jobs:
            status = "enabled" if j.get("enabled", True) else "disabled"
            lines.append(
                f"[{j['id'][:8]}] ({status}) {j['cron']} -> {j['task'][:80]}\n"
                f"  last_run: {j.get('last_run', 'never')} | last_result: {(j.get('last_result') or 'N/A')[:200]}"
            )
        return ToolResult(
            success=True,
            output="\n\n".join(lines),
            data={"jobs": jobs},
        )
    except (KeyError, ValueError, OSError) as e:
        return ToolResult(success=False, output=f"Failed to list schedules: {e}")
