"""The rate is computed under policies, so a policy nobody chose is a defect.

`ComputeIn` is the one body in this API that refuses a key it does not know.
Everything here is pure — no database — because the guarantee is about the
shape of the request, not about any row.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# A policy nobody chose


def test_the_compute_body_refuses_a_key_it_does_not_know():
    """`admin_labour_basis` must be a 422, not a rate under the default.

    Every field on `ComputeIn` is a policy with a default, so pydantic's
    ordinary behaviour — drop the unknown key, apply the default — turns a
    misremembered field name into a rate computed under a basis nobody chose,
    answering 200 and saying nothing. `admin_labour_basis` is the name of the
    *column* the answer is stored in, which is the name anybody reads off the
    schema, and sending it computes OBJECTIVE while the caller believes they
    asked for POOL. Nine points of combined rate.

    Found while building the min/max band: the scenario harness only caught it
    because it read the basis back off `v_rate_buildup` afterwards.
    """
    from pydantic import ValidationError

    from app.routers.rates import ComputeIn

    good = ComputeIn(admin_labour="POOL")
    assert good.admin_labour == "POOL"

    for wrong in ("admin_labour_basis", "period", "adminLabour"):
        with pytest.raises(ValidationError) as e:
            ComputeIn(**{wrong: "POOL"})
        # The refusal has to name the field, or the caller is left guessing at
        # which of five policies they misspelled.
        assert wrong in str(e.value)


def test_every_policy_on_the_compute_body_still_has_a_default():
    """Forbidding extras must not turn an empty body into a 422.

    `POST /api/rates/compute` with `{}` is what the screen sends and what four
    drives send. If a field ever loses its default, that call starts failing
    and the refusal will read as though the caller did something wrong.
    """
    from app.routers.rates import ComputeIn

    empty = ComputeIn()
    assert empty.admin_labour == "OBJECTIVE"
    assert empty.fringe_base == "SALARIES_WAGES"
