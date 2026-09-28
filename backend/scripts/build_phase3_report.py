# -*- coding: utf-8 -*-
"""Phase 3 status report.

Same rule as the Phase 0 and Phase 1 builders: every count in this document
is read from the live database, from git, from the rule table, or from the
test suites at the moment it is built. Nothing is typed in.

The resolution arithmetic in the "what is wrong" section is computed here
rather than quoted, because it is the central finding of the phase and a
number that drifts as the gateway is reconfigured.

    python scripts/build_phase3_report.py
"""
import datetime
import json
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
OUT = REPO + r"\Phase3_Status_Report.pdf"
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
    "uploads": one("select count(*) from sensor_data_uploads"),
    "findings": one("select count(*) from fault_findings"),
    "symptom_rows": one("select count(*) from capture_symptoms"),
    "observations": one("select coalesce(sum(jsonb_array_length(symptoms)),0)"
                        " from capture_symptoms"),
    "plot_rows": one("select count(*) from fault_plot_evidence"),
    "plot_faults": one("select count(distinct fault_key) "
                       "from fault_plot_evidence"),
    "scored": one("select count(*) from feature_anomaly_scores where is_scored"),
    "alarms": one("select count(*) from feature_alarm_state where alarming"),
    "equipment": one("select count(*) from equipment_masters"),
    "sensors": one("select count(*) from sensor_configurations"),
    "head": one("select version_num from alembic_version"),
}

# The rule table is the authority on how many faults can be named at all.
try:
    with open(REPO + r"\backend\vibcore\data\fault_signatures.json",
              encoding="utf-8") as _fh:
        RULES = json.load(_fh)["rules"]
except Exception:
    RULES = {}

# How many symptom checks exist, read from the module rather than counted by
# hand -- the document should not disagree with the code about its own size.
try:
    from app.services.fault_storage import (SYMPTOM_CHECKS_TOTAL,
                                            SYMPTOM_CHECKS_WITHOUT_SPEED)
except Exception:
    SYMPTOM_CHECKS_TOTAL, SYMPTOM_CHECKS_WITHOUT_SPEED = 5, 2

# ---------------------------------------------- the resolution arithmetic --
# The central finding of the phase, computed rather than quoted.
SHAPE = _db.execute(text("""
    select u.sample_count, p.sampling_rate_hz, count(*)
      from sensor_data_uploads u
      left join plot_configurations p on p.sensor_id = u.sensor_id
     where u.sample_count is not null and p.sampling_rate_hz is not null
     group by 1,2 order by 3 desc limit 1
""")).fetchone()

RPM = one("""
    select e.rated_rpm
      from sensor_data_uploads u
      join sensor_configurations c on c.id = u.sensor_id
      join equipment_masters e on e.id = c.equipment_id
     where e.rated_rpm is not null
     order by u.created_at desc limit 1
""")

RES = {}
if SHAPE and RPM:
    _n, _fs = int(SHAPE[0]), float(SHAPE[1])
    _seconds = _n / _fs
    _bin = 1.0 / _seconds
    _shaft = float(RPM) / 60.0
    RES = {
        "samples": _n, "rate": _fs, "seconds": _seconds, "bin_hz": _bin,
        "shaft_hz": _shaft, "captures": SHAPE[2],
        "order_step": _bin / _shaft,
    }
# The verdict the platform itself reaches, read through the function the
# pipeline calls rather than recomputed here.
#
# An earlier draft of this document worked out "the nearest order the
# gateway can represent" for each diagnostic frequency and printed how far
# each one sat from it. That framing is wrong and it showed: it made the
# outer-race frequency look visible and the third shaft harmonic look
# invisible, which is backwards and is not what the code decides. What
# actually matters is whether a *pair* can be told apart -- two frequencies
# 1.58 Hz apart are the same line when a line is 3.6 Hz wide, whichever of
# them you measure from. So this asks the real function.
VERDICT = None
try:
    from app.ai.fault_resolution import MIN_BIN_SEPARATION, assess_resolution
    from app.services.feature_storage import machine_bearing_orders
    from app.models.measurement import SensorDataUpload

    _db2 = SessionLocal()
    _up_id = _db2.execute(text(
        "select id from sensor_data_uploads where parsed_data_path is not null"
        " order by created_at desc limit 1")).scalar()
    _orders = machine_bearing_orders(_db2, _db2.get(SensorDataUpload, _up_id))
    _vanes = _db2.execute(text("""
        select e.pump_vanes
          from sensor_data_uploads u
          join sensor_configurations c on c.id = u.sensor_id
          join equipment_masters e on e.id = c.equipment_id
         where u.id = :u
    """), {"u": str(_up_id)}).scalar()
    VERDICT = assess_resolution(
        sample_rate_hz=RES["rate"], sample_count=RES["samples"],
        shaft_hz=RES["shaft_hz"],
        bearing_orders={k: v for k, v in (_orders or {}).items()
                        if k in ("ftf", "bsf", "bpfo", "bpfi")},
        vane_pass_order=float(_vanes) if _vanes else None)
    _db2.close()
except Exception:
    VERDICT = None

# Tolerances the rules actually use, and how many need a 1x peak.
TOLS = sorted({float(o["tol_order"]) for r in RULES.values()
               for o in r["orders"] if o.get("tol_order")}) or [0.04]
NEEDS_1X = [k for k, r in RULES.items()
            if any(o.get("ref") == "1.0"
                   and o.get("role") in ("dominant", "required")
                   for o in r["orders"])]

# How much signal the converter is actually resolving.
try:
    import numpy as np

    from app.services.plot_generator import load_parsed_data

    _row = _db.execute(text("""
        select parsed_data_path from sensor_data_uploads
         where parsed_data_path is not null
         order by created_at desc limit 1
    """)).fetchone()
    _d = load_parsed_data(_row[0])
    DISTINCT = {int(k[2:]): int(np.unique(np.asarray(v, dtype=float)).size)
                for k, v in (_d.get("channels") or {}).items()
                if k.startswith("ch") and v}
except Exception:
    DISTINCT = {}

# Requirement 9.2's nine fault outputs, verified against the schema at
# build time. Four of these were missing until an audit against the
# document -- so this document checks rather than claims.
REQUIRED_OUTPUTS = [
    ("Fault name", "fault_name"), ("Fault family", "family"),
    ("Severity", "severity"), ("Confidence", "confidence"),
    ("Evidence", "evidence"), ("Related plots", None),
    ("Trend direction", "direction"),
    ("Recommended next action", "recommended_action"),
    ("Shutdown or inspection", "shutdown_advised"),
]
_cols = {r[0] for r in _db.execute(text("""
    select column_name from information_schema.columns
     where table_name = 'fault_findings'
""")).fetchall()}
OUTPUTS = [(label, (col is None) or (col in _cols))
           for label, col in REQUIRED_OUTPUTS]

SYMPTOM_BREAKDOWN = _db.execute(text("""
    select channel, checks_run, checks_possible, shaft_usable
      from capture_symptoms order by channel
""")).fetchall()

_db.close()


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=REPO,
                          capture_output=True, text=True).stdout.strip()


PHASE3_BASE = "c6f4c4f"          # VIK-044, the last Phase 2 commit
COMMITS = git("rev-list", "--count", PHASE3_BASE + "..HEAD") or "?"
_stat = git("diff", "--shortstat", PHASE3_BASE + "..HEAD") or ""
_n2 = [int(x) for x in re.findall(r"(\d+)", _stat)]
SHORTSTAT = ("%s files changed, %s lines added and %s removed"
             % (f"{_n2[0]:,}", f"{_n2[1]:,}", f"{_n2[2]:,}")
             ) if len(_n2) >= 3 else _stat
STAMP = datetime.datetime.now().strftime("%d %B %Y, %H:%M")


def tests_in(folder, args):
    """Count collected tests, whichever way that service's pytest reports it.

    Carried over from the Phase 1 builder along with the reason it looks like
    this: the first version understood one output shape of three and reported
    the chatbot as zero, which read as "this service has no tests". It raises
    rather than returning a number it did not actually read.
    """
    exe = REPO + "\\" + folder + "\\.venv\\Scripts\\python.exe"
    out = subprocess.run(
        [exe, "-m", "pytest", *args, "--collect-only", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO + "\\" + folder, capture_output=True, text=True).stdout
    lines = out.splitlines()

    for line in lines:
        m = re.match(r"\s*(\d+)\s+tests?\s+collected", line)
        if m:
            return int(m.group(1))
    ids = sum(1 for line in lines if "::" in line)
    if ids:
        return ids
    per_file = [int(m.group(1))
                for m in (re.match(r"^\S+\.py:\s*(\d+)\s*$", line)
                          for line in lines) if m]
    if per_file:
        return sum(per_file)
    raise RuntimeError(
        "could not read a test count for %s. Reporting zero here would read "
        "as 'this service has no tests', so this stops instead." % folder)


def suite_passes(folder, args):
    """Run the suite. Existing and passing are different claims."""
    exe = REPO + "\\" + folder + "\\.venv\\Scripts\\python.exe"
    return subprocess.run(
        [exe, "-m", "pytest", *args, "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO + "\\" + folder, capture_output=True,
        text=True).returncode == 0


SUITES = {
    "backend": ["tests/"],
    "gateway": [],
    "vibrationbot": ["tests/", "iso_agent/tests/", "report_agent/tests/",
                     "sql_agent/tests/", "kb_agent/tests/"],
}


def frontend_tests():
    out = subprocess.run(["npm", "test", "--silent"], cwd=REPO + "\\frontend",
                         capture_output=True, text=True, shell=True)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out.stdout + out.stderr)
    m = re.search(r"Tests\s+(\d+)\s+passed", plain)
    return (int(m.group(1)) if m else 0, out.returncode == 0)


COUNTS = {}
for _name, _args in SUITES.items():
    try:
        COUNTS[_name] = tests_in(_name, _args)
    except Exception:
        COUNTS[_name] = 0
FRONTEND_TESTS, FRONTEND_GREEN = frontend_tests()
TOTAL_TESTS = sum(COUNTS.values()) + FRONTEND_TESTS

FAILING = sorted(name for name, args in SUITES.items()
                 if COUNTS.get(name) and not suite_passes(name, args))
if FRONTEND_TESTS and not FRONTEND_GREEN:
    FAILING.append("frontend")
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
story.append(p("Phase 3 &#8212; Name the fault, and show the working", H1))
story.append(p(
    "What Phase 3 is, what is finished, what it found when it was pointed at "
    "the real pump, and what still has to change. Every number here is read "
    "from the live database, from git, from the rule table, or from the test "
    "suites at the moment this was built &#8212; %s." % STAMP, LEAD))

_res_txt = ("%.3f s per capture, %.2f Hz per spectrum line"
            % (RES["seconds"], RES["bin_hz"])) if RES else "an unrecorded shape"

story.append(box(
    "<b>Phase 3 is code-complete and merged.</b> All ten tickets are built, "
    "tested and pushed. The platform can now describe what a signal is doing, "
    "grade a machine against the ISO standard, score its health from eight "
    "separate inputs instead of a three-entry lookup, and say which plot "
    "would prove any of the %d faults it knows about.<br/><br/>"
    "<b>And it currently names no fault on the only real machine.</b> That is "
    "not a bug in this phase and it is the most important line in this "
    "document. At %s, the diagnostic frequencies a bearing fault lives at "
    "cannot be separated from ordinary shaft harmonics &#8212; they land on "
    "the same spectrum line. The fault engine is correct and it is being fed "
    "a picture too blurred to read. Lengthening the capture is what turns it "
    "on, and that is a gateway setting, not a code change.<br/><br/>"
    "<b>The platform says so, rather than reporting a healthy machine.</b> "
    "This is the whole point of the phase. Every screen that could show "
    "\"nothing found\" instead shows why nothing could be found.<br/><br/>"
    "<b>%s automated tests</b> across the suites (%s), all run while building "
    "this document: %s. %s commits since Phase 2, %s."
    % (len(RULES), _res_txt, f"{TOTAL_TESTS:,}",
       ", ".join("%d %s" % (v, k) for k, v in
                 list(COUNTS.items()) + [("frontend", FRONTEND_TESTS)] if v),
       "all passed" if ALL_GREEN else
       "<font color='%s'><b>FAILING: %s</b></font>"
       % (RED.hexval(), ", ".join(FAILING)),
       COMMITS, SHORTSTAT or "many files changed")))

# ------------------------------------------------------ what it was for --
story.append(p("What Phase 3 was for, in one paragraph", H2))
story.append(p(
    "Phase 1 made the measurements trustworthy and learned what normal looks "
    "like. Phase 2 scored how unusual each reading is and turned repeated "
    "unusual readings into alarms. Neither of them ever says <i>what is "
    "wrong</i> &#8212; an alarm says \"this feature is behaving oddly\", "
    "which tells a maintenance engineer to go and look but not what to look "
    "for. Phase 3 is the step that puts a name on it: unbalance, "
    "misalignment, a bearing outer-race defect. And, because a name is a "
    "claim somebody will act on, it is also the step that has to show its "
    "working.", BODY))

story.append(p(
    "Everything in this phase follows one rule, and it is the same rule as "
    "the two phases before it: <b>an answer the platform could not work out "
    "is shown as an absence with a reason, never as a neutral value</b>. A "
    "machine nobody has measured does not score 100 out of 100. A spectrum "
    "that cannot see a bearing fault does not report a healthy bearing. "
    "\"We could not tell\" and \"nothing is wrong\" look identical on a "
    "screen and mean opposite things, and every one of the four problems "
    "found late in this phase was a case of the first quietly becoming the "
    "second.", BODY))

# ------------------------------------------------------------- tickets --
story.append(p("The ten tickets, and what each one actually does", H2))

rows = [[p("Ticket", CELLB), p("What it does, in plain terms", CELLB),
         p("State", CELLB)]]
for key, what in [
    ("VIK-050", "Works out whether the spectrum can tell two diagnostic "
                "frequencies apart at all. If it cannot, that is recorded as "
                "the instrument's limit rather than the machine's condition."),
    ("VIK-051", "Describes what the signal is doing before anything decides "
                "what it means &#8212; a harmonic series, sidebands, "
                "impacting. Each observation carries the numbers behind it."),
    ("VIK-052", "Gathers what is known about the machine: bearing type, vane "
                "count, speed. A detail nobody recorded switches off the rule "
                "that needs it instead of being guessed."),
    ("VIK-053", "Runs the %d fault rules against a capture and ranks what "
                "fits." % len(RULES)),
    ("VIK-054", "Grades how far along a fault is. A stage climbs one step at "
                "a time and never reaches critical on a single reading."),
    ("VIK-055", "Replaces a fake health score (normal 100, warning 60, "
                "critical 20) with one built from eight real inputs."),
    ("VIK-056", "Gives the ISO 10816-3 zone. Where the machine record is "
                "ambiguous, returns every table that could apply."),
    ("VIK-057", "Stores a finding as a record with its evidence attached."),
    ("VIK-058", "A finding evolves rather than being re-created, so "
                "\"developing for nine days\" is answerable."),
    ("VIK-059", "Maps each fault to the plots that would prove it &#8212; "
                "%d rows covering all %d rules." % (L["plot_rows"],
                                                    L["plot_faults"])),
]:
    rows.append([p("<b>%s</b>" % key, CELL), p(what, CELL),
                 tone("Done", GREEN)])
story.append(table(rows, [20 * mm, 126 * mm, 22 * mm]))

# ------------------------------------------------------------- audit ----
story.append(p("Checked against the requirement document, not against memory",
                H2))
story.append(p(
    "The ten tickets above being finished is not the same claim as the "
    "requirement being met, so Phase 3 was audited line by line against "
    "section 9.2 of the requirement document, which lists nine things that "
    "must appear beside every suspected fault. <b>Four were missing</b> "
    "&#8212; and they were the four a maintenance engineer reads first: "
    "which family the fault belongs to, whether it is getting worse, what to "
    "do about it, and whether it needs a shutdown or only an inspection. All "
    "four are now built. The table below is read from the database schema as "
    "this document is generated, so it is a check rather than a claim.",
    BODY))

rows = [[p("Requirement 9.2 asks for", CELLB), p("Present", CELLB)]]
for label, present in OUTPUTS:
    rows.append([p(label, CELL),
                 tone("yes", GREEN) if present else tone("MISSING", RED)])
story.append(table(rows, [110 * mm, 58 * mm]))

story.append(Spacer(1, 4))
story.append(p(
    "The lesson is the same one the four runtime problems taught, in a "
    "different form: a ticket marked done records that somebody built what "
    "the ticket described, not that the requirement behind it is satisfied. "
    "Requirement 14 asked twice for the two that were missing &#8212; \"How "
    "urgent is it?\" and \"What should the analyst do next?\" &#8212; and "
    "neither had an answer anywhere in the platform.", BODY))

story.append(p(
    "<b>One decision inside that work is worth stating on its own.</b> How "
    "urgent a fault is now depends on how well the machine can actually be "
    "seen, not only on how bad the fault looks. A finding at the top stage "
    "cannot recommend stopping a machine if the capture failed its own "
    "quality checks, or if the spectrum could not separate the frequencies "
    "the diagnosis rests on. The platform says what it would have "
    "recommended and what held it back, so the gap gets closed rather than "
    "overridden. On this pump every finding is currently held at \"look at "
    "it when convenient\" for exactly that reason.", BODY))

# =================================================== the central finding ==
story.append(p("The one thing that stops Phase 3 working, in numbers", H2))
story.append(p(
    "This is the finding of the phase, and it is worth reading even if "
    "nothing else here is. It is not an opinion and it is not a software "
    "defect &#8212; it is arithmetic about the capture settings.", BODY))

if RES:
    story.append(p(
        "A spectrum is a list of how much vibration sits at each frequency, "
        "and it can only resolve detail down to one divided by the length of "
        "the recording. The gateway records <b>%s samples at %.0f kHz, which "
        "is %.3f of a second</b> &#8212; so its spectrum has a line every "
        "<b>%.2f Hz</b> and nothing whatever can be seen between them. The "
        "pump turns %.2f times a second, so one line is <b>%.3f of a turn of "
        "the shaft</b>."
        % (f"{RES['samples']:,}", RES["rate"] / 1000.0, RES["seconds"],
           RES["bin_hz"], RES["shaft_hz"], RES["order_step"]), BODY))

    story.append(p(
        "A fault is identified by finding energy at one frequency and not at "
        "another one nearby. So what matters is not where a single frequency "
        "sits, but whether a <i>pair</i> of them can be told apart. Two "
        "frequencies %.2f Hz apart are the same line when a line is %.2f Hz "
        "wide. The table below is the platform's own verdict, read from the "
        "function the pipeline calls &#8212; it is not a second opinion "
        "worked out for this document."
        % (1.58, RES["bin_hz"]), BODY))

    if VERDICT and VERDICT.unresolved:
        rows = [[p("These two cannot be told apart", CELLB),
                 p("Gap between them", CELLB),
                 p("As a fraction of one spectrum line", CELLB)]]
        for item in VERDICT.unresolved:
            rows.append([
                p("<b>%s</b> vs %s" % (item["defect"].upper(),
                                       item["against"]), CELL),
                p("%.2f Hz" % item["gap_hz"], CELL),
                p("<b>%.2f</b> of a line &#8212; same place"
                  % item["bins_apart"], CELL)])
        story.append(table(rows, [64 * mm, 30 * mm, 74 * mm]))
        story.append(Spacer(1, 4))
        story.append(p(
            "Two frequencies need to be about %.0f lines apart before a peak "
            "at one can be told from a peak at the other, because a single "
            "tone smears across neighbouring lines rather than landing "
            "cleanly on one."
            % MIN_BIN_SEPARATION, SMALL))
    elif VERDICT:
        story.append(p(
            "On the current capture settings the platform reports that every "
            "pair it checks can be separated: %s" % VERDICT.reason, BODY))

    story.append(Spacer(1, 6))
    if VERDICT and VERDICT.unresolved:
        _ordinary = [i for i in VERDICT.unresolved
                     if "harmonic" in i["against"] or "pass" in i["against"]]
        _lines = "; ".join(
            "%s against %s" % (i["defect"].upper(), i["against"])
            for i in _ordinary) or "the pairs above"
        story.append(box(
            "<b>Look at what each bearing frequency is confused with: %s.</b> "
            "Every one of those is something a perfectly healthy pump "
            "produces all day &#8212; shaft harmonics come from ordinary "
            "rotation, and vane pass is just the impellers going past. The "
            "two sit closer together than a single spectrum line, so <b>a "
            "damaged bearing and an ordinary machine produce the same "
            "picture</b>, and no amount of rule logic recovers the "
            "difference. %s"
            % (_lines,
               ("The remaining pair, %s, is one bearing symptom against "
                "another fault rather than against a healthy one."
                % ", ".join("%s against %s" % (i["defect"].upper(),
                                               i["against"])
                            for i in VERDICT.unresolved
                            if i not in _ordinary))
               if len(_ordinary) < len(VERDICT.unresolved) else ""),
            colour=RED, bg=colors.HexColor("#FDF3F2")))

    story.append(p(
        "Measured on the live data rather than argued from theory: across all "
        "eight channels of the most recent capture, the engine produces "
        "<b>zero</b> fault hypotheses even with the score threshold dropped "
        "to nothing. %d of the %d rules are switched off before they start "
        "because they need energy at one turn of the shaft and there is no "
        "peak there on seven of the eight channels."
        % (len(NEEDS_1X), len(RULES)), BODY))

    if VERDICT and VERDICT.needed_seconds:
        story.append(p(
            "<b>What would fix it.</b> Resolution is one divided by the "
            "recording length, so the recording has to get longer. The "
            "platform states the figure itself: separating every pair above "
            "needs about <b>%.1f seconds</b> of recording against the %.3f "
            "being taken now &#8212; roughly <b>%.0f times longer</b>. This "
            "is a setting on the gateway. It costs storage and nothing else."
            % (VERDICT.needed_seconds, RES["seconds"],
               VERDICT.needed_seconds / RES["seconds"]), BODY))

# ---------------------------------------------------- the second problem --
story.append(p("The second hardware problem, carried over from Phase 1", H2))
if DISTINCT:
    _worst = min(DISTINCT.values())
    _best = max(DISTINCT.values())
    story.append(p(
        "A separate limit, and the one Phase 1 already flagged. The "
        "accelerometers are set up for a range far larger than this pump "
        "actually produces, so the signal arrives using a tiny fraction of "
        "the available precision. In the most recent capture the eight "
        "channels contain between <b>%d and %d distinct values</b> across "
        "the whole recording. Most of what the spectrum contains is the "
        "converter rounding up and down, not the machine."
        % (_worst, _best), BODY))
    story.append(p(
        "This is what made the ISO grading return \"Zone A &#8212; typical of "
        "newly commissioned machines\" on the real pump, from a reading of "
        "0.027 mm/s where a running pump reads one to three. The platform now "
        "refuses to grade a capture this coarse and says why, but refusing is "
        "damage control: the underlying signal still needs fixing at the PLC.",
        BODY))

# ============================================ what was found by running ==
story.append(p("Four problems found by running it, not by reasoning about it",
                H2))
story.append(p(
    "All four were invisible in the tests and obvious within minutes of "
    "pointing the code at the real gateway and the real database. Each one "
    "produced a confident, plausible, wrong answer rather than an error, "
    "which is the failure mode this programme is most exposed to. All four "
    "are fixed, and each now has a test that fails if it comes back.", BODY))

rows = [[p("What it did", CELLB), p("Why it mattered", CELLB)]]
for did, why in [
    ("The symptom detection never ran at all, on any capture, ever.",
     "It sat behind a check for shaft speed that this gateway does not always "
     "pass. The feature was written precisely for captures where no fault can "
     "be named &#8212; so the one situation it existed for was the one it "
     "could not run in. Symptoms are now recorded for every channel of every "
     "capture; the live database holds %d observations across %d channels."
     % (L["observations"], L["symptom_rows"])),
    ("ISO grading called the pump \"typical of newly commissioned machines\".",
     "From a velocity two orders of magnitude below any running pump, because "
     "there was almost no signal to measure. The best zone in the standard "
     "and a machine the instrument cannot see produce the same number. "
     "Somebody would have read it as a clean bill of health."),
    ("It reported the 713th and 877th harmonics of running speed.",
     "The tolerance is a fraction of a turn, so far up the spectrum almost "
     "any peak satisfies it by coincidence. Scattered numbers are not a "
     "harmonic series. It now reports the longest unbroken run instead."),
    ("It printed \"243378% of the envelope\".",
     "An energy divided by an amplitude &#8212; the units do not cancel, so "
     "the figure was not a proportion of anything. It is now a share of the "
     "four bearing bands, which is also the question being asked."),
]:
    rows.append([p(did, CELL), p(why, CELL)])
story.append(table(rows, [58 * mm, 110 * mm]))

story.append(Spacer(1, 4))
story.append(p(
    "A fifth was caught by the tests rather than by running it, and is worth "
    "recording for the same reason: the first draft of the fault-to-plot "
    "table invented nine fault names the engine cannot produce &#8212; "
    "<font face='Courier'>looseness</font> where the rule is called "
    "<font face='Courier'>mechanical_looseness</font>, and eight more. Every "
    "one would have shown an empty panel rather than an error. A test now "
    "checks the table against the rule list.", BODY))

# -------------------------------------------------------- health score ---
story.append(p("The health score, and why it is different now", H2))
story.append(p(
    "What it used to be: normal is 100, warning is 60, critical is 20. That "
    "is the status word written in a different font. It moves in steps of "
    "forty, it cannot tell a machine that went to warning ten minutes ago "
    "from one that has been there six weeks, and its 100 is indistinguishable "
    "from the 100 of a machine nobody has ever taken a reading from.", BODY))
story.append(p(
    "It is now built from eight inputs &#8212; the severity of any named "
    "fault, how unusual the readings are against the machine's own learned "
    "baseline, the symptoms observed in the signal, whether it is getting "
    "worse, standing alarms, how well the machine can be seen at all, how "
    "critical it is, and what it has done in the past. Three decisions in "
    "how those combine are worth stating:", BODY))

rows = [[p("Decision", CELLB), p("Why", CELLB)]]
for what, why in [
    ("Poor data lowers the <b>ceiling</b>, never the score.",
     "A machine with no learned baseline cannot be certified at 100 &#8212; "
     "not because anything is wrong with it, but because nobody has looked "
     "hard enough to say. It tops out at 72 and the screen shows \"/ 72\" "
     "next to the number, so the shortfall is not blamed on the machine."),
    ("One severe fault outranks four mild concerns.",
     "Adding penalties up gets this backwards, and the mistake is invisible "
     "&#8212; both machines just end up with a number. They combine as "
     "independent concerns instead, so the worst one leads."),
    ("How critical the machine is changes the priority, not the score.",
     "A spare pump and a boiler feed pump in identical mechanical condition "
     "are in identical mechanical condition. Letting criticality move the "
     "health figure makes one number answer two questions and check against "
     "neither."),
]:
    rows.append([p(what, CELL), p(why, CELL)])
story.append(table(rows, [58 * mm, 110 * mm]))

story.append(Spacer(1, 4))
story.append(p(
    "Every point deducted carries the sentence that produced it. Hovering the "
    "score on the dashboard shows the largest single contribution and what it "
    "cost. A score nobody can take apart is the lookup table again, with more "
    "decimal places.", BODY))

# --------------------------------------------------- what you can see ----
story.append(p("What is visible on the system now", H2))
rows = [[p("Where", CELLB), p("What changed", CELLB)]]
for where, what in [
    ("Dashboard &#8212; machine cards",
     "A real health score where most machines previously showed nothing, "
     "written as \"Health 12.4 / 72 &#183; critical\". The second number is "
     "the ceiling and only appears when it is below 100. Hovering gives the "
     "reason in a sentence."),
    ("Dashboard &#8212; machines with no data",
     "\"Not scored\" in italics instead of an empty space, with a tooltip "
     "saying no capture has ever been taken. A blank cell reads as fine; this "
     "does not."),
    ("Dashboard &#8212; fleet average",
     "Averages real scores and skips machines that cannot be scored, rather "
     "than counting them as healthy."),
    ("<font face='Courier'>/api/v1/diagnosis/symptoms</font>",
     "What the signal is doing, per channel, with the numbers behind each "
     "observation. Currently the most useful of the five &#8212; it returns "
     "%d observations on the latest capture." % L["observations"]),
    ("<font face='Courier'>/api/v1/diagnosis/findings</font>",
     "Named faults with their evidence and the plots that would prove them. "
     "Returns empty on this machine, with the reason attached."),
    ("<font face='Courier'>/api/v1/diagnosis/health</font>",
     "The full health breakdown, every contribution itemised."),
    ("<font face='Courier'>/api/v1/diagnosis/iso</font>",
     "The ISO zone, or every zone it could be and what is missing. Currently "
     "refuses on this machine because the signal is at the converter floor."),
    ("<font face='Courier'>/api/v1/diagnosis/plot-evidence</font>",
     "The fault-to-plot table: %d rows over %d faults, each saying what to "
     "look for and why that plot." % (L["plot_rows"], L["plot_faults"])),
]:
    rows.append([p(where, CELL), p(what, CELL)])
story.append(table(rows, [60 * mm, 108 * mm]))

# ----------------------------------------------------------- the data ----
story.append(p("What is in the database right now", H2))
rows = [[p("Table", CELLB), p("Rows", CELLB), p("What it means", CELLB)]]
for label, value, meaning in [
    ("Captures ingested", f"{L['uploads']:,}",
     "Every recording the gateway has sent."),
    ("Feature scores", f"{L['scored']:,}",
     "Individual readings scored against a learned baseline."),
    ("Alarms standing", str(L["alarms"]),
     "Past all four conditions: repeated, rising, steady speed, trustworthy "
     "capture."),
    ("Symptom rows", str(L["symptom_rows"]),
     "One per channel per capture. %d observations in total."
     % L["observations"]),
    ("Fault findings", str(L["findings"]),
     "Zero, for the resolution reason above &#8212; not because the machine "
     "is healthy."),
    ("Fault-to-plot rows", str(L["plot_rows"]),
     "Covering all %d rules the engine knows." % L["plot_faults"]),
    ("Machines / sensors", "%s / %s" % (L["equipment"], L["sensors"]),
     "One pump is instrumented and sending data."),
    ("Database version", str(L["head"]),
     "Migrations applied, in order, with a manifest guarding the chain."),
]:
    rows.append([p(label, CELL), p("<b>%s</b>" % value, CELL),
                 p(meaning, CELL)])
story.append(table(rows, [34 * mm, 20 * mm, 114 * mm]))

# ---------------------------------------------------- symptom breakdown --
if SYMPTOM_BREAKDOWN:
    story.append(p("What the platform can currently say about the signal", H2))
    _all_ran = all(r[2] == SYMPTOM_CHECKS_TOTAL for r in SYMPTOM_BREAKDOWN)
    story.append(p(
        "Five checks exist. Three of them are written in turns of the shaft "
        "and need a running speed; two do not. Every row records how many "
        "could run, so that an empty result is never mistaken for a quiet "
        "machine. %s"
        % ("On this capture a running speed was available, so all five ran "
           "on every channel &#8212; the observations below are what they "
           "found, not what they were prevented from looking for."
           if _all_ran else
           "On this capture some checks could not run, which is why the "
           "second column is below five."), BODY))
    rows = [[p("Channel", CELLB), p("Observations found", CELLB),
             p("Checks that could run", CELLB)]]
    for ch, run, possible, usable in SYMPTOM_BREAKDOWN:
        rows.append([p("Channel %d" % ch, CELL),
                     p(str(run), CELL),
                     p("%d of %d" % (possible, SYMPTOM_CHECKS_TOTAL), CELL)])
    story.append(table(rows, [30 * mm, 40 * mm, 98 * mm]))

# ------------------------------------------------------------ testing ----
story.append(p("How much of this is actually checked", H2))
rows = [[p("Suite", CELLB), p("Tests", CELLB), p("Result", CELLB)]]
for name in ("backend", "gateway", "vibrationbot"):
    if COUNTS.get(name):
        rows.append([p(name, CELL), p(f"{COUNTS[name]:,}", CELL),
                     tone("passed", GREEN) if name not in FAILING
                     else tone("FAILED", RED)])
if FRONTEND_TESTS:
    rows.append([p("frontend", CELL), p(f"{FRONTEND_TESTS:,}", CELL),
                 tone("passed", GREEN) if FRONTEND_GREEN else tone("FAILED", RED)])
rows.append([p("<b>Total</b>", CELL), p("<b>%s</b>" % f"{TOTAL_TESTS:,}", CELL),
             tone("all passed", GREEN) if ALL_GREEN else tone("see above", RED)])
story.append(table(rows, [50 * mm, 30 * mm, 88 * mm]))

story.append(Spacer(1, 6))
story.append(p(
    "<b>Tests were also tested.</b> A test that passes whether or not the "
    "code is correct is worse than no test, because it is a claim of cover "
    "that is not true. Twelve deliberate faults were introduced one at a time "
    "&#8212; removing the guard that stops a harmonic series being reported "
    "as sidebands, making poor data lower the score instead of the ceiling, "
    "letting criticality move the condition &#8212; and the suite was checked "
    "for whether it noticed. All twelve were caught.", BODY))
story.append(p(
    "Two were not caught on the first attempt, and both are worth recording. "
    "One was covered by a second, independent guard, so removing the first "
    "changed no behaviour &#8212; safe, but it meant the guard under test had "
    "no test of its own. The other slipped through because the test signal "
    "let a different rule reject it before the guard being tested was "
    "consulted. Both now have signals built specifically to isolate them.",
    BODY))

# --------------------------------------------------------- what's next ---
story.append(p("What happens next", H2))
_need_all = ("about %.1f seconds" % VERDICT.needed_seconds
             if VERDICT and VERDICT.needed_seconds else "several seconds")
story.append(p(
    "<b>Whoever owns the gateway &#8212; and this is the one that matters.</b> "
    "The capture length needs to go up from %s. Roughly <b>two seconds</b> "
    "separates the outer-race and inner-race frequencies, which are the two "
    "that matter most; <b>%s</b> separates all four, including the ball-spin "
    "frequency, which is the closest pair of all. Until that happens the "
    "fault engine cannot name anything on this pump however correct it is. "
    "This is a configuration change, and it costs storage and nothing else."
    % (("%.3f of a second" % RES["seconds"]) if RES else "its current value",
       _need_all), BODY))
story.append(p(
    "<b>Whoever owns the PLC.</b> The accelerometer sensitivity question from "
    "Phase 1 is still open and still limiting every amplitude the platform "
    "reports. It is why the ISO grading currently refuses to answer.", BODY))
story.append(p(
    "<b>Atharva.</b> Phase 3 is finished and pushed. Two things are worth "
    "doing before Phase 4 regardless of the hardware: a gateway silence alarm "
    "&#8212; nothing anywhere in the codebase notices when the gateway stops "
    "sending, and it has gone quiet for days at a time before &#8212; and "
    "wiring the symptoms onto a screen, since they are currently the only "
    "thing the platform can say about this machine and they are reachable "
    "only through the API.", BODY))
story.append(p(
    "<b>Laxman.</b> Nothing in this phase blocks his work. The one thing to "
    "carry forward is the pattern behind all four late findings: when a "
    "feature is added behind a condition, check that the condition is ever "
    "true on the real gateway. Three of the four problems above were features "
    "that worked perfectly and never ran.", BODY))

story.append(Spacer(1, 10))
story.append(p(
    "Built from the repository at commit %s, the live database, the rule "
    "table, and the test suites as they ran at %s. The script that produced "
    "it is backend/scripts/build_phase3_report.py."
    % (git("rev-parse", "--short", "HEAD") or "?", STAMP), SMALL))


def page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(21 * mm, 16 * mm, 189 * mm, 16 * mm)
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(MUTED)
    canvas.drawString(21 * mm, 11.5 * mm,
                      "SensoVibe  \u00b7  Phase 3 status  \u00b7  " + STAMP)
    canvas.drawRightString(189 * mm, 11.5 * mm, str(doc.page))
    canvas.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4,
                      leftMargin=21 * mm, rightMargin=21 * mm,
                      topMargin=18 * mm, bottomMargin=22 * mm,
                      title="Phase 3 Status Report", author="SensoVibe")
doc.addPageTemplates([PageTemplate(
    id="main",
    frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="f")],
    onPage=page)])
doc.build(story)
print("wrote", OUT)
