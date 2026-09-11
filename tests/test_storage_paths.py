"""Everything a user uploads has to land on the volume, in the right place.

Railway discards the container filesystem on every deploy. A volume is
mounted at YBI_STORAGE_DIR and survives; anything written anywhere else does
not. The register goes on listing the document either way, so the loss is
silent until somebody asks for it — which, for an audit file, is the worst
possible moment to find out.

These are structural tests because the mistake is one line and the failure is
invisible in every environment that has no volume — which includes every
developer's laptop and every test run. They cost nothing to make and would
have cost the whole document library.

Since `app/storage.py` took ownership of the layout, the structural claim is
stronger than "the constant mentions the setting": no router writes bytes to
disk at all. There is one place where a path is decided, so there is one
place to get it wrong.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
ROUTERS = APP / "routers"

#: Modules that accept an upload and put it on disk.
WRITERS = ["documents.py", "evidence.py", "imports.py"]


@pytest.mark.parametrize("module", WRITERS)
def test_upload_goes_through_the_storage_module(module):
    src = (ROUTERS / module).read_text()
    assert "from app import storage" in src, (
        f"{module} accepts uploads but does not import app.storage. The "
        f"layout of the volume is decided in one place; a router that builds "
        f"its own path is how the tree and the register drift apart.")
    assert "storage.place(" in src, (
        f"{module} imports app.storage but does not write through "
        f"storage.place(). That is the only function that creates the "
        f"directory before writing into it.")


def test_no_router_writes_bytes_itself():
    """`write_bytes` belongs to app/storage.py and nowhere else.

    A router that writes directly is a router that decided a path directly,
    which is the mistake this whole module exists to make impossible.
    """
    offenders = [
        f"{path.name}:{node.lineno}"
        for path in sorted(ROUTERS.glob("*.py"))
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"write_bytes", "write_text"}
    ]
    assert not offenders, (
        "a router writes a file itself instead of through storage.place(): "
        + "; ".join(offenders))


def test_storage_root_comes_from_the_setting():
    src = (APP / "storage.py").read_text()
    root = next((ast.unparse(n.value)
                 for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", None) == "ROOT" for t in n.targets)),
                None)
    assert root, "app/storage.py has no ROOT to check"
    assert "settings.storage_dir" in root, (
        f"storage.ROOT is {root}, which is a path inside the container. "
        f"Railway discards that on every deploy while the register goes on "
        f"listing the documents. Derive it from settings.storage_dir.")


def test_no_module_writes_to_a_literal_relative_path():
    """The same mistake, wearing different clothes."""
    offenders = []
    for path in sorted([*ROUTERS.glob("*.py"), APP / "storage.py"]):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Path"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            literal = node.args[0].value
            if isinstance(literal, str) and not literal.startswith("/"):
                offenders.append(f"{path.name}: Path({literal!r})")
    assert not offenders, (
        "a module builds a path from a bare relative string: "
        + "; ".join(offenders)
        + ". On Railway the working directory is /srv and only the mounted "
          "volume survives a deploy, so a relative path is a file that "
          "disappears.")
