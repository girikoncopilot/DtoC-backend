from __future__ import annotations

import re
from pathlib import Path
from typing import Any

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent / "bundled-framework"

FRAMEWORK_PATHS = {
    "copilotInstructions": "copilot-instructions.md",
    "dtoCPrompt": "prompts/DtoC.md",
    "implementJiraPrompt": "prompts/01-implement-jira.prompt.md",
    "requirementToCodePrompt": "prompts/08-requirement-to-code.prompt.md",
    "angularJiraTask": "instructions/orchestration/angular-jira-task.md",
    "planningEngine": "instructions/orchestration/planning-engine.md",
    "executionEngine": "instructions/orchestration/execution-engine.md",
    "validationEngine": "instructions/orchestration/validation-engine.md",
    "outputEngine": "instructions/core/08-output-engine.md",
    "runtimeDefinition": "runtime/runtime-definition.md",
    "fullRuntime": "runtime/01-full-runtime.md",
}

SKILL_RULES = [
    {"skill": "forms", "patterns": [r"form", r"input", r"field", r"validation"]},
    {"skill": "tables", "patterns": [r"table", r"grid", r"column", r"row"]},
    {"skill": "sorting", "patterns": [r"sort", r"ordering"]},
    {"skill": "filtering", "patterns": [r"filter", r"facet"]},
    {"skill": "search", "patterns": [r"search", r"lookup"]},
    {"skill": "uploads", "patterns": [r"upload", r"attachment", r"document", r"file"]},
    {"skill": "preview", "patterns": [r"preview", r"view", r"modal"]},
    {"skill": "accessibility", "patterns": [r"accessibility", r"keyboard", r"screen reader", r"aria"]},
    {"skill": "dashboard", "patterns": [r"dashboard", r"widget"]},
    {"skill": "authentication", "patterns": [r"login", r"authentication", r"authorization", r"permission"]},
]


def _read_file(relative_path: str) -> str:
    return (FRAMEWORK_ROOT / relative_path).read_text(encoding="utf-8")


def _compact_lines(content: str, limit: int = 14) -> list[str]:
    return [line.rstrip() for line in content.splitlines() if line.strip()][:limit]


def _extract_bullet_section(content: str, heading_pattern: str, limit: int = 10) -> list[str]:
    lines = content.splitlines()
    start_index = next((index for index, line in enumerate(lines) if re.search(heading_pattern, line)), -1)
    if start_index == -1:
        return []

    collected: list[str] = []
    for line in lines[start_index + 1 :]:
        if line.startswith("#") and collected:
            break
        if re.match(r"^\s*-\s+", line):
            collected.append(re.sub(r"^\s*-\s+", "", line).strip())
        if len(collected) >= limit:
            break
    return collected


def load_framework() -> dict[str, Any]:
    files = {key: _read_file(relative_path) for key, relative_path in FRAMEWORK_PATHS.items()}
    return {
        "files": files,
        "metadata": {
            "frameworkRoot": str(FRAMEWORK_ROOT),
            "frameworkPaths": FRAMEWORK_PATHS,
        },
    }


def detect_skills(requirement_text: str, workspace_summary: dict[str, Any]) -> list[str]:
    haystack = "\n".join(
        [
            requirement_text or "",
            workspace_summary.get("workspaceName", "") or "",
            *[folder.get("name", "") for folder in workspace_summary.get("folders", [])],
            workspace_summary.get("activeFile", "") or "",
            *workspace_summary.get("fileInventory", []),
            *workspace_summary.get("topLevelEntries", []),
        ]
    )

    detected = []
    for rule in SKILL_RULES:
        if any(re.search(pattern, haystack, re.IGNORECASE) for pattern in rule["patterns"]):
            detected.append(rule["skill"])

    enriched = set(detected)
    haystack_lower = haystack.lower()
    if "correspondence" in haystack_lower:
        enriched.update({"forms", "tables", "uploads"})
    if "attachment" in haystack_lower or "upload" in haystack_lower:
        enriched.add("uploads")
    if "table" in haystack_lower or "column" in haystack_lower:
        enriched.add("tables")

    return list(enriched) if enriched else ["forms", "tables"]


def build_framework_summary(framework: dict[str, Any]) -> dict[str, Any]:
    files = framework["files"]
    return {
        "runtimePhases": _compact_lines(files["fullRuntime"], 26),
        "dtoCEntry": _compact_lines(files["dtoCPrompt"], 12),
        "implementJiraHighlights": _extract_bullet_section(files["implementJiraPrompt"], r"^# Required Input", 8),
        "requirementToCodeRules": _extract_bullet_section(files["requirementToCodePrompt"], r"^# Prompt-Specific Rules", 10),
        "angularExecutionOrder": _compact_lines(files["angularJiraTask"], 26),
        "planningHighlights": _extract_bullet_section(files["planningEngine"], r"^# 11C\. Pre-Implementation Change Approval", 8),
        "executionHighlights": _extract_bullet_section(files["executionEngine"], r"^# 15\. Engineering Rules", 8),
        "validationHighlights": _extract_bullet_section(files["validationEngine"], r"^# 5A\. External Evidence Validation", 8),
    }


def build_protected_prompt(
    jira_id: str,
    requirement_text: str,
    workspace_summary: dict[str, Any],
    detected_skills: list[str],
    framework_summary: dict[str, Any],
) -> str:
    workspace_name = workspace_summary.get("workspaceName") or "Unnamed workspace"
    folder_names = [folder.get("name") for folder in workspace_summary.get("folders", []) if folder.get("name")]
    active_file = workspace_summary.get("activeFile") or "No active file reported"
    requirement_block = requirement_text.strip() if requirement_text else (
        "No Jira requirement text was provided. Ask for acceptance criteria if Jira integration is unavailable."
    )

    lines = [
        f"Use the protected AI Engineering Framework runtime for Jira {jira_id}.",
        "",
        "Execute the Implement Jira Prompt and follow the runtime exactly.",
        "",
        f"Workspace: {workspace_name}",
        f"Folders: {', '.join(folder_names)}" if folder_names else "Folders: none provided",
        f"Active file: {active_file}",
        "",
        "Requirement source:",
        requirement_block,
        "",
        f"Detected required skills: {', '.join(detected_skills)}",
        "",
        "Runtime expectations:",
        *framework_summary["runtimePhases"][:12],
        "",
        "Prompt-specific rules:",
        *[f"- {rule}" for rule in framework_summary["requirementToCodeRules"]],
        "",
        "Planning and approval guardrails:",
        *[f"- {item}" for item in framework_summary["planningHighlights"]],
        "",
        "Validation focus:",
        *[f"- {item}" for item in framework_summary["validationHighlights"]],
        "",
        "Treat backend-issued workflow output as authoritative.",
        "If Jira details are missing, request acceptance criteria before implementation.",
        "If design evidence exists, preserve layout, spacing, grouping, and hierarchy.",
    ]
    return "\n".join(lines)
