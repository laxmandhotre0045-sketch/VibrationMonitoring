/**
 * SensoVibe Technical Documentation — build script.
 *
 * Merges docs/_sdd_part1..7.md into a single master document with:
 *   - cover page, document control block, revision history
 *   - clickable table of contents (GitHub-style anchors)
 *   - list of figures / list of tables
 *   - sequential Figure N and Table N captions derived from the nearest heading
 *   - page breaks before every top-level section (for PDF export)
 *
 * Usage:  node docs/build-doc.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DOCS = path.dirname(fileURLToPath(import.meta.url));
const PARTS = [1, 2, 3, 4, 5, 6, 7].map((n) =>
  path.join(DOCS, "_parts", `_sdd_part${n}.md`)
);
const OUT_MD = path.join(DOCS, "SensoVibe_Technical_Documentation.md");
const OUT_HTML = path.join(DOCS, "SensoVibe_Technical_Documentation.html");

const DOC_VERSION = "1.1";
// Date the 1.0 baseline was cut; the 0.x revision-history rows all belong to it.
const DOC_DATE = "26 July 2026";
const REVISION_DATE = "17 August 2026";
const PROJECT_VERSION = "Backend 1.1.0 · Frontend 1.0.0 · Schema rev 011";

// ---------------------------------------------------------------- slugger ---
function makeSlugger() {
  const seen = new Map();
  return (text) => {
    const base = text
      .toLowerCase()
      .replace(/`/g, "")
      .replace(/\*\*/g, "")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/[^\w\- ]+/g, "")
      .trim()
      .replace(/\s+/g, "-");
    const n = seen.get(base) ?? 0;
    seen.set(base, n + 1);
    return n === 0 ? base : `${base}-${n}`;
  };
}

// ------------------------------------------------------------------ merge ---
let body = PARTS.map((p) => {
  if (!fs.existsSync(p)) throw new Error(`Missing source part: ${p}`);
  return fs.readFileSync(p, "utf8").trim();
}).join("\n\n");

// Drop the original title block from part 1 — the cover page replaces it.
body = body.replace(
  /^# SensoVibe[\s\S]*?(?=^# 1\.0 Project Overview)/m,
  ""
);

// ------------------------------------- annotate figures, tables, headings ---
const lines = body.split(/\r?\n/);
const out = [];
const toc = [];
const figures = [];
const tables = [];

const slug = makeSlugger();
let inFence = false;
let fenceLang = "";
let currentHeading = "Document";
let figureNo = 0;
let tableNo = 0;
let firstTopLevel = true;

const isTableSeparator = (s) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(s) && s.includes("-") && s.includes("|");
const isTableRow = (s) => /^\s*\|/.test(s);

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  const fence = line.match(/^```(\w*)/);

  // ---- fenced blocks ----
  if (fence) {
    if (!inFence) {
      inFence = true;
      fenceLang = fence[1] ?? "";
      if (fenceLang === "mermaid") {
        figureNo += 1;
        figures.push({ n: figureNo, title: currentHeading });
      }
      out.push(line);
      continue;
    }
    inFence = false;
    out.push(line);
    if (fenceLang === "mermaid") {
      out.push("");
      out.push(`*Figure ${figureNo} — ${currentHeading}*`);
    }
    fenceLang = "";
    continue;
  }
  if (inFence) {
    out.push(line);
    continue;
  }

  // ---- headings ----
  const h = line.match(/^(#{1,4})\s+(.*)$/);
  if (h) {
    const level = h[1].length;
    const text = h[2].trim();
    currentHeading = text.replace(/`/g, "");
    const id = slug(text);
    if (level <= 3) toc.push({ level, text: currentHeading, id });
    if (level === 1) {
      if (!firstTopLevel) {
        out.push('<div class="page-break"></div>');
        out.push("");
      }
      firstTopLevel = false;
    }
    out.push(`<a id="${id}"></a>`);
    out.push(line);
    continue;
  }

  // ---- tables ----
  if (isTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
    tableNo += 1;
    tables.push({ n: tableNo, title: currentHeading });
    out.push(`*Table ${tableNo} — ${currentHeading}*`);
    out.push("");
    out.push(line);
    continue;
  }

  out.push(line);
}

const annotated = out.join("\n");

// ------------------------------------------------------------ front matter ---
const tocMd = toc
  .map(({ level, text, id }) => `${"  ".repeat(level - 1)}- [${text}](#${id})`)
  .join("\n");

const figuresMd = figures.map((f) => `| ${f.n} | ${f.title} |`).join("\n");
const tablesMd = tables.map((t) => `| ${t.n} | ${t.title} |`).join("\n");

const front = `<a id="cover"></a>

<div class="cover">

# SensoVibe

## AI Powered Industrial Vibration Intelligence Platform

### Software Design & Technical Documentation

**Document version ${DOC_VERSION}**

| | |
|---|---|
| **Project** | SensoVibe — AI Powered Industrial Vibration Intelligence Platform |
| **Repository** | \`VibrationMonitoring\` |
| **Product version** | ${PROJECT_VERSION} |
| **Document version** | ${DOC_VERSION} |
| **Document type** | Software Design Document (SDD) / Complete Technical Documentation |
| **Document scope** | Frontend + Backend + Database + Configuration + Assets + APIs + Project Structure |
| **Source of truth** | Extracted exclusively from the source code in this repository |
| **Source branch** | \`laxman-dev\` |
| **Date** | ${REVISION_DATE} |
| **Prepared by** | Engineering — SensoVibe Platform Team |
| **Reviewed by** | _pending_ |
| **Approved by** | _pending_ |
| **Company** | SensoVibe |
| **Classification** | Internal — Engineering / Stakeholder distribution |
| **Status** | Baselined |

</div>

<div class="page-break"></div>

<a id="document-control"></a>

# Document Control

## Purpose and scope

This document is the complete technical specification of the SensoVibe platform. It covers the frontend application, the backend service, the database schema, every REST endpoint, all configuration files, the deployment topology, the test position, performance characteristics, and the security posture.

> **Reading note.** Every statement in this document is derived from code that exists in the repository. Where a feature is declared but not implemented (for example the Change Password screen), this document says so explicitly rather than describing intended behaviour.

## Intended audience

| Audience | Recommended reading |
|---|---|
| New developers | §1, §2, §3, §4, §10, §11, §12 |
| Backend engineers | §2, §4, §5, §6, §7, §8, §14 |
| Frontend engineers | §2, §3, §8, §9, §10 |
| Database administrators | §6, §11, §12, §14 |
| Security reviewers | §7, §15 |
| QA engineers | §5, §9, §13, §15 |
| DevOps / SRE | §11, §12, §14, §15 |
| Project managers and stakeholders | §1, §8, §9, §12, §13 |

## Conventions used

| Convention | Meaning |
|---|---|
| \`monospace\` | File path, identifier, command, or literal value |
| **§n.n** | Cross-reference to a numbered section of this document |
| ✔ / ✘ | Implemented / not implemented |
| *Figure n* | Numbered diagram; indexed in the List of Figures |
| *Table n* | Numbered table; indexed in the List of Tables |
| "stated plainly" notes | Deliberate disclosure of a gap, limitation, or unused artefact |

Page numbers are applied by the PDF renderer at export time; section, figure, and table numbering are fixed within this document.

<div class="page-break"></div>

<a id="revision-history"></a>

# Revision History

| Version | Date | Author | Description of change | Status |
|---|---|---|---|---|
| 0.1 | ${DOC_DATE} | Engineering | Initial draft — Project Overview and System Architecture (§1–§2) | Superseded |
| 0.2 | ${DOC_DATE} | Engineering | Added Frontend Documentation (§3) | Superseded |
| 0.3 | ${DOC_DATE} | Engineering | Added Backend Documentation (§4) | Superseded |
| 0.4 | ${DOC_DATE} | Engineering | Added REST API Documentation (§5) | Superseded |
| 0.5 | ${DOC_DATE} | Engineering | Added Database Documentation and Authentication & Security (§6–§7) | Superseded |
| 0.6 | ${DOC_DATE} | Engineering | Added Business Logic, User Flows and Module Documentation (§8–§10) | Superseded |
| 0.7 | ${DOC_DATE} | Engineering | Added Configuration, Deployment, Testing, Performance, Troubleshooting, Appendix and References (§11–§17) | Superseded |
| 1.0 | ${DOC_DATE} | Engineering | Consolidated master document: merged all parts, added cover page, document control, revision history, clickable table of contents, list of figures, list of tables, sequential figure and table numbering, and page-break formatting for PDF export. | Superseded |
| **${DOC_VERSION}** | **${REVISION_DATE}** | **Engineering** | **Corrected the signal-processing description: Hann amplitude scaling is \`2 / window.sum()\`, \`fft_lines\` is a line count (block = \`2 × fft_lines\`) with 50 %-overlap averaging, and the acquisition formula sizes captures at \`2 × lor\`. Documented \`GET /api/v1/dashboard/summary\` and \`GET /api/v1/lookups/plants\`, and rewrote the plant-selector and notification-bell entries, which are now wired to real data.** | **Current** |

## Document baseline

| Item | Value |
|---|---|
| Source revision | Working tree of branch \`laxman-dev\` |
| Backend version | 1.1.0 (\`backend/app/main.py\`) |
| Frontend version | 1.0.0 (\`frontend/package.json\`) |
| Database schema | Alembic revision \`011\` |
| Endpoints documented | 48 |
| Database tables documented | 17 |
| Database columns documented | 215 |
| Figures | ${figures.length} |
| Tables | ${tables.length} |

<div class="page-break"></div>

<a id="table-of-contents"></a>

# Table of Contents

- [Cover Page](#cover)
- [Document Control](#document-control)
- [Revision History](#revision-history)
- [Table of Contents](#table-of-contents)
- [List of Figures](#list-of-figures)
- [List of Tables](#list-of-tables)

${tocMd}

<div class="page-break"></div>

<a id="list-of-figures"></a>

# List of Figures

| Figure | Subject |
|---|---|
${figuresMd}

<div class="page-break"></div>

<a id="list-of-tables"></a>

# List of Tables

| Table | Subject |
|---|---|
${tablesMd}

<div class="page-break"></div>
`;

const master = `${front}\n${annotated}\n`;
fs.writeFileSync(OUT_MD, master, "utf8");

// -------------------------------------------------------- print-ready HTML ---
const css = `
:root { --ink:#15366D; --accent:#FF6B00; --muted:#5C6B7A; --border:#E5E1DA; --bg:#FFFFFF; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Inter, system-ui, -apple-system, sans-serif;
       color:#1a2733; background:var(--bg); line-height:1.55; font-size:10.5pt;
       margin:0; padding:0 18mm; }
h1,h2,h3,h4 { color:var(--ink); font-weight:700; line-height:1.25; margin:1.4em 0 .5em; page-break-after:avoid; }
h1 { font-size:20pt; border-bottom:3px solid var(--accent); padding-bottom:.25em; }
h2 { font-size:15pt; border-bottom:1px solid var(--border); padding-bottom:.2em; }
h3 { font-size:12.5pt; } h4 { font-size:11pt; color:var(--muted); }
p, li { orphans:3; widows:3; }
a { color:var(--ink); text-decoration:none; }
a:hover { text-decoration:underline; }
code { font-family:"Cascadia Mono",Consolas,monospace; font-size:9.2pt;
       background:#F5F3EF; padding:.1em .35em; border-radius:3px; }
pre { background:#FAF9F6; border:1px solid var(--border); border-left:3px solid var(--accent);
      border-radius:4px; padding:10px 12px; overflow-x:auto; page-break-inside:avoid; font-size:9pt; }
pre code { background:none; padding:0; }
table { border-collapse:collapse; width:100%; margin:.6em 0 1.1em; font-size:9.2pt; page-break-inside:avoid; }
th { background:#F5F3EF; color:var(--ink); font-weight:600; text-align:left; }
th, td { border:1px solid var(--border); padding:5px 8px; vertical-align:top; }
tbody tr:nth-child(even) { background:#FCFBF9; }
blockquote { border-left:3px solid var(--accent); background:#FFF8F2; margin:1em 0;
             padding:.6em 1em; color:#3a4654; }
em { color:var(--muted); }
p > em:only-child { display:block; font-size:8.8pt; letter-spacing:.02em; margin:.2em 0 .8em; }
.page-break { page-break-after:always; break-after:page; height:0; }
.cover { text-align:center; padding-top:38mm; }
.cover h1 { font-size:40pt; border:none; letter-spacing:-.02em; margin-bottom:0; }
.cover h2 { font-size:16pt; border:none; color:var(--accent); font-weight:600; margin-top:.3em; }
.cover h3 { font-size:13pt; color:var(--muted); font-weight:500; margin-top:1.6em; }
.cover table { width:78%; margin:2.4em auto 0; text-align:left; }
.mermaid { page-break-inside:avoid; text-align:center; margin:1em 0; }
@page { size:A4; margin:16mm 0 16mm 0; }
@media print { body { padding:0 14mm; } a { color:inherit; } }
`;

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>SensoVibe — Technical Documentation v${DOC_VERSION}</title>
<style>${css}</style>
<script type="module">
  import { marked } from "https://cdn.jsdelivr.net/npm/marked@12/lib/marked.esm.js";
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

  mermaid.initialize({
    startOnLoad: false, theme: "neutral", securityLevel: "loose",
    maxTextSize: 500000, maxEdges: 2000, fontFamily: "Segoe UI, Inter, system-ui, sans-serif",
  });

  const target = document.getElementById("doc");
  target.innerHTML = marked.parse(document.getElementById("src").textContent, {
    gfm: true, breaks: false,
  });

  // Collect diagram sources, then render each one explicitly so that a failure
  // in one diagram can never prevent the others from rendering.
  const jobs = [...target.querySelectorAll("pre > code.language-mermaid")].map((el, i) => {
    const holder = document.createElement("div");
    holder.className = "mermaid";
    el.parentElement.replaceWith(holder);
    return { id: "mmd-" + i, code: el.textContent, holder };
  });

  let ok = 0, failed = 0;
  for (const job of jobs) {
    try {
      const { svg } = await mermaid.render(job.id, job.code);
      job.holder.innerHTML = svg;
      ok++;
    } catch (err) {
      failed++;
      job.holder.innerHTML =
        '<pre class="mermaid-fallback">' +
        job.code.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])) +
        "</pre>";
      console.error("mermaid render failed for " + job.id, err);
    }
  }
  document.body.dataset.mermaidOk = String(ok);
  document.body.dataset.mermaidFailed = String(failed);
  document.body.dataset.renderComplete = "true";
</script>
</head><body>
<script type="text/plain" id="src">${master.replace(/<\/script>/g, "<\\/script>")}</script>
<div id="doc"></div>
</body></html>`;

fs.writeFileSync(OUT_HTML, html, "utf8");

console.log(`Master markdown : ${OUT_MD}`);
console.log(`Print HTML      : ${OUT_HTML}`);
console.log(`Sections (h1)   : ${toc.filter((t) => t.level === 1).length}`);
console.log(`TOC entries     : ${toc.length}`);
console.log(`Figures         : ${figures.length}`);
console.log(`Tables          : ${tables.length}`);
console.log(`Lines           : ${master.split("\n").length}`);
