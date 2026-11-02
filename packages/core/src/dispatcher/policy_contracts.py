"""Declarative routing and evaluation inputs; model capability claims are operator supplied."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from dispatcher.contracts import Contract

Name = Annotated[str, Field(min_length=1, max_length=100)]


class Variant(Contract):
    """A weighted candidate uses a LiteLLM model alias configured by the operator."""

    name: Name
    model: Name
    weight: int = Field(default=1, ge=1, le=10000)


class Experiment(Contract):
    """Immutable experiment settings keep assignments and comparisons reproducible."""

    id: UUID = Field(default_factory=uuid4)
    name: Name
    app: Name
    environment: Name
    seed: Name
    variants: list[Variant] = Field(min_length=2, max_length=10)
    baseline: Name
    minimum_tasks: int = Field(default=30, ge=2, le=100000)
    minimum_quality: Decimal = Field(default=Decimal("0.9"), ge=0, le=1)
    quality_margin: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    maximum_latency_ms: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    configuration_source: Name | None = None
    configuration_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def distinct_variants(self):
        """Reject ambiguous labels and comparisons of a model against itself."""
        if len({variant.name for variant in self.variants}) != len(self.variants):
            raise ValueError("Variant names must be unique")
        if len({variant.model for variant in self.variants}) != len(self.variants):
            raise ValueError("Variant models must be distinct")
        if self.baseline not in {variant.name for variant in self.variants}:
            raise ValueError("Baseline must name a configured variant")
        if (self.configuration_source is None) != (self.configuration_digest is None):
            raise ValueError("Configuration evaluation requires both source and content digest")
        return self


class ModelPolicy(Contract):
    """One active policy per app/environment; explicit capabilities gate every route."""

    id: Name
    app: Name
    environment: Name
    allowed_models: list[Name] = Field(min_length=1, max_length=100)
    primary: Name | None = None
    fallbacks: list[Name] = Field(default_factory=list, max_length=10)
    required_capabilities: list[Name] = Field(default_factory=list, max_length=30)
    model_capabilities: dict[Name, list[Name]] = Field(default_factory=dict)
    experiment_id: UUID | None = None

    @model_validator(mode="after")
    def compatible_routes(self):
        """Capability declarations are mandatory when the task has compatibility requirements."""
        routes = self.allowed_models
        if len(set(routes)) != len(routes) or len(set(self.fallbacks)) != len(self.fallbacks):
            raise ValueError("Model lists must not contain duplicates")
        if (self.primary and self.primary not in routes) or set(self.fallbacks) - set(routes):
            raise ValueError("Primary and fallback aliases must be allowed models")
        required = set(self.required_capabilities)
        for model in routes:
            if not required.issubset(self.model_capabilities.get(model, [])):
                raise ValueError("Each allowed model must satisfy declared task capabilities")
        return self


class TaskOutcome(Contract):
    """Final app-provided feedback for the whole assigned task, without prompts or outputs."""

    assignment_id: UUID
    app: Name
    environment: Name
    status: Literal["completed", "failed"]
    quality: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    duration_ms: Decimal = Field(ge=0, allow_inf_nan=False)
    coverage_complete: bool
    fees_accounted: bool
    additional_cost: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    evaluator: Name
