"""
Benchmark Evaluator
====================

Scores benchmark results against ground truth and generates a report.

Usage:
    python scripts/evaluate.py results/benchmark_results_*.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = s.replace("$", "").replace(",", "").replace("%", "")
    s = s.replace("°c", "").replace("°f", "").replace("°", "")
    s = s.replace("\n", " ")
    return s.strip()


def partial_match(extracted: str, expected: str) -> bool:
    ext = normalize_value(extracted)
    exp = normalize_value(expected)
    
    if ext in exp or exp in ext:
        return True
    
    try:
        ext_num = float(ext)
        exp_num = float(exp)
        if abs(ext_num - exp_num) / max(abs(exp_num), 1) < 0.05:
            return True
    except ValueError:
        pass
    
    ext_words = set(ext.split())
    exp_words = set(exp.split())
    if ext_words and exp_words:
        overlap = len(ext_words & exp_words) / len(exp_words)
        if overlap >= 0.5:
            return True
    
    return False


def evaluate_result(result: dict[str, Any]) -> dict[str, Any]:
    extracted = result.get("extracted_values", {})
    expected = result.get("expected_values", {})
    
    exact = 0
    partial = 0
    missing = 0
    
    for key, expected_val in expected.items():
        extracted_val = extracted.get(key, "")
        
        if not extracted_val:
            missing += 1
        elif normalize_value(extracted_val) == normalize_value(expected_val):
            exact += 1
        elif partial_match(extracted_val, expected_val):
            partial += 1
        else:
            missing += 1
    
    total = len(expected) if expected else 1
    score = result.get("score", (exact * 1.0 + partial * 0.5) / total if total > 0 else 0.0)
    success = score >= 0.67
    
    return {
        "task_id": result["task_id"],
        "template": result["template"],
        "variant": result["variant"],
        "mode": result["mode"],
        "success": success,
        "score": score,
        "exact_matches": exact,
        "partial_matches": partial,
        "missing": missing,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate benchmark results")
    parser.add_argument("results", help="Path to results JSONL file")
    parser.add_argument("--output", default=None, help="Output evaluation JSONL path")
    
    args = parser.parse_args()
    
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"File not found: {results_path}")
        exit(1)
    
    evaluated = []
    with open(results_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            result = json.loads(line)
            ev = evaluate_result(result)
            evaluated.append(ev)
    
    # Summary
    ws = [e for e in evaluated if e["mode"] == "with_skill"]
    wos = [e for e in evaluated if e["mode"] == "without_skill"]
    
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    
    if ws:
        success_rate = sum(1 for e in ws if e["success"]) / len(ws)
        avg_score = sum(e["score"] for e in ws) / len(ws)
        print(f"\n📊 WITH SKILL ({len(ws)} runs)")
        print(f"   Success Rate:  {success_rate:.1%}")
        print(f"   Avg Score:     {avg_score:.2f}/1.00")
    
    if wos:
        success_rate = sum(1 for e in wos if e["success"]) / len(wos)
        avg_score = sum(e["score"] for e in wos) / len(wos)
        print(f"\n📊 WITHOUT SKILL ({len(wos)} runs)")
        print(f"   Success Rate:  {success_rate:.1%}")
        print(f"   Avg Score:     {avg_score:.2f}/1.00")
    
    # Per-template breakdown
    templates = sorted(set(e["template"] for e in evaluated))
    print(f"\n📋 PER-TEMPLATE BREAKDOWN")
    print(f"{'Template':<20} {'With Skill':<15} {'Without':<15} {'Delta':<10}")
    print("-" * 65)
    for template in templates:
        ws_t = [e for e in ws if e["template"] == template]
        wos_t = [e for e in wos if e["template"] == template]
        ws_rate = sum(1 for e in ws_t if e["success"]) / len(ws_t) if ws_t else 0
        wos_rate = sum(1 for e in wos_t if e["success"]) / len(wos_t) if wos_t else 0
        delta = ws_rate - wos_rate
        print(f"{template:<20} {ws_rate:<15.1%} {wos_rate:<15.1%} {delta:+.1%}")
    
    print("\n" + "=" * 70)
    
    # Save
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = results_path.with_suffix(".evaluated.jsonl")
    
    with open(output_path, "w") as f:
        for ev in evaluated:
            f.write(json.dumps(ev) + "\n")
    
    print(f"\nDetailed evaluation saved to: {output_path}")


if __name__ == "__main__":
    main()
