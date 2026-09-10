"""Unit tests for extraction-side fixes: section nesting and node backfill."""

from app.ingestion.document_multimodal_pipeline import (
    MAX_SECTION_DEPTH,
    _push_section,
)
from app.ingestion.document_pdf_pipeline import _build_nodes


def test_section_stack_is_bounded_without_level_info():
    """Regression: the stack was appended to but never popped."""
    stack: list[str] = []
    for i in range(200):
        _push_section(stack, f"Heading {i}", None)
    assert len(stack) <= MAX_SECTION_DEPTH
    assert stack[-1] == "Heading 199"


def test_section_stack_truncates_to_level():
    stack: list[str] = []
    _push_section(stack, "Chapter 1", 0)
    _push_section(stack, "Section 1.1", 1)
    _push_section(stack, "Clause 1.1.1", 2)
    assert stack == ["Chapter 1", "Section 1.1", "Clause 1.1.1"]

    # A new level-1 heading replaces the deeper entries rather than stacking.
    _push_section(stack, "Section 1.2", 1)
    assert stack == ["Chapter 1", "Section 1.2"]

    _push_section(stack, "Chapter 2", 0)
    assert stack == ["Chapter 2"]


def test_section_path_stays_small_over_a_long_document():
    """The symptom the bound exists to prevent: multi-KB section paths."""
    stack: list[str] = []
    for i in range(500):
        _push_section(stack, f"A Fairly Long Heading Title Number {i}", None)
        assert len(" > ".join(stack)) < 500


def _legacy_backfill(nodes):
    """The original O(n^2) backfill, for equivalence checking."""
    for node in nodes:
        if not node.text:
            child_texts = [n.text for n in nodes if n.parent_id == node.node_id and n.text]
            if child_texts:
                node.text = " ".join(child_texts[:3])[:500]
    return [(n.node_id, n.text) for n in nodes]


def test_backfill_is_equivalent_to_the_original_algorithm():
    """The O(n^2) -> linear change must be purely a performance change.

    Note this preserves an existing quirk: the backfill is a single ordered
    pass, so a chapter whose children are all (still empty) sections is not
    back-filled. That behaviour is unchanged here by design.
    """
    pages = [
        {
            "page_num": 1,
            "text": "\n".join(
                [
                    "CHAPTER 1",
                    "1.1 First Section",
                    "This is the body text of the first clause which is long enough.",
                    "1.2 Second Section",
                    "This is the body text of the second clause which is long enough.",
                    "CHAPTER 2",
                    "2.1 Another Section",
                    "Yet more body text here that comfortably exceeds the minimum.",
                ]
            ),
        }
    ]

    new_result = [(n.node_id, n.text) for n in _build_nodes(pages, "doc")]

    # Rebuild, strip the back-filled text, then re-apply the legacy algorithm.
    raw = _build_nodes(pages, "doc")
    for node in raw:
        node.text = node.text if node.node_type in ("clause", "table") else ""
    legacy_result = _legacy_backfill(raw)

    assert new_result == legacy_result


def test_backfill_pulls_from_own_children_and_caps_length():
    pages = [
        {
            "page_num": 1,
            "text": "\n".join(
                [
                    "1.1 First Section",
                    "This is the body text of the first clause which is long enough.",
                    "1.2 Second Section",
                    "This is the body text of the second clause which is long enough.",
                ]
            ),
        }
    ]
    nodes = _build_nodes(pages, "doc")
    by_id = {n.node_id: n for n in nodes}

    filled = [n for n in nodes if n.node_type == "section" and n.text]
    assert filled, "sections with clause children should be back-filled"

    for node in filled:
        children = [c for c in nodes if c.parent_id == node.node_id and c.text]
        assert any(node.text.startswith(c.text[:30]) for c in children)
        assert len(node.text) <= 500

    for node in nodes:
        if node.parent_id:
            assert node.parent_id in by_id


def test_build_nodes_scales_linearly_with_headings():
    """Regression guard for the O(n^2) backfill on heading-rich documents."""
    import time

    def make_pages(n_headings):
        lines = []
        for i in range(n_headings):
            lines.append(f"{i}.1 Section Heading Number {i}")
            lines.append(f"Body text for section {i} that is definitely long enough.")
        return [{"page_num": 1, "text": "\n".join(lines)}]

    t0 = time.perf_counter()
    _build_nodes(make_pages(200), "d")
    small = time.perf_counter() - t0

    t0 = time.perf_counter()
    _build_nodes(make_pages(1600), "d")
    large = time.perf_counter() - t0

    # 8x the input. Quadratic would be ~64x; allow generous headroom for noise.
    assert large < max(small * 24, 0.5), f"small={small:.4f}s large={large:.4f}s"


# ---------------------------------------------------------------------------
# Parallel table extraction
# ---------------------------------------------------------------------------


def test_parallel_and_serial_table_extraction_agree(tmp_path):
    """Parallelism must be a pure performance change, not a behaviour change."""
    import fitz

    from app.ingestion.document_pdf_pipeline import (
        _extract_tables,
        _extract_tables_serial,
    )

    pdf_path = tmp_path / "tables.pdf"
    doc = fitz.open()
    for i in range(60):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i} heading")
        if i % 17 == 0:  # tables on a few scattered pages
            for row in range(4):
                y = 100 + row * 20
                page.draw_line((72, y), (400, y))
                page.insert_text((80, y - 5), f"r{row}c0 | r{row}c1")
            for x in (72, 240, 400):
                page.draw_line((x, 100), (x, 160))
    doc.save(str(pdf_path))
    n_pages = len(doc)
    doc.close()

    serial = _extract_tables_serial(pdf_path, n_pages)
    parallel = _extract_tables(pdf_path, n_pages)
    assert serial == parallel


def test_small_documents_use_the_serial_path(tmp_path, monkeypatch):
    """Process startup would outweigh the saving below the threshold."""
    import fitz

    from app.ingestion import document_pdf_pipeline as pdf_mod

    pdf_path = tmp_path / "small.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "hello")
    doc.save(str(pdf_path))
    doc.close()

    called = []
    monkeypatch.setattr(
        pdf_mod,
        "ProcessPoolExecutor",
        lambda *a, **k: called.append(1) or (_ for _ in ()).throw(AssertionError("pool used")),
    )
    assert pdf_mod._extract_tables(pdf_path, 1) == {}
    assert not called


def test_table_extraction_falls_back_when_pool_fails(tmp_path, monkeypatch):
    import fitz

    from app.ingestion import document_pdf_pipeline as pdf_mod

    pdf_path = tmp_path / "big.pdf"
    doc = fitz.open()
    for _ in range(50):
        doc.new_page().insert_text((72, 72), "text")
    doc.save(str(pdf_path))
    n_pages = len(doc)
    doc.close()

    def boom(*a, **k):
        raise OSError("no subprocesses here")

    monkeypatch.setattr(pdf_mod, "ProcessPoolExecutor", boom)
    # Must not raise — ingest never fails over table extraction.
    assert pdf_mod._extract_tables(pdf_path, n_pages) == {}
