"""Test-only routes registered on isolated app instances inside the test suite."""

from fastapi import APIRouter, Depends, FastAPI

from app.core.auth import AuthContext, get_current_user
from app.core.errors import NotFoundError

TEST_ROUTE_PREFIX = "/_test"


def register_test_routes(app: FastAPI) -> None:
    router = APIRouter(prefix=TEST_ROUTE_PREFIX, tags=["test-only"])

    @router.get("/me")
    def test_me(current_user: AuthContext = Depends(get_current_user)) -> dict[str, str]:
        return {
            "user_id": str(current_user.user_id),
            "organization_id": str(current_user.organization_id),
            "role": current_user.role.value,
        }

    @router.get("/not-found")
    def test_not_found() -> None:
        raise NotFoundError(
            code="CASE_NOT_FOUND",
            message="Recovery case was not found.",
        )

    @router.get("/internal-error")
    def test_internal_error() -> None:
        raise RuntimeError("super-secret-token leaked")

    app.include_router(router)
