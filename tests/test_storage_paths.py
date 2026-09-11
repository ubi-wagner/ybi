"""Everything a user uploads has to land on the volume.

Railway discards the container filesystem on every deploy. A volume is
mounted at YBI_STORAGE_DIR and survives; anything written anywhere else does
not. The register goes on listing the document either way, so the loss is
silent until somebody asks for it — which, for an audit file, is the worst
possible moment to find out.

This is a structural test because the mistake is a one-line constant and the
failure is invisible in every environment that has no volume — which includes
every developer's laptop and every test run. It cost nothing to make and
would have cost the whole document library.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROUTERS = Path(__file__).resolve().parent.parent / "app" / "routers"

#: Modules that accept an upload and write it to disk.
WRITERS = ["documents.py", "evidence.py", "imports.py"]


@pytest.mark.parametrize("module", WRITERS)
def test_upload_storage_comes_from_the_setting(module):
    src = (ROUTERS / module).read_text()
    assign = re.search(r"^STORAGE\s*=\s*(.+)$", src, re.M)
    assert assign, f"{module} has no STORAGE constant to check"
    value = assign.group(1)
    assert "settings.storage_dir" in value, (
        f"{module} writes uploads to {value.strip()}, which is a path inside "
        f"the container. Railway discards that on every deploy and the "
        f"register goes on listing the documents. Derive it from "
        f"settings.storage_dir.")


def test_no_router_writes_to_a_literal_relative_path():
    """The same mistake, wearing different clothes."""
    offenders = []
    for path in sorted(ROUTERS.glob("*.py")):
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
        "a router builds a path from a bare relative string: "
        + "; ".join(offenders)
        + ". On Railway the working directory is /srv and only the mounted "
          "volume survives a deploy, so a relative path is a file that "
          "disappears.")
