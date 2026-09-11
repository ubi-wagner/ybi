"""Every request model can actually be built.

`from __future__ import annotations` is on every module here, so a Pydantic
model's annotations are strings until something asks for them. A missing
import therefore does **not** fail at import time — the module loads, the
routes register, the application starts, and the first request that touches
the model answers 500 with

    `DonationRateIn` is not fully defined; you should define `Decimal`

That is the shape this catches. `DonationRateIn` shipped with `Decimal`
unimported and every check short of a live request was happy: it parsed, it
imported, the router mounted, `--help` worked.

Building each model's validator is the cheapest thing that would have caught
it, and it covers every future one without anybody remembering.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from pydantic import BaseModel

import app.routers


def models():
    out = []
    for mod in pkgutil.iter_modules(app.routers.__path__):
        module = importlib.import_module(f"app.routers.{mod.name}")
        for name, obj in vars(module).items():
            if (inspect.isclass(obj) and issubclass(obj, BaseModel)
                    and obj is not BaseModel
                    and obj.__module__ == module.__name__):
                out.append((f"{mod.name}.{name}", obj))
    return sorted(out)


MODELS = models()


def test_there_are_models_to_check():
    """If the discovery breaks, every test below passes over nothing."""
    assert len(MODELS) >= 20, f"only found {len(MODELS)} request models"


@pytest.mark.parametrize("name,model", MODELS, ids=[n for n, _ in MODELS])
def test_the_model_is_fully_defined(name, model):
    """`model_rebuild` resolves the annotations the way a request would.

    `force=True` because a model that was already built during import would
    otherwise be skipped, and those are exactly the ones nobody worries
    about.
    """
    model.model_rebuild(force=True)
    assert model.__pydantic_complete__, (
        f"{name} cannot be built: something in its annotations is not "
        f"imported. With `from __future__ import annotations` this does not "
        f"fail until the first request that uses it.")
