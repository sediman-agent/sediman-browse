#!/usr/bin/env bash
#
# Sediman API Usage Examples
#
# Start the server first:
#   sediman serve --port 8000
#
set -euo pipefail

BASE="http://localhost:8000"

# ── Health / Status ──────────────────────────────────────────────────────────

echo "=== Server Status ==="
curl -s "$BASE/api/status" | python3 -m json.tool

# ── Create a Task ────────────────────────────────────────────────────────────

echo -e "\n=== Create Task ==="
RESPONSE=$(curl -s -X POST "$BASE/api/task" \
  -H "Content-Type: application/json" \
  -d '{"task": "Go to https://news.ycombinator.com and list the top 5 headlines"}')
echo "$RESPONSE" | python3 -m json.tool

TASK_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
echo "Task ID: $TASK_ID"

# ── Check Task Status ────────────────────────────────────────────────────────

echo -e "\n=== Task Status (poll until done) ==="
for i in $(seq 1 30); do
  STATUS=$(curl -s "$BASE/api/task/$TASK_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  [$i] status=$STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 5
done

echo -e "\n=== Final Result ==="
curl -s "$BASE/api/task/$TASK_ID" | python3 -m json.tool

# ── List Skills ──────────────────────────────────────────────────────────────

echo -e "\n=== List Skills ==="
curl -s "$BASE/api/skills" | python3 -m json.tool

# ── Get a Specific Skill ────────────────────────────────────────────────────

echo -e "\n=== Get Skill: stock-checker ==="
curl -s "$BASE/api/skills/stock-checker" | python3 -m json.tool

# ── Run a Skill ──────────────────────────────────────────────────────────────

echo -e "\n=== Run Skill ==="
curl -s -X POST "$BASE/api/skills/stock-checker/run" \
  -H "Content-Type: application/json" \
  -d '{"name": "stock-checker"}' | python3 -m json.tool

# ── Delete a Skill ───────────────────────────────────────────────────────────

echo -e "\n=== Delete Skill ==="
curl -s -X DELETE "$BASE/api/skills/my-old-skill" | python3 -m json.tool

# ── Schedule a Cron Job ──────────────────────────────────────────────────────

echo -e "\n=== Schedule Cron Job ==="
curl -s -X POST "$BASE/api/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "cron": "0 9 * * 1-5",
    "task": "Check AAPL stock price on Yahoo Finance and report",
    "skill": "stock-checker"
  }' | python3 -m json.tool

# ── List Scheduled Jobs ──────────────────────────────────────────────────────

echo -e "\n=== List Schedule ==="
curl -s "$BASE/api/schedule" | python3 -m json.tool

# ── Remove a Scheduled Job ───────────────────────────────────────────────────

echo -e "\n=== Remove Scheduled Job ==="
JOB_ID="your-job-id-here"
curl -s -X DELETE "$BASE/api/schedule/$JOB_ID" | python3 -m json.tool

# ── Browse the Skill Hub ────────────────────────────────────────────────────

echo -e "\n=== Hub Browse ==="
curl -s "$BASE/api/hub/browse" | python3 -m json.tool

echo -e "\n=== Hub Search ==="
curl -s "$BASE/api/hub/search?q=stock" | python3 -m json.tool

# ── Install a Skill from the Hub ────────────────────────────────────────────

echo -e "\n=== Hub Install ==="
curl -s -X POST "$BASE/api/hub/install" \
  -H "Content-Type: application/json" \
  -d '{"name": "weather-checker"}' | python3 -m json.tool

# ── Memory ───────────────────────────────────────────────────────────────────

echo -e "\n=== Memory ==="
curl -s "$BASE/api/memory" | python3 -m json.tool

# ── Sessions ─────────────────────────────────────────────────────────────────

echo -e "\n=== Recent Sessions ==="
curl -s "$BASE/api/sessions" | python3 -m json.tool

# ── Screenshot ───────────────────────────────────────────────────────────────

echo -e "\n=== Take Screenshot ==="
curl -s "$BASE/api/screenshot" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'screenshot' in data:
    print(f'Screenshot received ({len(data[\" screenshot\"])} chars base64)')
else:
    print(data)
"

# ── Recording ────────────────────────────────────────────────────────────────

echo -e "\n=== Start Recording ==="
curl -s -X POST "$BASE/api/skills/record/start" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-new-skill",
    "description": "Example recording",
    "fps": 3,
    "max_duration": 60
  }' | python3 -m json.tool

echo -e "\n=== Active Recordings ==="
curl -s "$BASE/api/skills/record/active" | python3 -m json.tool

echo -e "\n=== Stop Recording ==="
SESSION_ID="your-session-id-here"
curl -s -X POST "$BASE/api/skills/record/$SESSION_ID/stop" | python3 -m json.tool
