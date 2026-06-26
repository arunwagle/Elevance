# Feature 06 — UI Design & Mockup

## 1. Feature Summary

Defines all **user interface pages**, **layouts**, **navigation**, **UX flows**, and **client-side behavior** for the Protegrity Tokenizer App — modeled after the existing Carelon Dx Utility UI patterns.

---

## 2. Design Reference

The UI follows the existing **Carelon Dx Utility** application patterns:
- Left sidebar icon navigation
- Purple/violet brand color scheme
- Form-based upload with metadata dropdowns
- Tab-based sub-navigation within pages
- Breadcrumb-style file/folder browsing
- Action dots (•••) per row in data tables
- Approval workflow indicators

---

## 2.1 Key UI Behaviors (Implemented)

- **Header brand** ("🔐 Carelon Tokenizer") is a clickable link → navigates to `/dashboard`
- **Landing page** is the Dashboard (`/dashboard`), NOT the browse page
- **No login form** — user is auto-authenticated via platform; session created on first request
- **Session timeout modal** is disabled for Phase 1
- **Browse page** gracefully handles missing Volume (shows error message instead of 500)

---

## 3. Layout Structure

### 3.1 Master Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER BAR (purple/violet)                                            │
│ ┌─────────────┐                                    ┌────────────────┐│
│ │ 🔐 App Logo  │                                    │ AG53447  [PM]  ││
│ │ Protegrity   │                                    │ IT USER   ⏻   ││
│ │ Tokenizer    │                                    │                ││
│ └─────────────┘                                    └────────────────┘│
├────────┬─────────────────────────────────────────────────────────────┤
│ LEFT   │  MAIN CONTENT AREA                                          │
│ SIDEBAR│                                                              │
│ (icons)│  ┌─────────────────────────────────────────────────────────┐│
│        │  │ TAB BAR (sub-navigation within page)                    ││
│ ┌────┐ │  │ [Tab 1] | [Tab 2]                                      ││
│ │ 📁 │ │  └─────────────────────────────────────────────────────────┘│
│ │File/│ │                                                              │
│ │Tmpl │ │  ┌─────────────────────────────────────────────────────────┐│
│ │Mgmt │ │  │ FORM / CONTENT AREA                                    ││
│ └────┘ │  │                                                          ││
│        │  │ (Page-specific content: forms, tables, etc.)             ││
│ ┌────┐ │  │                                                          ││
│ │ 🔓 │ │  │                                                          ││
│ │De-  │ │  │                                                          ││
│ │token│ │  └─────────────────────────────────────────────────────────┘│
│ └────┘ │                                                              │
│        │  ┌─────────────────────────────────────────────────────────┐│
│ ┌────┐ │  │ BOTTOM SECTION (approval queue / status)                ││
│ │ ⚙️ │ │  │ Total Delimited / XL files for Approval: N    [+]      ││
│ │Admin│ │  └─────────────────────────────────────────────────────────┘│
│ └────┘ │                                                              │
│        │                                                              │
│ ┌────┐ │                                                              │
│ │ 📊 │ │                                                              │
│ │Audit│ │                                                              │
│ └────┘ │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

### 3.2 Left Sidebar Navigation Items

| Icon | Label | Permission Required | Route |
|------|-------|-------------------|-------|
| 📁 | File/Template Management | `browse`, `upload` | `/files/` |
| 🔓 | Detokenize | `detokenize` | `/detokenize/` |
| ⚙️ | Admin / Configurations | `manage_permissions` | `/admin/` |
| 📊 | Audit Log | `manage_permissions` | `/admin/audit` |
| 👁️ | Browse Files | `browse` | `/files/browse` |

Sidebar items are **permission-aware** — only shown if user's group has the required permission.

---

## 4. Page Designs

### 4.1 Login Page

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                        │
│                   ┌─────────────────────────────────┐                  │
│                   │  🔐 Protegrity Tokenizer         │                  │
│                   │     Data Protection Portal       │                  │
│                   │                                   │                  │
│                   │  Username:                        │                  │
│                   │  [________________________]       │                  │
│                   │                                   │                  │
│                   │  Password:                        │                  │
│                   │  [________________________]       │                  │
│                   │                                   │                  │
│                   │         [ Log In ]                │                  │
│                   │                                   │                  │
│                   │  ⚠️ {error message if any}        │                  │
│                   └─────────────────────────────────┘                  │
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 4.2 File Upload / Approvals Page (Main Upload)

**Route:** `/upload/`  
**Tabs:** `File Upload/Approvals` | `Template Edit & Download/Approvals`

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │  File Upload/Approvals  |  Template Edit & Download/Approvals│
│        │─────────────────────────────────────────────────────────────│
│        │                                                              │
│  📁    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│ File/  │  │Entity Type *│  │Entity Name *│  │  Domain *   │         │
│ Tmpl   │  │[Other/Reg ▼]│  │[MDT_Fixed ▼]│  │[  MDT    ▼] │         │
│ Mgmt   │  └─────────────┘  └─────────────┘  └─────────────┘         │
│ (active)│                                                             │
│        │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  🔓    │  │Interface *  │  │ LOB Type *  │  │Incumbent PBM│         │
│ Detoken│  │[Claim Hist▼]│  │[Medicaid ▼] │  │[  ESI    ▼] │         │
│        │  └─────────────┘  └─────────────┘  └─────────────┘         │
│  ⚙️    │                                                              │
│ Admin  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐    │
│        │  │Load File    │  │ File Type * │  │ Template Name *  │    │
│  📊    │  │Type *       │  │[Fixed Wid ▼]│  │[MDT_CLAIMHIST_ ▼]│    │
│ Audit  │  │[Initial  ▼] │  └─────────────┘  └──────────────────┘    │
│        │  └─────────────┘                                             │
│        │                                                              │
│        │  ┌───────────────┐                                           │
│        │  │ File Upload * │                                           │
│        │  │               │                                           │
│        │  │ [Upload File] │                                           │
│        │  └───────────────┘                                           │
│        │                                                              │
│        │                     ⊙ Preview    ⊙ Upload    ⊗ Cancel       │
│        │                                                              │
│        │─────────────────────────────────────────────────────────────│
│        │  Total Delimited / XL files for Approval :  1         [+]   │
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

### 4.2.1 Upload Form Fields (Metadata Dropdowns)

| Field | Type | Source | Purpose |
|-------|------|--------|---------|
| Entity Type * | Dropdown | Config | Categorize the file source (e.g., Other/Registered) |
| Entity Name * | Dropdown | Config | Name identifier for the entity |
| Domain * | Dropdown | Config | Business domain (e.g., MDT) |
| Interface * | Dropdown | Config | Data interface type (e.g., Claim History) |
| LOB Type * | Dropdown | Config | Line of Business (e.g., Medicaid) |
| Incumbent PBM * | Dropdown | Config | PBM identifier (e.g., ESI) |
| Load File Type * | Dropdown | Config | Load type (e.g., Initial, Delta) |
| File Type * | Dropdown | Config | Format (Fixed Width, Delimited, Excel) |
| Template Name * | Dropdown | Templates DB | Pre-configured Protegrity template |
| File Upload * | File input | User | The actual data file (max 2 GB) |

### 4.2.2 Action Buttons

| Button | Style | Behavior |
|--------|-------|----------|
| Preview | Outlined/ghost | Show first N rows of uploaded file before tokenizing |
| Upload | Primary (filled) | Trigger tokenization + upload to Volume |
| Cancel | Red/danger outline | Clear form and discard |

---

### 4.3 File Browse Page (Volume Browser)

**Route:** `/files/browse`

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │                                                              │
│        │  ┌──────────────────────────┐  ┌────────────────────────┐   │
│  📁    │  │ Root Volume Path *       │  │ Application Folder(s) *│   │
│  🔓    │  │[/Volumes/main/default  ▼]│  │[phi/gbd/prd/outbound ▼]│   │
│  ⚙️    │  └──────────────────────────┘  └────────────────────────┘   │
│  📊    │                                                              │
│        │                               [ 📁 Upload File ]  [ 🔍 Search ]│
│  👁️   │                                                              │
│(active)│  ─── phi > gbd > prd > outbound > dxu > cet_billing ───    │
│        │                                                              │
│        │  Total Records :  29                                    🔍   │
│        │                                                              │
│        │  ┌──────────────────────────────────────────────────────────┐│
│        │  │ NAME                    │ TYPE │ LAST MODIFIED (ET) │SIZE│ACT││
│        │  ├─────────────────────────┼──────┼────────────────────┼────┼───┤│
│        │  │ CLMWKLY_PRD_RX_HBSC_   │ TXT  │ Dec 15, 2025       │7.8K│•••││
│        │  │  251215043718.TXT       │      │ 04:37:30           │    │   ││
│        │  ├─────────────────────────┼──────┼────────────────────┼────┼───┤│
│        │  │ CLMWKLY_PRD_RX_HBSC_   │ TXT  │ Jun 16, 2025       │122M│•••││
│        │  │  250616043520.TXT       │      │ 04:35:41           │    │   ││
│        │  ├─────────────────────────┼──────┼────────────────────┼────┼───┤│
│        │  │ CLMWKLY_PRD_RX_HBSC_   │ TXT  │ Nov 7, 2024        │124M│•••││
│        │  │  241028090531.TXT       │      │ 00:42:46           │    │   ││
│        │  └──────────────────────────────────────────────────────────┘│
│        │                                                              │
│        │  ••• Actions menu (per row):                                 │
│        │  ┌────────────────┐                                          │
│        │  │ ⬇ Download     │                                          │
│        │  │ 👁 Preview     │                                          │
│        │  │ 🗑 Delete      │                                          │
│        │  │ 🔗 Share       │                                          │
│        │  │ 🔓 Detokenize  │                                          │
│        │  └────────────────┘                                          │
│        │  (items shown based on user permission)                      │
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

### 4.3.1 Browse Features

| Feature | Behavior |
|---------|----------|
| Root Volume Path | Dropdown selecting the UC Volume |
| Application Folder(s) | Dropdown/breadcrumb for subfolder navigation |
| Breadcrumb trail | Clickable path segments for folder navigation |
| Total Records | Count of files in current directory |
| Search (🔍) | Filter files by name |
| Upload File button | Quick upload from browse view |
| ••• Actions | Context menu per file (permission-filtered) |

---

### 4.4 Detokenize Page

**Route:** `/detokenize/`

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │  Detokenize                                                  │
│        │─────────────────────────────────────────────────────────────│
│        │                                                              │
│  📁    │  Select file to detokenize:                                  │
│  🔓    │  ┌──────────────────────────────────────────────────────┐   │
│(active)│  │ Volume Path: [/Volumes/main/default/tokenized ▼]     │   │
│  ⚙️    │  │ File:        [CLMWKLY_PRD_RX_HBSC_251215.TXT  ▼]    │   │
│  📊    │  └──────────────────────────────────────────────────────┘   │
│        │                                                              │
│        │  Protegrity Template:                                        │
│        │  ┌──────────────────────────────────────────────────────┐   │
│        │  │ Template Name: [MDT_CLAIMHISTORY_ESI_Version ▼]      │   │
│        │  │   — OR —                                              │   │
│        │  │ Upload Template: [Choose File]                        │   │
│        │  └──────────────────────────────────────────────────────┘   │
│        │                                                              │
│        │                     ⊙ Preview    ⊙ Detokenize & Download    │
│        │                                                              │
│        │  ⚠️ Note: Detokenized data is streamed for download only.   │
│        │     It is never stored on the server.                        │
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

---

### 4.5 Admin Dashboard (Home)

**Route:** `/admin/` or `/admin/dashboard`

The admin landing page is a **4-tile dashboard**. Each tile navigates to a dedicated sub-page. Only visible to users with `manage_permissions` permission.

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │  Admin Dashboard                                             │
│        │─────────────────────────────────────────────────────────────│
│        │                                                              │
│  📁    │  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│  🔓    │  │  🔑                      │  │  ⚡                      │   │
│  ⚙️    │  │  Permissions Management │  │  Manage Databricks Jobs │   │
│(active)│  │                          │  │                          │   │
│  📊    │  │  Manage group roles &   │  │  View & create jobs,    │   │
│        │  │  permission assignments │  │  monitor job runs        │   │
│        │  └─────────────────────────┘  └─────────────────────────┘   │
│        │                                                              │
│        │  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│        │  │  🛡️                      │  │  🖥️                      │   │
│        │  │  Setup ABAC Policies    │  │  Create Job Clusters    │   │
│        │  │                          │  │                          │   │
│        │  │  Row filters & column   │  │  Configure compute for  │   │
│        │  │  masks for UC tables    │  │  Databricks job runs     │   │
│        │  └─────────────────────────┘  └─────────────────────────┘   │
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

#### Admin Tiles

| Tile | Route | Token | Description |
|------|-------|-------|-------------|
| 🔑 Permissions Management | `/admin/permissions` | User | Permission matrix editor |
| ⚡ Manage Databricks Jobs | `/admin/jobs` | SP | Job list + expandable runs |
| 🛡️ Setup ABAC Policies | `/admin/abac-policies` | User | Row filter / column mask creation |
| 🖥️ Create Job Clusters | `/admin/clusters` | SP | Cluster creation form |

---

### 4.5.1 Manage Databricks Jobs

**Route:** `/admin/jobs`

Infinite-scroll job list with expandable run details. Job data fetched via **SP token** (no user scope available for Jobs API in Public Preview).

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │  ← Admin    Manage Databricks Jobs     [+ Create Job ↗]     │
│        │─────────────────────────────────────────────────────────────│
│        │  🔍 [_Search jobs by name_________]                          │
│        │                                                              │
│        │  ┌──────────────────────────────────────────────────────────┐│
│        │  │ ▶ ETL_Daily_Pipeline                                      ││
│        │  │   Job Id: #255283504811035              [🔗 View Job ↗]   ││
│        │  │   👤 arun.wagle   📅 Jun 20   ⏰ 0 8 * * ?               ││
│        │  └──────────────────────────────────────────────────────────┘│
│        │                                                              │
│        │  ┌──────────────────────────────────────────────────────────┐│
│        │  │ ▼ Weekly_Report_Generator       (expanded)                ││
│        │  │   Job Id: #255283504811036              [🔗 View Job ↗]   ││
│        │  │   👤 jane.smith   📅 Jun 18   ⏰ 0 9 * * MON             ││
│        │  │   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈  ││
│        │  │   ┌────────────────────────────────────────────────────┐  ││
│        │  │   │ SUCCESS │ 🕐 Jun 23, 09:00 │ ⏱ 4m 12s │ 🔗 View ↗│  ││
│        │  │   ├────────────────────────────────────────────────────┤  ││
│        │  │   │ SUCCESS │ 🕐 Jun 16, 09:00 │ ⏱ 3m 58s │ 🔗 View ↗│  ││
│        │  │   ├────────────────────────────────────────────────────┤  ││
│        │  │   │ FAILED  │ 🕐 Jun 09, 09:01 │ ⏱ 1m 02s │ 🔗 View ↗│  ││
│        │  │   └────────────────────────────────────────────────────┘  ││
│        │  └──────────────────────────────────────────────────────────┘│
│        │                                                              │
│        │  ⏳ Loading more...  (infinite scroll)                       │
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

#### Job List Features

| Feature | Behavior |
|---------|----------|
| Infinite scroll | 25 jobs/page, loads more on scroll |
| Search | Debounced 400ms name filter |
| Expand/collapse | Click job header → `▶` becomes `▼`, shows last 10 runs |
| Job ID | Displayed as `Job Id: #<id>` |
| View Job ↗ | Opens `https://{host}/#job/{id}` in new tab |
| View Run ↗ | Opens `run_page_url` (from API) in new tab |
| + Create Job ↗ | Opens workspace job creation page in new tab |
| Run state badges | Color-coded: green=SUCCESS, red=FAILED, yellow=RUNNING |
| Run duration | Human-friendly: `4m 12s`, `1h 3m` |

---

### 4.5.2 Admin Permissions Page

**Route:** `/admin/permissions`

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │  Permissions Management                                      │
│        │─────────────────────────────────────────────────────────────│
│        │                                                              │
│  📁    │  ┌──────────────────┬───────┬───────────┬────────┬────────┐ │
│  🔓    │  │ Permission       │ Admin │Data Stewrd│Analyst │ Viewer │ │
│  ⚙️    │  ├──────────────────┼───────┼───────────┼────────┼────────┤ │
│(active)│  │ Browse           │  [✓]  │   [✓]    │  [✓]   │  [✓]  │ │
│  📊    │  │ Upload           │  [✓]  │   [✓]    │  [✓]   │  [ ]  │ │
│        │  │ Download         │  [✓]  │   [✓]    │  [✓]   │  [ ]  │ │
│        │  │ Delete           │  [✓]  │   [✓]    │  [ ]   │  [ ]  │ │
│        │  │ Preview          │  [✓]  │   [✓]    │  [✓]   │  [✓]  │ │
│        │  │ Detokenize       │  [✓]  │   [✓]    │  [ ]   │  [ ]  │ │
│        │  │ Share            │  [✓]  │   [ ]    │  [ ]   │  [ ]  │ │
│        │  │ Manage Perms     │  [✓]  │   [ ]    │  [ ]   │  [ ]  │ │
│        │  └──────────────────┴───────┴───────────┴────────┴────────┘ │
│        │                                                              │
│        │  [ Save Changes ]                                            │
│        │                                                              │
│        │  ─── Add Group Mapping ─────────────────────────────────── │
│        │  Databricks Group: [________________▼]                       │
│        │  App Role:         [________________▼]                       │
│        │  [ Add Mapping ]                                             │
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

---

### 4.6 Audit Log Page

**Route:** `/admin/audit`

```
┌────────┬─────────────────────────────────────────────────────────────┐
│SIDEBAR │  Audit Log                                                   │
│        │─────────────────────────────────────────────────────────────│
│        │                                                              │
│  📁    │  Filters:                                                    │
│  🔓    │  User [______▼] Action [______▼] From [_____] To [_____]    │
│  ⚙️    │                                                [ 🔍 Search ] │
│  📊    │                                                              │
│(active)│  Total Records: 1,204                                        │
│        │  ┌───────────────┬──────────┬────────┬──────────┬──────────┐│
│        │  │ Timestamp     │ User     │ Action │ Resource │ Status   ││
│        │  ├───────────────┼──────────┼────────┼──────────┼──────────┤│
│        │  │ 10:30:15      │ john.doe │ upload │ cust.csv │ Success  ││
│        │  │ 10:28:02      │ jane.s   │ delete │ old.csv  │ Success  ││
│        │  │ 10:25:44      │ bob.j    │ detoken│ data.csv │ Denied   ││
│        │  └───────────────┴──────────┴────────┴──────────┴──────────┘│
│        │                                                              │
└────────┴─────────────────────────────────────────────────────────────┘
```

---

## 5. Color Scheme & CSS Design System

### 5.1 Color Palette (Matching Carelon/Elevance Purple Theme)

| Token | Color | Usage |
|-------|-------|-------|
| `--primary` | #6B2D8B | Header bar, sidebar active state, primary buttons |
| `--primary-dark` | #4A1D6B | Hover states, active nav item |
| `--primary-light` | #F3E8F9 | Selected tab background, hover rows |
| `--accent` | #00A88F | Upload/action buttons (teal/green) |
| `--danger` | #DC3545 | Cancel buttons, error messages |
| `--surface` | #FFFFFF | Cards, form backgrounds |
| `--background` | #F8F6FA | Page background (light lavender) |
| `--sidebar-bg` | #FFFFFF | Sidebar background |
| `--sidebar-active` | #6B2D8B | Active sidebar item text/icon |
| `--text` | #333333 | Body text |
| `--text-muted` | #6C757D | Secondary text, labels |
| `--border` | #E0D8E6 | Form borders, table borders |
| `--header-bg` | #6B2D8B | Header bar background (purple) |
| `--header-text` | #FFFFFF | Header text |

### 5.2 Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Header brand | System sans-serif | 16px | Bold |
| Sidebar labels | System sans-serif | 11px | Normal |
| Form labels | System sans-serif | 13px | 600 |
| Form inputs | System sans-serif | 14px | Normal |
| Table headers | System sans-serif | 13px | 600 |
| Table body | System sans-serif | 13px | Normal |
| Buttons | System sans-serif | 14px | 500 |

### 5.3 Component Classes

| Class | Description |
|-------|-------------|
| `.sidebar` | Left vertical navigation bar |
| `.sidebar-item` | Nav item with icon + label |
| `.sidebar-item.active` | Purple text/icon, left border indicator |
| `.header-bar` | Top purple branded header |
| `.tab-bar` | Horizontal tab navigation within page |
| `.tab-bar .active` | Underlined active tab |
| `.form-group` | Label + input container |
| `.form-select` | Styled dropdown select |
| `.btn-primary` | Purple filled button |
| `.btn-accent` | Teal/green filled button (Upload File) |
| `.btn-outline` | Ghost/outlined button (Preview) |
| `.btn-danger` | Red cancel button |
| `.data-table` | File listing table |
| `.data-table .actions` | ••• action menu trigger |
| `.breadcrumb` | Folder path breadcrumb |
| `.approval-bar` | Bottom status bar (file count + add button) |
| `.context-menu` | Dropdown menu from ••• actions |

---

## 6. Client-Side JavaScript Modules

### 6.1 `static/js/upload.js`

- Populate cascading dropdowns (Entity Type → Entity Name → Domain)
- Client-side file validation (extension, size < 2 GB)
- Preview button shows first N rows before upload
- Upload triggers tokenization pipeline via AJAX
- Progress indicator during processing

### 6.2 `static/js/browse.js`

- Load folder contents on Volume/folder selection change
- Breadcrumb navigation (click segment → navigate to that level)
- ••• action menu: show/hide context menu per row
- Confirmation modal on delete action
- Search/filter file list by name

### 6.3 `static/js/session.js`

- Inactivity detection (mousemove, keypress, click, scroll)
- Heartbeat POST to `/auth/heartbeat` (debounced)
- Warning modal at 45s idle
- Auto-redirect to login at 60s idle
- "Stay Logged In" button resets timer

### 6.4 `static/js/admin.js`

- Checkbox matrix interactions (grant/revoke permissions)
- AJAX save for permission changes
- ABAC policy form submission + SQL preview
- Cluster creation form handler

### 6.5 `static/js/admin_jobs.js`

- Infinite scroll job list (25/page, loads on scroll or window bottom)
- Debounced search (400ms) — filters by job name
- Expandable job cards: click header to toggle run list
- Lazy-load runs on first expand (`GET /admin/jobs/<id>/runs`)
- Run rows: state badge (color-coded), start time, duration
- View Job button → `https://{DATABRICKS_HOST}/#job/{id}` (new tab)
- View Run Details → `run_page_url` from API (new tab)
- Create Job button → `https://{DATABRICKS_HOST}/#job/create` (new tab)
- `window.DATABRICKS_HOST` injected from Flask config via template

---

## 7. Responsive Behavior

| Viewport | Behavior |
|----------|----------|
| Desktop (>1200px) | Full sidebar + content layout as shown |
| Tablet (768-1200px) | Collapsed sidebar (icons only, no labels) |
| Mobile (<768px) | Sidebar hidden, hamburger menu toggle |

---

## 8. Files Delivered by This Feature

```
templates/
├── layout.html                  # Master layout: header + sidebar + content area
├── login.html                   # Login page (no sidebar)
├── dashboard.html               # Welcome/landing page with nav cards (Admin → /admin/dashboard)
├── upload.html                  # Upload form with metadata dropdowns + tabs
├── browse.html                  # File browser with Volume selector + breadcrumb
├── preview.html                 # Data preview (modal or inline table)
├── detokenize.html              # Detokenize form + download
├── admin/
│   ├── dashboard.html           # 4-tile admin landing page
│   ├── permissions.html         # Permission matrix editor
│   ├── jobs.html                # Manage Jobs (infinite scroll + expandable runs)
│   ├── abac_policies.html       # ABAC row filter / column mask form
│   ├── clusters.html            # Cluster creation form
│   └── audit.html               # Audit log viewer
└── components/
    ├── sidebar.html             # Left navigation (included in layout)
    ├── tab_bar.html             # Reusable tab bar component
    ├── context_menu.html        # ••• action dropdown
    ├── confirm_modal.html       # Delete confirmation
    └── timeout_modal.html       # Session expiring warning

static/
├── css/
│   └── styles.css               # Full stylesheet (purple theme + admin tiles + run rows)
└── js/
    ├── upload.js                # Upload form + Volume picker modal
    ├── browse.js                # File browser + breadcrumb + actions
    ├── session.js               # Inactivity timer + heartbeat (disabled Phase 1)
    ├── admin.js                 # Permissions matrix + ABAC/cluster form handlers
    └── admin_jobs.js            # Infinite scroll jobs + expandable runs + View links
```

---

## 9. Accessibility (a11y)

- All form inputs have associated `<label>` elements
- Dropdown selects use native `<select>` for screen reader support
- Action menus are keyboard navigable (Enter to open, Escape to close)
- Color contrast meets WCAG 2.1 AA (purple on white passes)
- Focus indicators on all interactive elements
- Status messages use `role="alert"` for screen readers
