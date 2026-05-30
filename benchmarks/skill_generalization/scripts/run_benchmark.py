"""
Benchmark Runner for Evil Skill Generalization (Browser-Use Direct)
===================================================================

Runs browser-use Agent directly against the evil benchmark pages.
Each task gets a fresh temporary browser profile for clean isolation.

Usage:
    cd benchmarks/skill_generalization
    python mock_server/server.py
    export MINIMAX_API_KEY=...
    python scripts/run_benchmark.py --all --provider minimax --model MiniMax-M2.7
    python scripts/run_benchmark.py --template finance_01 --provider minimax
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from sediman.browser.session import extract_result
from sediman.llm.provider import create_provider
from sediman.skills.engine import SkillEngine


def cleanup_stale_browsers() -> int:
    """Kill any stale Chromium/Chrome processes left from previous benchmark runs."""
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = ' '.join(str(x) for x in cmdline)
            if any(marker in cmdline_str for marker in (
                '--remote-debugging-port=',
                'benchmark-browser-',
                'sediman-browser-',
            )):
                os.kill(proc.info['pid'], signal.SIGKILL)
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            pass
    if killed:
        print(f"Cleaned up {killed} stale browser process(es)")
    return killed


BENCHMARK_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BENCHMARK_DIR / "results"
SKILLS_DIR = BENCHMARK_DIR / "skills"
GROUND_TRUTH_DIR = BENCHMARK_DIR / "mock_server" / "pages"


@dataclass
class BenchmarkResult:
    task_id: str
    template: str
    variant: str
    mode: str
    success: bool = False
    score: float = 0.0
    steps_taken: int = 0
    time_seconds: float = 0.0
    tokens_used: int = 0
    skill_used: bool = False
    skill_name: str | None = None
    error_type: str | None = None
    result_text: str = ""
    extracted_values: dict[str, str] = field(default_factory=dict)
    expected_values: dict[str, str] = field(default_factory=dict)
    progress_resets: int = 0


def load_ground_truth(template: str, variant: str) -> dict[str, str]:
    truth_path = GROUND_TRUTH_DIR / "ground_truth.json"
    if not truth_path.exists():
        return {}
    truth = json.loads(truth_path.read_text())
    key = f"{template}:{variant}"
    return truth.get(key, {})


def extract_values_from_text(text: str, expected_keys: list[str]) -> dict[str, str]:
    extracted = {}
    for key in expected_keys:
        variants = [key, key.replace('_', ' '), key.replace('_', '')]
        for display_key in variants:
            patterns = [
                rf"\*?\*?{re.escape(display_key)}[\s*:]+(\$?[0-9,]+\.?\d*[BKM]?)",
                rf"\*?\*?{re.escape(display_key)}\s+is\s+(\$?[0-9,]+\.?\d*[BKM]?)",
            ]
            for p in patterns:
                m = re.search(p, text, re.IGNORECASE)
                if m:
                    extracted[key] = m.group(1).strip()
                    break
            if key in extracted:
                break
    return extracted


async def run_single_task(
    task_config: dict[str, Any],
    variant: str,
    mode: str,
    server_url: str,
    provider: str,
    model: str | None,
    headless: bool = True,
    max_failures: int = 80,
) -> BenchmarkResult:
    """Run a single benchmark task — creates browser_use Agent directly."""

    from browser_use import Agent, Browser

    template = task_config["template"]
    task_id = task_config["id"]
    expected_keys = task_config["expected_keys"]

    result = BenchmarkResult(
        task_id=task_id,
        template=template,
        variant=variant,
        mode=mode,
    )

    result.expected_values = load_ground_truth(template, variant)

    url = f"{server_url}/{template}_{variant.replace('/', '_SLASH_')}.html"

    task_desc = (
        f"Navigate to {url} and extract the following data: {', '.join(expected_keys)}. "
        f"The page is a multi-layer web form with hidden navigation. "
        f"You must navigate through the compliance layers to find the data table. "
        f"Wrong clicks will reset your progress. Look for hidden or invisible elements."
    )

    if mode == "with_skill":
        engine = SkillEngine(skills_dir=SKILLS_DIR)
        skill_name = f"benchmark-{template.replace('_', '-')}"
        skill_data = engine.read(skill_name)

        if skill_data:
            result.skill_used = True
            result.skill_name = skill_name
            steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(skill_data.get("steps", [])))
            task_desc += (
                f"\n\n=== SKILL GUIDANCE (USE THESE EXACT STEPS) ===\n"
                f"STAY ON {url} — DO NOT navigate to any external website.\n\n"
                f"{steps_text}\n\n"
                f"RULES:\n"
                f"- Only click elements currently VISIBLE on the page\n"
                f"- Hidden elements with opacity:0.005 are real navigation buttons\n"
                f"- Wrong clicks trigger 'Session reset' alert and restart progress\n"
                f"- WAIT for page to update before next action\n"
                f"- Final data table is inside layer6 (id='layer6')\n"
                f"=============================================="
            )
        else:
            result.error_type = "SkillNotFound"
            result.result_text = f"Skill {skill_name} not found"
            return result

    temp_dir = tempfile.mkdtemp(prefix="benchmark-browser-")
    browser = None

    try:
        llm_instance = create_provider(provider, model)
        browser = Browser(
            headless=headless,
            user_data_dir=temp_dir,
            highlight_elements=True,
            keep_alive=True,
        )
        await browser.start()

        agent = Agent(
            task=task_desc,
            llm=llm_instance.get_browser_use_llm(),
            browser=browser,
            use_vision=True,
            max_failures=max_failures,
            max_actions_per_step=5,
            flash_mode=True,
            step_timeout=120,
            llm_timeout=60,
            loop_detection_enabled=True,
        )

        start_time = time.monotonic()
        raw_result = await agent.run()
        result.time_seconds = time.monotonic() - start_time

        result_text = extract_result(raw_result)
        result.result_text = result_text or ""

        actions = []
        if hasattr(raw_result, "all_model_outputs") and raw_result.all_model_outputs is not None:
            for output in raw_result.all_model_outputs:
                if isinstance(output, dict):
                    actions.append(output)
        result.steps_taken = len(actions)

        result.extracted_values = extract_values_from_text(result.result_text, expected_keys)

        def _normalize(val: str) -> str:
            return (val.replace("$", "").replace(",", "").replace("B", "")
                    .replace("K", "").replace("M", "").replace("*", "")
                    .strip().lower())

        if result.expected_values:
            exact = 0
            partial = 0
            missing = 0
            for key, expected_val in result.expected_values.items():
                extracted_val = result.extracted_values.get(key, "")
                if not extracted_val:
                    missing += 1
                elif _normalize(extracted_val) == _normalize(expected_val):
                    exact += 1
                elif (_normalize(expected_val) in _normalize(extracted_val) or
                      _normalize(extracted_val) in _normalize(expected_val)):
                    partial += 1
                else:
                    try:
                        ext_num = float(re.sub(r'[^0-9.]', '', extracted_val))
                        exp_num = float(re.sub(r'[^0-9.]', '', expected_val))
                        if abs(ext_num - exp_num) / max(abs(exp_num), 1) < 0.05:
                            partial += 1
                        else:
                            missing += 1
                    except ValueError:
                        missing += 1
            total = len(expected_keys)
            result.score = (exact * 1.0 + partial * 0.5) / total if total > 0 else 0.0
            result.success = result.score >= 0.67

    except asyncio.CancelledError:
        result.error_type = "Cancelled"
        result.result_text = "Task cancelled (timeout or interrupt)"
    except Exception as e:
        result.error_type = type(e).__name__
        result.result_text = str(e)[:500]
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    return result


async def run_benchmark(
    templates: list[dict[str, Any]],
    server_url: str = "http://localhost:9999",
    provider: str = "openai",
    model: str | None = None,
    with_skill: bool = True,
    without_skill: bool = True,
    headless: bool = True,
    max_failures: int = 80,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []

    for task_config in templates:
        for variant in task_config["variants"]:
            if with_skill:
                print(f"  [WITH SKILL] {task_config['id']} / {variant} ...", end=" ", flush=True)
                r = await run_single_task(
                    task_config, variant, "with_skill",
                    server_url, provider, model, headless, max_failures,
                )
                results.append(r)
                print(f"score={r.score:.2f} time={r.time_seconds:.1f}s")

            if without_skill:
                print(f"  [WITHOUT]    {task_config['id']} / {variant} ...", end=" ", flush=True)
                r = await run_single_task(
                    task_config, variant, "without_skill",
                    server_url, provider, model, headless, max_failures,
                )
                results.append(r)
                print(f"score={r.score:.2f} time={r.time_seconds:.1f}s")

            await asyncio.sleep(1)

    return results


def save_results(results: list[BenchmarkResult], output_path: Path) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in results:
            record = {
                "task_id": r.task_id,
                "template": r.template,
                "variant": r.variant,
                "mode": r.mode,
                "success": r.success,
                "score": r.score,
                "steps_taken": r.steps_taken,
                "time_seconds": r.time_seconds,
                "tokens_used": r.tokens_used,
                "skill_used": r.skill_used,
                "skill_name": r.skill_name,
                "error_type": r.error_type,
                "result_text": r.result_text[:500],
                "extracted_values": r.extracted_values,
                "expected_values": r.expected_values,
            }
            f.write(json.dumps(record) + "\n")
    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Run evil skill generalization benchmark")
    parser.add_argument("--all", action="store_true", help="Run all tasks")
    parser.add_argument("--template", type=str, help="Run specific template")
    parser.add_argument("--variant", type=str, help="Run specific variant")
    parser.add_argument("--with-skill-only", action="store_true")
    parser.add_argument("--without-skill-only", action="store_true")
    parser.add_argument("--server", default="http://localhost:9999")
    parser.add_argument("--provider", default="minimax")
    parser.add_argument("--model", default="MiniMax-M2.7")
    parser.add_argument("--headless", default=True, type=bool)
    parser.add_argument("--max-failures", type=int, default=80, dest="max_failures")

    args = parser.parse_args()

    tasks_path = BENCHMARK_DIR / "tasks.yaml"
    with open(tasks_path) as f:
        config = yaml.safe_load(f)
    templates = config["templates"]

    if args.template:
        templates = [t for t in templates if t["id"] == args.template]

    if args.variant:
        for t in templates:
            if args.variant in t["variants"]:
                t["variants"] = [args.variant]
            else:
                t["variants"] = []
        templates = [t for t in templates if t["variants"]]

    if not templates:
        print("No tasks to run")
        sys.exit(1)

    with_skill = not args.without_skill_only
    without_skill = not args.with_skill_only

    print(f"\n{'=' * 70}")
    print("SEDIMAN EVIL SKILL GENERALIZATION BENCHMARK")
    print(f"{'=' * 70}")
    print(f"Templates:     {len(templates)}")
    print(f"Provider:      {args.provider}")
    print(f"Model:         {args.model}")
    print(f"Server:        {args.server}")
    print(f"Modes:         with_skill={with_skill}, without_skill={without_skill}")
    print(f"Isolation:     temp browser profile per task")
    print(f"{'=' * 70}\n")

    cleanup_stale_browsers()

    if with_skill:
        engine = SkillEngine(skills_dir=SKILLS_DIR)
        available_skills = [f"benchmark-{t['template'].replace('_', '-')}" for t in templates]
        found = sum(1 for s in available_skills if engine.read(s))
        print(f"Skills loaded: {found}/{len(available_skills)}")
        if found == 0:
            print("\nWARNING: No skills found. Run generate_skills.py first!")
            print("  python scripts/generate_skills.py\n")
            if not args.without_skill_only:
                sys.exit(1)

    results = asyncio.run(run_benchmark(
        templates=templates,
        server_url=args.server,
        provider=args.provider,
        model=args.model,
        with_skill=with_skill,
        without_skill=without_skill,
        headless=args.headless,
        max_failures=args.max_failures,
    ))

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = RESULTS_DIR / f"benchmark_results_{timestamp}.jsonl"
    save_results(results, output_path)

    ws = [r for r in results if r.mode == "with_skill"]
    wos = [r for r in results if r.mode == "without_skill"]

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    if ws:
        success_rate = sum(1 for r in ws if r.success) / len(ws)
        avg_score = sum(r.score for r in ws) / len(ws)
        avg_time = sum(r.time_seconds for r in ws) / len(ws)
        print(f"\nWith Skill ({len(ws)} runs):")
        print(f"  Success Rate:  {success_rate:.1%}")
        print(f"  Avg Score:     {avg_score:.2f}/1.00")
        print(f"  Avg Time:      {avg_time:.1f}s")

    if wos:
        success_rate = sum(1 for r in wos if r.success) / len(wos)
        avg_score = sum(r.score for r in wos) / len(wos)
        avg_time = sum(r.time_seconds for r in wos) / len(wos)
        print(f"\nWithout Skill ({len(wos)} runs):")
        print(f"  Success Rate:  {success_rate:.1%}")
        print(f"  Avg Score:     {avg_score:.2f}/1.00")
        print(f"  Avg Time:      {avg_time:.1f}s")

    if ws and wos:
        ws_avg = sum(r.score for r in ws) / len(ws)
        wos_avg = sum(r.score for r in wos) / len(wos)
        delta = ws_avg - wos_avg
        pct = delta / wos_avg * 100 if wos_avg > 0 else (float('inf') if delta > 0 else 0)
        print(f"\nScore Improvement: +{delta:.2f} ({pct:.0f}%)")

    print(f"\nNext: python scripts/evaluate.py {output_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
