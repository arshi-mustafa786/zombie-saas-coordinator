"""HTTP endpoints for reading consolidation proposals (US-3)."""

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status

from zombie_saas_coordinator.agents.auditor.tools import (
    ProposalSigningError,
    load_proposal,
    verify_proposal_signature,
)

router = APIRouter(prefix="/api/v1/proposals", tags=["proposals"])


@router.get("/{proposal_id}")
def get_proposal(
    proposal_id: str,
    # Placeholder tenant scoping until Firebase Auth (US-5) supplies a verified tenant claim.
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID")] = "",
) -> dict[str, Any]:
    """Return a stored proposal if it belongs to the caller's tenant."""
    try:
        proposal = load_proposal(proposal_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Proposal storage is temporarily unavailable",
        ) from error

    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if not tenant_id or proposal.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Proposal belongs to a different tenant",
        )

    try:
        signature_valid: bool | None = verify_proposal_signature(proposal)
    except ProposalSigningError:
        signature_valid = None

    return {"proposal": proposal, "signature_valid": signature_valid}
