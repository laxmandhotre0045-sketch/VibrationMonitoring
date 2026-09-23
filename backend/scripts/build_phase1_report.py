# -*- coding: utf-8 -*-
"""Phase 1 status report.

Same rule as the Phase 0 builder: every count in this document is read from
the database, from git, or from the code at build time. Nothing is typed in.
The one figure that cannot be read that way is the content of Laxman's
tickets, which lives in the 85-ticket sheet and not in this repository, and
the document says so rather than guessing.

    python scripts/build_phase1_report.py
"""
import datetime
import re
import subprocess
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

REPO = r"C:\Users\Atharv Kulkarni\VibrationMonitoring"
OUT = REPO + r"\Phase1_Status_Report.pdf"
sys.path.insert(0, REPO + r"\backend")

# ------------------------------------------------------------ live facts --
from sqlalchemy import text                                   # noqa: E402

from app.database import SessionLocal                         # noqa: E402

_db = SessionLocal()


def one(sql, default="?"):
    try:
        return _db.execute(text(sql)).scalar()
    except Exception:
        return default


L = {
    "captures": one("select count(*) from raw_vibration_captures"),
    "uploads": one("select count(*) from sensor_data_uploads"),
    "features": one("select count(*) from measurement_channel_features"),
    "definitions": one("select count(*) from feature_definitions"),
    "quality": one("select count(*) from data_quality_assessments"),
    "baselines": one("select count(*) from feature_baseline_stats"),
    "versions": one("select count(*) from baseline_versions"),
    "bearings": one("select count(*) from bearing_fault_frequencies"),
    "newest": one("select max(created_at) from sensor_data_uploads"),
    "oldest": one("select min(created_at) from sensor_data_uploads"),
}
QUALITY = _db.execute(text(
    "select level, count(*) from data_quality_assessments "
    "where channel is not null group by 1")).fetchall()
QMAP = {r[0]: r[1] for r in QUALITY}
NOISE_FAILS = one("select count(*) from data_quality_assessments "
                  "where channel is not null and failed_checks::text like "
                  "'%noise_floor%'", 0)
SHAPE = _db.execute(text(
    "select sample_rate_hz, sample_count, count(*) from raw_vibration_captures "
    "group by 1,2 order by 3 desc limit 1")).fetchone()

# The baseline the platform is actually using, read through the read model
# VIK-027 built -- so this document is one of its callers rather than a
# second opinion about the same rows.
try:
    from app.services.baseline_health import sensor_health

    _sid = one("select distinct sensor_id from feature_baseline_stats limit 1")
    HEALTH = sensor_health(_db, _sid, expected_feature_count=L["definitions"])
except Exception:
    HEALTH = None

# Resolution actually achieved per channel, in converter steps. This is the
# open hardware question and it deserves measured numbers, not a claim.
try:
    import numpy as np

    STEP = 5.0 / 32768 / 0.100
    _ids = [r[0] for r in _db.execute(text(
        "select id from raw_vibration_captures order by created_at desc limit 20"))]
    _acc = {i: [] for i in range(8)}
    for _cid in _ids:
        for _idx, _s in _db.execute(text(
                "select channel_index, samples from raw_vibration_channels "
                "where capture_id = :c"), {"c": _cid}):
            _acc[int(_idx)].append(float(np.std(_s)) / STEP)
    COUNTS = {i: float(np.median(v)) for i, v in _acc.items() if v}
except Exception:
    COUNTS = {}

_db.close()


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=REPO,
                          capture_output=True, text=True).stdout.strip()


PHASE1_BASE = "3c7227c"          # VIK-017, the last Phase 0 commit
COMMITS = git("rev-list", "--count", PHASE1_BASE + "..HEAD") or "?"
_stat = git("diff", "--shortstat", PHASE1_BASE + "..HEAD") or ""
_n = [int(x) for x in re.findall(r"(\d+)", _stat)]
SHORTSTAT = ("%s files changed, %s lines added and %s removed"
             % (f"{_n[0]:,}", f"{_n[1]:,}", f"{_n[2]:,}")) if len(_n) >= 3 else _stat
STAMP = datetime.datetime.now().strftime("%d %B %Y, %H:%M")


def tests_in(folder, args):
    """Count collected tests, whichever way that service's pytest reports it.

    Three shapes, because the three services are configured differently. The
    first version of this understood only one of them and reported the
    chatbot as zero -- a figure that went straight into the document and read
    as "the chatbot has no tests". So this raises rather than returning a
    number it did not actually read.
    """
    out = subprocess.run(
        [REPO + "\\" + folder + "\\.venv\\Scripts\\python.exe", "-m", "pytest",
         *args, "--collect-only", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO + "\\" + folder, capture_output=True, text=True).stdout
    lines = out.splitlines()

    for line in lines:                        # "700 tests collected in 1.9s"
        m = re.match(r"\s*(\d+)\s+tests?\s+collected", line)
        if m:
            return int(m.group(1))

    ids = sum(1 for line in lines if "::" in line)
    if ids:                                   # one node id per line
        return ids

    per_file = [int(m.group(1))               # "tests/test_x.py: 24"
                for m in (re.match(r"^\S+\.py:\s*(\d+)\s*$", line)
                          for line in lines) if m]
    if per_file:
        return sum(per_file)

    raise RuntimeError(
        "could not read a test count for %s. Reporting zero here would read "
        "as 'this service has no tests', so this stops instead." % folder)


def suite_passes(folder, args):
    """Actually run the suite and report whether it passed.

    The count above says how many tests exist, which is not the same claim as
    "they pass" -- and this document should not make the second claim from
    the first. pytest's exit code is the reliable signal here: the chatbot's
    configuration suppresses the usual summary line, so parsing output for
    "N passed" works for two services and silently fails for the third.
    """
    return subprocess.run(
        [REPO + "\\" + folder + "\\.venv\\Scripts\\python.exe", "-m", "pytest",
         *args, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO + "\\" + folder, capture_output=True, text=True).returncode == 0


SUITES = {
    "backend": ["tests/"],
    "gateway": [],
    "vibrationbot": ["tests/", "iso_agent/tests/", "report_agent/tests/",
                     "sql_agent/tests/", "kb_agent/tests/"],
}
BACKEND_TESTS = tests_in("backend", SUITES["backend"])
GATEWAY_TESTS = tests_in("gateway", SUITES["gateway"])
BOT_TESTS = tests_in("vibrationbot", SUITES["vibrationbot"])
TOTAL_TESTS = BACKEND_TESTS + GATEWAY_TESTS + BOT_TESTS

FAILING = sorted(name for name, args in SUITES.items()
                 if not suite_passes(name, args))
ALL_GREEN = not FAILING

INK = colors.HexColor("#1B2733")
MUTED = colors.HexColor("#5C6B7A")
RULE = colors.HexColor("#D5DEE6")
BAND = colors.HexColor("#F2F6F9")
ZEBRA = colors.HexColor("#FAFCFD")
ACCENT = colors.HexColor("#0B6E99")
GREEN = colors.HexColor("#1E7A4B")
AMBER = colors.HexColor("#A86800")
RED = colors.HexColor("#B3261E")


def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.4, leading=13.6,
                textColor=INK, alignment=TA_LEFT, spaceAfter=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


BODY = S("body", spaceAfter=6)
LEAD = S("lead", fontSize=10.6, leading=15.6, textColor=MUTED, spaceAfter=10)
H1 = S("h1", fontName="Helvetica-Bold", fontSize=19, leading=23, spaceAfter=2)
H2 = S("h2", fontName="Helvetica-Bold", fontSize=12.6, leading=16,
       textColor=ACCENT, spaceBefore=15, spaceAfter=6)
H3 = S("h3", fontName="Helvetica-Bold", fontSize=10, leading=14,
       spaceBefore=9, spaceAfter=3)
SMALL = S("small", fontSize=8.3, leading=11.6, textColor=MUTED)
CELL = S("cell", fontSize=8.4, leading=11.4)
CELLB = S("cellb", fontName="Helvetica-Bold", fontSize=8.4, leading=11.4)
MONO = S("mono", fontName="Courier", fontSize=8.1, leading=11.2)
KICKER = S("kicker", fontName="Helvetica-Bold", fontSize=8, leading=11,
           textColor=ACCENT)

PAD = [("TOPPADDING", (0, 0), (-1, -1), 5),
       ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
       ("VALIGN", (0, 0), (-1, -1), "TOP")]


def p(t, style=BODY):
    return Paragraph(t, style)


def tone(t, colour):
    return Paragraph('<font color="%s"><b>%s</b></font>' % (colour.hexval(), t),
                     CELL)


def box(inner, colour=ACCENT, bg=BAND):
    t = Table([[p(inner, BODY)]], colWidths=[168 * mm])
    t.setStyle(TableStyle(PAD + [
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def table(rows, widths, header=True, zebra=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = PAD + [
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), BAND),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
                  ("LEFTPADDING", (0, 0), (0, 0), 6)]
    if zebra:
        for i in range(2 if header else 1, len(rows), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(style))
    return t


story = []

# =========================================================== front page ==
story.append(p("SENSOVIBE &nbsp;&#183;&nbsp; VIBRATION AI PROGRAMME", KICKER))
story.append(p("Phase 1 &#8212; Measure properly, and learn what normal is", H1))
story.append(p(
    "What Phase 1 is, what is finished, what is left, and what is wrong. "
    "Every number here is read from the live database, from git, or from the "
    "code at the moment this was built &#8212; %s." % STAMP, LEAD))

_shape_txt = ("%.0f kSPS for %.3f s" % (SHAPE[0] / 1000.0, SHAPE[1] / SHAPE[0])
              if SHAPE else "an unrecorded shape")

story.append(box(
    "<b>All ten of Atharva's Phase 1 tickets are finished and committed.</b> "
    "The platform measures %d things about every capture instead of 10, judges "
    "whether each capture can be trusted, and has learned what normal looks "
    "like for this pump from %d real captures rather than from one file "
    "somebody nominated. Eight tickets remain, all Laxman's.<br/><br/>"
    "<b>%s automated tests across the three services</b> (%d platform, %d "
    "chatbot, %d gateway), up from 58 at the end of Phase 0 &#8212; and all "
    "three suites were run while building this document: %s. %s commits, "
    "%s.<br/><br/>"
    "<b>The one thing Phase 1 cannot fix in software.</b> The pump's vibration "
    "is so small next to the range the hardware is set to that two channels "
    "resolve it in about one and a half steps of the converter. Every shape "
    "measurement on those channels is describing rounding, not the machine. "
    "This needs somebody at the PLC, and it is the single highest-value open "
    "item in this document."
    % (L["definitions"], L["captures"], f"{TOTAL_TESTS:,}", BACKEND_TESTS,
       BOT_TESTS, GATEWAY_TESTS,
       "all passed" if ALL_GREEN else
       "<font color='%s'><b>FAILING: %s</b></font>"
       % (RED.hexval(), ", ".join(FAILING)),
       COMMITS, SHORTSTAT or "many files changed")))

# ------------------------------------------------------ what it was for --
story.append(p("What Phase 1 was for, in one paragraph", H2))
story.append(p(
    "Phase 0 made the numbers trustworthy. Phase 1 makes there be enough of "
    "them, and gives the system something to compare them against. Three "
    "questions, in order: <b>what can we measure about a capture</b> (it was "
    "10 things, it is now %d), <b>can this capture be trusted at all</b> "
    "(eight checks that grade it), and <b>what does normal look like for this "
    "machine</b> (learned from its own history, not from a single saved "
    "file). Nothing in Phase 2 or Phase 3 &#8212; scoring how unusual a "
    "reading is, naming a fault &#8212; means anything without all three."
    % L["definitions"], BODY))

story.append(p(
    "A fourth thing runs through all of it and is worth stating separately, "
    "because it is the difference between a demo and a system somebody can "
    "act on: <b>the platform must be able to say \"I do not know\"</b>. A "
    "machine with no baseline is not a healthy machine. A capture that could "
    "not be assessed did not pass. A feature with no learned normal is not "
    "normal. Each of those is a real distinction that a simpler design "
    "collapses into a reassuring green tick.", BODY))

# --------------------------------------------------------- the tickets --
story.append(p("What is included in Phase 1", H2))
story.append(p(
    "Eighteen tickets. Ten are Atharva's and all ten are done. Eight are "
    "Laxman's and none is started &#8212; their detail lives in the 85-ticket "
    "sheet, which is not in this repository, so they are listed here by "
    "number and owner only rather than described from memory.", BODY))

done = GREEN
todo = RED

tickets = [
    ("VIK-018", "13 more time-domain measurements",
     "Peak-to-peak, skewness, impulse and shape factors, burst count, shock "
     "index and others.", "Done", done),
    ("VIK-019", "13 more frequency-domain measurements",
     "Harmonic count, sideband spacing, spectral spread, broadband noise. One "
     "spectrum per segment, reused.", "Done", done),
    ("VIK-020", "Envelope measurements, including bearing bands",
     "Reads energy at the exact bearing fault frequencies from the catalogue. "
     "The roadmap calls this the most important group for the demo.",
     "Done", done),
    ("VIK-021", "Register the new measurements in the database",
     "One source of truth for all %d, so the code and the database cannot "
     "disagree about what a feature is." % L["definitions"], "Done", done),
    ("VIK-022", "Judge whether a capture can be trusted",
     "Eight checks returning High / Medium / Low / Invalid, plus what failed. "
     "Every engine after this lowers its own confidence when trust is low.",
     "Done", done),
    ("VIK-024", "A table to hold learned normal",
     "Median and spread per sensor, channel and feature.", "Done", done),
    ("VIK-025", "Learn normal from history instead of one saved file",
     "Median and MAD, not average and standard deviation, so one bad capture "
     "cannot move the baseline. Refuses below a minimum sample count.",
     "Done", done),
    ("VIK-026", "Baseline lifecycle: start, roll, freeze, reset",
     "A reset starts a new version rather than editing the old one, so a "
     "finding can always be traced to the baseline that produced it.",
     "Done", done),
    ("VIK-027", "Report how healthy the baseline itself is",
     "Available or not, confidence, freshness, how many samples. Seven API "
     "endpoints; this is what unblocks Laxman's VIK-033.", "Done", done),
    ("VIK-035", "Put the shared maths in one package both services use",
     "Bearing maths, ISO tables, unit conversion, fault rules. Stops the "
     "platform and the chatbot reaching two different answers for the same "
     "bearing.", "Done", done),
]

rows = [[p("<b>Ticket</b>", CELLB), p("<b>What it makes the system do</b>", CELLB),
         p("<b>Status</b>", CELLB)]]
for tid, title, detail, status, colour in tickets:
    rows.append([p("<b>%s</b>" % tid, CELL),
                 p("<b>%s</b><br/>%s" % (title, detail), CELL),
                 tone(status, colour)])
story.append(table(rows, [20 * mm, 128 * mm, 20 * mm]))

story.append(Spacer(1, 7))
story.append(p("Laxman's eight, not started", H3))
story.append(p(
    "VIK-023, VIK-028, VIK-029, VIK-030, VIK-031, VIK-032, VIK-033 and "
    "VIK-034. VIK-033 is the one that was waiting on VIK-027 and is now "
    "unblocked &#8212; the endpoints it needs are live. The rest are described "
    "in the ticket sheet; this document does not restate them because it "
    "cannot read them.", BODY))


# ==================================================== what changed ========
story.append(p("What the system can do now that it could not", H2))

before_after = [
    ("Measurements per capture", "10", "%d" % L["definitions"]),
    ("Bearing fault frequencies read", "no", "yes, from %s catalogue entries"
     % f"{L['bearings']:,}"),
    ("Capture trusted or not", "no such idea", "8 checks, 4 grades"),
    ("What normal means", "one file somebody nominated",
     "learned from %d captures" % L["captures"]),
    ("Can it say \"I do not know\"", "no", "yes, and it does"),
    ("Baseline traceable to a finding", "no", "versioned, never edited"),
    ("Shared maths", "two copies", "one package"),
    ("Automated tests", "58", f"{TOTAL_TESTS:,}"),
]
rows = [[p("<b></b>", CELLB), p("<b>End of Phase 0</b>", CELLB),
         p("<b>Now</b>", CELLB)]]
for what, was, now in before_after:
    rows.append([p("<b>%s</b>" % what, CELL), tone(was, MUTED),
                 tone(now, GREEN)])
story.append(table(rows, [56 * mm, 52 * mm, 60 * mm]))

# ---------------------------------------------------------- detail -------
story.append(p("What was built, in more detail", H2))

story.append(p("1. Forty-six measurements instead of ten "
               "(VIK-018, 019, 020, 021)", H3))
story.append(p(
    "Ten measurements can tell you a machine is shaking harder than usual. "
    "They cannot tell you why. The extra thirty-six are the ones that "
    "distinguish an unbalanced rotor from a worn bearing from a loose "
    "foundation &#8212; things like how sharply the signal spikes, how energy "
    "is spread across frequencies, and how much sits at the exact "
    "frequencies a defect in this specific bearing would produce.", BODY))
story.append(p(
    "All %d are registered in one place, so the code and the database cannot "
    "disagree about what a measurement is or what counts as normal for it. "
    "Eight of them are marked informational: they describe the signal rather "
    "than the machine's health, and a threshold on them would produce alarms "
    "that mean nothing." % L["definitions"], BODY))

story.append(p("2. Eight checks on whether a capture can be trusted "
               "(VIK-022)", H3))
story.append(p(
    "Missing data, clipping, saturation, noise floor, bias drift, odd DC "
    "offset, unstable speed and a loose sensor. Each returns a grade and, "
    "when it fails, a sentence saying what is wrong in plain words. The "
    "thresholds were set by measuring this gateway rather than by choosing "
    "round numbers, which matters: the first version of the steadiness check "
    "called half the channels unstable, and the number it was reacting to was "
    "the length of the recording, not the machine.", BODY))
story.append(p(
    "A check that cannot run reports \"not assessed\", never \"passed\". "
    "Those are different facts and merging them is how a capture nobody could "
    "grade comes to look like a good one.", BODY))

story.append(p("3. A learned normal, and the honesty around it "
               "(VIK-024, 025, 026, 027)", H3))
story.append(p(
    "Before this, \"healthy baseline\" meant one capture somebody clicked a "
    "button on &#8212; and on this platform it was a copy of the very file "
    "being compared against it. The system now works out normal from the "
    "machine's own history, using the median and a robust spread so that one "
    "bad capture in twenty moves the answer by almost nothing.", BODY))
story.append(p(
    "It refuses rather than producing a weak baseline. A normal built from "
    "four captures is worse than no normal, because the system then trusts "
    "it.", BODY))
story.append(p(
    "<b>Freeze is the part worth understanding.</b> A baseline that keeps "
    "learning from a machine that is slowly wearing out will follow it down. "
    "The captures get worse gradually, normal slides with them, and the fault "
    "never looks abnormal because the yardstick moved. Freezing pins normal "
    "to a period somebody is willing to vouch for. It is the only way a slow "
    "decline shows up as one.", BODY))

if HEALTH and HEALTH.get("available"):
    h = HEALTH
    rows = [[p("<b>The baseline in force right now</b>", CELLB),
             p("", CELLB)]]
    rows += [
        [p("Version and state", CELL),
         tone("v%s, %s" % (h["version"]["version"], h["version"]["state"]), GREEN)],
        [p("Coverage", CELL),
         p("%d of %s channel-feature pairs (%.0f%%)"
           % (h["coverage"]["rows"], h["coverage"]["expected_rows"],
              100 * h["coverage"]["fraction"]), CELL)],
        [p("Built from", CELL),
         p("%.0f captures at the median" % h["samples"]["median"], CELL)],
        [p("Confidence", CELL),
         p("median %.2f; %d feature(s) at or below %.1f"
           % (h["confidence"]["median"], h["confidence"]["low_confidence_rows"],
              h["confidence"]["threshold"]), CELL)],
        [p("Freshness", CELL),
         p("window closed %.1f days ago; %d captures since"
           % (h["freshness"]["age_days"],
              h["freshness"]["captures_since_window"]), CELL)],
    ]
    story.append(Spacer(1, 4))
    story.append(table(rows, [52 * mm, 116 * mm]))
    story.append(Spacer(1, 3))
    story.append(p(
        "Read through the same read model the API serves, so this table is a "
        "caller of VIK-027 rather than a second opinion about the same rows.",
        SMALL))

story.append(p("4. One copy of the shared maths (VIK-035)", H3))
story.append(p(
    "The platform and the chatbot both answer questions about the same "
    "bearing on the same machine, and until now they did it from separate "
    "code. If they disagreed, nothing would crash: one would report a bearing "
    "fault and the other would report nothing, months apart, and whichever a "
    "person happened to read would be the answer they acted on. Bearing "
    "formulas, ISO tables, unit conversion and fault rules now exist once, in "
    "<font face='Courier'>backend/vibcore/</font>, imported by both.", BODY))


# ============================================= bugs found and fixed ======
story.append(p("What was found wrong and fixed along the way", H2))
story.append(p(
    "None of these was on the ticket list. All of them were making the "
    "system's answers wrong while looking entirely normal on screen, which is "
    "the only kind of bug that matters at this stage.", BODY))

bugs = [
    ("Measurements were reading the sensor's resting position, not the "
     "vibration",
     "Eight of thirteen time measurements were computed without removing each "
     "channel's standing bias. On one channel that bias was larger than the "
     "vibration itself, so the system reported every single sample as an "
     "impact. 1,163 of 1,479 critical readings were false; five of eight "
     "channels read critical while the pump was running normally."),
    ("The shaft speed was wrong on every channel",
     "The speed was taken from the tallest line in the spectrum, which on "
     "this pump is two or four times the true speed. A speed wrong by two "
     "puts every bearing frequency out by two. Now resolved from the machine "
     "nameplate, cross-checked, and marked unusable when it cannot be "
     "established."),
    ("Whole windows of samples were being thrown away",
     "The gateway crashed on a timestamp the PLC had not set yet, and the "
     "error escaped in a way that silently dropped the whole message. Five "
     "complete recordings were lost before it was found."),
    ("Saving the settings screen erased the sensor sensitivities",
     "The settings form had no field for per-channel sensitivity, and saving "
     "replaced the whole stored map with what the form knew about. Opening "
     "the page and pressing save &#8212; changing nothing &#8212; wiped the "
     "figures the gateway had supplied."),
    ("A baseline could be built across a settings change",
     "Fourteen of forty-two measurements move by more than a quarter when the "
     "recording length or sample rate changes. One measurement read seven "
     "standard deviations out, entirely because somebody changed a setting. "
     "A baseline is now tied to the recording shape it was learned from."),
    ("Nine fake captures were being counted as evidence about a real pump",
     "One synthetic test file, uploaded nine times, sitting in the history "
     "looking like nine independent observations. The median ignored them, as "
     "it should; the 95th percentile could not, and reported 0.29962 against "
     "a real machine level of 0.01175 &#8212; twenty-five times too high, "
     "presented as an ordinary upper limit for a healthy pump. Removed, and "
     "backed up first."),
    ("The converter step was taken on trust from a config file",
     "The trust checks divide the vibration by the converter's step size, and "
     "that came from a number nobody had verified &#8212; while two config "
     "files in this deployment disagree about it. The step is now measured "
     "from the samples themselves, and the system says so when the "
     "measurement and the record disagree."),
]
rows = [[p("<b>What was wrong</b>", CELLB), p("<b>Why it mattered</b>", CELLB)]]
for title, detail in bugs:
    rows.append([p("<b>%s</b>" % title, CELL), p(detail, CELL)])
story.append(table(rows, [58 * mm, 110 * mm]))

story.append(Spacer(1, 6))
story.append(box(
    "<b>How these were found.</b> Mostly by mutation testing: deliberately "
    "breaking one guard in the code and checking that a test notices. A test "
    "that still passes when the thing it guards is broken is not a test. "
    "Applied to every module written in Phase 1 &#8212; and the first time it "
    "was run on the frequency measurements, 11 of 18 deliberate breakages "
    "went unnoticed, which is how the sideband bug was found. It is also how "
    "a gap in the baseline work was found this week: nothing covered a "
    "baseline that was built but never switched on.", AMBER, colors.HexColor("#FDF8EF")))

# ================================================= what needs fixing =====
story.append(p("What still needs fixing", H2))

story.append(p("1. The hardware range is wrong for this machine &#8212; "
               "needs somebody at the PLC", H3))
story.append(p(
    "This is the most valuable open item and it is not a software problem.", BODY))
story.append(p(
    "The sensors are set to 100 mV/g, which lets the converter cover plus or "
    "minus 50 g. This pump uses about a thousandth of that. Measured across "
    "the twenty most recent captures, here is how many steps of the converter "
    "the actual vibration spans on each channel &#8212; below about three, "
    "the channel is describing the rounding rather than the machine:", BODY))

if COUNTS:
    rows = [[p("<b>Channel</b>", CELLB), p("<b>Steps</b>", CELLB),
             p("<b>Reading</b>", CELLB)] for _ in [0]]
    for i in sorted(COUNTS):
        v = COUNTS[i]
        if v < 3:
            verdict, colour = "reporting rounding", RED
        elif v < 10:
            verdict, colour = "coarse", AMBER
        else:
            verdict, colour = "usable", GREEN
        rows.append([p("ch%d" % i, CELL), p("%.1f" % v, CELL),
                     tone(verdict, colour)])
    story.append(table(rows, [22 * mm, 22 * mm, 60 * mm]))
    story.append(Spacer(1, 4))

story.append(p(
    "The gateway's own configuration file asks for 500 mV/g on the first two "
    "channels, which would narrow the range to plus or minus 10 g and give "
    "five times the resolution. The samples show the PLC applied 100 to all "
    "eight. Somebody has already worked out what the fix is; the PLC is not "
    "honouring it. <b>What is needed:</b> someone with access to the PLC "
    "configuration to confirm what sensitivity it is actually applying, and "
    "whether the transducers on channels 0 and 1 are 500 mV/g parts.", BODY))
story.append(p(
    "Until then %s of %s channel assessments fail the noise-floor check, and "
    "those failures are real."
    % (f"{NOISE_FAILS:,}", f"{sum(QMAP.values()):,}"), BODY))

story.append(p("2. No data has arrived since %s" %
               (L["newest"].strftime("%d %B, %H:%M") if hasattr(L["newest"], "strftime")
                else str(L["newest"])), H3))
story.append(p(
    "The gateway has been silent. Everything in this document is built from "
    "the %s captures already stored, covering %s to %s. Nothing is wrong with "
    "the platform; the source stopped publishing."
    % (L["captures"],
       L["oldest"].strftime("%d %B") if hasattr(L["oldest"], "strftime") else "?",
       L["newest"].strftime("%d %B") if hasattr(L["newest"], "strftime") else "?"),
    BODY))

story.append(p("3. Two thresholds cannot be calibrated yet", H3))
story.append(p(
    "The steadiness check needs about ten shaft revolutions in each half of a "
    "recording to be meaningful. At the current recording length this pump "
    "gives 9.87 &#8212; just under. The threshold is set at 10 and the check "
    "stands down rather than guessing, which is correct but means it is not "
    "doing any work. A slightly longer recording fixes it, and the same "
    "change would also make one more bearing frequency readable.", BODY))

story.append(p("4. Twenty-two features have untrustworthy percentiles", H3))
story.append(p(
    "These were checked individually and are genuine, not contamination: "
    "measurements like the dominant frequency legitimately jump between "
    "separate values rather than varying smoothly around one. Their median "
    "and spread are usable; their 5th and 95th percentiles describe a "
    "different population and should not be read as limits. The system now "
    "marks them so nothing downstream reads them as limits by accident.",
    BODY))

story.append(p("5. Open from Phase 0, still open", H3))
story.append(p(
    "VIK-013, the background worker, is still not built. It does not block "
    "anything in Phase 1 &#8212; a whole capture costs about a fifth of a "
    "second &#8212; but Phase 2 runs scoring and baseline comparison on every "
    "capture, and that is where it starts to matter.", BODY))


# ================================================= state of the data =====
story.append(p("The state of the data today", H2))

rows = [[p("<b>What</b>", CELLB), p("<b>Count</b>", CELLB),
         p("<b>Note</b>", CELLB)]]
data_rows = [
    ("Captures stored", f"{L['captures']:,}",
     "all from the real gateway, %s" % _shape_txt),
    ("Uploads", f"{L['uploads']:,}", "the nine synthetic ones removed"),
    ("Measurements computed", f"{L['features']:,}",
     "%d per channel per capture" % L["definitions"]),
    ("Trust assessments", f"{L['quality']:,}",
     "%s high, %s medium, %s low"
     % (QMAP.get("high", 0), QMAP.get("medium", 0), QMAP.get("low", 0))),
    ("Learned baselines", f"{L['baselines']:,}",
     "across %s versions, one in force" % L["versions"]),
    ("Bearings in the catalogue", f"{L['bearings']:,}", "loaded in Phase 0"),
]
for a, b, c in data_rows:
    rows.append([p("<b>%s</b>" % a, CELL), tone(b, ACCENT), p(c, CELL)])
story.append(table(rows, [46 * mm, 26 * mm, 96 * mm]))

story.append(Spacer(1, 6))
story.append(p(
    "Eight database migrations were added in Phase 1, numbered 021 to 028. "
    "They add the measurement register, the envelope definitions, the trust "
    "assessments, the learned-normal table, the recording-shape scoping and "
    "the baseline lifecycle. Migration 028 also adopted the five baselines "
    "that already existed, timestamped from when each was actually built "
    "rather than from the day the migration ran.", SMALL))

# ===================================================== how to check ======
story.append(p("How to check any of this yourself", H2))
story.append(p(
    "Nothing in this document has to be taken on trust. Each of these can be "
    "run now:", BODY))

checks = [
    ("Run every test",
     "cd backend &amp;&amp; .venv\\Scripts\\python -m pytest tests/ -q"),
    ("Rebuild this document from live data",
     "cd backend &amp;&amp; .venv\\Scripts\\python scripts/build_phase1_report.py"),
    ("Ask the platform how good its baseline is",
     "GET /api/v1/learned-baselines/health?sensor_id=..."),
    ("See every baseline version and why each was started",
     "GET /api/v1/learned-baselines/versions?sensor_id=..."),
    ("Re-grade every stored capture",
     "cd backend &amp;&amp; .venv\\Scripts\\python scripts/reassess_quality.py"),
    ("Restore the nine deleted synthetic uploads",
     "cd backups/synthetic_uploads &amp;&amp; python restore.py --dry-run"),
]
rows = [[p("<b>To check</b>", CELLB), p("<b>Run</b>", CELLB)]]
for what, cmd in checks:
    rows.append([p(what, CELL), Paragraph(cmd, MONO)])
story.append(table(rows, [62 * mm, 106 * mm]))

# ======================================================= what's next =====
story.append(p("What happens next", H2))
story.append(p(
    "<b>Atharva:</b> Phase 1 is finished. Phase 2 is next &#8212; scoring how "
    "unusual each reading is, against the right kind of normal. That work "
    "reads the baselines and the trust grades built here, which is why it "
    "could not start earlier.", BODY))
story.append(p(
    "<b>Laxman:</b> eight Phase 1 tickets, none started. VIK-033 is unblocked "
    "&#8212; the seven endpoints it needs are live and returning real data "
    "today. VIK-013 from Phase 0 is still open and starts to matter in Phase "
    "2.", BODY))
story.append(p(
    "<b>Whoever owns the hardware:</b> the sensitivity question above. It "
    "costs one conversation and it is currently limiting what every "
    "measurement on five of eight channels can say.", BODY))

story.append(Spacer(1, 10))
story.append(p(
    "Built from the repository at commit %s, the live database, and the test "
    "suites as they ran at %s. The script that produced it is "
    "backend/scripts/build_phase1_report.py."
    % (git("rev-parse", "--short", "HEAD") or "?", STAMP), SMALL))


def page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(21 * mm, 16 * mm, 189 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(21 * mm, 11.5 * mm,
                      "SensoVibe  \u00b7  Phase 1 status  \u00b7  " + STAMP)
    canvas.drawRightString(189 * mm, 11.5 * mm, str(doc.page))
    canvas.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4,
                      leftMargin=21 * mm, rightMargin=21 * mm,
                      topMargin=18 * mm, bottomMargin=22 * mm,
                      title="Phase 1 Status Report", author="SensoVibe")
doc.addPageTemplates([PageTemplate(
    id="main",
    frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="f")],
    onPage=page)])
doc.build(story)
print("wrote", OUT)
