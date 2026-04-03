#!/usr/bin/env python3

from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / ".pre-commit-config.yaml"
REQUIRED_SNIPPETS = {
    "default_install_hook_types": "default_install_hook_types",
    "default_stages": "default_stages",
    "pre-push": "pre-push",
    "ruff": "id: ruff",
    "ruff-format": "id: ruff-format",
    "bandit": "id: bandit",
}


def main() -> int:
    content = CONFIG_PATH.read_text(encoding="utf-8")
    missing = [name for name, snippet in REQUIRED_SNIPPETS.items() if snippet not in content]
    if missing:
        raise SystemExit("Missing pre-commit hook contract entries: " + ", ".join(missing))
    print("pre-commit hook contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
