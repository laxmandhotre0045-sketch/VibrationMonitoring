"""
Generate 3–4 page project progress summary PDF.
Run: python scripts/generate_project_summary_pdf.py
"""
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)
from reportlab.lib.colors import HexColor

OUTPUT = Path(__file__).resolve().parent.parent / "AI_Vibration_Platform_Progress_Summary.pdf"

PRIMARY = HexColor("#15366D")
ACCENT = HexColor("#F5A623")
TEXT = HexColor("#1a1a2e")
MUTED = HexColor("#64748b")
LIGHT = HexColor("#f8fafc")


def styles():
    b = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle("title", parent=b["Title"], fontSize=20, textColor=PRIMARY,
                                 alignment=TA_CENTER, spaceAfter=6, fontName="Helvetica-Bold")
    s["sub"] = ParagraphStyle("sub", parent=b["Normal"], fontSize=10, textColor=MUTED,
                               alignment=TA_CENTER, spaceAfter=14)
    s["h1"] = ParagraphStyle("h1", parent=b["Heading1"], fontSize=14, textColor=PRIMARY,
                              spaceBefore=10, spaceAfter=6, fontName="Helvetica-Bold")
    s["h2"] = ParagraphStyle("h2", parent=b["Heading2"], fontSize=11, textColor=ACCENT,
                              spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold")
    s["body"] = ParagraphStyle("body", parent=b["Normal"], fontSize=9.5, textColor=TEXT,
                                spaceAfter=5, leading=13)
    s["bullet"] = ParagraphStyle("bullet", parent=s["body"], leftIndent=12, spaceAfter=3)
    s["formula"] = ParagraphStyle("formula", parent=b["Code"], fontSize=8.5, textColor=TEXT,
                                   backColor=LIGHT, leftIndent=6, spaceAfter=4, leading=11)
    s["small"] = ParagraphStyle("small", parent=s["body"], fontSize=8, textColor=MUTED)
    return s


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=HexColor("#e2e8f0"), spaceAfter=6)


def tbl(data, widths):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build():
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)
    s = styles()
    story = []

    # ── Cover ──
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("AI Vibration Intelligence Platform", s["title"]))
    story.append(Paragraph("Stage 1 — Progress Summary (Input → Process → Output)", s["sub"]))
    story.append(Paragraph(f"Generated: {date.today().strftime('%B %d, %Y')}", s["small"]))
    story.append(hr())
    story.append(Paragraph(
        "This document summarizes work completed so far: Equipment &amp; Sensor Master registration, "
        "database storage, sensor data upload, and five diagnostic vibration plots with formulas.",
        s["body"],
    ))
    story.append(PageBreak())

    # ── Page 1: Overview + Workflow 1 ──
    story.append(Paragraph("1. Platform Overview", s["h1"]))
    story.append(Paragraph(
        "<b>Stack:</b> React frontend (port 5173) · FastAPI backend (port 8000) · PostgreSQL (port 5433) · pgAdmin (port 5050)",
        s["body"],
    ))
    story.append(tbl([
        ["Layer", "Technology", "Role"],
        ["Frontend", "React, TypeScript, Vite, Tailwind", "UI forms, equipment list, vibration analysis plots"],
        ["Backend", "FastAPI, SQLAlchemy, Pydantic", "REST APIs, validation, plot generation"],
        ["Database", "PostgreSQL 16 + Alembic", "Persistent storage of equipment, sensors, uploads, config"],
        ["Admin", "pgAdmin", "Browse tables, run SQL, verify stored data"],
    ], [3.2*cm, 4.8*cm, 7.5*cm]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("2. Workflow A — Equipment &amp; Sensor Master", s["h1"]))
    story.append(tbl([
        ["Stage", "Input", "Internal Process", "Output"],
        ["INPUT", "User fills 6-step form:\n• Plant / Area / Line\n• Machine name, type, criticality\n• Mechanical & rotating details\n• Operating conditions\n• Sensor config (type, location, orientation)\n• Optional equipment image",
         "—", "Form data in browser"],
        ["PROCESS", "—",
         "1. POST /api/v1/equipment/ (JSON)\n2. Pydantic validates request\n3. CRUD inserts row in equipment_masters\n4. Nested sensors → sensor_configurations\n5. Image → POST /equipment/{id}/image → disk\n6. Alembic manages schema migrations",
         "—"],
        ["OUTPUT", "—", "Data in PostgreSQL (viewable in pgAdmin)",
         "• equipment_masters (1 row per machine)\n• sensor_configurations (1 row per sensor)\n• Image file path in DB; file on disk\n• UUID for each equipment & sensor"],
    ], [2.2*cm, 4.5*cm, 5*cm, 4*cm]))

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Database tables (Stage 1):</b>", s["h2"]))
    story.append(tbl([
        ["Table", "Records", "Key fields"],
        ["equipment_masters", "1 per machine", "plant_name, machine_name, machine_type, 40+ technical columns"],
        ["sensor_configurations", "Many per equipment", "sensor_type, mounting_location, orientation, sampling_rate"],
        ["plot_configurations", "1 per sensor", "channel_count, active_channel, sampling_rate_hz, fft_lines, enabled_plots"],
        ["sensor_data_uploads", "1 per file upload", "sensor_id, channel_count, parse_status, sample_count"],
    ], [4*cm, 3.5*cm, 8*cm]))

    story.append(PageBreak())

    # ── Page 2: Workflow 2 + APIs ──
    story.append(Paragraph("3. Workflow B — Sensor Data Upload &amp; Plots", s["h1"]))
    story.append(tbl([
        ["Stage", "Input", "Internal Process", "Output"],
        ["INPUT",
         "• sensor_id (UUID from equipment)\n• channel_count (e.g. 8)\n• CSV or PDF file\n  (timestamp_, ch0…ch7)\n• Plot config (sampling rate, FFT lines, active channel)",
         "—", "Multipart upload + saved config"],
        ["PROCESS",
         "—",
         "1. POST /api/v1/measurements/upload\n2. pdf_parser extracts rows\n3. Parsed JSON saved to disk\n4. plot_configurations applied\n5. signal_processing computes 5 plots\n6. GET /uploads/{id}/plots returns x,y arrays",
         "—"],
        ["OUTPUT", "—", "Plots rendered in Vibration Analysis UI",
         "• 5 diagnostic plots for selected channel (ch0–ch7)\n• Zoom, pan, autoscale on each chart\n• Upload history per sensor"],
    ], [2.2*cm, 4.5*cm, 5*cm, 4*cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("4. Key API Endpoints", s["h1"]))
    story.append(tbl([
        ["API", "Method", "Purpose"],
        ["/api/v1/equipment/", "POST / GET / PATCH / DELETE", "Equipment CRUD"],
        ["/api/v1/equipment/{id}/sensors", "POST / GET / PUT / DELETE", "Sensor CRUD"],
        ["/api/v1/equipment/{id}/image", "POST / GET", "Equipment photo upload"],
        ["/api/v1/measurements/configure", "POST / GET / PUT", "Plot & acquisition settings per sensor"],
        ["/api/v1/measurements/upload", "POST", "Upload CSV/PDF sensor data"],
        ["/api/v1/measurements/uploads/{id}/plots", "GET", "Generate all 5 plots (?channel=0–7)"],
        ["/health", "GET", "Backend health check"],
    ], [5.5*cm, 3.5*cm, 7.5*cm]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>Data flow diagram:</b> User → React UI → FastAPI → PostgreSQL (metadata) + File storage (images, parsed JSON) → Plot JSON → SVG charts",
        s["body"],
    ))
    story.append(PageBreak())

    # ── Page 3: Formulas ──
    story.append(Paragraph("5. Plot Formulas (Backend: signal_processing.py)", s["h1"]))
    story.append(Paragraph(
        "Notation: x[n] = sample amplitude, N = sample count, f<sub>s</sub> = sampling_rate_hz, t[n] = time in seconds.",
        s["body"],
    ))

    story.append(Paragraph("5.1 Time Axis (shared)", s["h2"]))
    story.append(Paragraph("If timestamp is epoch/batch ID:  t[n] = n / f<sub>s</sub>", s["formula"]))
    story.append(Paragraph("Else:  t[n] = timestamp[n] − timestamp[0]  (seconds or ms/1000)", s["formula"]))

    story.append(Paragraph("5.2 Plot 1 — Time Waveform", s["h2"]))
    story.append(Paragraph("X = t[n],  Y = x[n]  (raw amplitude vs time)", s["formula"]))

    story.append(Paragraph("5.3 Plot 2 — Circular Time Waveform", s["h2"]))
    story.append(Paragraph("θ[n] = 2π·n / N", s["formula"]))
    story.append(Paragraph("X[n] = x[n]·cos(θ[n]),  Y[n] = x[n]·sin(θ[n])", s["formula"]))

    story.append(Paragraph("5.4 Plot 3 — FFT Spectrum", s["h2"]))
    story.append(Paragraph("Hanning window:  w[n] = 0.5·(1 − cos(2πn/(N−1)))", s["formula"]))
    story.append(Paragraph("Windowed data:  x<sub>w</sub>[n] = x[n]·w[n]", s["formula"]))
    story.append(Paragraph("Magnitude:  M[k] = |FFT(x<sub>w</sub>)[k]| · 2/N", s["formula"]))
    story.append(Paragraph("Frequency:  f[k] = k·f<sub>s</sub> / N", s["formula"]))

    story.append(Paragraph("5.5 Plot 4 — Envelope Spectrum", s["h2"]))
    story.append(Paragraph("Analytic signal:  z[n] = x[n] + j·Hilbert(x[n])", s["formula"]))
    story.append(Paragraph("Envelope:  e[n] = |z[n]| − mean(|z|)", s["formula"]))
    story.append(Paragraph("Then FFT of e[n] (same as Plot 3)", s["formula"]))

    story.append(Paragraph("5.6 Plot 5 — Trend Plot", s["h2"]))
    story.append(Paragraph("Split into 32 segments; per segment i:", s["formula"]))
    story.append(Paragraph("RMS<sub>i</sub> = √( (1/N<sub>seg</sub>) · Σ x[n]² )", s["formula"]))
    story.append(Paragraph("X = time at segment centre,  Y = RMS<sub>i</sub>", s["formula"]))

    story.append(PageBreak())

    # ── Page 4: Frontend + status ──
    story.append(Paragraph("6. Frontend Pages Built", s["h1"]))
    story.append(tbl([
        ["Page / Route", "Status", "Function"],
        ["/equipment", "Active", "List, filter, delete equipment"],
        ["/equipment/new & /equipment/:id/edit", "Active", "6-step Equipment Master wizard"],
        ["/analysis", "Active", "Configure sensor, upload CSV/PDF, view 5 plots, switch ch0–ch7"],
        ["/", "Dashboard", "Placeholder — upcoming analytics"],
        ["/settings", "Placeholder", "Planned — acquisition config for edge script"],
    ], [4.5*cm, 2.5*cm, 8.5*cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("7. What Is Complete vs Planned", s["h1"]))
    story.append(tbl([
        ["Area", "Status"],
        ["Equipment & sensor registration → DB", "✓ Complete"],
        ["pgAdmin / PostgreSQL storage", "✓ Complete"],
        ["CSV/PDF upload & parsing", "✓ Complete"],
        ["5 diagnostic plots + formulas", "✓ Complete"],
        ["Plot zoom / pan / autoscale", "✓ Complete"],
        ["Configure API per sensor", "✓ Complete"],
        ["Edge UDP acquisition script integration", "Planned — MAC mapping, own configure URL"],
        ["Settings page for acquisition JSON", "Planned"],
        ["Dashboard live view from uploads", "Planned"],
        ["Replace external Sensovibe APIs", "Planned"],
    ], [7*cm, 9.5*cm]))

    story.append(Spacer(1, 12))
    story.append(hr())
    story.append(Paragraph(
        "AI Vibration Intelligence Platform — Stage 1 Progress Summary · "
        f"{date.today().strftime('%Y-%m-%d')}",
        s["small"],
    ))

    doc.build(story)
    print(f"PDF created: {OUTPUT}")
    return OUTPUT


if __name__ == "__main__":
    build()
