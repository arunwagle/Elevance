# 03 — File Operations Flow

## 1. Purpose

This document defines the file management operations available to users after tokenized files are stored in the Databricks Volume: **Browse**, **Download**, **Delete**, **Preview**, **Detokenize**, and **Share**.

---

## 2. Operations Summary

| Operation | Permission | HTTP Endpoint | Description |
|-----------|-----------|---------------|-------------|
| Browse | `browse` | GET `/files/` | List files in the Volume |
| Download | `download` | GET `/files/<path>/download` | Download a file from Volume |
| Delete | `delete` | DELETE `/files/<path>` | Remove a file from Volume |
| Preview | `preview` | GET `/files/<path>/preview` | View first N rows |
| Detokenize | `detokenize` | POST `/files/<path>/detokenize` | Reverse tokenization |
| Share | `share` | POST `/files/<path>/share` | Grant access to users/groups |

---

## 3. Browse Flow

### 3.1 Behavior

- Lists all files in the configured Volume path
- Displays: filename, size, upload date, uploaded_by, tokenization status
- Supports folder navigation within the Volume
- Sortable columns
- Actions shown per file based on user's permissions

### 3.2 Sequence

```
User                          Flask App                     Volume Service
────                          ─────────                     ──────────────
  │  GET /files/                   │                              │
  │───────────────────────────────▶│                              │
  │                                │── list_directory_contents() ─▶│
  │                                │◀── file list ────────────────│
  │◀───────────────────────────────│                              │
  │  Render browse.html            │                              │
  │  (with permission-filtered     │                              │
  │   action buttons per file)     │                              │
```

### 3.3 File Metadata

Each file entry displays:

| Field | Source |
|-------|--------|
| Filename | Volume path |
| Size | File metadata |
| Upload Date | File metadata / naming convention timestamp |
| Format | File extension |
| Status | `tokenized` / `detokenized` / `raw` |

---

## 4. Download Flow

### 4.1 Behavior

- Streams file from Volume to user's browser
- Supports large files (streaming, not loading into memory)
- Sets proper Content-Disposition header for browser download dialog

### 4.2 Sequence

```
User                          Flask App                     Volume Service
────                          ─────────                     ──────────────
  │  GET /files/<path>/download    │                              │
  │───────────────────────────────▶│                              │
  │                                │── Check 'download' perm      │
  │                                │── download(path) ────────────▶│
  │                                │◀── file stream ──────────────│
  │◀───────────────────────────────│                              │
  │  File download (streamed)      │                              │
```

### 4.3 Implementation Notes

- Use `databricks-sdk` `files.download()` to get a streaming response
- Set `Content-Type` based on file extension
- Set `Content-Disposition: attachment; filename="..."`
- For files > 100 MB, use chunked transfer encoding

---

## 5. Delete Flow

### 5.1 Behavior

- Removes a file from the Volume permanently
- Requires confirmation in the UI before proceeding
- Logged for audit trail

### 5.2 Sequence

```
User                          Flask App                     Volume Service
────                          ─────────                     ──────────────
  │  DELETE /files/<path>          │                              │
  │  (after UI confirmation)       │                              │
  │───────────────────────────────▶│                              │
  │                                │── Check 'delete' perm        │
  │                                │── delete(path) ──────────────▶│
  │                                │◀── success ──────────────────│
  │◀───────────────────────────────│                              │
  │  200: {status: "deleted"}      │                              │
```

### 5.3 Safeguards

- UI shows confirmation modal: "Are you sure you want to delete {filename}?"
- Server validates the file path is within the configured Volume (no path traversal)
- Delete action is logged: `{user, file, timestamp}`

---

## 6. Preview Flow

### 6.1 Behavior

- Shows the first N rows (default: 50, configurable) of a file in a table view
- Does NOT download the entire file — reads only the needed portion
- Supports CSV and Excel formats
- Displays column headers and data types

### 6.2 Sequence

```
User                          Flask App                     Volume Service
────                          ─────────                     ──────────────
  │  GET /files/<path>/preview     │                              │
  │  ?rows=50                      │                              │
  │───────────────────────────────▶│                              │
  │                                │── Check 'preview' perm       │
  │                                │── download(path) ────────────▶│
  │                                │◀── file content (partial) ───│
  │                                │── Parse first N rows          │
  │◀───────────────────────────────│                              │
  │  Render preview.html           │                              │
  │  (HTML table with N rows)      │                              │
```

### 6.3 Implementation Notes

- For CSV: use `pandas.read_csv(nrows=N)` on the downloaded stream
- For Excel: use `pandas.read_excel(nrows=N)`
- Display as HTML table with horizontal scroll for wide files
- Show total row count if available (file size heuristic)

---

## 7. Detokenize Flow

### 7.1 Behavior

- Reverses the tokenization on a previously tokenized file
- Requires the user to upload the **same Protegrity template** used during tokenization
- Calls Protegrity's detokenize API (or synthetic reverse)
- Result is available for **download only** — not stored in Volume (security)

### 7.2 Sequence

```
User                          Flask App                     Protegrity Client
────                          ─────────                     ─────────────────
  │  POST /files/<path>/detokenize │                              │
  │  {protegrity_template}         │                              │
  │───────────────────────────────▶│                              │
  │                                │── Check 'detokenize' perm    │
  │                                │── Download file from Volume   │
  │                                │── Parse into DataFrame        │
  │                                │── For each tokenized column:  │
  │                                │    detokenize_batch() ────────▶│
  │                                │◀── original values ──────────│
  │                                │── Convert to download format  │
  │◀───────────────────────────────│                              │
  │  File download (detokenized)   │                              │
  │  (streamed, NOT stored)        │                              │
```

### 7.3 Design Decisions

- **Detokenized output is NEVER stored** on disk or in Volume — streamed directly to user
- This ensures raw PII is only accessible in-transit to authorized users
- Requires same Protegrity template to know which columns/functions to reverse
- Audit log records: who detokenized what, when

### 7.4 Synthetic Detokenize Implementation

Each synthetic function has a reverse:

| Function | Reverse Logic |
|----------|---------------|
| `FPE_ASCII` | Reverse character shift |
| `HASH_SHA256` | **Not reversible** — return `[HASH-IRREVERSIBLE]` |
| `MASK` | **Not reversible** — return `[MASKED-IRREVERSIBLE]` |
| `TOKENIZE_NUMERIC` | Reverse digit shift |
| `DEFAULT_TOKENIZE` | **Not reversible** — return `[TOKEN-IRREVERSIBLE]` |

Note: In production, Protegrity's real API handles reversibility based on vault/key management.

---

## 8. Share Flow

### 8.1 Behavior

- Allows an Admin to grant specific users or groups access to individual files
- Sharing creates a record that's checked during Browse/Download/Preview
- Does NOT copy files — just grants visibility

### 8.2 Share Model

```json
{
  "file_path": "/Volumes/main/default/tokenized-files/data_tokenized_20240101.csv",
  "shared_by": "admin",
  "shared_with": [
    {"type": "user", "id": "u002"},
    {"type": "group", "id": "analyst"}
  ],
  "permissions": ["browse", "download", "preview"],
  "shared_at": "2024-01-15T10:30:00Z",
  "expires_at": null
}
```

### 8.3 Sequence

```
Admin                         Flask App                     Permissions Store
─────                         ─────────                     ─────────────────
  │  POST /files/<path>/share      │                              │
  │  {shared_with, permissions}    │                              │
  │───────────────────────────────▶│                              │
  │                                │── Check 'share' perm         │
  │                                │── Save share record ─────────▶│
  │◀───────────────────────────────│                              │
  │  200: {status: "shared"}       │                              │
```

### 8.4 Design Decisions

- File-level sharing (not folder-level for now)
- Share grants specific operations (browse, download, preview) — never delete/detokenize
- Optional expiration date for time-limited access
- Admin can revoke shares at any time

---

## 9. Module Responsibilities

### 9.1 `routes/file_ops_routes.py`

**Blueprint:** `file_ops_bp` (prefix: `/files`)

| Endpoint | Method | Permission | Purpose |
|----------|--------|-----------|---------|
| `/files/` | GET | `browse` | List files |
| `/files/<path>/download` | GET | `download` | Download file |
| `/files/<path>` | DELETE | `delete` | Delete file |
| `/files/<path>/preview` | GET | `preview` | Preview rows |
| `/files/<path>/share` | POST | `share` | Share file |

### 9.2 `routes/detokenize_routes.py`

**Blueprint:** `detokenize_bp` (prefix: `/detokenize`)

| Endpoint | Method | Permission | Purpose |
|----------|--------|-----------|---------|
| `/detokenize/<path>` | GET | `detokenize` | Render detokenize form |
| `/detokenize/<path>` | POST | `detokenize` | Execute detokenization + stream download |

### 9.3 `services/volume_service.py` (Extended)

| Method | Purpose |
|--------|---------|
| `list_files(path)` | List directory contents |
| `download_file(path)` | Stream file content |
| `delete_file(path)` | Remove file |
| `read_preview(path, nrows)` | Read first N rows |
| `write_tokenized_file(df, filename, ...)` | Write tokenized output |
| `get_file_metadata(path)` | Get size, modified date |

### 9.4 `services/detokenizer.py`

**Class:** `DetokenizationOrchestrator`

| Method | Purpose |
|--------|---------|
| `detokenize(file_path, protegrity_template_path)` | Full reverse pipeline |

---

## 10. Error Handling

| Operation | Error | Response |
|-----------|-------|----------|
| Browse | Volume not accessible | 500: "Cannot access Volume. Check configuration." |
| Download | File not found | 404: "File not found at specified path." |
| Delete | File not found | 404: "File not found." |
| Delete | Permission denied | 403: "You don't have permission to delete files." |
| Preview | Unsupported format | 400: "Cannot preview this file format." |
| Detokenize | Missing template | 400: "Protegrity template required for detokenization." |
| Detokenize | Irreversible function | 200: Partial result with `[IRREVERSIBLE]` markers |
| Share | Invalid user/group | 400: "User or group not found." |
