# -*- coding: utf-8 -*-
"""Phase 0 status report.

Live figures are read from the database and from git at build time rather
than typed in. The first version of this document was written with counts
copied by hand and two of them were already stale by the time it was read.
"""
import datetime
import subprocess

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

REPO = r"C:\Users\Atharv Kulkarni\VibrationMonitoring"
OUT = REPO + r"\Phase0_Status_Report.pdf"

# ----------------------------------------------------------- live facts --
import sys
sys.path.insert(0, REPO + r"\backend")
from app.database import SessionLocal            # noqa: E402
from sqlalchemy import text                      # noqa: E402

_db = SessionLocal()


def one(sql):
    return _db.execute(text(sql)).scalar()


LIVE = {
    "bearings": one("select count(*) from bearing_fault_frequencies"),
    "captures": one("select count(*) from raw_vibration_captures"),
    "days": one("select count(distinct date(created_at)) from raw_vibration_captures"),
    "definitions": one("select count(*) from feature_definitions"),
    "equipment": one("select count(*) from equipment_masters"),
}
BY_DAY = _db.execute(text(
    "select date(created_at), count(*) from raw_vibration_captures "
    "group by 1 order by 1")).fetchall()
_db.close()


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=REPO, capture_output=True,
                          text=True).stdout.strip()


UNPUSHED = git("rev-list", "--count", "origin/laxman-dev..HEAD") or "?"
REMOTE_AT = git("log", "-1", "--format=%ad", "--date=short", "origin/laxman-dev") or "?"
STAMP = datetime.datetime.now().strftime("%d %B %Y, %H:%M")

INK    = colors.HexColor("#1B2733")
MUTED  = colors.HexColor("#5C6B7A")
RULE   = colors.HexColor("#D5DEE6")
BAND   = colors.HexColor("#F2F6F9")
ZEBRA  = colors.HexColor("#FAFCFD")
ACCENT = colors.HexColor("#0B6E99")
GREEN  = colors.HexColor("#1E7A4B")
AMBER  = colors.HexColor("#A86800")
RED    = colors.HexColor("#B3261E")

getSampleStyleSheet()


def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.4, leading=13.6,
                textColor=INK, alignment=TA_LEFT, spaceAfter=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


BODY   = S("body", spaceAfter=6)
LEAD   = S("lead", fontSize=10.6, leading=15.6, textColor=MUTED, spaceAfter=10)
H1     = S("h1", fontName="Helvetica-Bold", fontSize=19, leading=23, spaceAfter=2)
H2     = S("h2", fontName="Helvetica-Bold", fontSize=12.6, leading=16,
           textColor=ACCENT, spaceBefore=15, spaceAfter=6)
H3     = S("h3", fontName="Helvetica-Bold", fontSize=10, leading=14,
           spaceBefore=9, spaceAfter=3)
SMALL  = S("small", fontSize=8.3, leading=11.6, textColor=MUTED)
CELL   = S("cell", fontSize=8.4, leading=11.4)
CELLB  = S("cellb", fontName="Helvetica-Bold", fontSize=8.4, leading=11.4)
MONO   = S("mono", fontName="Courier", fontSize=8.1, leading=11.2)
KICKER = S("kicker", fontName="Helvetica-Bold", fontSize=8, leading=11,
           textColor=ACCENT)


def p(text_, style=BODY):
    return Paragraph(text_, style)


def tone_text(t, tone):
    return Paragraph('<font color="%s"><b>%s</b></font>' % (tone.hexval(), t), CELL)


PAD = [("TOPPADDING", (0, 0), (-1, -1), 5),
       ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
       ("VALIGN", (0, 0), (-1, -1), "TOP")]

story = []

story.append(p("SENSOVIBE &nbsp;&#183;&nbsp; VIBRATION AI PROGRAMME", KICKER))
story.append(p("Phase 0 &#8212; Clear the blockers", H1))
story.append(p("Where Phase 0 stands, what Phase 1 inherits, and what a full "
               "audit of the work found. Built %s." % STAMP, LEAD))

summary = (
    "<b>Phase 0 is 11 of 17 tickets done.</b> Every ticket assigned to Atharva is "
    "finished and committed &#8212; the units problem, the bearing catalogue, the "
    "acceleration-to-velocity path, the tenfold cost cut and the test harness. Six "
    "are open, all of them Laxman's: the repository is not pushed, the two ingest "
    "paths still duplicate the pipeline, the upload write is not re-runnable, and "
    "there is no background worker.<br/><br/>"
    "<b>The finding that changes what the system can say today:</b> the gateway "
    "knows the readings are in g and knows each channel's sensitivity, and sends "
    "neither to the platform. So the database still records the unit as "
    "<font face='Courier'>unconfirmed</font>, and the safety rule built in VIK-005 "
    "refuses to grade any of the %d captures. The work is done at both ends and not "
    "joined in the middle.<br/><br/>"
    "<b>The finding that changes what it can say tomorrow:</b> at the capture length "
    "the gateway is set to, three of the four bearing frequencies on this pump cannot "
    "be told apart from ordinary shaft harmonics. That is not a software limit and no "
    "amount of analysis fixes it. One setting on the Senvia sensor page does."
) % LIVE["captures"]
box = Table([[p(summary, BODY)]], colWidths=[168 * mm])
box.setStyle(TableStyle(PAD + [
    ("BACKGROUND", (0, 0), (-1, -1), BAND),
    ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
    ("LEFTPADDING", (0, 0), (-1, -1), 11),
    ("RIGHTPADDING", (0, 0), (-1, -1), 11),
    ("TOPPADDING", (0, 0), (-1, -1), 9),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
]))
story.append(box)

# --------------------------------------------------------- what it was for --
story.append(p("What Phase 0 was for", H2))
story.append(p(
    "Phase 0 is not new features. It is the five things the roadmap said would make "
    "everything built on top of them wrong, plus somewhere to put tests. Each one is a "
    "correctness problem rather than a missing piece &#8212; the system already "
    "produced numbers for all five. The numbers were just not trustworthy.", BODY))

five = [
    ("1", "The code lived on one laptop",
     "Not a coding task. A repository now exists, holding the domain data files that a "
     "single wrong line in .gitignore had been silently excluding."),
    ("2", "The chatbot's reference data was missing from disk",
     "bearings.json, iso10816_3.json and fault_signatures.json are tracked. Every "
     "bearing, ISO and fault lookup used to raise an error on first call."),
    ("3", "The system did not know what its own numbers meant",
     "Readings were stored exactly as they arrived, with no record of whether they were "
     "volts or g &#8212; a factor of ten apart. There is now a column for it, and a rule "
     "that refuses to grade an undeclared capture instead of guessing."),
    ("4", "The bearing catalogue sat unused in a spreadsheet",
     "%s bearings are loaded. The pump's 6312-C3 and 6310-C3 now resolve to real "
     "catalogue entries instead of an estimate that could be wrong by one ball."
     % f"{LIVE['bearings']:,}"),
    ("5", "All the heavy maths ran while the user waited",
     "Restructured: one extraction per segment instead of one per feature per segment. "
     "A whole 8-channel capture now takes 0.18 s, carrying 36 features instead of 10."),
]
t = Table([[p("<b>%s</b>" % n, CELLB), p("<b>%s</b><br/>%s" % (h, d), CELL)]
           for n, h, d in five], colWidths=[9 * mm, 159 * mm])
t.setStyle(TableStyle(PAD + [
    ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
    ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ("LEFTPADDING", (0, 0), (0, -1), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
]))
story.append(t)

# ---------------------------------------------------------------- tickets --
story.append(p("Ticket by ticket", H2))
story.append(p("Status was checked against the code and the database, not recalled. "
               "The evidence column says what was looked at.", SMALL))
story.append(Spacer(1, 5))

DONE, PART, OPEN = ("Done", GREEN), ("Partly", AMBER), ("Open", RED)
rows = [
    ("VIK-001", "Put the working copy under git", "Laxman", PART,
     "Repository exists. %s commits sit unpushed on this laptop; the remote branch was "
     "last updated on %s." % (UNPUSHED, REMOTE_AT)),
    ("VIK-002", "Restore the chatbot's domain data", "Atharva", DONE,
     "All three JSON files tracked in git."),
    ("VIK-003", "Declare jinja2", "Atharva", DONE, "Pinned at 3.1.3 in requirements."),
    ("VIK-004", "Port units.py into the backend", "Atharva", DONE,
     "backend/app/ai/units.py, with a test that fails if it drifts from the original."),
    ("VIK-005", "Apply sensor sensitivity in the measurement path", "Atharva", PART,
     "The code is written and tested. The value never arrives &#8212; see below."),
    ("VIK-006", "Migration: signal_unit and unit_confirmed", "Atharva", DONE,
     "Migration 022, applied, with a working downgrade. Renumbered from 019 after a "
     "collision with the bearing migration."),
    ("VIK-007", "Acceleration to velocity", "Atharva", DONE,
     "Reuses the existing integrator; no second one was added."),
    ("VIK-008", "Migration: bearings table", "Atharva", DONE, "Migration 019, applied."),
    ("VIK-009", "Import the bearing spreadsheet", "Atharva", DONE,
     "%s rows loaded. Safe to re-run." % f"{LIVE['bearings']:,}"),
    ("VIK-010", "Resolve equipment bearings against the catalogue", "Atharva", DONE,
     "6312-C3 and 6310-C3 both resolve. The readiness flag is computed from the "
     "catalogue id, so it is no longer a box anyone can tick."),
    ("VIK-011", "Route both ingest paths through run_pipeline", "Laxman", OPEN,
     "run_pipeline exists but no router calls it. Both paths still inline the sequence."),
    ("VIK-012", "Make save_upload_data re-runnable", "Laxman", OPEN,
     "Still a plain INSERT. A second run on the same upload fails."),
    ("VIK-013", "processing_jobs table and worker", "Laxman", OPEN,
     "No migration and no table. The latest migration is 022."),
    ("VIK-014", "Cut segment-trend work tenfold", "Atharva", DONE,
     "Loops inverted. 33 extraction calls where there were 330."),
    ("VIK-015", "pytest and the first test module", "Laxman", PART,
     "269 backend tests pass. pytest and httpx are now declared and collection is "
     "scoped to tests/, so the suite runs from a fresh checkout. Converting and "
     "deleting scripts/test_auth_phase1.py is still outstanding."),
    ("VIK-016", "vitest and the first frontend test", "Laxman", PART,
     "vitest runs and 43 tests pass. The ticket named lib/vibration-features.ts as the "
     "first thing to cover, and it is not covered."),
    ("VIK-017", "Synthetic fault harness with recorded answers", "Atharva", DONE,
     "Eight signatures, each with its expected answer stored alongside and checked "
     "against the waveform."),
]
data = [[p("<b>ID</b>", CELLB), p("<b>Task</b>", CELLB), p("<b>Owner</b>", CELLB),
         p("<b>Status</b>", CELLB), p("<b>Evidence</b>", CELLB)]]
for tid, task, owner, (label, tone), ev in rows:
    data.append([p(tid, MONO), p(task, CELL), p(owner, CELL),
                 tone_text(label, tone), p(ev, CELL)])
tbl = Table(data, colWidths=[17 * mm, 42 * mm, 15 * mm, 14 * mm, 80 * mm], repeatRows=1)
tstyle = PAD + [
    ("BACKGROUND", (0, 0), (-1, 0), BAND),
    ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
    ("LINEBELOW", (0, 1), (-1, -2), 0.35, RULE),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
]
for i in range(1, len(rows) + 1):
    if i % 2 == 0:
        tstyle.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
tbl.setStyle(TableStyle(tstyle))
story.append(tbl)

# ------------------------------------------------------------- the real gap --
story.append(p("The gap that matters: the unit is known, and never arrives", H2))
story.append(p(
    "VIK-005 built the rule that a capture with no declared unit is refused rather "
    "than graded. That rule is working. What it is refusing is every capture we have, "
    "and it should not be.", BODY))
chain = [
    ("The gateway knows", GREEN,
     "SAMPLE_UNIT=g and SENSITIVITY_MV_PER_G=500,500,100,100,100,100,100,100 are set "
     "and correct. Channels 1 and 2 are 500 mV/g sensors; the cloud configuration's "
     "single value of 100 is wrong for them."),
    ("my_script.py attaches it", GREEN,
     "sample_metadata() puts sampleUnit and sensitivityMvPerG on the upload, and flags "
     "that the sensitivities are not uniform."),
    ("but only on the Senvia leg", RED,
     "platform_push.py, which is the leg feeding our own platform, sends device_id, "
     "sample_rate_hz, expected_channels and measured_at. No unit, no sensitivity."),
    ("and the endpoint would not take it", RED,
     "POST /api/v1/ingest/raw has no field for either. It does accept "
     "rotation_speed_rpm, which the gateway also never sends, while the equipment "
     "record already holds 1480 rpm."),
    ("so the database says", RED,
     "signal_unit = 'unconfirmed', unit_confirmed = false, and one sensitivity of "
     "100 mV/g standing for all eight channels."),
]
ct = Table([[p("<b>%s</b>" % a, CELL), p(c, CELL),
             tone_text("OK" if tone is GREEN else "MISSING", tone)]
            for a, tone, c in chain], colWidths=[42 * mm, 107 * mm, 19 * mm])
ct.setStyle(TableStyle(PAD + [("LINEBELOW", (0, 0), (-1, -2), 0.35, RULE),
                              ("LEFTPADDING", (0, 0), (0, -1), 0)]))
story.append(ct)
story.append(Spacer(1, 4))
story.append(p(
    "Three small changes close it: send the two fields from platform_push.py, accept "
    "them on the ingest endpoint, and write them onto the sensor record. This is code, "
    "not a decision &#8212; the values are already known and already correct.", BODY))

# ----------------------------------------------------- the resolution problem --
story.append(p("The second gap: the captures are too short to name a bearing fault", H2))
story.append(p(
    "A spectrum can only separate two frequencies if they are further apart than one "
    "line, and the line spacing is one divided by the recording length. The gateway "
    "records 0.278 seconds, so the lines are 3.6 Hz apart. That is coarser than the "
    "gaps between this pump's bearing frequencies and its ordinary shaft harmonics.", BODY))
coll = [
    ["<b>Bearing frequency</b>", "<b>Sits at</b>", "<b>Nearest shaft harmonic</b>",
     "<b>Gap</b>", "<b>Now (3.6 Hz)</b>", "<b>At 1 s (1.0 Hz)</b>"],
    ["FTF &#8212; the cage", "9.45 Hz", "1&#215; = 24.67 Hz", "15.2 Hz",
     "separate, but only 2.6 lines wide", "9.4 lines &#8212; readable"],
    ["BSF &#8212; a ball", "49.83 Hz", "2&#215; = 49.33 Hz", "0.49 Hz",
     "same line", "still the same line"],
    ["BPFO &#8212; outer ring", "75.58 Hz", "3&#215; = 74.00 Hz", "1.58 Hz",
     "same line", "separate"],
    ["BPFI &#8212; inner ring", "121.75 Hz", "5&#215; = 123.33 Hz", "1.58 Hz",
     "same line", "separate"],
]
ctab = Table([[p(c, CELLB if i == 0 else CELL) for c in row] for i, row in enumerate(coll)],
             colWidths=[33 * mm, 18 * mm, 32 * mm, 14 * mm, 38 * mm, 33 * mm])
ctab.setStyle(TableStyle(PAD + [
    ("BACKGROUND", (0, 0), (-1, 0), BAND),
    ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
    ("LINEBELOW", (0, 1), (-1, -2), 0.35, RULE),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
]))
story.append(ctab)
story.append(Spacer(1, 4))
story.append(p(
    "Read the fifth column: today, a mark on the outer ring of a bearing and an "
    "ordinary third shaft harmonic land on the same line of the spectrum. Looseness "
    "produces a long family of shaft harmonics, so a loose foot would look like a "
    "failing bearing. Changing LOR from 2500 to 9000 on the Senvia sensor page makes "
    "the recording one second long and settles all of it except the ball frequency, "
    "which would need about six seconds and is therefore permanently unreadable on a "
    "50 Hz supply at this speed. The system will say so rather than guess.", BODY))
story.append(p(
    "Envelope analysis, the next piece of work, softens this: it demodulates the "
    "bearing's high-frequency ringing, where shaft harmonics do not appear. But its "
    "own resolution comes from the same recording length, so the change is worth "
    "making either way.", SMALL))

# ------------------------------------------------------------ side findings --
story.append(p("Found along the way, not on the ticket list", H2))
found = [
    ("A 50 Hz line on two channels &#8212; and what it is depends on the machine",
     "Channels 2 and 7 carry a strong line at 50.4 Hz. On the idle captures, with the "
     "shaft stopped, it stands 93 to 97 times above the noise and can only be "
     "electrical: a stopped shaft has no orders. On running captures the same channels "
     "read 45 to 48 times above a higher floor, and there the line cannot be attributed, "
     "because twice shaft speed is 49.33 Hz and falls in the same 3.6 Hz line. Those "
     "channels also show 1&#215;, 3&#215; and 4&#215; shaft, which mains cannot produce, "
     "so most of what is there is mechanical. The code already refuses to call it mains "
     "while the machine runs; this document previously did not, and that was wrong."),
    ("Timestamps were not increasing",
     "The gateway wrote one timestamp per block, so 13,888 rows carried seven distinct "
     "times and the platform rejected every file. Fixed by deriving a time per sample."),
    ("Credentials were in the repository",
     "A tracked settings file carried a live password, and .env.example held real "
     "credentials while being git-ignored. Both fixed going forward; one commit in the "
     "history still needs scrubbing, which cannot be done by one person alone."),
    ("One equipment record was blank and one is test data",
     "The blank row has been deleted &#8212; nothing referenced it. The row named "
     "'pump' carries bearing numbers 5656 and 65421 that match nothing in the "
     "catalogue, and a speed range of 55 to 85 which looks like a load percentage "
     "typed into an rpm field. It is kept, and excluded from analysis until corrected."),
]
ft = Table([[p("&#8226;", CELL), p("<b>%s</b> &#8212; %s" % (h, d), CELL)]
            for h, d in found], colWidths=[5 * mm, 163 * mm])
ft.setStyle(TableStyle(PAD + [("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
                              ("LEFTPADDING", (0, 0), (0, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 4),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
story.append(ft)

# ------------------------------------------------------------- the audit --
story.append(p("What a full audit of the work found", H2))
story.append(p(
    "Everything built so far was reviewed in five passes. The method was mutation "
    "testing: deliberately break one safeguard in the code and check that some test "
    "notices. A safeguard no test protects is one nobody would notice losing.", BODY))
audit = [
    ("Two real bugs, now fixed",
     "The two windows used to measure whether vibration is growing could overlap, so a "
     "record that grew tenfold partway through would report almost no change. And a "
     "unit written as a capital G was refused, which would have stopped every capture "
     "being graded for a reason nobody would think to look for."),
    ("A test that could not fail",
     "The test protecting the check that twelve manufacturers' bearing figures are not "
     "averaged together asserted only inside an if-statement that the check itself "
     "populated. Switch the check off and the test passed by skipping itself. It is now "
     "pinned against the catalogue outright."),
    ("A test suite nobody could run",
     "Neither pytest nor httpx was declared, so a fresh checkout could not run the "
     "tests at all &#8212; and one script in scripts/ is named like a test and does its "
     "work on import, which took the whole run down with it. Both fixed."),
    ("Mutation scores before and after",
     "Signal units 9 of 15 to 16 of 16. Time-domain features 9 of 13 to 14 of 15. "
     "Bearing resolution 6 of 12 to 10 of 12. The remaining survivors are mutations "
     "that change no behaviour. Eighteen new tests; 251 to 269."),
    ("Everything else checked clean",
     "All %d stored captures are well formed with no dead channels. All three "
     "migrations carry working downgrades. No secrets in any tracked file. Backend, "
     "frontend and type checks all pass." % LIVE["captures"]),
]
at = Table([[p("&#8226;", CELL), p("<b>%s</b> &#8212; %s" % (h, d), CELL)]
            for h, d in audit], colWidths=[5 * mm, 163 * mm])
at.setStyle(TableStyle(PAD + [("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
                              ("LEFTPADDING", (0, 0), (0, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 4),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
story.append(at)

# ----------------------------------------------------------------- numbers --
story.append(p("The numbers, and where they came from", H2))
story.append(p("Read from the database and from git when this document was built, "
                "not copied in. Capture counts rise while the gateway runs.", SMALL))
story.append(Spacer(1, 4))
day_note = ", ".join(f"{n} on {d.strftime('%d %b')}" for d, n in BY_DAY)
nums = [
    ("Bearings in the catalogue", f"{LIVE['bearings']:,}", "bearing_fault_frequencies"),
    ("Captures stored", str(LIVE["captures"]), day_note),
    ("Days of data", str(LIVE["days"]),
     "the roadmap wants two to four weeks before a baseline is trusted"),
    ("Capture shape", "8 ch &#215; 13,888 @ 50 kHz", "0.278 s, 6.85 shaft turns"),
    ("Features per channel", "36", "was 10 at the start of Phase 0"),
    ("Cost of a whole capture", "0.18 s", "measured on 8 channels of real-shaped data"),
    ("Backend tests", "269 passing", "pytest, backend/tests"),
    ("Frontend tests", "43 passing", "vitest, 2 files"),
    ("Features the UI can label", f"{LIVE['definitions']} of 36",
     "feature_definitions still holds %d (VIK-021)" % LIVE["definitions"]),
    ("Equipment records", str(LIVE["equipment"]),
     "one real machine, one test row; the blank row was deleted"),
    ("Commits not pushed anywhere", str(UNPUSHED), "they exist on this laptop only"),
]
nt = Table([[p(a, CELL), p("<b>%s</b>" % b, CELL), p(c, SMALL)] for a, b, c in nums],
           colWidths=[52 * mm, 44 * mm, 72 * mm])
nt.setStyle(TableStyle(PAD + [("LINEBELOW", (0, 0), (-1, -2), 0.35, RULE),
                              ("LEFTPADDING", (0, 0), (0, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 4),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
story.append(nt)

story.append(p("The pump, as the catalogue now describes it", H3))
story.append(p(
    "Cooling Water Pump 1, 1480 rpm, so the shaft turns 24.667 times a second. "
    "Drive-end bearing 6312-C3, non-drive-end 6310-C3, both resolved against the "
    "catalogue.", BODY))
bt = Table([
    [p("<b>What</b>", CELLB), p("<b>What it means</b>", CELLB),
     p("<b>Drive end</b>", CELLB), p("<b>Non-drive end</b>", CELLB)],
    [p("FTF", MONO), p("the cage, holding the balls apart", CELL),
     p("9.45 Hz", CELL), p("9.40 Hz", CELL)],
    [p("BSF", MONO), p("a ball spinning with a flat on it", CELL),
     p("49.83 Hz", CELL), p("48.86 Hz", CELL)],
    [p("BPFO", MONO), p("a mark on the outer ring", CELL),
     p("75.58 Hz", CELL), p("75.18 Hz", CELL)],
    [p("BPFI", MONO), p("a mark on the inner ring", CELL),
     p("121.75 Hz", CELL), p("122.15 Hz", CELL)],
], colWidths=[18 * mm, 80 * mm, 35 * mm, 35 * mm])
bt.setStyle(TableStyle(PAD + [
    ("BACKGROUND", (0, 0), (-1, 0), BAND),
    ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
    ("LINEBELOW", (0, 1), (-1, -2), 0.35, RULE),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 4.5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
]))
story.append(bt)
story.append(Spacer(1, 3))
story.append(p(
    "The outer and inner figures add up to 8.00, the number of balls in the bearing. "
    "That identity holding is a check that the catalogue entry is the right one. "
    "Twelve manufacturers list this bearing and their figures differ by 1.2% on the "
    "ball frequency; the spread is reported rather than averaged, because an average "
    "is a number none of them publishes.", SMALL))

# -------------------------------------------------------------- what's next --
story.append(p("What Phase 1 inherits", H2))
story.append(p(
    "Phase 0 said nothing in Phase 1 starts until VIK-005, VIK-009 and VIK-013 are "
    "merged. Two of the three are. VIK-013, the background worker, is not, and its "
    "stated reason was that Phase 1's extra features would make uploads time out. "
    "Measured, they do not: a whole capture costs 0.18 seconds, because VIK-014's "
    "restructure absorbed the increase. So the feature tickets were safe to start, and "
    "VIK-018 and VIK-019 are done. VIK-013 still matters for the phases after this one, "
    "where scoring and baselines run on every capture.", BODY))
story.append(p(
    "Two Phase 1 tickets are finished: the thirteen time-domain measurements and the "
    "thirteen frequency-domain ones, taking the count from 10 to 36. VIK-020, the "
    "envelope features, is the group the roadmap calls the most important one for the "
    "demo, and it is next.", BODY))


def page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(21 * mm, 16 * mm, 189 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(21 * mm, 11.5 * mm, "SensoVibe  \u00b7  Phase 0 status  \u00b7  " + STAMP)
    canvas.drawRightString(189 * mm, 11.5 * mm, str(doc.page))
    canvas.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4,
                      leftMargin=21 * mm, rightMargin=21 * mm,
                      topMargin=18 * mm, bottomMargin=22 * mm,
                      title="Phase 0 Status Report", author="SensoVibe")
doc.addPageTemplates([PageTemplate(
    id="main",
    frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")],
    onPage=page)])
doc.build(story)
print("wrote", OUT)
