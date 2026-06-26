# Feature 02 — Access Control & Permissions

## 1. Feature Summary

A complete role-based access control system that:
- Maps **Databricks Account groups** (synced from IDP) to app-level permissions
- Stores permission assignments in **Delta tables** for auditability and scalability
- Provides an **Admin UI** for managing group-to-permission mappings
- Enforces permissions at both UI and API levels via middleware
- Logs all operations to an audit trail Delta table

---

## 2. What This Feature Delivers

- [x] Delta table schema for permissions, audit log, and group mappings
- [x] Permission resolution service (user → groups → permissions)
- [x] `@require_permission` decorator for server-side enforcement
- [x] Admin routes for managing group permissions
- [x] Admin HTML page for permission assignment UI
- [x] Audit logging service (all actions tracked)
- [x] Extensible permission model (add new operations without code changes)

---

## 3. Identity Model

### 3.1 Source of Truth

- **Users** and **Groups** come from **Databricks Account** (synced from organization IDP)
- The app does NOT create or manage users — it reads identity from platform headers
- The app only manages **which permissions are granted to which groups**

### 3.2 How Identity is Resolved

```
IDP (Okta/Azure AD/etc.)
    │
    ▼ (SCIM sync)
Databricks Account
    │
    ▼ (workspace membership)
Databricks Workspace / Apps Platform
    │
    ▼ (X-Forwarded-* headers injected by platform)
Flask App → reads email, username, user_id from headers
    │
    ▼ (config lookup or Delta table)
Group resolution → maps email to app groups (admin, analyst, etc.)
    │
    ▼ (Delta table lookup)
app_permissions table → resolves effective permissions
```

**Headers used for identity:**

| Header | Description |
|--------|-------------|
| `X-Forwarded-Email` | User's email from IdP |
| `X-Forwarded-Preferred-Username` | Username from IdP |
| `X-Forwarded-User` | User identifier from IdP |
| `X-Forwarded-Access-Token` | User's OAuth token (for downstream API calls) |

---

## 4. Delta Table Schema

### 4.1 `app_permissions` — Group-to-Permission Assignments

Stores which permissions are assigned to which Databricks Account groups.

```sql
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.app_permissions (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  group_name STRING NOT NULL,          -- Databricks Account group name (from IDP)
  permission_id STRING NOT NULL,       -- Operation: browse, upload, download, delete, 
                                       --   preview, detokenize, share, manage_permissions
  granted_by STRING NOT NULL,          -- Who assigned this permission
  granted_at TIMESTAMP NOT NULL DEFAULT current_timestamp(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,  -- Soft delete support
  CONSTRAINT pk_permissions PRIMARY KEY (group_name, permission_id)
);
```

**Seed data (default Admin permissions):**
```sql
INSERT INTO {catalog}.{schema}.app_permissions (group_name, permission_id, granted_by)
VALUES
  ('admin', 'browse', 'SYSTEM'),
  ('admin', 'upload', 'SYSTEM'),
  ('admin', 'download', 'SYSTEM'),
  ('admin', 'delete', 'SYSTEM'),
  ('admin', 'preview', 'SYSTEM'),
  ('admin', 'detokenize', 'SYSTEM'),
  ('admin', 'share', 'SYSTEM'),
  ('admin', 'manage_permissions', 'SYSTEM');
```

### 4.2 `app_audit_log` — Operation Audit Trail

Tracks all user operations for compliance and troubleshooting.

```sql
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.app_audit_log (
  event_id STRING NOT NULL DEFAULT uuid(),    -- Unique event ID
  event_timestamp TIMESTAMP NOT NULL DEFAULT current_timestamp(),
  user_id STRING NOT NULL,                    -- Databricks Account user ID
  user_email STRING,                          -- User email for readability
  action STRING NOT NULL,                     -- Operation performed
  resource_path STRING,                       -- File/resource acted upon
  details STRING,                             -- JSON blob: additional context
  status STRING NOT NULL,                     -- success, failure, denied
  ip_address STRING,                          -- Client IP (if available)
  session_id STRING                           -- Flask session ID
);
```

**Partitioning:** Partition by `event_timestamp` (daily) for query performance.

### 4.3 `app_group_mappings` — Group-to-Role Aliasing (Optional)

Maps Databricks Account groups to app-level role aliases. This provides a layer of indirection so that if IDP group names change, only the mapping needs updating.

```sql
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.app_group_mappings (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  databricks_group STRING NOT NULL,    -- Actual Databricks Account group name
  app_role STRING NOT NULL,            -- App role alias: admin, data_steward, analyst, viewer
  mapped_by STRING NOT NULL,
  mapped_at TIMESTAMP NOT NULL DEFAULT current_timestamp(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT pk_group_mappings PRIMARY KEY (databricks_group)
);
```

### 4.4 `app_available_permissions` — Permission Registry

Defines all available permissions in the system (self-documenting, extensible).

```sql
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.app_available_permissions (
  permission_id STRING NOT NULL PRIMARY KEY,
  display_name STRING NOT NULL,
  description STRING,
  category STRING,                     -- Grouping: file_ops, admin, tokenization
  created_at TIMESTAMP NOT NULL DEFAULT current_timestamp()
);
```

**Seed data:**
```sql
INSERT INTO {catalog}.{schema}.app_available_permissions 
  (permission_id, display_name, description, category)
VALUES
  ('browse', 'Browse Files', 'View list of files in Volume', 'file_ops'),
  ('upload', 'Upload Files', 'Upload and tokenize data files', 'file_ops'),
  ('download', 'Download Files', 'Download files from Volume', 'file_ops'),
  ('delete', 'Delete Files', 'Remove files from Volume', 'file_ops'),
  ('preview', 'Preview Files', 'View first N rows of a file', 'file_ops'),
  ('detokenize', 'Detokenize Files', 'Reverse tokenization (download only)', 'tokenization'),
  ('share', 'Share Files', 'Share files via Delta Sharing', 'file_ops'),
  ('manage_permissions', 'Manage Permissions', 'Assign permissions to groups', 'admin');
```

---

## 5. Permission Resolution Logic

### 5.1 Algorithm

```
get_user_permissions(user_groups):
  1. User's groups are resolved at login from config (Phase 1) or Delta table (Phase 2)
  2. For each group, optionally lookup app_group_mappings → get app_role
  3. Query app_permissions WHERE group_name IN (user_groups) AND is_active = TRUE
  4. Return UNION of all permission_ids
  5. Permissions are cached in Flask session for the duration of the session
```

### 5.2 Example

```
User: john.doe@company.com
Resolved Groups: ["analyst"]  (from config or app_group_mappings)

app_permissions:
  analyst → [browse, upload, download, preview]

Effective permissions: [browse, upload, download, preview]
(Stored in session['permissions'] at login)
```

---

## 6. Services

### 6.1 `services/permissions_service.py`

**Class:** `PermissionsService`

| Method | Purpose |
|--------|---------|
| `get_user_permissions(user_groups)` | Resolve all permissions for given groups |
| `has_permission(user_groups, permission_id)` | Single permission check |
| `get_all_available_permissions()` | List from app_available_permissions table |
| `get_group_permissions(group_name)` | Get permissions for a specific group |
| `grant_permission(group_name, permission_id, granted_by)` | Add permission assignment |
| `revoke_permission(group_name, permission_id)` | Soft-delete (set is_active=FALSE) |
| `get_all_group_assignments()` | Full matrix for admin UI |

### 6.2 `services/audit_service.py`

**Class:** `AuditService`

| Method | Purpose |
|--------|---------|
| `log_event(user, action, resource, details, status)` | Write audit record |
| `get_audit_log(filters, page, page_size)` | Query with pagination |
| `get_user_activity(user_id, since)` | User-specific history |

---

## 7. Middleware

### 7.1 `middleware/auth_middleware.py`

**Decorator:** `@require_permission(permission_id)`

```python
from functools import wraps
from flask import session, jsonify, request
from services.audit_service import audit_service

def require_permission(permission_id):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Check session exists
            if 'user_id' not in session:
                return jsonify({'error': 'Authentication required'}), 401
            
            # 2. Check permission (stored in session at login)
            user_permissions = session.get('permissions', [])
            if permission_id not in user_permissions:
                # 3. Log denied attempt
                audit_service.log_event(
                    user=session.get('username', 'unknown'),
                    action=permission_id,
                    resource=request.path,
                    details=None,
                    status='denied'
                )
                return jsonify({'error': 'Permission denied'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

**Usage in routes:**
```python
@file_ops_bp.route('/files/<path>/download')
@require_permission('download')
def download_file(path):
    ...
```

---

## 8. Admin Routes

### 8.1 `routes/admin_routes.py`

**Blueprint:** `admin_bp` (prefix: `/admin`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/permissions` | GET | Render permissions management page |
| `/admin/permissions/matrix` | GET | Return current permissions matrix as JSON |
| `/admin/permissions/grant` | POST | Grant permission to group |
| `/admin/permissions/revoke` | POST | Revoke permission from group |
| `/admin/groups` | GET | List all Databricks groups with their app permissions |
| `/admin/audit` | GET | Render audit log viewer page |
| `/admin/audit/search` | GET | Query audit log with filters |

**All admin routes require `manage_permissions` permission.**

---

## 9. Extensibility

### Adding a New Permission (Zero Code Changes)

1. Insert into `app_available_permissions` table:
   ```sql
   INSERT INTO app_available_permissions (permission_id, display_name, description, category)
   VALUES ('export_report', 'Export Reports', 'Export data as PDF/Excel report', 'file_ops');
   ```
2. Grant to desired groups via Admin UI (or SQL):
   ```sql
   INSERT INTO app_permissions (group_name, permission_id, granted_by)
   VALUES ('data_steward', 'export_report', 'admin@company.com');
   ```
3. Add `@require_permission('export_report')` to the new route

No service or model code changes needed — the system reads available permissions dynamically from Delta.

### Adding a New Group

1. Group is created in IDP → synced to Databricks Account
2. Map the group in `app_group_mappings` (or add to admin config)
3. Admin assigns permissions via Admin UI
4. Users in that group immediately get those permissions on next login

---

## 10. Files Delivered by This Feature

```
services/
├── permissions_service.py       # Delta table permission CRUD
└── audit_service.py             # Audit log write/query

middleware/
└── auth_middleware.py           # @require_permission decorator

routes/
└── admin_routes.py              # Admin permission management endpoints

models/
└── permission.py                # Permission, GroupPermission dataclasses

templates/admin/
├── permissions.html             # Permission assignment UI
└── audit.html                   # Audit log viewer

sql/
├── create_permissions_table.sql
├── create_audit_log_table.sql
├── create_group_mappings_table.sql
├── create_available_permissions_table.sql
└── seed_default_permissions.sql
```

---

## 11. Dependencies

- `databricks-sdk` — for downstream API calls using forwarded access token
- `flask` — session management, route decorators
- Delta table access via Databricks SQL or Spark SQL

---

## 12. Error Handling

| Scenario | Response |
|----------|----------|
| No session (missing headers) | 401: "Authentication required." |
| Permission denied | 403: "You don't have permission for this action." |
| Group not found | 400: "Group '{name}' not found in Databricks Account." |
| Delta table not accessible | 500: "Permission system unavailable. Contact admin." |
| Invalid permission_id | 400: "Unknown permission: '{id}'. Available: [...]" |
