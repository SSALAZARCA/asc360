"""
tests/test_deps_current_user_is_distribuidor.py — `sdd/distributor-vehicle-delivery`
PR1, task 1.6: `CurrentUser.is_distribuidor`, mirroring the existing
`is_proveedor`/`is_administrativo` properties. Not wired into any endpoint
guard yet (that's PR3's `require_distribuidor`) -- this only pins the
property itself.
"""
from app.api.deps import CurrentUser


def _user(role: str) -> CurrentUser:
    return CurrentUser(user_id="u1", role=role, tenant_id=None)


def test_parts_dealer_role_is_distribuidor():
    assert _user("parts_dealer").is_distribuidor is True


def test_other_roles_are_not_distribuidor():
    for role in ("superadmin", "jefe_taller", "technician", "client", "proveedor", "administrativo"):
        assert _user(role).is_distribuidor is False
