from __future__ import annotations

import time
from typing import Any

from app.framework import build_framework_summary, build_protected_prompt, detect_skills, load_framework
from app.jira import create_jira_client_from_env
from app.repository_planner import enrich_repository_plan


def normalize_jira_id(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_workspace(workspace: dict[str, Any] | None) -> dict[str, Any]:
    source = workspace or {}
    folders = source.get("folders") if isinstance(source.get("folders"), list) else []
    return {
        "workspaceName": str(source.get("workspaceName") or "").strip(),
        "folders": [
            {"name": str(folder.get("name") or "").strip(), "path": str(folder.get("path") or "").strip()}
            for folder in folders
        ],
        "activeFile": str(source.get("activeFile") or "").strip(),
        "fileInventory": source.get("fileInventory") if isinstance(source.get("fileInventory"), list) else [],
        "topLevelEntries": source.get("topLevelEntries") if isinstance(source.get("topLevelEntries"), list) else [],
        "buildFiles": source.get("buildFiles") if isinstance(source.get("buildFiles"), list) else [],
    }


def build_implementation_hints(requirement_text: str, detected_skills: list[str], workspace_summary: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    if not workspace_summary.get("workspaceName"):
        hints.append("Open the target repository workspace before implementation so repository analysis can be grounded in real files.")
    if not requirement_text:
        hints.append("No acceptance criteria were provided. Ask for Jira details or pasted requirements before implementation.")
    if "uploads" in detected_skills:
        hints.append("Check attachment handling, file validation, and repository-native upload patterns.")
    if "tables" in detected_skills:
        hints.append("Inspect existing table patterns, displayed columns, and repository-native pagination/sorting behavior.")
    if "forms" in detected_skills:
        hints.append("Reuse repository-native form controls and validate field grouping against design evidence when present.")
    return hints


def build_planned_changes(repository_plan: dict[str, Any], jira_issue: dict[str, Any] | None, detected_skills: list[str]) -> list[str]:
    planned = [f"Modify: {file_path}" for file_path in repository_plan.get("filesToModify", [])]
    if "tables" in detected_skills:
        planned.append("Validate displayed columns and data-source bindings for table changes.")
    if "uploads" in detected_skills:
        planned.append("Review upload validation, attachment handling, and backend header/data flow.")
    if jira_issue and jira_issue.get("figmaLinks"):
        planned.append("Attempt Figma retrieval for discovered design links before UI implementation.")
    return planned


async def create_runtime_session(body: dict[str, Any], runtime_version: str, project_id: str) -> dict[str, Any]:
    jira_client = create_jira_client_from_env()
    jira_id = normalize_jira_id(body.get("jiraId"))
    jira_issue = await jira_client.fetch_issue(jira_id) if jira_client else None
    framework = load_framework()
    framework_summary = build_framework_summary(framework)
    workflow = str(body.get("workflow") or "DtoC").strip() or "DtoC"
    requirement_text = str(
        body.get("requirementText")
        or body.get("requirements")
        or ((jira_issue or {}).get("businessSummary"))
        or ((jira_issue or {}).get("descriptionText"))
        or ""
    ).strip()
    workspace_summary = normalize_workspace(body.get("workspace"))
    detected_skills = detect_skills(requirement_text, workspace_summary)
    repository_plan = enrich_repository_plan(workspace_summary, jira_issue, requirement_text, detected_skills)
    implementation_hints = build_implementation_hints(requirement_text, detected_skills, workspace_summary)
    planned_changes = build_planned_changes(repository_plan, jira_issue, detected_skills)

    notices = [
        f"Using protected runtime {runtime_version}.",
        f"Project context: {project_id}." if project_id else "No backend project id configured.",
        (
            f"Jira retrieval succeeded for {jira_issue['id']}."
            if jira_issue
            else "Requirement text supplied directly to backend session."
            if requirement_text
            else "No Jira requirement text supplied. Backend will require acceptance criteria before implementation."
        ),
    ]
    if jira_issue and jira_issue.get("figmaLinks"):
        notices.append(f"Discovered Figma links: {', '.join(jira_issue['figmaLinks'])}")

    return {
        "sessionId": f"session_{int(time.time() * 1000)}",
        "workflow": workflow,
        "jiraId": jira_id,
        "chatCommand": f"/DtoC {jira_id}",
        "promptText": build_protected_prompt(jira_id, requirement_text, workspace_summary, detected_skills, framework_summary),
        "notices": notices,
        "requirementStatus": {
            "hasRequirementText": bool(requirement_text),
            "requiresUserInput": not bool(requirement_text),
            "source": "jira" if jira_issue else ("direct-input" if requirement_text else "missing"),
        },
        "frameworkContext": {
            "runtimeEntry": "Implement Jira Prompt",
            "dtoCPrompt": "DtoC",
            "detectedSkills": detected_skills,
            "projectOptimized": True,
        },
        "implementationHints": implementation_hints,
        "plannedChanges": planned_changes,
        "runtimeChecklist": [
            "Repository Analysis",
            "Jira Analysis",
            "Feature Detection",
            "Context Resolution",
            "Planning",
            "Implementation",
            "Testing",
            "Validation",
            "Review",
            "Launch",
        ],
        "sourcePriorities": [
            "Jira acceptance criteria",
            "Repository architecture and reuse map",
            "Approved design evidence",
            "Framework runtime rules",
        ],
        "jira": jira_issue,
        "repositoryPlan": repository_plan,
    }
