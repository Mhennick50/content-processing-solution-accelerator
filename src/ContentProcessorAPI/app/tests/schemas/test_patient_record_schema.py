import importlib.util
from pathlib import Path
import sys


def _load_patient_record_module():
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "samples"
        / "schemas"
        / "patient_record.py"
    )
    spec = importlib.util.spec_from_file_location("patient_record_schema", schema_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_patient_record_has_required_contract_methods():
    module = _load_patient_record_module()
    patient_record = module.PatientRecord.from_json(module.PatientRecord.example())

    assert isinstance(module.PatientRecord.json_schema(), dict)
    assert isinstance(patient_record.to_dict(), dict)
    assert patient_record.to_dict()["schema_version"] == "patient_record_v1"


def test_patient_record_normalize_and_validate_payload():
    module = _load_patient_record_module()
    payload = {
        "identifiers": {
            "mrn": "ABC1234",
            "age": 40,
            "date_of_service": "2026-03-05",
            "visit_type": "Follow-up",
        }
    }
    normalized = module.PatientRecord.normalize_payload(payload)
    issues = module.PatientRecord.validate_payload(normalized)

    assert normalized["identifiers"]["date_of_service"] == "03-05-2026"
    assert issues == []


def test_patient_record_builds_cliniq_payload():
    module = _load_patient_record_module()
    payload = {
        "meta": {"discipline": "Medical", "specialty_profile": "InternalMedicine"},
        "identifiers": {
            "full_name": "Jane Doe",
            "mrn": "MRN12345",
            "age": 40,
            "date_of_service": "03/05/2026",
            "visit_type": "Follow-up",
            "rendering_provider": "Alex Smith",
            "encounter_number": "ENC-001",
        },
        "chief_complaint": {"summary": "Headache"},
        "assessment": ["Migraine"],
        "plan": ["Hydration and rest"],
    }
    shaped = module.PatientRecord.to_cliniq_payload(
        payload, {"tenant_id": "cliniq", "encounter_id": "enc-001"}
    )

    assert shaped["template_key"] == "medical_patient_record_template"
    assert shaped["discipline"] == "Medical"
    assert shaped["encounter"]["identifiers"]["mrn"] == "MRN12345"
    assert shaped["source_metadata"]["tenant_id"] == "cliniq"


def test_patient_record_auto_detects_discipline_and_specialty():
    module = _load_patient_record_module()
    payload = {
        "chief_complaint": {"summary": "Follow up for anxiety and depression"},
        "assessment": ["Major depressive disorder"],
        "plan": ["Psychotherapy follow up"],
        "identifiers": {"mrn": "12345", "age": 30, "date_of_service": "03-05-2026", "visit_type": "Follow-up"},
    }
    shaped = module.PatientRecord.to_cliniq_payload(payload, {})

    assert shaped["discipline"] in {"Psychiatry", "BehavioralHealth"}
    assert shaped["template_key"] in {
        "psychiatry_patient_record_template",
        "behavioral_health_patient_record_template",
    }
