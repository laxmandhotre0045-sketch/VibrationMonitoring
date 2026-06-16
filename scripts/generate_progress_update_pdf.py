"""
Generate progress update PDF — changes since Day 0-1 summary.
Run: python scripts/generate_progress_update_pdf.py
"""
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.colors import HexColor

OUTPUT = Path(__file__).resolve().parent.parent / "AI_Vibration_Platform_Progress_Update_Since_Day01.pdf"

PRIMARY = HexColor("#15366D")
ACCENT = HexColor("#F5A623")
TEXT = HexColor("#1E293B")
MUTED = HexColor("#64748B")
LIGHT_BG = HexColor("#F8FAFC")


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontSize=22,
            textColor=PRIMARY,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontSize=14,
            textColor=PRIMARY,
            spaceBefore=12,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=11,
            textColor=PRIMARY,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=9.5,
            textColor=TEXT,
            leading=13,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontSize=9.5,
            textColor=TEXT,
            leading=13,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            leading=11,
        ),
    }


def table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def hr():
    return HRFlowable(width="100%", thickness=1, color=ACCENT, spaceBefore=4, spaceAfter=10)


def main():
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    story = []

    # ── Cover ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.2 * cm))
    story.append(Paragraph("AI Vibration Intelligence Platform", styles["title"]))
    story.append(Paragraph("Progress Update — Changes Since Day 0–1 Summary", styles["subtitle"]))
    story.append(
        Paragraph(
            f"Generated: {date.today().strftime('%d %B %Y')} · Branch: <b>vaibhavi</b> · "
            f"Baseline doc: <i>AI_Vibration_Platform_Progress_Summary(day 0 -1).docx</i>",
            styles["small"],
        )
    )
    story.append(hr())
    story.append(
        Paragraph(
            "This document lists everything built <b>after</b> the original Day 0–1 progress summary. "
            "That first document covered Equipment Master, CSV/PDF upload, five diagnostic plots (on-demand), "
            "plot configuration API, and basic Vibration Analysis UI. The work below extends the platform "
            "with Docker deployment, authentication, edge acquisition config, persistent plot storage, "
            "and a merged frontend from the <b>laxman-dev</b> branch.",
            styles["body"],
        )
    )

    # ── Page 1: Summary table ─────────────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", styles["h1"]))
    story.append(
        table(
            [
                ["Area", "Day 0–1 Status", "Current Status"],
                ["Equipment Master", "Complete", "Complete (unchanged core)"],
                ["Upload & parsing", "Complete", "Complete + plots stored in DB"],
                ["5 diagnostic plots", "Computed on every GET", "Computed on upload, cached in PostgreSQL"],
                ["Charts UI", "Basic / Plotly-era", "ECharts with zoom, pan, thresholds"],
                ["Authentication", "Not started", "Phase 1 backend + frontend login"],
                ["API protection", "All APIs open", "Only /auth/me protected (Phase 2 pending)"],
                ["Edge acquisition", "Planned", "GET /measurements/acquisition implemented"],
                ["Docker deployment", "Partial / manual", "Full docker-compose stack"],
                ["Git / team merge", "Single branch work", "laxman-dev merged into vaibhavi"],
            ],
            col_widths=[4.2 * cm, 5.2 * cm, 6.6 * cm],
        )
    )

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("2. Database & Migrations (New Since Day 0–1)", styles["h1"]))
    story.append(
        table(
            [
                ["Migration", "What was added"],
                ["004_auth_tables", "users, roles, user_roles, refresh_tokens + seed roles"],
                ["005_sensor_device_id", "device_id column on sensor_configurations (edge MAC lookup)"],
                ["006_plot_results", "plot_results table (JSONB x/y), plots_status on uploads"],
            ],
            col_widths=[4.5 * cm, 11.5 * cm],
        )
    )
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>New table: plot_results</b>", styles["h2"]))
    for line in [
        "Stores computed graph output per upload + plot_type + channel.",
        "Columns: x_data, y_data (JSONB), title, x_label, y_label, metadata, config_fingerprint.",
        "On upload: 5 plots × all channels → e.g. 8 channels = 40 rows per upload.",
        "GET /plots now reads from DB (no recompute on every request).",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(PageBreak())

    # ── Page 2: Backend ───────────────────────────────────────────────────
    story.append(Paragraph("3. Backend Changes", styles["h1"]))
    story.append(Paragraph("3.1 Authentication (Phase 1 — Backend)", styles["h2"]))
    for line in [
        "JWT access token (30 min) + refresh token (7 days, SHA-256 hash in DB).",
        "APIs: POST /api/v1/auth/login, /token, /refresh, /logout, GET /api/v1/auth/me.",
        "Super admin seeded from .env on startup (INITIAL_ADMIN_EMAIL / PASSWORD).",
        "Roles seeded: super_admin, plant_admin, engineer, operator, viewer.",
        "Swagger: BearerAuth scheme for testing /auth/me.",
        "Packages added: python-jose, passlib[bcrypt], bcrypt==4.0.1, email-validator.",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("3.2 Edge Acquisition Config", styles["h2"]))
    for line in [
        "GET /api/v1/measurements/acquisition?device_id={MAC} — Sensovibe-compatible JSON.",
        "GET /api/v1/measurements/acquisition/by-sensor/{sensor_uuid} — testing before device_id set.",
        "Builder: backend/app/services/acquisition_config.py.",
        "Links plot_configurations + sensor device_id for UDP acquisition scripts.",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("3.3 Plot Storage Service", styles["h2"]))
    for line in [
        "New service: backend/app/services/plot_storage.py.",
        "compute_config_fingerprint() — invalidates cache when FFT/sampling settings change.",
        "persist_all_plot_results() — runs on upload for all channels.",
        "upload response now includes plots_status: pending | ready | failed.",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("3.4 Config & Bug Fixes", styles["h2"]))
    for line in [
        "config.py: max_pdf_size_mb=50, measurement_upload_dir for uploads.",
        "machine_id made nullable (migration 002).",
        "seed.py: must_change_password=False for initial admin (was blocking login UI).",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("4. Frontend Changes (incl. laxman-dev merge)", styles["h1"]))
    story.append(Paragraph("4.1 Authentication UI (Phase 1 — Frontend)", styles["h2"]))
    for line in [
        "Login page (/login) with branded UI.",
        "AuthContext + sessionStorage token storage (auth-storage.ts).",
        "Axios Bearer interceptor on all API calls (api/client.ts).",
        "ProtectedRoute — redirects unauthenticated users to /login.",
        "Role-based route guards (ALL_ROLES, WRITE_ROLES, ADMIN_ROLES).",
        "Unauthorized page (/unauthorized) for missing roles.",
        "Change password page (/change-password) — UI placeholder; API not yet built.",
        "TopNav: logout button wired to POST /auth/logout.",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("4.2 Vibration Analysis — Chart Upgrade", styles["h2"]))
    for line in [
        "Charts migrated from Plotly to <b>ECharts</b> (EchartsDiagnosticChart.tsx).",
        "Per-plot option builders: waveform, orbit, FFT, envelope, trend.",
        "Frontend-generated time axis in milliseconds (waveform-time-axis.ts) — fixes CSV timestamp_ms batch IDs.",
        "Channel switcher ch0–ch7, plot type tabs, zoom/pan/dataZoom toolbar.",
        "Vibration Analysis route restored in sidebar after merge conflict.",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(PageBreak())

    # ── Page 3: DevOps, APIs, validation ─────────────────────────────────
    story.append(Paragraph("5. Docker & Deployment", styles["h1"]))
    story.append(
        table(
            [
                ["Service", "Port", "Notes"],
                ["postgres", "5433", "PostgreSQL 16, healthcheck"],
                ["pgadmin", "5050", "admin@vibration.com / admin2024"],
                ["backend", "8000", "alembic upgrade head on container start"],
                ["frontend", "4173", "nginx preview build (Docker target: preview)"],
            ],
            col_widths=[3.5 * cm, 2.5 * cm, 10 * cm],
        )
    )
    story.append(Spacer(1, 0.2 * cm))
    for line in [
        "backend/Dockerfile — Python 3.11, runs migrations then uvicorn.",
        "frontend/Dockerfile — multi-stage build with VITE_API_BASE_URL arg.",
        "frontend/nginx.conf — SPA routing for production preview.",
        "Volumes: postgres_data, pgadmin_data, uploads_data.",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("6. Updated API Reference (New Endpoints)", styles["h1"]))
    story.append(
        table(
            [
                ["Endpoint", "Method", "Purpose"],
                ["/api/v1/auth/login", "POST", "JSON login → access + refresh tokens"],
                ["/api/v1/auth/token", "POST", "OAuth2 form login (Swagger)"],
                ["/api/v1/auth/refresh", "POST", "Rotate access token"],
                ["/api/v1/auth/logout", "POST", "Revoke refresh token"],
                ["/api/v1/auth/me", "GET", "Current user profile + roles (protected)"],
                ["/api/v1/measurements/acquisition", "GET", "Edge config by device_id query"],
                ["/api/v1/measurements/acquisition/{device_id}", "GET", "Edge config by path"],
                ["/api/v1/measurements/uploads/{id}/plots", "GET", "Plots from DB cache (?channel=)"],
            ],
            col_widths=[6.2 * cm, 1.8 * cm, 8 * cm],
        )
    )

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("7. Validation Performed", styles["h1"]))
    for line in [
        "8-channel CSV snapshot (12,800 samples @ 25,600 Hz) uploaded and parsed.",
        "All 5 plots verified against raw data: time waveform, circular, FFT, envelope, trend.",
        "plot_results table populated (5 plots × 8 channels = 40 rows per upload).",
        "Login flow tested via Swagger and React UI.",
        "laxman-dev merged into vaibhavi; pushed to GitHub (commit d5d1d7b).",
    ]:
        story.append(Paragraph(f"• {line}", styles["bullet"]))

    story.append(Paragraph("8. Known Issues & Workarounds", styles["h1"]))
    story.append(
        table(
            [
                ["Issue", "Workaround / Next step"],
                [
                    "active_channel=7 in plot config shows empty plots for channels without data",
                    "Select ch0–ch3 after upload; reset active_channel in config",
                ],
                [
                    "Change password API not implemented",
                    "must_change_password cleared in DB; build API in Phase 7",
                ],
                [
                    "Equipment/measurement APIs still open (no JWT required)",
                    "Phase 2 RBAC middleware",
                ],
                [
                    "FFT dominant label shows 0 Hz (DC spike)",
                    "Expected with DC offset; improve label to skip DC",
                ],
                [
                    "Accidental sss file from merge",
                    "Remove with git rm sss",
                ],
            ],
            col_widths=[6.5 * cm, 9.5 * cm],
        )
    )

    story.append(PageBreak())

    # ── Page 4: Roadmap ───────────────────────────────────────────────────
    story.append(Paragraph("9. What Is Still Planned", styles["h1"]))
    story.append(
        table(
            [
                ["Phase", "Scope", "Status"],
                ["Phase 2", "RBAC, user_plants, protect all APIs", "Not started"],
                ["Phase 3–5", "Admin panel, user CRUD, audit, API keys", "Not started"],
                ["Phase 7", "Change password API + wire ChangePassword page", "Not started"],
                ["Edge", "UDP script auto-upload using acquisition config", "Config API ready"],
                ["Dashboard", "Live analytics, alarms, KPIs", "Placeholder"],
            ],
            col_widths=[2.5 * cm, 8.5 * cm, 5 * cm],
        )
    )

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("10. Git Commit Timeline (Since Day 0–1)", styles["h1"]))
    story.append(
        table(
            [
                ["Commit", "Summary"],
                ["5a540e5", "Initial project upload"],
                ["6c47a45 / fbb3365", "Backend + frontend baseline"],
                ["a0985fb / bd27e4d", "Vibration analysis page + plots"],
                ["83b2e55", "Backend auth and database (migration 004)"],
                ["0a4c2c0", "JWT changes"],
                ["e9ef646", "Login page (laxman-dev)"],
                ["d975de6", "Fix upload config + restore analysis in sidebar"],
                ["6cae33e", "Store computed plot results in PostgreSQL"],
                ["d5d1d7b", "Merge laxman-dev into vaibhavi"],
            ],
            col_widths=[3 * cm, 13 * cm],
        )
    )

    story.append(Spacer(1, 0.5 * cm))
    story.append(hr())
    story.append(
        Paragraph(
            "<b>How to regenerate this document:</b><br/>"
            "<font face='Courier'>python scripts/generate_progress_update_pdf.py</font><br/><br/>"
            "Repository: github.com/laxmandhotre0045-sketch/VibrationMonitoring · Branch: vaibhavi",
            styles["small"],
        )
    )

    doc.build(story)
    print(f"Created: {OUTPUT}")


if __name__ == "__main__":
    main()
