from __future__ import annotations

from modelforge.agents.base import AgentContext
from modelforge.agents.problem_parser import ProblemParserAgent
from modelforge.providers.llm import MockProvider
from modelforge.schemas.problem import FileManifest, InputManifest


def _manifest(text: str) -> InputManifest:
    return InputManifest(
        run_id="run_test",
        problem_text=text,
        files=[
            FileManifest(
                file_id="f_problem",
                original_name="problem.txt",
                normalized_name="problem.txt",
                content_hash="h",
                mime_type="text/plain",
                size_bytes=len(text.encode()),
                role="problem",
            ),
            FileManifest(
                file_id="f_soil",
                original_name="soil.csv",
                normalized_name="soil.csv",
                content_hash="h2",
                mime_type="text/csv",
                size_bytes=10,
                role="data",
            ),
            FileManifest(
                file_id="f_weather",
                original_name="weather.csv",
                normalized_name="weather.csv",
                content_hash="h3",
                mime_type="text/csv",
                size_bytes=10,
                role="data",
            ),
        ],
    )


def test_irrigation_problem_parser_extracts_subproblems_without_qubo_core() -> None:
    title = "\u519c\u4e1a\u704c\u6e89\u7cfb\u7edf\u4f18\u5316"
    text = (
        f"{title}\n"
        "Use soil moisture records and weather observations to estimate crop water "
        "demand, then optimize irrigation scheduling under cost and water limits."
    )
    ctx = AgentContext(run_id="run_test", provider=MockProvider())
    result = ProblemParserAgent(ctx).parse(_manifest(text))

    assert result.ok, result.failure
    card = result.output
    assert card.title == title
    assert len(card.subproblems) >= 3
    subproblem_text = " ".join(sp.statement + " " + sp.objective for sp in card.subproblems)
    assert "soil moisture" in subproblem_text.lower()
    assert "weather" in subproblem_text.lower()
    assert "scheduling" in subproblem_text.lower()
    assert "qubo" not in card.problem_summary.lower()
    assert "quantum" not in card.problem_summary.lower()
    assert any("qubo" in item.lower() for item in card.forbidden_misreadings)
    assert all("qubo" not in sp.statement.lower() for sp in card.subproblems)
