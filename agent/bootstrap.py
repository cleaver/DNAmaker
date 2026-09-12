"""Load independently developed component adapters into the MCP process."""

from __future__ import annotations

import importlib
import os
from typing import Any

from .errors import WorkflowError
from .session import WorkflowManager


def _load_factory(setting: str) -> Any:
    value = os.environ.get(setting)
    if not value:
        raise WorkflowError("adapter_unconfigured", f"Set {setting} to a 'module:factory' reference.")
    try:
        module_name, factory_name = value.split(":", 1)
        factory = getattr(importlib.import_module(module_name), factory_name)
    except (ValueError, AttributeError, ModuleNotFoundError) as error:
        raise WorkflowError("adapter_configuration_invalid", f"Invalid {setting} value: {value}") from error
    return factory()


class UnavailableSnapGene:
    """Permit biology-only workflows without a desktop installation."""

    def __getattr__(self, name: str) -> Any:
        def unavailable(*args: Any, **kwargs: Any) -> Any:
            raise WorkflowError("snapgene_unavailable", "The SnapGene adapter has not been configured.")
        return unavailable


def manager_from_environment() -> WorkflowManager:
    """Build the production manager from factories owned by Persons 1 and 2."""
    biology = _load_factory("DNA_MAKER_BIOLOGY_ADAPTER")
    snapgene = (_load_factory("DNA_MAKER_SNAPGENE_ADAPTER")
                if os.environ.get("DNA_MAKER_SNAPGENE_ADAPTER") else UnavailableSnapGene())
    return WorkflowManager(biology, snapgene)
