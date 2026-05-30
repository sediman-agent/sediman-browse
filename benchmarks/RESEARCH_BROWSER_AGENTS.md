# Browser Automation Agents: State-of-the-Art Research Report (2024-2026)

## Table of Contents
1. [WebArena Benchmark Leaders](#1-webarena-benchmark-leaders)
2. [Key Systems & Architectures](#2-key-systems--architectures)
3. [Key Architectural Innovations](#3-key-architectural-innovations)
4. [Benchmark Analysis](#4-benchmark-analysis)
5. [Specific Techniques](#5-specific-techniques)
6. [Cross-Cutting Themes & What Separates Top Agents](#6-cross-cutting-themes)

---

## 1. WebArena Benchmark Leaders

### Current Top Scores (WebArena / WebArena-Lite)

| Agent / System | WebArena Score | WebArena-Lite Score | Architecture | Date |
|---|---|---|---|---|
| **Human** | **78.24%** | — | — | 2023 |
| **GUI-Owl-1.5 (235B)** | **48.4%** | — | Native GUI agent, multi-platform RL (MRPO), hybrid data flywheel | Feb 2026 |
| **CUA-Gym-A17B** | Transfers | **72.6% OSWorld-Verified** | GSPO RL training on 32K verified tuples, 110 environments | May 2026 |
| **OS-Symphony** | — | **65.84% OSWorld** | Reflection-Memory Agent + Multimodal Searcher (SeeAct paradigm) | Jan 2026 |
| **WebServ (Qwen3-4B RL)** | — | **55.5%** | Full-stack RL-ready web env, Incus containers, GRPO training | Oct 2025 |
| **WebATLAS** | — | **63.0%** | Memory-augmented, planner-simulator-critic loop, no fine-tuning | Oct 2025 |
| **Agent-as-Annotators (9B)** | **41.5%** | — | Structured distillation from Gemini 3 Pro teacher, SFT only | Apr 2026 |
| **MiRA + Gemma3-12B** | — | **43.0%** | Subgoal-driven planning + milestone-based RL rewards | Mar 2026 |
| **WebRL + Llama-3.1-8B** | — | **42.4%** | Self-evolving online curriculum RL, outcome-supervised RM | Nov 2024 |
| **WebRL + GLM-4-9B** | — | **43.0%** | Same as above | Nov 2024 |
| **AutoGLM** | **55.2%** (VAB-WA-Lite) | — | Progressive RL, intermediate interface, self-evolving curriculum | Oct 2024 |
| **Plan-MCTS** | SOTA (claimed) | — | MCTS in semantic Plan Space, Dual-Gating Reward | Feb 2026 |
| **WebUncertainty** | SOTA (claimed) | — | Dual-level uncertainty, MCTS reasoning, adaptive planning | Apr 2026 |
| GPT-4o (baseline) | ~14-31.5% | 13.9% | Direct prompting | 2024 |
| Claude 3.5 Sonnet (baseline) | ~36.0% | — | Direct prompting | 2024 |
| GPT-4-Turbo (baseline) | — | 17.6% | Direct prompting | 2024 |

### Key Observation: What Top Agents Do Differently
- **RL training is essential**: Every top-performing agent uses some form of RL fine-tuning (WebRL, MiRA, GSPO, WebServ)
- **Dense reward signals**: Milestone-based rewards dramatically outperform sparse outcome rewards (MiRA: 6.4% → 43.0%)
- **Structured planning before execution** significantly improves results over pure ReAct
- **Environment diversity in training** transfers to held-out benchmarks (CUA-Gym, Weasel)

---

## 2. Key Systems & Architectures

### 2.1 WebRL (arxiv: 2411.02337, ICLR 2025)
- **Authors**: Zehan Qi, Xiao Liu et al. (Tsinghua)
- **Key Innovation**: Self-evolving online curriculum RL framework
  - Generates new training tasks from unsuccessful attempts (curriculum)
  - Robust outcome-supervised reward model (ORM)
  - Adaptive RL strategies to prevent policy distribution drift
- **Results**: Llama-3.1-8B: 4.8% → 42.4% on WebArena-Lite; GLM-4-9B: 6.1% → 43.0%
- **Architecture**: Online RL with curriculum generation, not SFT on expert demos

### 2.2 SeeAct (arxiv: 2401.01614)
- **Authors**: Boyuan Zheng, Boyu Gou, Jihyung Kil, Huan Sun, Yu Su (OSU)
- **Key Innovation**: First generalist web agent using LMMs (GPT-4V) for integrated visual understanding + acting
  - Leverages both HTML structure and visuals for grounding
  - Set-of-mark prompting for element identification
  - Online evaluation on live websites (not just cached)
- **Results**: GPT-4V achieves 51.1% with manual grounding on live sites; grounding remains the major challenge
- **Significance**: Established vision-language approach for web agents

### 2.3 AutoGLM / AutoWebGLM (arxiv: 2411.00820; arxiv: 2404.03648, KDD 2024)
- **Authors**: Xiao Liu et al. (Tsinghua/ChatGLM)
- **Key Innovations**:
  - **Intermediate interface**: Separates planning and grounding into distinct optimization targets
  - **Progressive training**: Self-evolving online curriculum RL
  - HTML simplification algorithm inspired by human browsing patterns
  - Rejection sampling + RL bootstrapping
- **Results**: 55.2% on VAB-WebArena-Lite (59.1% with 2nd attempt); 96.2% on OpenTable
- **Architecture**: ChatGLM-based with progressive RL, hybrid human-AI data for curriculum training

### 2.4 Agent-as-Annotators / Structured Distillation (arxiv: 2604.07776)
- **Authors**: Xing Han Lù, Siva Reddy (McGill)
- **Key Innovation**: Structured trajectory generation by analogy to human annotation roles
  - Task Designer, Annotator, Supervisor → modular LLM components
  - 3,000 trajectories from Gemini 3 Pro, filtered to 2,322
  - **9B student surpasses Claude 3.5 Sonnet (36.0%) and GPT-4o (31.5%)**
- **Results**: **41.5% WebArena** (pure SFT, no RL); +18.2pp on WorkArena L1 (unseen)
- **Architecture**: Pure supervised learning on quality-filtered teacher trajectories

### 2.5 CUA-Gym (arxiv: 2605.25624)
- **Authors**: Bowen Wang et al. (Alibaba/Qwen team)
- **Key Innovation**: Scalable RLVR (RL with Verifiable Rewards) pipeline for CUAs
  - Co-generates task instructions, environment states, and reward functions
  - Generator + Discriminator agents with adversarial loop
  - **32,112 verified RLVR training tuples across 110 environments**
  - MRPO: Multi-platform environment RL algorithm
- **Results**: CUA-Gym-A17B: **72.6% OSWorld-Verified**; transfers to held-out WebArena
- **Architecture**: GSPO training on synthesized RLVR data, multi-platform RL scaling

### 2.6 WebServ (arxiv: 2510.16252)
- **Authors**: Yuxuan Lu et al. (IBM/UNC)
- **Key Innovation**: Full-stack RL-ready web environment
  - Incus containers with COW: 5x faster launch, 240x less storage
  - 200+ concurrent isolated environments per host
  - Site-agnostic observation/action interface from DOM with interactivity cues
  - Network-aware waiting for reliable SPA support
- **Results**: **Qwen3-4B RL → 55.5%** (surpasses Claude 4.5 Sonnet 50.0% and WebAgent-R1 8B 51.8%)

### 2.7 Plan-MCTS (arxiv: 2602.14083)
- **Authors**: Weiming Zhang et al. (Shanghai Jiao Tong)
- **Key Innovation**: MCTS in semantic Plan Space (not action space)
  - Decouples strategic planning from execution grounding
  - Dense Plan Tree for efficient exploration
  - Abstracted Semantic History for precise state awareness
  - Dual-Gating Reward: validates physical executability + strategic alignment
  - Structural Refinement: on-policy repair of failed subplans
- **Results**: SOTA on WebArena (exact score TBD, claims significant improvement)

### 2.8 WebUncertainty (arxiv: 2604.17821)
- **Authors**: Lingfeng Zhang et al. (Hefei University of Technology)
- **Key Innovation**: Dual-level uncertainty framework
  - **Task Uncertainty-Driven Adaptive Planning**: selects planning modes adaptively
  - **Action Uncertainty-Driven MCTS Reasoning**: ConActU strategy quantifies aleatoric + epistemic uncertainty
  - Optimizes search process for robust decision-making
- **Results**: Superior performance on WebArena and WebVoyager vs SOTA

### 2.9 OS-Symphony (arxiv: 2601.07779)
- **Authors**: Bowen Yang et al.
- **Key Innovation**: Holistic CUA framework
  - **Reflection-Memory Agent**: milestone-driven long-term memory for trajectory-level self-correction
  - **Versatile Tool Agents**: Multimodal Searcher with SeeAct paradigm for live tutorials
  - Orchestrator coordinates both components
- **Results**: **65.84% OSWorld** (new SOTA); works across varying model scales

### 2.10 WebATLAS (arxiv: 2510.22732)
- **Authors**: Jiali Cheng et al. (Microsoft/UMass)
- **Key Innovation**: Memory-augmented agent with action simulation
  - **Planner-Simulator-Critic loop**: hypothetical action rollouts before real execution
  - Curiosity-driven exploration builds persistent cognitive map
  - Experience-based memory of past failures
- **Results**: **63.0% WebArena-Lite** (prev SOTA: 53.9%); no website-specific fine-tuning needed

### 2.11 GUI-Owl-1.5 / Mobile-Agent-v3.5 (arxiv: 2602.16855)
- **Authors**: Haiyang Xu et al. (Alibaba)
- **Key Innovation**: Multi-platform native GUI agent
  - Sizes: 2B/4B/8B/32B/235B with instruct/thinking variants
  - **Hybrid Data Flywheel**: simulated + cloud sandbox data pipeline
  - **MRPO**: Multi-platform environment RL for long-horizon tasks
  - Unified thought-synthesis pipeline for reasoning
- **Results**: **48.4% WebArena**, 56.5% OSWorld, 71.6% AndroidWorld, 80.3% ScreenSpotPro

### 2.12 APEX (arxiv: 2605.21240)
- **Authors**: Yibo Li et al. (National University of Singapore)
- **Key Innovation**: Autonomous Policy Exploration for self-evolving agents
  - Strategy map: directed acyclic graph of milestones with dependencies
  - Fork Discovery expands unexplored directions
  - Policy Selection balances exploration/exploitation
- **Results**: Outperforms all baselines on WebArena and Jericho text games

### 2.13 MiRA / Subgoal-driven Framework (arxiv: 2603.19685)
- **Authors**: Taiyi Wang et al. (Google DeepMind)
- **Key Innovation**:
  - **Online subgoal decomposition** with proprietary models for planning
  - **MiRA**: RL with dense, milestone-based reward signals (not sparse outcome rewards)
  - Explicit inference-time planning + milestone-based rewards
- **Results**: Gemma3-12B: 6.4% → 43.0% (surpasses GPT-4-Turbo 17.6%, GPT-4o 13.9%, WebRL 38.4%)

### 2.14 AgentPRM (arxiv: 2511.08325)
- **Authors**: Zhiheng Xi et al. (Fudan)
- **Key Innovation**: Process Reward Models for agent tasks
  - Evaluates each decision based on proximity to goal + progress made
  - Temporal Difference-based estimation with GAE for scalable labeling
  - **8x more compute-efficient** than baselines
- **Architecture**: PRM guides agent decision-making; applies to RL training of LLM agents

### 2.15 AgentHER (arxiv: 2603.21357)
- **Authors**: Liang Ding
- **Key Innovation**: Hindsight Experience Replay for agent trajectories
  - Failed trajectory for goal A → correct demo for achievable goal B
  - 4-stage pipeline: failure classification, outcome extraction, LLM-guided relabeling, data packaging
  - Converts discarded failures into SFT/DPO/ShareGPT data
- **Results**: +7.6-11.4% over success-only SFT; 2x sample efficiency; +3.0-6.2% over Agent Workflow Memory

### 2.16 Weasel (arxiv: 2605.20291, ICML 2026)
- **Authors**: Fatemeh Pesaran Zadeh et al. (McGill/Samsung)
- **Key Innovation**: Trajectory selection for OOD generalization
  - Balances unary importance with pairwise diversity over states, websites, patterns
  - Target-centered AXTree pruning
  - Style-consistent rationales for reasoning-native models
- **Results**: 9.7-12.5x training speedups; improves OOD performance across WebArena, WorkArena, MiniWob

---

## 3. Key Architectural Innovations

### 3.1 Multi-Step Planning vs Reactive Execution

**The Plan-Then-Execute Debate** (arxiv: 2605.14290):
- **Key argument**: ReAct is the wrong default for web agents because web content mixes inputs from many parties (sellers, reviews, ads), creating prompt injection surface
- **Plan-then-execute**: Commit to a task-specific program BEFORE observing runtime web content
- **Finding**: 80% of WebArena tasks can be completed with purely programmatic plans (no runtime LLM)
- **Barrier**: Current web tools (click, type, scroll) have page-dependent meanings → need typed interfaces

**PlanAhead** (arxiv: 2605.29927):
- Systematic comparison of 4 plan representations: sequential subgoals, narrative, pseudocode, checklist
- Plan formulation AND underlying LLM significantly influence agent robustness
- Different LLM families respond differently to different plan formats

**Subgoal-driven Framework (MiRA)** (arxiv: 2603.19685):
- Explicit online subgoal decomposition during inference
- Dense milestone-based rewards during RL training
- Solves both the inference-time and training-time problems of long-horizon planning

### 3.2 Tree-of-Thought / MCTS Approaches

**Plan-MCTS** (arxiv: 2602.14083):
- Reformulates web navigation by exploring in semantic Plan Space (not action space)
- Sparse action space → Dense Plan Tree for efficient exploration
- Noisy DOM context → Abstracted Semantic History for precise state
- Dual-Gating Reward validates both physical executability AND strategic alignment

**WebUncertainty** (arxiv: 2604.17821):
- MCTS with uncertainty-aware reasoning
- Confidence-induced Action Uncertainty (ConActU) quantifies both aleatoric and epistemic uncertainty
- Task-level uncertainty drives adaptive planning mode selection

**APEX** (arxiv: 2605.21240):
- Strategy map as DAG of milestones with dependency edges
- Fork Discovery for unexplored directions
- Addresses "exploration collapse" in self-evolving agents

### 3.3 Self-Reflection and Self-Correction

**OS-Symphony** (arxiv: 2601.07779):
- **Reflection-Memory Agent**: milestone-driven long-term memory enables trajectory-level self-correction
- Mitigates visual context loss in long-horizon tasks
- Multimodal Searcher navigates browser sandbox for live tutorials

**WebATLAS** (arxiv: 2510.22732):
- **Planner-Simulator-Critic loop**: evaluates actions in "cognitive space" before real execution
- Curiosity-driven exploration + experience-driven memory
- Learns lightweight internal model of environment from interaction

**Environment Maps** (arxiv: 2603.23610, ICLR 2026 Workshop):
- Persistent, agent-agnostic representation consolidating heterogeneous evidence
- 4 components: Contexts (locations), Actions (affordances), Workflows (trajectories), Tacit Knowledge
- **28.2% success vs 14.2% baseline** (nearly doubling performance)

**V-GEMS** (arxiv: 2603.02626):
- Visual grounding + explicit memory stack with state tracking
- Maintains structured map of traversal path for valid backtracking
- Prevents cyclical failures in deep navigation

### 3.4 Handling Dynamic DOM Changes

**Region4Web** (arxiv: 2605.07134):
- Reorganizes AXTree into functional regions (hierarchical decomposition + semantic abstraction)
- **PageDigest**: compact per-page observation that persists across steps
- Substantially reduces observation length while improving task success rate

**ContextCurator** (arxiv: 2604.11462):
- Decouples context management from task execution
- RL-trained lightweight policy model aggressively prunes noise, preserves "reasoning anchors"
- 7B ContextCurator matches GPT-4o context management performance
- Improves Gemini-3.0-flash from 36.4% to 41.2% while reducing tokens 8.8%

**TOCTOU Vulnerabilities** (arxiv: 2603.00476):
- Time-of-check-to-time-of-use vulnerability in browser-use agents
- Dynamic/adversarial content exploits window between planning and execution
- Lightweight mitigation: pre-execution validation of DOM/layout changes

### 3.5 Reward Models / RL Approaches

**AgentPRM** (arxiv: 2511.08325):
- Process Reward Models for agent tasks (not just reasoning)
- Evaluates based on proximity to goal + progress made (not binary correctness)
- TD-based estimation + GAE for scalable data labeling
- 8x more compute-efficient than baselines

**AgentHER** (arxiv: 2603.21357):
- Hindsight Experience Replay for natural-language trajectories
- Failed trajectory for goal A = correct demo for goal B
- +7.6-11.4% over success-only SFT across 4 model families

**AdaRubric** (arxiv: 2603.21362, ACL 2026):
- Task-adaptive evaluation rubrics generated from task descriptions
- Dense reward signals for preference learning (DPO)
- +6.8-8.5% task success over best baseline

**WebAgent-R1** (referenced in WebServ paper):
- RL-trained 8B model achieves 51.8% on WebArena-Lite
- Surpassed by WebServ's RL-trained 4B model (55.5%)

### 3.6 Vision vs DOM-only vs Hybrid

**SeeAct** (arxiv: 2401.01614):
- Vision-language approach: GPT-4V processes screenshots + HTML
- Best grounding uses BOTH HTML structure and visuals
- Set-of-mark prompting alone is NOT effective for web agents
- Oracle grounding: 51.1% → huge gap with automatic grounding

**Region4Web** (arxiv: 2605.07134):
- DOM-only with intelligent reorganization
- Functional regions > element-level processing
- More compact and informative than raw DOM or screenshots

**GUI-Owl-1.5** (arxiv: 2602.16855):
- Hybrid: native GUI agent with vision + accessibility tree
- Multi-platform (desktop, mobile, browser)
- RL scaling across platforms

**Consensus**: Hybrid (vision + structured DOM/AXTree) consistently outperforms either alone. Vision helps with spatial layout and visual elements; DOM helps with precise element identification and form interaction.

---

## 4. Benchmark Analysis

### 4.1 WebArena
- **812 tasks** across e-commerce, social forums, GitLab, CMS, maps, Wikipedia
- **Human: 78.24%** | Best agents: 41-48% (as of early 2026)
- **Key challenge**: Long-horizon, multi-step tasks requiring state tracking
- **Updated framework**: AgentLab provides parallel experiments, unified leaderboard
- **What separates 40% from 80%**:
  1. State management across page transitions
  2. Recovery from wrong actions (self-correction)
  3. Handling dynamic content/popups
  4. Multi-step reasoning chains (>5 steps)
  5. Information synthesis across multiple pages

### 4.2 WebArena-Lite
- Subset of WebArena for faster evaluation
- Human baselines not published
- Top scores: ~43-63% depending on agent
- Primary benchmark for training-focused papers

### 4.3 VisualWebArena
- Vision-augmented version of WebArena
- Requires visual understanding (e.g., "click the red shirt")
- SeeAct paper (arxiv: 2401.01614) established early baselines
- Integrated into BrowserGym/AgentLab framework

### 4.4 OSWorld
- Full desktop OS environment (not just browser)
- **Human: ~72.7%** | Top agents:
  - OS-Symphony: **65.84%**
  - CUA-Gym-A17B: **72.6%**
  - GUI-Owl-1.5: **56.5%**
- Tests file management, application use, multi-app workflows

### 4.5 Mind2Web
- Offline evaluation benchmark (cached websites)
- 2000+ tasks across 137 websites
- **PolySkill** (arxiv: 2510.15863): +9.4% on Mind2Web via polymorphic skill learning
- Focuses on generalization to unseen websites

### 4.6 WebLINX
- Conversational web navigation benchmark
- Real-world demonstrations from human annotators
- Focuses on dialogue-guided web interaction
- Dense annotation of human actions

### 4.7 GAIA
- General AI Assistant benchmark
- Tests reasoning, web browsing, multi-modal understanding
- Frontier models still struggle significantly

### 4.8 WebForge (arxiv: 2604.10955)
- **New (2026)**: Resolves the realism-reproducibility-scalability trilemma
- 4-agent pipeline (Plan, Generate, Refine, Validate) produces interactive web environments
- **934 tasks**, 7 domains, 3 difficulty levels
- 7-dimensional difficulty control framework

### 4.9 WebServ Benchmark
- Full-stack RL-ready evaluation
- Single-prompt SOTA results across GPT-4o, o3, Llama-3.1-8B
- RL-trained 4B outperforms Claude 4.5 Sonnet

### What Separates 40% Agents from 80% Agents

1. **Planning architecture**: 40% agents use pure ReAct; 80% agents use hierarchical planning with subgoal decomposition
2. **Training data quality**: Structured trajectory synthesis + quality filtering >> random exploration
3. **Reward design**: Dense milestone rewards >> sparse outcome rewards
4. **Memory**: Persistent memory across steps/episodes (not just context window)
5. **Self-correction**: Explicit reflection + backtracking mechanisms
6. **Environment robustness**: Handling SPAs, popups, dynamic content, network issues
7. **Observation space**: Functional region-level DOM >> element-level DOM; hybrid >> single modality
8. **RL fine-tuning**: Every top agent uses some form of RL; pure prompting is insufficient

---

## 5. Specific Techniques

### 5.1 AgentQ-Style Q-Learning for Web Agents
- **AgentQ** (Commute Labs): Applies Q-learning inspired approach to web agents
  - Learned value function over web states
  - Combines MCTS with learned Q-values for planning
  - Not directly found on arxiv; referenced in blog posts and discussions
- **Related: AgentPRM** (arxiv: 2511.08325): Process reward models serve similar purpose as Q-functions
- **Related: WebRL** (arxiv: 2411.02337): Outcome-supervised reward model acts as value function

### 5.2 STEVE-1 / Vision-Language Navigation
- STEVE-1: Vision-language model for embodied navigation
- Not directly a web agent paper, but influenced SeeAct's vision-language approach
- **Key transfer**: Visual grounding + action generation from multimodal models

### 5.3 SeeAct / VisualWebArena Approaches
- **SeeAct** (arxiv: 2401.01614): GPT-4V as generalist web agent
  - Two-stage: (1) generate textual plan, (2) ground plan to actions
  - Grounding is the primary bottleneck (not planning)
  - Hybrid HTML+visual grounding > either alone
- **VisualWebArena**: Extends WebArena with visual understanding requirements
  - Requires processing images, layouts, visual relationships
  - Vision-language models significantly outperform text-only models

### 5.4 WebCanvas Evaluation Methodology
- WebCanvas: Framework for evaluating web agents on process metrics (not just outcomes)
- Related to **AgentLens** (arxiv: 2605.12925): Process-level assessment of SWE-agent trajectories
- Identifies "Lucky Passes" where agents succeed through trial-and-error
- Decomposes behavior into Exploration, Implementation, Verification, Orchestration phases

### 5.5 DigiRL / RL from Digital Interactions
- **DigiRL** (not directly found on arxiv under this name; concept widely used):
  - RL training directly in digital environments (browsers, OS)
  - Key challenge: environment cost, reward sparsity, distribution drift
- **WebRL** (arxiv: 2411.02337): Most direct implementation of this concept
  - Self-evolving curriculum generates tasks from failures
  - Online RL with adaptive strategies
- **WebServ** (arxiv: 2510.16252): Infrastructure for scalable RL training
  - 200+ parallel environments, 5x faster launch
- **CUA-Gym** (arxiv: 2605.25624): 32K verified RLVR tuples across 110 environments

### 5.6 Distillation / Small-Model Approaches

**Agent-as-Annotators** (arxiv: 2604.07776):
- 9B student from Gemini 3 Pro teacher → **41.5% WebArena**
- Surpasses Claude 3.5 Sonnet (36.0%) and GPT-4o (31.5%)
- Pure SFT on quality-filtered trajectories

**Weasel** (arxiv: 2605.20291, ICML 2026):
- Trajectory selection for efficient training
- 9.7-12.5x training speedups with OOD improvements
- Works with Qwen2.5-7B, Gemma3-4B, Qwen3-8B

**WebServ 4B** (arxiv: 2510.16252):
- RL-trained Qwen3-4B: **55.5%** (surpasses Claude 4.5 Sonnet 50.0%)
- Proves small models with good RL training can beat large proprietary models

**ContextCurator** (arxiv: 2604.11462):
- 7B context management model matches GPT-4o performance
- Demonstrates specialized small models can handle sub-tasks effectively

**PolySkill** (arxiv: 2510.15863):
- Polymorphic skill abstraction: decouple goal from implementation
- +13.9% on unseen websites; +1.7x skill reuse on seen sites
- Generalizable skills across different websites

### 5.7 AutoSurfer (arxiv: 2604.27253)
- **Breadth-first exploration** of websites (vs random walk)
- Queue-based page discovery, propagates knowledge across pages
- Trajectory-guided task synthesis reduces hallucinations
- 24.23% on WebArena (SOTA for synthetic data generation approaches)

### 5.8 WebXSkill (arxiv: 2604.13318)
- **Executable skills**: parameterized action programs + step-level NL guidance
- 3 stages: skill extraction → skill organization (URL-based graph) → skill deployment
- Grounded mode (fully automated) and guided mode (step-by-step instructions)
- +9.8pp on WebArena, +12.9pp on WebVoyager

---

## 6. Cross-Cutting Themes & What Separates Top Agents

### The Fundamental Architecture Shift (2024 → 2026)

**Phase 1 (2023-2024)**: Prompt engineering on frontier models
- GPT-4 with ReAct, chain-of-thought, accessibility tree → 14.41% WebArena
- SeeAct with GPT-4V → 51.1% with oracle grounding

**Phase 2 (2024-2025)**: RL fine-tuning of open models
- WebRL: 4.8% → 42.4% (Llama-3.1-8B) via curriculum RL
- AutoGLM: progressive RL with intermediate interfaces → 55.2%

**Phase 3 (2025-2026)**: Specialized training infrastructure + dense rewards
- CUA-Gym: 32K verified RLVR tuples → 72.6% OSWorld-Verified
- WebServ: Full-stack RL infrastructure → 55.5% with 4B model
- MiRA: Milestone-based rewards → 43.0% with 12B model

**Phase 4 (2026)**: Plan-then-execute, self-evolving agents, environment-aware architectures
- Plan-MCTS: Search in plan space, not action space
- OS-Symphony: Orchestrator + reflection-memory + multimodal search
- APEX: Self-evolving strategy maps for sustained exploration

### Critical Success Factors

1. **RL Training is Non-Negotiable**: Every top agent uses RL. Pure prompting maxes out at ~35%.
2. **Dense Rewards Beat Sparse**: Milestone/process rewards >> outcome-only rewards.
3. **Planning Architecture Matters**: Hierarchical planning, subgoal decomposition, plan-space search.
4. **Observation Space Design**: Functional regions > raw DOM; hybrid (vision+DOM) > single modality.
5. **Training Infrastructure**: Scalable environment parallelism (200+ concurrent envs) enables RL at scale.
6. **Memory Systems**: Persistent memory across steps prevents context loss in long-horizon tasks.
7. **Self-Correction Loops**: Reflection, backtracking, and re-planning mechanisms are essential.
8. **Small Models Can Win**: With proper RL training, 4-9B models beat proprietary frontier models.

### Open Challenges

1. **Grounding gap**: Converting visual/textual plans into precise element interactions
2. **Prompt injection security**: Web content from multiple parties creates attack surface
3. **Dynamic environments**: Handling popups, SPAs, network issues, content drift
4. **Evaluation validity**: "Lucky passes" inflate scores; process-level evaluation needed
5. **Cross-site generalization**: Skills learned on one site don't transfer well
6. **Long-horizon degradation**: Agent drift (overthinking/overacting) in extended tasks
7. **Agentic Web Interface**: Need purpose-built interfaces for agents (not human UIs)

---

## Paper Index (by arxiv ID)

| arxiv ID | Paper | Key Contribution |
|---|---|---|
| 2307.13854 | WebArena | Benchmark environment (812 tasks) |
| 2401.01614 | SeeAct | GPT-4V as generalist web agent, vision+HTML grounding |
| 2404.03648 | AutoWebGLM | HTML simplification, curriculum RL, KDD 2024 |
| 2411.00820 | AutoGLM | Intermediate interface, progressive RL |
| 2411.02337 | WebRL | Self-evolving curriculum RL, ICLR 2025 |
| 2510.03285 | WAREX | Reliability evaluation under real-world conditions |
| 2510.15863 | PolySkill | Polymorphic skill learning for cross-site generalization |
| 2510.16252 | WebServ | Full-stack RL-ready web environment |
| 2510.22732 | WebATLAS | Memory-augmented agent with action simulation |
| 2511.04481 | Sustainable Web Agents | Energy consumption benchmarking |
| 2511.08325 | AgentPRM | Process Reward Models for agents |
| 2506.10953 | Build the web for agents | Agentic Web Interface (AWI) proposal |
| 2601.07779 | OS-Symphony | 65.84% OSWorld, reflection-memory agent |
| 2602.14083 | Plan-MCTS | MCTS in plan space, dual-gating reward |
| 2602.16855 | GUI-Owl-1.5 | Multi-platform GUI agent, 48.4% WebArena |
| 2603.00476 | TOCTOU Vulnerabilities | Security analysis of browser-use agents |
| 2603.19685 | MiRA / Subgoal-driven | Milestone RL rewards, 43.0% WA-Lite |
| 2603.21357 | AgentHER | Hindsight Experience Replay for trajectories |
| 2603.21362 | AdaRubric | Task-adaptive rubrics for reward learning |
| 2603.23610 | Environment Maps | Persistent structured representations |
| 2604.00694 | Unbrowse | Internal APIs vs browser automation (3.6x speedup) |
| 2604.02623 | Poison Memory | Memory poisoning attacks on web agents |
| 2604.07776 | Agent-as-Annotators | 9B model beats GPT-4o via structured distillation |
| 2604.10955 | WebForge | Automated benchmark generation |
| 2604.11462 | ContextCurator | RL-based context management, 7B matches GPT-4o |
| 2604.13318 | WebXSkill | Executable skills for web agents |
| 2604.17821 | WebUncertainty | Dual-level uncertainty MCTS |
| 2604.27253 | AutoSurfer | BFS website exploration for trajectory generation |
| 2605.00528 | SAGA | GPU cluster scheduling for agent workflows |
| 2605.07134 | Region4Web | Functional region DOM reorganization |
| 2605.14290 | Plan-Then-Execute | Security argument against ReAct default |
| 2605.20291 | Weasel | Trajectory selection for OOD generalization, ICML 2026 |
| 2605.21240 | APEX | Strategy maps for self-evolving agents |
| 2605.25624 | CUA-Gym | 32K RLVR tuples, 72.6% OSWorld |
| 2605.26548 | SEC-bench Pro | Security agent benchmark (V8/SpiderMonkey) |
| 2605.29927 | PlanAhead | Plan representation comparison |
