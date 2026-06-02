"""Method library loader with search, filtering, and suitability ranking.

Retrieval is deterministic and entirely local (spec 8.3 invariant: retrieved
methods come from registered library entries). Ranking scores a method by how
well its problem families and keyword surface match the problem/domain.
"""

from __future__ import annotations

from functools import lru_cache

from modelforge.schemas.enums import MethodCategory, ProblemFamily
from modelforge.schemas.problem import DomainAnalysis, ProblemCard, RetrievedMethod
from modelforge.services.method_library.records import METHOD_FAMILIES, METHODS


class MethodLibrary:
    def __init__(self, methods: list[RetrievedMethod] | None = None) -> None:
        self._methods = methods if methods is not None else list(METHODS)
        self._by_id = {m.method_id: m for m in self._methods}

    # ------------------------------------------------------------------ #
    def all(self) -> list[RetrievedMethod]:
        return list(self._methods)

    def get(self, method_id: str) -> RetrievedMethod | None:
        return self._by_id.get(method_id)

    def by_category(self, category: MethodCategory) -> list[RetrievedMethod]:
        return [m for m in self._methods if m.category is category]

    def by_family(self, family: ProblemFamily) -> list[RetrievedMethod]:
        return [
            m for m in self._methods if family in METHOD_FAMILIES.get(m.method_id, [])
        ]

    def families_for(self, method_id: str) -> list[ProblemFamily]:
        return METHOD_FAMILIES.get(method_id, [])

    def search(self, query: str) -> list[RetrievedMethod]:
        q = query.lower()
        return [
            m
            for m in self._methods
            if q in m.name.lower()
            or q in m.summary.lower()
            or any(q in uc.lower() for uc in m.use_cases)
        ]

    # ------------------------------------------------------------------ #
    def retrieve(
        self,
        problem_card: ProblemCard,
        domain_analysis: DomainAnalysis,
        *,
        top_k: int = 8,
    ) -> list[RetrievedMethod]:
        """Rank methods by family overlap + keyword surface, return top_k.

        Returns copies with ``suitability_score`` populated, so callers see the
        ranking without mutating the library.
        """
        families = set(domain_analysis.likely_problem_families) or {ProblemFamily.UNKNOWN}
        text = " ".join(
            [
                problem_card.title,
                problem_card.problem_summary,
                problem_card.objective_summary,
                " ".join(problem_card.objectives),
                " ".join(domain_analysis.domain_tags),
                " ".join(domain_analysis.key_terms),
            ]
        ).lower()

        scored: list[tuple[float, RetrievedMethod]] = []
        for method in self._methods:
            method_families = set(METHOD_FAMILIES.get(method.method_id, []))
            family_overlap = len(method_families & families)
            score = 0.0
            if family_overlap:
                score += 0.6 * min(1.0, family_overlap)
            # Keyword surface: use-case / name term hits.
            terms = [*method.use_cases, method.name]
            hits = sum(1 for t in terms if any(w in text for w in t.lower().split()))
            score += 0.4 * min(1.0, hits / max(1, len(terms)))
            if score > 0:
                ranked = method.model_copy(update={"suitability_score": round(score, 4)})
                scored.append((score, ranked))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        result = [m for _, m in scored[:top_k]]
        # Guarantee at least one method so downstream stages are not starved.
        if not result and self._methods:
            fallback = self._methods[0].model_copy(update={"suitability_score": 0.1})
            result = [fallback]
        return result


@lru_cache(maxsize=1)
def get_method_library() -> MethodLibrary:
    return MethodLibrary()
