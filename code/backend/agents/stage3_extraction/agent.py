"""Stage 3 Extraction & Multimodal Vision Dialectical Pair (MultimodalVisionExtractor <-> EvidenceProvenanceAuditor)."""
from __future__ import annotations

from typing import Any
from google.adk import Workflow
from google.adk.agents import LlmAgent, SequentialAgent

from config import get_settings
from features.workflow.state_tools import (
    audit_provenance_bounding_boxes_tool,
    complete_stage,
    get_project_state,
    parse_multimodal_pdf_pages_tool,
    post_to_message_board,
    read_message_board,
)

_settings = get_settings()


def create_multimodal_vision_extractor_agent() -> LlmAgent:
    """Create MultimodalVisionExtractor builder agent for Stage 3."""
    return LlmAgent(
        name="MultimodalVisionExtractor",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Extracts empirical claims and bounding boxes from multimodal PDF pages.",
        instruction="You are MultimodalVisionExtractor. Parse PDF pages for mathematical claims and crops.",
        tools=[parse_multimodal_pdf_pages_tool, get_project_state, post_to_message_board, read_message_board, complete_stage],
        output_key="extraction_result",
    )


def create_evidence_provenance_auditor_agent() -> LlmAgent:
    """Create EvidenceProvenanceAuditor auditor agent for Stage 3."""
    return LlmAgent(
        name="EvidenceProvenanceAuditor",
        model=getattr(_settings, "adk_tier2_model", _settings.adk_model_name),
        description="Audits extraction confidence and verifies bounding-box coordinates.",
        instruction="You are EvidenceProvenanceAuditor. Audit evidence claims for provenance and validity.",
        tools=[audit_provenance_bounding_boxes_tool, get_project_state, post_to_message_board, read_message_board],
        output_key="provenance_critique_result",
    )


def create_stage3_extraction_workflow() -> SequentialAgent:
    """Create Stage 3 sequential dialectical workflow."""
    builder = create_multimodal_vision_extractor_agent()
    critic = create_evidence_provenance_auditor_agent()
    return SequentialAgent(
        name="Stage3ExtractionDialecticalPair",
        sub_agents=[builder, critic],
    )


MultimodalVisionExtractor = create_multimodal_vision_extractor_agent
EvidenceProvenanceAuditor = create_evidence_provenance_auditor_agent
stage3_extraction_workflow = create_stage3_extraction_workflow()

__all__ = [
    "EvidenceProvenanceAuditor",
    "MultimodalVisionExtractor",
    "create_evidence_provenance_auditor_agent",
    "create_multimodal_vision_extractor_agent",
    "create_stage3_extraction_workflow",
    "stage3_extraction_workflow",
]
