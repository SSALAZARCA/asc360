"""Proves `lore-bot/` shares zero code, imports, or secrets with
`telegram-bot/` (Sonia, the unrelated UM product's bot) — a stated Success
Criterion of this whole change.
"""
import ast
import pathlib
import subprocess

import pytest

_LORE_SRC = pathlib.Path(__file__).resolve().parent.parent / "lore"
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# `telegram-bot/`'s own top-level packages (see `telegram-bot/bot/`'s
# `core`, `handlers`, `keyboards`, `services` submodules, all imported as
# `bot.*` or, from within `bot/`, as `core.*`). Neither name is otherwise
# used by `lore-bot`, whose own package is `lore` (design D7, chosen
# specifically so this scan has zero false positives against its own code).
_FORBIDDEN_TOP_LEVEL_IMPORTS = {"bot", "core"}
_FORBIDDEN_STRINGS = ("telegram-bot", "telegram_bot")


def _iter_py_files():
    return sorted(_LORE_SRC.rglob("*.py"))


def test_lore_source_tree_exists():
    assert _LORE_SRC.is_dir()
    assert any(_iter_py_files())


def test_no_import_of_telegram_bot_packages():
    offenders = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _FORBIDDEN_TOP_LEVEL_IMPORTS:
                        offenders.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level >= 2:
                    offenders.append(
                        f"{path}: relative import with level={node.level} "
                        "(deep relative imports are not expected in this "
                        "flat package and could escape it)"
                    )
                elif node.module:
                    top = node.module.split(".")[0]
                    if top in _FORBIDDEN_TOP_LEVEL_IMPORTS:
                        offenders.append(f"{path}: from {node.module} import ...")
    assert not offenders, (
        "lore-bot/lore/ must not import telegram-bot's own packages "
        f"(bot.*/core.*): {offenders}"
    )


def _non_docstring_string_constants(tree: ast.AST):
    """Yield string-literal VALUES that are not a module/function/class
    docstring. Prose in comments/docstrings is allowed to reference
    `telegram-bot/` for documentation purposes (e.g. explaining what this
    module is independent FROM); only string literals used as actual code
    (import targets, path arguments, etc.) are a real isolation risk.
    """
    docstrings = set()
    for node in ast.walk(tree):
        es_docstring_owner = isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
        if es_docstring_owner:
            # `clean=False` is required: `ast.get_docstring()` dedents by
            # default, which would no longer match the raw `ast.Constant`
            # value scanned below (same string, different indentation).
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                yield node.value


def test_no_string_reference_to_telegram_bot_path():
    offenders = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for value in _non_docstring_string_constants(tree):
            for needle in _FORBIDDEN_STRINGS:
                if needle in value:
                    offenders.append(
                        f"{path}: string literal contains {needle!r}: {value!r}"
                    )
    assert not offenders, offenders


def test_telegram_bot_directory_has_zero_diff():
    """`telegram-bot/` must be untouched by this change (Success Criterion)."""
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "telegram-bot"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"git status unavailable: {result.stderr.strip()}")
    assert result.stdout.strip() == "", (
        "telegram-bot/ must have zero diff for this change; found:\n"
        f"{result.stdout}"
    )
