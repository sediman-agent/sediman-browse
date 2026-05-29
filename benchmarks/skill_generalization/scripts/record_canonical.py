"""
Record Canonical Tasks for Benchmark
======================================

Records the screen for each canonical task (first variant of each template),
then converts the recording to a skill via TraceToSkill.

Key fix: Layer-aware navigation — only queries within the currently visible layer.

Usage:
    python scripts/record_canonical.py --all
    python scripts/record_canonical.py --template finance_01
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from sediman.agent.recording_manager import RecordingManager
from sediman.agent.trace_to_skill import TraceToSkill
from sediman.browser.session import BrowserSession
from sediman.llm.provider import create_provider
from sediman.skills.engine import SkillEngine

BENCHMARK_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BENCHMARK_DIR / "skills"
RECORDINGS_DIR = BENCHMARK_DIR / "recordings"


async def navigate_evil_maze(page):
    """Navigate the 7-layer evil maze programmatically.
    
    Golden path (layer-aware — only queries within visible layer):
    1. Click hidden 'Explore' nav in layer0 (opacity 0.005 inline style)
    2. Click 'I Agree — Continue' in layer1
    3. Check invisible consent checkbox in layer2 (parent has 'data processing')
    4. Click ghost button in layer3 (empty text + onclick contains showLayer)
    5. Expand 'Summary for {variant}' accordion in layer5
    6. Click 'View {variant} Data' button in layer5
    7. Extract from table in layer6
    """
    
    # Layer 0: Click hidden nav button
    await asyncio.sleep(1)
    try:
        layer = await page.query_selector("#layer0")
        if layer:
            buttons = await layer.query_selector_all("button")
            for btn in buttons:
                style = await btn.evaluate("el => el.getAttribute('style') || ''")
                if "opacity:0.005" in style or "opacity: 0.005" in style:
                    await btn.click()
                    break
    except Exception:
        pass
    
    await asyncio.sleep(1)
    
    # Layer 1: Accept Terms
    try:
        layer = await page.query_selector("#layer1")
        if layer:
            buttons = await layer.query_selector_all("button")
            for btn in buttons:
                text = await btn.inner_text()
                if text and "agree" in text.lower() and "continue" in text.lower():
                    await btn.click()
                    break
    except Exception:
        pass
    
    await asyncio.sleep(1)
    
    # Layer 2: Check invisible consent
    try:
        layer = await page.query_selector("#layer2")
        if layer:
            checkboxes = await layer.query_selector_all("input[type='checkbox']")
            for cb in checkboxes:
                js = """el => {
                    const p = el.parentElement;
                    return p ? p.innerText : '';
                }"""
                text = await cb.evaluate(js)
                if text and "data processing" in text.lower():
                    await cb.evaluate("el => el.checked = true")
                    break
            # Click Continue button
            buttons = await layer.query_selector_all("button")
            for btn in buttons:
                text = await btn.inner_text()
                if text and "continue" in text.lower():
                    await btn.click()
                    break
    except Exception:
        pass
    
    await asyncio.sleep(1)
    
    # Layer 3: Click ghost button (empty text + onclick has showLayer)
    try:
        layer = await page.query_selector("#layer3")
        if layer:
            buttons = await layer.query_selector_all("button")
            for btn in buttons:
                text = await btn.inner_text()
                onclick = await btn.evaluate("el => el.getAttribute('onclick') || ''")
                if (not text or text.strip() == "") and "showLayer" in onclick:
                    await btn.click()
                    break
    except Exception:
        pass
    
    await asyncio.sleep(1)
    
    # Layer 4: Security check - click hidden submit button
    try:
        layer = await page.query_selector("#layer4")
        if layer:
            buttons = await layer.query_selector_all("button")
            for btn in buttons:
                style = await btn.evaluate("el => el.getAttribute('style') || ''")
                onclick = await btn.evaluate("el => el.getAttribute('onclick') || ''")
                if "opacity:0.005" in style and "showLayer" in onclick:
                    await btn.click()
                    break
    except Exception:
        pass
    
    await asyncio.sleep(1)
    
    # Layer 5: Expand correct accordion and click data access
    try:
        layer = await page.query_selector("#layer5")
        if layer:
            headers = await layer.query_selector_all("div")
            for h in headers:
                text = await h.inner_text()
                if text and "summary" in text.lower():
                    await h.click()
                    await asyncio.sleep(0.5)
                    break
            buttons = await layer.query_selector_all("button")
            for btn in buttons:
                text = await btn.inner_text()
                if text and "data" in text.lower() and "→" in text:
                    await btn.click()
                    break
    except Exception:
        pass
    
    # Layer 6: Wait for data table
    await asyncio.sleep(2)


async def record_canonical(
    template_id: str,
    template_config: dict,
    server_url: str = "http://localhost:9999",
    provider: str = "openai",
    model: str | None = None,
    headless: bool = True,
) -> str | None:
    """Record a canonical task and save as skill."""
    
    template = template_config["template"]
    variant = template_config["variants"][0]  # Canonical = first variant
    skill_name = f"benchmark-{template}"
    
    url = f"{server_url}/{template}_{variant.replace('/', '_SLASH_')}.html"
    
    browser = BrowserSession(headless=headless, stealth=False)
    
    try:
        await browser.start()
        
        manager = RecordingManager()
        session = await manager.start_recording(
            name=skill_name,
            browser=browser,
            description=f"Extract data for {variant} from {template}",
            fps=2,
            max_duration=120,
        )
        
        page = None
        if browser.browser:
            try:
                bw_session = await browser.browser.create_session()
                page = bw_session.agent_current_page
            except Exception:
                pass
        
        if not page:
            print(f"❌ Could not get page for {template_id}")
            return None
        
        await page.goto(url)
        await asyncio.sleep(1)
        
        # Handle alert dialogs (resetProgress triggers them)
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
        
        # Navigate the evil maze
        await navigate_evil_maze(page)
        
        # Stop recording
        recording = await manager.stop_recording(skill_name)
        
        print(f"  📊 {recording.frame_count} frames, {len(recording.actions)} actions, {recording.duration_seconds:.1f}s")
        
        # Convert to skill
        llm = create_provider(provider, model)
        converter = TraceToSkill(llm)
        skill_data = await converter.convert(recording)
        
        if not skill_data:
            print(f"  ❌ TraceToSkill failed for {template_id}")
            return None
        
        # Save skill
        engine = SkillEngine(skills_dir=SKILLS_DIR)
        engine.create(
            name=skill_data.get("skill_name", skill_name),
            description=skill_data.get("description", f"Extract {template} data"),
            steps=skill_data.get("steps", []),
            category="benchmark",
        )
        
        # Save manifest
        manifest = {
            "skill_name": skill_name,
            "template": template,
            "variant": variant,
            "frames": recording.frame_count,
            "actions": len(recording.actions),
            "duration": recording.duration_seconds,
        }
        (RECORDINGS_DIR / f"{skill_name}_manifest.json").write_text(json.dumps(manifest, indent=2))
        
        return skill_name
        
    except Exception as e:
        print(f"❌ Error recording {template_id}: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        await browser.stop()


async def record_all(
    server_url: str = "http://localhost:9999",
    provider: str = "openai",
    model: str | None = None,
) -> dict[str, str | None]:
    """Record all canonical tasks."""
    tasks_path = BENCHMARK_DIR / "tasks.yaml"
    with open(tasks_path) as f:
        config = yaml.safe_load(f)
    
    results: dict[str, str | None] = {}
    
    for task_config in config["templates"]:
        template_id = task_config["id"]
        print(f"\n{'='*60}")
        print(f"Recording {template_id} ({task_config['template']} / {task_config['variants'][0]})")
        print(f"{'='*60}")
        
        skill_name = await record_canonical(
            template_id=template_id,
            template_config=task_config,
            server_url=server_url,
            provider=provider,
            model=model,
        )
        results[template_id] = skill_name
        if skill_name:
            print(f"✅ Saved: {skill_name}")
        else:
            print(f"❌ Failed")
        await asyncio.sleep(2)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Record canonical tasks")
    parser.add_argument("--all", action="store_true", help="Record all templates")
    parser.add_argument("--template", type=str, help="Record specific template")
    parser.add_argument("--server", default="http://localhost:9999")
    parser.add_argument("--provider", default="minimax")
    parser.add_argument("--model", default="MiniMax-Text-01")
    parser.add_argument("--headless", default=True, type=bool)
    
    args = parser.parse_args()
    
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.all:
        results = asyncio.run(record_all(args.server, args.provider, args.model))
        
        print("\n" + "=" * 60)
        print("CANONICAL RECORDING RESULTS")
        print("=" * 60)
        success = 0
        for tid, name in results.items():
            status = "✅" if name else "❌"
            print(f"  {status} {tid}: {name or 'FAILED'}")
            if name:
                success += 1
        print(f"\nTotal: {success}/{len(results)} successful")
        
    elif args.template:
        tasks_path = BENCHMARK_DIR / "tasks.yaml"
        with open(tasks_path) as f:
            config = yaml.safe_load(f)
        
        task_config = next((t for t in config["templates"] if t["id"] == args.template), None)
        if not task_config:
            print(f"Template '{args.template}' not found")
            sys.exit(1)
        
        skill_name = asyncio.run(record_canonical(
            template_id=args.template,
            template_config=task_config,
            server_url=args.server,
            provider=args.provider,
            model=args.model,
            headless=args.headless,
        ))
        
        if skill_name:
            print(f"\n✅ Recorded: {skill_name}")
        else:
            print(f"\n❌ Failed to record {args.template}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
