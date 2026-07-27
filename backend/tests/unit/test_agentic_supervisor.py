from __future__ import annotations

from collections.abc import Mapping

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.agentic.supervisor import (
    SPECIALIST_ROLES,
    AdaptiveDocumentSupervisor,
    resolve_model_profile,
)


def test_profiles_expose_the_approved_wave_and_call_budgets() -> None:
    assert resolve_model_profile("paperplane-ade-fast-latest").max_waves == 1
    assert resolve_model_profile("paperplane-ade-fast-latest").max_specialist_calls == 4
    assert resolve_model_profile("paperplane-ade-latest").max_waves == 2
    assert resolve_model_profile("paperplane-ade-latest").max_specialist_calls == 10
    assert resolve_model_profile("paperplane-ade-audit-latest").max_waves == 3
    assert resolve_model_profile("paperplane-ade-audit-latest").max_specialist_calls == 20
    assert SPECIALIST_ROLES == frozenset(
        {
            "text_fidelity",
            "tables",
            "forms",
            "visual",
            "special_marks",
            "hierarchy_order",
        }
    )


@pytest.mark.asyncio
async def test_supervisor_enforces_fast_call_budget_and_records_safe_trace() -> None:
    calls: list[tuple[str, int]] = []

    async def assess(page: Mapping[str, object]) -> dict[str, object]:
        return {"roles": list(SPECIALIST_ROLES)}

    async def specialist(page: Mapping[str, object], role: str, wave: int) -> dict[str, object]:
        calls.append((role, wave))
        return {"role": role, "summary": f"checked {role}"}

    async def critic(
        page: Mapping[str, object], actions: list[Mapping[str, object]], wave: int
    ) -> dict[str, object]:
        return {"accepted": False, "request_roles": list(SPECIALIST_ROLES)}

    supervisor = AdaptiveDocumentSupervisor(assessor=assess, specialist=specialist, critic=critic)

    result = await supervisor.run_document(
        [{"page_number": 1, "content": "fixture"}],
        model="paperplane-ade-fast-latest",
        thread_id="fast-budget",
    )

    assert len(calls) == 4
    assert result["results"][0]["specialist_calls"] == 4
    assert result["results"][0]["waves_completed"] == 1
    assert all("chain_of_thought" not in event for event in result["trace"])
    assert all("reasoning" not in event for event in result["trace"])
    assert {event["model"] for event in result["trace"]} == {
        "gpt-5.6-luna",
        "gpt-5.6-terra",
    }


@pytest.mark.asyncio
async def test_supervisor_stops_after_accepted_first_wave() -> None:
    calls: list[tuple[str, int]] = []

    async def assess(page: Mapping[str, object]) -> dict[str, object]:
        return {"roles": ["tables", "forms"]}

    async def specialist(page: Mapping[str, object], role: str, wave: int) -> dict[str, object]:
        calls.append((role, wave))
        return {"role": role, "summary": "complete"}

    async def critic(
        page: Mapping[str, object], actions: list[Mapping[str, object]], wave: int
    ) -> dict[str, object]:
        return {"accepted": True, "request_roles": ["visual"]}

    supervisor = AdaptiveDocumentSupervisor(assessor=assess, specialist=specialist, critic=critic)
    result = await supervisor.run_document(
        [{"page_number": 7}], model="paperplane-ade-latest", thread_id="early-stop"
    )

    assert calls == [("tables", 1), ("forms", 1)]
    assert result["results"][0]["accepted"] is True
    assert result["results"][0]["waves_completed"] == 1
    assert result["results"][0]["stop_reason"] == "accepted"


@pytest.mark.asyncio
async def test_critic_routes_a_second_wave_to_only_its_requested_specialist() -> None:
    calls: list[tuple[str, int]] = []

    async def assess(page: Mapping[str, object]) -> dict[str, object]:
        return {"roles": ["text_fidelity"]}

    async def specialist(page: Mapping[str, object], role: str, wave: int) -> dict[str, object]:
        calls.append((role, wave))
        return {"role": role, "summary": "complete"}

    async def critic(
        page: Mapping[str, object], actions: list[Mapping[str, object]], wave: int
    ) -> dict[str, object]:
        if wave == 1:
            return {"accepted": False, "request_roles": ["tables"]}
        return {"accepted": True}

    supervisor = AdaptiveDocumentSupervisor(assessor=assess, specialist=specialist, critic=critic)
    result = await supervisor.run_document(
        [{"page_number": 1}], model="paperplane-ade-latest", thread_id="adaptive-routing"
    )

    assert calls == [("text_fidelity", 1), ("tables", 2)]
    assert result["results"][0]["waves_completed"] == 2
    assert result["results"][0]["accepted"] is True


@pytest.mark.asyncio
async def test_document_graph_uses_thread_id_checkpoints_and_page_fanout() -> None:
    async def assess(page: Mapping[str, object]) -> dict[str, object]:
        return {"roles": ["text_fidelity"]}

    async def specialist(page: Mapping[str, object], role: str, wave: int) -> dict[str, object]:
        return {"role": role, "summary": str(page["page_number"])}

    async def critic(
        page: Mapping[str, object], actions: list[Mapping[str, object]], wave: int
    ) -> dict[str, object]:
        return {"accepted": True}

    checkpointer = InMemorySaver()
    supervisor = AdaptiveDocumentSupervisor(
        assessor=assess,
        specialist=specialist,
        critic=critic,
        checkpointer=checkpointer,
    )
    result = await supervisor.run_document(
        [{"page_number": 1}, {"page_number": 2}],
        model="paperplane-ade-latest",
        thread_id="parallel-pages",
    )

    assert [item["page_number"] for item in result["results"]] == [1, 2]
    checkpoint = checkpointer.get_tuple({"configurable": {"thread_id": "parallel-pages"}})
    assert checkpoint is not None
