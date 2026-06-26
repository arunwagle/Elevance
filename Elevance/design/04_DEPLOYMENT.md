# 04 — Deployment & Configuration

## 1. Purpose

This document defines the deployment configuration, environment setup, and operational details for deploying the **Carelon App** via Declarative Asset Bundles (DAB).

---

## 2. Bundle Configuration (`databricks.yml`)

```yaml
bundle:
  name: carelon_app_bundle

resources:
  apps:
    carelon_app:
      name: 'carelon-app'
      source_code_path: ./apps
      description: 'Carelon Data Tokenization App — PII protection using Protegrity REST APIs'

      # OAuth scopes for on-behalf-of user authorization (files only)
      # Volume operations use the user's token with 'files' scope.
      # Jobs/Clusters admin ops use the app's service principal token
      # (no 'jobs' scope available in Public Preview user auth).
      user_api_scopes:
        - 'files'

      permissions:
        - level: CAN_USE
          group_name: users

targets:
  dev:
    mode: development
    default: true
    workspace:
      host: https://fevm-aw-serverless-stable.cloud.databricks.com
  prod:
    mode: production
    workspace:
      host: https://fevm-aw-serverless-stable.cloud.databricks.com
      root_path: /Workspace/Users/arun.wagle@databricks.com/.bundle/${bundle.name}/${bundle.target}
    permissions:
      - user_name: arun.wagle@databricks.com
        level: CAN_MANAGE
```

---

## 3. App Runtime Configuration (`apps/app.yaml`)

```yaml
command:
  - gunicorn
  - app:app
  - --bind
  - 0.0.0.0:${DATABRICKS_APP_PORT}
  - -w
  - 4
  - --timeout
  - '120'
  - --max-requests
  - '1000'
  - --max-requests-jitter
  - '50'
env:
  - name: 'VOLUME_PATH'
    value: '/Volumes/main/default/tokenized-files'
  - name: 'PROTEGRITY_API_BASE_URL'
    value: 'http://localhost:5001/api/v1'
  - name: 'FLASK_ENV'
    value: 'production'
  - name: 'MAX_UPLOAD_SIZE_MB'
    value: '2048'
  - name: 'SESSION_TIMEOUT_HOURS'
    value: '8'
  - name: 'PREVIEW_DEFAULT_ROWS'
    value: '50'
  - name: 'ADMIN_USERS'
    value: 'arun.wagle@databricks.com'
  - name: 'SECRET_KEY'
    valueFrom: 'secret/carelon-app/flask-secret-key'
  - name: 'PROTEGRITY_API_KEY'
    valueFrom: 'secret/carelon-app/api-key'
```

---

## 4. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABRICKS_APP_PORT` | (injected) | Port assigned by Databricks platform |
| `VOLUME_PATH` | `/Volumes/main/default/tokenized-files` | Target UC Volume for output |
| `PROTEGRITY_API_BASE_URL` | `http://localhost:5001/api/v1` | Protegrity DSG endpoint |
| `PROTEGRITY_API_KEY` | (secret) | API key for Protegrity auth |
| `PROTEGRITY_API_TIMEOUT` | `30` | HTTP timeout in seconds |
| `MAX_UPLOAD_SIZE_MB` | `2048` | Max upload size (2 GB) |
| `FLASK_ENV` | `production` | Flask environment |
| `SECRET_KEY` | (secret) | Flask session signing key |
| `SESSION_TIMEOUT_HOURS` | `8` | Login session duration |
| `PREVIEW_DEFAULT_ROWS` | `50` | Default rows for file preview |
| `ADMIN_USERS` | `arun.wagle@databricks.com` | Comma-separated admin emails (full permissions) |
| `PERMISSIONS_FILE_PATH` | `data/permissions.json` | Path to permissions store |

---

## 5. Dependencies (`apps/requirements.txt`)

```
flask>=3.0.0
gunicorn>=21.2.0
pandas>=2.1.0
openpyxl>=3.1.0
requests>=2.31.0
databricks-sdk>=0.72.0
python-dotenv>=1.0.0
werkzeug>=3.0.0
bcrypt>=4.1.0
flask-wtf>=1.2.0
```

| Package | Purpose |
|---------|---------|
| flask | Web framework |
| gunicorn | Production WSGI server |
| pandas | DataFrame operations for file parsing |
| openpyxl | Excel file read/write support |
| requests | HTTP client (real Protegrity API calls) |
| databricks-sdk | Unity Catalog Volume operations |
| python-dotenv | Local dev environment variable loading |
| werkzeug | Secure file handling utilities |
| bcrypt | Password hashing for user auth |
| flask-wtf | CSRF protection for forms |

---

## 6. Deployment Methods

### 6.0 Deploy from Workspace (Recommended — No Git Required)

**From the Databricks Apps UI:**
1. Go to **Apps** → Select `carelon-app` → Click **Deploy**
2. Browse to: `/Workspace/Users/arun.wagle@databricks.com/Elevance/carelon-app/apps`
3. Click **Select**, then **Deploy**

**From CLI:**
```bash
databricks apps deploy carelon-app \
  --source-code-path /Workspace/Users/arun.wagle@databricks.com/Elevance/carelon-app/apps
```

### 6.1 First-Time Setup (via DAB)

```bash
# 1. Validate the bundle configuration
databricks bundle validate

# 2. Deploy the bundle to the dev workspace
databricks bundle deploy

# 3. Start the app (first deploy)
databricks bundle run carelon_app

# 4. Check deployment status
databricks bundle summary
```

### 6.2 Iterative Development

```bash
# After code changes:
databricks bundle deploy

# The app auto-redeploys on bundle deploy.
# To manually restart:
databricks apps restart carelon-app
```

### 6.3 Production Deployment

```bash
# Deploy to production target
databricks bundle deploy --target prod

# Verify
databricks bundle summary --target prod
```

---

## 7. Volume Setup (Pre-requisite)

Before deploying the app, ensure the target Volume exists:

```sql
-- Create catalog/schema if needed
CREATE CATALOG IF NOT EXISTS main;
CREATE SCHEMA IF NOT EXISTS main.default;

-- Create the Volume for tokenized output
CREATE VOLUME IF NOT EXISTS main.default.`tokenized-files`
COMMENT 'Stores tokenized data files from Carelon App';

-- Grant the app service principal write access
GRANT WRITE VOLUME ON VOLUME main.default.`tokenized-files`
TO `carelon-app`;

GRANT READ VOLUME ON VOLUME main.default.`tokenized-files`
TO `carelon-app`;
```

---

## 8. Configuration Module (`apps/config.py`)

```python
import os

class Config:
    # Volume
    VOLUME_PATH = os.environ.get('VOLUME_PATH', '/Volumes/main/default/tokenized-files')

    # Protegrity
    PROTEGRITY_API_BASE_URL = os.environ.get('PROTEGRITY_API_BASE_URL', 'http://localhost:5001/api/v1')
    PROTEGRITY_API_TIMEOUT = int(os.environ.get('PROTEGRITY_API_TIMEOUT', '30'))
    PROTEGRITY_API_KEY = os.environ.get('PROTEGRITY_API_KEY', '')

    # Upload
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '2048')) * 1024 * 1024

    # Auth
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
    SESSION_TIMEOUT_HOURS = int(os.environ.get('SESSION_TIMEOUT_HOURS', '8'))
    PERMISSIONS_FILE_PATH = os.environ.get('PERMISSIONS_FILE_PATH', 'data/permissions.json')

    # Admin users (get full admin group permissions)
    ADMIN_USERS = [
        e.strip() for e in
        os.environ.get('ADMIN_USERS', 'arun.wagle@databricks.com').split(',')
    ]

    # File operations
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'tsv'}
    UPLOAD_FOLDER = '/tmp/uploads'
    PREVIEW_DEFAULT_ROWS = int(os.environ.get('PREVIEW_DEFAULT_ROWS', '50'))
```

---

## 9. Secrets Management

For production, sensitive values use `valueFrom` in `app.yaml` to reference Databricks secrets:

```yaml
env:
  - name: 'ADMIN_USERS'
    value: 'arun.wagle@databricks.com'
  - name: 'SECRET_KEY'
    valueFrom: 'secret/carelon-app/flask-secret-key'
  - name: 'PROTEGRITY_API_KEY'
    valueFrom: 'secret/carelon-app/api-key'
```

**Setup secrets:**
```bash
# Create a secret scope
databricks secrets create-scope carelon-app

# Store the Flask secret key
databricks secrets put-secret carelon-app flask-secret-key

# Store the Protegrity API key
databricks secrets put-secret carelon-app api-key
```

---

## 10. OAuth Scope & Token Architecture

### 10.1 User Authorization (on-behalf-of)

| API | Scope | Token Source |
|-----|-------|--------------|
| Files API (Volume browse/upload/download) | `files` | `X-Forwarded-Access-Token` |
| SQL Statement API (ABAC policies) | `sql` | `X-Forwarded-Access-Token` |

### 10.2 App Authorization (service principal)

| API | Auth Method | Token Source |
|-----|-------------|--------------|
| Jobs API (list/create) | `client_credentials` | SP token via `/oidc/v1/token` |
| Clusters API (create) | `client_credentials` | SP token via `/oidc/v1/token` |

> **Why?** `jobs` and `compute` scopes don't exist in the Public Preview user authorization model.
> Admin operations use the SP token. The SP must be added to the `users` group for job visibility.

### 10.3 SDK Configuration

All `WorkspaceClient` calls that use the user token MUST set `auth_type='pat'` to avoid conflict with the SP env vars (`DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) auto-injected by the platform.

```python
# Volume operations — user identity
WorkspaceClient(host=host, token=user_token, auth_type='pat')

# Admin operations — SP identity (client_credentials flow)
requests.post(f'{host}/oidc/v1/token', data={
    'grant_type': 'client_credentials',
    'client_id': os.environ['DATABRICKS_CLIENT_ID'],
    'client_secret': os.environ['DATABRICKS_CLIENT_SECRET'],
    'scope': 'all-apis',
})
```

### 10.4 Post-Deploy Setup

1. Run `notebooks/setup_app_scopes` to configure `user_api_scopes` via SDK
2. Add the app SP to the `users` group (Settings → Identity & Access → Groups → users → Add member)
3. Revoke existing OAuth consent (notebook handles this) so users get fresh tokens
4. Users re-consent on next app access in incognito window

---

## 11. Monitoring & Health

### 10.1 Health Check Endpoint

```
GET /health → {"status": "healthy", "app": "carelon-app"}
```

### 10.2 Logging

- All requests logged with: timestamp, user, endpoint, method, status code
- Auth events: login success/failure, permission denied
- File operations: upload, delete, detokenize, share
- Errors: full stack traces for 500s

### 10.3 Gunicorn Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Workers (`-w`) | 4 | Handle concurrent users |
| Timeout | 120s | Large file processing (up to 2 GB) |
| Max requests | 1000 | Worker recycling to prevent memory leaks |
| Max requests jitter | 50 | Prevent all workers recycling simultaneously |

---

## 11. Local Development

For local testing before deploying:

```bash
# Install dependencies
pip install -r apps/requirements.txt

# Set environment variables
export VOLUME_PATH="/tmp/local-volume"
export FLASK_ENV="development"
export SECRET_KEY="local-dev-key"

# Run with Flask dev server (from apps/ directory)
cd apps && python app.py

# Or with Gunicorn (closer to production)
cd apps && gunicorn app:app --bind 0.0.0.0:8000 -w 2
```

Note: Local dev uses filesystem instead of Databricks Volume. The `VolumeService` should support a local filesystem fallback when `FLASK_ENV=development`.

---

## 12. Folder Structure at Deployment

The project root (`carelon-app/`) contains the bundle config and supporting assets. Only the `apps/` directory (UI + Flask dependencies) is deployed as the Databricks App:

```
carelon-app/
├── databricks.yml                      # DAB bundle config (stays at root)
├── sql/                                # DDL scripts (run separately, not deployed with app)
│   ├── create_permissions_table.sql
│   ├── create_audit_log_table.sql
│   ├── create_group_mappings_table.sql
│   ├── create_available_permissions_table.sql
│   └── seed_default_permissions.sql
├── tests/                              # Unit/integration tests (not deployed with app)
│   ├── test_file_parser.py
│   ├── test_template_parser.py
│   ├── test_protegrity_client.py
│   ├── test_tokenizer.py
│   ├── test_permissions.py
│   └── test_auth.py
├── sample_templates/                   # Reference templates (not deployed with app)
│   ├── sample_processing_template.json
│   └── sample_protegrity_template.json
└── apps/                               # ← Deployed as the Databricks App
    ├── app.yaml                        # App runtime config (gunicorn, env vars)
    ├── requirements.txt                # Python dependencies
    ├── app.py                          # Flask app entry point
    ├── config.py                       # Configuration module
    ├── routes/
    │   ├── __init__.py
    │   ├── auth_routes.py
    │   ├── upload_routes.py
    │   ├── file_ops_routes.py
    │   ├── share_routes.py
    │   ├── detokenize_routes.py
    │   └── admin_routes.py
    ├── services/
    │   ├── __init__.py
    │   ├── auth_service.py
    │   ├── permissions_service.py
    │   ├── audit_service.py
    │   ├── file_parser.py
    │   ├── template_parser.py
    │   ├── protegrity_client.py
    │   ├── tokenizer.py
    │   ├── detokenizer.py
    │   ├── volume_service.py
    │   └── sharing_service.py
    ├── models/
    │   ├── __init__.py
    │   ├── user.py
    │   ├── permission.py
    │   ├── file_template.py
    │   └── protegrity_template.py
    ├── middleware/
    │   ├── __init__.py
    │   ├── auth_middleware.py
    │   └── session_middleware.py
    ├── templates/
    │   ├── layout.html
    │   ├── login.html
    │   ├── dashboard.html
    │   ├── upload.html
    │   ├── browse.html
    │   ├── preview.html
    │   ├── share.html
    │   ├── status.html
    │   ├── admin/
    │   │   ├── permissions.html
    │   │   └── audit.html
    │   └── components/
    │       ├── sidebar.html
    │       ├── tab_bar.html
    │       ├── context_menu.html
    │       ├── confirm_modal.html
    │       └── timeout_modal.html
    └── static/
        ├── css/styles.css
        └── js/
            ├── upload.js
            ├── browse.js
            ├── session.js
            └── admin.js
```

The `source_code_path: ./apps` in `databricks.yml` tells DAB to package and deploy only the `apps/` directory as the application code. Everything at the root (`sql/`, `tests/`, `sample_templates/`, `databricks.yml`) supports development and operations but is NOT included in the deployed app artifact.
