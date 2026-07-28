from __future__ import annotations

import re
from typing import Any


def _normalize_workspace(workspace: dict[str, Any] | None) -> dict[str, Any]:
    source = workspace or {}
    return {
        "workspaceName": str(source.get("workspaceName") or "").strip(),
        "activeFile": str(source.get("activeFile") or "").strip(),
        "folders": source.get("folders") if isinstance(source.get("folders"), list) else [],
        "fileInventory": source.get("fileInventory") if isinstance(source.get("fileInventory"), list) else [],
        "topLevelEntries": source.get("topLevelEntries") if isinstance(source.get("topLevelEntries"), list) else [],
        "buildFiles": source.get("buildFiles") if isinstance(source.get("buildFiles"), list) else [],
    }


def _dirname(file_path: str) -> str:
    normalized = str(file_path or "").replace("\\", "/")
    index = normalized.rfind("/")
    return "" if index == -1 else normalized[:index]


def _basename(file_path: str) -> str:
    normalized = str(file_path or "").replace("\\", "/")
    index = normalized.rfind("/")
    return normalized if index == -1 else normalized[index + 1 :]


def _score_file(file_path: str, keywords: list[str]) -> int:
    target = file_path.lower()
    score = 0
    for keyword in keywords:
        if keyword in target:
            score += 2
        if target.endswith(f"{keyword}.ts") or target.endswith(f"{keyword}.html") or target.endswith(f"{keyword}.scss"):
            score += 1
    return score


def _normalize_relative_path(file_path: str, workspace: dict[str, Any]) -> str:
    raw = str(file_path or "").strip()
    if not raw:
        return ""
    for folder in workspace.get("folders", []):
        folder_path = str(folder.get("path") or "")
        if folder_path and raw.startswith(folder_path):
            return re.sub(r"^/+", "", raw[len(folder_path):])
    return raw


def _extract_keywords(jira_issue: dict[str, Any] | None, requirement_text: str, active_file: str) -> list[str]:
    inputs = " ".join([
        jira_issue.get("summary", "") if jira_issue else "",
        jira_issue.get("descriptionText", "") if jira_issue else "",
        requirement_text or "",
        active_file or "",
    ]).lower()
    raw_words = re.findall(r"[a-z0-9_-]{4,}", inputs)
    stop_words = {
        "that", "with", "from", "this", "have", "will", "when", "should", "into", "using",
        "user", "jira", "runtime", "acceptance", "criteria", "repository",
    }
    ordered = []
    for word in raw_words:
        if word not in stop_words and word not in ordered:
            ordered.append(word)
    return ordered[:12]


def _detect_repo_type(workspace: dict[str, Any]) -> str:
    build_files = [str(entry).lower() for entry in workspace.get("buildFiles", [])]
    top_level = [str(entry).lower() for entry in workspace.get("topLevelEntries", [])]
    inventory = [str(entry).lower() for entry in workspace.get("fileInventory", [])]
    if any("angular.json" in entry for entry in build_files) or "angular.json" in top_level or "angular.json" in inventory:
        return "angular"
    if "package.json" in top_level:
        return "node"
    return "unknown"


def _derive_sibling_files(active_file: str, inventory: list[str]) -> list[str]:
    current = str(active_file or "").strip()
    if not current:
        return []
    file_name = _basename(current)
    folder_path = _dirname(current)
    lower_inventory = [str(entry).replace("\\", "/") for entry in inventory]
    inventory_set = set(lower_inventory)
    siblings: set[str] = set()
    if folder_path:
        for file_path in lower_inventory:
            if _dirname(file_path) == folder_path:
                siblings.add(file_path)
    if file_name.endswith(".component.ts"):
        base = current[:-3]
        for candidate in [f"{base}.html", f"{base}.scss", f"{base}.css", f"{base}.spec.ts"]:
            if candidate in inventory_set:
                siblings.add(candidate)
    return [item for item in siblings if item]


def _derive_project_support_files(inventory: list[str], detected_skills: list[str]) -> list[str]:
    results: set[str] = set()
    lower_inventory = [str(entry).replace("\\", "/") for entry in inventory]
    for file_path in lower_inventory:
        if re.search(r"labels\.json$", file_path, re.IGNORECASE):
            results.add(file_path)
        if re.search(r"service", file_path, re.IGNORECASE) and "uploads" in detected_skills:
            results.add(file_path)
        if re.search(r"module\.ts$", file_path, re.IGNORECASE) and "forms" in detected_skills:
            results.add(file_path)
    return list(results)


def _infer_build_run_commands(repo_type: str, top_level_entries: list[str]) -> dict[str, str]:
    if repo_type == "angular":
        package_managers = [entry.lower() for entry in top_level_entries]
        if "pnpm-lock.yaml" in package_managers:
            return {"build": "pnpm run build", "run": "pnpm start", "preview": "ngrok http 4200"}
        if "yarn.lock" in package_managers:
            return {"build": "yarn build", "run": "yarn start", "preview": "ngrok http 4200"}
        return {"build": "npm run build", "run": "npm start", "preview": "ngrok http 4200"}
    return {"build": "Determine from repository", "run": "Determine from repository", "preview": "Determine from repository"}


def enrich_repository_plan(
    workspace: dict[str, Any] | None,
    jira_issue: dict[str, Any] | None,
    requirement_text: str,
    detected_skills: list[str],
) -> dict[str, Any]:
    normalized = _normalize_workspace(workspace)
    repo_type = _detect_repo_type(normalized)
    keywords = _extract_keywords(jira_issue, requirement_text, normalized.get("activeFile", ""))
    normalized_inventory = [_normalize_relative_path(file_path, normalized) for file_path in normalized.get("fileInventory", [])]
    active_file = _normalize_relative_path(normalized.get("activeFile", ""), normalized)
    sibling_files = _derive_sibling_files(active_file, normalized_inventory)
    support_files = _derive_project_support_files(normalized_inventory, detected_skills)

    ranked_files = [
        {"filePath": file_path, "score": _score_file(file_path, keywords)}
        for file_path in normalized_inventory
    ]
    ranked_files = [entry for entry in ranked_files if entry["score"] > 0]
    ranked_files.sort(key=lambda item: item["score"], reverse=True)
    ranked_files = [entry["filePath"] for entry in ranked_files[:12]]

    files_to_inspect = []
    for file_path in [active_file, *sibling_files, *support_files, *ranked_files]:
        if file_path and file_path not in files_to_inspect:
            files_to_inspect.append(file_path)

    build_run = _infer_build_run_commands(repo_type, normalized.get("topLevelEntries", []))
    likely_areas = [
        "Angular feature modules and shared components" if repo_type == "angular" else "Project source tree",
        "Form controls and validation flows" if "forms" in detected_skills else "",
        "Table/grid rendering and displayed columns" if "tables" in detected_skills else "",
        "Upload flows and attachment handling" if "uploads" in detected_skills else "",
    ]
    likely_areas = [item for item in likely_areas if item]

    files_to_modify = [file_path for file_path in files_to_inspect if re.search(r"\.(ts|html|scss|css|json)$", file_path, re.IGNORECASE)]

    reuse_map: list[str] = []
    if any(re.search(r"service", file_path, re.IGNORECASE) for file_path in files_to_inspect):
        reuse_map.append("Reuse existing services before introducing new data flows.")
    if any(re.search(r"component", file_path, re.IGNORECASE) for file_path in files_to_inspect):
        reuse_map.append("Extend existing feature components before creating new ones.")
    if repo_type == "angular":
        reuse_map.append("Preserve Angular module/component structure and repository-native form/table patterns.")

    return {
        "repoType": repo_type,
        "filesToInspect": files_to_inspect,
        "filesToModify": files_to_modify,
        "likelyAreas": likely_areas,
        "buildRun": build_run,
        "keywords": keywords,
        "reuseMap": reuse_map,
    }
