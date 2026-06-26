# Carelon App — Master Design Plan

## 1. Overview

A **Databricks App** (deployed from workspace folder via Declarative Asset Bundles) named **Carelon App** that enables business users to:

1. **Upload** structured data files (CSV, Excel, TSV, etc.) up to **2 GB** — supports **batch upload** (multiple files, each with its own template)
2. **Tokenize** PII columns in-memory using **Protegrity REST APIs**
3. **Store** tokenized output in a **user-selectable Databricks Unity Catalog Volume**
4. **Manage** file operations (Browse, Download, Delete, Preview, Detokenize, Share)
5. **Control access** via IDP-integrated Databricks Account user groups with role-based permissions stored in **Delta tables**

The app is built with **Python Flask**, uses a modular architecture, and initially uses a **synthetic (mock) Protegrity API**.

---

## 2. Key Design Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Volume path | **Permission-gated** — users see only folders they have upload permission on (from `permission_assignments` table) |
| 2 | Template creation | **Template builder UI** as a menu option (placeholder for now, not implemented in Phase 1) |
| 3 | Batch processing | **Multiple files per upload**, each associated with its own processing + Protegrity template |
| 4 | Detokenization output | **Download only** — detokenized data is NEVER stored, only streamed to authorized user |
| 5 | Sharing mechanism | **Delta Sharing** — use Databricks Delta Sharing to share Volume files with other users/groups |
| 6 | Session timeout | **Disabled for Phase 1** — will re-enable with configurable timeout later |
| 7 | Permissions store | **Delta tables** — not JSON files; supports querying, audit, and scales with the platform |
| 8 | User/Group source | **Platform identity** — Databricks Apps injects user via X-Forwarded-* headers; no login form |
| 9 | Protegrity API auth | **Placeholders** — implement credential hooks without real integration for now |
| 10 | App name | **carelon-app** (bundle: `carelon_app_bundle`) |
| 11 | Landing page | **Dashboard** — welcome page with nav cards; NOT direct Volume browse |
| 12 | Deployment | **Workspace folder** — deploy from `/Workspace/.../carelon-app/apps`; no Git repo required |
| 13 | Folder structure | **`apps/` subfolder** — only UI/Flask code deployed; sql/tests/samples stay at root |
| 14 | Volume auth | **User identity only** — all Volume ops use X-Forwarded-Access-Token with `files` scope; no SP fallback |
| 15 | Admin API auth | **Service Principal** — Jobs/Clusters APIs have no user-auth scope in Public Preview; admin ops use SP `client_credentials` flow |
| 16 | OAuth scopes | `files` is the only user-auth scope configured; `jobs`/`compute` scopes don't exist in Public Preview |
| 17 | SDK auth_type | `auth_type='pat'` in all `WorkspaceClient` calls to avoid conflict with SP env vars (`DATABRICKS_CLIENT_ID`/`SECRET`) |

---

## 3. Supported Operations

| Operation | Description |
|-----------|-------------|
| **Browse** | View list of files in the Volume (tokenized and raw) |
| **Upload** | Upload multiple data files + per-file templates, trigger tokenization pipeline |
| **Download** | Download tokenized files from the Volume |
| **Delete** | Remove files from the Volume |
| **Preview** | View first N rows of a file without downloading |
| **Detokenize** | Reverse tokenization — result streamed as download, never persisted |
| **Share** | Share Volume files via Delta Sharing |
| **Template Builder** | *(Future)* UI to construct processing/Protegrity templates visually |
| **Admin Dashboard** | 4-tile admin home: Permissions Management, Manage Jobs, ABAC Policies, Job Clusters |
| **Manage Jobs** | List workspace jobs (infinite scroll), expand to see runs, View Job/Run in workspace |
| **ABAC Policies** | Create row filters and column masks via SQL (preview SQL before executing) |
| **Job Clusters** | Create job clusters via REST API (node types, autoscale, spot policy) |

---

## 4. Access Control Model (Summary)

### 4.1 User Groups & Permissions Matrix

| Permission | Admin | Data Steward | Analyst | Viewer |
|------------|:-----:|:------------:|:-------:|:------:|
| Browse | ✅ | ✅ | ✅ | ✅ |
| Upload | ✅ | ✅ | ✅ | ❌ |
| Download | ✅ | ✅ | ✅ | ❌ |
| Delete | ✅ | ✅ | ❌ | ❌ |
| Preview | ✅ | ✅ | ✅ | ✅ |
| Detokenize | ✅ | ✅ | ❌ | ❌ |
| Share | ✅ | ❌ | ❌ | ❌ |
| Manage Permissions | ✅ | ❌ | ❌ | ❌ |

### 4.2 Group Resolution (Phase 1)

- Admin users defined in `ADMIN_USERS` env var (comma-separated emails)
- All other authenticated users default to `analyst` group
- Phase 2: Lookup from Delta table `app_group_mappings`

> Full details: [Feature 02 — Access Control & Permissions](./design/02_ACCESS_CONTROL_FLOW.md)

---

## 5. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                                 │
│  [Platform Auth] → [Dashboard] → [Upload | Browse | Preview | Admin]│
└───────────────────────────────────┬─────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│          DATABRICKS APPS PLATFORM (Reverse Proxy)                    │
│  • Authenticates user via SSO/IdP                                    │
│  • Injects X-Forwarded-Email, X-Forwarded-User headers              │
│  • Injects X-Forwarded-Access-Token for downstream calls             │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│            CARELON APP (Flask + Gunicorn on Apps Serverless)          │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ Auth &       │  │ File Ops     │  │ Tokenization            │   │
│  │ Permissions  │  │ (Browse/     │  │ Pipeline                │   │
│  │ (Headers +  │  │  Download/   │  │ (Batch Upload →         │   │
│  │  Delta Tbl) │  │  Delete/     │  │  Per-file Tokenize →    │   │
│  │              │  │  Preview/    │  │  Store in Volume)       │   │
│  │              │  │  Share)      │  │                          │   │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘   │
│         │                  │                     │                    │
│         ▼                  ▼                     ▼                    │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ Delta Tables │  │ Volume       │  │ Protegrity Client       │   │
│  │ (perms,     │  │ Service +    │  │ (Synthetic/Real)        │   │
│  │  audit log) │  │ Delta Sharing│  │                          │   │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│              DATABRICKS UNITY CATALOG                                 │
│  ┌────────────────────────┐  ┌──────────────────────────────────┐   │
│  │ Delta Tables           │  │ Volumes (user-selectable)         │   │
│  │ • app_permissions      │  │ /Volumes/{catalog}/{schema}/{vol} │   │
│  │ • app_audit_log        │  │                                    │   │
│  │ • app_group_mappings   │  │ Shared via Delta Sharing          │   │
│  └────────────────────────┘  └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Feature Documents

Each document is a **self-contained, implementable feature** with its own scope, deliverables, services, routes, templates, and error handling.

| # | Feature | Document | Scope |
|---|---------|----------|-------|
| 01 | **Upload & Tokenize** | [01_UPLOAD_TOKENIZE_FLOW.md](./design/01_UPLOAD_TOKENIZE_FLOW.md) | Batch file upload, per-file templates, tokenization pipeline, user-selectable Volume |
| 02 | **Access Control & Permissions** | [02_ACCESS_CONTROL_FLOW.md](./design/02_ACCESS_CONTROL_FLOW.md) | Delta table schema, permission model, group mappings, admin UI, middleware, audit logging |
| 03 | **File Operations** | [03_FILE_OPERATIONS_FLOW.md](./design/03_FILE_OPERATIONS_FLOW.md) | Browse, Download, Delete, Preview, Detokenize (download-only), Delta Sharing |
| 04 | **Deployment** | [04_DEPLOYMENT.md](./design/04_DEPLOYMENT.md) | DAB config, app.yaml, gunicorn.conf.py, env vars, secrets, workspace deployment |
| 05 | **Login & Session** | [05_LOGIN_SESSION_FLOW.md](./design/05_LOGIN_SESSION_FLOW.md) | Platform identity (X-Forwarded-* headers), auto-login, session management |
| 06 | **UI Design & Mockup** | [06_UI_DESIGN_MOCKUP.md](./design/06_UI_DESIGN_MOCKUP.md) | All page layouts, wireframes, navigation, CSS design system, JS modules, accessibility |

---

## 7. Project Structure

```
carelon-app/
├── databricks.yml                      # DAB bundle config (source_code_path: ./apps)
├── sql/                                # Delta table DDL scripts (NOT deployed with app)
│   ├── create_permissions_table.sql
│   ├── create_audit_log_table.sql
│   ├── create_group_mappings_table.sql
│   ├── create_available_permissions_table.sql
│   └── seed_default_permissions.sql
├── sample_templates/                   # Example template files (NOT deployed with app)
│   ├── sample_processing_template.json
│   └── sample_protegrity_template.json
├── tests/                              # Unit/integration tests (NOT deployed with app)
│   ├── test_file_parser.py
│   ├── test_template_parser.py
│   ├── test_protegrity_client.py
│   ├── test_tokenizer.py
│   ├── test_permissions.py
│   └── test_auth.py
│
└── apps/                               # ← DEPLOYED as the Databricks App
    ├── app.yaml                        # App runtime config (gunicorn command + env vars)
    ├── gunicorn.conf.py                # Port binding from DATABRICKS_APP_PORT env var
    ├── requirements.txt                # Python dependencies (no bcrypt needed)
    ├── app.py                          # Flask app entry point + /dashboard route
    ├── config.py                       # Centralized config (incl. ADMIN_USERS)
    │
    ├── routes/                         # Flask Blueprints (HTTP layer)
    │   ├── __init__.py
    │   ├── auth_routes.py              # Auto-login from headers, logout, heartbeat
    │   ├── upload_routes.py            # Batch file upload + tokenization trigger
    │   ├── file_ops_routes.py          # Browse (graceful error), Download, Delete, Preview
    │   ├── volume_api_routes.py        # Volume browser REST API (browse, create-folder)
    │   ├── share_routes.py             # Delta Sharing integration
    │   ├── detokenize_routes.py        # Detokenization (download-only)
    │   └── admin_routes.py             # Admin dashboard, Jobs (SP), ABAC, Clusters (SP)
    │
    ├── services/                       # Business logic (no HTTP concerns)
    │   ├── __init__.py
    │   ├── auth_service.py             # Platform identity (X-Forwarded-* headers) + session
    │   ├── permissions_service.py      # Permission checks & management (in-memory Phase 1)
    │   ├── audit_service.py            # Audit log writes and queries (in-memory Phase 1)
    │   ├── file_parser.py              # Read CSV/Excel/TSV into DataFrame
    │   ├── template_parser.py          # Parse both template types
    │   ├── protegrity_client.py        # Protegrity REST API client (synthetic)
    │   ├── tokenizer.py                # Orchestrates batch tokenization pipeline
    │   ├── detokenizer.py              # Orchestrates detokenization (stream-only)
    │   ├── volume_service.py           # Volume file ops (user token + auth_type='pat', no SP fallback)
    │   ├── volume_browser_service.py   # Volume directory browsing (user token only)
    │   └── sharing_service.py          # Delta Sharing operations
    │
    ├── models/                         # Data classes / domain models
    │   ├── __init__.py
    │   ├── user.py                     # User model (from platform headers)
    │   ├── permission.py               # Permission, GroupPermission (in-memory defaults)
    │   ├── file_template.py            # FileProcessingTemplate dataclass
    │   └── protegrity_template.py      # ProtegrityTemplate dataclass
    │
    ├── middleware/                     # Cross-cutting concerns
    │   ├── __init__.py
    │   ├── auth_middleware.py          # @login_required + @require_permission (no timeout)
    │   └── session_middleware.py       # (Future) Inactivity timeout enforcement
    │
    ├── templates/                      # Jinja2 HTML templates
    │   ├── layout.html                 # Base layout (header brand → dashboard, sidebar)
    │   ├── dashboard.html              # Welcome/landing page with nav cards
    │   ├── upload.html                 # Batch upload form (multi-file + templates)
    │   ├── browse.html                 # File browser with graceful Volume error handling
    │   ├── preview.html                # File preview (first N rows)
    │   ├── share.html                  # Delta Sharing configuration
    │   ├── detokenize.html             # Detokenization page
    │   ├── admin/
    │   │   ├── permissions.html        # Assign permissions to groups
    │   │   └── audit.html              # View audit log
    │   └── components/
    │       ├── timeout_modal.html      # (Future) Session expiring warning
    │       └── confirm_modal.html      # Delete confirmation
    │
    └── static/                         # Static assets
        ├── css/
        │   └── styles.css              # Purple theme, tiles, job list, run rows
        └── js/
            ├── upload.js               # Multi-file upload + Volume picker
            ├── browse.js               # File browser interactions
            ├── session.js              # (Future) Client-side inactivity timer
            ├── admin.js                # Permissions matrix + ABAC/cluster forms
            └── admin_jobs.js           # Infinite scroll job list + expandable runs
```

---

## 8. Key Constraints

| Constraint | Value |
|------------|-------|
| App name | **carelon-app** |
| Bundle name | **carelon_app_bundle** |
| Max file upload size | **2 GB** |
| Supported file formats | CSV, TSV, XLS, XLSX |
| Batch upload | Multiple files per request, each with own template pair |
| Authentication | **Databricks Apps platform identity** (X-Forwarded-* headers, no login form) |
| Admin users | `ADMIN_USERS` env var (comma-separated emails, default: `arun.wagle@databricks.com`) |
| Permissions storage | In-memory Phase 1 → **Delta tables** Phase 2 |
| User/Group source | Platform headers → config-based groups (Phase 1), SCIM (Phase 2) |
| Session timeout | **Disabled** (Phase 1) — re-enable with configurable duration later |
| Landing page | `/dashboard` welcome page (NOT Volume browse) |
| Sharing mechanism | **Delta Sharing** |
| Detokenize output | Stream to download only — never stored |
| Volume selection | User-selectable at upload time |
| Deployment source | **Workspace folder** (`/Workspace/.../carelon-app/apps`) — no Git repo required |
| Runtime | Gunicorn (via `gunicorn.conf.py`) + Flask on Databricks Apps Serverless |
| Port binding | `gunicorn.conf.py` reads `DATABRICKS_APP_PORT` env var (not in app.yaml command) |

---

## 9. Implementation Status

### Phase 1: Auth & App Skeleton ✅ (Complete)
- [x] Flask app skeleton with blueprints and config
- [x] Auto-login via platform identity headers (X-Forwarded-*)
- [x] `@login_required` and `@require_permission` middleware (timeout disabled)
- [x] Permission model (in-memory with default groups)
- [x] Dashboard welcome page as landing page
- [x] Layout with purple sidebar + clickable header brand
- [x] Gunicorn + app.yaml + gunicorn.conf.py deployment config
- [x] Successful deployment from workspace folder

### Phase 2: Upload & Tokenization ✅ (Complete)
- [x] 5-step upload wizard: Data File → Processing Template → Parsed Preview → Protegrity Template → Target Folder
- [x] Client-side fixed-width file parsing using template Start/End positions (SheetJS)
- [x] PHI column detection from template's "PHI Type" column
- [x] Permitted folders endpoint (`GET /api/volumes/permitted-folders`) — admins see all folders, non-admins see only assigned
- [x] `loadPermittedFolders()` with 90s client-side cache and retry on error
- [x] **Upload & Tokenize** end-to-end flow:
  - Parsed data from Step 3 sent as JSON to `POST /upload/tokenize`
  - Mock Protegrity API call — ONLY columns with declared `phi_type` from template are masked
  - Masking by phi_type: SSN, Phone, Email, DOB, Name, Address, ZIP, Member_ID, etc.
  - Non-PHI columns pass through unchanged
  - Output filename: `{original_name}_tokenized.txt` (pipe-delimited)
  - Uploaded to user-selected Volume folder via Files API
  - Audit log event on success/failure
- [x] Template parsing (processing + Protegrity)
- [x] File parser (CSV + Excel, fixed-width via template)
- [x] Synthetic Protegrity Client (format-preserving masking per phi_type)
- [x] Volume Service (write to user-selected path, user token + auth_type='pat')
- [x] Volume Browser Service (list directories, create folders, 90s TTL cache, 3x retry on 429)
- [x] OAuth scope `files` configured for user-identity Volume access
- [x] Upload results display (output path, rows processed, PHI columns masked)

> **Features:** 01 (Upload & Tokenize) + partial 06 (UI: upload wizard, results display)

### Admin Dashboard ✅ (Complete)
- [x] 4-tile admin home: Permissions, Manage Jobs, ABAC Policies, Job Clusters
- [x] Manage Jobs: infinite scroll list via SP token + `GET /api/2.1/jobs/list`
- [x] Expandable job runs (click job → see last 10 runs as child rows)
- [x] View Job → opens workspace (`https://{host}/#job/{id}`) in new tab
- [x] View Run Details → opens `run_page_url` in new tab
- [x] Create Job button → opens Databricks workspace job creation page
- [x] ABAC Policies page (row filter / column mask, SQL preview)
- [x] Job Clusters page (node type, autoscale, spark conf)
- [x] SP `client_credentials` flow for Jobs/Clusters APIs
- [x] Setup notebook (`notebooks/setup_app_scopes`) for scope configuration

> **Auth model:** Volume ops use user token (`files` scope); Jobs/Clusters use SP token (no user scope available)

### Phase 3: File Operations
- [ ] Browse (list files in selected Volume with actions)
- [ ] Download (stream from Volume)
- [ ] Delete (with confirmation + permission check)
- [ ] Preview (first N rows, paginated)
- [ ] Detokenize (reverse pipeline, download-only stream)
- [ ] Delta Sharing integration

> **Features:** 03 (File Operations) + partial 06 (UI: browse, preview, share pages)

### Phase 3.5: Admin & Permissions ✅ (Complete)
- [x] Admin detection: session `is_admin` flag + groups check + `ADMIN_USERS` config
- [x] `@require_admin` decorator in `auth_middleware.py`
- [x] All 19 admin routes use `@require_admin` (not `@require_permission('manage_permissions')`)
- [x] Admin sidebar visibility: dual check (`session.is_admin` OR `'admin' in groups`)
- [x] Entitlement tables in Delta: `permission_types`, `permission_assignments`, `volume_grants`
- [x] `permission_assignments` has `resource_path` column for folder-level permissions
- [x] Setup notebook for entitlement tables (parameterized, SP GRANTs, seed data)
- [x] Admin permissions page: folder browser modal for selecting permission targets
- [x] Detokenize sidebar link removed
- [x] Dashboard cards: File Explorer (not old Browse), Admin card with is_admin check

### Phase 4: Polish & Production
- [ ] Re-enable session timeout (configurable duration)
- [ ] Admin Permissions: "Create Folder" button in folder browser modal
- [ ] File Explorer: Preview implementation (first N rows)
- [ ] File Explorer: Share and Detokenize actions
- [ ] Complete CSS styling & responsive layout
- [ ] Template Builder placeholder (menu item + coming soon page)
- [ ] Full unit test coverage for all services
- [ ] End-to-end integration testing
- [ ] Replace synthetic Protegrity with real API
- [ ] Logging, telemetry, monitoring
- [ ] Remove `/admin/token-debug` temp endpoint

> **Features:** 04 (production deploy), remainder of 06 (UI polish) + tests

---

## 10. Caching Architecture

The app implements multi-layer caching to minimize Volume API calls and handle rate limits gracefully:

| Layer | Location | TTL | Scope | Invalidation |
|-------|----------|-----|-------|---------------|
| Backend | `volume_browser_service.py` | 90s | Per-path directory listing | On folder creation |
| Frontend (File Explorer) | `file_explorer.js` | 90s | Tree expansion, my-access, file listings | Refresh button, delete action |
| Frontend (Upload Wizard) | `upload.js` | 90s | Permitted folders list | Session-scoped, retry button |

**Rate limit handling:** Both layers retry on HTTP 429 with exponential backoff (backend: 3 retries, frontend: 5 retries). Users see "Rate limit reached. Retrying in Xs..." during backoff.

---

## 11. Tokenization Pipeline (Mock Protegrity)

The upload wizard's tokenization uses the **PHI Type** column from the processing template to determine which columns to mask and how:

```
Step 3 (Parsed Preview)
  │
  │  Template has columns: Field Name | Start | End | PHI Type
  │  Only rows with non-empty PHI Type are flagged
  │
  ▼
Step 5 (Submit) → POST /upload/tokenize
  │
  │  Payload: { headers, rows, phi_columns, phi_indices, phi_types, volume_path }
  │
  ▼
Backend: _mock_protegrity_api_call()
  │
  │  For each row:
  │    For each (col_index, phi_type) in zip(phi_indices, phi_types):
  │      row[col_index] = _mask_value(row[col_index], phi_type)
  │
  │  Non-PHI columns: UNCHANGED
  │
  ▼
Output: {filename}_tokenized.txt (pipe-delimited) → uploaded to Volume
```

**Masking functions by PHI Type:**

| phi_type | Example Input | Example Output |
|----------|---------------|----------------|
| SSN | 123-45-6789 | ***-**-6789 |
| Phone | 5551234567 | (***) ***-4567 |
| Email | john@acme.com | j***@acme.com |
| DOB | 1990-05-15 | ****-**-** (1990) |
| Name | Johnson | J****** |
| Address | 123 Main St | 123 **** ** |
| ZIP | 90210 | 902** |
| Member_ID | MBR12345 | TOK_A3F2B8C91E04 |

---

## 12. Deployment Quick Reference

```bash
# From Databricks Apps UI:
# 1. Go to Apps → Select "carelon-app" → Click Deploy
# 2. Select folder: /Workspace/Users/arun.wagle@databricks.com/Elevance/carelon-app/apps
# 3. Click Deploy

# OR via CLI:
databricks apps deploy carelon-app \
  --source-code-path /Workspace/Users/arun.wagle@databricks.com/Elevance/carelon-app/apps

# Health check:
# GET https://carelon-app-<id>.aws.databricksapps.com/health
```

**No Git repo required.** The app deploys directly from the workspace folder.
