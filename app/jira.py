from __future__ import annotations

import base64
import os
import re
from typing import Any

import httpx

FIGMA_URL_PATTERN = re.compile(r"https?://(?:www\.)?figma\.com/[^\s)]+", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def _collect_text_from_adf(node: Any, state: dict[str, list[str]]) -> None:
    if not isinstance(node, dict):
        return

    text = node.get("text")
    if isinstance(text, str):
        state["text"].append(text)

    if node.get("type") in {"inlineCard", "link", "smartLink"}:
        attrs = node.get("attrs") or {}
        url = attrs.get("url") or attrs.get("href") or ((attrs.get("data") or {}).get("url")) or node.get("url")
        if isinstance(url, str):
            state["links"].append(url)

    marks = node.get("marks")
    if isinstance(marks, list):
        for mark in marks:
            href = ((mark or {}).get("attrs") or {}).get("href")
            if isinstance(href, str):
                state["links"].append(href)

    content = node.get("content")
    if isinstance(content, list):
        for child in content:
            _collect_text_from_adf(child, state)


def adf_to_text_and_links(value: Any) -> dict[str, Any]:
    if not value:
        return {"text": "", "links": []}

    if isinstance(value, str):
        return {"text": value, "links": list(dict.fromkeys(URL_PATTERN.findall(value)))}

    state = {"text": [], "links": []}
    _collect_text_from_adf(value, state)
    return {
        "text": re.sub(r"\s+", " ", " ".join(state["text"])).strip(),
        "links": list(dict.fromkeys(state["links"])),
    }


def normalize_attachment(attachment: dict[str, Any]) -> dict[str, Any]:
    mime_type = str(
        attachment.get("mimeType")
        or attachment.get("mime_type")
        or attachment.get("contentType")
        or ""
    ).lower()
    filename = str(attachment.get("filename") or attachment.get("name") or "").strip()
    is_image = mime_type.startswith("image/")
    return {
        "id": str(attachment.get("id") or ""),
        "filename": filename,
        "mimeType": mime_type,
        "contentUrl": attachment.get("content") or attachment.get("contentUrl") or "",
        "thumbnailUrl": attachment.get("thumbnail") or attachment.get("thumbnailUrl") or "",
        "classification": "direct_image" if is_image else ("non_visual" if mime_type else "unsupported"),
    }


def normalize_comment(comment: dict[str, Any]) -> dict[str, Any]:
    body = adf_to_text_and_links(comment.get("body") or comment.get("comment") or "")
    author = (((comment.get("author") or {}).get("displayName")) or ((comment.get("author") or {}).get("name")) or "")
    return {"author": author, "text": body["text"], "links": body["links"]}


def infer_acceptance_criteria(fields: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for key, value in (fields or {}).items():
        if value is None:
            continue
        key_lc = key.lower()
        extracted = adf_to_text_and_links(value)["text"]
        if (
            "acceptance" in key_lc
            or "criteria" in key_lc
            or "ac_" in key_lc
            or "technical" in key_lc
            or "notes" in key_lc
        ):
            if extracted:
                candidates.append({"field": key, "text": extracted})
            continue
        if re.search(r"acceptance criteria|^ac[:\s-]", extracted, re.IGNORECASE):
            candidates.append({"field": key, "text": extracted})
    return candidates


def infer_acceptance_criteria_from_comments(comments: list[dict[str, Any]]) -> list[dict[str, str]]:
    inferred: list[dict[str, str]] = []
    for comment in comments:
        if re.search(r"acceptance criteria|criteria|should|must", comment.get("text", ""), re.IGNORECASE):
            inferred.append({
                "field": f"comment:{comment.get('author') or 'unknown'}",
                "text": comment.get("text", ""),
            })
    return inferred


def extract_business_summary(summary: str, description_text: str, acceptance_criteria: list[dict[str, str]]) -> str:
    parts = []
    if summary:
        parts.append(f"Summary: {summary}")
    if description_text:
        parts.append(f"Description: {description_text}")
    if acceptance_criteria:
        joined = " | ".join(f"{item['field']}: {item['text']}" for item in acceptance_criteria)
        parts.append(f"Acceptance Criteria Sources: {joined}")
    return "\n".join(parts)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys([value for value in values if value]))


def _extract_links_from_texts(texts: list[str]) -> list[str]:
    results: list[str] = []
    for text in texts:
        if isinstance(text, str):
            results.extend(URL_PATTERN.findall(text))
    return _unique(results)


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    description = adf_to_text_and_links(fields.get("description") or "")
    comments = [normalize_comment(item) for item in ((fields.get("comment") or {}).get("comments") or [])]
    attachments = [normalize_attachment(item) for item in (fields.get("attachment") or [])]
    acceptance_criteria = infer_acceptance_criteria(fields) + infer_acceptance_criteria_from_comments(comments)
    comment_texts = [comment.get("text", "") for comment in comments]
    links = _unique(
        description["links"]
        + [link for comment in comments for link in comment.get("links", [])]
        + _extract_links_from_texts(comment_texts)
        + _extract_links_from_texts([item["text"] for item in acceptance_criteria])
    )
    figma_links = _unique([match.group(0) for link in links for match in [FIGMA_URL_PATTERN.search(link)] if match])
    summary = str(fields.get("summary") or "").strip()
    return {
        "id": issue.get("key") or "",
        "summary": summary,
        "descriptionText": description["text"],
        "acceptanceCriteria": acceptance_criteria,
        "comments": comments,
        "attachments": attachments,
        "figmaLinks": figma_links,
        "labels": fields.get("labels") if isinstance(fields.get("labels"), list) else [],
        "components": [component.get("name") for component in fields.get("components", []) if component.get("name")],
        "priority": ((fields.get("priority") or {}).get("name")) or "",
        "businessSummary": extract_business_summary(summary, description["text"], acceptance_criteria),
    }


class JiraClient:
    def __init__(self, base_url: str, headers: dict[str, str], fields: str):
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.fields = fields

    async def fetch_issue(self, jira_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/issue/{jira_id}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=self.headers, params={"fields": self.fields})
        if response.status_code >= 400:
            raise RuntimeError(f"Jira fetch failed: {response.status_code} {response.reason_phrase}")
        return normalize_issue(response.json())


def create_jira_client_from_env(env: dict[str, str] | None = None) -> JiraClient | None:
    source = env or os.environ
    base_url = source.get("AEF_JIRA_BASE_URL") or source.get("JIRA_BASE_URL") or ""
    email = source.get("AEF_JIRA_EMAIL") or source.get("JIRA_EMAIL") or ""
    api_token = source.get("AEF_JIRA_API_TOKEN") or source.get("JIRA_API_TOKEN") or ""
    bearer_token = source.get("AEF_JIRA_BEARER_TOKEN") or source.get("JIRA_BEARER_TOKEN") or ""

    if not base_url:
        return None

    fields = source.get("AEF_JIRA_FIELDS") or ",".join([
        "summary",
        "description",
        "comment",
        "attachment",
        "issuelinks",
        "subtasks",
        "labels",
        "components",
        "priority",
    ])

    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    elif email and api_token:
        encoded = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"

    return JiraClient(base_url=base_url, headers=headers, fields=fields)
