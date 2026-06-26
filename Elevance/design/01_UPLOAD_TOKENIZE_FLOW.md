# Feature 01 — Upload & Tokenization

## 1. Feature Summary

A complete batch upload and tokenization pipeline that:
- Accepts **multiple data files** (CSV, Excel, TSV) up to **2 GB each**
- Associates each file with its own **processing template** + **Protegrity template**
- Tokenizes PII columns in-memory via Protegrity REST APIs
- Writes tokenized output to a **user-selectable** Databricks Unity Catalog Volume

---

## 2. What This Feature Delivers

- [x] Batch upload endpoint (multiple files per request)
- [x] Per-file template association (processing + Protegrity)
- [x] Processing template parser + validation
- [x] Protegrity template parser + validation
- [x] File parser service (CSV, TSV, Excel)
- [x] Synthetic Protegrity Client (5 tokenization functions)
- [x] Tokenization Orchestrator (coordinates full pipeline)
- [x] Volume Service — write to user-selected path
- [x] Status/results endpoint (per-file success/failure reporting)
- [x] Temp file cleanup after processing

---

## 3. Preconditions

- User is authenticated and has **Upload** permission (see Feature 02)
- Target Volume exists and app has WRITE VOLUME access
- User has prepared per file:
  - A **data file** (CSV, TSV, XLS, XLSX) — max **2 GB**
  - A **processing template** (JSON) — defines how to read the file
  - A **Protegrity template** (JSON) — defines tokenization functions per column

---

## 4. Flow Diagram

```
User Browser                          Flask App                           Databricks Volume
─────────────                         ─────────                           ─────────────────
     │                                     │                                     │
     │  1. Select files + templates        │                                     │
     │     (batch: N file groups)          │                                     │
     │  2. Select target Volume            │                                     │
     │  3. Click "Upload & Tokenize All"   │                                     │
     │─────────────────────────────────────▶│                                     │
     │     POST /upload/file               │                                     │
     │     (multipart: per-file groups)    │                                     │
     │                                     │                                     │
     │                                     │── 3. Validate files (size, type)    │
     │                                     │── 4. Save to /tmp/uploads           │
     │                                     │── FOR EACH FILE GROUP:              │
     │                                     │──   5. Parse processing template    │
     │                                     │──   6. Parse Protegrity template    │
     │                                     │──   7. Read data file → DataFrame   │
     │                                     │──   8. For each PII column:         │
     │                                     │──      tokenize_batch()             │
     │                                     │──   9. Write tokenized DataFrame    │
     │                                     │──────────────────────────────────── ▶│
     │                                     │──      to selected Volume           │
     │                                     │── END FOR EACH                      │
     │                                     │──10. Clean up temp files            │
     │◀────────────────────────────────────│                                     │
     │     Response: {results: [           │                                     │
     │       {file, status, output_path,   │                                     │
     │        rows, cols_tokenized},       │                                     │
     │       ...                           │                                     │
     │     ]}                              │                                     │
```

---

## 5. Processing Template (User-Defined)

A JSON file that tells the app **how to read the data file**.

### 5.1 Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_type` | string | Yes | Format: `csv`, `tsv`, `xlsx`, `xls` |
| `is_delimited` | boolean | Yes | Whether the file uses a delimiter |
| `delimiter` | string | Conditional | Delimiter char (required if `is_delimited: true`) |
| `has_header` | boolean | Yes | Whether first row contains column headers |
| `sheet_name` | string | No | For Excel — which sheet to read (default: first) |
| `pii_columns` | list[string] | Yes | Column names containing PII to tokenize |

### 5.2 Example

```json
{
  "file_type": "csv",
  "is_delimited": true,
  "delimiter": ",",
  "has_header": true,
  "sheet_name": null,
  "pii_columns": ["ssn", "email", "phone_number", "credit_card"]
}
```

### 5.3 Validation Rules

- `file_type` must be one of: `csv`, `tsv`, `xlsx`, `xls`
- If `is_delimited` is true, `delimiter` must be provided and non-empty
- `pii_columns` must be non-empty array
- All `pii_columns` values must exist as columns in the data file (validated at runtime)

---

## 6. Protegrity Template (Contract Format)

A JSON file in **Protegrity's fixed-pattern contract format** that maps each PII column to a tokenization function.

### 6.1 Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sessionId` | string | Yes | Protegrity session identifier |
| `dataElements` | list[object] | Yes | Data element definitions |
| `dataElements[].name` | string | Yes | Column name (must match data file) |
| `dataElements[].dataType` | string | Yes | Type: `STRING`, `NUMERIC`, `DATE` |
| `dataElements[].length` | int | Yes | Max field length |
| `tokenizeFunctions` | object | Yes | Map: column_name → function_name |

### 6.2 Supported Functions (Synthetic Implementation)

| Function | Behavior | Use Case |
|----------|----------|----------|
| `FPE_ASCII` | Format-preserving encryption (same length, char class) | SSN, Credit Card |
| `HASH_SHA256` | SHA-256 hash truncated to original length | Email addresses |
| `MASK` | First/last char visible, middle masked with `*` | Names |
| `TOKENIZE_NUMERIC` | Numeric shift tokenization | Phone numbers |
| `DEFAULT_TOKENIZE` | MD5-based token with `TOK_` prefix | Fallback/generic |

### 6.3 Example

```json
{
  "sessionId": "sess-001-abc",
  "dataElements": [
    {"name": "ssn", "dataType": "STRING", "length": 11},
    {"name": "email", "dataType": "STRING", "length": 255},
    {"name": "phone_number", "dataType": "STRING", "length": 15},
    {"name": "credit_card", "dataType": "STRING", "length": 19}
  ],
  "tokenizeFunctions": {
    "ssn": "FPE_ASCII",
    "email": "HASH_SHA256",
    "phone_number": "TOKENIZE_NUMERIC",
    "credit_card": "FPE_ASCII"
  }
}
```

### 6.4 Validation Rules

- Every column in `tokenizeFunctions` must also appear in `dataElements`
- Every column in `tokenizeFunctions` must appear in the processing template's `pii_columns`
- `dataType` must be one of: `STRING`, `NUMERIC`, `DATE`
- Function names must be from the supported set

---

## 7. Module Responsibilities

### 7.1 `routes/upload_routes.py`

**Blueprint:** `upload_bp` (prefix: `/upload`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload/` | GET | Render the batch upload form page |
| `/upload/file` | POST | Accept multipart batch upload, trigger pipeline |
| `/upload/volumes` | GET | Return list of available Volumes for selector |

**Logic:**
1. Check user has `Upload` permission (via middleware)
2. Validate all file groups have 3 files each
3. Validate file extensions of data files
4. Validate each file size ≤ 2 GB
5. Save to temp directory
6. For each file group: call `TokenizationOrchestrator.process()`
7. Return batch JSON result (per-file status)
8. Clean up temp files (finally block)

### 7.2 `services/file_parser.py`

**Class:** `FileParser`

| Method | Input | Output |
|--------|-------|--------|
| `parse(file_path, template)` | File path + ProcessingTemplate | pandas DataFrame |
| `_parse_delimited(path, template)` | Internal | DataFrame |
| `_parse_excel(path, template)` | Internal | DataFrame |

**Key behaviors:**
- All columns read as `dtype=str` (preserves format for tokenization)
- For files without headers, generates column names: `col_0`, `col_1`, ...
- Handles encoding detection for CSV files
- For files > 500 MB, uses chunked reading

### 7.3 `services/template_parser.py`

**Class:** `TemplateParser`

| Method | Input | Output |
|--------|-------|--------|
| `parse_processing_template(path)` | JSON file path | `FileProcessingTemplate` |
| `parse_protegrity_template(path)` | JSON file path | `ProtegrityTemplate` |
| `validate_templates(proc, prot)` | Both templates | Raises on mismatch |

### 7.4 `services/protegrity_client.py`

**Class:** `ProtegrityClient`

| Method | Input | Output |
|--------|-------|--------|
| `tokenize_batch(template, column_name, values)` | Template + column + list[str] | list[str] |
| `_synthetic_tokenize(value, function_name)` | Single value + function | str |

**Production swap:** Replace `_synthetic_tokenize` body with HTTP POST to real Protegrity DSG endpoint.

### 7.5 `services/tokenizer.py`

**Class:** `TokenizationOrchestrator`

| Method | Input | Output |
|--------|-------|--------|
| `process(data_path, proc_tmpl_path, prot_tmpl_path, volume_path)` | 3 file paths + target Volume | Result dict |
| `process_batch(file_groups, volume_path)` | List of file groups + Volume | List of results |

**Orchestration (per file):**
1. `TemplateParser.parse_processing_template()`
2. `TemplateParser.parse_protegrity_template()`
3. `TemplateParser.validate_templates()`
4. `FileParser.parse()`
5. For each PII column → `ProtegrityClient.tokenize_batch()`
6. `VolumeService.write_tokenized_file()`
7. Return `{output_path, rows_processed, columns_tokenized}`

---

## 8. Error Handling

| Step | Error | Response |
|------|-------|----------|
| Upload | Missing file in group | 400: "All 3 files required per group: data_file, processing_template, protegrity_template" |
| Upload | File too large | 413: "File exceeds 2 GB limit" |
| Upload | Bad extension | 400: "Unsupported format. Allowed: csv, tsv, xlsx, xls" |
| Template parse | Invalid JSON | 400: "Malformed template: {parse error}" |
| Template validate | Column mismatch | 400: "PII column 'X' not found. Available: [...]" |
| Tokenization | Function error | 500: "Tokenization failed for column 'X': {detail}" |
| Volume write | Permission denied | 500: "Cannot write to Volume. Check WRITE VOLUME permission." |
| Batch | Partial failure | 207: Mixed results — per-file status in response |

**Batch behavior:** If one file fails, continue processing remaining files. Return per-file status.

---

## 9. Performance Considerations

- **2 GB file handling**: Use chunked reading for very large files (pandas `chunksize` parameter)
- **Batch tokenization**: Process columns in batches of configurable size (default: 10,000 rows per batch)
- **Memory management**: Process one column at a time, not all simultaneously
- **Batch parallelism**: Process files sequentially (memory-safe) or optionally in parallel (configurable)
- **Gunicorn timeout**: Set to 120s for large file processing; consider async workers for 2 GB files

---

## 10. Files Delivered by This Feature

```
routes/
└── upload_routes.py             # Batch upload + Volume selector + trigger pipeline

services/
├── file_parser.py               # CSV/Excel/TSV → DataFrame
├── template_parser.py           # Parse + validate both template types
├── protegrity_client.py         # Tokenize via Protegrity (synthetic)
├── tokenizer.py                 # Orchestrate per-file and batch pipeline
└── volume_service.py            # Write tokenized output to Volume

models/
├── file_template.py             # FileProcessingTemplate dataclass
└── protegrity_template.py       # ProtegrityTemplate dataclass

sample_templates/
├── sample_processing_template.json
└── sample_protegrity_template.json
```
