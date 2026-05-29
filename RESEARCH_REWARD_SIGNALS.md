# Reward Signals & Progress Estimation for Browser Automation Agents

Research survey of techniques for evaluating progress and providing reward signals to browser automation agents **at inference time, without RL training or model fine-tuning**. Applicable to Sediman's prompt-based architecture.

---

## Table of Contents
1. [LLM-as-Judge Reward Models](#1-llm-as-judge-reward-models)
2. [Heuristic Reward Signals for Web Tasks](#2-heuristic-reward-signals-for-web-tasks)
3. [Process Reward Models at Inference Time](#3-process-reward-models-at-inference-time)
4. [Milestone/Subgoal-Based Rewards](#4-milestonesubgoal-based-rewards)
5. [Outcome-Supervised Reward Models (ORM)](#5-outcome-supervised-reward-models-orm)
6. [Practical Implementation Patterns for Sediman](#6-practical-implementation-patterns-for-sediman)

---

## 1. LLM-as-Judge Reward Models

### 1.1 Core Technique

Use an LLM (same or different model) to evaluate the agent's trajectory and current state against the task goal. The judge outputs a score or binary verdict.

**Reference**: WebRL (Qi et al., 2024, arXiv:2411.02337, ICLR 2025) trains a dedicated ORM that takes as input:
- The task instruction `I`
- The history of actions taken
- The HTML of the **final state only** (to fit in context window)

The model outputs "YES" or "NO" by comparing token probabilities. This is effectively an LLM-as-judge pattern, but with a fine-tuned model.

**For Sediman (no fine-tuning)**: Use the same LLM with a structured evaluation prompt.

### 1.2 Implementation: Zero-Shot LLM Judge Prompt

```
You are evaluating whether a web automation task has been completed.

TASK: {task_description}

ACTIONS TAKEN:
{action_history}

CURRENT PAGE STATE:
{accessibility_tree_or_dom_summary}

Evaluate:
1. Has the task goal been achieved? (YES/NO)
2. What percentage of the task is complete? (0-100%)
3. What remains to be done? (brief description)
4. Score: float 0.0-1.0

Output as JSON: {"completed": bool, "progress_pct": int, "remaining": str, "score": float}
```

### 1.3 Key Design Decisions from Literature

**What to include in the judge's context:**
- WebRL: instruction + action history + final-state HTML only (drops intermediate HTML)
- MiRA (Wang et al., 2026, arXiv:2603.19685): uses Gemini-2.5-Pro as a subgoal checker, same prompt format as final goal checker
- OpenComputer (Wei et al., 2026, arXiv:2605.19769): found hard-coded verifiers align more closely with human judgment than LLM-as-judge for fine-grained application state

**Critical finding**: LLM judges are noisy for partial progress. They're reliable for final outcome evaluation (YES/NO) but unreliable for intermediate progress scoring. MiRA addresses this by using **hard milestones** (binary achieved/not-achieved) rather than soft scores.

### 1.4 SRaR: Step-wise Rubrics (Xie et al., 2026, arXiv:2605.17291)

Even without training, the rubric-based approach is adaptable:
1. Define evaluation criteria (rubrics) for the task
2. Have the LLM judge attribute each criterion to a specific step
3. Score each step independently

**Adaptation for Sediman**: Auto-generate rubrics from the task description:

```
Given the web task: "{task_description}"
Generate 3-5 verifiable checkpoints that indicate progress.
For each checkpoint, specify what DOM state or URL pattern indicates completion.

Output as JSON array of: {"checkpoint": str, "verification_method": str, "weight": float}
```

---

## 2. Heuristic Reward Signals for Web Tasks

### 2.1 URL Progress Signal

Track URL changes relative to the expected target URL structure.

```python
def url_progress_score(current_url: str, task_hint_urls: list[str]) -> float:
    """
    Score based on URL path similarity.
    Returns 0.0-1.0 based on path component overlap.
    """
    current_parts = set(urlparse(current_url).path.strip("/").split("/"))
    max_overlap = 0.0
    for hint_url in task_hint_urls:
        hint_parts = set(urlparse(hint_url).path.strip("/").split("/"))
        if not hint_parts:
            continue
        overlap = len(current_parts & hint_parts) / len(hint_parts)
        max_overlap = max(max_overlap, overlap)
    return max_overlap
```

**Limitations**: URL progress is domain-specific and unreliable. Many tasks don't have predictable URL patterns (SPAs, dynamic routing). Use as a **weak auxiliary signal** only.

### 2.2 DOM State Matching

Check for the presence of expected elements on the page.

```python
def dom_element_score(accessibility_tree: str, expected_elements: list[str]) -> float:
    """
    Check what fraction of expected elements are present in the current DOM.
    expected_elements: list of text patterns or aria labels to look for.
    """
    found = sum(1 for elem in expected_elements if elem.lower() in accessibility_tree.lower())
    return found / max(len(expected_elements), 1)
```

**Where do expected_elements come from?**
- Auto-generated from the task description using an LLM call at task start
- Stored as part of the task's milestone checkpoints

### 2.3 Task Completion Signals from Page Content

Pattern-based detection of common completion states:

```python
COMPLETION_PATTERNS = {
    "form_submitted": ["thank you", "confirmation", "successfully submitted", "order placed"],
    "search_completed": ["results", "found .* items", "showing .* of"],
    "navigation_done": lambda url, target: target in url,
    "data_extracted": lambda response, expected: expected in response,
    "login_success": ["welcome", "dashboard", "account", "signed in"],
    "purchase_complete": ["order confirmed", "receipt", "transaction id"],
}

def detect_completion(page_text: str, task_type: str) -> tuple[bool, float]:
    """Returns (is_complete, confidence)"""
    patterns = COMPLETION_PATTERNS.get(task_type, [])
    for pattern in patterns:
        if re.search(pattern, page_text, re.IGNORECASE):
            return True, 0.8
    return False, 0.0
```

### 2.4 Multi-Step Progress Estimation

Combine signals across the full trajectory:

```python
def estimate_progress(
    step_index: int,
    total_expected_steps: int,
    milestones_achieved: list[bool],
    url_score: float,
    dom_score: float,
    llm_judge_score: float,
) -> float:
    """
    Weighted combination of multiple progress signals.
    Weights are tuned empirically.
    """
    milestone_ratio = sum(milestones_achieved) / max(len(milestones_achieved), 1)
    step_ratio = step_index / max(total_expected_steps, 1)

    # Weighted combination
    score = (
        0.40 * milestone_ratio +   # strongest signal
        0.25 * llm_judge_score +    # semantic understanding
        0.20 * dom_score +          # structural progress
        0.10 * url_score +          # navigational progress
        0.05 * step_ratio           # weak time-based signal
    )
    return min(score, 1.0)
```

---

## 3. Process Reward Models at Inference Time

### 3.1 AgentPRM (Xi et al., 2025, arXiv:2511.08325)

**Core Innovation**: Redefines process rewards for agent tasks by measuring two things per step:
1. **Promise**: probability that the current state leads to goal achievement (Q-value)
2. **Progress**: advantage — how much better/worse this step is vs. the previous step

**Key insight for inference-time use**: The concept of "promise + progress" can be implemented purely via prompting, without training a separate model.

**Prompt-based simulation**:

```
Given:
- Task: {task}
- Actions so far: {action_history}
- Current page state: {page_summary}

Rate the current state on two dimensions:
1. PROMISE (0-1): How likely is it that the task can be completed from this state?
2. PROGRESS (-1 to +1): Compared to the previous step, did we move closer to or further from the goal?

Output: {"promise": float, "progress": float, "reasoning": str}
```

**Why this matters**: AgentPRM showed 8x compute efficiency over baselines. The dual-scoring captures both "are we on track?" and "did this step help?" — critical for web agents where some steps temporarily move away from the goal (e.g., navigating to a login page before posting).

### 3.2 PAIR: Prefix-Aware Internal Reward (Kim et al., 2026, arXiv:2605.17877)

**Finding**: Hidden-state probes degrade under "prefix contamination" in multi-step settings — the model tracks coherence with the prefix rather than correctness. Attention-based features remain robust.

**For Sediman**: This suggests that asking the LLM to self-evaluate mid-trajectory is unreliable because it will tend to say "yes, I'm on track" due to anchoring to its own previous actions. **Use an independent evaluation call** (separate from the action-generating call) to avoid this bias.

### 3.3 Can PRMs Work Without Fine-Tuning?

**Yes, via prompting**. The SRaR paper (arXiv:2605.17291) shows that rubric-based evaluation can be done zero-shot:

1. **Generate rubrics** from the task description (one LLM call at task start)
2. **Evaluate each step** against rubrics (one LLM call per evaluation point)
3. **Aggregate** rubric scores into a per-step reward

The cost is additional LLM calls. For Sediman, this means:
- At task start: 1 extra call to generate milestones/rubrics
- Every N steps: 1 extra call to evaluate progress
- At task end: 1 extra call to verify completion

---

## 4. Milestone/Subgoal-Based Rewards

### 4.1 MiRA: Milestoning your RL Agent (Wang et al., 2026, arXiv:2603.19685)

**The current SOTA approach for web agents.** Gemma3-12B + MiRA achieves 43.0% on WebArena-Lite, surpassing GPT-4-Turbo (17.6%) and WebRL (38.4%).

**How MiRA Works (inference-time component)**:

1. **Subgoal Generation**: A larger model (Gemini-2.5-Pro) decomposes the task into ordered subgoals:
   ```
   Task: "Find the filming location of 'The Chair' in Pennsylvania on the map"
   Subgoals:
     1. Navigate to Wikipedia and find "The Chair" TV show page
     2. Identify the filming location (college name)
     3. Navigate to OpenStreetMap
     4. Search for the college on the map
   ```

2. **Progress Labeling**: At each step, check if the current subgoal has been completed:
   ```python
   def check_milestone(subgoal: str, page_state: str) -> bool:
       # Use LLM to verify: "Has subgoal X been achieved given this page state?"
       # Binary YES/NO — no soft scores
       pass
   ```

3. **Dynamic Milestoning at Inference**: The agent gets the current subgoal in its context:
   ```
   Current subgoal: {active_subgoal}
   Status: {"achieved" | "in_progress" | "blocked"}
   
   If blocked, trigger replanning to generate new subgoals.
   ```

**Failure Analysis Finding (critical)**: MiRA's failure analysis reveals that **~42-49% of failures are "Get Stuck Midway"** — the agent enters repetitive action loops. Subgoals directly address this by giving the agent a clear next target.

### 4.2 Auto-Generating Milestones from Task Descriptions

**Prompt for milestone generation**:

```
You are a web automation task planner. Given a task, break it into 2-5 
verifiable milestones. For each milestone, specify:

1. A clear description of what should be achieved
2. How to verify it's complete (URL pattern, DOM element, or content check)
3. Dependencies on previous milestones

TASK: {task_description}

Output as JSON array.
```

**Example output for "Book a table at an Italian restaurant for 2 tonight on OpenTable"**:
```json
[
  {
    "id": 1,
    "description": "Navigate to OpenTable website",
    "verify": "URL contains 'opentable.com'",
    "depends_on": []
  },
  {
    "id": 2,
    "description": "Search for Italian restaurants",
    "verify": "Page shows restaurant listings with cuisine filter 'Italian'",
    "depends_on": [1]
  },
  {
    "id": 3,
    "description": "Select a restaurant and choose time for 2 people",
    "verify": "Reservation form is visible with party size 2",
    "depends_on": [2]
  },
  {
    "id": 4,
    "description": "Complete the reservation",
    "verify": "Confirmation page or message appears",
    "depends_on": [3]
  }
]
```

### 4.3 Checking Milestone Completion Without Human Labels

Three methods, ordered by reliability:

1. **Hardcoded DOM/URL checks** (most reliable, least general):
   ```python
   def verify_milestone_hardcoded(milestone, current_state):
       if "URL contains" in milestone["verify"]:
           return milestone["verify_pattern"] in current_state["url"]
       if "DOM element" in milestone["verify"]:
           return milestone["verify_pattern"] in current_state["dom"]
   ```

2. **LLM-as-judge verification** (general, moderately reliable):
   ```
   Given milestone: "{milestone_description}"
   Current page state: {page_summary}
   Has this milestone been achieved? Answer YES or NO.
   ```

3. **Teacher model verification** (most reliable, most expensive):
   - Use a stronger model (e.g., GPT-4) to verify milestone completion
   - MiRA uses Gemini-2.5-Pro for subgoal checking

**Recommendation for Sediman**: Use method 1 where possible, fall back to method 2 with the same model (separate evaluation call).

---

## 5. Outcome-Supervised Reward Models (ORM)

### 5.1 WebRL's ORM Approach

**Architecture** (Qi et al., 2024, arXiv:2411.02337):

The ORM is a fine-tuned LLM that takes:
- Task instruction `I`
- Action history (text, not HTML)
- Final-state HTML only

And outputs binary YES/NO via token probability comparison:
```python
# Pseudo-code from WebRL
p_yes = model.forward(input, target_token="YES")
p_no = model.forward(input, target_token="NO")
reward = 1.0 if p_yes > p_no else 0.0
```

**Training data**: The ORM is trained on trajectories from the agent's own exploration — successful trajectories get label 1, failures get label 0. This is the "outcome-supervised" part.

### 5.2 Building a Lightweight ORM from Sediman's Trajectory Data

Sediman already has:
- Screen recordings with cursor tracking
- Session storage with SQLite + FTS5
- Skill execution traces with success/failure outcomes

**No fine-tuning needed — use the existing LLM as ORM via prompting**:

```python
async def evaluate_task_outcome(task: str, trajectory: list[dict], final_state: str) -> float:
    """
    Zero-shot ORM using the same LLM that drives the agent.
    Returns 0.0 or 1.0.
    """
    prompt = f"""Evaluate whether this web automation task was completed successfully.

TASK: {task}

ACTIONS TAKEN:
{format_actions(trajectory)}

FINAL PAGE CONTENT:
{truncate(final_state, max_tokens=2000)}

Did the agent successfully complete the task? Consider:
- Did the agent reach the correct final page/state?
- Were all required actions performed?
- Is the outcome consistent with the task requirements?

Answer ONLY "YES" or "NO"."""
    
    response = await llm.generate(prompt, max_tokens=1)
    return 1.0 if "YES" in response else 0.0
```

### 5.3 Trajectory Data as Training Signal (Future Direction)

If Sediman accumulates enough trajectory data with known outcomes, you could:

1. **Log trajectories** with outcome labels (success/failure from user confirmation)
2. **Build a dataset**: (instruction, action_history, final_html, outcome)
3. **Fine-tune a small model** (e.g., Qwen2.5-0.5B) as a dedicated ORM
4. **Use the ORM at inference time** for fast, cheap reward evaluation

This is exactly what WebRL does — but it requires thousands of labeled trajectories.

---

## 6. Practical Implementation Patterns for Sediman

### 6.1 Simplest Effective Reward Signal

**The minimum viable approach**: A single LLM-as-judge call at task completion.

```python
async def simple_reward(task: str, trajectory: list, final_state: dict) -> dict:
    """
    Simplest reward: ask the LLM "did you complete the task?"
    Called once at the end of execution.
    """
    evaluation = await llm.evaluate(
        task=task,
        actions=summarize_actions(trajectory),
        page_state=extract_text(final_state["dom"]),
    )
    return {
        "success": evaluation["completed"],
        "confidence": evaluation["score"],
        "reasoning": evaluation["reasoning"],
    }
```

**Why this works**: WebRL's entire ORM is essentially this — an LLM judging completion. The difference is WebRL fine-tunes a model for it, but zero-shot prompting with a strong model is a reasonable starting point.

### 6.2 Combined Multi-Signal Approach

The recommended architecture for Sediman:

```
┌─────────────────────────────────────────────────────────┐
│                    TASK START                            │
│  1. Generate milestones (1 LLM call)                    │
│  2. Store milestones in session context                  │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│                AGENT LOOP                                │
│  Every step:                                             │
│    - Fast: URL change detection (free)                   │
│    - Fast: DOM element presence check (free)             │
│    - Fast: Loop detection via action hashing (free)      │
│                                                          │
│  Every N steps (N=3-5) or on milestone transition:       │
│    - Milestone completion check (1 LLM call)             │
│    - Progress score update                               │
│                                                          │
│  On loop detection:                                      │
│    - Trigger replanning (1 LLM call)                     │
│    - Update milestones                                   │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│               TASK END                                   │
│  1. Final outcome evaluation (1 LLM call)                │
│  2. Log trajectory with outcome for future ORM training  │
└─────────────────────────────────────────────────────────┘
```

### 6.3 How Often to Compute Rewards

| Signal Type | Frequency | Cost | Reliability |
|---|---|---|---|
| URL change detection | Every step | Free (string compare) | Low |
| DOM element presence | Every step | Free (string search) | Medium |
| Action loop detection | Every step | Free (hash comparison) | High |
| Milestone completion | Every 3-5 steps or on page transition | 1 LLM call | High |
| LLM progress judge | Every 3-5 steps | 1 LLM call | Medium |
| Final outcome eval | Once at task end | 1 LLM call | High |

**Recommendation**:
- **Free signals** (URL, DOM, loop detection): Every step
- **LLM-based signals**: Every 3-5 steps or on significant state change (page navigation, form submission)
- **Milestone checks**: On page navigation events (these are natural transition points)

### 6.4 Loop Detection (Critical for Web Agents)

MiRA's failure analysis shows **42-49% of failures are "stuck midway"** — the agent loops on the same actions. This is the single biggest failure mode.

```python
import hashlib
from collections import deque

class LoopDetector:
    def __init__(self, window_size: int = 5, max_repeats: int = 3):
        self.recent_actions = deque(maxlen=window_size * max_repeats)
        self.window_size = window_size
        self.max_repeats = max_repeats
    
    def check(self, action: str, page_state: str) -> bool:
        """Returns True if the agent is stuck in a loop."""
        state_hash = hashlib.md5(
            f"{action}:{page_state[:500]}".encode()
        ).hexdigest()
        self.recent_actions.append(state_hash)
        
        if len(self.recent_actions) < self.window_size:
            return False
        
        # Check if the recent window repeats
        window = list(self.recent_actions)[-self.window_size:]
        all_windows = [
            list(self.recent_actions)[i:i+self.window_size]
            for i in range(len(self.recent_actions) - self.window_size + 1)
        ]
        
        repeat_count = sum(1 for w in all_windows if w == window)
        return repeat_count >= self.max_repeats
```

### 6.5 Putting It All Together: Sediman Reward Module

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class RewardState:
    task: str
    milestones: list[dict] = field(default_factory=list)
    current_milestone_idx: int = 0
    milestones_achieved: list[bool] = field(default_factory=list)
    step_count: int = 0
    last_evaluation_step: int = 0
    evaluation_interval: int = 4
    progress_score: float = 0.0
    is_stuck: bool = False

class RewardModule:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.loop_detector = LoopDetector()
    
    async def initialize(self, task: str) -> RewardState:
        """Called at task start. Generates milestones."""
        milestones = await self._generate_milestones(task)
        state = RewardState(
            task=task,
            milestones=milestones,
            milestones_achieved=[False] * len(milestones),
        )
        return state
    
    async def step_reward(
        self,
        state: RewardState,
        action: str,
        page_url: str,
        page_dom: str,
    ) -> tuple[RewardState, dict]:
        """
        Called after each agent step.
        Returns updated state and reward info.
        """
        state.step_count += 1
        
        # Free signals: every step
        loop_detected = self.loop_detector.check(action, page_dom)
        url_changed = self._url_progress(page_url, state)
        dom_elements = self._dom_check(page_dom, state)
        
        reward_info = {
            "loop_detected": loop_detected,
            "url_progress": url_changed,
            "dom_progress": dom_elements,
        }
        
        # LLM-based: every N steps or on loop detection
        should_evaluate = (
            state.step_count - state.last_evaluation_step >= state.evaluation_interval
            or loop_detected
            or url_changed.get("major_navigation", False)
        )
        
        if should_evaluate:
            state.last_evaluation_step = state.step_count
            
            # Check current milestone
            if state.current_milestone_idx < len(state.milestones):
                milestone = state.milestones[state.current_milestone_idx]
                achieved = await self._check_milestone(milestone, page_url, page_dom)
                if achieved:
                    state.milestones_achieved[state.current_milestone_idx] = True
                    state.current_milestone_idx += 1
            
            # Get overall progress score
            state.progress_score = await self._llm_progress_judge(
                state.task, state.milestones_achieved, page_url, page_dom
            )
            reward_info["progress_score"] = state.progress_score
        
        if loop_detected:
            state.is_stuck = True
            # Trigger replanning
            new_milestones = await self._replan(state, page_url, page_dom)
            if new_milestones:
                state.milestones = new_milestones
                state.milestones_achieved = [False] * len(new_milestones)
                state.current_milestone_idx = 0
                state.is_stuck = False
        
        return state, reward_info
    
    async def final_reward(
        self,
        state: RewardState,
        trajectory: list[dict],
        final_url: str,
        final_dom: str,
    ) -> dict:
        """Called at task end. Evaluates final outcome."""
        outcome = await self._evaluate_outcome(
            state.task, trajectory, final_url, final_dom
        )
        return {
            "success": outcome["completed"],
            "confidence": outcome["score"],
            "milestones_achieved": sum(state.milestones_achieved),
            "total_milestones": len(state.milestones),
            "total_steps": state.step_count,
            "progress_score": state.progress_score,
        }
```

### 6.6 Cost Analysis

For a typical 10-step web task:

| Component | LLM Calls | Estimated Tokens |
|---|---|---|
| Milestone generation (1x) | 1 | ~500 in, ~300 out |
| Milestone checks (every 4 steps = 2-3x) | 2-3 | ~300 in, ~50 out each |
| Progress judge (2-3x) | 2-3 | ~500 in, ~100 out each |
| Final outcome eval (1x) | 1 | ~1000 in, ~100 out |
| **Total** | **6-8 extra calls** | **~4,000-5,000 tokens** |

This is roughly a 15-20% overhead on top of the agent's own LLM calls. Acceptable for tasks where reliability matters.

### 6.7 Priority Implementation Order

1. **Loop detection** (free, addresses #1 failure mode) — implement immediately
2. **Final outcome evaluation** (1 extra call at task end) — implement immediately  
3. **Milestone generation + checking** (biggest quality improvement) — implement next
4. **URL/DOM heuristic signals** (free incremental signal) — implement with milestones
5. **Continuous progress judge** (expensive, diminishing returns) — implement last

---

## Key Papers Referenced

| Paper | arXiv | Key Contribution | Training Required? |
|---|---|---|---|
| **AgentPRM** (Xi et al., 2025) | 2511.08325 | Promise + Progress dual scoring, TD-based estimation | Yes (but concept adaptable) |
| **WebRL** (Qi et al., 2024) | 2411.02337 | Self-evolving curriculum, ORM training, KL-constrained RL | Yes (but ORM concept adaptable) |
| **MiRA** (Wang et al., 2026) | 2603.19685 | Subgoal decomposition, milestone-based reward shaping | Yes for RL, but subgoal planning works at inference |
| **Symbolic Learning** (Zhou et al., 2024) | 2406.18532 | Self-evolving agents via symbolic backprop | No (prompt-based) |
| **CUA-Gym** (Wang et al., 2026) | 2605.25624 | Co-generating tasks + environments + reward functions | Yes (RL training) |
| **OpenComputer** (Wei et al., 2026) | 2605.19769 | Verifier-grounded framework, partial-credit rewards | Yes |
| **SRaR** (Xie et al., 2026) | 2605.17291 | Step-wise rubric attribution, per-step scoring | Yes (but rubrics concept adaptable) |
| **PAIR** (Kim et al., 2026) | 2605.17877 | Prefix contamination in self-evaluation | N/A (finding) |
| **Eureka** (Ma et al., 2023) | 2310.12931 | LLM-generated reward code via evolutionary optimization | Yes (RL) |
