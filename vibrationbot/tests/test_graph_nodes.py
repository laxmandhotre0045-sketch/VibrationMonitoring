"""Node-level tests for the LangGraph vibration analyst.

Each node is exercised with a plain dict and a fake LLM, so nothing here
compiles a graph or touches the network.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from app.chat.graph import nodes
from app.chat.graph.state import GraphState, bump, new_state
from app.chat.graph.tools_domain import DomainContext
from app.chat.graph.tools_retrieval import RetrievalContext
from tests.fake_llm import FakeChatModel, make_get_chat_model, tool_call_message

SESSION = "test-session"


@pytest.fixture
def contexts():
    retrieval = RetrievalContext(allowed_docs=[], top_k=6)
    domain = DomainContext()
    nodes.set_turn_contexts(SESSION, retrieval, domain)
    yield retrieval, domain
    nodes.clear_turn_contexts(SESSION)


@pytest.fixture
def fake(monkeypatch):
    model = FakeChatModel()
    monkeypatch.setattr(nodes, "get_chat_model", make_get_chat_model(model))
    return model


def state(**overrides) -> GraphState:
    base = new_state(question="test question", session_id=SESSION, top_k=6)
    base.update(overrides)
    return base


class TestClassify:
    def test_extracts_route_and_stated_facts(self, fake, contexts):
        fake.responses["classify"] = nodes.RouteDecision(
            route="numeric",
            rewritten_query="bearing fault frequency 6205",
            bearing_designation="6205",
            shaft_rpm=1750,
        )
        result = nodes.classify(state())

        assert result["route"] == "numeric"
        assert result["retrieval_query"] == "bearing fault frequency 6205"
        assert result["stated_facts"]["shaft_rpm"] == 1750
        assert result["stated_facts"]["bearing_designation"] == "6205"

    def test_omits_facts_the_user_did_not_state(self, fake, contexts):
        """A guessed RPM silently corrupts every frequency derived from it."""
        fake.responses["classify"] = nodes.RouteDecision(route="theory", rewritten_query="oil whirl")
        result = nodes.classify(state())

        assert "shaft_rpm" not in result["stated_facts"]
        assert "foundation" not in result["stated_facts"]

    def test_request_machine_id_beats_the_models_guess(self, fake, contexts):
        fake.responses["classify"] = nodes.RouteDecision(
            route="data", rewritten_query="q", machine_id="WRONG-1"
        )
        result = nodes.classify(state(machine_id="P-101"))
        assert result["machine_id"] == "P-101"

    def test_classification_failure_defaults_to_hybrid(self, monkeypatch, contexts):
        """Routing must never be able to fail the whole turn."""

        def boom(*_a, **_k):
            raise RuntimeError("api down")

        monkeypatch.setattr(nodes, "get_chat_model", boom)
        assert nodes.classify(state())["route"] == "hybrid"


class TestGrade:
    def _fake_chunks(self, n=3):
        return [
            {"text": f"excerpt {i}", "chunk_id": f"c{i}", "doc_id": "d", "score": 1.0}
            for i in range(1, n + 1)
        ]

    def test_keeps_only_relevant_excerpts(self, fake, contexts):
        fake.responses["grade"] = nodes.GradeResult(
            grades=[
                nodes.ExcerptGrade(index=1, relevant=True),
                nodes.ExcerptGrade(index=2, relevant=False, reason="different topic"),
                nodes.ExcerptGrade(index=3, relevant=True),
            ]
        )
        result = nodes.grade(state(retrieved=self._fake_chunks()))

        assert [c["chunk_id"] for c in result["graded"]] == ["c1", "c3"]

    def test_grades_everything_in_one_call(self, fake, contexts):
        """Per-excerpt calls would cost top_k times as much for a binary decision."""
        fake.responses["grade"] = nodes.GradeResult(
            grades=[nodes.ExcerptGrade(index=i, relevant=True) for i in range(1, 7)]
        )
        nodes.grade(state(retrieved=self._fake_chunks(6)))
        assert fake.count("grade") == 1

    def test_grader_failure_keeps_everything(self, monkeypatch, contexts):
        def boom(*_a, **_k):
            raise RuntimeError("api down")

        monkeypatch.setattr(nodes, "get_chat_model", boom)
        chunks = self._fake_chunks()
        assert nodes.grade(state(retrieved=chunks))["graded"] == chunks

    def test_empty_retrieval_short_circuits(self, fake, contexts):
        assert nodes.grade(state(retrieved=[]))["graded"] == []
        assert fake.count("grade") == 0


class TestExecuteTools:
    def test_artifact_becomes_a_computation_with_an_id(self, fake, contexts):
        """The record must reach state; only the summary reaches the model."""
        message = tool_call_message(
            "bearing_fault_frequencies", {"designation": "6205", "shaft_rpm": 1750}
        )
        result = nodes.execute_tools(state(messages=[message]))

        assert len(result["computations"]) == 1
        record = result["computations"][0]
        assert record["id"] == "C1"
        assert record["tool"] == "bearing_fault_frequencies"
        assert record["outputs"]["BPFO_hz"] == pytest.approx(104.56, abs=0.05)
        assert "104.56" in record["summary_text"]

    def test_computation_ids_continue_across_loops(self, fake, contexts):
        message = tool_call_message("bearing_fault_frequencies", {"designation": "6205", "shaft_rpm": 1750})
        result = nodes.execute_tools(state(messages=[message], computations=[{"id": "C1"}]))
        assert result["computations"][0]["id"] == "C2"

    def test_tool_loop_counter_increments(self, fake, contexts):
        message = tool_call_message("bearing_fault_frequencies", {"designation": "6205", "shaft_rpm": 1750})
        assert nodes.execute_tools(state(messages=[message], tool_loops=2))["tool_loops"] == 3

    def test_unknown_tool_does_not_crash_the_turn(self, fake, contexts):
        result = nodes.execute_tools(state(messages=[tool_call_message("no_such_tool", {})]))
        assert result["computations"] == []
        assert "Unknown tool" in result["messages"][0].content

    def test_tool_returning_no_artifact_records_nothing(self, fake, contexts):
        """A tool that cannot compute must not manufacture a computation record."""
        message = tool_call_message("bearing_fault_frequencies", {"designation": "22312"})
        result = nodes.execute_tools(state(messages=[message]))

        assert result["computations"] == []
        assert "Cannot compute" in result["messages"][0].content


class TestGenerate:
    def test_computed_block_reaches_the_prompt(self, fake, contexts):
        fake.responses["generate"] = "BPFO is 104.56 Hz."
        computations = [
            {
                "id": "C1",
                "tool": "bearing_fault_frequencies",
                "inputs": {"designation": "6205", "shaft_rpm": 1750},
                "outputs": {"BPFO_hz": 104.56},
                "summary_text": "BPFO = 104.56 Hz (3.585x)",
                "formula": "BPFO=(n/2)(1-r)fr",
                "assumptions": ["pure rolling, no slip"],
                "confidence": 1.0,
            }
        ]
        nodes.generate(state(computations=computations, route="numeric"))

        prompt = fake.calls[-1]["messages"][-1].content
        assert "<COMPUTED>" in prompt
        assert "104.56" in prompt
        assert "pure rolling" in prompt

    def test_chitchat_skips_retrieval_entirely(self, fake, contexts):
        fake.responses["generate"] = "Hello!"
        result = nodes.generate(state(route="chitchat"))

        assert result["answer"] == "Hello!"
        assert "<COMPUTED>" not in fake.calls[-1]["messages"]

    def test_regeneration_appends_the_unsupported_claims(self, fake, contexts):
        fake.responses["generate"] = "revised"
        nodes.generate(
            state(route="numeric", regen_count=1, stated_facts={"_unsupported": ["invented 7.1 mm/s limit"]})
        )
        assert "invented 7.1 mm/s limit" in fake.calls[-1]["messages"][-1].content


class TestGroundedness:
    def test_grounded_answer_passes(self, fake, contexts):
        fake.responses["verify"] = nodes.GroundednessResult(grounded=True)
        assert nodes.check_groundedness(state(answer="x", route="numeric"))["grounded"] is True

    def test_ungrounded_answer_records_claims_and_bumps_counter(self, fake, contexts):
        fake.responses["verify"] = nodes.GroundednessResult(
            grounded=False, unsupported_claims=["made-up threshold"]
        )
        result = nodes.check_groundedness(state(answer="x", route="numeric"))

        assert result["grounded"] is False
        assert result["regen_count"] == 1
        assert result["stated_facts"]["_unsupported"] == ["made-up threshold"]

    def test_checker_failure_never_blocks_an_answer(self, monkeypatch, contexts):
        def boom(*_a, **_k):
            raise RuntimeError("api down")

        monkeypatch.setattr(nodes, "get_chat_model", boom)
        assert nodes.check_groundedness(state(answer="x", route="numeric"))["grounded"] is True

    def test_chitchat_and_fallback_are_not_checked(self, fake, contexts):
        nodes.check_groundedness(state(answer="hi", route="chitchat"))
        nodes.check_groundedness(state(answer="x", route="numeric", used_fallback=True))
        assert fake.count("verify") == 0


class TestFormatting:
    def test_computations_render_inputs_formula_and_assumptions(self):
        text = nodes.format_computations(
            [
                {
                    "id": "C1",
                    "tool": "iso_severity_zone",
                    "inputs": {"velocity_rms_mm_s": 4.9, "machine_group": 3, "foundation": None},
                    "outputs": {"zone": "C"},
                    "summary_text": "Zone C",
                    "formula": "table lookup",
                    "assumptions": ["10-1000 Hz broadband"],
                    "confidence": 1.0,
                    "supporting_chunk_id": "chunk_42",
                    "supporting_doc_id": "iso_10816_3",
                }
            ]
        )

        assert "[C1]" in text
        assert "velocity_rms_mm_s=4.9" in text
        assert "foundation" not in text  # None inputs are omitted
        assert "10-1000 Hz broadband" in text
        assert "iso_10816_3#chunk_42" in text

    def test_no_computations_says_so_explicitly(self):
        assert "No calculations" in nodes.format_computations([])

    def test_excerpts_carry_page_and_section(self):
        text = nodes.format_excerpts(
            [{"text": "body", "section_path": "Ch 2 > Bearings", "page_start": 71,
              "page_end": 73, "chunk_type": "clause", "doc_id": "book"}]
        )
        assert "pp.71-73" in text
        assert "Ch 2 > Bearings" in text

    def test_single_page_excerpt_uses_singular_form(self):
        text = nodes.format_excerpts(
            [{"text": "b", "section_path": "S", "page_start": 5, "page_end": 5,
              "chunk_type": "clause", "doc_id": "d"}]
        )
        assert "p.5" in text and "pp." not in text


def test_bump_returns_absolute_value_not_a_delta():
    """These counters overwrite; returning a delta would double them."""
    assert bump({}, "rewrite_count") == 1
    assert bump({"rewrite_count": 1}, "rewrite_count") == 2
    assert bump({"rewrite_count": None}, "rewrite_count") == 1
