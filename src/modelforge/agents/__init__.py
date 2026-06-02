"""Reasoning agents (spec section 8).

Each agent has a typed input model, a typed output model, a versioned prompt, and
bounded retry with one repair attempt. Agents record model-call metadata
(provider, model, tokens, cost, latency) for observability (spec 31) and never
fabricate experiment metrics (working rule 5).
"""

from modelforge.agents.base import AgentContext, AgentResult, BaseAgent
from modelforge.agents.code_author import CodeAuthorAgent
from modelforge.agents.debugger import DebuggerAgent
from modelforge.agents.domain_analyst import DomainAnalystAgent
from modelforge.agents.method_retriever import MethodRetrieverAgent
from modelforge.agents.paper_architect import PaperArchitectAgent
from modelforge.agents.paper_writer import PaperWriterAgent
from modelforge.agents.problem_parser import ProblemParserAgent
from modelforge.agents.skeptic import SkepticAgent
from modelforge.agents.strategy_judge import StrategyJudgeAgent
from modelforge.agents.strategy_proposer import StrategyProposerAgent

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "CodeAuthorAgent",
    "DebuggerAgent",
    "DomainAnalystAgent",
    "MethodRetrieverAgent",
    "PaperArchitectAgent",
    "PaperWriterAgent",
    "ProblemParserAgent",
    "SkepticAgent",
    "StrategyJudgeAgent",
    "StrategyProposerAgent",
]
