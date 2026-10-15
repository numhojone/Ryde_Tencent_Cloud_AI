"""核心数据模型：争议工单、advocate 案件、judge 裁决。"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


RulingStatus = Literal["upheld", "rejected", "partial", "escalated"]


class DisputeTicket(BaseModel):
    dispute_id: str
    trip_id: str
    filed_by: str
    rider_id: str
    driver_id: str
    dispute_type: str
    description: str
    filed_at: str
    requested_resolution: Optional[str] = None
    requested_amount: Optional[float] = None


class ExtractedFacts(BaseModel):
    """Facts the rider's story states. Anything the story does not say is null / empty: never inferred."""
    quoted_amount: Optional[float] = None
    charged_amount: Optional[float] = None
    claimed_difference: Optional[float] = None
    fee_type: Optional[Literal["cleaning_fee", "cancellation_fee", "damage_fee"]] = None
    pickup_place: Optional[str] = None
    dropoff_place: Optional[str] = None
    time_mentions: list[str] = Field(default_factory=list)
    driver_actions: list[str] = Field(default_factory=list)
    rider_actions: list[str] = Field(default_factory=list)
    safety_indicators: list[str] = Field(default_factory=list)
    detected_language: Optional[str] = None


class TriageResult(BaseModel):
    """受理分类智能体的输出：把乘客自由文本投诉归类到平台支持的争议类型。"""
    dispute_type: str
    classification_confidence: float = Field(ge=0.0, le=1.0)
    classification_reasoning: str
    normalized_claim: str = Field(description="用平台术语重述的一句话主张")
    requested_amount: Optional[float] = None
    requested_resolution: Optional[str] = None
    detected_signals: list[str] = Field(default_factory=list, description="Signals in the complaint that drove the classification")
    safety_flag: bool = Field(default=False, description="Complaint contains safety indicators (policy 5.2): always human review")
    extracted_facts: ExtractedFacts = Field(default_factory=ExtractedFacts)
    missing_info: list[str] = Field(default_factory=list, description="What would help the case but the story did not say")


class AdvocateCase(BaseModel):
    """advocate 提交给 judge 的案件。"""
    agent: str
    side: Literal["rider", "driver"]
    claim: str = Field(description="一句话主张")
    requested_outcome: str
    requested_amount: Optional[float] = None
    policy_clauses_referenced: list[str] = Field(default_factory=list)
    evidence_cited: list[str] = Field(default_factory=list, description="具体证据数据点")
    reasoning: str = Field(description="论证过程，必须只引用工具返回的数据")


class Ruling(BaseModel):
    """judge 输出的裁决，严格符合 spec。"""
    dispute_id: str
    ruling: RulingStatus
    refund_amount: Optional[float] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_cited: list[str] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_summary: Optional[str] = None
    goodwill_credit: Optional[float] = None
    policy_clauses: list[str] = Field(default_factory=list)
    policy_path: Optional[dict] = None
    confidence_breakdown: Optional[dict] = None
    precedent_id: Optional[str] = None
    recommendation: Optional[dict] = None
    policy_check: Optional[dict] = None
