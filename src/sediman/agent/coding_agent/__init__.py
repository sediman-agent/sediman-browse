from sediman.agent.coding_agent.agent import CodingAgent, create_coding_agent

CodingSubagent = CodingAgent

from sediman.agent.coding_agent.context import discover_project
from sediman.agent.coding_agent.hooks import (
    HookPipeline,
    HookContext,
    PreHookResult,
    PostHookResult,
    create_default_pipeline,
    secret_detection_pre_hook,
    audit_log_post_hook,
    destructive_command_pre_hook,
    file_size_pre_hook,
)
from sediman.agent.coding_agent.monitor import MonitorResult, MonitorEvent, run_monitor
from sediman.agent.coding_agent.prompts import (
    build_system_prompt,
    build_classification_prompt,
)
from sediman.agent.coding_agent.tools import create_coding_tool_registry
from sediman.agent.coding_agent.types import (
    CodingResult,
    ProjectInfo,
    VerifyResult,
    PlanStep,
    HookContext as HookContextType,
    MonitorResult as MonitorResultType,
    MonitorEvent as MonitorEventType,
)
from sediman.agent.coding_agent.verifier import InlineVerifier, VerifyLoop

__all__ = [
    "CodingAgent",
    "CodingSubagent",
    "create_coding_agent",
    "create_coding_tool_registry",
    "CodingResult",
    "ProjectInfo",
    "VerifyResult",
    "PlanStep",
    "InlineVerifier",
    "VerifyLoop",
    "HookPipeline",
    "HookContext",
    "PreHookResult",
    "PostHookResult",
    "create_default_pipeline",
    "secret_detection_pre_hook",
    "audit_log_post_hook",
    "destructive_command_pre_hook",
    "file_size_pre_hook",
    "run_monitor",
    "MonitorResult",
    "MonitorEvent",
    "discover_project",
    "build_system_prompt",
    "build_classification_prompt",
]
