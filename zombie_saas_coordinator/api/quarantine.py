"""Quarantine and Disposal API endpoints — US-12.

Provides:
  POST /{proposal_id}/quarantine             — Place source data into quarantine
  GET  /{proposal_id}                        — Get quarantine status and disposal eligibility
  POST /{proposal_id}/legal-hold             — Set or release legal hold
  POST /{proposal_id}/disposal/sign          — Submit multi-sig disposal signature
  POST /{proposal_id}/disposal/execute       — Execute verifiable disposal
  POST /{proposal_id}/exceptions/{id}/resolve— Resolve validation discrepancy
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from zombie_saas_coordinator.shared.auth.firebase_auth import verify_firebase_auth_token
from zombie_saas_coordinator.shared.models.quarantine import (
    DisposalCertificate,
    DisposalExecuteRequest,
    DisposalSignRequest,
    LegalHoldRequest,
    QuarantineRecord,
    QuarantineSourceRequest,
    ResolveExceptionRequest,
)
from zombie_saas_coordinator.shared.quarantine.service import (
    check_disposal_eligibility,
    execute_verifiable_disposal,
    get_quarantine_record,
    quarantine_source_data,
    resolve_validation_exception,
    set_legal_hold,
    submit_disposal_signature,
)

router = APIRouter(prefix="/api/v1/quarantine", tags=["quarantine", "disposal"])


@router.post(
    "/{proposal_id}/quarantine", status_code=status.HTTP_200_OK, response_model=QuarantineRecord
)
async def quarantine_source_endpoint(
    proposal_id: str,
    request: QuarantineSourceRequest,
) -> QuarantineRecord:
    """Places source SaaS data into SOURCE_QUARANTINED status with retention window."""
    verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["admin", "it_ops", "ciso", "security_admin"],
    )
    return quarantine_source_data(
        proposal_id=proposal_id,
        source_metadata=request.source_metadata,
        retention_days=request.retention_days,
    )


@router.get("/{proposal_id}", status_code=status.HTTP_200_OK)
async def get_quarantine_status_endpoint(
    proposal_id: str,
) -> dict[str, Any]:
    """Retrieves current quarantine status, blockers, and disposal eligibility."""
    record = get_quarantine_record(proposal_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarantine record for '{proposal_id}' was not found.",
        )
    eligibility = check_disposal_eligibility(proposal_id)
    return {
        "record": record.model_dump(mode="json"),
        "eligibility": eligibility,
    }


@router.post(
    "/{proposal_id}/legal-hold", status_code=status.HTTP_200_OK, response_model=QuarantineRecord
)
async def set_legal_hold_endpoint(
    proposal_id: str,
    request: LegalHoldRequest,
) -> QuarantineRecord:
    """Applies or releases a legal hold on quarantined source data."""
    operator_info = verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["legal", "ciso", "security_admin", "admin"],
    )
    return set_legal_hold(
        proposal_id=proposal_id,
        operator_info=operator_info,
        legal_hold=request.legal_hold,
        reason=request.reason,
    )


@router.post("/{proposal_id}/disposal/sign", status_code=status.HTTP_200_OK)
async def submit_disposal_signature_endpoint(
    proposal_id: str,
    request: DisposalSignRequest,
) -> dict[str, Any]:
    """Submits an authorized SSO signature for multi-signature disposal approval."""
    signer_info = verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["ciso", "compliance_officer", "security_admin", "admin"],
    )
    return submit_disposal_signature(
        proposal_id=proposal_id,
        signer_info=signer_info,
        notes=request.notes,
    )


@router.post(
    "/{proposal_id}/disposal/execute",
    status_code=status.HTTP_200_OK,
    response_model=DisposalCertificate,
)
async def execute_disposal_endpoint(
    proposal_id: str,
    request: DisposalExecuteRequest,
) -> DisposalCertificate:
    """Executes verifiable cryptographic destruction of quarantined source data."""
    executor_info = verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["ciso", "security_admin", "admin"],
    )
    return execute_verifiable_disposal(
        proposal_id=proposal_id,
        executor_info=executor_info,
    )


@router.post("/{proposal_id}/exceptions/{exception_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_exception_endpoint(
    proposal_id: str,
    exception_id: str,
    request: ResolveExceptionRequest,
) -> dict[str, Any]:
    """Resolves an active validation or reconciliation discrepancy."""
    resolver_info = verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["it_ops", "admin", "ciso", "security_admin"],
    )
    return resolve_validation_exception(
        proposal_id=proposal_id,
        exception_id=exception_id,
        resolution_notes=request.resolution_notes,
        resolved_by=resolver_info["uid"],
    )
