from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import structlog

logger = structlog.get_logger()


@dataclass
class MonitorEvent:
    line: str
    stream: str
    timestamp: float = 0.0


@dataclass
class MonitorResult:
    exit_code: int | None = None
    output: str = ""
    events: list[MonitorEvent] = field(default_factory=list)
    timed_out: bool = False
    stopped_by_pattern: bool = False
    matched_pattern: str = ""
    elapsed: float = 0.0


async def run_monitor(
    command: str,
    cwd: str | None = None,
    timeout: int = 300,
    stop_pattern: str | None = None,
    on_line: Any | None = None,
) -> MonitorResult:
    timeout = max(1, min(timeout, 600))
    stop_re = re.compile(stop_pattern) if stop_pattern else None
    events: list[MonitorEvent] = []
    all_output: list[str] = []

    try:
        import time
        start = time.monotonic()

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        async def _read_stream(stream: asyncio.StreamReader, name: str) -> None:
            nonlocal events, all_output
            while True:
                try:
                    line_bytes = await asyncio.wait_for(
                        stream.readline(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue

                if not line_bytes:
                    break

                line = line_bytes.decode(errors="replace").rstrip("\n\r")
                timestamp = time.monotonic()
                event = MonitorEvent(line=line, stream=name, timestamp=timestamp)
                events.append(event)
                all_output.append(f"[{name}] {line}")

                if on_line and callable(on_line):
                    try:
                        await on_line(event)
                    except Exception:
                        pass

                if stop_re and stop_re.search(line):
                    logger.info(
                        "monitor_stop_pattern_matched",
                        pattern=stop_pattern,
                        line=line[:100],
                    )
                    return

        try:
            stdout_task = asyncio.create_task(
                _read_stream(proc.stdout, "stdout")
            )
            stderr_task = asyncio.create_task(
                _read_stream(proc.stderr, "stderr")
            )

            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task, proc.wait()),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("monitor_timeout", command=command[:80])
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

            return MonitorResult(
                exit_code=proc.returncode,
                output="\n".join(all_output),
                events=events,
                timed_out=True,
                elapsed=time.monotonic() - start,
            )

        stopped_by_pattern = stop_re is not None and len(events) > 0
        matched = ""
        if stopped_by_pattern and stop_re:
            for event in events:
                if stop_re.search(event.line):
                    matched = event.line[:100]
                    break

        return MonitorResult(
            exit_code=proc.returncode,
            output="\n".join(all_output),
            events=events,
            timed_out=False,
            stopped_by_pattern=stopped_by_pattern,
            matched_pattern=matched,
            elapsed=time.monotonic() - start,
        )

    except FileNotFoundError:
        return MonitorResult(
            exit_code=-1,
            output=f"Command not found: {command.split()[0] if command else 'unknown'}",
            events=[],
        )
    except Exception as e:
        logger.error("monitor_error", error=str(e))
        return MonitorResult(
            exit_code=-1,
            output=f"Monitor failed: {e}",
            events=events,
        )
