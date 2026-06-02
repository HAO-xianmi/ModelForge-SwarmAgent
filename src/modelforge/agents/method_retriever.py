"""MethodRetrieverAgent (spec 8.3).

Retrieval is deterministic against the local method library (invariant: methods
come from registered entries), so this agent does not call the LLM — it ranks
library entries by the problem card + domain analysis. This is intentional:
spec 4.5 says deterministic work should be a deterministic service.
"""

from __future__ import annotations

from modelforge.schemas.problem import DomainAnalysis, ProblemCard, RetrievedMethod
from modelforge.services.method_library import MethodLibrary, get_method_library


class MethodRetrieverAgent:
    agent_key = "method_retriever"
    name = "MethodRetrieverAgent"

    def __init__(self, library: MethodLibrary | None = None) -> None:
        self.library = library or get_method_library()

    def retrieve(
        self,
        problem_card: ProblemCard,
        domain_analysis: DomainAnalysis,
        *,
        top_k: int = 8,
    ) -> list[RetrievedMethod]:
        return self.library.retrieve(problem_card, domain_analysis, top_k=top_k)
