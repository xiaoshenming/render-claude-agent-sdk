"""Independent layout recheck and semantic-preservation validation."""

from .checkpoints import require_layout_certificate, require_semantic_certificate
from .failures import StageExecutionError
from .ports import LayoutRecheckPort, LayoutSemanticVerificationPort


def verify_layout(
    port: LayoutRecheckPort,
    revision,
    render,
    logic_checkpoint,
    assessment,
    request,
    policy,
):
    try:
        raw = port.verify(
            revision, render, assessment, logic_checkpoint, request, policy
        )
        return require_layout_certificate(
            raw, revision, render, logic_checkpoint, assessment, request, policy
        )
    except Exception as error:
        raise StageExecutionError(
            "layout_recheck_error", str(error), revision.revision_id
        ) from error


def verify_semantic(
    port: LayoutSemanticVerificationPort,
    logic_checkpoint,
    revision,
    render,
    assessment,
    request,
):
    if revision.revision_id == logic_checkpoint.revision_id:
        return None
    try:
        raw = port.verify(logic_checkpoint, revision, render, assessment, request)
        return require_semantic_certificate(
            raw, logic_checkpoint, revision, request, port.identity
        )
    except Exception as error:
        raise StageExecutionError(
            "layout_semantic_error", str(error), revision.revision_id
        ) from error
