from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Rule:
    cidr: str | None
    client_random_prefix: str | None
    action: str


def load_rules(path: Path) -> list[Rule]:
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    rules = data.get("rule", [])
    parsed: list[Rule] = []
    for rule in rules:
        cidr = rule.get("cidr")
        client_random_prefix = rule.get("client_random_prefix")
        action = rule.get("action")
        if not action:
            raise ValueError("Each rule must have an action")
        parsed.append(
            Rule(
                cidr=str(cidr) if cidr else None,
                client_random_prefix=str(client_random_prefix)
                if client_random_prefix
                else None,
                action=str(action),
            )
        )
    return parsed


def save_rules(path: Path, rules: list[Rule]) -> None:
    lines: list[str] = []
    for rule in rules:
        lines.append("[[rule]]")
        if rule.cidr:
            lines.append(f"cidr = \"{_escape(rule.cidr)}\"")
        if rule.client_random_prefix:
            lines.append(f"client_random_prefix = \"{_escape(rule.client_random_prefix)}\"")
        lines.append(f"action = \"{_escape(rule.action)}\"")
        lines.append("")
    content = "\n".join(lines).rstrip() + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")


def format_rules_summary(rules: list[Rule]) -> str:
    if not rules:
        return "Rules: (нет правил)"
    lines = ["Rules:"]
    for rule in rules:
        parts = []
        if rule.cidr:
            parts.append(f"cidr={rule.cidr}")
        if rule.client_random_prefix:
            parts.append(f"client_random_prefix={rule.client_random_prefix}")
        parts.append(f"action={rule.action}")
        lines.append("- " + ", ".join(parts))
    return "\n".join(lines)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
