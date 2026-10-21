"""
Import scope policy (unit): the pre-enrolled student importer never touches
financial/demo tables, keeps roster scoping tight, and is idempotent by
design (PK skip + username/registration-ID business keys).
"""
import importlib.util
import sys
import uuid
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "import_preview_students.py"
_spec = importlib.util.spec_from_file_location("import_preview_students", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["import_preview_students"] = _mod
_spec.loader.exec_module(_mod)


def _sample_source():
    sid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    eid = str(uuid.uuid4())
    return {
        "students": [{"id": sid, "user_id": uid, "cma_registration_id": "CMA-2026-7001",
                      "portal_slug": "unitstu", "first_name": "Unit", "last_name": "Stu"}],
        "users": [{"id": uid, "username": "unitstu", "role": "STUDENT",
                   "hashed_password": "$2b$12$abcdefghijklmnop", "is_active": 1}],
        "enrollments": [{"id": eid, "student_id": sid, "programme_id": "piano",
                         "programme_name": "Piano", "fee_plan": "4_classes", "status": "active"}],
        "class_sessions": [{"id": str(uuid.uuid4()), "student_id": sid, "enrollment_id": eid,
                            "scheduled_date": "2026-11-02", "scheduled_start": "17:00:00",
                            "scheduled_end": "18:00:00", "status": "scheduled"}],
        "invoices": [{"id": str(uuid.uuid4()), "student_id": sid, "invoice_number": "X"}],
        "payments": [{"id": str(uuid.uuid4()), "amount_paise": 1}],
        "fee_records": [{"id": str(uuid.uuid4()), "student_id": sid}],
        "credit_ledger": [{"id": str(uuid.uuid4()), "student_id": sid}],
        "exam_fees": [{"id": str(uuid.uuid4()), "student_id": sid}],
        "audit_events": [{"id": str(uuid.uuid4())}],
        "sequence_counters": [{"name": "cma_seq_2026", "value": 5}],
        "support_requests": [{"id": str(uuid.uuid4())}],
        "notifications": [{"id": str(uuid.uuid4()), "user_id": uid}],
    }


def test_financial_and_demo_tables_are_never_imported():
    src = _sample_source()
    scope = _mod.build_scope(src)
    for t in _mod.FINANCIAL_TABLES:
        assert t not in _mod.IMPORT_ORDER, t
    for t in ("audit_events", "sequence_counters", "support_requests"):
        assert t in _mod.OUT_OF_SCOPE_TABLES, t
    assert _mod.select_scope("invoices", src["invoices"], scope) == []
    assert _mod.select_scope("payments", src["payments"], scope) == []
    assert _mod.select_scope("fee_records", src["fee_records"], scope) == []
    assert _mod.select_scope("credit_ledger", src["credit_ledger"], scope) == []
    assert _mod.select_scope("exam_fees", src["exam_fees"], scope) == []
    assert _mod.select_scope("audit_events", src["audit_events"], scope) == []


def test_roster_scoping_keeps_only_linked_rows():
    src = _sample_source()
    stranger = str(uuid.uuid4())
    src["enrollments"].append({"id": str(uuid.uuid4()), "student_id": stranger,
                               "programme_id": "x", "programme_name": "X", "status": "active"})
    src["class_sessions"].append({"id": str(uuid.uuid4()), "student_id": stranger,
                                  "scheduled_date": "2026-11-03", "scheduled_start": "10:00:00",
                                  "scheduled_end": "11:00:00", "status": "scheduled"})
    scope = _mod.build_scope(src)
    enr = _mod.select_scope("enrollments", src["enrollments"], scope)
    assert len(enr) == 1 and enr[0]["student_id"] == scope["roster"].copy().pop()
    ses = _mod.select_scope("class_sessions", src["class_sessions"], scope)
    assert len(ses) == 1
    # only roster users are imported
    users = _mod.select_scope("users", src["users"], scope)
    assert [u["username"] for u in users] == ["unitstu"]


def test_notifications_scoped_to_imported_users():
    src = _sample_source()
    src["notifications"].append({"id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())})
    scope = _mod.build_scope(src)
    notes = _mod.select_scope("notifications", src["notifications"], scope)
    assert len(notes) == 1
