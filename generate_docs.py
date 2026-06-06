from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import ListFlowable, ListItem

OUTPUT = r"c:\Users\vaibh\OneDrive\Documents\AI_Powered_Platform\AI_Vibration_Platform_Documentation.pdf"

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    rightMargin=2*cm, leftMargin=2*cm,
    topMargin=2*cm, bottomMargin=2*cm,
    title="AI Vibration Intelligence Platform — Full Technical Documentation",
    author="Vaibhavi"
)

W = A4[0] - 4*cm  # usable width

# ─── Styles ──────────────────────────────────────────────────────────────────
base = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

COVER_TITLE   = S("CoverTitle",   fontName="Helvetica-Bold", fontSize=28, textColor=colors.HexColor("#1e40af"), alignment=TA_CENTER, spaceAfter=8)
COVER_SUB     = S("CoverSub",     fontName="Helvetica",      fontSize=14, textColor=colors.HexColor("#6b7280"), alignment=TA_CENTER, spaceAfter=6)
COVER_META    = S("CoverMeta",    fontName="Helvetica",      fontSize=11, textColor=colors.HexColor("#374151"), alignment=TA_CENTER, spaceAfter=4)

H1 = S("H1", fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=18, spaceAfter=8, borderPad=4,
        borderColor=colors.HexColor("#3b82f6"), borderWidth=0)
H2 = S("H2", fontName="Helvetica-Bold", fontSize=14, textColor=colors.HexColor("#1e40af"),
        spaceBefore=14, spaceAfter=6)
H3 = S("H3", fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#2563eb"),
        spaceBefore=10, spaceAfter=4)
H4 = S("H4", fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#374151"),
        spaceBefore=8, spaceAfter=3)

BODY  = S("Body",  fontName="Helvetica",      fontSize=10, textColor=colors.HexColor("#111827"), spaceAfter=4, leading=15)
BODYJ = S("BodyJ", fontName="Helvetica",      fontSize=10, textColor=colors.HexColor("#111827"), spaceAfter=4, leading=15, alignment=TA_JUSTIFY)
CODE  = S("Code",  fontName="Courier",        fontSize=9,  textColor=colors.HexColor("#1f2937"),
          backColor=colors.HexColor("#f3f4f6"), spaceAfter=3, leading=13,
          leftIndent=10, rightIndent=10, borderPad=6)
NOTE  = S("Note",  fontName="Helvetica-Oblique", fontSize=9, textColor=colors.HexColor("#6b7280"), spaceAfter=4, leading=13)
BULLET= S("Bullet",fontName="Helvetica",      fontSize=10, textColor=colors.HexColor("#111827"),
          leftIndent=18, spaceAfter=3, leading=14, bulletIndent=6)

def hr(): return HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb"), spaceAfter=8, spaceBefore=4)
def hr_blue(): return HRFlowable(width="100%", thickness=2, color=colors.HexColor("#3b82f6"), spaceAfter=10, spaceBefore=2)

def h1(t): return Paragraph(t, H1)
def h2(t): return Paragraph(t, H2)
def h3(t): return Paragraph(t, H3)
def h4(t): return Paragraph(t, H4)
def p(t):  return Paragraph(t, BODY)
def pj(t): return Paragraph(t, BODYJ)
def code(t): return Paragraph(t.replace("\n","<br/>").replace(" ","&nbsp;"), CODE)
def note(t): return Paragraph(f"<i>{t}</i>", NOTE)
def sp(n=6): return Spacer(1, n)
def bullet(t): return Paragraph(f"• {t}", BULLET)

def section_box(text):
    tbl = Table([[Paragraph(text, S("SB", fontName="Helvetica-Bold", fontSize=13,
                                    textColor=colors.white, alignment=TA_LEFT))]], colWidths=[W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#1e40af")),
        ("TOPPADDING",  (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return tbl

def info_table(rows, col_widths=None):
    if col_widths is None:
        col_widths = [W*0.35, W*0.65]
    data = []
    for label, val in rows:
        data.append([
            Paragraph(f"<b>{label}</b>", S("TL", fontName="Helvetica-Bold", fontSize=9,
                                            textColor=colors.HexColor("#374151"))),
            Paragraph(str(val), S("TV", fontName="Helvetica", fontSize=9,
                                   textColor=colors.HexColor("#111827")))
        ])
    tbl = Table(data, colWidths=col_widths, repeatRows=0)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (0,-1), colors.HexColor("#f8fafc")),
        ("BACKGROUND",   (1,0), (1,-1), colors.white),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#f9fafb"), colors.white]),
    ]))
    return tbl

def api_table(rows):
    header = [Paragraph(h, S("AH", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white))
              for h in ["Method", "Endpoint", "Description"]]
    data = [header]
    method_colors = {
        "GET":    colors.HexColor("#16a34a"),
        "POST":   colors.HexColor("#2563eb"),
        "PUT":    colors.HexColor("#d97706"),
        "PATCH":  colors.HexColor("#7c3aed"),
        "DELETE": colors.HexColor("#dc2626"),
    }
    for method, endpoint, desc in rows:
        mc = method_colors.get(method, colors.HexColor("#374151"))
        data.append([
            Paragraph(f"<b>{method}</b>", S(f"M{method}", fontName="Helvetica-Bold", fontSize=9, textColor=mc)),
            Paragraph(endpoint, S("EP", fontName="Courier", fontSize=8, textColor=colors.HexColor("#1f2937"))),
            Paragraph(desc, S("AD", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#374151"))),
        ])
    tbl = Table(data, colWidths=[W*0.12, W*0.42, W*0.46])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),  colors.HexColor("#1e40af")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.HexColor("#f0f4ff"), colors.white]),
        ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#d1d5db")),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING",  (0,0), (-1,-1), 7),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    return tbl

# ─── Build Story ─────────────────────────────────────────────────────────────
story = []

# ══════════════════════════════════════════════════════════════════════════════
# COVER PAGE
# ══════════════════════════════════════════════════════════════════════════════
story += [
    sp(60),
    Paragraph("AI Vibration Intelligence Platform", COVER_TITLE),
    Paragraph("Stage 1 — Equipment Master Data", COVER_SUB),
    sp(10),
    HRFlowable(width="60%", thickness=3, color=colors.HexColor("#3b82f6"), hAlign="CENTER", spaceAfter=16),
    Paragraph("Complete Technical Documentation", S("CT2", fontName="Helvetica-Bold", fontSize=16,
              textColor=colors.HexColor("#374151"), alignment=TA_CENTER, spaceAfter=6)),
    sp(30),
    Paragraph("Backend · Frontend · Database · APIs · Workflow", COVER_META),
    Paragraph("Architecture · File-by-File Breakdown · Connection Map", COVER_META),
    sp(60),
    HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb"), hAlign="CENTER", spaceAfter=10),
    Paragraph("Generated: June 2026 &nbsp;|&nbsp; Stack: FastAPI + React + PostgreSQL",
              S("CG", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#9ca3af"), alignment=TA_CENTER)),
    PageBreak(),
]

# ══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ══════════════════════════════════════════════════════════════════════════════
story += [h1("Table of Contents"), hr_blue()]
toc_items = [
    ("1.", "Project Overview & Architecture"),
    ("2.", "Technology Stack"),
    ("3.", "Backend — File-by-File Documentation"),
    ("   3.1", "app/main.py"),
    ("   3.2", "app/config.py"),
    ("   3.3", "app/database.py"),
    ("   3.4", "app/models/equipment.py"),
    ("   3.5", "app/models/sensor.py"),
    ("   3.6", "app/schemas/equipment.py"),
    ("   3.7", "app/crud/equipment.py"),
    ("   3.8", "app/routers/equipment.py"),
    ("   3.9", "app/routers/lookups.py"),
    ("   3.10","alembic/ — Database Migrations"),
    ("4.", "Frontend — File-by-File Documentation"),
    ("   4.1", "src/main.tsx & index.html"),
    ("   4.2", "src/App.tsx"),
    ("   4.3", "src/api/client.ts"),
    ("   4.4", "src/api/equipment.ts"),
    ("   4.5", "src/types/equipment.ts"),
    ("   4.6", "src/pages/Dashboard.tsx"),
    ("   4.7", "src/pages/EquipmentMaster.tsx"),
    ("   4.8", "src/components/equipment/EquipmentForm.tsx"),
    ("   4.9", "src/components/equipment/tabs/ (all 6 tabs)"),
    ("   4.10","src/components/equipment/SensorMountingDiagram.tsx"),
    ("   4.11","src/components/ui/ (FormField, MultiSelect, SectionCard, Toast)"),
    ("   4.12","src/lib/utils.ts"),
    ("5.", "Database — Schema & Design"),
    ("6.", "API Reference — All Endpoints"),
    ("7.", "Frontend ↔ Backend Connection Map"),
    ("8.", "Dashboard Image — What You See & Why"),
    ("9.", "AI Readiness Score — Calculation & Logic"),
    ("10.","Full Request/Response Workflow"),
    ("11.","Deployment & Infrastructure"),
]
toc_data = [[Paragraph(n, S("TN", fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor("#1e40af"))),
             Paragraph(t, S("TT", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#111827")))]
            for n, t in toc_items]
toc_tbl = Table(toc_data, colWidths=[W*0.12, W*0.88])
toc_tbl.setStyle(TableStyle([
    ("TOPPADDING", (0,0),(-1,-1), 3), ("BOTTOMPADDING",(0,0),(-1,-1), 3),
    ("LINEBELOW", (0,0),(-1,-1), 0.3, colors.HexColor("#f3f4f6")),
    ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story += [toc_tbl, PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PROJECT OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("1. Project Overview & Architecture"), sp(8)]
story += [pj("""
The <b>AI Vibration Intelligence Platform</b> is an industrial IoT / predictive maintenance web application.
Stage 1, documented here, is the <b>Equipment Master Data</b> module — a system that allows engineers
to register every rotating machine in a plant with full metadata: location hierarchy, mechanical specs,
rotating component parameters, operating conditions, sensor configurations, and AI readiness flags.
This rich metadata becomes the foundation for future stages (real-time vibration data ingestion,
AI-based fault detection, alarm management, and predictive maintenance scheduling).
""")]
story += [sp(6)]

arch_rows = [
    ["Layer", "Technology", "Purpose"],
    ["Frontend", "React 18 + TypeScript + Vite", "Browser SPA — 2 pages, 6-tab form, equipment list"],
    ["API Layer", "FastAPI (Python 3.11)", "RESTful JSON API, image upload, validation, CORS"],
    ["ORM", "SQLAlchemy 2.0 + Alembic", "Database models, queries, schema migrations"],
    ["Database", "PostgreSQL 16 (Docker)", "Persistent storage of all equipment & sensor data"],
    ["State Mgmt", "TanStack React Query v5", "Server state, caching, background refetch"],
    ["Forms", "React Hook Form + Zod", "Multi-tab form state, schema validation"],
    ["Styling", "Tailwind CSS 3.4", "Utility-first responsive CSS"],
]
arch_tbl = Table(
    [[Paragraph(c, S(f"AH{i}", fontName="Helvetica-Bold" if i==0 else "Helvetica", fontSize=9,
                     textColor=colors.white if i==0 else colors.HexColor("#111827"))) for c in row]
     for i, row in enumerate(arch_rows)],
    colWidths=[W*0.18, W*0.35, W*0.47]
)
arch_tbl.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e3a8a")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#eff6ff"), colors.white]),
    ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#dbeafe")),
    ("TOPPADDING",   (0,0), (-1,-1), 6), ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ("LEFTPADDING",  (0,0), (-1,-1), 8), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
]))
story += [arch_tbl, sp(10)]

story += [h2("Architecture Flow")]
story += [pj("""
<b>Browser → Vite Dev Server (port 5173)</b><br/>
The React SPA runs in the browser. All API calls are made via Axios to the FastAPI backend.
<br/><br/>
<b>FastAPI Backend (port 8000)</b><br/>
Receives HTTP requests, validates them through Pydantic schemas, executes CRUD operations
via SQLAlchemy, and returns JSON responses. Image uploads are stored on disk in <i>backend/uploads/</i>.
<br/><br/>
<b>PostgreSQL Database (port 5433 on host, 5432 in container)</b><br/>
Docker container running PostgreSQL 16. SQLAlchemy connects via connection string in <i>.env</i>.
Two tables: <b>equipment_masters</b> and <b>sensor_configurations</b>.
""")]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TECH STACK
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("2. Technology Stack"), sp(8)]

story += [h2("Backend Dependencies (requirements.txt)")]
story += [info_table([
    ("fastapi==0.115.0", "Web framework — routing, dependency injection, OpenAPI docs auto-generation"),
    ("uvicorn[standard]", "ASGI server that runs FastAPI — handles HTTP/WebSocket connections"),
    ("sqlalchemy==2.0.35", "ORM — maps Python classes to PostgreSQL tables, handles all queries"),
    ("alembic==1.13.3", "Database migration tool — version-controls schema changes"),
    ("psycopg2-binary", "PostgreSQL driver — the actual connection adapter between SQLAlchemy and Postgres"),
    ("python-multipart", "Required for FastAPI to handle multipart/form-data (file uploads)"),
    ("pydantic==2.9.2", "Data validation and serialization — defines request/response schemas"),
    ("pydantic-settings", "Loads config from .env file into Settings class"),
    ("pillow==10.4.0", "Image processing library (imported, used for potential future image ops)"),
    ("aiofiles==24.1.0", "Async file I/O (available for async image handling)"),
])]
story += [sp(8)]

story += [h2("Frontend Dependencies (package.json)")]
story += [info_table([
    ("react@18.3.1", "UI library — component tree, virtual DOM, hooks"),
    ("react-router-dom@6.27", "Client-side routing — /  /equipment/new  /equipment/:id/edit"),
    ("@tanstack/react-query@5", "Server state management — fetching, caching, background sync"),
    ("react-hook-form@7.53", "Form state management — tracks field values, errors, dirty state"),
    ("zod@3.23", "TypeScript-first schema validation — validates form data before API call"),
    ("@hookform/resolvers", "Bridge between Zod schema and React Hook Form"),
    ("axios@1.7.7", "HTTP client — makes all API calls to FastAPI backend"),
    ("tailwindcss@3.4", "Utility CSS framework — all styling done via class names"),
    ("lucide-react@0.454", "Icon library — all icons in the UI (Cpu, Trash2, Edit2, etc.)"),
    ("@radix-ui/*", "Accessible headless UI primitives — Dialog, Select, Toast, Popover"),
    ("vite@5.4", "Build tool and dev server — instant HMR, fast TypeScript bundling"),
    ("typescript@5.6", "Type safety across all frontend files"),
], col_widths=[W*0.30, W*0.70])]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — BACKEND FILES
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("3. Backend — File-by-File Documentation"), sp(8)]

# 3.1 main.py
story += [h2("3.1  backend/app/main.py"), hr()]
story += [pj("""
<b>Role:</b> The application entry point. This file creates the FastAPI app instance, registers all
middleware, mounts routers, and sets up the static file directory for uploaded images.
""")]
story += [info_table([
    ("FastAPI()", "Creates the ASGI application with title, description, and version metadata. These appear in auto-generated /docs (Swagger UI)"),
    ("CORSMiddleware", "Allows the React frontend (http://localhost:5173) to make cross-origin requests. Without this, browsers would block all API calls"),
    ("app.include_router()", "Registers the equipment router (prefix: /api/v1/equipment) and lookups router (prefix: /api/v1/lookups)"),
    ("UPLOAD_DIR", "Reads UPLOAD_DIR from environment variable (defaults to 'uploads'). Creates the directory if it doesn't exist"),
    ("GET /health", "Health check endpoint — returns {status: ok}. Used to verify the backend is running"),
])]
story += [sp(6)]

# 3.2 config.py
story += [h2("3.2  backend/app/config.py"), hr()]
story += [pj("""
<b>Role:</b> Centralized configuration management using <b>pydantic-settings</b>.
Reads all environment variables from the <i>.env</i> file and exposes them as a typed
<code>settings</code> singleton used throughout the application.
""")]
story += [info_table([
    ("database_url", "PostgreSQL connection string, e.g. postgresql://user:pass@localhost:5433/dbname"),
    ("secret_key", "Application secret (currently unused — reserved for JWT authentication in future stages)"),
    ("upload_dir", "Directory path where equipment images are stored (default: 'uploads')"),
    ("max_image_size_mb", "Maximum allowed image upload size in MB (default: 10)"),
    ("class Config", "Tells pydantic-settings to load from .env file and ignore extra keys"),
])]
story += [sp(6)]

# 3.3 database.py
story += [h2("3.3  backend/app/database.py"), hr()]
story += [pj("""
<b>Role:</b> Sets up the SQLAlchemy database engine, session factory, and base class for all ORM models.
Also provides the <b>get_db()</b> dependency injected into every API endpoint.
""")]
story += [info_table([
    ("create_engine()", "Creates the SQLAlchemy engine with the PostgreSQL connection string. pool_pre_ping=True tests the connection before use to handle dropped connections"),
    ("SessionLocal", "Session factory — each call creates a new database session (transaction). autocommit=False means changes must be committed explicitly"),
    ("Base", "declarative_base() — the parent class all ORM model classes inherit from. SQLAlchemy uses it to track the table registry"),
    ("get_db()", "FastAPI dependency function. Yields a database session and ensures it's closed after the request completes (even on error). Every router endpoint that needs DB access uses Depends(get_db)"),
])]
story += [sp(6)]

# 3.4 models/equipment.py
story += [h2("3.4  backend/app/models/equipment.py"), hr()]
story += [pj("""
<b>Role:</b> Defines the <b>Equipment</b> ORM model — the Python class that maps to the
<b>equipment_masters</b> PostgreSQL table. Every column in the database is declared here.
""")]
story += [info_table([
    ("id (UUID)", "Primary key — auto-generated UUID4. Stored as PostgreSQL native UUID type"),
    ("plant_name / area / line", "Three-level location hierarchy. All required (NOT NULL). Organises machines by factory → zone → production line"),
    ("machine_name", "Human-readable name (e.g. 'Cooling Water Pump P-204'). Required"),
    ("machine_id", "Unique asset code (e.g. 'PUMP-P204'). Has UNIQUE constraint + index for fast lookup"),
    ("machine_type", "Category: Motor, Pump, Fan, Blower, Compressor, Gearbox, Turbine, Generator, etc."),
    ("machine_criticality", "Four-tier: Low / Medium / High / Critical"),
    ("rated_power_kw", "Numeric(10,2) — e.g. 75.50 kW"),
    ("rated_rpm", "Integer — nameplate speed, e.g. 1480"),
    ("bearing_number_de / nde", "Drive End and Non-Drive End bearing catalogue numbers — used for fault frequency calculations"),
    ("operating_speed_min/max", "Actual operating speed range. Used in AI readiness check"),
    ("operating_environment", "PostgreSQL ARRAY(String) — multi-value field, e.g. ['Dusty', 'High Temperature']"),
    ("equipment_image_path", "Relative file path to the uploaded image, e.g. 'uploads/uuid.png'"),
    ("machine_train_configured", "Boolean AI readiness flag — has the machine chain been defined?"),
    ("bearing_database_mapped", "Boolean AI readiness flag — have bearing numbers been entered?"),
    ("operating_mode_configured", "Boolean AI readiness flag — have speed and load ranges been set?"),
    ("asset_status", "Current state: Active / Inactive / Under Maintenance / Decommissioned"),
    ("created_at / updated_at", "Auto-managed timestamps. updated_at uses onupdate=datetime.utcnow"),
    ("sensors (relationship)", "SQLAlchemy ORM relationship to SensorConfiguration. cascade='all, delete-orphan' means deleting equipment auto-deletes its sensors"),
])]
story += [sp(6)]

# 3.5 models/sensor.py
story += [h2("3.5  backend/app/models/sensor.py"), hr()]
story += [pj("""
<b>Role:</b> Defines the <b>SensorConfiguration</b> ORM model — maps to the
<b>sensor_configurations</b> table. Each sensor belongs to one piece of equipment (many-to-one).
""")]
story += [info_table([
    ("id", "UUID primary key, auto-generated"),
    ("equipment_id", "Foreign key → equipment_masters.id with ondelete=CASCADE"),
    ("sensor_type", "Category: IEPE Accelerometer, Velocity Sensor, Temperature, etc."),
    ("mounting_location", "Where physically mounted: Bearing Housing DE/NDE, Motor DE/NDE, Gearbox, etc."),
    ("orientation", "Measurement direction: Horizontal / Vertical / Axial / Radial / Tangential"),
    ("mounting_method", "How attached: Stud Mounted, Magnetic Base, Adhesive, etc."),
    ("sensitivity", "Numeric(10,4) — sensor output per unit, e.g. 100.0 mV/g"),
    ("sensitivity_unit", "Unit: mV/g, mV/mm/s, mV/µm, mA, V"),
    ("sampling_rate", "Pre-set string (e.g. '4096 Hz') or 'Custom'"),
    ("sampling_rate_custom", "Integer Hz value when sampling_rate = 'Custom'"),
    ("frequency_range", "Pre-set string (e.g. '0-5000 Hz') or 'Custom'"),
    ("frequency_range_custom_min/max", "Integer bounds when frequency_range = 'Custom'"),
    ("is_active", "Boolean — can deactivate a sensor without deleting it"),
])]
story += [sp(6)]

# 3.6 schemas/equipment.py
story += [h2("3.6  backend/app/schemas/equipment.py"), hr()]
story += [pj("""
<b>Role:</b> Pydantic schemas define the shape of data coming <b>into</b> and going <b>out of</b>
the API. They perform automatic validation — FastAPI rejects invalid requests with a 422 error
before they reach the CRUD layer. There are separate schemas for Create, Update, and Output.
""")]
story += [info_table([
    ("SensorConfigBase", "Shared fields for all sensor schemas. Defines defaults and optional fields"),
    ("SensorConfigCreate", "Inherits SensorConfigBase — used when POST /sensors is called"),
    ("SensorConfigUpdate", "All fields Optional — allows partial updates via PUT"),
    ("SensorConfigOut", "Adds id, equipment_id, created_at. from_attributes=True lets it read from ORM objects"),
    ("EquipmentBase", "All equipment fields with defaults. Shared by Create and Out schemas"),
    ("EquipmentCreate", "Extends EquipmentBase, adds sensors: List[SensorConfigCreate]"),
    ("EquipmentUpdate", "All fields Optional — enables PATCH semantics (only send changed fields)"),
    ("EquipmentOut", "Full equipment response including id, image path, sensor list, timestamps"),
    ("EquipmentListItem", "Lightweight schema for the dashboard list — omits heavy fields like bearing_details, maintenance_notes"),
    ("AIReadinessOut", "Response for /ai-readiness endpoint: score_percent + 5 boolean checks"),
    ("PaginatedEquipment", "Wraps list response: total, page, page_size, items[]"),
])]
story += [sp(6)]

# 3.7 crud/equipment.py
story += [h2("3.7  backend/app/crud/equipment.py"), hr()]
story += [pj("""
<b>Role:</b> The data access layer. All database operations are here — completely separated
from routing logic. Each function receives a SQLAlchemy Session and returns ORM objects or primitives.
""")]
story += [info_table([
    ("get_equipment_list()", "Queries with optional filters (plant_name ilike, machine_type ==, criticality ==). Applies ORDER BY created_at DESC, then LIMIT/OFFSET pagination"),
    ("get_equipment_by_id()", "Simple SELECT WHERE id = ? — returns None if not found"),
    ("get_equipment_by_machine_id()", "Used to check for duplicate machine IDs before creating"),
    ("create_equipment()", "Extracts sensors from payload, creates Equipment first (db.flush() to get the id), then creates each SensorConfiguration with the new equipment_id. Commits atomically"),
    ("update_equipment()", "Loads equipment, iterates model_dump(exclude_unset=True) so only provided fields are changed, commits"),
    ("delete_equipment()", "Loads and deletes — cascade handles sensors automatically"),
    ("update_image_path()", "Sets equipment_image_path to file path string (or None to remove)"),
    ("get_sensors_by_equipment()", "Returns all sensors WHERE equipment_id = ?"),
    ("create_sensor() / update_sensor() / delete_sensor()", "Sensor-level CRUD — same pattern as equipment"),
    ("compute_ai_readiness()", "Pure function — no DB call. Takes an equipment ORM object and evaluates 5 boolean checks (see Section 9 for full logic)"),
])]
story += [sp(6)]

# 3.8 routers/equipment.py
story += [h2("3.8  backend/app/routers/equipment.py"), hr()]
story += [pj("""
<b>Role:</b> Defines all HTTP endpoints under <code>/api/v1/equipment</code>.
Each endpoint validates the request using Pydantic schemas, calls the appropriate CRUD function,
and returns a typed response. FastAPI handles serialization automatically.
""")]
story += [api_table([
    ("POST",   "/api/v1/equipment/",                       "Create new equipment. Checks for duplicate machine_id first (409 if exists). Returns full EquipmentOut"),
    ("GET",    "/api/v1/equipment/",                       "List all equipment with pagination (page, page_size) and optional filters (plant_name, machine_type, machine_criticality)"),
    ("GET",    "/api/v1/equipment/{id}",                   "Get single equipment by UUID. Returns full EquipmentOut with sensors"),
    ("PUT",    "/api/v1/equipment/{id}",                   "Full update — replaces all provided fields"),
    ("PATCH",  "/api/v1/equipment/{id}",                   "Partial update — only updates fields present in request body"),
    ("DELETE", "/api/v1/equipment/{id}",                   "Delete equipment and all its sensors (cascade). Returns 204 No Content"),
    ("POST",   "/api/v1/equipment/{id}/image",             "Upload equipment image. Validates MIME type (JPEG/PNG/WebP/GIF) and file size (≤10MB). Saves to uploads/{id}.ext"),
    ("GET",    "/api/v1/equipment/{id}/image",             "Serve uploaded image as FileResponse (direct binary download)"),
    ("DELETE", "/api/v1/equipment/{id}/image",             "Remove image file from disk and clear path in database"),
    ("GET",    "/api/v1/equipment/{id}/sensors",           "List all sensors for an equipment"),
    ("POST",   "/api/v1/equipment/{id}/sensors",           "Add a new sensor to an equipment"),
    ("PUT",    "/api/v1/equipment/{id}/sensors/{sid}",     "Update a specific sensor"),
    ("DELETE", "/api/v1/equipment/{id}/sensors/{sid}",     "Remove a sensor"),
    ("GET",    "/api/v1/equipment/{id}/ai-readiness",      "Calculate and return AI readiness score (0-100%) with breakdown"),
])]
story += [sp(6)]

# 3.9 routers/lookups.py
story += [h2("3.9  backend/app/routers/lookups.py"), hr()]
story += [pj("""
<b>Role:</b> Provides static reference data (dropdown values) to the frontend.
Instead of hard-coding lists in both frontend and backend, they live here and the
frontend could fetch them dynamically. Currently the frontend uses local constants
for speed, but the API is available for future dynamic use.
""")]
story += [info_table([
    ("GET /api/v1/lookups/", "Returns all lookup categories as a single JSON object"),
    ("GET /api/v1/lookups/{name}", "Returns values for one category (e.g. /lookups/machine-types)"),
    ("Available lookups", "machine-types (13 types), machine-criticality, drive-types, load-types, foundation-types, coupling-types, motor-pole-counts, direction-of-rotation, operating-environments (13 values), lubrication-types, sensor-types (14 types), mounting-locations (11), sensor-orientations, mounting-methods (9), sensitivity-units, sampling-rates (9 presets + Custom), frequency-ranges (6 presets + Custom), asset-status"),
])]
story += [sp(6)]

# 3.10 alembic
story += [h2("3.10  alembic/ — Database Migrations"), hr()]
story += [pj("""
<b>Role:</b> Alembic manages database schema versioning — like git for the database.
Instead of manually running SQL, developers write migration scripts that Alembic applies in order.
""")]
story += [info_table([
    ("alembic.ini", "Configuration: tells Alembic where to find migration scripts and how to connect (reads from .env)"),
    ("alembic/env.py", "Migration environment — imports all models so Alembic can auto-detect schema changes"),
    ("alembic/script.py.mako", "Template used when generating new migration files"),
    ("versions/001_initial_schema.py", "First (and currently only) migration. Creates both tables with all columns, indexes, unique constraints, and foreign keys"),
    ("upgrade()", "Creates equipment_masters and sensor_configurations tables. Adds UNIQUE on machine_id. Adds indexes on plant_name and machine_type"),
    ("downgrade()", "Drops both tables (in reverse order to respect foreign key constraint)"),
    ("Command to run", "cd backend && alembic upgrade head"),
])]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — FRONTEND FILES
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("4. Frontend — File-by-File Documentation"), sp(8)]

# 4.1 main.tsx
story += [h2("4.1  src/main.tsx & index.html"), hr()]
story += [pj("""
<b>index.html</b> is the single HTML file Vite serves. It has a <code>&lt;div id="root"&gt;</code>
and a script tag loading <code>/src/main.tsx</code>.
<br/><br/>
<b>main.tsx</b> is the JavaScript entry point. It mounts the React tree into the DOM.
""")]
story += [info_table([
    ("ReactDOM.createRoot()", "Creates a React 18 concurrent root at #root div"),
    ("QueryClientProvider", "Provides TanStack React Query's query client to the entire app — enables all useQuery/useMutation hooks"),
    ("BrowserRouter", "Enables HTML5 history-based routing (React Router v6)"),
    ("App", "The root component, which contains all routes"),
])]
story += [sp(6)]

# 4.2 App.tsx
story += [h2("4.2  src/App.tsx"), hr()]
story += [pj("""
<b>Role:</b> The root React component. Defines the route tree and wraps everything in the
<b>ToastProvider</b> context (so toast notifications work anywhere in the app).
""")]
story += [info_table([
    ("/ → Dashboard", "The equipment list page (default route)"),
    ("/equipment/new → NewEquipmentPage", "The empty 6-tab form for adding a new machine"),
    ("/equipment/:id/edit → EditEquipmentPage", "The pre-filled 6-tab form for editing an existing machine"),
    ("* → Navigate('/')", "Any unknown URL redirects to the dashboard"),
    ("ToastProvider", "Wraps all routes so any component can call showToast() to display notifications"),
])]
story += [sp(6)]

# 4.3 api/client.ts
story += [h2("4.3  src/api/client.ts"), hr()]
story += [pj("""
<b>Role:</b> Creates and exports a pre-configured Axios instance as the single HTTP client
used by all API functions. This is the bridge between React and FastAPI.
""")]
story += [info_table([
    ("baseURL", "Reads from VITE_API_BASE_URL environment variable. Falls back to http://localhost:8000"),
    ("Content-Type header", "Sets 'application/json' as default. Overridden to 'multipart/form-data' for image uploads"),
    ("Why a shared instance?", "All API calls share the same base URL and headers. Adding auth tokens later only requires changing this one file"),
])]
story += [sp(6)]

# 4.4 api/equipment.ts
story += [h2("4.4  src/api/equipment.ts"), hr()]
story += [pj("""
<b>Role:</b> Contains every API call function used by the frontend. Each function maps to one
backend endpoint. These functions are called from React hooks (useQuery, useMutation).
""")]
story += [info_table([
    ("createEquipment(data)", "POST /api/v1/equipment/ — sends full form data, receives EquipmentOut"),
    ("updateEquipment(id, data)", "PATCH /api/v1/equipment/{id} — sends partial data"),
    ("getEquipment(id)", "GET /api/v1/equipment/{id} — fetches single equipment for edit form"),
    ("listEquipment(params)", "GET /api/v1/equipment/ — paginated list with optional filters"),
    ("deleteEquipment(id)", "DELETE /api/v1/equipment/{id}"),
    ("uploadEquipmentImage(id, file)", "POST /api/v1/equipment/{id}/image — builds FormData, sends as multipart"),
    ("addSensor / updateSensor / deleteSensor", "Sensor CRUD — POST/PUT/DELETE on /sensors sub-resource"),
    ("getAIReadiness(id)", "GET /api/v1/equipment/{id}/ai-readiness"),
    ("getLookup(name)", "GET /api/v1/lookups/{name} — fetches one dropdown list"),
    ("getAllLookups()", "GET /api/v1/lookups/ — fetches all dropdown data at once"),
])]
story += [sp(6)]

# 4.5 types/equipment.ts
story += [h2("4.5  src/types/equipment.ts"), hr()]
story += [pj("""
<b>Role:</b> The type system for the entire frontend. Defines Zod validation schemas
(which also generate TypeScript types via inference), interface definitions for API responses,
and UI constants like criticality color maps.
""")]
story += [info_table([
    ("sensorSchema (Zod)", "Validates a single sensor entry. Required: sensor_type, mounting_location, orientation. All others optional with type coercion (z.coerce.number())"),
    ("equipmentSchema (Zod)", "Full equipment form schema. All fields are optional at the schema level (backend handles required), but Zod coerces number strings to numbers"),
    ("EquipmentFormData (type)", "TypeScript type inferred from equipmentSchema — used everywhere in form components"),
    ("EquipmentListItem", "Interface for dashboard table rows — lightweight, no sensor data"),
    ("EquipmentOut", "Full API response type extending EquipmentFormData with id, image path, timestamps"),
    ("AIReadiness", "Interface for readiness score response: score_percent + 5 booleans"),
    ("PaginatedEquipment", "Wraps list response with pagination metadata"),
    ("CRITICALITY_COLORS", "Maps 'Low'→green, 'Medium'→yellow, 'High'→red, 'Critical'→purple CSS classes for badges"),
    ("CRITICALITY_DOT", "Maps criticality to dot color classes for the colored bullet in list"),
])]
story += [sp(6)]

# 4.6 Dashboard.tsx
story += [h2("4.6  src/pages/Dashboard.tsx"), hr()]
story += [pj("""
<b>Role:</b> The main landing page. Shows the equipment inventory as a searchable,
filterable, paginated table with summary statistics at the top.
""")]
story += [info_table([
    ("useQuery(['equipment', ...])", "Fetches equipment list from GET /api/v1/equipment/. Re-fetches when page, filterType, or filterCriticality change"),
    ("Stats Bar (4 cards)", "Counts: Total (data.total), Critical (filter items), High (filter items), Active (filter items). Rendered from a map over a config array"),
    ("Search box", "Client-side filter — searches machine_name, machine_id, plant_name in the already-loaded page of results"),
    ("Type / Criticality dropdowns", "Server-side filters — changing them triggers a new API call with updated query params"),
    ("Equipment Table", "7 columns: Machine (icon + name + manufacturer), ID (monospace badge), Type, Plant/Area, Criticality (colored badge), Status (colored pill), Actions (edit/delete icons)"),
    ("Delete flow", "Calls window.confirm(), then deleteEquipment() via useMutation. On success, invalidates ['equipment'] query to refresh the list"),
    ("Edit button", "Navigates to /equipment/{id}/edit"),
    ("Pagination", "Previous/Next buttons. Only shown when total > 20. Page state is local React state"),
    ("Loading/Error states", "Spinner while loading, red error message if backend unreachable"),
])]
story += [sp(6)]

# 4.7 EquipmentMaster.tsx
story += [h2("4.7  src/pages/EquipmentMaster.tsx"), hr()]
story += [pj("""
<b>Role:</b> Two exported page components — <b>NewEquipmentPage</b> and <b>EditEquipmentPage</b>.
New just renders the form with no data. Edit fetches the equipment first, transforms
date strings, then passes the data as <code>initialData</code> to the form.
""")]
story += [info_table([
    ("NewEquipmentPage", "Renders <EquipmentForm /> with no props. Form starts empty with default values"),
    ("EditEquipmentPage", "Reads :id from URL params. Calls GET /api/v1/equipment/{id} via useQuery. Shows spinner while loading"),
    ("Date transformation", "API returns ISO datetime strings — splits on 'T' to extract date-only (YYYY-MM-DD) for the HTML date inputs"),
    ("initialData prop", "Spreads API response + overrides sensors/operating_environment arrays. Passes editId so form knows to call PATCH instead of POST"),
])]
story += [sp(6)]

# 4.8 EquipmentForm.tsx
story += [h2("4.8  src/components/equipment/EquipmentForm.tsx"), hr()]
story += [pj("""
<b>Role:</b> The master form container. Manages the 6-tab navigation, the form context,
and the final submission logic. All tab components are children rendered here.
""")]
story += [info_table([
    ("useForm + zodResolver", "Creates the form with Zod validation. mode='onChange' validates as user types"),
    ("FormProvider", "Wraps all tabs — lets each tab component call useFormContext() to access form state without prop drilling"),
    ("TABS array", "Defines 6 tabs with id, label, icon. Controls navigation rendering"),
    ("completedTabs state", "Tracks which tabs have been visited. Completed tabs show a blue checkmark badge"),
    ("pendingImage state", "Stores the selected File object. Image is uploaded AFTER equipment is created (to get the equipment id first)"),
    ("goToTab()", "Updates completedTabs when moving forward, updates activeTab"),
    ("onSubmit()", "1) Calls createEquipment() or updateEquipment(). 2) If pendingImage exists, calls uploadEquipmentImage() with the returned equipment.id. 3) Shows toast. 4) Navigates to / after 1.2s"),
    ("Tab rendering", "Uses conditional rendering (activeTab === N) — only one tab is in the DOM at a time"),
    ("Footer navigation", "Back/Next buttons + progress dots. Tab 6 shows 'Save & Finish' submit button instead of Next"),
])]
story += [sp(6)]

# 4.9 Tabs
story += [h2("4.9  src/components/equipment/tabs/ — All 6 Tabs"), hr()]

story += [h3("Tab 1: BasicDetailsTab.tsx")]
story += [pj("""
Three-column grid layout. Column 1: Location Hierarchy (plant, area, line).
Column 2: Machine Identification (name, ID, type, criticality).
Column 3: Manufacturer & Model + Equipment Image upload.
<br/><br/>
<b>Image upload logic:</b> Uses a hidden <code>&lt;input type="file"&gt;</code> with a ref.
When a file is selected, it calls URL.createObjectURL() for instant preview.
The actual File object is passed up to EquipmentForm via <code>onImageSelect</code> prop.
Upload to backend happens only after the equipment record is saved (to have an ID).
""")]

story += [h3("Tab 2: MechanicalDetailsTab.tsx")]
story += [pj("""
Single section card with a 4-column grid.
Fields: Rated Power (kW), Rated RPM, Drive Type (dropdown), Load Type (dropdown),
Foundation Type (dropdown), Coupling Details (dropdown).
All dropdowns use Controller + SelectInput for consistent styling.
""")]

story += [h3("Tab 3: RotatingComponentsTab.tsx")]
story += [pj("""
Two section cards: Bearing Details and Rotating Component Specifications.
<br/><br/>
<b>Conditional field rendering</b> — watches machine_type and drive_type:
<br/>• Motor / Generator / DG Set → shows Motor Pole Count
<br/>• Fan / Blower → shows Number of Fan Blades
<br/>• Pump → shows Number of Pump Vanes
<br/>• Gearbox machine type OR Gear Drive → shows Gearbox Ratio + Gear Teeth
<br/>• Otherwise → shows an info message explaining the fields appear based on selection
""")]

story += [h3("Tab 4: OperatingProcessTab.tsx")]
story += [pj("""
Two section cards: Process & Operating Details, and Lubrication & Maintenance.
<br/><br/>
Operating speeds and load ranges use a custom <b>RangeInput</b> component with Min/Max fields.
Operating Environment uses a <b>MultiSelect</b> component (13 options, multi-choice).
Maintenance section has date pickers and a textarea for notes.
""")]

story += [h3("Tab 5: SensorsOrientationTab.tsx")]
story += [pj("""
Two-panel layout: left panel (2/3 width) = sensor table, right panel (1/3 width) = SVG diagram.
<br/><br/>
<b>Default sensor rows:</b> 6 pre-defined rows for standard motor-pump measurement points:
DE Horizontal, DE Vertical, DE Axial, NDE Horizontal, NDE Vertical, NDE Axial.
Each row has editable Mounting Location and Orientation dropdowns (local state, not submitted to backend via form).
<br/><br/>
<b>Additional sensors:</b> Uses React Hook Form's <code>useFieldArray</code> to manage a dynamic list
of sensor objects that ARE included in the form submission. Each sensor has 7+ fields.
<br/><br/>
<b>Custom values:</b> When sampling_rate = 'Custom' or frequency_range = 'Custom', extra
integer input fields appear inline for the custom Hz values.
<br/><br/>
<b>SensorMountingDiagram:</b> Receives a map of location→orientation. Arrows in the SVG
turn blue (active) when a location has an orientation configured.
""")]

story += [h3("Tab 6: ReviewSaveTab.tsx")]
story += [pj("""
Two-column layout: left (2/3) = full form data summary, right (1/3) = AI Readiness widget.
<br/><br/>
The left column shows every filled-in field grouped in expandable sections.
Null/empty fields are skipped (ReviewRow returns null if no value).
<br/><br/>
The right column shows:
<br/>• Circular SVG gauge (0–100%) with color coding
<br/>• 5-item checklist with green/grey icons
<br/>• Asset Configuration section (status dropdown + 3 boolean checkboxes)
""")]
story += [sp(6)]

# 4.10 SensorMountingDiagram.tsx
story += [h2("4.10  src/components/equipment/SensorMountingDiagram.tsx"), hr()]
story += [pj("""
<b>Role:</b> A pure SVG visualization component. Shows a schematic cross-section of a motor-pump
train with arrows indicating measurement directions.
<br/><br/>
<b>Layout:</b> NDE block (blue, left) → Shaft (center bar) → DE block (yellow, right).
Six arrows: Vertical↑ on NDE, Vertical↑ on DE, Axial← on NDE, Axial→ on DE,
Horizontal on NDE (left side), Horizontal↓ on DE (bottom).
<br/><br/>
<b>Color logic:</b> <code>getColor(location)</code> — if <code>orientations[location]</code> has a value,
returns blue (#2563eb); otherwise returns grey (#d1d5db). This turns arrows blue when
the corresponding row in the sensor table has a selection.
""")]
story += [sp(6)]

# 4.11 UI components
story += [h2("4.11  src/components/ui/ — Reusable UI Components"), hr()]
story += [info_table([
    ("FormField.tsx", "Label wrapper with error display. Also exports: TextInput (styled input), SelectInput (styled select), TextareaInput, RangeInput (min-to-max input pair with unit label)"),
    ("MultiSelect.tsx", "Custom dropdown for selecting multiple values from a list (used for operating environment). Shows selected items as pills, remaining as checkboxes in dropdown"),
    ("SectionCard.tsx", "White card with border, shadow, title row with icon, and a content area. Used as a consistent section wrapper throughout all tabs"),
    ("Toast.tsx", "Toast notification system. ToastProvider creates a React Context with showToast(). Renders absolute-positioned toast messages (success=green, error=red). Auto-dismisses after 3.5s"),
])]
story += [sp(6)]

# 4.12 utils.ts
story += [h2("4.12  src/lib/utils.ts"), hr()]
story += [pj("""
Exports a single <code>cn()</code> utility function that merges Tailwind class names.
Uses <b>clsx</b> (conditional class composition) and <b>tailwind-merge</b> (resolves conflicting
Tailwind classes, e.g. p-2 + p-4 → p-4). Used throughout the component tree for conditional styling.
""")]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — DATABASE
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("5. Database — Schema & Design"), sp(8)]

story += [h2("5.1  equipment_masters Table")]
story += [pj("Primary table. Every registered machine is one row.")]

db1_data = [
    [Paragraph(h, S("H", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white))
     for h in ["Column", "Type", "Constraint", "Description"]],
]
db1_rows = [
    ("id", "UUID", "PK, DEFAULT gen_random_uuid()", "Unique equipment identifier"),
    ("plant_name", "VARCHAR(255)", "NOT NULL", "Factory / plant name"),
    ("area", "VARCHAR(255)", "NOT NULL", "Zone within the plant"),
    ("line", "VARCHAR(255)", "NOT NULL", "Production line"),
    ("machine_name", "VARCHAR(255)", "NOT NULL", "Descriptive name"),
    ("machine_id", "VARCHAR(100)", "NOT NULL, UNIQUE, INDEX", "Asset code"),
    ("machine_type", "VARCHAR(50)", "NOT NULL, INDEX", "Equipment category"),
    ("machine_criticality", "VARCHAR(20)", "NOT NULL", "Low/Medium/High/Critical"),
    ("manufacturer", "VARCHAR(255)", "nullable", "OEM name"),
    ("model", "VARCHAR(255)", "nullable", "Model number"),
    ("serial_number", "VARCHAR(100)", "nullable", "Serial number"),
    ("rated_power_kw", "NUMERIC(10,2)", "nullable", "Nameplate power in kW"),
    ("rated_rpm", "INTEGER", "nullable", "Nameplate speed"),
    ("drive_type", "VARCHAR(50)", "nullable", "Direct/Belt/Gear/VFD..."),
    ("load_type", "VARCHAR(50)", "nullable", "Constant/Variable..."),
    ("foundation_type", "VARCHAR(50)", "nullable", "Concrete/Skid..."),
    ("coupling_details", "VARCHAR(50)", "nullable", "Flexible/Gear/Jaw..."),
    ("bearing_details", "TEXT", "nullable", "Free text bearing description"),
    ("bearing_number_de", "VARCHAR(100)", "nullable", "Drive end bearing part#"),
    ("bearing_number_nde", "VARCHAR(100)", "nullable", "Non-drive end bearing part#"),
    ("gearbox_ratio", "NUMERIC(8,3)", "nullable", "e.g. 4.250"),
    ("gear_teeth", "INTEGER", "nullable", "Number of gear teeth"),
    ("motor_pole_count", "INTEGER", "nullable", "2/4/6/8/10/12"),
    ("fan_blades", "INTEGER", "nullable", "Number of fan blades"),
    ("pump_vanes", "INTEGER", "nullable", "Number of impeller vanes"),
    ("direction_of_rotation", "VARCHAR(30)", "nullable", "CW/CCW/Bidirectional"),
    ("operating_speed_min", "INTEGER", "nullable", "Min actual RPM"),
    ("operating_speed_max", "INTEGER", "nullable", "Max actual RPM"),
    ("load_range_min", "NUMERIC(5,2)", "nullable", "Min load %"),
    ("load_range_max", "NUMERIC(5,2)", "nullable", "Max load %"),
    ("normal_operating_load", "NUMERIC(5,2)", "nullable", "Typical load %"),
    ("process_details", "TEXT", "nullable", "Process description"),
    ("operating_environment", "TEXT[]", "nullable", "PostgreSQL array of tags"),
    ("lubrication_type", "VARCHAR(50)", "nullable", "Grease/Oil Bath..."),
    ("installation_date", "DATE", "nullable", "Commission date"),
    ("last_maintenance_date", "DATE", "nullable", "Last service date"),
    ("maintenance_notes", "TEXT", "nullable", "Free text notes"),
    ("equipment_image_path", "VARCHAR(500)", "nullable", "Relative file path"),
    ("asset_status", "VARCHAR(30)", "DEFAULT 'Active'", "Operational state"),
    ("machine_train_configured", "BOOLEAN", "DEFAULT false", "AI readiness flag"),
    ("bearing_database_mapped", "BOOLEAN", "DEFAULT false", "AI readiness flag"),
    ("operating_mode_configured", "BOOLEAN", "DEFAULT false", "AI readiness flag"),
    ("created_at", "TIMESTAMPTZ", "DEFAULT now()", "Creation timestamp"),
    ("updated_at", "TIMESTAMPTZ", "DEFAULT now()", "Last update timestamp"),
]
for row in db1_rows:
    db1_data.append([Paragraph(c, S("DC", fontName="Courier" if i<2 else "Helvetica", fontSize=8,
                                     textColor=colors.HexColor("#1f2937"))) for i,c in enumerate(row)])
db1_tbl = Table(db1_data, colWidths=[W*0.26, W*0.19, W*0.25, W*0.30])
db1_tbl.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e3a8a")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f0f4ff"), colors.white]),
    ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#dbeafe")),
    ("TOPPADDING",   (0,0), (-1,-1), 4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ("LEFTPADDING",  (0,0), (-1,-1), 5), ("VALIGN",(0,0),(-1,-1),"TOP"),
    ("FONTSIZE",     (0,0), (-1,0), 9),
]))
story += [db1_tbl, sp(10)]

story += [h2("5.2  sensor_configurations Table")]
story += [pj("Child table. Many sensors can belong to one equipment (one-to-many).")]

db2_rows = [
    ("id", "UUID", "PK", "Sensor identifier"),
    ("equipment_id", "UUID", "FK → equipment_masters.id ON DELETE CASCADE, INDEX", "Owner equipment"),
    ("sensor_type", "VARCHAR(50)", "NOT NULL", "IEPE Accelerometer, Velocity Sensor, etc."),
    ("mounting_location", "VARCHAR(100)", "NOT NULL", "Bearing Housing DE/NDE, Motor, etc."),
    ("orientation", "VARCHAR(30)", "NOT NULL", "Horizontal/Vertical/Axial"),
    ("mounting_method", "VARCHAR(50)", "nullable", "Stud/Magnetic/Adhesive..."),
    ("sensitivity", "NUMERIC(10,4)", "nullable", "e.g. 100.0000 mV/g"),
    ("sensitivity_unit", "VARCHAR(20)", "nullable", "mV/g, mV/mm/s, etc."),
    ("sampling_rate", "VARCHAR(20)", "nullable", "e.g. '4096 Hz' or 'Custom'"),
    ("sampling_rate_custom", "INTEGER", "nullable", "Hz value if Custom"),
    ("frequency_range", "VARCHAR(20)", "nullable", "e.g. '0-5000 Hz' or 'Custom'"),
    ("frequency_range_custom_min", "INTEGER", "nullable", "Min Hz if Custom"),
    ("frequency_range_custom_max", "INTEGER", "nullable", "Max Hz if Custom"),
    ("is_active", "BOOLEAN", "DEFAULT true", "Active/inactive flag"),
    ("created_at", "TIMESTAMPTZ", "DEFAULT now()", "Creation timestamp"),
]
db2_data = [[Paragraph(h, S("H2", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white))
             for h in ["Column", "Type", "Constraint", "Description"]]]
for row in db2_rows:
    db2_data.append([Paragraph(c, S("D2", fontName="Courier" if i<2 else "Helvetica", fontSize=8,
                                     textColor=colors.HexColor("#1f2937"))) for i,c in enumerate(row)])
db2_tbl = Table(db2_data, colWidths=[W*0.26, W*0.19, W*0.25, W*0.30])
db2_tbl.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e3a8a")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f0f4ff"), colors.white]),
    ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#dbeafe")),
    ("TOPPADDING",   (0,0), (-1,-1), 4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ("LEFTPADDING",  (0,0), (-1,-1), 5), ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story += [db2_tbl, sp(10)]

story += [h2("5.3  Database Design Decisions")]
story += [info_table([
    ("UUID primary keys", "UUIDs (not integers) prevent enumeration attacks and allow safe distributed key generation. PostgreSQL's gen_random_uuid() generates them server-side"),
    ("CASCADE delete", "sensor_configurations.equipment_id has ON DELETE CASCADE — deleting equipment automatically deletes all its sensors, maintaining referential integrity"),
    ("ARRAY column", "operating_environment uses PostgreSQL's native ARRAY(TEXT) type — avoids creating a junction table for a simple multi-select field"),
    ("Indexes", "machine_id has UNIQUE index for fast duplicate checks. plant_name and machine_type have non-unique indexes for filter queries"),
    ("Numeric precision", "rated_power_kw: NUMERIC(10,2), gearbox_ratio: NUMERIC(8,3), sensitivity: NUMERIC(10,4) — precise decimal storage without floating-point errors"),
    ("Timestamps", "Both tables use TIMESTAMPTZ (timezone-aware). equipment_masters.updated_at auto-updates via SQLAlchemy onupdate"),
    ("No soft delete", "Currently uses hard delete. CASCADE ensures no orphan sensor rows"),
])]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — API REFERENCE (COMPLETE)
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("6. API Reference — All Endpoints"), sp(8)]
story += [pj("Base URL: <b>http://localhost:8000</b>  |  All equipment endpoints: <b>/api/v1/equipment</b>  |  Lookups: <b>/api/v1/lookups</b>")]
story += [sp(6)]

story += [h2("6.1  Equipment Endpoints")]
story += [api_table([
    ("POST",   "/api/v1/equipment/",                    "Create equipment. Body: EquipmentCreate JSON. Returns: EquipmentOut (201)"),
    ("GET",    "/api/v1/equipment/",                    "List equipment. Params: page, page_size, plant_name, machine_type, machine_criticality. Returns: PaginatedEquipment"),
    ("GET",    "/api/v1/equipment/{id}",                "Get single equipment with all sensors. Returns: EquipmentOut"),
    ("PUT",    "/api/v1/equipment/{id}",                "Full update. Body: EquipmentUpdate JSON. Returns: EquipmentOut"),
    ("PATCH",  "/api/v1/equipment/{id}",                "Partial update. Body: partial EquipmentUpdate. Returns: EquipmentOut"),
    ("DELETE", "/api/v1/equipment/{id}",                "Delete equipment + sensors. Returns: 204 No Content"),
])]
story += [sp(8)]

story += [h2("6.2  Image Endpoints")]
story += [api_table([
    ("POST",   "/api/v1/equipment/{id}/image",          "Upload image. Body: multipart/form-data, field 'file'. Max 10MB. Allowed: JPEG, PNG, WebP, GIF"),
    ("GET",    "/api/v1/equipment/{id}/image",          "Download/view image. Returns: binary FileResponse"),
    ("DELETE", "/api/v1/equipment/{id}/image",          "Remove image file and clear DB path. Returns: 204"),
])]
story += [sp(8)]

story += [h2("6.3  Sensor Endpoints")]
story += [api_table([
    ("GET",    "/api/v1/equipment/{id}/sensors",        "List all sensors for equipment"),
    ("POST",   "/api/v1/equipment/{id}/sensors",        "Add sensor. Body: SensorConfigCreate"),
    ("PUT",    "/api/v1/equipment/{id}/sensors/{sid}",  "Update sensor. Body: SensorConfigUpdate"),
    ("DELETE", "/api/v1/equipment/{id}/sensors/{sid}",  "Delete sensor"),
])]
story += [sp(8)]

story += [h2("6.4  AI Readiness & Lookup Endpoints")]
story += [api_table([
    ("GET", "/api/v1/equipment/{id}/ai-readiness",      "Returns AIReadinessOut: score_percent (0-100) + 5 boolean checks"),
    ("GET", "/api/v1/lookups/",                          "Returns all lookup categories as single JSON object"),
    ("GET", "/api/v1/lookups/{name}",                    "Returns values array for one lookup category"),
    ("GET", "/health",                                   "Health check. Returns: {status: 'ok'}"),
])]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — CONNECTION MAP
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("7. Frontend ↔ Backend Connection Map"), sp(8)]
story += [pj("""
Every API call that the frontend makes, where it's made from, what triggers it, and what API
function/endpoint it hits.
""")]
story += [sp(4)]

conn_data = [
    [Paragraph(h, S("CH", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white))
     for h in ["Trigger / Component", "API Function", "HTTP Call", "Purpose"]],
]
conn_rows = [
    ("Dashboard mounts", "listEquipment()", "GET /api/v1/equipment/?page=1&page_size=20", "Initial equipment list load"),
    ("Filter dropdown change", "listEquipment({machine_type})", "GET /api/v1/equipment/?machine_type=Pump", "Server-side filter"),
    ("Pagination Next/Prev", "listEquipment({page:2})", "GET /api/v1/equipment/?page=2", "Load next page"),
    ("Delete icon click", "deleteEquipment(id)", "DELETE /api/v1/equipment/{id}", "Remove equipment"),
    ("+ Add Equipment btn", "(React Router navigate)", "/equipment/new route", "Navigate to form"),
    ("Edit icon click", "(React Router navigate)", "/equipment/{id}/edit route", "Navigate to edit form"),
    ("EditEquipmentPage mounts", "getEquipment(id)", "GET /api/v1/equipment/{id}", "Load existing data into form"),
    ("Form Tab 6: Save & Finish (new)", "createEquipment(data)", "POST /api/v1/equipment/", "Create new equipment record"),
    ("Form Tab 6: Save & Finish (edit)", "updateEquipment(id, data)", "PATCH /api/v1/equipment/{id}", "Update existing record"),
    ("After save, if image selected", "uploadEquipmentImage(id, file)", "POST /api/v1/equipment/{id}/image", "Upload equipment photo"),
    ("AI Readiness widget (Tab 6)", "(computed locally)", "No API call — computed from form state", "Live readiness score"),
]
for row in conn_rows:
    conn_data.append([Paragraph(c, S("CD", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#111827")))
                      for c in row])
conn_tbl = Table(conn_data, colWidths=[W*0.23, W*0.20, W*0.32, W*0.25])
conn_tbl.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e40af")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f0f9ff"), colors.white]),
    ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#e0f2fe")),
    ("TOPPADDING",   (0,0), (-1,-1), 5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ("LEFTPADDING",  (0,0), (-1,-1), 6), ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story += [conn_tbl, sp(10)]

story += [h2("7.1  How CORS Works Here")]
story += [pj("""
The browser enforces the Same-Origin Policy — it blocks requests from one origin (localhost:5173)
to another (localhost:8000) unless the server explicitly allows it.
<br/><br/>
FastAPI's <b>CORSMiddleware</b> sends these response headers:
<br/>• <b>Access-Control-Allow-Origin: http://localhost:5173</b>
<br/>• <b>Access-Control-Allow-Methods: *</b>
<br/>• <b>Access-Control-Allow-Headers: *</b>
<br/><br/>
The Axios client on the frontend does NOT need to do anything special — the browser reads
these headers and allows the response to reach JavaScript code.
""")]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — DASHBOARD IMAGE EXPLANATION
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("8. Dashboard Image — What You See & Why"), sp(8)]

story += [pj("""
The screenshot shows the Dashboard page after one equipment entry (a Pump) has been created.
Here is a precise technical explanation of every visible element.
""")]
story += [sp(6)]

story += [h2("8.1  Header Bar")]
story += [info_table([
    ("Blue icon (Activity)", "Lucide-react 'Activity' icon. Rendered in a blue-600 rounded-xl div"),
    ("'AI Vibration Intelligence Platform'", "h1 with font-bold text-gray-900. Hardcoded in Dashboard.tsx line 61"),
    ("'Equipment Master Data — Stage 1'", "Subtitle paragraph text-xs text-gray-500. Describes the current module"),
    ("'+ Add Equipment' button", "Blue button that calls navigate('/equipment/new'). Only shown in header. Uses Plus icon from lucide-react"),
])]
story += [sp(6)]

story += [h2("8.2  Stats Cards (4 Cards)")]
story += [pj("""
Four cards in a responsive grid (2-column on mobile, 4-column on desktop).
Each card shows a Cpu icon in a colored background circle, a bold number, and a label.
""")]
story += [info_table([
    ("'1 — Total Equipment'", "data.total from PaginatedEquipment response = 1. This is the server-side total count"),
    ("'0 — Critical'", "data.items.filter(i => i.machine_criticality === 'Critical').length = 0. Filters current page client-side"),
    ("'0 — High'", "data.items.filter(i => i.machine_criticality === 'High').length = 0"),
    ("'1 — Active'", "data.items.filter(i => i.asset_status === 'Active').length = 1. The one equipment has status='Active'"),
    ("Colors", "Total=blue, Critical=purple, High=red, Active=green — defined in the stat config array in Dashboard.tsx"),
])]
story += [sp(6)]

story += [h2("8.3  Search & Filter Bar")]
story += [info_table([
    ("Search input", "Controlled input, value=search state. Filters client-side over machine_name, machine_id, plant_name of current page results"),
    ("'All Types' dropdown", "Select with options from MACHINE_TYPES array. On change sets filterType state → triggers new API call"),
    ("'All Criticality' dropdown", "Select with Low/Medium/High/Critical. Sets filterCriticality → triggers new API call"),
])]
story += [sp(6)]

story += [h2("8.4  Equipment Table Row")]
story += [pj("The single row visible in the screenshot corresponds to the one saved equipment record:")]
story += [info_table([
    ("Machine column (blue icon + '—' + 'Pump')", "Icon: Cpu in bg-blue-100 div. '—' is machine_name (either empty or set to dash). 'Pump' shows below as manufacturer — but wait: looking at the screenshot, the machine name appears to be blank/dash and 'Pump' is in the Type column"),
    ("ID column (grey badge)", "machine_id rendered in font-mono bg-gray-100 badge. Appears blank/loading"),
    ("Type column: 'Pump'", "machine_type = 'Pump' from the saved record"),
    ("Plant/Area column", "plant_name / area from the record (appears empty in screenshot)"),
    ("Criticality: 'Medium' (yellow badge)", "machine_criticality = 'Medium'. Badge uses CRITICALITY_COLORS['Medium'] = 'bg-yellow-100 text-yellow-800 border-yellow-200'. The yellow dot uses CRITICALITY_DOT['Medium'] = 'bg-yellow-500'"),
    ("Status: 'Active' (green pill)", "asset_status = 'Active'. Conditional class: bg-green-100 text-green-700"),
    ("Edit icon (pencil)", "Edit2 icon from lucide-react. Navigates to /equipment/{id}/edit"),
    ("Delete icon (trash)", "Trash2 icon. Opens window.confirm() then calls deleteEquipment(id)"),
])]
story += [sp(6)]

story += [h2("8.5  Why These Values?")]
story += [pj("""
The data visible in the dashboard comes from the database record created when someone
submitted the 6-tab Equipment Form with:
<br/>• <b>machine_type = 'Pump'</b> (selected in Tab 1, BasicDetailsTab dropdown)
<br/>• <b>machine_criticality = 'Medium'</b> (selected in Tab 1 criticality dropdown)
<br/>• <b>asset_status = 'Active'</b> (default value set in Tab 6, ReviewSaveTab)
<br/>• machine_name and machine_id appear empty/dash — the user may not have filled those fields,
  or they submitted with defaults
<br/><br/>
The backend stored this via <b>POST /api/v1/equipment/</b>, SQLAlchemy wrote it to PostgreSQL,
and the dashboard fetches it via <b>GET /api/v1/equipment/</b> on page load using React Query.
""")]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — AI READINESS SCORE
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("9. AI Readiness Score — Calculation & Logic"), sp(8)]

story += [pj("""
The AI Readiness Score quantifies how well an equipment record is prepared for AI-based
vibration analysis. A score of 100% means the AI engine has all the data it needs to:
calculate fault frequencies, detect anomalies, and generate alerts.
""")]
story += [sp(6)]

story += [h2("9.1  The 5 Checks")]
story += [info_table([
    ("1. Machine Train Configured", "equipment.machine_train_configured == True. A boolean flag the user explicitly checks in Tab 6. Indicates: machine chain (motor + coupling + pump) has been defined"),
    ("2. Asset Status Set", "equipment.asset_status is not None and not empty string. Almost always True since default = 'Active'"),
    ("3. Sensor Coverage", "len(equipment.sensors) > 0. At least one sensor must be configured in Tab 5. This is the most commonly missing check"),
    ("4. Bearing Database Mapped", "equipment.bearing_database_mapped == True. A boolean flag the user checks. Indicates: bearing catalogue numbers (DE + NDE) have been entered in Tab 3"),
    ("5. Operating Mode Configured", "equipment.operating_speed_min is not None AND equipment.operating_speed_max is not None. The speed range in Tab 4 must be filled"),
])]
story += [sp(6)]

story += [h2("9.2  Score Calculation (Backend — crud/equipment.py)")]
story += [pj("The <b>compute_ai_readiness()</b> function:")]
story += [code(
    "checks = {\n"
    "    'machine_train_configured': equipment.machine_train_configured or False,\n"
    "    'asset_status_set': equipment.asset_status not in (None, ''),\n"
    "    'sensor_coverage': len(equipment.sensors) > 0,\n"
    "    'bearing_database_mapped': equipment.bearing_database_mapped or False,\n"
    "    'operating_mode_configured': (\n"
    "        equipment.operating_speed_min is not None and\n"
    "        equipment.operating_speed_max is not None\n"
    "    ),\n"
    "}\n"
    "score = int(sum(checks.values()) / len(checks) * 100)\n"
    "# sum(checks.values()) = number of True checks (0-5)\n"
    "# / len(checks) = / 5\n"
    "# * 100 = percentage\n"
    "# int() truncates (not rounds): 3/5*100 = 60, 2/5*100 = 40"
)]
story += [sp(4)]

story += [info_table([
    ("0 checks pass", "score = 0%"),
    ("1 check passes", "score = 20%"),
    ("2 checks pass", "score = 40%"),
    ("3 checks pass", "score = 60%"),
    ("4 checks pass", "score = 80%"),
    ("5 checks pass", "score = 100%"),
])]
story += [sp(6)]

story += [h2("9.3  Frontend Display (ReviewSaveTab.tsx)")]
story += [pj("""
The frontend computes the same score <b>locally from form state</b> using identical logic —
so users see a live score as they fill in the form without making an API call:
""")]
story += [code(
    "const score = Math.round(\n"
    "    (checks.filter(c => c.value).length / checks.length) * 100\n"
    ");"
)]
story += [pj("""
Note: The frontend uses Math.round() while the backend uses int() (truncation). For multiples
of 20 these give the same result.
<br/><br/>
<b>Gauge color coding:</b>
<br/>• score ≥ 80% → green (#16a34a)
<br/>• score ≥ 60% → blue (#2563eb)
<br/>• score ≥ 40% → amber (#f59e0b)
<br/>• score < 40% → red (#ef4444)
<br/><br/>
<b>Gauge SVG math:</b> The circle has r=40, so circumference = 2π×40 ≈ 251.2.
strokeDasharray = [(score/100) × 251.2, 251.2]. The SVG is rotated -90° so the arc
starts at the top (12 o'clock position).
<br/><br/>
<b>Text below gauge:</b>
<br/>• 100% → "Fully AI-Ready!"
<br/>• ≥ 60% → "Good Coverage"
<br/>• < 60% → "Needs More Data"
""")]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — FULL WORKFLOW
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("10. Full Request/Response Workflow"), sp(8)]

story += [h2("10.1  Creating New Equipment (Happy Path)")]
workflow_rows = [
    ("Step", "Where", "What Happens"),
    ("1. User clicks '+ Add Equipment'", "Dashboard.tsx", "navigate('/equipment/new') — React Router renders NewEquipmentPage"),
    ("2. Form initializes", "EquipmentForm.tsx", "useForm({resolver: zodResolver(equipmentSchema)}) sets up form state with default values. FormProvider wraps all tabs"),
    ("3. User fills Tab 1", "BasicDetailsTab.tsx", "useFormContext() reads/writes form state. Image file stored in pendingImage state (not form)"),
    ("4. User clicks 'Next'", "EquipmentForm.tsx", "goToTab(2) called. Tab 1 added to completedTabs set. activeTab = 2"),
    ("5. User fills Tabs 2-5", "Each tab component", "All controlled by React Hook Form via useFormContext(). Sensor arrays managed by useFieldArray"),
    ("6. Tab 6 auto-renders", "ReviewSaveTab.tsx", "watch() reads all form values. AI score computed locally from checks. User sees full summary"),
    ("7. User clicks 'Save & Finish'", "EquipmentForm.tsx", "handleSubmit(onSubmit) runs. Zod validates all fields. If valid, onSubmit() called"),
    ("8. createEquipment() called", "api/equipment.ts", "axios.post('/api/v1/equipment/', data). Full form JSON sent"),
    ("9. FastAPI receives POST", "routers/equipment.py", "Pydantic validates body as EquipmentCreate. Calls crud.create_equipment(db, data)"),
    ("10. DB write", "crud/equipment.py", "Equipment ORM object created, db.flush() to get UUID. SensorConfiguration objects created. db.commit()"),
    ("11. Response returned", "FastAPI → axios → React", "EquipmentOut JSON returned (HTTP 201). axios resolves the promise"),
    ("12. Image upload (if selected)", "EquipmentForm.tsx", "uploadEquipmentImage(equipment.id, pendingImage). POST /api/v1/equipment/{id}/image with FormData"),
    ("13. Backend saves image", "routers/equipment.py", "Validates MIME + size. Saves to uploads/{id}.ext. Updates equipment_image_path in DB"),
    ("14. Toast shown", "Toast.tsx", "showToast('Equipment saved!', 'success') — green notification appears for 3.5s"),
    ("15. Navigate", "EquipmentForm.tsx", "setTimeout(() => navigate('/'), 1200) — returns to dashboard after 1.2s"),
    ("16. Dashboard refreshes", "Dashboard.tsx", "React Query automatically has stale ['equipment'] query → refetches → new row appears"),
]
wf_data = []
for i, row in enumerate(workflow_rows):
    style_fn = (lambda c: Paragraph(c, S("WHdr", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white))) if i==0 else (lambda c: Paragraph(c, S("WBody", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#111827"))))
    wf_data.append([style_fn(c) for c in row])
wf_tbl = Table(wf_data, colWidths=[W*0.30, W*0.20, W*0.50])
wf_tbl.setStyle(TableStyle([
    ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1e3a8a")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f8fafc"), colors.white]),
    ("GRID",         (0,0), (-1,-1), 0.4, colors.HexColor("#e2e8f0")),
    ("TOPPADDING",   (0,0), (-1,-1), 4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
    ("LEFTPADDING",  (0,0), (-1,-1), 6), ("VALIGN",(0,0),(-1,-1),"TOP"),
]))
story += [wf_tbl, sp(10)]

story += [h2("10.2  Editing Equipment")]
story += [info_table([
    ("1. Edit icon clicked", "navigate('/equipment/{id}/edit') — React Router loads EditEquipmentPage"),
    ("2. useQuery fires", "GET /api/v1/equipment/{id} — fetches full equipment with sensors"),
    ("3. Data transformation", "Date strings split on 'T' to get YYYY-MM-DD for HTML date inputs"),
    ("4. Form pre-filled", "initialData passed to EquipmentForm → useForm defaultValues populated"),
    ("5. User edits any field", "Form state updated reactively by React Hook Form"),
    ("6. Save & Finish", "updateEquipment(editId, data) → PATCH /api/v1/equipment/{id} with changed fields"),
    ("7. SQLAlchemy UPDATE", "model_dump(exclude_unset=True) ensures only sent fields are updated in DB"),
])]
story += [sp(8)]

story += [h2("10.3  Deleting Equipment")]
story += [info_table([
    ("1. User clicks trash icon", "handleDelete(id, name) called"),
    ("2. Confirmation dialog", "window.confirm('Delete X? This cannot be undone.') — browser native dialog"),
    ("3. If confirmed", "deleteMutation.mutate(id) → DELETE /api/v1/equipment/{id}"),
    ("4. Backend processes", "crud.delete_equipment() loads equipment, calls db.delete() — CASCADE removes sensors"),
    ("5. On success", "queryClient.invalidateQueries(['equipment']) — React Query marks list as stale, re-fetches"),
    ("6. Toast shown", "showToast('Equipment deleted.', 'success')"),
])]
story += [PageBreak()]

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — DEPLOYMENT
# ══════════════════════════════════════════════════════════════════════════════
story += [section_box("11. Deployment & Infrastructure"), sp(8)]

story += [h2("11.1  Docker Compose (docker-compose.yml)")]
story += [pj("""
Two Docker services are defined. They are started with <code>docker-compose up -d</code>
from the project root.
""")]
story += [info_table([
    ("postgres service", "Image: postgres:16. Container: vibration_platform_db. Exposes port 5433 (host) → 5432 (container). Uses named volume postgres_data for persistence. Reads POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB from .env"),
    ("pgadmin service", "Image: dpage/pgadmin4. Container: vibration_platform_pgadmin. Exposes port 5050 → 80. Web UI for browsing the database. Depends on postgres starting first"),
    ("Health check", "postgres service has a pg_isready health check (10s interval, 5 retries) so dependent services wait for DB to be ready"),
    ("Named volumes", "postgres_data and pgadmin_data persist data across container restarts"),
])]
story += [sp(6)]

story += [h2("11.2  Backend Startup")]
story += [info_table([
    ("1. Create .env", "Copy .env.example, fill in DATABASE_URL pointing to localhost:5433"),
    ("2. Create venv", "python -m venv .venv && .venv\\Scripts\\activate"),
    ("3. Install deps", "pip install -r requirements.txt"),
    ("4. Run migrations", "alembic upgrade head — creates tables in PostgreSQL"),
    ("5. Start server", "uvicorn app.main:app --reload --port 8000"),
    ("Swagger UI", "http://localhost:8000/docs — auto-generated interactive API documentation"),
])]
story += [sp(6)]

story += [h2("11.3  Frontend Startup")]
story += [info_table([
    ("1. Install deps", "cd frontend && npm install"),
    ("2. Start dev server", "npm run dev — Vite starts on http://localhost:5173 with HMR"),
    ("3. Build for prod", "npm run build — TypeScript compile + Vite bundle → dist/ folder"),
    ("VITE_API_BASE_URL", "Set in frontend/.env to override the backend URL (default: http://localhost:8000)"),
])]
story += [sp(6)]

story += [h2("11.4  Port Summary")]
story += [info_table([
    ("5173", "Vite dev server — React frontend"),
    ("8000", "Uvicorn — FastAPI backend"),
    ("5433", "PostgreSQL (Docker, mapped from container's 5432)"),
    ("5050", "pgAdmin web UI (Docker)"),
])]
story += [sp(10)]

story += [hr_blue()]
story += [Paragraph("End of Documentation", S("END", fontName="Helvetica-Bold", fontSize=12,
          textColor=colors.HexColor("#6b7280"), alignment=TA_CENTER, spaceBefore=20))]
story += [Paragraph("AI Vibration Intelligence Platform — Stage 1 Equipment Master Data",
          S("END2", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#9ca3af"),
            alignment=TA_CENTER, spaceAfter=6))]

# ─── Build PDF ────────────────────────────────────────────────────────────────
doc.build(story)
print(f"PDF generated: {OUTPUT}")
