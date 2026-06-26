# Feature 05 — Login & Session Management

## 1. Feature Summary

Authentication and session management using **Databricks Apps platform identity**:
- **No login form** — users are authenticated by the Databricks platform before reaching the app
- User identity is passed via **X-Forwarded-\* HTTP headers** from the platform reverse proxy
- Manages **Flask sessions** (inactivity timeout **disabled for Phase 1**, re-enable later)
- Implements **client-side inactivity detection** (JS timer) + server-side enforcement
- Handles auto-login, logout, and session refresh flows

---

## 2. What This Feature Delivers

- [x] Automatic user authentication via platform headers (no login form)
- [x] Identity resolution from X-Forwarded-Email / X-Forwarded-Preferred-Username
- [x] Flask session creation with user info + groups + permissions
- [x] Session timeout middleware (1-min inactivity, server-side)
- [x] Client-side inactivity timer (JS) with warning modal
- [x] Logout route (explicit + timeout-triggered)
- [x] Session refresh on activity (heartbeat endpoint)
- [x] Redirect-to-login on expired session (re-creates session from headers)

---

## 3. Authentication Strategy

### 3.1 Platform-Based Identity (Databricks Apps)

Databricks Apps authenticates users **at the platform level** before requests reach the app. The platform injects identity via HTTP headers:

| Header | Description |
|--------|-------------|
| `X-Forwarded-Email` | User's email from IdP |
| `X-Forwarded-Preferred-Username` | Username from IdP |
| `X-Forwarded-User` | User identifier from IdP |
| `X-Forwarded-Access-Token` | User's OAuth access token (for downstream API calls) |

**No login form is needed.** The `/login` route reads headers and creates a session automatically.

### 3.2 Group Resolution

| Phase | Approach |
|-------|----------|
| Phase 1 | Admin list in `config.py` (env var `ADMIN_USERS`). All other users get `analyst` group. |
| Phase 2 | Query Delta table `app_group_mappings` for email-to-group assignments. |
| Phase 3 | SCIM group sync from Databricks Account API. |

### 3.3 Identity Resolution

```python
# How we get user info from Databricks Apps headers
from flask import request

email = request.headers.get('X-Forwarded-Email')
username = request.headers.get('X-Forwarded-Preferred-Username')
user_id = request.headers.get('X-Forwarded-User')
access_token = request.headers.get('X-Forwarded-Access-Token')
```

---

## 4. Login Flow

### 4.1 Sequence Diagram

```
User (Browser)                Databricks Platform              Flask App
──────────────                ────────────────────              ─────────
  │                                   │                            │
  │  Access app URL                   │                            │
  │──────────────────────────────────▶│                            │
  │                                   │── Authenticate user (SSO)  │
  │                                   │── Inject X-Forwarded-*     │
  │                                   │   headers                  │
  │                                   │───────────────────────────▶│
  │                                   │                            │── Check session?
  │                                   │                            │   NO → /auth/login
  │◀──────────────────────────────────────────────────────────────│
  │  302 → /auth/login                                             │
  │                                                                │
  │  GET /auth/login (with X-Forwarded-* headers)                  │
  │───────────────────────────────────────────────────────────────▶│
  │                                                                │── Read headers
  │                                                                │── Resolve groups
  │                                                                │── Create session:
  │                                                                │   {user_id, email,
  │                                                                │    groups, perms,
  │                                                                │    last_activity}
  │◀───────────────────────────────────────────────────────────────│
  │  302 → /dashboard                                           │
  │                                                                │
```

### 4.2 Auto-Login Behavior

- **No form is shown** — the platform has already authenticated the user
- On first request, middleware redirects to `/auth/login`
- `/auth/login` reads `X-Forwarded-*` headers, creates session, redirects to `/dashboard`
- If headers are missing (direct access without platform), returns 401
- After logout, `/auth/login` re-creates session from headers (user is still authenticated at platform level)

---

## 5. Session Management

### 5.1 Session Data Structure

```python
session = {
    'user_id': 'arun.wagle',
    'username': 'arun.wagle',
    'display_name': 'arun.wagle',
    'email': 'arun.wagle@databricks.com',
    'groups': ['admin'],
    'permissions': ['browse', 'upload', 'download', 'delete', 'preview',
                    'detokenize', 'share', 'manage_permissions'],
    'last_activity': 1705312200.0,  # time.time() — updated on every request
    'timeout_seconds': 60,
}
```

### 5.2 Inactivity Timeout — Server Side

> **⚠️ Phase 1:** Timeout check is **disabled** in `auth_middleware.py` to avoid blocking the app during development. Only session existence is checked. The timeout logic below will be re-enabled in Phase 4.


**Middleware:** `middleware/session_middleware.py`

```python
import time
from flask import session, redirect, url_for, request

def check_session_timeout():
    """Before-request hook to enforce inactivity timeout."""
    # Skip for auth routes and static files
    if request.path.startswith('/auth') or request.path.startswith('/static'):
        return None

    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    last_activity = session.get('last_activity')
    timeout_seconds = session.get('timeout_seconds', 60)

    if last_activity:
        elapsed = time.time() - last_activity
        if elapsed > timeout_seconds:
            session.clear()
            return redirect(url_for('auth.login'))

    # Update last activity timestamp
    session['last_activity'] = time.time()
    return None
```

### 5.3 Inactivity Timeout — Client Side

**File:** `static/js/session.js`

Purpose: Warn user before session expires, auto-redirect on timeout.

```
┌─────────────────────────────────────────────┐
│ Client-Side Inactivity Timer                 │
│                                              │
│ Activity events: mousemove, keypress, click, │
│                  scroll, touch               │
│                                              │
│ On activity → POST /auth/heartbeat           │
│               (resets server-side timer)      │
│                                              │
│ 45 seconds idle → Show warning modal:        │
│   "Session expiring in 15 seconds..."        │
│   [Stay Logged In] button                    │
│                                              │
│ 60 seconds idle → redirect to /auth/login    │
│                   (auto re-creates session)   │
└─────────────────────────────────────────────┘
```

### 5.4 Heartbeat Endpoint

```
POST /auth/heartbeat → 200 {status: "alive"}
                     → 401 {status: "expired"}
```

Called by client JS on user activity (debounced to max once per 10 seconds). Resets the server-side `last_activity` timestamp.

---

## 6. Logout Flow

### 6.1 Explicit Logout

```
User clicks "Logout" → POST /auth/logout → session.clear() → redirect /auth/login
                                                              (auto re-creates session)
```

Note: Since the platform still has the user authenticated, `/auth/login` will immediately re-create the session. Logout effectively resets the inactivity timer and re-resolves groups/permissions.

### 6.2 Timeout Logout

```
Client JS detects 60s idle → redirect /auth/login (re-creates session from headers)
Server middleware detects stale last_activity → session.clear() → redirect /auth/login
```

---

## 7. Routes

### 7.1 `routes/auth_routes.py`

**Blueprint:** `auth_bp` (prefix: `/auth`)

| Endpoint | Method | Auth Required | Purpose |
|----------|--------|:-------------:|---------|
| `/auth/login` | GET | ❌ | Auto-create session from platform headers, redirect to browse |
| `/auth/logout` | POST/GET | ✅ | Destroy session, redirect to login |
| `/auth/heartbeat` | POST | ✅ | Refresh session (called by JS timer) |

---

## 8. Services

### 8.1 `services/auth_service.py`

**Class:** `AuthService`

| Method | Purpose |
|--------|---------|
| `get_user_from_headers()` | Extract identity from X-Forwarded-* headers |
| `_resolve_groups(email)` | Map email to groups (admin list or default) |
| `create_session(user)` | Populate Flask session with user data + permissions |
| `get_current_user()` | Read user from active session |
| `ensure_session()` | Get user from session OR create from headers |
| `get_access_token()` | Get X-Forwarded-Access-Token for downstream calls |
| `refresh_activity()` | Update last_activity timestamp |
| `destroy_session()` | Clear all session data |

---

## 9. Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TIMEOUT_SECONDS` | `60` | Inactivity timeout (1 minute) |
| `SECRET_KEY` | (secret) | Flask session signing key |
| `ADMIN_USERS` | `arun.wagle@databricks.com` | Comma-separated admin emails |
| `SESSION_COOKIE_SECURE` | `True` | HTTPS-only cookies |
| `SESSION_COOKIE_HTTPONLY` | `True` | Prevent JS access to session cookie |

---

## 10. Files Delivered by This Feature

```
routes/
└── auth_routes.py               # Auto-login, logout, heartbeat

services/
└── auth_service.py              # Identity resolution from headers + session logic

middleware/
└── session_middleware.py        # Before-request timeout check

templates/
└── components/
    └── timeout_modal.html       # Session expiring warning modal

static/js/
└── session.js                   # Client-side inactivity timer + heartbeat
```

Note: `login.html` template is no longer needed (no login form).

---

## 11. Security Considerations

- Session cookie: `Secure`, `HttpOnly`, `SameSite=Lax`
- CSRF protection on state-changing routes (flask-wtf)
- All requests authenticated at platform level before reaching app
- Failed identity resolution logged to audit table
- Session ID rotated on login (prevent session fixation)
- No sensitive data in client-visible session cookie (server-side session)
- Access token from headers used only for downstream API calls, never stored

---

## 12. Error Handling

| Scenario | Response |
|----------|----------|
| Missing identity headers | 401: "Unauthorized: No Databricks identity found in request headers." |
| Session expired (server-side) | 302 → `/auth/login` (auto re-creates session) |
| Heartbeat with no session | 401: `{status: "expired"}` (JS handles redirect) |
| Group resolution failure | Default to `analyst` group with basic permissions |
