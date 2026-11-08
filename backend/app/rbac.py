"""Server-side authorization. Roles are granted globally (dept_id NULL) or per department."""
from fastapi import HTTPException
RANK = {"viewer": 1, "reviewer": 2, "editor": 2, "admin": 9}
CAN = {"read": {"viewer", "reviewer", "editor", "admin"}, "write": {"editor", "admin"}, "review": {"reviewer", "admin"}, "admin": {"admin"}}
def roles_of(cx, user_id):
    return cx.execute("SELECT dept_id, role::text AS role FROM user_roles WHERE user_id=%s", (user_id,)).fetchall()
def is_admin(roles): return any(r["role"] == "admin" and r["dept_id"] is None for r in roles)
def depts_for(cx, user, perm: str) -> set[str] | None:
    """Departments the user may use for `perm`. None means all departments."""
    roles = user["roles"]
    if is_admin(roles): return None
    allowed = {"admin"} if perm == "admin" else CAN[perm]
    if any(r["dept_id"] is None and r["role"] in allowed for r in roles):
        return None
    return {r["dept_id"] for r in roles if r["dept_id"] and r["role"] in allowed}
def require(cx, user, perm: str, dept_id: str | None = None):
    d = depts_for(cx, user, perm)
    if d is None: return
    if perm == "admin" or dept_id is None or dept_id not in d:
        raise HTTPException(403, "You do not have permission to do this.")
