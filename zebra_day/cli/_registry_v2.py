"""Explicit cli-core-yo v2 registration helpers for zebra_day."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

from cli_core_yo.registry import CommandRegistry
from cli_core_yo.spec import CommandPolicy

ZEBRA_RUNTIME_TAG = "zebra-runtime"

EXEMPT = CommandPolicy(runtime_guard="exempt")
EXEMPT_JSON = CommandPolicy(supports_json=True, runtime_guard="exempt")
EXEMPT_MUTATING = CommandPolicy(mutates_state=True, runtime_guard="exempt")
EXEMPT_MUTATING_JSON = CommandPolicy(
    mutates_state=True,
    supports_json=True,
    runtime_guard="exempt",
)
EXEMPT_MUTATING_INTERACTIVE = CommandPolicy(
    mutates_state=True,
    interactive=True,
    runtime_guard="exempt",
)

REQUIRED = CommandPolicy(runtime_guard="required", prereq_tags={ZEBRA_RUNTIME_TAG})
REQUIRED_JSON = CommandPolicy(
    supports_json=True,
    runtime_guard="required",
    prereq_tags={ZEBRA_RUNTIME_TAG},
)
REQUIRED_MUTATING = CommandPolicy(
    mutates_state=True,
    runtime_guard="required",
    prereq_tags={ZEBRA_RUNTIME_TAG},
)
REQUIRED_MUTATING_JSON = CommandPolicy(
    mutates_state=True,
    supports_json=True,
    runtime_guard="required",
    prereq_tags={ZEBRA_RUNTIME_TAG},
)
REQUIRED_MUTATING_INTERACTIVE = CommandPolicy(
    mutates_state=True,
    interactive=True,
    runtime_guard="required",
    prereq_tags={ZEBRA_RUNTIME_TAG},
)
REQUIRED_LONG_RUNNING = CommandPolicy(
    long_running=True,
    runtime_guard="required",
    prereq_tags={ZEBRA_RUNTIME_TAG},
)
REQUIRED_MUTATING_LONG_RUNNING = CommandPolicy(
    mutates_state=True,
    long_running=True,
    runtime_guard="required",
    prereq_tags={ZEBRA_RUNTIME_TAG},
)

CommandDef = tuple[str, Callable[..., Any], CommandPolicy]


def help_text(callback: Callable[..., Any]) -> str:
    """Return deterministic CLI help text from the callback docstring."""
    return inspect.getdoc(callback) or ""


def register_group_commands(
    registry: CommandRegistry,
    group_path: str,
    group_help: str,
    commands: Sequence[CommandDef],
) -> None:
    """Register one explicit command group and its command callbacks."""
    if "/" in group_path:
        parent = registry._resolve_parent(group_path)
        if parent is None:
            raise ValueError(f"Unable to create command group {group_path!r}")
        if group_help and parent.help_text and parent.help_text != group_help:
            raise ValueError(f"Conflicting help text for command group {group_path!r}")
        if group_help and not parent.help_text:
            parent.help_text = group_help
    else:
        registry.add_group(group_path, help_text=group_help)
    for name, callback, policy in commands:
        registry.add_command(
            group_path,
            name,
            callback,
            help_text=help_text(callback),
            policy=policy,
        )
