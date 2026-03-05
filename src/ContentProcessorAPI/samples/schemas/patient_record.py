"""
ClinIQ Peer Review Parsing Schema
=================================

Goal
----
Provide a disciplined, AI-parsable structure for extracting *only the clinically pertinent*
information needed for peer review, based on discipline and specialty.

Core Rules (Non-Negotiable)
---------------------------
1) DO NOT FABRICATE: If a field is not explicitly present in the source document, set it to None.
2) DISCIPLINE-SCOPED: Only include data that is directly relevant to the visit’s discipline + chief complaint.
3) MINIMIZE NOISE: Prefer pertinent positives/negatives; do not surface unrelated historical medical details.
4) TRACEABILITY: When possible, keep "verbatim_excerpt" snippets for key items to support defensibility.
5) ROS/Exam SYSTEMS: Only include ROS / Exam subsections that have documented findings (positive OR negative).
6) PAYER/ACCREDITATION READY: The structure supports HRSA/FQHC, Ryan White, CCBHC, CARF, and SAMHSA
   documentation patterns without forcing irrelevant content into the reviewer view.

Usage Pattern in ClinIQ
-----------------------
- Parse source documents into one of the DisciplineEncounter schemas (Medical, Psychiatry, BehavioralHealth,
  CaseManagement, Dental).
- Select a SpecialtyProfile (optional) to further tune inclusion and emphasis.
- Use PresentationPolicy to control what is surfaced to a reviewer vs. what is retained as "hidden context".

This file intentionally avoids external dependencies to keep it portable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar, Union
from datetime import datetime
import json
import re


# -------------------------
# Shared Core Value Objects
# -------------------------

@dataclass
class SourceTrace:
    """
    Traceability anchor. Use for defensibility in peer review.
    - verbatim_excerpt should be a short snippet (not long quotes).
    - source_section is a best guess heading in the source document (e.g., "HPI", "Assessment").
    """
    verbatim_excerpt: Optional[str] = None
    source_section: Optional[str] = None
    page_hint: Optional[str] = None  # e.g., "p1", "p2" if known


@dataclass
class Identifiers:
    full_name: Optional[str] = None
    dob: Optional[str] = None              # Use MM-DD-YYYY if present; otherwise None
    mrn: Optional[str] = None
    patient_id: Optional[str] = None       # If non-MRN identifier exists
    encounter_id: Optional[str] = None


@dataclass
class ProviderInfo:
    rendering_provider: Optional[str] = None
    provider_credentials: Optional[str] = None
    supervising_provider: Optional[str] = None
    location: Optional[str] = None


@dataclass
class EncounterMeta:
    date_of_service: Optional[str] = None  # MM-DD-YYYY
    visit_type: Optional[str] = None       # In-Person/Telehealth/Phone/Group/Outreach/etc.
    discipline: Literal["Medical", "Psychiatry", "BehavioralHealth", "CaseManagement", "Dental"] = "Medical"
    specialty_profile: Optional[str] = None  # e.g., "OBGYN", "InfectiousDisease", "MHR", etc.


@dataclass
class Medication:
    name: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    indication: Optional[str] = None
    status: Optional[Literal["Current", "New", "Changed", "Discontinued", "PRN", "Unknown"]] = None
    trace: Optional[SourceTrace] = None


@dataclass
class Allergy:
    allergen: Optional[str] = None
    reaction: Optional[str] = None
    severity: Optional[str] = None
    trace: Optional[SourceTrace] = None


@dataclass
class Diagnosis:
    name: Optional[str] = None
    icd10: Optional[str] = None
    status: Optional[Literal["New", "Established", "Stable", "Worsening", "Resolved", "Unknown"]] = None
    rationale: Optional[str] = None
    trace: Optional[SourceTrace] = None


@dataclass
class PlanItem:
    category: Optional[Literal[
        "Medication", "Labs", "Imaging", "Procedure", "Referral", "Counseling",
        "Education", "FollowUp", "SafetyPlan", "CareCoordination", "Other"
    ]] = None
    description: Optional[str] = None
    trace: Optional[SourceTrace] = None


@dataclass
class Vitals:
    blood_pressure: Optional[str] = None
    heart_rate: Optional[str] = None
    respiratory_rate: Optional[str] = None
    temperature: Optional[str] = None
    spo2: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    bmi: Optional[str] = None
    pain_score: Optional[str] = None
    trace: Optional[SourceTrace] = None


# -------------------------
# Review of Systems / Exam
# -------------------------

@dataclass
class ROS:
    """
    Only include systems that have data. Leave absent systems as None.
    """
    constitutional: Optional[str] = None
    heent: Optional[str] = None
    eyes: Optional[str] = None
    cardiovascular: Optional[str] = None
    respiratory: Optional[str] = None
    gastrointestinal: Optional[str] = None
    genitourinary: Optional[str] = None
    musculoskeletal: Optional[str] = None
    integumentary: Optional[str] = None
    neurological: Optional[str] = None
    psychiatric: Optional[str] = None
    endocrine: Optional[str] = None
    hematologic_lymphatic: Optional[str] = None
    allergic_immunologic: Optional[str] = None
    trace: Optional[SourceTrace] = None


@dataclass
class PhysicalExam:
    """
    Only include systems documented. Leave absent systems as None.
    """
    general: Optional[str] = None
    heent: Optional[str] = None
    neck: Optional[str] = None
    cardiovascular: Optional[str] = None
    respiratory: Optional[str] = None
    abdomen: Optional[str] = None
    genitourinary: Optional[str] = None
    musculoskeletal: Optional[str] = None
    skin: Optional[str] = None
    neurological: Optional[str] = None
    psychiatric: Optional[str] = None
    trace: Optional[SourceTrace] = None


# -------------------------
# Discipline-Specific Blocks
# -------------------------

@dataclass
class MentalStatusExam:
    appearance: Optional[str] = None
    behavior: Optional[str] = None
    speech: Optional[str] = None
    mood: Optional[str] = None
    affect: Optional[str] = None
    thought_process: Optional[str] = None
    thought_content: Optional[str] = None
    perception: Optional[str] = None
    insight: Optional[str] = None
    judgment: Optional[str] = None
    cognition: Optional[str] = None
    orientation: Optional[str] = None
    memory: Optional[str] = None
    concentration: Optional[str] = None
    trace: Optional[SourceTrace] = None


@dataclass
class RiskAssessment:
    """
    Critical for Psychiatry / Behavioral Health / CCBHC / SAMHSA-aligned workflows.
    """
    suicide_risk_level: Optional[str] = None
    homicide_risk_level: Optional[str] = None
    self_harm_risk: Optional[str] = None
    violence_risk: Optional[str] = None
    protective_factors: Optional[str] = None
    risk_factors: Optional[str] = None
    safety_plan_documented: Optional[bool] = None
    crisis_intervention_provided: Optional[bool] = None
    trace: Optional[SourceTrace] = None


@dataclass
class TreatmentPlan:
    """
    CARF/CCBHC-oriented: problems -> goals -> objectives -> interventions.
    Populate only what is documented.
    """
    problems: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    objectives: Optional[List[str]] = None
    interventions: Optional[List[str]] = None
    patient_involvement: Optional[str] = None
    target_dates: Optional[List[str]] = None
    progress_summary: Optional[str] = None
    trace: Optional[SourceTrace] = None


@dataclass
class CaseManagementBlock:
    """
    Only include medical details if directly relevant to the CM action.
    Focus on needs, barriers, coordination, referrals, benefits, resources, follow-up.
    """
    identified_needs: Optional[List[str]] = None
    barriers_to_care: Optional[List[str]] = None
    actions_taken: Optional[List[str]] = None
    referrals_made: Optional[List[str]] = None
    resources_provided: Optional[List[str]] = None
    benefits_assistance: Optional[str] = None
    housing_assistance: Optional[str] = None
    transportation_assistance: Optional[str] = None
    legal_support: Optional[str] = None
    follow_up_actions: Optional[List[str]] = None
    trace: Optional[SourceTrace] = None


@dataclass
class DentalAssessment:
    chief_dental_complaint: Optional[str] = None
    oral_exam_findings: Optional[str] = None
    caries_status: Optional[str] = None
    periodontal_status: Optional[str] = None
    radiographs_reviewed: Optional[str] = None
    occlusion: Optional[str] = None
    soft_tissue_findings: Optional[str] = None
    dental_diagnoses: Optional[List[Diagnosis]] = None
    procedures_performed: Optional[List[str]] = None
    trace: Optional[SourceTrace] = None


@dataclass
class ScreeningTools:
    """
    Populate only tools actually documented (PHQ-9, GAD-7, AUDIT, DAST, etc.).
    """
    phq9: Optional[str] = None
    gad7: Optional[str] = None
    audit: Optional[str] = None
    dast: Optional[str] = None
    cage: Optional[str] = None
    other: Optional[Dict[str, str]] = None
    trace: Optional[SourceTrace] = None


# -------------------------
# Presentation Policy Layer
# -------------------------

@dataclass
class PresentationPolicy:
    """
    Controls what the reviewer sees.

    show_minimum_necessary:
      - True  => hide non-pertinent medical history by default
      - False => show more context if available

    allow_hidden_context:
      - True  => store non-pertinent findings in hidden_context fields (not shown to reviewer)
      - False => discard non-pertinent content entirely
    """
    show_minimum_necessary: bool = True
    allow_hidden_context: bool = True

    # Switches for common categories
    include_full_pmh: bool = False
    include_full_med_list: bool = True
    include_full_ros: bool = True  # still only populated systems are shown
    include_full_exam: bool = True

    # Discipline-specific visibility toggles
    include_mse: bool = True
    include_risk_assessment: bool = True
    include_treatment_plan: bool = True
    include_case_mgmt_block: bool = True
    include_dental_block: bool = True


# -------------------------
# Specialty Profiles
# -------------------------

MedicalSpecialty = Literal["InternalMedicine", "Pediatrics", "OBGYN", "InfectiousDisease", "TransgenderServices", "General"]
BehavioralSpecialty = Literal["Psychology", "MHR", "General"]

@dataclass
class SpecialtyProfile:
    """
    Specialty profiles refine what is considered "pertinent".
    Example: InfectiousDisease might prioritize exposure history, STI screening, HIV labs.
    """
    name: str
    emphasis_keywords: List[str] = field(default_factory=list)
    required_blocks: List[str] = field(default_factory=list)  # e.g., ["RiskAssessment"]


SPECIALTY_PROFILES: Dict[str, SpecialtyProfile] = {
    # Medical
    "InternalMedicine": SpecialtyProfile(
        name="InternalMedicine",
        emphasis_keywords=["chronic", "medication", "labs", "risk", "follow-up"],
        required_blocks=[]
    ),
    "Pediatrics": SpecialtyProfile(
        name="Pediatrics",
        emphasis_keywords=["immunization", "growth", "development", "guardian"],
        required_blocks=[]
    ),
    "OBGYN": SpecialtyProfile(
        name="OBGYN",
        emphasis_keywords=["LMP", "pregnancy", "contraception", "pelvic", "pap", "prenatal"],
        required_blocks=[]
    ),
    "InfectiousDisease": SpecialtyProfile(
        name="InfectiousDisease",
        emphasis_keywords=["exposure", "STI", "HIV", "hepatitis", "vaccination", "screening"],
        required_blocks=[]
    ),
    "TransgenderServices": SpecialtyProfile(
        name="TransgenderServices",
        emphasis_keywords=["gender-affirming", "hormone", "labs", "consent", "fertility", "pronouns"],
        required_blocks=[]
    ),

    # Behavioral Health
    "Psychology": SpecialtyProfile(
        name="Psychology",
        emphasis_keywords=["therapy", "CBT", "skills", "behavior", "function", "goals"],
        required_blocks=["TreatmentPlan"]
    ),
    "MHR": SpecialtyProfile(
        name="MHR",
        emphasis_keywords=["support", "engagement", "skills", "stability", "resources"],
        required_blocks=["TreatmentPlan"]
    ),
}


# -------------------------
# Base Encounter
# -------------------------

@dataclass
class BaseEncounter:
    """
    Shared across all disciplines. Keep tight and visit-focused.

    hidden_context:
      - Optional store for information extracted but not shown to reviewer (if policy allows).
      - This supports defensibility and later audits without cluttering reviewer UX.
    """
    identifiers: Identifiers = field(default_factory=Identifiers)
    provider: ProviderInfo = field(default_factory=ProviderInfo)
    meta: EncounterMeta = field(default_factory=EncounterMeta)
    policy: PresentationPolicy = field(default_factory=PresentationPolicy)

    chief_complaint: Optional[str] = None
    presenting_problem: Optional[str] = None  # a normalized short form of CC if available
    hpi: Optional[str] = None

    medications: Optional[List[Medication]] = None
    allergies: Optional[List[Allergy]] = None

    ros: Optional[ROS] = None
    vitals: Optional[Vitals] = None
    physical_exam: Optional[PhysicalExam] = None

    diagnostics: Optional[List[str]] = None          # simple list of labs/imaging/procedures ordered/reviewed
    screening_tools: Optional[ScreeningTools] = None # for BH/Psych or integrated screening where documented

    assessment: Optional[List[Diagnosis]] = None
    plan: Optional[List[PlanItem]] = None

    # Always optional; used when the policy allows keeping non-pertinent extracted context
    hidden_context: Optional[Dict[str, Any]] = None

    # ---- Required static methods for ClinIQ schema conventions ----

    @staticmethod
    def example() -> Dict[str, Any]:
        """Return a minimal example dict (not exhaustive)."""
        return {
            "identifiers": {"full_name": "Doe, Jane", "dob": "01-15-1990", "mrn": "12345"},
            "provider": {"rendering_provider": "Alex Smith", "provider_credentials": "NP"},
            "meta": {"date_of_service": "03-05-2026", "visit_type": "In-Person", "discipline": "Medical"},
            "chief_complaint": "Follow-up visit.",
            "hpi": "Patient presents for follow-up...",
            "assessment": [{"name": "Hypertension", "icd10": "I10", "status": "Established"}],
            "plan": [{"category": "FollowUp", "description": "Return in 3 months."}],
        }

    @staticmethod
    def from_json(data: Union[str, Dict[str, Any]], cls: Optional[Type["BaseEncounter"]] = None) -> "BaseEncounter":
        """
        Construct from JSON string or dict.
        Note: This is a lightweight loader; real-world validation can be layered on top.
        """
        if cls is None:
            cls = BaseEncounter
        if isinstance(data, str):
            payload = json.loads(data)
        else:
            payload = data

        def _obj(dc_cls, v):
            if v is None:
                return None
            return dc_cls(**v)

        # Manual construction to keep dependency-free and predictable
        obj = cls(
            identifiers=_obj(Identifiers, payload.get("identifiers", {})) or Identifiers(),
            provider=_obj(ProviderInfo, payload.get("provider", {})) or ProviderInfo(),
            meta=_obj(EncounterMeta, payload.get("meta", {})) or EncounterMeta(),
            policy=_obj(PresentationPolicy, payload.get("policy", {})) or PresentationPolicy(),
            chief_complaint=payload.get("chief_complaint"),
            presenting_problem=payload.get("presenting_problem"),
            hpi=payload.get("hpi"),
            medications=[Medication(**m) for m in payload.get("medications", [])] if payload.get("medications") else None,
            allergies=[Allergy(**a) for a in payload.get("allergies", [])] if payload.get("allergies") else None,
            ros=_obj(ROS, payload.get("ros")),
            vitals=_obj(Vitals, payload.get("vitals")),
            physical_exam=_obj(PhysicalExam, payload.get("physical_exam")),
            diagnostics=payload.get("diagnostics"),
            screening_tools=_obj(ScreeningTools, payload.get("screening_tools")),
            assessment=[Diagnosis(**d) for d in payload.get("assessment", [])] if payload.get("assessment") else None,
            plan=[PlanItem(**p) for p in payload.get("plan", [])] if payload.get("plan") else None,
            hidden_context=payload.get("hidden_context"),
        )
        return obj

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return asdict(self)


# -------------------------
# Discipline Encounters
# -------------------------

@dataclass
class MedicalEncounter(BaseEncounter):
    """
    Medical discipline encounter.

    Specialty profiles supported:
      - InternalMedicine, Pediatrics, OBGYN, InfectiousDisease, TransgenderServices, General

    Medical-specific note:
      - For non-medical disciplines (BH/CM/Dental), DO NOT use this schema unless the visit truly was medical.
    """
    meta: EncounterMeta = field(default_factory=lambda: EncounterMeta(discipline="Medical"))
    medical_specialty: Optional[MedicalSpecialty] = "General"

    # Optional medical blocks; only populate if documented and relevant
    problem_focused_pmh: Optional[List[str]] = None  # Only PMH relevant to CC
    immunizations: Optional[List[str]] = None
    procedures: Optional[List[str]] = None


@dataclass
class PsychiatryEncounter(BaseEncounter):
    """
    Psychiatry encounter: focuses on diagnosis, meds, MSE, risk, and med management.
    Only include general medical data if directly relevant to psychiatric safety or prescribing.
    """
    meta: EncounterMeta = field(default_factory=lambda: EncounterMeta(discipline="Psychiatry"))
    mse: Optional[MentalStatusExam] = None
    risk: Optional[RiskAssessment] = None
    treatment_plan: Optional[TreatmentPlan] = None

    # Psychiatry-specific
    psychiatric_history: Optional[str] = None
    substance_use_history: Optional[str] = None
    medication_adherence: Optional[str] = None


@dataclass
class BehavioralHealthEncounter(BaseEncounter):
    """
    Behavioral Health (therapy/counseling) encounter.

    Specialty profiles supported:
      - Psychology, MHR, General

    Medical info should be *minimal necessary*:
      - only items that affect therapy, safety, or care coordination.
    """
    meta: EncounterMeta = field(default_factory=lambda: EncounterMeta(discipline="BehavioralHealth"))
    behavioral_specialty: Optional[BehavioralSpecialty] = "General"

    mse: Optional[MentalStatusExam] = None
    risk: Optional[RiskAssessment] = None
    treatment_plan: Optional[TreatmentPlan] = None

    # Therapy session structure
    session_focus: Optional[str] = None
    interventions_used: Optional[List[str]] = None  # e.g., CBT, MI, grounding, psychoeducation
    response_to_intervention: Optional[str] = None
    homework_or_practice: Optional[str] = None


@dataclass
class CaseManagementEncounter(BaseEncounter):
    """
    Case Management encounter.

    Do not surface broad medical content.
    Only include medical items if they are directly connected to:
      - eligibility, benefits, referrals, care coordination, barriers, adherence support, or safety.
    """
    meta: EncounterMeta = field(default_factory=lambda: EncounterMeta(discipline="CaseManagement"))
    case_management: Optional[CaseManagementBlock] = None

    # CM-specific
    acuity_level: Optional[str] = None
    service_plan: Optional[TreatmentPlan] = None  # can reuse TreatmentPlan structure for service plans
    consent_for_release: Optional[bool] = None


@dataclass
class DentalEncounter(BaseEncounter):
    """
    Dental encounter.

    Only include medical history that affects dental care (e.g., anticoagulants, diabetes, endocarditis risk).
    """
    meta: EncounterMeta = field(default_factory=lambda: EncounterMeta(discipline="Dental"))
    dental: Optional[DentalAssessment] = None

    # Dental-specific
    anesthesia_used: Optional[str] = None
    pain_management_plan: Optional[str] = None


# -------------------------
# Helper: Policy Presets
# -------------------------

def default_policy_for(discipline: str) -> PresentationPolicy:
    """
    Recommended defaults:
      - Medical: show meds/allergies/ROS/Exam relevant systems
      - Psychiatry/BH: show MSE + risk prominently; medical data only if relevant
      - Case Management: show CM actions; minimal medical
      - Dental: show dental block; only pertinent medical
    """
    d = discipline
    if d == "Medical":
        return PresentationPolicy(
            show_minimum_necessary=True,
            allow_hidden_context=True,
            include_full_pmh=False,
            include_full_med_list=True,
            include_full_ros=True,
            include_full_exam=True,
            include_mse=False,
            include_risk_assessment=False,
            include_treatment_plan=False,
            include_case_mgmt_block=False,
            include_dental_block=False,
        )
    if d == "Psychiatry":
        return PresentationPolicy(
            show_minimum_necessary=True,
            allow_hidden_context=True,
            include_full_pmh=False,
            include_full_med_list=True,  # relevant for prescribing
            include_full_ros=False,
            include_full_exam=False,
            include_mse=True,
            include_risk_assessment=True,
            include_treatment_plan=True,
            include_case_mgmt_block=False,
            include_dental_block=False,
        )
    if d == "BehavioralHealth":
        return PresentationPolicy(
            show_minimum_necessary=True,
            allow_hidden_context=True,
            include_full_pmh=False,
            include_full_med_list=False,  # only include if therapy-relevant
            include_full_ros=False,
            include_full_exam=False,
            include_mse=True,
            include_risk_assessment=True,
            include_treatment_plan=True,
            include_case_mgmt_block=False,
            include_dental_block=False,
        )
    if d == "CaseManagement":
        return PresentationPolicy(
            show_minimum_necessary=True,
            allow_hidden_context=True,
            include_full_pmh=False,
            include_full_med_list=False,
            include_full_ros=False,
            include_full_exam=False,
            include_mse=False,
            include_risk_assessment=False,
            include_treatment_plan=True,   # as service plan
            include_case_mgmt_block=True,
            include_dental_block=False,
        )
    if d == "Dental":
        return PresentationPolicy(
            show_minimum_necessary=True,
            allow_hidden_context=True,
            include_full_pmh=False,
            include_full_med_list=True,    # but only if dental-relevant
            include_full_ros=False,
            include_full_exam=False,
            include_mse=False,
            include_risk_assessment=False,
            include_treatment_plan=False,
            include_case_mgmt_block=False,
            include_dental_block=True,
        )
    return PresentationPolicy()


# -------------------------
# Helper: Build Encounter
# -------------------------

EncounterType = Union[MedicalEncounter, PsychiatryEncounter, BehavioralHealthEncounter, CaseManagementEncounter, DentalEncounter]

def make_encounter(discipline: Literal["Medical", "Psychiatry", "BehavioralHealth", "CaseManagement", "Dental"],
                   specialty: Optional[str] = None) -> EncounterType:
    """
    Convenience constructor used by ClinIQ when initializing a parse target.
    """
    if discipline == "Medical":
        e = MedicalEncounter()
        e.policy = default_policy_for("Medical")
        e.meta.specialty_profile = specialty
        if specialty in SPECIALTY_PROFILES:
            e.medical_specialty = specialty  # type: ignore
        return e
    if discipline == "Psychiatry":
        e = PsychiatryEncounter()
        e.policy = default_policy_for("Psychiatry")
        e.meta.specialty_profile = specialty
        return e
    if discipline == "BehavioralHealth":
        e = BehavioralHealthEncounter()
        e.policy = default_policy_for("BehavioralHealth")
        e.meta.specialty_profile = specialty
        if specialty in ("Psychology", "MHR"):
            e.behavioral_specialty = specialty  # type: ignore
        return e
    if discipline == "CaseManagement":
        e = CaseManagementEncounter()
        e.policy = default_policy_for("CaseManagement")
        e.meta.specialty_profile = specialty
        return e
    if discipline == "Dental":
        e = DentalEncounter()
        e.policy = default_policy_for("Dental")
        e.meta.specialty_profile = specialty
        return e
    # fallback
    e = MedicalEncounter()
    e.policy = default_policy_for("Medical")
    return e


# -----------------------------------------------------------------------------
# ClinIQ runtime schema contract used by pipeline map/evaluate handlers.
# -----------------------------------------------------------------------------
from pydantic import BaseModel, Field


class PatientRecordIdentifiersV1(BaseModel):
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    mrn: Optional[str] = None
    encounter_number: Optional[str] = None
    rendering_provider: Optional[str] = None
    age: Optional[int] = None
    date_of_service: Optional[str] = None
    visit_type: Optional[str] = None
    primary_location: Optional[str] = None
    sex_at_birth: Optional[str] = None
    gender_identity: Optional[str] = None


class PatientRecordSectionV1(BaseModel):
    summary: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    not_documented: bool = False
    flag: Optional[str] = None


class PatientRecordMetaV1(BaseModel):
    discipline: Literal[
        "Medical", "Psychiatry", "BehavioralHealth", "CaseManagement", "Dental"
    ] = "Medical"
    specialty_profile: Optional[str] = None
    template_key: Optional[str] = None


class PatientRecord(BaseModel):
    __schema_version__ = "patient_record_v1"

    schema_version: str = Field(default=__schema_version__)
    meta: PatientRecordMetaV1 = Field(default_factory=PatientRecordMetaV1)
    identifiers: PatientRecordIdentifiersV1 = Field(default_factory=PatientRecordIdentifiersV1)
    chief_complaint: Optional[PatientRecordSectionV1] = None
    hpi: Optional[PatientRecordSectionV1] = None
    family_history: Optional[PatientRecordSectionV1] = None
    social_history: Optional[PatientRecordSectionV1] = None
    medications: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    ros: Optional[dict[str, Any]] = None
    vital_signs: Optional[dict[str, Any]] = None
    physical_exam: Optional[dict[str, Any]] = None
    diagnostic_data: Optional[list[str]] = None
    assessment: Optional[list[str]] = None
    plan: Optional[list[str]] = None
    validation_issues: Optional[list[str]] = None

    @staticmethod
    def example() -> Dict[str, Any]:
        return {
            "schema_version": "patient_record_v1",
            "meta": {
                "discipline": "Medical",
                "specialty_profile": "InternalMedicine",
                "template_key": "medical_patient_record_template",
            },
            "identifiers": {
                "full_name": "Jane Doe",
                "date_of_birth": "01-15-1990",
                "mrn": "MRN-100234",
                "encounter_number": "ENC-20260305-001",
                "rendering_provider": "Alex Smith, NP",
                "age": 36,
                "date_of_service": "03-05-2026",
                "visit_type": "Follow-up",
                "primary_location": "ClinIQ Main Campus",
                "sex_at_birth": "Female",
                "gender_identity": "Female",
            },
            "chief_complaint": {"summary": "Follow up for chronic condition."},
            "hpi": {"summary": "Patient reports improved symptoms over the last 2 weeks."},
            "medications": ["lisinopril 10mg daily"],
            "allergies": ["NKDA"],
            "assessment": ["Hypertension"],
            "plan": ["Continue current medications", "Return in 3 months"],
        }

    @staticmethod
    def from_json(data: Union[str, Dict[str, Any]]) -> "PatientRecord":
        if isinstance(data, str):
            return PatientRecord.model_validate_json(data)
        return PatientRecord.model_validate(data)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @staticmethod
    def json_schema() -> Dict[str, Any]:
        return PatientRecord.model_json_schema()

    @staticmethod
    def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload or {})
        meta = dict(normalized.get("meta") or {})
        discipline = meta.get("discipline") or "Medical"
        meta["discipline"] = discipline
        meta["template_key"] = PatientRecord.resolve_template_key(
            {"meta": meta}
        )
        ids = dict(normalized.get("identifiers") or {})
        ids["date_of_birth"] = PatientRecord._normalize_date_mmddyyyy(
            ids.get("date_of_birth")
        )
        ids["date_of_service"] = PatientRecord._normalize_date_mmddyyyy(
            ids.get("date_of_service")
        )
        normalized["identifiers"] = ids
        normalized["meta"] = meta
        normalized["schema_version"] = PatientRecord.__schema_version__
        return normalized

    @staticmethod
    def validate_payload(payload: Dict[str, Any]) -> list[str]:
        issues: list[str] = []
        ids = dict(payload.get("identifiers") or {})

        if not ids.get("mrn"):
            issues.append("Missing required field: identifiers.mrn")
        elif not PatientRecord._is_mrn_like(str(ids["mrn"])):
            issues.append("Invalid identifiers.mrn format")

        if ids.get("age") is None:
            issues.append("Missing required field: identifiers.age")

        dos = ids.get("date_of_service")
        if not dos:
            issues.append("Missing required field: identifiers.date_of_service")
        elif isinstance(dos, str) and not PatientRecord._is_mmddyyyy(dos):
            issues.append("Invalid identifiers.date_of_service format (expected MM-DD-YYYY)")

        if not ids.get("visit_type"):
            issues.append("Missing required field: identifiers.visit_type")

        return issues

    @staticmethod
    def section_completeness(payload: Dict[str, Any]) -> Dict[str, float]:
        tracked_sections = [
            "chief_complaint",
            "hpi",
            "family_history",
            "social_history",
            "medications",
            "allergies",
            "ros",
            "vital_signs",
            "physical_exam",
            "diagnostic_data",
            "assessment",
            "plan",
        ]
        result: Dict[str, float] = {}
        for section in tracked_sections:
            value = payload.get(section)
            if isinstance(value, dict):
                has_data = any(v not in (None, "", [], {}, "ND") for v in value.values())
                result[section] = 1.0 if has_data else 0.0
            elif isinstance(value, list):
                result[section] = 1.0 if len(value) > 0 else 0.0
            else:
                result[section] = 1.0 if value not in (None, "", "ND") else 0.0
        return result

    @staticmethod
    def _normalize_date_mmddyyyy(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None

        formats = [
            "%Y-%m-%d",
            "%m-%d-%Y",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%m-%d-%y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt).strftime("%m-%d-%Y")
            except ValueError:
                pass
        return raw

    @staticmethod
    def _is_mmddyyyy(value: str) -> bool:
        return bool(
            re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])-\d{4}$", value.strip())
        )

    @staticmethod
    def _is_mrn_like(value: str) -> bool:
        v = value.strip()
        return len(v) >= 4 and any(ch.isdigit() for ch in v)

    @staticmethod
    def resolve_template_key(payload: Dict[str, Any]) -> str:
        meta = dict(payload.get("meta") or {})
        discipline = meta.get("discipline", "Medical")
        mapping = {
            "Medical": "medical_patient_record_template",
            "Psychiatry": "psychiatry_patient_record_template",
            "BehavioralHealth": "behavioral_health_patient_record_template",
            "CaseManagement": "case_management_patient_record_template",
            "Dental": "dental_patient_record_template",
        }
        return mapping.get(discipline, "medical_patient_record_template")

    @staticmethod
    def to_cliniq_payload(payload: Dict[str, Any], source_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        original = dict(payload or {})
        source = PatientRecord.normalize_payload(original)

        src_meta = dict(source_metadata or {})
        meta = dict(source.get("meta") or {})

        discipline = PatientRecord.infer_discipline(original, src_meta)
        specialty = PatientRecord.infer_specialty(original, discipline, src_meta)
        meta["discipline"] = discipline
        meta["specialty_profile"] = specialty
        meta["template_key"] = PatientRecord.resolve_template_key({"meta": meta})
        source["meta"] = meta

        encounter = make_encounter(discipline, specialty=specialty)

        # Map identifiers and encounter metadata.
        ids = dict(source.get("identifiers") or {})
        encounter.identifiers.full_name = ids.get("full_name")
        encounter.identifiers.dob = ids.get("date_of_birth")
        encounter.identifiers.mrn = ids.get("mrn")
        encounter.identifiers.encounter_id = ids.get("encounter_number")

        encounter.provider.rendering_provider = ids.get("rendering_provider")
        encounter.provider.location = ids.get("primary_location")
        encounter.meta.date_of_service = ids.get("date_of_service")
        encounter.meta.visit_type = ids.get("visit_type")
        encounter.meta.discipline = discipline
        encounter.meta.specialty_profile = specialty

        if isinstance(source.get("chief_complaint"), dict):
            encounter.chief_complaint = source["chief_complaint"].get("summary")
        if isinstance(source.get("hpi"), dict):
            encounter.hpi = source["hpi"].get("summary")

        if isinstance(source.get("medications"), list):
            encounter.medications = [Medication(name=m) for m in source["medications"] if m]
        if isinstance(source.get("allergies"), list):
            encounter.allergies = [Allergy(allergen=a) for a in source["allergies"] if a]
        if isinstance(source.get("assessment"), list):
            encounter.assessment = [Diagnosis(name=a) for a in source["assessment"] if a]
        if isinstance(source.get("plan"), list):
            encounter.plan = [PlanItem(category="Other", description=p) for p in source["plan"] if p]

        result = {
            "schema_version": source.get("schema_version", PatientRecord.__schema_version__),
            "template_key": PatientRecord.resolve_template_key(source),
            "discipline": discipline,
            "specialty_profile": specialty,
            "encounter": asdict(encounter),
            "validation_issues": source.get("validation_issues", []),
            "section_completeness": PatientRecord.section_completeness(source),
            "source_metadata": source_metadata or {},
        }
        return result

    @staticmethod
    def infer_discipline(payload: Dict[str, Any], source_metadata: Optional[Dict[str, Any]] = None) -> str:
        source_metadata = source_metadata or {}
        explicit = str(
            source_metadata.get("discipline")
            or (payload.get("meta") or {}).get("discipline")
            or ""
        ).strip()
        allowed = {"Medical", "Psychiatry", "BehavioralHealth", "CaseManagement", "Dental"}
        if explicit in allowed:
            return explicit

        text = PatientRecord._collect_text(payload).lower()
        score = {
            "Psychiatry": 0,
            "BehavioralHealth": 0,
            "CaseManagement": 0,
            "Dental": 0,
            "Medical": 0,
        }

        for kw in ["depression", "anxiety", "suicidal", "psychosis", "mood", "psychiatry", "mse"]:
            if kw in text:
                score["Psychiatry"] += 2
        for kw in ["therapy", "counseling", "cbt", "intervention", "coping", "behavioral"]:
            if kw in text:
                score["BehavioralHealth"] += 2
        for kw in ["case management", "housing", "transportation", "benefits", "care coordination", "social worker"]:
            if kw in text:
                score["CaseManagement"] += 2
        for kw in ["dental", "tooth", "teeth", "gingiva", "periodontal", "caries", "oral"]:
            if kw in text:
                score["Dental"] += 2
        for kw in ["blood pressure", "hypertension", "diabetes", "follow-up", "medical"]:
            if kw in text:
                score["Medical"] += 1

        inferred = max(score, key=score.get)
        return inferred if score[inferred] > 0 else "Medical"

    @staticmethod
    def infer_specialty(
        payload: Dict[str, Any],
        discipline: str,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        source_metadata = source_metadata or {}
        explicit = str(
            source_metadata.get("specialty_profile")
            or (payload.get("meta") or {}).get("specialty_profile")
            or ""
        ).strip()
        if explicit:
            return explicit

        text = PatientRecord._collect_text(payload).lower()
        if discipline == "Medical":
            if "obgyn" in text or "pregnancy" in text or "prenatal" in text:
                return "OBGYN"
            if "hiv" in text or "hepatitis" in text or "sti" in text:
                return "InfectiousDisease"
            if "pediatric" in text or "guardian" in text or "immunization" in text:
                return "Pediatrics"
            return "InternalMedicine"
        if discipline == "BehavioralHealth":
            if "mhr" in text:
                return "MHR"
            return "Psychology"
        return None

    @staticmethod
    def _collect_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return " ".join(PatientRecord._collect_text(v) for v in value)
        if isinstance(value, dict):
            return " ".join(PatientRecord._collect_text(v) for v in value.values())
        return str(value)
