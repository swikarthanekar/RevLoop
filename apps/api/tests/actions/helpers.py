"""Shared helpers for recovery action tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.demo.constants import DEMO_ORGANIZATION_ID
from app.domain.enums import RecoveryActionType, RecoveryCaseStatus
from app.models.recovery_case import RecoveryCase
from app.models.recovery_recommendation import RecoveryRecommendation
from tests.workflows.helpers import create_case, create_customer


def setup_recommended_case(
    session: Session,
    *,
    action_type: RecoveryActionType = RecoveryActionType.CREATE_PAYMENT_LINK,
    amount_at_risk_minor: int = 499900,
    organization_id: uuid.UUID = DEMO_ORGANIZATION_ID,
) -> tuple[RecoveryCase, uuid.UUID, RecoveryRecommendation]:
    customer = create_customer(session, organization_id=organization_id)
    case = create_case(
        session,
        organization_id=organization_id,
        customer_id=customer.id,
        status=RecoveryCaseStatus.RECOMMENDED,
    )
    case.amount_at_risk_minor = amount_at_risk_minor
    run_id = uuid.uuid4()
    case.current_analysis_run_id = run_id
    recommendation = RecoveryRecommendation(
        organization_id=organization_id,
        case_id=case.id,
        analysis_run_id=run_id,
        action_type=action_type.value,
        rank=1,
        success_probability=Decimal("0.720000"),
        expected_recovered_minor=amount_at_risk_minor,
        expected_value_minor=350000,
        confidence=Decimal("0.810000"),
        policy_eligible=True,
        requires_approval=False,
        policy_reasons=[],
        factors=[],
        model_version="test-model",
        feature_schema_version="recovery_features_v1",
    )
    session.add(recommendation)
    session.commit()
    return case, run_id, recommendation


def payment_link_success_payload(
    *,
    reference_id: str,
    amount: int,
    currency: str = "INR",
) -> dict:
    return {
        "id": "plink_test_001",
        "reference_id": reference_id,
        "amount": amount,
        "currency": currency,
        "status": "created",
        "short_url": "https://rzp.io/i/testlink",
        "accept_partial": False,
    }
