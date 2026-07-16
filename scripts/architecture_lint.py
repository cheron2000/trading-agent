"""
scripts/architecture_lint.py
==============================

Architecture linter — enforces the no-cross-layer-import rule.

Fails with exit code 1 if any layer imports directly from a layer
above it in the stack. All cross-layer communication must go through
the EventBus (Communication layer) only.

Allowed dependency direction (downward only):
    dashboard   → communication, foundation
    analytics   → communication, foundation
    execution   → communication, intelligence, foundation (events only)
    intelligence→ communication, data, foundation
    data        → communication, foundation
    communication → foundation
    foundation  → (nothing)

Dashboard must NEVER import from execution, intelligence, data, analytics.

Python Version: 3.11+
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Root of src/
SRC_ROOT = Path(__file__).parent.parent / "src"

# Illegal cross-layer import rules:
# { layer_dir: [forbidden_import_prefixes] }
FORBIDDEN: dict[str, list[str]] = {
    "dashboard": ["execution", "intelligence", "data", "analytics"],
    "analytics": ["dashboard"],
    "execution": ["dashboard", "analytics"],
    "intelligence": ["dashboard", "analytics", "execution"],
    "data": ["dashboard", "analytics", "execution", "intelligence"],
    "communication": ["dashboard", "analytics", "execution", "intelligence", "data"],
    "foundation": ["dashboard", "analytics", "execution", "intelligence", "data", "communication"],
}


def get_imports(filepath: Path) -> list[str]:
    """Extract all imported module names from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def lint() -> int:
    """Run architecture lint. Returns 0 on pass, 1 on violations."""
    violations: list[str] = []

    for layer, forbidden_prefixes in FORBIDDEN.items():
        layer_path = SRC_ROOT / layer
        if not layer_path.exists():
            continue

        for py_file in layer_path.rglob("*.py"):
            imports = get_imports(py_file)
            rel = py_file.relative_to(SRC_ROOT)

            for imp in imports:
                for forbidden in forbidden_prefixes:
                    if imp == forbidden or imp.startswith(f"{forbidden}."):
                        violations.append(
                            f"  VIOLATION: {rel} imports from '{imp}' "
                            f"(layer '{layer}' must not import from '{forbidden}')"
                        )

    if violations:
        print("Architecture lint FAILED — illegal cross-layer imports detected:\n")
        for v in violations:
            print(v)
        print(f"\nTotal violations: {len(violations)}")
        return 1

    print("Architecture lint PASSED — no illegal cross-layer imports.")
    return 0


if __name__ == "__main__":
    sys.exit(lint())
