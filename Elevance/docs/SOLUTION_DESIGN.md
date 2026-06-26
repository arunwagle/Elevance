# Carelon App — Solution Design Document

**Version:** 1.0  
**Last Updated:** June 2026  
**Author:** Arun Wagle  
**Platform:** Databricks Apps (AWS)  
**Runtime:** Python Flask + Gunicorn on Serverless Compute

---

## 1. System Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                               │
│   [SSO Login] → [Dashboard] → [Upload Wizard | File Explorer | Admin] │
└─────────────────────────────────┬───────────────────────────────────┘
                                    │ HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│          DATABRICKS APPS REVERSE PROXY                             │
│  • Authenticates user via enterprise SSO/IdP                        │
│  • Injects: X-Forwarded-Email, X-Forwarded-User                     │
│  • Injects: X-Forwarded-Access-Token (OAuth, files scope)           │
└─────────────────────────────────┬───────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                CARELON APP (Flask + Gunicorn)                        │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Routes      │  │ Services    │  │ Middleware                │  │
│  │ (Blueprints)│  │ (Business  │  │ • @login_required          │  │
│  │             │  │  Logic)     │  │ • @require_permission      │  │
│  │             │  │            │  │ • @require_admin           │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│         │                │                                            │
│         ▼                ▼                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Templates   │  │ Static/JS   │  │ Models                    │  │
│  │ (Jinja2)    │  │ (Frontend) │  │ (Dataclasses)             │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │                       │                        │
         ▼                       ▼                        ▼
┌───────────────┐  ┌───────────────────┐  ┌──────────────────┐
│ Unity Catalog │  │ Files API (REST)   │  │ SQL Statement    │
│ Volumes       │  │ (User Token)       │  │ API (SP Token)   │
└───────────────┘  └───────────────────┘  └──────────────────┘
```

### 1.2 Component Overview

| Component | Technology | Responsibility |
|-----------|-----------|----------------|
| Frontend | Vanilla JS + Jinja2 HTML | UI rendering, client-side parsing, caching |
| Backend | Python Flask | API endpoints, business logic, file operations |
| Auth Layer | Databricks Apps Proxy | SSO authentication, token injection |
| Storage | Unity Catalog Volumes | Tokenized file storage |
| Metadata | Delta Tables | Permissions, assignments, audit log |
| Compute | Gunicorn on Apps Serverless | Request handling, concurrent users |

---

## 2. Authentication & Authorization

### 2.1 Authentication Flow

```
User Browser → Databricks Apps Proxy → Flask App
                    │
                    ├─ X-Forwarded-Email: user@company.com
                    ├─ X-Forwarded-User: User Name
                    ├─ X-Forwarded-Access-Token: eyJ...
                    └─ X-Forwarded-Preferred-Username: user@company.com
```

**No login form required.** The Databricks Apps reverse proxy handles SSO/IdP authentication and injects user identity headers into every request.

### 2.2 Session Creation

```python
# auth_service.py: create_session()
session['email'] = headers['X-Forwarded-Email']
session['username'] = headers['X-Forwarded-User']
session['groups'] = resolve_groups(email)  # from platform
session['is_admin'] = 'admin' in groups
```

### 2.3 Authorization Model

```
Request → @login_required → @require_permission('action') → Route Handler
              │                        │
              │                        ├─ Check session exists
              │                        ├─ Query permission_assignments table
              │                        └─ Verify action + resource_path match
              │
              └─ If admin route: @require_admin
                   ├─ session['is_admin'] == True?
                   ├─ 'admin' in session['groups']?
                   └─ email in ADMIN_USERS config?
```

### 2.4 Dual Token Strategy

| Token Type | Source | Used For |
|-----------|--------|----------|
| User Token | X-Forwarded-Access-Token | Volume file operations (read/write/delete), directory listing |
| SP Token | client_credentials flow | SQL queries (permission lookups), Jobs API, Clusters API |

---

## 3. Upload & Tokenization Pipeline

### 3.1 Sequence Diagram

```
Browser (upload.js)                    Flask (/upload/tokenize)           Volume (Files API)
       │                                        │                              │
       │── Step 1: Select data file ─────────▶│                              │
       │   (client-side, no upload yet)         │                              │
       │                                        │                              │
       │── Step 2: Select processing template ─▶│                              │
       │   (client-side, SheetJS parse)         │                              │
       │                                        │                              │
       │── Step 3: Build parsed preview ──────▶│                              │
       │   (fixed-width parse using Start/End)  │                              │
       │   Identify PHI cols (phiType ≠ "")     │                              │
       │   Store: parsedHeaders, parsedDataRows │                              │
       │          phiColumnNames, phiColumnTypes │                              │
       │                                        │                              │
       │── Step 4: Select Protegrity template ─▶│                              │
       │                                        │                              │
       │── Step 5: Select target folder ──────▶│                              │
       │   (loadPermittedFolders -> cards)      │                              │
       │                                        │                              │
       │── Click "Upload & Tokenize" ─────────▶│                              │
       │   POST /upload/tokenize                │                              │
       │   { headers, rows, phi_columns,        │                              │
       │     phi_indices, phi_types,             │                              │
       │     volume_path, original_filename }    │                              │
       │                                        │                              │
       │                                        │── Protegrity API call        │
       │                                        │   (POC: mock masking)        │
       │                                        │   (Prod: DSG /protect)       │
       │                                        │   Only PHI cols w/ phi_type  │
       │                                        │                              │
       │                                        │── Build pipe-delimited CSV   │
       │                                        │                              │
       │                                        │── PUT /api/2.0/fs/files/ ───▶│
       │                                        │   {name}_tokenized.txt       │
       │                                        │                              │
       │◀── 200 { output_path, rows, cols } ──┤                              │
       │                                        │                              │
```

### 3.2 Tokenization Logic

#### Production Architecture (Phase 4 — Protegrity DSG)

In production, tokenization and detokenization are performed by the **Protegrity Data Security Gateway (DSG)** REST API:

```python
# upload_routes.py — Production flow (Phase 4)
def _protegrity_api_call(headers, rows, phi_columns, phi_indices, phi_types, template):
    """
    Calls Protegrity DSG REST API to tokenize PHI columns.
    
    Endpoint: POST https://<protegrity-host>/api/v1/protect
    Payload: { "data_elements": [...], "policy": "<from_template>", "values": [...] }
    Returns: tokenized values from DSG vault (reversible via /api/v1/unprotect)
    """
    dsg_host = os.environ.get('PROTEGRITY_DSG_HOST')
    api_key = os.environ.get('PROTEGRITY_API_KEY')  # From Databricks Secrets
    
    # Map phi_types to Protegrity data elements
    elements = [{"name": col, "type": ptype} for col, ptype in zip(phi_columns, phi_types)]
    
    # Call DSG protect endpoint
    response = requests.post(
        f"{dsg_host}/api/v1/protect",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"data_elements": elements, "policy": template['policy_id'], "records": rows}
    )
    return response.json()['tokenized_records'], response.json()['metadata']
```

#### POC Implementation (Current — Phase 1)

For the POC, the Protegrity API is **mocked with deterministic masking functions**:

```python
# upload_routes.py — POC mock (current implementation)
def _mock_protegrity_api_call(headers, rows, phi_columns, phi_indices, phi_types):
    """
    POC ONLY: Simulates Protegrity DSG response with pattern-based masking.
    
    LIMITATIONS vs Production:
    - Masking is one-way (cannot be reversed — no vault)
    - Deterministic output (same input → same output)
    - No encryption key management
    - No policy enforcement from DSG
    """
    tokenized_rows = []
    for row in rows:
        new_row = list(row)
        for col_idx, phi_type in zip(phi_indices, phi_types):
            if col_idx < len(new_row):
                new_row[col_idx] = _mask_value(new_row[col_idx], phi_type)
        tokenized_rows.append(new_row)
    return tokenized_rows, metadata
```

**Key design decisions:**
1. Masking function is determined by the `phi_type` declared in the template, NOT by guessing from column names
2. If a column has no `phi_type`, it is never masked
3. The interface contract (input/output format) is identical for POC and Production — only the implementation changes
4. In Production, the Tokenization Template (Step 4) provides the `policy_id` for the Protegrity DSG call

### 3.3 Detokenization Logic

#### Production (Phase 4 — Protegrity DSG)

```python
# file_ops_routes.py — Production detokenize flow
def detokenize_file():
    # 1. Read tokenized file from Volume
    tokenized_content = fetch_file_from_volume(file_path)
    
    # 2. Call Protegrity DSG unprotect endpoint
    response = requests.post(
        f"{dsg_host}/api/v1/unprotect",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"tokenized_records": parsed_rows, "policy": policy_id}
    )
    original_data = response.json()['original_records']
    
    # 3. Stream to user — NEVER store
    return Response(original_data, mimetype='text/plain',
                    headers={'X-Never-Stored': 'true'})
```

#### POC (Current — Phase 1)

```python
# file_ops_routes.py — POC mock detokenize
def detokenize_file():
    # POC: Cannot truly reverse the masking (no vault)
    # Returns file content as-is with a "mock detokenized" marker
    tokenized_content = fetch_file_from_volume(file_path)
    return Response(tokenized_content, mimetype='text/plain',
                    headers={'X-Detokenized': 'true', 'X-Never-Stored': 'true'})
```

> ⚠️ **POC vs Production:** In the POC, "detokenize" returns the tokenized file content unchanged because the mock masking has no reversible vault. In Production, Protegrity DSG maintains the token-to-original mapping and can recover the true PHI values.

---

## 4. File Explorer Design

### 4.1 Two-Panel Layout

```
┌───────────────────┬─┬─────────────────────────────────────────────┐
│  FOLDER TREE       │◤│  FILE LIST + PERMISSIONS                        │
│                    │ │                                               │
│  ▼ dxutility       │ │  Breadcrumb: Root › claims › 2024             │
│    ▶ claims        │R│  Perms: [Browse] [Upload] [Download] [Delete] │
│    ▼ eligibility   │e│                                               │
│      ▶ 2024        │s│  ┌────┬──────────────┬─────┬───────┬───────┬────┐│
│      ▶ 2025        │i│  │Icon│ Name         │Size │Perms  │Actions│    ││
│    ▶ pharmacy      │z│  ├────┼──────────────┼─────┼───────┼───────┼────┤│
│    ▶ test          │e│  │ 📁 │ subfolder_a  │  —  │[Brws] │  —    │    ││
│                    │r│  │ 📊 │ data.csv     │ 2MB │[All]  │ ⬇ 👁 🗑│    ││
│  [Refresh ↻]       │ │  │ 📄 │ claims_tok.. │ 1MB │[All]  │ ⬇ 👁 🗑│    ││
│                    │ │  └────┴──────────────┴─────┴───────┴───────┴────┘│
└───────────────────┴─┴─────────────────────────────────────────────┘
```

### 4.2 API Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/files/` | GET | Render File Explorer page | @login_required |
| `/files/api/my-access` | GET | User's permitted folders + actions (admin override) | @login_required |
| `/files/api/tree?path=` | GET | Lazy-load child folders for tree expansion | @login_required |
| `/files/api/list?folder_path=` | GET | List files + subfolders in a folder | @login_required |
| `/files/api/download?file_path=` | GET | Stream file download | @login_required |
| `/files/api/delete?file_path=` | DELETE | Delete a file | @login_required |

### 4.3 Admin Access Logic

```python
def _is_admin():
    if session.get('is_admin'):    return True
    if 'admin' in session.get('groups', []): return True
    email = _get_user_email()
    return email.lower() in [e.lower() for e in current_app.config.get('ADMIN_USERS', [])]

# In get_my_access():
if _is_admin():
    return _get_admin_all_folders(user_email)  # ALL folders, ALL actions
else:
    return query_permission_assignments(user_email)  # Only assigned folders
```

---

## 5. Caching Architecture

### 5.1 Multi-Layer Cache Design

```
User Request
    │
    ▼
┌─────────────────────────────────────────┐
│ Layer 1: Frontend Cache (JS)          │
│ TTL: 90 seconds                       │
│ Scope: Per-path (tree, my-access, list)│
│ Invalidation: Refresh btn, delete      │
│                                        │
│ Cache Hit? ──▶ Return immediately      │
└────────────────┬───────────────────────┘
                 │ Cache Miss
                 ▼
┌─────────────────────────────────────────┐
│ Layer 2: Backend Cache (Python)        │
│ TTL: 90 seconds                       │
│ Scope: Per-path directory listing      │
│ Thread-safe: threading.Lock            │
│ Invalidation: On folder creation       │
│                                        │
│ Cache Hit? ──▶ Return immediately      │
└────────────────┬───────────────────────┘
                 │ Cache Miss
                 ▼
┌─────────────────────────────────────────┐
│ Databricks Files API                   │
│ GET /api/2.0/fs/directories/{path}     │
│                                        │
│ 429? ──▶ Retry with exponential backoff │
│         (3 attempts, Retry-After header)│
└─────────────────────────────────────────┘
```

### 5.2 Cache Keys

| Cache | Key Format | Example |
|-------|-----------|--------|
| Backend directory | `dir:{full_path}` | `dir:/Volumes/cat/schema/vol/claims` |
| Frontend tree | `tree:{path}` | `tree:/Volumes/cat/schema/vol/claims` |
| Frontend my-access | `my-access` | (singleton) |
| Frontend file list | `{folder_path}` | `/Volumes/cat/schema/vol/claims` |
| Upload permitted folders | `_permFoldersCache` | (singleton, 90s) |

### 5.3 Rate Limit Handling

```
HTTP 429 received
    │
    ├─ Read Retry-After header (or use default backoff)
    ├─ Wait: attempt * INITIAL_BACKOFF_SEC
    ├─ Retry (up to MAX_RETRIES)
    │
    └─ After all retries exhausted:
       Frontend: "Rate limit reached. Please wait and try again."
       Backend: Return error with helpful message
```

---

## 6. Security Design

### 6.1 Token Flow

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ User OAuth  │ ─▶ │ Volume Ops      │     │ Files API       │
│ Token       │     │ (Read/Write/Del)│ ─▶ │ (User identity) │
└─────────────┘     └─────────────────┘     └─────────────────┘

┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ SP Token    │ ─▶ │ Admin Ops       │     │ SQL Statement   │
│ (client_    │     │ (Permissions,   │ ─▶ │ API + Jobs API  │
│ credentials)│     │  Jobs, ABAC)    │     │ (SP identity)   │
└─────────────┘     └─────────────────┘     └─────────────────┘
```

### 6.2 Permission Resolution

```sql
-- Non-admin: Query permission_assignments for user's folders
SELECT DISTINCT resource_path, action
FROM permission_assignments
WHERE permission_type = 'files'
  AND is_active = TRUE
  AND (entity_name = '{user_email}' OR entity_type = 'group')
```

### 6.3 PHI Data Protection

1. **Never stored in original form** — raw PHI exists only in the client browser during preview
2. **Tokenized before upload** — backend calls Protegrity DSG (or POC mock) to tokenize PHI columns before writing to Volume
3. **Detokenization is download-only** — in Production, Protegrity DSG reverses tokens; result is streamed to browser, NEVER persisted to disk or Volume
4. **Audit trail** — every tokenization and detokenization event logged with user, file, columns, and timestamp
5. **Protegrity vault isolation** — only the DSG holds the token-to-original mapping; the app never sees or stores encryption keys
6. **POC safety** — even in mock mode, the same security constraints apply (no-store headers, audit logging, permission checks)

---

## 7. API Contract Details

### 7.1 POST /upload/tokenize

**Request:**
```json
{
  "headers": ["MEMBER_ID", "FIRST_NAME", "SSN", "DOB", "ADDRESS", "CLAIM_AMT"],
  "rows": [
    ["MBR001", "John", "123-45-6789", "1990-05-15", "123 Main St", "1500.00"],
    ["MBR002", "Jane", "987-65-4321", "1985-03-22", "456 Oak Ave", "2300.50"]
  ],
  "phi_columns": ["MEMBER_ID", "FIRST_NAME", "SSN", "DOB", "ADDRESS"],
  "phi_indices": [0, 1, 2, 3, 4],
  "phi_types": ["Member_ID", "Name", "SSN", "DOB", "Address"],
  "volume_path": "/Volumes/aw_serverless_stable_catalog/carelon/dxutility/claims",
  "original_filename": "claims_q1.dat"
}
```

**Response (200):**
```json
{
  "message": "File tokenized and uploaded successfully.",
  "output_path": "/Volumes/.../claims/claims_q1_tokenized.txt",
  "output_filename": "claims_q1_tokenized.txt",
  "rows_processed": 2,
  "columns_tokenized": ["MEMBER_ID", "FIRST_NAME", "SSN", "DOB", "ADDRESS"],
  "phi_types_applied": {
    "MEMBER_ID": "Member_ID",
    "FIRST_NAME": "Name",
    "SSN": "SSN",
    "DOB": "DOB",
    "ADDRESS": "Address"
  },
  "total_columns": 6,
  "file_size_bytes": 245,
  "protegrity_response": {
    "api_endpoint": "https://protegrity-dsg.mock.internal/api/v1/tokenize",
    "policy_applied": "CARELON_PHI_MASKING_v1",
    "tokens_generated": 10,
    "status": "SUCCESS"
  }
}
```

**Output file content (claims_q1_tokenized.txt):**
```
MEMBER_ID|FIRST_NAME|SSN|DOB|ADDRESS|CLAIM_AMT
TOK_7B3A9F2C1E04|J***|***-**-6789|****-**-** (1990)|123 **** **|1500.00
TOK_E1D4A8B7C930|J***|***-**-4321|****-**-** (1985)|456 *** ***|2300.50
```

Note: `CLAIM_AMT` (no phi_type) passes through unchanged.

### 7.2 GET /api/volumes/permitted-folders

**Response (Admin):**
```json
{
  "folders": [
    {"path": "/Volumes/.../dxutility/claims", "display_name": "claims", "entity_type": "admin"},
    {"path": "/Volumes/.../dxutility/eligibility", "display_name": "eligibility", "entity_type": "admin"}
  ],
  "is_admin": true
}
```

**Response (Non-admin):**
```json
{
  "folders": [
    {"path": "/Volumes/.../dxutility/test", "display_name": "test", "entity_name": "user@co.com", "entity_type": "user"}
  ]
}
```

### 7.3 GET /files/api/my-access

**Response:**
```json
{
  "folders": [
    {
      "path": "/Volumes/.../dxutility/test",
      "display_name": "test",
      "actions": ["browse", "delete", "detokenize", "download", "preview", "share", "upload"]
    }
  ],
  "user": "arun.wagle@databricks.com",
  "is_admin": true
}
```

---

## 8. Deployment Architecture

### 8.1 Runtime Configuration

```yaml
# app.yaml
command:
  - gunicorn
  - app:create_app()
env:
  - name: DATABRICKS_SQL_WAREHOUSE_ID
    value: "2d8e531640ffa469"
  - name: ADMIN_USERS
    value: "arun.wagle@databricks.com"
```

```python
# gunicorn.conf.py
import os
bind = f"0.0.0.0:{os.environ.get('DATABRICKS_APP_PORT', '8000')}"
workers = 2
threads = 4
timeout = 120
```

### 8.2 Environment Variables

| Variable | Source | Purpose |
|----------|--------|--------|
| DATABRICKS_HOST | Platform-injected | Workspace URL |
| DATABRICKS_CLIENT_ID | Platform-injected | SP client ID |
| DATABRICKS_CLIENT_SECRET | Platform-injected | SP secret |
| DATABRICKS_SQL_WAREHOUSE_ID | app.yaml | SQL warehouse for permission queries |
| DATABRICKS_APP_PORT | Platform-injected | Port to bind Gunicorn |
| ADMIN_USERS | app.yaml | Comma-separated admin emails |
| PROTEGRITY_DSG_HOST | Databricks Secrets (Phase 4) | Protegrity DSG REST API base URL |
| PROTEGRITY_API_KEY | Databricks Secrets (Phase 4) | API key for DSG authentication |
| PROTEGRITY_MODE | app.yaml | `mock` (POC) or `live` (Production) — controls whether real DSG API is called |

### 8.3 Deploy Command

```bash
databricks apps deploy carelon-app \
  --source-code-path /Workspace/Users/arun.wagle@databricks.com/Elevance/carelon-app/apps
```

---

## 9. Error Handling Strategy

| Error Type | Frontend Handling | Backend Handling |
|-----------|-------------------|------------------|
| Rate limit (429) | Retry 5x with backoff, show countdown | Retry 3x with Retry-After header |
| Auth failure (401/403) | Redirect to login or show 403 page | Return JSON error with GRANT instructions |
| Network error | "Network error" toast + retry button | Log + return 500 with message |
| Validation error | Inline form validation, prevent submit | Return 400 with field-level errors |
| Volume not found | "Folder not found" message | Return 404 with path info |
| SQL query failure | "Failed to load permissions" | Log + fallback to empty permissions |

---

## 10. Testing Strategy

| Test Type | Scope | Tools |
|-----------|-------|-------|
| Unit Tests | Services (masking, parsing, permissions) | pytest |
| Integration Tests | API endpoints with mock tokens | pytest + Flask test client |
| E2E Tests | Full wizard flow with sample files | Manual / Selenium (future) |
| Load Tests | Concurrent user simulation | locust (future) |

---

## 11. Monitoring & Observability

| Signal | Implementation | Location |
|--------|---------------|----------|
| Request logging | Python `logging` module | All route handlers |
| Audit trail | `audit_service.log_event()` | Upload, delete, download, admin actions |
| Error tracking | Logger with exc_info=True | All exception handlers |
| Cache metrics | Log cache hit/miss | volume_browser_service.py |
| Performance | Duration logging per operation | Tokenization, file upload |

---

## 12. Known Limitations

1. **POC: Mock Protegrity** — Tokenization uses deterministic masking functions (not reversible). In Production (Phase 4), the Protegrity DSG REST API (`/api/v1/protect` + `/api/v1/unprotect`) will provide format-preserving encryption with a reversible token vault
2. **No streaming upload** — Entire parsed data sent as JSON; limits practical file size to ~100MB for the JSON payload
3. **Single warehouse** — All SQL queries route to one Serverless Starter warehouse
4. **No real-time permissions** — Permission changes require page refresh to take effect (90s cache)
5. **Fixed-width only** — Client-side parsing currently supports fixed-width files via template; CSV/delimiter support requires template extension
6. **No file versioning** — Re-uploading same file overwrites without history
