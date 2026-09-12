"""Internal construct models used behind the shared adapter interface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int
    end: int


class Feature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    start: int
    end: int
    strand: int | None = 1
    qualifiers: dict[str, list[str]] = Field(default_factory=dict)
    parts: list[Location] | None = None

    @field_validator("qualifiers", mode="before")
    @classmethod
    def normalize_qualifiers(cls, value: Any) -> dict[str, list[str]]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("qualifiers must be an object")
        return {
            str(key): [str(item) for item in values]
            if isinstance(values, (list, tuple))
            else [str(values)]
            for key, values in value.items()
        }

    def locations(self) -> list[Location]:
        return self.parts or [Location(start=self.start, end=self.end)]

    def summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "start": self.start,
            "end": self.end,
            "strand": self.strand,
            "qualifiers": self.qualifiers,
        }
        if self.parts:
            result["parts"] = [part.model_dump(mode="json") for part in self.parts]
        return result


class Construct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sequence: str
    topology: str = "linear"
    features: list[Feature] = Field(default_factory=list)
    primers: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sequence", mode="before")
    @classmethod
    def normalize_sequence(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise TypeError("sequence must be a string")
        return "".join(value.split()).upper()
