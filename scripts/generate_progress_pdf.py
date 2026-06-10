"""Generate 3-4 page project progress PDF. Run: python scripts/generate_progress_pdf.py"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from reportlab.lib.colors import HexColor
from pathlib import Path
from datetime import date

OUTPUT = Path(__file__).resolve().parent.parent / "AI_Vibration_Platform_Progress.pdf"
PRIMARY = HexColor("#1e3a5f")
ACCENT = HexColor("#2563eb")
LIGHT = HexColor("#f0f4f8")
TEXT = HexColor("#1a1a2e")
MUTED = HexColor("#64748b")


def S():
    b = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=b["Title"], fontSize=20, textColor=PRIMARY, spaceAfter=6, fontName="Helvetica-Bold"),
        "sub": ParagraphStyle("s", parent=b["Normal"], fontSize=10, textColor=MUTED, spaceAfter=14, alignment=1),
        "h1": ParagraphStyle("h1", parent=b["Heading1"], fontSize=14, textColor=PRIMARY, spaceBefore=14, spaceAfter=8, fontName="Helvetica-Bold"),
        "h2": ParagraphStyle("h2", parent=b["Heading2"], fontSize=11, textColor=ACCENT, spaceBefore=10, spaceAfter=5, fontName="Helvetica-Bold"),
        "body": ParagraphStyle("body", parent=b["Normal"], fontSize=9.5, textColor=TEXT, spaceAfter=5, leading=13),
        "bullet": ParagraphStyle("bullet", parent=b["Normal"], fontSize=9.5, leftIndent=14, spaceAfter=3, leading=12),
        "code": ParagraphStyle("code", parent=b["Code"], fontSize=8, fontName="Courier", backColor=HexColor("#f1f5f9"), leftIndent=6),
        "small": ParagraphStyle("small", parent=b["Normal"], fontSize=8, textColor=MUTED),
    }


def tbl(data, widths):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build():
    s = S()
    story = []
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=1.8*cm, bottomMargin=1.8*cm)

    story.append(Paragraph("AI Vibration Intelligence Platform", s["title"]))
    story.append(Paragraph("Stage 1 Progress Report — Equipment Master &amp; Vibration Analysis", s["sub"]))
    story.append(Paragraph(f"Generated: {date.today().strftime('%B %d, %Y')}", s["small"]))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#e2e8f0"), spaceAfter=10))

    # PAGE 1 — Overview + Flow 1
    story.append(Paragraph("1. Project Overview", s["h1"]))
    story.append(Paragraph(
        "Full-stack industrial vibration platform (Stage 1). React frontend, FastAPI backend, PostgreSQL database. "
        "Two main workflows: (A) Equipment &amp; Sensor registration, (B) Sensor data upload and diagnostic plot generation.",
        s["body"],
    ))
    story.append(Paragraph("Technology Stack", s["h2"]))
    story.append(tbl([
        ["Layer", "Technology"],
        ["Frontend", "React 18, TypeScript, Vite, Tailwind, React Query, Axios"],
        ["Backend", "FastAPI, SQLAlchemy, Alembic, Pydantic, NumPy, SciPy"],
        ["Database", "PostgreSQL 16 (port 5433), pgAdmin (port 5050)"],
        ["Deployment", "Docker Compose — postgres, pgadmin, backend, frontend"],
    ], [4*cm, 13*cm]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("2. Workflow A — Equipment &amp; Sensor Master Data", s["h1"]))
    story.append(tbl([
        ["Stage", "Input", "Internal Process", "Output"],
        ["Input", "User fills 6-step form: plant, machine, mechanical, rotating, operating, sensor tabs",
         "React Hook Form + Zod validation on frontend",
         "Validated JSON payload"],
        ["API", "POST /api/v1/equipment/",
         "FastAPI router → Pydantic schema → CRUD → SQLAlchemy ORM",
         "Equipment row in equipment_masters"],
        ["Sensors", "Nested sensors[] in create payload",
         "Insert sensor_configurations rows with equipment_id FK",
         "Sensor records linked to equipment"],
        ["Storage", "All field values",
         "Alembic migration 001/002/003; PostgreSQL tables",
         "Data visible in pgAdmin at localhost:5050"],
        ["Output", "—", "GET /api/v1/equipment/ and /{id}",
         "Equipment list &amp; detail with all fields in DB"],
    ], [2.2*cm, 4.5*cm, 4.8*cm, 4*cm]))

    story.append(PageBreak())

    # PAGE 2 — DB + Workflow B input/process
    story.append(Paragraph("3. Database Tables", s["h1"]))
    story.append(tbl([
        ["Table", "Purpose", "Key relationship"],
        ["equipment_masters", "~40 columns — machine digital twin", "Parent table, UUID primary key"],
        ["sensor_configurations", "Sensor type, mounting, sampling, orientation", "FK equipment_id → CASCADE delete"],
        ["plot_configurations", "Per-sensor plot settings (channel, FFT, sampling rate)", "FK sensor_id, unique per sensor"],
        ["sensor_data_uploads", "Uploaded file metadata, parse status, sample count", "FK sensor_id"],
    ], [4.5*cm, 5.5*cm, 6.5*cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("4. Workflow B — Sensor Data Upload &amp; Plots", s["h1"]))
    story.append(tbl([
        ["Stage", "Input", "Internal Process", "Output"],
        ["Configure", "sensor_id, channel_count, active_channel, sampling_rate_hz, fft_lines",
         "POST /api/v1/measurements/configure (upsert) → plot_configurations table",
         "Saved plot configuration per sensor"],
        ["Upload", "CSV or PDF file + sensor_id + channel_count (multipart form)",
         "pdf_parser.py extracts timestamp_, ch0..chN → JSON file on disk",
         "sensor_data_uploads record (parse_status=parsed)"],
        ["Parse", "Raw rows: timestamp_ms, ch0, ch1, ... ch7",
         "Auto-detect channels; handle epoch timestamps; save parsed JSON",
         "Structured timestamps + channel arrays"],
        ["Plots", "upload_id + optional channel query param",
         "signal_processing.py computes 5 plots → plot_generator.py",
         "JSON with x/y arrays for each plot"],
        ["Display", "Plot JSON from API",
         "Vibration Analysis page (/analysis) — PlotChart SVG with zoom/pan",
         "5 interactive diagnostic charts in browser"],
    ], [2*cm, 4.2*cm, 5.3*cm, 4*cm]))

    story.append(PageBreak())

    # PAGE 3 — APIs + Formulae
    story.append(Paragraph("5. Key API Endpoints", s["h1"]))
    story.append(tbl([
        ["Method", "Endpoint", "Purpose"],
        ["POST", "/api/v1/equipment/", "Create equipment + sensors"],
        ["GET", "/api/v1/equipment/{id}", "Get equipment with sensors"],
        ["POST", "/api/v1/measurements/configure", "Create/update plot config (upsert)"],
        ["POST", "/api/v1/measurements/upload", "Upload CSV/PDF sensor data"],
        ["GET", "/api/v1/measurements/uploads/{id}/plots?channel=N", "Generate all 5 plots"],
        ["GET", "/health", "Backend health check — port 8000"],
    ], [2*cm, 6.5*cm, 7*cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("6. Plot Formulas", s["h1"]))
    story.append(Paragraph("<b>Time axis (all time-based plots):</b> t[n] = n / f_s when timestamps are Unix epoch/batch IDs; otherwise t[n] = timestamp[n] − timestamp[0]", s["bullet"]))
    story.append(Paragraph("<b>1. Time Waveform:</b> Y = x[n] (raw amplitude) vs t[n]. No transformation.", s["bullet"]))
    story.append(Paragraph("<b>2. Circular Time Waveform:</b> θ[n] = 2π·n/N; X[n] = x[n]·cos(θ[n]); Y[n] = x[n]·sin(θ[n])", s["bullet"]))
    story.append(Paragraph("<b>3. FFT Spectrum:</b> Hanning window w[n]; X[k] = FFT(x[n]·w[n]); M[k] = |X[k]|·2/N_fft; f[k] = k·f_s/N_fft", s["bullet"]))
    story.append(Paragraph("<b>4. Envelope Spectrum:</b> e[n] = |Hilbert(x[n])|; remove DC; FFT of e[n] → envelope magnitude vs frequency", s["bullet"]))
    story.append(Paragraph("<b>5. Trend Plot:</b> Split into 32 segments; RMS_i = √(mean(x²)) per segment; plot RMS vs time at segment centre", s["bullet"]))
    story.append(Paragraph("Implementation: backend/app/services/signal_processing.py", s["small"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("7. Frontend Pages (Additive Changes Only)", s["h1"]))
    story.append(tbl([
        ["Page / Route", "Status", "Notes"],
        ["/equipment", "Active", "Equipment list, create, edit — unchanged"],
        ["/analysis", "New", "Upload, configure, 5 plots, ch0–ch7 channel switcher"],
        ["/", "Placeholder", "Dashboard — coming soon"],
        ["/settings", "Placeholder", "Settings — coming soon"],
    ], [3.5*cm, 2.5*cm, 10.5*cm]))

    story.append(PageBreak())

    # PAGE 4 — Edge integration + ports
    story.append(Paragraph("8. Planned Edge Integration (Not Yet Built)", s["h1"]))
    story.append(Paragraph(
        "A separate Python UDP acquisition script collects live 8-channel vibration data at 256 kHz, "
        "fetches configure JSON from an external API, and uploads CSV snippets. Planned integration:",
        s["body"],
    ))
    story.append(Paragraph("• Replace external CONFIG_API_URL with platform configure API (by sensor MAC)", s["bullet"]))
    story.append(Paragraph("• Replace external UPLOAD_API_URL with POST /api/v1/measurements/upload", s["bullet"]))
    story.append(Paragraph("• Map hardware sensorId (MAC) → platform sensor UUID in Equipment Master", s["bullet"]))
    story.append(Paragraph("• Dashboard to auto-display latest upload plots per sensor", s["bullet"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("9. Ports &amp; Access", s["h1"]))
    story.append(tbl([
        ["Service", "URL / Port"],
        ["Frontend (dev)", "http://localhost:5173"],
        ["Frontend (Docker)", "http://localhost:4173"],
        ["Backend API + Swagger", "http://localhost:8000/docs"],
        ["PostgreSQL", "localhost:5433"],
        ["pgAdmin", "http://localhost:5050"],
    ], [5*cm, 11.5*cm]))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#e2e8f0")))
    story.append(Paragraph("AI Vibration Intelligence Platform — Stage 1 Progress Document", s["small"]))

    doc.build(story)
    print(f"PDF: {OUTPUT}")


if __name__ == "__main__":
    build()
