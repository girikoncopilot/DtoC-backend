# AI Engineering Framework Protected Backend

This service is the protected server-side runtime companion for the thin-client VS Code extension.

It now runs on **Python + FastAPI** and keeps the same HTTP contract and planning logic that previously lived in the Node backend.

## Purpose

The extension should stay lightweight and should not ship the proprietary framework source.

This backend provides:

- health checks
- capability discovery
- protected runtime session creation
- Jira-backed requirement retrieval when Jira credentials are configured
- repository-aware planning enrichment from workspace file inventory
- bundled protected framework assets for runtime prompting and guardrails

## Endpoints

- `GET /health`
- `GET /capabilities`
- `POST /runtime/session`

## Environment Variables

- `AEF_HOST` - optional, defaults to `127.0.0.1`
- `AEF_PORT` - optional, defaults to `8787`
- `AEF_API_TOKEN` - optional bearer token for authenticating extension requests
- `AEF_PROJECT_ID` - optional project identifier returned in notices
- `AEF_RUNTIME_VERSION` - optional runtime version label
- `AEF_JIRA_BASE_URL` - Jira site base URL, for example `https://your-domain.atlassian.net`
- `AEF_JIRA_EMAIL` - Jira account email for API access
- `AEF_JIRA_API_TOKEN` - Jira API token for basic auth
- `AEF_JIRA_BEARER_TOKEN` - optional bearer token alternative for Jira access
- `AEF_JIRA_FIELDS` - optional comma-separated Jira fields override

## Run Locally

```bash
cd "/Users/mayankdhyani/Downloads/dtocbackend"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## Docker

```bash
docker build -t dtoc-protected-backend .
docker run --rm -p 8787:8787 --env-file .env dtoc-protected-backend
```

## Extension Configuration Example

In VS Code settings:

- `aiEngineeringFramework.backendUrl` = `http://127.0.0.1:8787`
- `aiEngineeringFramework.healthEndpoint` = `/health`
- `aiEngineeringFramework.capabilitiesEndpoint` = `/capabilities`
- `aiEngineeringFramework.sessionEndpoint` = `/runtime/session`
- `aiEngineeringFramework.apiToken` = same as `AEF_API_TOKEN` if auth is enabled

## Current Behavior

If Jira credentials are configured, the backend attempts to:

- fetch the Jira issue by ID
- extract description text and acceptance-criteria-like custom fields
- extract comments, links, attachments, and Figma links
- use that Jira material as the primary requirement source

If Jira credentials are not configured, the backend falls back to any requirement text supplied by the extension or user.

## Bundled Framework Assets

The backend package uses `framework/` as its single server-side framework source of truth.

These files stay server-side and are not shipped in the `.vsix`.
