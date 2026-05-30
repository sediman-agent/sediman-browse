"""
Generate Benchmark Skills Programmatically
=============================================

Creates 20 skill JSON files directly from the known golden paths in tasks.yaml.
This is the UPPER-BOUND skill condition for the benchmark paper.

No screen recording needed — skills are built from the ground-truth golden path.
This ensures perfect, deterministic skills for the "with_skill" baseline.

Usage:
    python scripts/generate_skills.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))

from sediman.skills.engine import SkillEngine

BENCHMARK_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BENCHMARK_DIR / "skills"


def generate_skill_from_config(task_config: dict) -> dict:
    """Build a skill dict from the task's golden path."""
    
    template = task_config["template"]
    variant = task_config["variants"][0]  # Canonical = first variant
    expected_keys = task_config["expected_keys"]
    golden_path = task_config.get("golden_path", [])
    
    skill_name = f"benchmark-{template.replace('_', '-')}"
    
    # Build steps from golden path, substituting variant
    steps = []
    for step in golden_path:
        formatted = step.replace("{variant}", variant.replace("_", " "))
        steps.append(formatted)
    
    # Add extraction step
    steps.append(f"Extract these fields from the data table: {', '.join(expected_keys)}")
    
    return {
        "skill_name": skill_name,
        "description": f"Navigate the evil maze to extract {', '.join(expected_keys)} from {template} for {variant}",
        "steps": steps,
        "category": "benchmark",
        "when_to_use": f"When asked to extract data from {template} pages with anti-automation layers",
        "pitfalls": [
            "Do NOT click any button with 'opacity:0.005' unless it matches the golden path step",
            "Wrong clicks trigger resetProgress() and reset all progress",
            "Only interact with elements inside the currently visible layer div",
            "The ghost button in cookie grid has empty text, uses addEventListener (no inline onclick) to call showLayer(4)",
            "Accordion headers must be clicked to reveal the data access button",
        ],
        "verification": f"After step 7, a table should be visible with rows containing {', '.join(expected_keys)}",
    }


async def generate_all_skills():
    """Generate all 20 benchmark skills programmatically."""
    
    tasks_path = BENCHMARK_DIR / "tasks.yaml"
    with open(tasks_path) as f:
        config = yaml.safe_load(f)
    
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    engine = SkillEngine(skills_dir=SKILLS_DIR)
    
    success = 0
    for task_config in config["templates"]:
        skill_data = generate_skill_from_config(task_config)
        
        try:
            engine.create(
                name=skill_data["skill_name"],
                description=skill_data["description"],
                steps=skill_data["steps"],
                category=skill_data["category"],
                when_to_use=skill_data.get("when_to_use"),
                pitfalls=skill_data.get("pitfalls", []),
                verification=skill_data.get("verification"),
            )
            success += 1
            print(f"  ✅ {skill_data['skill_name']}")
        except Exception as e:
            print(f"  ❌ {skill_data['skill_name']}: {e}")
    
    print(f"\n✅ Generated {success}/20 skills in {SKILLS_DIR}")
    return success


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark skills programmatically")
    args = parser.parse_args()
    
    import asyncio
    success = asyncio.run(generate_all_skills())
    
    if success == 20:
        print("\nAll skills ready. Next: run_benchmark.py")
    else:
        print(f"\nWarning: only {success}/20 skills generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
