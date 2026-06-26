# Carelon App — Requirements Document

**Version:** 1.0  
**Last Updated:** June 2026  
**Owner:** Arun Wagle  
**Status:** Implemented (Phase 1–3)

---

## 1. Executive Summary

The Carelon App is a secure, web-based Databricks Application that enables healthcare business users to upload structured data files containing Protected Health Information (PHI), tokenize sensitive columns using Protegrity-style masking, and store the de-identified output in Databricks Unity Catalog Volumes — all governed by role-based access controls tied to enterprise identity.

---

## 2. Business Requirements

### 2.1 Core Capabilities

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| BR-01 | Users shall upload structured data files (CSV, TSV, Excel, fixed-width) up to 2 GB | Must Have | Done |
| BR-02 | PHI columns shall be identified from a processing template and tokenized before storage | Must Have | Done |
| BR-03 | Tokenized output shall be stored in user-selected Unity Catalog Volume folders | Must Have | Done |
| BR-04 | Access shall be controlled by user groups with per-folder, per-action permissions | Must Have | Done |
| BR-05 | Admin users shall manage permissions, jobs, ABAC policies, and clusters | Must Have | Done |
| BR-06 | Users shall browse, download, and delete files based on folder-level permissions | Must Have | Done |
| BR-07 | The app shall authenticate via Databricks platform identity (SSO/IdP) with no login form | Must Have | Done |
| BR-08 | All file operations shall be audited | Should Have | Done |
| BR-09 | The app shall handle API rate limits gracefully without user-facing errors | Should Have | Done |
| BR-10 | Detokenization shall be available as a download-only stream (never stored) | Could Have | Planned |
| BR-11 | File sharing via Delta Sharing | Could Have | Planned |

### 2.2 User Roles & Access Levels

#### 2.2.1 Role Hierarchy

The application defines one administrative role and two business user groups differentiated by location (onshore/offshore). Access is governed at the **folder level** — each user/group is assigned specific actions on specific Volume folders via the `permission_assignments` Delta table.

```
┌─────────────────────────────────────────────────────────────┐
│                        ADMIN                                  │
│  (Full access to all folders + Admin Panel)                   │
├─────────────────────────────────────────────────────────────┤
│             BUSINESS USERS — ONSHORE (US-based)               │
│  (Upload, tokenize, download, delete, detokenize, share)      │
│  Higher access level: can view tokenized + detokenized data   │
├─────────────────────────────────────────────────────────────┤
│             BUSINESS USERS — OFFSHORE                         │
│  (Browse, preview, download — restricted PHI access)          │
│  Cannot view tokenized column values unless granted           │
│  detokenize permission; no delete, no upload                  │
└─────────────────────────────────────────────────────────────┘
```

#### 2.2.2 Role Definitions

| Role | Description | Assignment Method |
|------|-------------|-------------------|
| **Admin** | Full platform access. Manages permissions, infrastructure (jobs, clusters, ABAC policies). Bypasses all folder-level permission checks. Can view all data in all states. | `ADMIN_USERS` env var (comma-separated emails) OR `session['is_admin']` flag OR membership in `admin` group |
| **Business Users — Onshore** | US-based users responsible for data lifecycle. Can upload, tokenize, download, delete, preview, and detokenize files in assigned folders. Can view tokenized column values in preview. Cannot access admin panel. | Assigned via `permission_assignments` table with actions: browse, upload, download, delete, preview, detokenize, share |
| **Business Users — Offshore** | Offshore (non-US) users with restricted PHI access. Can browse folders, preview file structure and non-PHI columns, and download files. **Cannot view tokenized/PHI column values in preview** unless explicitly granted the `detokenize` permission. Cannot upload, delete, or share. | Assigned via `permission_assignments` table with actions: browse, preview, download |

#### 2.2.3 Tokenized Column Visibility Rules

A key security distinction between Onshore and Offshore users is how **tokenized (PHI) columns** are displayed:

| Scenario | Onshore | Offshore (no detokenize) | Offshore (with detokenize) |
|----------|---------|--------------------------|----------------------------|
| File list / metadata | ✅ Visible | ✅ Visible | ✅ Visible |
| Non-PHI columns in preview | ✅ Visible | ✅ Visible | ✅ Visible |
| Tokenized (masked) PHI column values in preview | ✅ Visible | ❌ Hidden / redacted | ✅ Visible |
| Detokenize action (stream original values) | ✅ If granted | ❌ Not available | ✅ Available |
| Download file (contains tokenized values) | ✅ Allowed | ✅ Allowed (tokenized only) | ✅ Allowed |

**Implementation:** When a user without `detokenize` permission previews a file, PHI columns are displayed as `[REDACTED]` instead of showing the masked/tokenized value. This prevents offshore users from seeing even the partial patterns (e.g., `***-**-6789`) unless they have been explicitly granted detokenize access.

#### 2.2.4 Available Actions (Permission Types)

| Action | Description | UI Capability |
|--------|-------------|---------------|
| `browse` | View folder contents and file metadata (name, size, date) | File Explorer: see files listed in a folder |
| `upload` | Upload data files and trigger tokenization to this folder | Upload Wizard: folder appears in Step 5 target selection |
| `download` | Download files from this folder | File Explorer: download button enabled on files |
| `delete` | Remove files from this folder permanently | File Explorer: delete button enabled on files |
| `preview` | View first N rows of a file (non-PHI columns always visible; PHI visibility depends on detokenize permission) | File Explorer: preview button enabled on files |
| `detokenize` | Reverse tokenization and stream original data as download; also unlocks tokenized column visibility in preview | File Explorer: detokenize action (never stored) + PHI columns visible in preview |
| `share` | Share files from this folder via Delta Sharing | File Explorer: share action |
| `manage_permissions` | Assign/revoke permissions for other users (Admin only) | Admin Panel: Permissions Management page |

#### 2.2.5 Permissions Matrix

| Action | Admin | Onshore Business Users | Offshore Business Users |
|--------|:-----:|:----------------------:|:-----------------------:|
| browse | ✅ (all folders) | ✅ (assigned) | ✅ (assigned) |
| upload | ✅ (all folders) | ✅ (assigned) | ❌ |
| download | ✅ (all folders) | ✅ (assigned) | ✅ (assigned) |
| delete | ✅ (all folders) | ✅ (assigned) | ❌ |
| preview (non-PHI) | ✅ (all folders) | ✅ (assigned) | ✅ (assigned) |
| preview (PHI columns visible) | ✅ (all folders) | ✅ (assigned) | ❌ (unless detokenize granted) |
| detokenize | ✅ (all folders) | ✅ (assigned) | ❌ (unless explicitly granted) |
| share | ✅ (all folders) | ✅ (assigned) | ❌ |
| manage_permissions | ✅ | ❌ | ❌ |
| Admin Panel access | ✅ | ❌ | ❌ |
| Jobs management | ✅ | ❌ | ❌ |
| ABAC policies | ✅ | ❌ | ❌ |
| Cluster management | ✅ | ❌ | ❌ |

#### 2.2.6 Folder-Level Scoping

Permissions are scoped to **specific Volume folders** via the `resource_path` column in `permission_assignments`:

```
Example 1: Onshore user "onshore.user@carelon.com" has these assignments:
┌────────────────────────────────────────────────────────────────────┐
│ resource_path                                        │ actions      │
├────────────────────────────────────────────────────────────────────┤
│ /Volumes/catalog/carelon/dxutility/claims            │ browse,      │
│                                                      │ upload,      │
│                                                      │ download,    │
│                                                      │ delete,      │
│                                                      │ preview,     │
│                                                      │ detokenize   │
└────────────────────────────────────────────────────────────────────┘

Result: Full access to "claims" folder — can upload, download, delete,
        preview (sees PHI columns), and detokenize files.

Example 2: Offshore user "offshore.user@vendor.com" has these assignments:
┌────────────────────────────────────────────────────────────────────┐
│ resource_path                                        │ actions      │
├────────────────────────────────────────────────────────────────────┤
│ /Volumes/catalog/carelon/dxutility/claims            │ browse,      │
│                                                      │ download,    │
│                                                      │ preview      │
└────────────────────────────────────────────────────────────────────┘

Result: Can see files, download them (tokenized), and preview — BUT
        PHI columns show [REDACTED] in preview since no detokenize
        permission. Cannot upload, delete, or share.

Example 3: Offshore user WITH detokenize (special approval):
┌────────────────────────────────────────────────────────────────────┐
│ resource_path                                        │ actions      │
├────────────────────────────────────────────────────────────────────┤
│ /Volumes/catalog/carelon/dxutility/claims            │ browse,      │
│                                                      │ download,    │
│                                                      │ preview,     │
│                                                      │ detokenize   │
└────────────────────────────────────────────────────────────────────┘

Result: Same as Example 2, but PHI columns ARE visible in preview,
        and detokenize action is available (stream original values).
```

#### 2.2.7 Admin Override Behavior

Admin users **bypass all folder-level permission checks**:

1. **File Explorer:** Sees ALL folders in the volume root, with ALL actions enabled
2. **Upload Wizard (Step 5):** All folders appear in permitted-folders selection
3. **API responses:** `/files/api/my-access` returns all top-level folders with full action set
4. **No `permission_assignments` query needed** — admin status is checked first

Admin detection logic (checked in order, first match wins):
```
1. session['is_admin'] == True
2. 'admin' in session['groups']
3. user email in ADMIN_USERS config list
```

#### 2.2.8 Permission Assignment Storage

Permissions are stored in the `permission_assignments` Delta table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | STRING | Unique assignment ID |
| `entity_id` | STRING | User or group identifier |
| `entity_type` | STRING | `user` or `group` |
| `entity_name` | STRING | User email or group name (matched against X-Forwarded-Email) |
| `permission_type` | STRING | Always `files` for Volume operations |
| `resource_path` | STRING | Full Volume path (e.g., `/Volumes/catalog/schema/volume/folder`) |
| `action` | STRING | One of: browse, upload, download, delete, preview, detokenize, share |
| `is_active` | BOOLEAN | TRUE = active, FALSE = revoked |
| `granted_by` | STRING | Admin email who granted the permission |
| `granted_at` | TIMESTAMP | When the permission was granted |

One row per (entity, resource_path, action) combination. A user with 4 actions on 2 folders has 8 rows.

#### 2.2.9 Group-Based Assignment

Permissions support group-level assignment aligned with the two business user groups:

| Group Name | Typical Members | Default Actions |
|------------|-----------------|-----------------|
| `onshore_business_users` | US-based Carelon staff | browse, upload, download, delete, preview, detokenize, share |
| `offshore_business_users` | Offshore vendor/contractor staff | browse, preview, download |
| `offshore_detokenize_approved` | Offshore users with special PHI access approval | browse, preview, download, detokenize |

Implementation:
- Assign actions to a group name via `permission_assignments` (entity_type = `group`)
- All users in that group inherit the folder permissions
- Group membership resolved from Databricks account SCIM integration
- Individual user assignments override group defaults
- An offshore user can be added to `offshore_detokenize_approved` to gain PHI visibility

---

## 3. Functional Requirements

### 3.1 Upload & Tokenization (5-Step Wizard)

| ID | Requirement | Details |
|----|-------------|--------|
| FR-01 | Step 1: Data file selection | Accept CSV, TSV, XLS, XLSX, DAT (fixed-width) files |
| FR-02 | Step 2: Processing template selection | Templates loaded from Volume (`/templates/input_file_parsing/`); two-panel layout with list + sheet preview; client-side SheetJS parsing |
| FR-03 | Step 3: Parsed preview with PHI identification | Client-side parsing using template positions; PHI columns highlighted with badge |
| FR-04 | Step 4: Protegrity template selection | Templates loaded from Volume (`/templates/tokenization/`); selectable list with JSON preview |
| FR-05 | Step 5: Target folder selection | Show only data folders (templates folder excluded); admins see all non-template folders |
| FR-06 | Tokenization execution | Only columns with declared phi_type are masked; all others pass through unchanged |
| FR-07 | Output file format | `{original_name}_tokenized.txt`, pipe-delimited |
| FR-08 | Upload to Volume | Output uploaded via Databricks Files API to selected folder |
| FR-09 | Audit logging | Success/failure logged with user, filename, PHI columns, output path |

### 3.2 Tokenization & Detokenization via Protegrity

#### 3.2.1 Production Architecture (Phase 4)

In production, all tokenization and detokenization is performed by the **Protegrity Data Security Gateway (DSG)** REST API:

```
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────────┐
│  Carelon App    │─────▶│  Protegrity DSG REST API  │─────▶│  Tokenized Data │
│  (Flask)        │      │  /api/v1/protect          │      │  (Volume)       │
│                 │◀─────│  /api/v1/unprotect        │◀─────│                 │
└─────────────────┘      └──────────────────────────┘      └─────────────────┘
```

| Operation | Protegrity API Endpoint | Purpose |
|-----------|------------------------|---------|
| **Tokenize** | `POST /api/v1/protect` | Apply Format-Preserving Encryption (FPE), hashing, or masking to PHI columns based on policy | 
| **Detokenize** | `POST /api/v1/unprotect` | Reverse tokenization to recover original PHI values (streamed, never stored) |

**Key integration details:**
- Protegrity policies are referenced via the **Tokenization Template** selected in Step 4
- Each PHI Type maps to a Protegrity **data element** with a specific protection method
- The DSG maintains the tokenization vault — only it can reverse the token to original value
- All calls are authenticated via API key/certificate managed in Databricks Secrets

#### 3.2.2 POC Implementation (Current — Phase 1)

For the proof-of-concept, Protegrity API calls are **simulated with deterministic masking functions**. The masking applies pattern-based redaction to demonstrate the flow without requiring a live Protegrity instance.

> ⚠️ **POC Limitation:** The mock masking is one-way and deterministic — it cannot be truly "detokenized" since no vault exists. In production, Protegrity DSG handles reversible tokenization via its internal key vault.

| PHI Type | POC Masking Rule | Example | Production (Protegrity) |
|----------|-----------------|---------|-------------------------|
| SSN | Keep last 4 digits | `123-45-6789` → `***-**-6789` | FPE: format-preserving encrypted value |
| Phone | Keep last 4 digits | `5551234567` → `(***) ***-4567` | FPE: encrypted phone number |
| Email | Keep first char + domain | `john@acme.com` → `j***@acme.com` | Tokenized email preserving domain |
| DOB | Keep year only | `1990-05-15` → `****-**-** (1990)` | FPE: encrypted date |
| Name | Keep first initial | `Johnson` → `J******` | FPE: encrypted name |
| Address | Keep house number | `123 Main St` → `123 **** **` | Tokenized address |
| ZIP | Keep first 3 | `90210` → `902**` | Partial masking (configurable) |
| Member_ID | Hash-based token | `MBR12345` → `TOK_A3F2B8C91E04` | SHA-256 HMAC token (irreversible) |

#### 3.2.3 Detokenization Flow

```
User clicks "Detokenize" in File Explorer
    │
    ▼
┌───────────────────────────────────────────────────────────┐
│ Production (Phase 4):                                      │
│   1. Read tokenized file from Volume                       │
│   2. Call Protegrity DSG POST /api/v1/unprotect            │
│      with tokenized values + policy reference              │
│   3. DSG returns original PHI values                       │
│   4. Stream to user's browser as download                  │
│   5. NEVER store detokenized output anywhere               │
│                                                            │
│ POC (Phase 1):                                             │
│   1. Read tokenized file from Volume                       │
│   2. Return file content as-is (mock — cannot reverse)     │
│   3. Stream to user with "mock detokenized" header         │
└───────────────────────────────────────────────────────────┘
```

**Security constraints (both POC and Production):**
- Detokenized data is NEVER written to disk, Volume, or any persistent store
- Response is streamed directly to browser with `X-Never-Stored: true` header
- Audit log records every detokenization event

### 3.3 File Explorer

| ID | Requirement | Details |
|----|-------------|--------|
| FR-10 | Two-panel layout | Left: folder tree, Right: file listing with permissions |
| FR-11 | Folder tree | Lazy-loading expand/collapse; admin sees all folders; non-admin sees permitted only |
| FR-12 | Inherited permissions | Files inherit permission badges from parent folder |
| FR-13 | Action buttons | Download, Preview, Delete — rendered only if folder grants that action |
| FR-14 | Resizable divider | Drag to resize tree panel (180–500px) |
| FR-15 | Subfolder navigation | Click subfolder in file list navigates into it |
| FR-16 | Refresh capability | Manual refresh button clears cache and reloads |

### 3.4 Admin Panel

| ID | Requirement | Details |
|----|-------------|--------|
| FR-17 | Admin detection | Session flag + groups list + ADMIN_USERS env var |
| FR-18 | Permissions management | Assign browse/upload/download/delete/preview/share/detokenize per user per folder |
| FR-19 | Manage Jobs | List all workspace jobs, view runs, trigger on demand |
| FR-20 | ABAC Policies | Create row filters and column masks via SQL |
| FR-21 | Job Clusters | Create compute clusters for jobs |
| FR-22 | Access restriction | All admin routes protected by `@require_admin` decorator |

### 3.5 Access Control

| ID | Requirement | Details |
|----|-------------|--------|
| FR-23 | Authentication | Databricks platform identity via X-Forwarded-* headers |
| FR-24 | Permission storage | Delta tables: `permission_types`, `permission_assignments`, `volume_grants` |
| FR-25 | Folder-level permissions | `resource_path` column in `permission_assignments` scopes actions to specific Volume folders |
| FR-26 | Admin override | Admin users bypass permission checks; see all folders with all actions |
| FR-27 | Service Principal | SP used for SQL queries (entitlement lookups); UUID-based UC GRANTs |

### 3.6 Template Design & Management

All templates are stored in Unity Catalog Volumes under a dedicated `/templates` directory tree that is **hidden from the File Explorer** and **excluded from target folder selection**. Templates are managed through the "Template Design Editor" tab and consumed by the Upload Wizard.

#### 3.6.1 Template Types

| Template Type | Volume Path | Format | Purpose |
|---------------|-------------|--------|--------|
| **Input File Parsing** | `/templates/input_file_parsing/` | Excel (XLSX) | Defines fixed-width column layout: Field Name, Start, End, PHI Type. Used in Step 2 to parse data files. |
| **Tokenization** | `/templates/tokenization/` | JSON / YAML | Defines Protegrity tokenization policies: which data elements to tokenize, protection methods, and element groups. Used in Step 4. |
| **Detokenization** | `/templates/detokenization/` | JSON / YAML | Defines reverse tokenization rules: element mappings, policy references, and output format. Used by the detokenize action. |

#### 3.6.2 Input File Parsing Template Requirements

| ID | Requirement | Details |
|----|-------------|--------|
| TD-01 | Template format | Excel workbook (`.xlsx`) with one or more sheets |
| TD-02 | Required columns | `Field Name` (string), `Start` (integer, 1-based), `End` (integer, inclusive), `PHI Type` (string, empty = non-PHI) |
| TD-03 | Multi-sheet support | If workbook has multiple sheets, user selects which sheet defines the layout |
| TD-04 | PHI Type values | Valid values: SSN, Phone, Email, DOB, Name, Address, ZIP, Member_ID (extensible) |
| TD-05 | Volume-based selection | Templates listed from Volume; selected template downloaded and parsed client-side with SheetJS |
| TD-06 | Preview | Selected template sheet rendered as a scrollable table showing all column definitions |

#### 3.6.3 Tokenization Template Requirements

| ID | Requirement | Details |
|----|-------------|--------|
| TD-07 | Template format | JSON or YAML defining tokenization policies |
| TD-08 | Content structure | Data elements, protection methods (FPE, hash, mask), element groups, policy references |
| TD-09 | Volume-based selection | Templates listed from Volume folder; selectable list with preview |
| TD-10 | JSON preview | Selected template content displayed in formatted JSON viewer |
| TD-11 | Mock integration | In Phase 1, templates define intent; actual Protegrity API integration in Phase 4 |

#### 3.6.4 Detokenization Template Requirements

| ID | Requirement | Details |
|----|-------------|--------|
| TD-12 | Template format | JSON or YAML defining reverse tokenization mappings |
| TD-13 | Content structure | Element mappings, original-to-token relationships, policy references |
| TD-14 | Security constraint | Detokenized output is NEVER stored — streamed directly to user as download |
| TD-15 | Audit requirement | Every detokenization event logged with user, file, timestamp, and "never stored" flag |

#### 3.6.5 Template Design Editor (Future — Phase 4)

| ID | Requirement | Details |
|----|-------------|--------|
| TD-16 | Visual editor | GUI for creating/editing input file parsing templates (add/remove/reorder columns) |
| TD-17 | Validation | Real-time validation of Start/End positions for overlaps and gaps |
| TD-18 | Test with sample data | Upload a sample file and preview how the template parses it |
| TD-19 | Version control | Template versioning with history and rollback |
| TD-20 | Approval workflow | Template changes require reviewer approval before becoming active |

#### 3.6.6 Template Folder Isolation

The `/templates` directory and all sub-paths are:
- **Hidden** from the File Explorer (tree panel, file list, my-access API)
- **Excluded** from the Upload Wizard target folder selection (Step 5)
- **Accessible** only through dedicated template endpoints (`/upload/processing-templates`, `/upload/protegrity-templates`)
- **Not assignable** as `resource_path` in `permission_assignments` for upload/browse actions

This ensures templates are treated as configuration artifacts, not user data files.

---

## 4. Non-Functional Requirements

### 4.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Page load time | < 3 seconds |
| NFR-02 | Directory listing cache | 90-second TTL (backend + frontend) |
| NFR-03 | Rate limit handling | Automatic retry (3x backend, 5x frontend) with exponential backoff |
| NFR-04 | File upload size | Up to 2 GB |
| NFR-05 | Concurrent users | Limited by Databricks Apps serverless capacity |

### 4.2 Security

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-06 | Authentication | Platform SSO via Databricks Apps reverse proxy |
| NFR-07 | Authorization | Per-folder, per-action permission checks on every API call |
| NFR-08 | Token handling | User OAuth token (X-Forwarded-Access-Token) for all Volume ops |
| NFR-09 | PHI protection | PHI masked before storage; original values never persisted |
| NFR-10 | Audit trail | All file operations logged with user, action, resource, timestamp |
| NFR-11 | No stored credentials | SP credentials via env vars injected by Databricks Apps platform |

### 4.3 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-12 | Graceful degradation | Rate limit retries, cached fallbacks, informative error messages |
| NFR-13 | Cache invalidation | Automatic on folder creation; manual via refresh button |
| NFR-14 | Error recovery | Retry buttons on failed loads; form state preserved on errors |

### 4.4 Deployment

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-15 | Deployment method | Databricks Apps from workspace folder (no Git repo required) |
| NFR-16 | Runtime | Flask + Gunicorn on Databricks Apps Serverless |
| NFR-17 | Configuration | Environment variables via app.yaml; secrets via Databricks Secrets |
| NFR-18 | Zero-downtime deploy | Rolling deploy via `databricks apps deploy` CLI |

---

## 5. Data Requirements

### 5.1 Entitlement Tables (Unity Catalog)

| Table | Purpose |
|-------|---------|
| `permission_types` | Master list of available permissions (browse, upload, download, delete, preview, share, detokenize, manage_permissions) |
| `permission_assignments` | Per-user/group permission grants with `resource_path` for folder-level scoping |
| `volume_grants` | Volume-level access grants for the Service Principal |

### 5.2 Volume Structure

```
/Volumes/aw_serverless_stable_catalog/carelon/dxutility/
├── {folder_1}/
│   ├── original_data.dat
│   └── original_data_tokenized.txt     ← output from tokenization
├── {folder_2}/
│   └── ...
└── {folder_n}/
```

### 5.3 Processing Template Format

| Column | Description | Example |
|--------|-------------|--------|
| Field Name | Column name in the data file | `MEMBER_SSN` |
| Start | Start position (1-based, for fixed-width) | `1` |
| End | End position (inclusive) | `11` |
| PHI Type | Type of PHI (empty = not PHI) | `SSN` |

---

## 6. Integration Points

| System | Integration | Method |
|--------|-------------|--------|
| Databricks Unity Catalog | Volume file storage | Files API (REST) |
| Databricks SQL | Permission queries | Statement API (REST) via SP token |
| Databricks Jobs | Job management | Jobs API (SDK) |
| Protegrity DSG | PII tokenization + detokenization | REST API: `/api/v1/protect` (tokenize), `/api/v1/unprotect` (detokenize). **POC: mocked with deterministic masking; Production: live DSG integration** |
| Databricks Identity | Authentication | X-Forwarded-* headers from Apps proxy |
| Delta Sharing | File sharing | (Planned — Phase 4) |

---

## 7. Constraints & Assumptions

1. The app runs as a Databricks App with a Service Principal for admin operations
2. Users are authenticated via enterprise SSO integrated with Databricks
3. The `files` OAuth scope is the only user-auth scope available (no `jobs`/`compute` scopes)
4. Volume operations always use the user's forwarded token (not SP)
5. Protegrity DSG integration is **mocked in POC (Phase 1)** — masking functions simulate the output format. Real Protegrity REST API (`/api/v1/protect` and `/api/v1/unprotect`) integration is planned for Phase 4. The mock cannot truly detokenize.
6. Fixed-width file parsing is done client-side via the processing template
7. No session timeout in Phase 1 (will be re-enabled in Phase 4)

---

## 8. Acceptance Criteria

### Upload & Tokenize
- [ ] User can upload a fixed-width file with a processing template
- [ ] Only columns with declared PHI Type are masked in output
- [ ] Non-PHI columns appear unchanged in the output file
- [ ] Output is named `{original}_tokenized.txt` and stored in selected folder
- [ ] Audit log captures user, action, filename, output path

### File Explorer
- [ ] Admin users see all folders in the tree panel
- [ ] Non-admin users see only folders they have permissions on
- [ ] Clicking a folder shows its files with inherited permission badges
- [ ] Download/Delete buttons only appear if user has those permissions
- [ ] Rate limits are handled transparently with retry

### Admin Panel
- [ ] Only admin users can access admin routes (403 for others)
- [ ] Permissions can be assigned per user per folder
- [ ] Jobs can be listed, triggered, and cancelled

---

## 9. Future Enhancements (Phase 4+)

| # | Enhancement | Status |
|---|-------------|--------|
| 1 | Real Protegrity DSG API integration | Planned |
| 2 | Detokenization (download-only, never stored) | **Done** (mock) |
| 3 | Delta Sharing for file distribution | Planned |
| 4 | Template Design Editor (visual template builder GUI) | Planned |
| 5 | Session timeout with configurable duration | Planned |
| 6 | SCIM-based group resolution for permissions | Planned |
| 7 | File preview (tabular, PHI-highlighted, delimiter-aware) | **Done** |
| 8 | Search/filter in file explorer | Planned |
| 9 | Template versioning and approval workflows | Planned |
| 10 | Volume-based template management (processing + tokenization) | **Done** |
| 11 | Role update: Admin + Business Users Onshore + Business Users Offshore | **Done** |
