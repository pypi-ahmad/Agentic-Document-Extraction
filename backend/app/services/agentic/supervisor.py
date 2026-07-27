"""Adaptive page supervision backed by a LangGraph document fan-out graph."""

from __future__ import annotations

import asyncio
import operator
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

Role = Literal[
    "text_fidelity",
    "tables",
    "forms",
    "visual",
    "special_marks",
    "hierarchy_order",
]

SPECIALIST_ROLE_ORDER: tuple[Role, ...] = (
    "text_fidelity",
    "tables",
    "forms",
    "visual",
    "special_marks",
    "hierarchy_order",
)
SPECIALIST_ROLES = frozenset(SPECIALIST_ROLE_ORDER)


@dataclass(frozen=True)
class ModelProfile:
    alias: str
    max_waves: int
    max_specialist_calls: int


_MODEL_PROFILES = {
    "paperplane-ade-fast-latest": ModelProfile(
        alias="paperplane-ade-fast-latest", max_waves=1, max_specialist_calls=4
    ),
    "paperplane-ade-latest": ModelProfile(
        alias="paperplane-ade-latest", max_waves=2, max_specialist_calls=10
    ),
    "paperplane-ade-audit-latest": ModelProfile(
        alias="paperplane-ade-audit-latest", max_waves=3, max_specialist_calls=20
    ),
}


def resolve_model_profile(alias: str) -> ModelProfile:
    """Return the fixed runtime budget for a public Paperplane model alias."""
    try:
        return _MODEL_PROFILES[alias]
    except KeyError as exc:
        raise ValueError(f"Unsupported Paperplane model alias: {alias}") from exc


class PageAssessor(Protocol):
    async def __call__(self, page: Mapping[str, object]) -> Mapping[str, object]: ...


class Specialist(Protocol):
    async def __call__(
        self, page: Mapping[str, object], role: Role, wave: int
    ) -> Mapping[str, object]: ...


class Critic(Protocol):
    async def __call__(
        self,
        page: Mapping[str, object],
        actions: Sequence[Mapping[str, object]],
        wave: int,
    ) -> Mapping[str, object]: ...


class DocumentGraphState(TypedDict, total=False):
    pages: list[dict[str, object]]
    page: dict[str, object]
    model: str
    results: Annotated[list[dict[str, object]], operator.add]
    trace: Annotated[list[dict[str, object]], operator.add]


class AdaptiveDocumentSupervisor:
    """Runs bounded specialist waves for every page through a LangGraph fan-out."""

    def __init__(
        self,
        *,
        assessor: PageAssessor,
        specialist: Specialist,
        critic: Critic,
        checkpointer: Any | None = None,
    ) -> None:
        self._assessor = assessor
        self._specialist = specialist
        self._critic = critic
        self._graph = self._build_graph(checkpointer)

    async def run_document(
        self,
        pages: Sequence[Mapping[str, object]],
        *,
        model: str,
        thread_id: str,
    ) -> dict[str, object]:
        """Fan out independent page supervisors and retain a resumable checkpoint."""
        resolve_model_profile(model)
        state = await self._graph.ainvoke(
            {
                "pages": [dict(page) for page in pages],
                "model": model,
                "results": [],
                "trace": [],
            },
            config={"configurable": {"thread_id": thread_id}},
        )
        return {
            "results": sorted(state.get("results", []), key=lambda item: int(item["page_number"])),
            "trace": state.get("trace", []),
        }

    def _build_graph(self, checkpointer: Any | None) -> Any:
        graph = StateGraph(DocumentGraphState)

        def dispatch_pages(state: DocumentGraphState) -> list[Send]:
            return [
                Send("page_agent", {"page": page, "model": state["model"]})
                for page in state.get("pages", [])
            ]

        async def page_agent(state: DocumentGraphState) -> dict[str, object]:
            result, trace = await self._run_page(state["page"], state["model"])
            return {"results": [result], "trace": trace}

        graph.add_node("page_agent", page_agent)
        graph.add_conditional_edges(START, dispatch_pages, ["page_agent"])
        graph.add_edge("page_agent", END)
        return graph.compile(checkpointer=checkpointer)

    async def _run_page(
        self, page: Mapping[str, object], model_alias: str
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        profile = resolve_model_profile(model_alias)
        page_number = int(page["page_number"])
        trace: list[dict[str, object]] = []
        assessment = await self._assessor(page)
        requested_roles = _normalise_roles(assessment.get("roles"))
        trace.append(
            _trace_event(
                page_number, "assessment", "luna_worker", "gpt-5.6-luna", "specialists selected"
            )
        )

        calls = 0
        accepted = False
        stop_reason = "no_relevant_specialists"
        completed_waves = 0
        actions: list[dict[str, object]] = []
        for wave in range(1, profile.max_waves + 1):
            roles = requested_roles[: profile.max_specialist_calls - calls]
            if not roles:
                stop_reason = "call_budget_exhausted" if calls else "no_relevant_specialists"
                break

            completed_waves = wave
            specialist_responses = await asyncio.gather(
                *(self._specialist(page, role, wave) for role in roles)
            )
            wave_actions = [
                _safe_action(role, response)
                for role, response in zip(roles, specialist_responses, strict=True)
            ]
            actions.extend(wave_actions)
            calls += len(wave_actions)
            trace.extend(
                _trace_event(
                    page_number,
                    "specialist",
                    f"luna_{action['role']}",
                    "gpt-5.6-luna",
                    str(action["summary"]),
                    wave=wave,
                )
                for action in wave_actions
            )

            verdict = await self._critic(page, wave_actions, wave)
            accepted = bool(verdict.get("accepted", False))
            trace.append(
                _trace_event(
                    page_number,
                    "verdict",
                    "terra_critic",
                    "gpt-5.6-terra",
                    "accepted" if accepted else "additional work requested",
                    wave=wave,
                )
            )
            if accepted:
                stop_reason = "accepted"
                break
            if calls >= profile.max_specialist_calls:
                stop_reason = "call_budget_exhausted"
                break
            requested_roles = _normalise_roles(verdict.get("request_roles"))
            if not requested_roles:
                stop_reason = "no_additional_work"
                break
        else:
            stop_reason = "wave_budget_exhausted"

        return (
            {
                "page_number": page_number,
                "accepted": accepted,
                "waves_completed": completed_waves,
                "specialist_calls": calls,
                "stop_reason": stop_reason,
                "actions": actions,
            },
            trace,
        )


def _normalise_roles(value: object) -> list[Role]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    requested = {item for item in value if item in SPECIALIST_ROLES}
    return [role for role in SPECIALIST_ROLE_ORDER if role in requested]


def _safe_action(role: Role, response: Mapping[str, object]) -> dict[str, object]:
    summary = str(response.get("summary", "completed")).strip()[:500]
    return {"role": role, "summary": summary or "completed"}


def _trace_event(
    page_number: int,
    action: str,
    agent: str,
    model: str,
    summary: str,
    *,
    wave: int | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "page_number": page_number,
        "action": action,
        "agent": agent,
        "model": model,
        "summary": summary[:500],
    }
    if wave is not None:
        event["wave"] = wave
    return event


__all__ = [
    "SPECIALIST_ROLES",
    "AdaptiveDocumentSupervisor",
    "ModelProfile",
    "resolve_model_profile",
]
