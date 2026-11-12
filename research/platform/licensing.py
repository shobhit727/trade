"""Explicit licence-review decisions for registered research datasets."""

from __future__ import annotations

from .data_catalog import LicenseStatus
from .storage import LICENCE_APPROVAL_EVENT, ExperimentStore


def approve_dataset(
    store: ExperimentStore,
    dataset_id: str,
    *,
    licence_reference: str,
    reviewed_by: str,
    decision: str = "approve",
) -> dict[str, object]:
    """Record one human licence review for a registered dataset.

    The manifest registered in the store is never rewritten: approval flips the
    effective licence status to APPROVED by appending an immutable decision event
    to the store's append-only licence-event log, and the overlay in
    ``ExperimentStore.get_dataset`` derives review state from that event stream.

    ``decision`` must be ``"approve"``; anything else is recorded as a rejection
    reason. Both rejection paths raise ``ValueError`` before any event is written,
    so the append-only log only ever contains executed, fully-attributed decisions.
    """
    # Only an explicit, traceable citation and a named reviewer may clear a licence.
    if not isinstance(licence_reference, str) or not licence_reference.strip():
        raise ValueError(
            "licence approval requires a non-empty licence_reference citation"
        )
    if not isinstance(reviewed_by, str) or not reviewed_by.strip():
        raise ValueError(
            "licence approval requires a non-empty reviewed_by reviewer identity"
        )

    row = store.get_dataset(dataset_id)  # KeyError for unknown datasets.
    manifest = row["manifest"]
    previous_status = str(manifest.get("license_status") or "")

    if decision.strip().lower() != "approve":
        raise ValueError(
            f"dataset {dataset_id} licence review rejected: unsupported decision {decision!r}; "
            "only explicit approval may clear a licence"
        )

    event_id = store.append_dataset_licence_event(
        dataset_id,
        LICENCE_APPROVAL_EVENT,
        {
            "decision": "approve",
            "licence_reference": licence_reference.strip(),
            "reviewed_by": reviewed_by.strip(),
            "previous_status": previous_status,
            "manifest_fingerprint": str(row["fingerprint"]),
        },
    )
    return {
        "dataset_id": dataset_id,
        "event_id": event_id,
        "decision": "approve",
        "licence_reference": licence_reference.strip(),
        "reviewed_by": reviewed_by.strip(),
        "previous_status": previous_status,
        "license_status": LicenseStatus.APPROVED.value,
    }
