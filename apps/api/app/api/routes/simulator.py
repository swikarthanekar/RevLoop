"""Read-only recovery simulator route.

Deliberately outside the demo router. The simulator scores hypothetical
scenarios through the production engine and writes nothing, so it is not a
demo-only affordance -- it is a legitimate read operation on the decision
engine, and gating it behind `DEMO_MODE` would imply otherwise.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_current_user
from app.core.deps import get_db
from app.schemas.simulator import SimulationRequest, SimulationResponse
from app.services.simulator import simulate

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.post("/score", response_model=SimulationResponse)
def score_scenario(
    request: SimulationRequest,
    current_user: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> SimulationResponse:
    """Score a hypothetical failed payment.

    Every role may call this: it creates nothing and changes nothing, so there
    is no privilege to gate. Authentication is still required, because the
    response reveals the caller's own merchant policy thresholds.

    Declared `def` rather than `async def` -- scoring is synchronous CPU work in
    scikit-learn, so FastAPI runs it in its threadpool instead of stalling the
    event loop while a slider drags.
    """
    return simulate(
        session,
        organization_id=current_user.organization_id,
        request=request,
    )
