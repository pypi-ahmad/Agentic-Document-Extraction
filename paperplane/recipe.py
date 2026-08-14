"""Versioned processing recipes with an operator rollback path."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RecipeVersion = Literal["v8", "v9"]


class VerificationBudget(BaseModel):
    max_terra_calls_per_page: int = Field(ge=0)
    max_crop_calls_per_page: int = Field(ge=0)


class ProcessingRecipe(BaseModel):
    version: RecipeVersion
    prompt_version: str
    verification_budgets: dict[str, VerificationBudget]


_RECIPES = {
    "v8": ProcessingRecipe(
        version="v8",
        prompt_version="v8",
        verification_budgets={
            "economy": VerificationBudget(max_terra_calls_per_page=0, max_crop_calls_per_page=0),
            "balanced": VerificationBudget(max_terra_calls_per_page=99, max_crop_calls_per_page=99),
            "audit": VerificationBudget(max_terra_calls_per_page=99, max_crop_calls_per_page=99),
        },
    ),
    "v9": ProcessingRecipe(
        version="v9",
        prompt_version="v8",
        verification_budgets={
            "economy": VerificationBudget(max_terra_calls_per_page=0, max_crop_calls_per_page=0),
            "balanced": VerificationBudget(max_terra_calls_per_page=2, max_crop_calls_per_page=1),
            "audit": VerificationBudget(max_terra_calls_per_page=6, max_crop_calls_per_page=5),
        },
    ),
}


def processing_recipe(version: RecipeVersion) -> ProcessingRecipe:
    return _RECIPES[version].model_copy(deep=True)


__all__ = ["ProcessingRecipe", "RecipeVersion", "VerificationBudget", "processing_recipe"]
