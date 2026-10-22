"""
Fee packages, month-wise ledger, invoices, payments and Razorpay webhooks.

Money is integer paise throughout. Ledger state changes only after a
verified provider event or an explicit authorized manual reconciliation —
never because a browser landed on a success URL.
"""
import json
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.roles import UserRole
from app.config import get_settings
from app.database import get_db
from app.models.billing import (
    FeePackage,
    Invoice,
    Payment,
    PaymentAllocation,
    PaymentEvent,
    PaymentOrder,
)
from app.models.enrollment import Enrollment
from app.models.fee_record import FeeRecord
from app.models.finance import CreditLedgerEntry, ExamFee, Receipt
from app.models.session import ClassSession
from app.models.student import Student
from app.models.user import User
from app.models.support import SupportRequest, SupportAttachment
from app.services.files import save_upload, safe_filename, PAYMENT_EVIDENCE_TYPES
from app.services.access import get_linked_student_ids, require_student_access
from app.services.audit import record_audit
from app.services.ids import generate_invoice_number
from app.services.notifications import notify_user
from app.services.payments import PaymentGatewayError, razorpay_service

router = APIRouter()


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------
class InvoiceCreate(BaseModel):
    enrollment_id: UUID
    billing_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    package_id: Optional[UUID] = None
    charge_type: str = Field("tuition", pattern="^(tuition|exam|other)$")
    description: Optional[str] = None
    amount_paise: Optional[int] = Field(None, gt=0)   # required for exam/other
    due_date: Optional[str] = None
    notes: Optional[str] = None


class GenerateChargesRequest(BaseModel):
    billing_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    due_day: Optional[int] = Field(None, ge=1, le=28)
    student_ids: Optional[List[UUID]] = None   # default: every active enrolment
    include_per_class: bool = True


class CreditApplyRequest(BaseModel):
    student_id: UUID
    invoice_id: UUID
    amount_paise: int = Field(..., gt=0)
    note: Optional[str] = None


class CreditAdvanceRequest(BaseModel):
    student_id: UUID
    enrollment_id: Optional[UUID] = None
    amount_paise: int = Field(..., gt=0)
    method: str = Field(..., min_length=2)
    paid_at: Optional[str] = None
    reference: Optional[str] = None
    payer_name: Optional[str] = None
    notes: Optional[str] = None


class VoidInvoiceRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class ExamFeeCreate(BaseModel):
    student_id: UUID
    enrollment_id: Optional[UUID] = None
    exam_id: Optional[UUID] = None
    board: Optional[str] = None
    instrument: Optional[str] = None
    grade_level: Optional[str] = None
    exam_session: Optional[str] = None
    fee_charged_paise: int = Field(0, ge=0)
    academy_paid_paise: int = Field(0, ge=0)
    provider_reference: Optional[str] = None
    notes: Optional[str] = None
    create_invoice: bool = True
    billing_month: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}$")
    due_date: Optional[str] = None


class ExamFeeUpdate(BaseModel):
    academy_paid_delta_paise: Optional[int] = None
    provider_reference: Optional[str] = None
    notes: Optional[str] = None


class ExamFeeReimburse(BaseModel):
    amount_paise: int = Field(..., gt=0)
    method: str = Field(..., min_length=2)
    date: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class OrderCreate(BaseModel):
    invoice_id: UUID


class AllocationSpec(BaseModel):
    invoice_id: UUID
    amount_paise: int = Field(..., gt=0)


class AllocatePaymentRequest(BaseModel):
    allocations: List[AllocationSpec] = Field(..., min_length=1)
    reason: Optional[str] = None


class ManualPaymentRequest(BaseModel):
    amount_paise: int = Field(..., gt=0)
    method: str = Field(..., min_length=2)
    paid_at: Optional[str] = None
    reference: Optional[str] = None
    payer_name: Optional[str] = None
    notes: Optional[str] = None
    allocations: List[AllocationSpec] = Field(..., min_length=1)
    # any amount beyond the allocations is kept as an advance credit on the
    # student's account (never silently dropped)
    keep_remainder_as_credit: bool = False


class ReverseAllocationRequest(BaseModel):
    reason: str = Field(..., min_length=3)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _serialize_invoice(inv: Invoice) -> dict:
    outstanding = max(inv.amount_paise - inv.amount_paid_paise, 0)
    return {
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "enrollment_id": str(inv.enrollment_id),
        "student_id": str(inv.student_id),
        "billing_month": inv.billing_month,
        "amount_paise": inv.amount_paise,
        "amount_paid_paise": inv.amount_paid_paise,
        "outstanding_paise": outstanding,
        "currency": inv.currency,
        "status": inv.status,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        "notes": inv.notes,
        "charge_type": inv.charge_type or "tuition",
        "description": inv.description,
    }


def _serialize_payment(payment: Payment) -> dict:
    return {
        "id": str(payment.id),
        "provider": payment.provider,
        "provider_payment_id": payment.provider_payment_id,
        "order_id": payment.order_id,
        "invoice_id": str(payment.invoice_id) if payment.invoice_id else None,
        "payer_name": payment.payer_name,
        "amount_paise": payment.amount_paise,
        "currency": payment.currency,
        "method": payment.method,
        "status": payment.status,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "verified_at": payment.verified_at.isoformat() if payment.verified_at else None,
        "notes": payment.notes,
        "receipt_number": payment.receipt_number,
        "source": payment.source or "manual",
    }


async def _apply_allocation(db: AsyncSession, invoice: Invoice, amount: int) -> None:
    """Update invoice totals + mirrored fee record inside the caller's transaction."""
    invoice.amount_paid_paise = (invoice.amount_paid_paise or 0) + amount
    if invoice.amount_paid_paise >= invoice.amount_paise:
        invoice.status = "paid"
    elif invoice.amount_paid_paise > 0:
        invoice.status = "partially_paid"
    else:
        invoice.status = "pending"
    invoice.updated_at = datetime.utcnow()

    if invoice.fee_record_id:
        fee_result = await db.execute(select(FeeRecord).where(FeeRecord.id == invoice.fee_record_id))
        fee = fee_result.scalar_one_or_none()
        if fee:
            fee.amount_paid = float(invoice.amount_paid_paise) / 100.0
            if invoice.status == "paid":
                fee.payment_status = "paid"
            elif invoice.status == "partially_paid":
                fee.payment_status = "partial"
            else:
                fee.payment_status = "pending"


async def _recompute_invoice_from_allocations(db: AsyncSession, invoice_id: UUID) -> None:
    result = await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.invoice_id == invoice_id)
    )
    total = sum(a.amount_paise for a in result.scalars().all())
    inv_result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = inv_result.scalar_one_or_none()
    if not invoice:
        return
    invoice.amount_paid_paise = total
    if total >= invoice.amount_paise:
        invoice.status = "paid"
    elif total > 0:
        invoice.status = "partially_paid"
    else:
        invoice.status = "pending"
    invoice.updated_at = datetime.utcnow()

    if invoice.fee_record_id:
        fee_result = await db.execute(select(FeeRecord).where(FeeRecord.id == invoice.fee_record_id))
        fee = fee_result.scalar_one_or_none()
        if fee:
            fee.amount_paid = float(total) / 100.0
            fee.payment_status = invoice.status


async def _issue_receipt(db: AsyncSession, payment: Payment, issued_by: Optional[UUID]) -> str:
    """Assign a receipt number to a verified payment exactly once."""
    if payment.receipt_number:
        return payment.receipt_number
    existing = (await db.execute(
        select(Receipt).where(Receipt.payment_id == payment.id))).scalar_one_or_none()
    if existing:
        payment.receipt_number = existing.receipt_number
        return existing.receipt_number
    year = (payment.paid_at or datetime.utcnow()).year
    seq = (await db.execute(
        select(func.count(Receipt.id)).where(Receipt.receipt_number.like(f"CMA/RCPT/{year}/%"))
    )).scalar_one() or 0
    number = f"CMA/RCPT/{year}/{seq + 1:04d}"
    while (await db.execute(select(Receipt).where(Receipt.receipt_number == number))).scalar_one_or_none():
        seq += 1
        number = f"CMA/RCPT/{year}/{seq + 1:04d}"
    db.add(Receipt(payment_id=payment.id, receipt_number=number, issued_by=issued_by))
    payment.receipt_number = number
    db.add(payment)
    return number


async def _credit_balance(db: AsyncSession, student_id: UUID) -> int:
    rows = (await db.execute(
        select(CreditLedgerEntry.amount_paise).where(CreditLedgerEntry.student_id == student_id)
    )).scalars().all()
    return sum(rows)


async def _record_credit(db: AsyncSession, *, student_id, kind, amount_paise, created_by,
                         enrollment_id=None, payment_id=None, invoice_id=None, note=None) -> CreditLedgerEntry:
    entry = CreditLedgerEntry(
        student_id=student_id,
        enrollment_id=enrollment_id,
        kind=kind,
        amount_paise=amount_paise,
        payment_id=payment_id,
        invoice_id=invoice_id,
        note=note,
        created_by=created_by,
    )
    db.add(entry)
    return entry


async def _allocated_total_for_payment(db: AsyncSession, payment_id: UUID) -> int:
    result = await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_id)
    )
    return sum(a.amount_paise for a in result.scalars().all())


async def _scoped_invoice_ids(db: AsyncSession, user: User) -> Optional[List[UUID]]:
    """None = unrestricted (admin). List = only these invoices may be seen."""
    if user.role == UserRole.ADMIN:
        return None
    if user.role in (UserRole.STUDENT, UserRole.PARENT):
        student_ids = await get_linked_student_ids(db, user)
        result = await db.execute(select(Invoice.id).where(Invoice.student_id.in_(student_ids)))
        return list(result.scalars().all())
    return []


# ------------------------------------------------------------------
# Packages
# ------------------------------------------------------------------
@router.get("/packages")
async def list_packages(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(FeePackage).where(FeePackage.is_active.is_(True)).order_by(FeePackage.fee_paise.asc())
    )
    return [
        {
            "id": str(p.id),
            "code": p.code,
            "name": p.name,
            "sessions_included": p.sessions_included,
            "fee_paise": p.fee_paise,
            "currency": p.currency,
            "billing_period": p.billing_period,
            "session_duration_minutes": p.session_duration_minutes,
            "description": p.description,
            "is_legacy": p.is_legacy,
        }
        for p in result.scalars().all()
    ]


class FeePackageUpsert(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=120)
    sessions_included: int = Field(ge=1, le=31)
    fee_paise: int = Field(gt=0, le=100_000_000)  # integer paise, max ₹10 lakh
    session_duration_minutes: int = Field(default=60, ge=15, le=240)
    description: Optional[str] = Field(default=None, max_length=500)
    is_legacy: bool = False


@router.post("/packages", status_code=status.HTTP_201_CREATED)
async def upsert_fee_package(
    body: FeePackageUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """
    Admin-only operational configuration: create or update a fee package.
    Codes are upserted; existing packages used on invoices are never deleted
    or deactivated implicitly.
    """
    result = await db.execute(select(FeePackage).where(FeePackage.code == body.code))
    existing = result.scalar_one_or_none()

    if existing:
        before = {"name": existing.name, "fee_paise": existing.fee_paise}
        existing.name = body.name
        existing.sessions_included = body.sessions_included
        existing.fee_paise = body.fee_paise
        existing.session_duration_minutes = body.session_duration_minutes
        existing.description = body.description
        existing.is_legacy = body.is_legacy
        existing.updated_at = datetime.utcnow()
        package = existing
        action = "fee_package.updated"
    else:
        package = FeePackage(
            code=body.code,
            name=body.name,
            sessions_included=body.sessions_included,
            fee_paise=body.fee_paise,
            session_duration_minutes=body.session_duration_minutes,
            description=body.description,
            is_legacy=body.is_legacy,
            is_active=True,
        )
        db.add(package)
        await db.flush()
        before = None
        action = "fee_package.created"

    await record_audit(
        db,
        action=action,
        entity_type="fee_package",
        entity_id=package.code,
        actor_user_id=current_user.id,
        actor_role=str(current_user.role),
        summary=f"{package.name} ({package.sessions_included} classes, {package.fee_paise} paise)",
        before_data=before,
        after_data={"name": package.name, "fee_paise": package.fee_paise},
    )
    await db.commit()
    return {
        "id": str(package.id),
        "code": package.code,
        "name": package.name,
        "sessions_included": package.sessions_included,
        "fee_paise": package.fee_paise,
        "session_duration_minutes": package.session_duration_minutes,
        "description": package.description,
        "is_legacy": package.is_legacy,
        "is_active": package.is_active,
    }


# ------------------------------------------------------------------
# Invoices
# ------------------------------------------------------------------
@router.post("/invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == body.enrollment_id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    existing = await db.execute(
        select(Invoice).where(
            Invoice.enrollment_id == body.enrollment_id,
            Invoice.billing_month == body.billing_month,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An invoice already exists for this enrollment and month")

    package = None
    if body.charge_type in ("exam", "other"):
        # exam/other charges carry their own explicit amount — package prices
        # are tuition defaults, never universal charges
        if not body.amount_paise:
            raise HTTPException(status_code=400, detail="amount_paise is required for exam/other charges")
        amount_paise = body.amount_paise
    elif body.package_id:
        package_result = await db.execute(select(FeePackage).where(FeePackage.id == body.package_id))
        package = package_result.scalar_one_or_none()
        if not package:
            raise HTTPException(status_code=404, detail="Package not found")
        amount_paise = package.fee_paise
    else:
        amount_paise = body.amount_paise or (int(float(enrollment.fee_amount) * 100) if enrollment.fee_amount else None)
        if not amount_paise:
            raise HTTPException(status_code=400, detail="Provide a package, an explicit amount or an enrollment fee amount")

    invoice_number = await generate_invoice_number(db, body.billing_month)
    due_date = date.fromisoformat(body.due_date) if body.due_date else None

    invoice = Invoice(
        invoice_number=invoice_number,
        enrollment_id=enrollment.id,
        student_id=enrollment.student_id,
        package_id=package.id if package else None,
        billing_month=body.billing_month,
        amount_paise=amount_paise,
        currency="INR",
        status="pending",
        due_date=due_date,
        notes=body.notes,
        charge_type=body.charge_type or "tuition",
        description=body.description,
        created_by=current_user.id,
    )
    db.add(invoice)
    await db.flush()

    # Mirror into the legacy month-wise fee ledger for continuity
    fee_record = FeeRecord(
        enrollment_id=enrollment.id,
        student_id=enrollment.student_id,
        fee_plan=enrollment.fee_plan or (package.code if package else None),
        period=body.billing_month,
        amount_expected=float(amount_paise) / 100.0,
        amount_paid=0,
        payment_status="pending",
        notes=body.notes,
    )
    db.add(fee_record)
    await db.flush()
    invoice.fee_record_id = fee_record.id

    if enrollment.fee_plan is None and package:
        enrollment.fee_plan = package.code
        enrollment.fee_amount = float(package.fee_paise) / 100.0

    await record_audit(
        db,
        action="invoice.created",
        entity_type="invoice",
        entity_id=invoice.invoice_number,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={"amount_paise": amount_paise, "billing_month": body.billing_month},
    )
    await db.flush()
    return _serialize_invoice(invoice)


@router.get("/invoices")
async def list_invoices(
    student_id: Optional[UUID] = None,
    billing_month: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Invoice)

    allowed = await _scoped_invoice_ids(db, current_user)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(Invoice.id.in_(allowed))

    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(Invoice.student_id == student_id)
    if billing_month:
        query = query.where(Invoice.billing_month == billing_month)
    if status_filter:
        query = query.where(Invoice.status == status_filter)

    query = query.order_by(Invoice.billing_month.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return [_serialize_invoice(i) for i in result.scalars().all()]


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Invoice, Student.cma_registration_id, Student.first_name, Student.last_name)
        .join(Student, Student.id == Invoice.student_id)
        .where(Invoice.id == invoice_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice, cma_id, first_name, last_name = row

    allowed = await _scoped_invoice_ids(db, current_user)
    if allowed is not None and invoice.id not in allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    allocations = await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.invoice_id == invoice_id)
    )
    payload = _serialize_invoice(invoice)
    payload["student"] = {
        "cma_registration_id": cma_id,
        "name": f"{first_name} {last_name}".strip(),
    }
    payload["allocations"] = [
        {
            "id": str(a.id),
            "payment_id": str(a.payment_id),
            "amount_paise": a.amount_paise,
            "allocated_at": a.allocated_at.isoformat() if a.allocated_at else None,
            "reason": a.reason,
            "reverses_allocation_id": str(a.reverses_allocation_id) if a.reverses_allocation_id else None,
        }
        for a in allocations.scalars().all()
    ]
    return payload


# ------------------------------------------------------------------
# Ledger
# ------------------------------------------------------------------
@router.get("/ledger")
async def month_wise_ledger(
    student_id: Optional[UUID] = None,
    month_from: Optional[str] = None,
    month_to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Invoice)
    allowed = await _scoped_invoice_ids(db, current_user)
    if allowed is not None:
        if not allowed:
            return {"entries": [], "outstanding_paise": 0}
        query = query.where(Invoice.id.in_(allowed))
    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(Invoice.student_id == student_id)
    if month_from:
        query = query.where(Invoice.billing_month >= month_from)
    if month_to:
        query = query.where(Invoice.billing_month <= month_to)

    result = await db.execute(query.order_by(Invoice.billing_month.desc()))
    invoices = list(result.scalars().all())
    outstanding = sum(max(i.amount_paise - i.amount_paid_paise, 0) for i in invoices)
    return {
        "entries": [_serialize_invoice(i) for i in invoices],
        "outstanding_paise": outstanding,
    }


# ------------------------------------------------------------------
# Payments
# ------------------------------------------------------------------
@router.get("/payments/config")
async def payment_config(current_user: User = Depends(get_current_user)):
    """Public-safe checkout configuration (key id only, never the secret)."""
    return razorpay_service.public_config()


@router.get("/payments")
async def list_payments(
    student_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Payment)
    if status_filter:
        query = query.where(Payment.status == status_filter)

    if current_user.role in (UserRole.STUDENT, UserRole.PARENT):
        student_ids = await get_linked_student_ids(db, current_user)
        if not student_ids:
            return []
        allocations = await db.execute(
            select(PaymentAllocation).where(PaymentAllocation.student_id.in_(student_ids))
        )
        payment_ids = {a.payment_id for a in allocations.scalars().all()}
        # Also include payments recorded directly against their invoices
        invoices = await db.execute(select(Invoice.id).where(Invoice.student_id.in_(student_ids)))
        invoice_ids = {i for i in invoices.scalars().all()}
        direct = await db.execute(select(Payment).where(Payment.invoice_id.in_(invoice_ids) if invoice_ids else False))
        payment_ids |= {p.id for p in direct.scalars().all()}
        # payments the family reported themselves (no invoice link yet)
        own = await db.execute(select(Payment.id).where(Payment.payer_user_id == current_user.id))
        payment_ids |= set(own.scalars().all())
        if not payment_ids:
            return []
        query = query.where(Payment.id.in_(list(payment_ids)))
    elif current_user.role == UserRole.INSTRUCTOR:
        # Instructors do not see billing unless explicitly permitted by admin
        raise HTTPException(status_code=403, detail="Billing is not available for this account")

    if student_id:
        await require_student_access(db, current_user, student_id)

    query = query.order_by(Payment.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    payments = result.scalars().all()
    if current_user.role != UserRole.ADMIN or not payments:
        return [_serialize_payment(p) for p in payments]

    # Admin claim context: resolve student + expected amount for the pending
    # table without guessing — invoice link first, then the payer account.
    inv_ids = {p.invoice_id for p in payments if p.invoice_id}
    invs = {}
    if inv_ids:
        invs = {i.id: i for i in (await db.execute(
            select(Invoice).where(Invoice.id.in_(list(inv_ids))))).scalars().all()}
    payer_ids = {p.payer_user_id for p in payments if p.payer_user_id}
    payer_students = {}
    if payer_ids:
        for st in (await db.execute(
                select(Student).where(Student.user_id.in_(list(payer_ids))))).scalars().all():
            payer_students[st.user_id] = st
    stu_ids = {inv.student_id for inv in invs.values() if inv.student_id} |               {st.id for st in payer_students.values()}
    stu_map = {}
    if stu_ids:
        stu_map = {st.id: st for st in (await db.execute(
            select(Student).where(Student.id.in_(list(stu_ids))))).scalars().all()}

    out = []
    for payment in payments:
        inv = invs.get(payment.invoice_id) if payment.invoice_id else None
        student = stu_map.get(inv.student_id) if inv and inv.student_id else None
        if student is None and payment.payer_user_id:
            student = payer_students.get(payment.payer_user_id)
        expected = inv.amount_paise if inv else None
        fee_label = None
        if inv:
            fee_label = " · ".join(x for x in [
                inv.description or (inv.charge_type or "tuition").replace("_", " ").title(),
                inv.billing_month] if x)
        out.append({
            **_serialize_payment(payment),
            "student_id": str(student.id) if student else None,
            "student_name": student.full_name if student else None,
            "cma_registration_id": student.cma_registration_id if student else None,
            "expected_paise": expected,
            "outstanding_paise": (max(inv.amount_paise - (inv.amount_paid_paise or 0), 0) if inv else None),
            "invoice_number": inv.invoice_number if inv else None,
            "billing_month": inv.billing_month if inv else None,
            "fee_label": fee_label,
            "claim_unlinked": student is None,
        })
    return out


@router.post("/payments/orders", status_code=status.HTTP_201_CREATED)
async def create_payment_order(
    body: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a secure server-side payment for one invoice (re-uses open orders)."""
    result = await db.execute(select(Invoice).where(Invoice.id == body.invoice_id))
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    allowed = await _scoped_invoice_ids(db, current_user)
    if allowed is not None and invoice.id not in allowed:
        raise HTTPException(status_code=403, detail="Access denied")

    if invoice.status == "paid":
        raise HTTPException(status_code=409, detail="This invoice is already fully paid")

    outstanding = invoice.amount_paise - invoice.amount_paid_paise
    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="Nothing outstanding on this invoice")

    # Re-use an existing open order to avoid duplicate charges
    existing_order = await db.execute(
        select(PaymentOrder).where(
            PaymentOrder.invoice_id == invoice.id,
            PaymentOrder.status == "created",
        )
    )
    open_order = existing_order.scalars().first()
    if open_order:
        return {
            "order_id": open_order.order_id,
            "amount_paise": open_order.amount_paise,
            "currency": open_order.currency,
            "key_id": razorpay_service.key_id if razorpay_service.enabled else None,
            "invoice_id": str(invoice.id),
            "reused": True,
        }

    if not razorpay_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Online checkout is not configured on this installation. You can settle dues by cash/UPI at the academy, or use the Razorpay payment buttons on the billing page (share the payment reference with the academy so it can be matched).",
        )

    try:
        order = razorpay_service.create_order(
            amount_paise=outstanding,
            receipt=invoice.invoice_number.replace("/", "-"),
            notes={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "billing_month": invoice.billing_month,
                "student_id": str(invoice.student_id),
            },
        )
    except PaymentGatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    payment_order = PaymentOrder(
        order_id=order["order_id"],
        invoice_id=invoice.id,
        amount_paise=outstanding,
        currency=order.get("currency", "INR"),
        status="created",
        requested_by=current_user.id,
    )
    db.add(payment_order)
    await db.flush()

    await record_audit(
        db,
        action="payment.order_created",
        entity_type="payment_order",
        entity_id=order["order_id"],
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={"invoice_id": str(invoice.id), "amount_paise": outstanding},
    )

    return {
        "order_id": order["order_id"],
        "amount_paise": outstanding,
        "currency": order.get("currency", "INR"),
        "key_id": order.get("key_id"),
        "invoice_id": str(invoice.id),
        "reused": False,
    }


@router.post("/payments/manual", status_code=status.HTTP_201_CREATED)
async def record_manual_payment(
    body: ManualPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Administrative reconciliation for payments received offline (cash/UPI/bank)."""
    total_allocated = sum(a.amount_paise for a in body.allocations)
    if total_allocated > body.amount_paise:
        raise HTTPException(status_code=400, detail="Allocations exceed the payment amount")

    # resolve the actual payer (student's account) — the admin is the recorder
    first_inv = (await db.execute(
        select(Invoice).where(Invoice.id == body.allocations[0].invoice_id))).scalar_one_or_none()
    payer_user_id = current_user.id
    if first_inv:
        stu = (await db.execute(select(Student).where(Student.id == first_inv.student_id))).scalar_one_or_none()
        if stu:
            payer_user_id = stu.user_id

    payment = Payment(
        provider="manual",
        provider_payment_id=body.reference or f"MANUAL-{uuid4().hex[:10].upper()}",
        payer_user_id=payer_user_id,
        payer_name=body.payer_name,
        amount_paise=body.amount_paise,
        currency="INR",
        method=body.method,
        status="verified",
        paid_at=datetime.fromisoformat(body.paid_at) if body.paid_at else datetime.utcnow(),
        verified_at=datetime.utcnow(),
        recorded_by=current_user.id,
        notes=body.notes,
        source="manual",
    )
    db.add(payment)
    await db.flush()
    await _issue_receipt(db, payment, current_user.id)

    for spec in body.allocations:
        inv_result = await db.execute(select(Invoice).where(Invoice.id == spec.invoice_id))
        invoice = inv_result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail=f"Invoice {spec.invoice_id} not found")
        db.add(
            PaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                enrollment_id=invoice.enrollment_id,
                student_id=invoice.student_id,
                amount_paise=spec.amount_paise,
                allocated_by=current_user.id,
            )
        )
        await _apply_allocation(db, invoice, spec.amount_paise)
        await _sync_exam_reimbursement(db, invoice)

    remainder = body.amount_paise - total_allocated
    if remainder > 0:
        if not body.keep_remainder_as_credit:
            raise HTTPException(
                status_code=400,
                detail=f"{remainder} paise of this payment is unallocated. Allocate it, or set "
                       "keep_remainder_as_credit=true to hold it as an advance credit on the account.",
            )
        student_id = first_inv.student_id if first_inv else None
        if not student_id:
            raise HTTPException(status_code=400, detail="Cannot keep a credit without a student")
        await _record_credit(
            db, student_id=student_id, kind="advance", amount_paise=remainder,
            created_by=current_user.id, enrollment_id=first_inv.enrollment_id if first_inv else None,
            payment_id=payment.id, note=body.notes or "Advance credit from over-payment",
        )

    await record_audit(
        db,
        action="payment.manual_recorded",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"{body.method} payment recorded by administration (not an independently verified bank transaction)",
        after_data={
            "amount_paise": body.amount_paise,
            "method": body.method,
            "receipt_number": payment.receipt_number,
            "source": "manual",
            "allocations": [{"invoice": str(a.invoice_id), "amount_paise": a.amount_paise} for a in body.allocations],
            "credit_advance_paise": remainder if remainder > 0 else 0,
        },
    )
    await db.flush()
    return _serialize_payment(payment)


@router.post("/payments/{payment_id}/allocations", status_code=status.HTTP_201_CREATED)
async def allocate_family_payment(
    payment_id: UUID,
    body: AllocatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """
    Explicitly allocate a (possibly combined family) payment across invoices.
    Each student's ledger is updated only for its own allocation.
    """
    payment_result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = payment_result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status not in ("verified",):
        raise HTTPException(status_code=400, detail="Only verified payments can be allocated")

    already = await _allocated_total_for_payment(db, payment.id)
    requested = sum(a.amount_paise for a in body.allocations)
    if already + requested > payment.amount_paise:
        raise HTTPException(
            status_code=400,
            detail=f"Allocation exceeds unallocated amount ({payment.amount_paise - already} paise remaining)",
        )

    created = []
    for spec in body.allocations:
        inv_result = await db.execute(select(Invoice).where(Invoice.id == spec.invoice_id))
        invoice = inv_result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail=f"Invoice {spec.invoice_id} not found")

        existing_to_invoice = (await db.execute(
            select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
                PaymentAllocation.invoice_id == invoice.id))).scalar_one()
        if existing_to_invoice + spec.amount_paise > invoice.amount_paise:
            remaining = max(invoice.amount_paise - existing_to_invoice, 0)
            raise HTTPException(
                status_code=400,
                detail=f"Allocation exceeds the invoice charge ({remaining} paise outstanding on "
                       f"{invoice.invoice_number})",
            )

        allocation = PaymentAllocation(
            payment_id=payment.id,
            invoice_id=invoice.id,
            enrollment_id=invoice.enrollment_id,
            student_id=invoice.student_id,
            amount_paise=spec.amount_paise,
            allocated_by=current_user.id,
            reason=body.reason,
        )
        db.add(allocation)
        await _apply_allocation(db, invoice, spec.amount_paise)
        await _sync_exam_reimbursement(db, invoice)
        created.append({"invoice_id": str(invoice.id), "student_id": str(invoice.student_id), "amount_paise": spec.amount_paise})

    await record_audit(
        db,
        action="payment.allocated",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=body.reason or "Family payment allocation",
        after_data={"allocations": created},
    )
    await db.flush()
    return {"payment_id": str(payment.id), "allocated": created, "already_allocated_paise": already + requested}


@router.post("/allocations/{allocation_id}/reverse")
async def reverse_allocation(
    allocation_id: UUID,
    body: ReverseAllocationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """
    Correct an allocation without destroying history: a reversing entry is
    recorded and the invoice is recomputed from remaining allocations.
    """
    result = await db.execute(select(PaymentAllocation).where(PaymentAllocation.id == allocation_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Allocation not found")
    if original.reverses_allocation_id:
        raise HTTPException(status_code=400, detail="This is already a reversing allocation")

    existing_reverse = await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.reverses_allocation_id == original.id)
    )
    if existing_reverse.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This allocation has already been reversed")

    reversal = PaymentAllocation(
        payment_id=original.payment_id,
        invoice_id=original.invoice_id,
        enrollment_id=original.enrollment_id,
        student_id=original.student_id,
        amount_paise=-original.amount_paise,
        allocated_by=current_user.id,
        reverses_allocation_id=original.id,
        reason=body.reason,
    )
    db.add(reversal)
    await db.flush()
    await _recompute_invoice_from_allocations(db, original.invoice_id)

    await record_audit(
        db,
        action="payment.allocation_reversed",
        entity_type="payment_allocation",
        entity_id=str(original.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=body.reason,
        before_data={"amount_paise": original.amount_paise},
        after_data={"amount_paise": -original.amount_paise},
    )
    await db.flush()
    return {"reversed_allocation_id": str(original.id), "reversal_id": str(reversal.id)}


# ------------------------------------------------------------------
# Razorpay webhook
# ------------------------------------------------------------------
@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Signed webhook receiver.

    - Signature verified against the RAW request body.
    - Duplicate deliveries are recorded once (unique event id) and ignored.
    - Amount/currency/order are validated before any ledger change.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response(status_code=400, content="Invalid payload")

    event_id = payload.get("id")
    event_type = payload.get("event", "")
    if not event_id:
        return Response(status_code=400, content="Missing event id")

    import hashlib
    import uuid as _uuid

    digest = hashlib.sha256(raw_body).hexdigest()
    signature_valid = razorpay_service.verify_webhook_signature(raw_body=raw_body, signature=signature)

    if not signature_valid:
        # Recorded for forensics under a non-colliding id so a forged request
        # can never poison the legitimate provider event id.
        db.add(
            PaymentEvent(
                event_id=f"invalid-{_uuid.uuid4().hex[:24]}",
                event_type=event_type,
                signature_valid=False,
                processing_status="failed",
                error_detail=f"Invalid webhook signature for provider event {event_id}",
                payload_digest=digest,
            )
        )
        await db.flush()
        return Response(status_code=400, content="Invalid signature")

    existing = await db.execute(select(PaymentEvent).where(PaymentEvent.event_id == event_id))
    if existing.scalar_one_or_none():
        # Idempotent replay — accept without side effects
        return {"status": "duplicate_ignored"}

    event = PaymentEvent(
        event_id=event_id,
        event_type=event_type,
        signature_valid=True,
        processing_status="received",
        payload_digest=digest,
    )
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"status": "duplicate_ignored"}

    payment_entity = (
        payload.get("payload", {}).get("payment", {}).get("entity", {})
        if isinstance(payload.get("payload"), dict)
        else {}
    )
    provider_payment_id = payment_entity.get("id")
    order_id = payment_entity.get("order_id")
    amount_paise = payment_entity.get("amount")
    currency = payment_entity.get("currency", "INR")
    method = payment_entity.get("method")

    if not provider_payment_id or not order_id:
        event.processing_status = "ignored"
        event.error_detail = "No payment entity in payload"
        await db.flush()
        return {"status": "ignored"}

    order_result = await db.execute(select(PaymentOrder).where(PaymentOrder.order_id == order_id))
    payment_order = order_result.scalar_one_or_none()
    if not payment_order:
        event.processing_status = "ignored"
        event.error_detail = f"Unknown order {order_id}"
        await db.flush()
        return {"status": "ignored"}

    invoice_result = await db.execute(select(Invoice).where(Invoice.id == payment_order.invoice_id))
    invoice = invoice_result.scalar_one_or_none()

    if event_type == "payment.failed":
        payment_order.status = "failed"
        event.processing_status = "processed"
        event.processed_at = datetime.utcnow()
        await db.flush()
        return {"status": "processed"}

    if event_type == "payment.refunded":
        # refund: mark the payment refunded and reverse its allocations —
        # nothing is silently deleted
        rp = await db.execute(
            select(Payment).where(
                Payment.provider == "razorpay",
                Payment.provider_payment_id == provider_payment_id,
            )
        )
        already = rp.scalar_one_or_none()
        if already:
            already.status = "refunded"
            db.add(already)
            allocs = (await db.execute(
                select(PaymentAllocation).where(PaymentAllocation.payment_id == already.id)
            )).scalars().all()
            refund_amount = int(amount_paise or already.amount_paise)
            remaining_refund = refund_amount
            for a in allocs:
                if a.amount_paise <= 0 or remaining_refund <= 0:
                    continue
                take = min(a.amount_paise, remaining_refund)
                remaining_refund -= take
                db.add(PaymentAllocation(
                    payment_id=already.id,
                    invoice_id=a.invoice_id,
                    enrollment_id=a.enrollment_id,
                    student_id=a.student_id,
                    amount_paise=-take,
                    allocated_by=None,
                    reverses_allocation_id=a.id,
                    reason=f"Refund (webhook {event_id})",
                ))
                await _recompute_invoice_from_allocations(db, a.invoice_id)
            event.payment_id = already.id
        event.processing_status = "processed"
        event.processed_at = datetime.utcnow()
        await db.flush()
        return {"status": "processed"}

    if event_type == "payment.authorized":
        # authorised is NOT captured: record it as pending verification and
        # never mark a charge paid on its own
        dup_pending = await db.execute(
            select(Payment).where(
                Payment.provider == "razorpay",
                Payment.provider_payment_id == provider_payment_id,
            )
        )
        existing_payment = dup_pending.scalar_one_or_none()
        if existing_payment is None:
            pending = Payment(
                provider="razorpay",
                provider_payment_id=provider_payment_id,
                order_id=order_id,
                invoice_id=invoice.id if invoice else None,
                amount_paise=int(amount_paise or 0),
                currency=currency,
                method=method,
                status="pending_verification",
                paid_at=None,
                notes=f"Authorised (not captured) — webhook {event_id}",
                source="online",
            )
            db.add(pending)
            await db.flush()
            event.payment_id = pending.id
        event.processing_status = "processed"
        event.processed_at = datetime.utcnow()
        await db.flush()
        return {"status": "pending_verification"}

    if event_type not in ("payment.captured", "payment.paid"):
        event.processing_status = "ignored"
        event.processed_at = datetime.utcnow()
        await db.flush()
        return {"status": "ignored"}

    # ---- verified captured payment ----
    if invoice is None:
        event.processing_status = "failed"
        event.error_detail = "Invoice missing for order"
        await db.flush()
        return {"status": "failed"}

    if currency != (invoice.currency or "INR"):
        event.processing_status = "failed"
        event.error_detail = f"Currency mismatch: {currency}"
        await db.flush()
        return {"status": "currency_mismatch"}

    if int(amount_paise or 0) < (invoice.amount_paise - invoice.amount_paid_paise):
        event.processing_status = "failed"
        event.error_detail = f"Amount mismatch: {amount_paise} < outstanding"
        await db.flush()
        return {"status": "amount_mismatch"}

    # Idempotency on provider payment reference
    dup = await db.execute(
        select(Payment).where(
            Payment.provider == "razorpay",
            Payment.provider_payment_id == provider_payment_id,
        )
    )
    if dup.scalar_one_or_none():
        event.processing_status = "ignored"
        event.error_detail = "Payment already recorded"
        await db.flush()
        return {"status": "already_recorded"}

    payer_uid = None
    payer_row = (await db.execute(
        select(Student).where(Student.id == invoice.student_id))).scalar_one_or_none()
    if payer_row:
        payer_uid = payer_row.user_id

    created_ts = payment_entity.get("created", payment_entity.get("created_at"))
    # Manual fee confirmation: a captured webhook RECORDS the payment (signed
    # provider data preserved) but the fee is marked paid only after an
    # authorised admin confirms the transaction.
    payment = Payment(
        provider="razorpay",
        provider_payment_id=provider_payment_id,
        order_id=order_id,
        invoice_id=invoice.id,
        payer_user_id=payer_uid,
        amount_paise=int(amount_paise),
        currency=currency,
        method=method,
        status="pending_verification",
        paid_at=datetime.utcfromtimestamp(created_ts) if created_ts else datetime.utcnow(),
        verified_at=None,
        notes=f"Webhook {event_id} captured — awaiting manual confirmation",
        source="online",
    )
    db.add(payment)
    await db.flush()

    event.payment_id = payment.id
    event.processing_status = "processed"
    event.processed_at = datetime.utcnow()
    await db.flush()
    return {"status": "pending_verification", "payment_id": str(payment.id)}


# ==================================================================
# Charge generation — flexible tuition billing
# ==================================================================
@router.post("/generate-charges")
async def generate_charges(
    body: GenerateChargesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Generate monthly fee charges from each enrolment's ACTUAL billing rule.

    - 4/8-class packages produce one monthly charge at the enrolment's own
      fee amount (package prices are defaults, not universal charges).
    - per-class enrolments are charged only for ELIGIBLE COMPLETED classes in
      the month — a scheduled class is never charged merely for existing.
    Repeated runs are idempotent: an existing charge for the month is skipped.
    """
    year, month = (int(x) for x in body.billing_month.split("-"))
    first = date(year, month, 1)
    import calendar
    last = date(year, month, calendar.monthrange(year, month)[1])
    due_date = date(year, month, body.due_day) if body.due_day else None

    q = select(Enrollment).where(Enrollment.status == "active")
    if body.student_ids:
        q = q.where(Enrollment.student_id.in_(body.student_ids))
    enrollments = (await db.execute(q)).scalars().all()

    created, skipped = [], []
    for enrollment in enrollments:
        existing = (await db.execute(
            select(Invoice).where(
                Invoice.enrollment_id == enrollment.id,
                Invoice.billing_month == body.billing_month,
            ))).scalar_one_or_none()
        if existing:
            skipped.append({"enrollment_id": str(enrollment.id), "reason": "already_exists",
                            "invoice": existing.invoice_number})
            continue

        plan = enrollment.fee_plan
        description = None
        if plan == "per_class":
            if not body.include_per_class:
                continue
            completed = (await db.execute(
                select(func.count(ClassSession.id)).where(
                    ClassSession.enrollment_id == enrollment.id,
                    ClassSession.scheduled_date >= first,
                    ClassSession.scheduled_date <= last,
                    ClassSession.status == "completed",
                ))).scalar_one() or 0
            if completed == 0:
                skipped.append({"enrollment_id": str(enrollment.id),
                                "reason": "no_completed_classes"})
                continue
            rate_paise = int(float(enrollment.fee_amount or 0) * 100)
            if not rate_paise:
                skipped.append({"enrollment_id": str(enrollment.id),
                                "reason": "no_per_class_rate"})
                continue
            amount_paise = rate_paise * completed
            description = f"Per-class tuition {body.billing_month}: {completed} completed class(es) × {rate_paise} paise"
        else:
            amount_paise = int(float(enrollment.fee_amount) * 100) if enrollment.fee_amount else None
            if not amount_paise:
                pkg = (await db.execute(
                    select(FeePackage).where(FeePackage.code == plan, FeePackage.is_active.is_(True))
                )).scalar_one_or_none()
                amount_paise = pkg.fee_paise if pkg else None
            if not amount_paise:
                skipped.append({"enrollment_id": str(enrollment.id), "reason": "no_fee_amount"})
                continue
            description = f"Monthly tuition {body.billing_month} ({plan})"

        invoice = Invoice(
            invoice_number=await generate_invoice_number(db, body.billing_month),
            enrollment_id=enrollment.id,
            student_id=enrollment.student_id,
            billing_month=body.billing_month,
            amount_paise=amount_paise,
            currency="INR",
            status="pending",
            due_date=due_date,
            charge_type="tuition",
            description=description,
            created_by=current_user.id,
        )
        db.add(invoice)
        await db.flush()
        fee_record = FeeRecord(
            enrollment_id=enrollment.id,
            student_id=enrollment.student_id,
            fee_plan=plan,
            period=body.billing_month,
            amount_expected=float(amount_paise) / 100.0,
            amount_paid=0,
            payment_status="pending",
            notes=description,
        )
        db.add(fee_record)
        await db.flush()
        invoice.fee_record_id = fee_record.id
        created.append({"enrollment_id": str(enrollment.id),
                        "invoice": invoice.invoice_number,
                        "amount_paise": amount_paise})

    await record_audit(
        db,
        action="billing.charges_generated",
        entity_type="billing_month",
        entity_id=body.billing_month,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Generated {len(created)} charge(s) for {body.billing_month} ({len(skipped)} skipped)",
        after_data={"created": created, "skipped": skipped},
    )
    await db.flush()
    return {"billing_month": body.billing_month, "created": created, "skipped": skipped}


# ==================================================================
# Advance credits
# ==================================================================
@router.get("/credits")
async def list_credits(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_student_access(db, current_user, student_id)
    rows = (await db.execute(
        select(CreditLedgerEntry).where(CreditLedgerEntry.student_id == student_id)
        .order_by(CreditLedgerEntry.created_at.desc())
    )).scalars().all()
    return {
        "student_id": str(student_id),
        "balance_paise": await _credit_balance(db, student_id),
        "entries": [
            {
                "id": str(r.id),
                "kind": r.kind,
                "amount_paise": r.amount_paise,
                "payment_id": str(r.payment_id) if r.payment_id else None,
                "invoice_id": str(r.invoice_id) if r.invoice_id else None,
                "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/credits/advance", status_code=status.HTTP_201_CREATED)
async def record_advance_credit(
    body: CreditAdvanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Record a payment kept as an advance credit on the family account.

    The payment is real (method/reference recorded) but unallocated — it is
    applied to future charges later through /credits/apply."""
    student = (await db.execute(select(Student).where(Student.id == body.student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    payment = Payment(
        provider="manual",
        provider_payment_id=body.reference or f"ADVANCE-{uuid4().hex[:10].upper()}",
        payer_user_id=student.user_id,
        payer_name=body.payer_name,
        amount_paise=body.amount_paise,
        currency="INR",
        method=body.method,
        status="verified",
        paid_at=datetime.fromisoformat(body.paid_at) if body.paid_at else datetime.utcnow(),
        verified_at=datetime.utcnow(),
        recorded_by=current_user.id,
        notes=body.notes or "Advance credit",
        source="manual",
    )
    db.add(payment)
    await db.flush()
    await _issue_receipt(db, payment, current_user.id)
    entry = await _record_credit(
        db, student_id=body.student_id, kind="advance", amount_paise=body.amount_paise,
        created_by=current_user.id, enrollment_id=body.enrollment_id,
        payment_id=payment.id, note=body.notes or "Advance payment held on account",
    )
    await record_audit(
        db,
        action="credit.advance_recorded",
        entity_type="student",
        entity_id=str(body.student_id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Advance credit of {body.amount_paise} paise recorded",
        after_data={"payment_id": str(payment.id), "amount_paise": body.amount_paise},
    )
    await db.flush()
    return {"payment_id": str(payment.id), "credit_entry_id": str(entry.id),
            "balance_paise": await _credit_balance(db, body.student_id),
            "receipt_number": payment.receipt_number}


@router.post("/credits/apply")
async def apply_credit(
    body: CreditApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Apply advance credit to a charge: allocates the advance payment and
    records the matching credit-ledger application."""
    balance = await _credit_balance(db, body.student_id)
    if body.amount_paise > balance:
        raise HTTPException(status_code=400, detail=f"Credit balance is {balance} paise")

    invoice = (await db.execute(select(Invoice).where(Invoice.id == body.invoice_id))).scalar_one_or_none()
    if not invoice or invoice.student_id != body.student_id:
        raise HTTPException(status_code=404, detail="Invoice not found for that student")
    if invoice.status == "void":
        raise HTTPException(status_code=400, detail="Cannot apply credit to a void invoice")

    existing_to_invoice = (await db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
            PaymentAllocation.invoice_id == invoice.id))).scalar_one()
    remaining_on_charge = max(invoice.amount_paise - existing_to_invoice, 0)
    if body.amount_paise > remaining_on_charge:
        raise HTTPException(status_code=400,
                            detail=f"Only {remaining_on_charge} paise outstanding on {invoice.invoice_number}")

    # draw from the student's advance payments (oldest first)
    advance_payments = (await db.execute(
        select(Payment).join(CreditLedgerEntry, CreditLedgerEntry.payment_id == Payment.id)
        .where(CreditLedgerEntry.student_id == body.student_id,
               CreditLedgerEntry.kind == "advance")
        .order_by(Payment.paid_at.asc())
    )).scalars().all()
    need = body.amount_paise
    applied_rows = []
    first_payment_id = None
    for ap in advance_payments:
        if need <= 0:
            break
        free = ap.amount_paise - await _allocated_total_for_payment(db, ap.id)
        take = min(free, need)
        if take <= 0:
            continue
        db.add(PaymentAllocation(
            payment_id=ap.id,
            invoice_id=invoice.id,
            enrollment_id=invoice.enrollment_id,
            student_id=invoice.student_id,
            amount_paise=take,
            allocated_by=current_user.id,
            reason=body.note or "Advance credit applied",
        ))
        await _apply_allocation(db, invoice, take)
        applied_rows.append({"payment_id": str(ap.id), "amount_paise": take})
        if not first_payment_id:
            first_payment_id = ap.id
        need -= take
    if need > 0:
        raise HTTPException(status_code=400, detail="Advance payments have no unallocated remainder left")

    await _record_credit(
        db, student_id=body.student_id, kind="applied", amount_paise=-body.amount_paise,
        created_by=current_user.id, invoice_id=invoice.id,
        payment_id=first_payment_id,
        note=body.note or f"Applied to {invoice.invoice_number}",
    )
    await record_audit(
        db,
        action="credit.applied",
        entity_type="invoice",
        entity_id=invoice.invoice_number,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Applied {body.amount_paise} paise credit",
        after_data={"applied": applied_rows},
    )
    await db.flush()
    return {"applied_paise": body.amount_paise,
            "balance_paise": await _credit_balance(db, body.student_id),
            "invoice": _serialize_invoice(invoice)}


# ==================================================================
# Invoice void (auditable correction)
# ==================================================================
@router.post("/invoices/{invoice_id}/void")
async def void_invoice(
    invoice_id: UUID,
    body: VoidInvoiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    invoice = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    allocations = (await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.invoice_id == invoice.id))).scalars().all()
    if any(a.amount_paise > 0 for a in allocations):
        raise HTTPException(
            status_code=409,
            detail="This invoice has payments — reverse the allocations first, then void",
        )
    before = {"status": invoice.status, "amount_paise": invoice.amount_paise}
    invoice.status = "void"
    invoice.notes = ((invoice.notes or "") + f" [VOIDED: {body.reason}]").strip()
    db.add(invoice)
    await record_audit(
        db,
        action="invoice.voided",
        entity_type="invoice",
        entity_id=invoice.invoice_number,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Voided: {body.reason}",
        before_data=before,
        after_data={"status": "void"},
    )
    await db.flush()
    return _serialize_invoice(invoice)


# ==================================================================
# Exam-fee accounting (separate from tuition)
# ==================================================================
def _refresh_exam_fee_status(fee: ExamFee, invoice: Optional[Invoice]) -> None:
    academy = fee.academy_paid_paise or 0
    reimbursed = fee.reimbursed_paise or 0
    invoice_paid = bool(invoice and invoice.status == "paid")
    if academy > 0 and reimbursed >= academy:
        fee.status = "settled" if (invoice_paid or not (fee.fee_charged_paise or 0)) else "reimbursed"
    elif academy > 0:
        fee.status = "academy_paid"
    elif invoice_paid:
        fee.status = "family_paid_first"
    else:
        fee.status = "open"


def _serialize_exam_fee(fee: ExamFee) -> dict:
    return {
        "id": str(fee.id),
        "student_id": str(fee.student_id),
        "enrollment_id": str(fee.enrollment_id) if fee.enrollment_id else None,
        "exam_id": str(fee.exam_id) if fee.exam_id else None,
        "invoice_id": str(fee.invoice_id) if fee.invoice_id else None,
        "board": fee.board,
        "instrument": fee.instrument,
        "grade_level": fee.grade_level,
        "exam_session": fee.exam_session,
        "fee_charged_paise": fee.fee_charged_paise,
        "academy_paid_paise": fee.academy_paid_paise,
        "reimbursed_paise": fee.reimbursed_paise,
        "reimbursement_balance_paise": max(fee.academy_paid_paise - fee.reimbursed_paise, 0),
        "reimbursement_method": fee.reimbursement_method,
        "reimbursement_date": fee.reimbursement_date.isoformat() if fee.reimbursement_date else None,
        "provider_reference": fee.provider_reference,
        "status": fee.status,
        "notes": fee.notes,
        "attachment": (
            {"filename": fee.attachment_filename, "stored_name": fee.attachment_stored_name,
             "content_type": fee.attachment_content_type}
            if fee.attachment_stored_name else None
        ),
        "created_at": fee.created_at.isoformat() if fee.created_at else None,
    }


async def _sync_exam_reimbursement(db: AsyncSession, invoice: Invoice) -> None:
    """Money allocated to an exam invoice counts as family reimbursement when
    the academy already paid the provider."""
    if (invoice.charge_type or "tuition") != "exam":
        return
    fee = (await db.execute(
        select(ExamFee).where(ExamFee.invoice_id == invoice.id))).scalar_one_or_none()
    if not fee:
        return
    total = (await db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
            PaymentAllocation.invoice_id == invoice.id))).scalar_one() or 0
    if fee.academy_paid_paise > 0:
        fee.reimbursed_paise = min(total, fee.academy_paid_paise)
        if fee.academy_paid_paise > 0 and not fee.reimbursement_date and total > 0:
            fee.reimbursement_date = date.today()
            fee.reimbursement_method = fee.reimbursement_method or "allocated payment"
    _refresh_exam_fee_status(fee, invoice)
    db.add(fee)


@router.get("/exam-fees")
async def list_exam_fees(
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(ExamFee).order_by(ExamFee.created_at.desc())
    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(ExamFee.student_id == student_id)
    else:
        if current_user.role == UserRole.INSTRUCTOR:
            raise HTTPException(status_code=403, detail="Financial records are not available to teaching staff")
        if current_user.role != UserRole.ADMIN:
            linked = await get_linked_student_ids(db, current_user)
            if not linked:
                return []
            query = query.where(ExamFee.student_id.in_(linked))
    return [_serialize_exam_fee(f) for f in (await db.execute(query)).scalars().all()]


@router.post("/exam-fees", status_code=status.HTTP_201_CREATED)
async def create_exam_fee(
    body: ExamFeeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Record an exam entry: the family charge (an exam invoice) and, where
    applicable, what the academy paid the provider. Academy payments to a
    board are a cost — they are never treated as money received."""
    student = (await db.execute(select(Student).where(Student.id == body.student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # exam charges attach to the student's (matching) enrolment — the invoice
    # schema requires one
    enrollment_id = body.enrollment_id
    if not enrollment_id:
        q = select(Enrollment).where(Enrollment.student_id == body.student_id,
                                     Enrollment.status == "active")
        if body.instrument:
            q = q.where(Enrollment.programme_name.ilike(f"%{body.instrument}%"))
        enr = (await db.execute(q.order_by(Enrollment.created_at.asc()))).scalars().first()
        if not enr:
            raise HTTPException(status_code=400, detail="No active enrolment found for this student — pass enrollment_id")
        enrollment_id = enr.id

    invoice = None
    if body.create_invoice and body.fee_charged_paise > 0:
        month = body.billing_month or date.today().strftime("%Y-%m")
        invoice = Invoice(
            invoice_number=await generate_invoice_number(db, month),
            enrollment_id=enrollment_id,
            student_id=body.student_id,
            billing_month=month,
            amount_paise=body.fee_charged_paise,
            currency="INR",
            status="pending",
            due_date=date.fromisoformat(body.due_date) if body.due_date else None,
            charge_type="exam",
            description=f"Exam fee: {body.board or 'exam'} {body.grade_level or ''} {body.exam_session or ''}".strip(),
            created_by=current_user.id,
        )
        db.add(invoice)
        await db.flush()

    fee = ExamFee(
        student_id=body.student_id,
        enrollment_id=enrollment_id,
        exam_id=body.exam_id,
        invoice_id=invoice.id if invoice else None,
        board=body.board,
        instrument=body.instrument,
        grade_level=body.grade_level,
        exam_session=body.exam_session,
        fee_charged_paise=body.fee_charged_paise,
        academy_paid_paise=body.academy_paid_paise,
        provider_reference=body.provider_reference,
        notes=body.notes,
        created_by=current_user.id,
    )
    _refresh_exam_fee_status(fee, invoice)
    db.add(fee)
    await db.flush()
    await record_audit(
        db,
        action="exam_fee.created",
        entity_type="exam_fee",
        entity_id=str(fee.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Exam fee recorded for {student.full_name}: charged {body.fee_charged_paise} paise",
        after_data={"invoice": invoice.invoice_number if invoice else None,
                    "academy_paid_paise": body.academy_paid_paise},
    )
    await db.flush()
    out = _serialize_exam_fee(fee)
    out["invoice"] = _serialize_invoice(invoice) if invoice else None
    return out


@router.post("/exam-fees/{exam_fee_id}/academy-payment")
async def exam_fee_academy_payment(
    exam_fee_id: UUID,
    body: ExamFeeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Record what the academy paid the exam provider (a cost, not income)."""
    fee = (await db.execute(select(ExamFee).where(ExamFee.id == exam_fee_id))).scalar_one_or_none()
    if not fee:
        raise HTTPException(status_code=404, detail="Exam fee not found")
    delta = body.academy_paid_delta_paise or 0
    if delta < 0 and fee.academy_paid_paise + delta < fee.reimbursed_paise:
        raise HTTPException(status_code=400, detail="Cannot reduce the academy payment below the reimbursed amount")
    fee.academy_paid_paise += delta
    if body.provider_reference:
        fee.provider_reference = body.provider_reference
    if body.notes:
        fee.notes = ((fee.notes or "") + f" | {body.notes}").strip(" |")
    invoice = None
    if fee.invoice_id:
        invoice = (await db.execute(select(Invoice).where(Invoice.id == fee.invoice_id))).scalar_one_or_none()
    _refresh_exam_fee_status(fee, invoice)
    db.add(fee)
    await record_audit(
        db,
        action="exam_fee.academy_payment",
        entity_type="exam_fee",
        entity_id=str(fee.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Academy paid provider {delta} paise (cost — not money received)",
        after_data={"academy_paid_paise": fee.academy_paid_paise,
                    "provider_reference": fee.provider_reference},
    )
    await db.flush()
    return _serialize_exam_fee(fee)


@router.post("/exam-fees/{exam_fee_id}/reimburse")
async def exam_fee_reimburse(
    exam_fee_id: UUID,
    body: ExamFeeReimburse,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Record the family reimbursing the academy for an exam cost.

    Creates a manual payment (with receipt) and allocates it to the exam
    invoice when one exists — the money therefore appears in the student's
    statement as an exam-charge payment, never as tuition."""
    fee = (await db.execute(select(ExamFee).where(ExamFee.id == exam_fee_id))).scalar_one_or_none()
    if not fee:
        raise HTTPException(status_code=404, detail="Exam fee not found")
    remaining = max(fee.academy_paid_paise - fee.reimbursed_paise, 0)
    if body.amount_paise > remaining:
        raise HTTPException(status_code=400, detail=f"Only {remaining} paise of reimbursement outstanding")

    student = (await db.execute(select(Student).where(Student.id == fee.student_id))).scalar_one_or_none()
    payment = Payment(
        provider="manual",
        provider_payment_id=body.reference or f"EXAMR-{uuid4().hex[:10].upper()}",
        payer_user_id=student.user_id if student else None,
        amount_paise=body.amount_paise,
        currency="INR",
        method=body.method,
        status="verified",
        paid_at=datetime.fromisoformat(body.date) if body.date else datetime.utcnow(),
        verified_at=datetime.utcnow(),
        recorded_by=current_user.id,
        notes=body.notes or f"Exam reimbursement ({fee.board or 'exam'} {fee.grade_level or ''})",
        source="manual",
    )
    db.add(payment)
    await db.flush()
    await _issue_receipt(db, payment, current_user.id)

    invoice = None
    if fee.invoice_id:
        invoice = (await db.execute(select(Invoice).where(Invoice.id == fee.invoice_id))).scalar_one_or_none()
    if invoice and invoice.status != "void":
        existing_to_invoice = (await db.execute(
            select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
                PaymentAllocation.invoice_id == invoice.id))).scalar_one()
        take = min(body.amount_paise, max(invoice.amount_paise - existing_to_invoice, 0))
        if take > 0:
            db.add(PaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                enrollment_id=invoice.enrollment_id,
                student_id=invoice.student_id,
                amount_paise=take,
                allocated_by=current_user.id,
                reason=body.notes or "Exam reimbursement",
            ))
            await _apply_allocation(db, invoice, take)

    fee.reimbursed_paise += body.amount_paise
    fee.reimbursement_method = body.method
    fee.reimbursement_date = date.fromisoformat(body.date) if body.date else date.today()
    _refresh_exam_fee_status(fee, invoice)
    db.add(fee)
    await record_audit(
        db,
        action="exam_fee.reimbursed",
        entity_type="exam_fee",
        entity_id=str(fee.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Reimbursed {body.amount_paise} paise via {body.method}",
        after_data={"reimbursed_paise": fee.reimbursed_paise,
                    "balance_paise": max(fee.academy_paid_paise - fee.reimbursed_paise, 0),
                    "payment_id": str(payment.id)},
    )
    await db.flush()
    out = _serialize_exam_fee(fee)
    out["payment_receipt_number"] = payment.receipt_number
    return out


# ==================================================================
# Receipts
# ==================================================================
@router.get("/payments/{payment_id}/receipt")
async def payment_receipt(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if current_user.role not in (UserRole.ADMIN,):
        allowed = await get_linked_student_ids(db, current_user)
        owns = payment.payer_user_id == current_user.id
        if not owns:
            related = (await db.execute(
                select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id)
            )).scalars().all()
            if not any(a.student_id in allowed for a in related):
                raise HTTPException(status_code=403, detail="You can only view your own receipts")

    if payment.status not in ("verified",):
        raise HTTPException(status_code=400, detail="Receipts are issued for verified payments only")
    receipt_number = await _issue_receipt(db, payment, current_user.id)
    await db.flush()

    allocations = (await db.execute(
        select(PaymentAllocation, Invoice)
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .where(PaymentAllocation.payment_id == payment.id)
    )).all()
    lines = "".join(
        f"<tr><td>{inv.invoice_number}</td><td>{inv.billing_month}</td>"
        f"<td>{inv.charge_type or 'tuition'}</td><td>{alloc.amount_paise / 100:.2f}</td></tr>"
        for alloc, inv in allocations
    ) or "<tr><td colspan='4'>Unallocated / advance credit</td></tr>"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Receipt {receipt_number}</title>
<style>body{{font-family:Georgia,serif;max-width:640px;margin:40px auto;color:#1c1a15}}
h1{{font-size:20px}}table{{width:100%;border-collapse:collapse;margin-top:14px}}
td,th{{border:1px solid #ccc;padding:8px;text-align:left;font-size:13px}}
.muted{{color:#6b6459;font-size:12px}}</style></head><body>
<h1>ChankArts Music Academy — Receipt</h1>
<p class="muted">Receipt no. <strong>{receipt_number}</strong> · Issued {datetime.utcnow().strftime('%d %b %Y')}</p>
<p><strong>Amount received:</strong> ₹{payment.amount_paise / 100:.2f} ({payment.currency})<br>
<strong>Method:</strong> {payment.method or payment.provider}
{' · admin-recorded (not an independently verified bank transaction)' if (payment.source or 'manual') == 'manual' else ''}<br>
<strong>Reference:</strong> {payment.provider_payment_id or '—'}<br>
<strong>Received on:</strong> {(payment.paid_at or datetime.utcnow()).strftime('%d %b %Y %H:%M')}</p>
<table><tr><th>Invoice</th><th>Period</th><th>Type</th><th>Allocated (₹)</th></tr>{lines}</table>
<p class="muted">This receipt was generated by the academy ledger. Payments recorded by staff are
marked as admin-recorded.</p></body></html>"""
    return HTMLResponse(html)


# ==================================================================
# Financial statement (student / family) + exports
# ==================================================================
@router.get("/statement")
async def financial_statement(
    student_id: Optional[UUID] = None,
    family: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Combined financial statement for one student, or for a parent's
    linked children (family=1). Instructors are never given financial data."""
    if current_user.role == UserRole.INSTRUCTOR:
        raise HTTPException(status_code=403, detail="Financial records are not available to teaching staff")

    if family and current_user.role == UserRole.PARENT:
        student_ids = await get_linked_student_ids(db, current_user)
    elif student_id:
        await require_student_access(db, current_user, student_id)
        student_ids = [student_id]
    else:
        student_ids = await get_linked_student_ids(db, current_user)
        if current_user.role == UserRole.ADMIN:
            raise HTTPException(status_code=400, detail="Provide student_id")
    if not student_ids:
        return {"students": [], "totals": {"charged_paise": 0, "paid_paise": 0,
                                           "outstanding_paise": 0, "credit_balance_paise": 0}}

    students_out = []
    totals = {"charged_paise": 0, "paid_paise": 0, "outstanding_paise": 0, "credit_balance_paise": 0}
    for sid in student_ids:
        st = (await db.execute(select(Student).where(Student.id == sid))).scalar_one_or_none()
        invoices = (await db.execute(
            select(Invoice).where(Invoice.student_id == sid, Invoice.status != "void")
            .order_by(Invoice.billing_month.desc()))).scalars().all()
        allocs = (await db.execute(
            select(PaymentAllocation, Payment)
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(PaymentAllocation.student_id == sid))).all()
        # unallocated payments made/reported by the family (e.g. pending
        # verification) must appear on the statement too
        if st:
            extra = (await db.execute(
                select(Payment).where(
                    Payment.payer_user_id == st.user_id,
                    Payment.invoice_id.is_(None),
                ))).scalars().all()
        else:
            extra = []
        credits = (await db.execute(
            select(CreditLedgerEntry).where(CreditLedgerEntry.student_id == sid)
            .order_by(CreditLedgerEntry.created_at.asc()))).scalars().all()
        exams = (await db.execute(
            select(ExamFee).where(ExamFee.student_id == sid).order_by(ExamFee.created_at.desc()))).scalars().all()

        payments_by_id = {}
        for alloc, payment in allocs:
            payments_by_id.setdefault(str(payment.id), {"payment": payment, "allocated_paise": 0})
            payments_by_id[str(payment.id)]["allocated_paise"] += alloc.amount_paise
        for payment in extra:
            payments_by_id.setdefault(str(payment.id), {"payment": payment, "allocated_paise": 0})

        charged = sum(i.amount_paise for i in invoices)
        paid = sum(i.amount_paid_paise or 0 for i in invoices)
        outstanding = sum(max(i.amount_paise - (i.amount_paid_paise or 0), 0) for i in invoices)
        credit_balance = await _credit_balance(db, sid)
        totals["charged_paise"] += charged
        totals["paid_paise"] += paid
        totals["outstanding_paise"] += outstanding
        totals["credit_balance_paise"] += credit_balance

        students_out.append({
            "student_id": str(sid),
            "student_name": st.full_name if st else None,
            "cma_registration_id": st.cma_registration_id if st else None,
            "charges": [
                {**_serialize_invoice(i),
                 "is_overdue": bool(i.due_date and i.status in ("pending", "partially_paid")
                                    and i.due_date < date.today())}
                for i in invoices
            ],
            "payments": [
                {
                    **_serialize_payment(v["payment"]),
                    "allocated_paise": v["allocated_paise"],
                }
                for v in payments_by_id.values()
            ],
            "credits": [
                {"kind": c.kind, "amount_paise": c.amount_paise, "note": c.note,
                 "created_at": c.created_at.isoformat() if c.created_at else None}
                for c in credits
            ],
            "exam_fees": [_serialize_exam_fee(e) for e in exams],
            "totals": {"charged_paise": charged, "paid_paise": paid,
                       "outstanding_paise": outstanding, "credit_balance_paise": credit_balance},
        })
    return {"students": students_out, "totals": totals}


@router.get("/statement/export")
async def export_statement(
    student_id: Optional[UUID] = None,
    family: bool = False,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Branded CSV fee statement (same scoping as /statement).

    Student-facing document: academy header, plain-language column names and
    amounts converted from paise to ₹.  Stored values are never modified.
    """
    data = await financial_statement(student_id=student_id, family=family, db=db, current_user=current_user)
    import csv
    import io as _io

    def inr(paise) -> str:
        """Integer paise → ₹1,234.56 (blank for None — never invent values)."""
        if paise is None or paise == "":
            return ""
        return f"₹{(int(paise) / 100):,.2f}"

    def status_label(s) -> str:
        return (s or "").replace("_", " ").title()

    buf = _io.StringIO()
    writer = csv.writer(buf)

    names = [st["student_name"] or "" for st in data["students"]]
    months = sorted({c["billing_month"] for st in data["students"] for c in st["charges"] if c.get("billing_month")})
    if month:
        period = month
    elif len(months) == 1:
        period = months[0]
    else:
        period = "All periods"

    writer.writerow(["CHANKARTS MUSIC ACADEMY"])
    writer.writerow(["Student Fee Statement"])
    writer.writerow(["Student", "; ".join(n for n in names if n) or "-"])
    writer.writerow(["Generated", date.today().isoformat()])
    writer.writerow(["Statement Period", period])
    writer.writerow(["Currency", "INR (₹)"])
    writer.writerow([])

    writer.writerow(["Student", "Transaction Type", "Reference", "Period / Date",
                     "Description", "Amount Charged (₹)", "Amount Paid (₹)",
                     "Outstanding (₹)", "Status"])
    for st in data["students"]:
        name = st["student_name"] or ""
        for c in st["charges"]:
            if month and c.get("billing_month") and c["billing_month"] != month:
                continue
            writer.writerow([name, "Fee Charge", c["invoice_number"], c.get("billing_month") or "",
                             (c.get("description") or str(c.get("charge_type") or "").replace("_", " ").title()),
                             inr(c["amount_paise"]), inr(c["amount_paid_paise"] or 0),
                             inr(c["outstanding_paise"]), status_label(c["status"])])
        for p in st["payments"]:
            writer.writerow([name, "Payment", p.get("provider_payment_id") or "",
                             (p.get("paid_at") or "")[:10],
                             " ".join(x for x in [str(p.get("method") or p.get("provider") or "").title(),
                                                  ("(reported)" if p.get("status") == "reported" else "")] if x),
                             "", inr(p["amount_paise"]), "", status_label(p["status"])])
        for e in st["exam_fees"]:
            writer.writerow([name, "Exam Fee", e.get("provider_reference") or str(e.get("id", ""))[:8],
                             e.get("exam_session") or "",
                             " ".join(x for x in [e.get("board") or "", e.get("grade_level") or ""] if x).strip(),
                             inr(e.get("fee_charged_paise")), inr(e.get("reimbursed_paise")),
                             inr(e.get("reimbursement_balance_paise")), status_label(e.get("status"))])
        credit = st["totals"].get("credit_balance_paise") or 0
        writer.writerow([name, "Available Credit Balance", "", "",
                         "Credit available toward future charges" if credit else "",
                         "", "", inr(credit), "Credit" if credit else ""])

    # summary row (charge-based totals; credit shown separately above)
    t = data["totals"]
    writer.writerow([])
    writer.writerow(["", "TOTAL", "", "", "", inr(t["charged_paise"]), inr(t["paid_paise"]),
                     inr(t["outstanding_paise"]), ""])
    writer.writerow(["", "Available Credit Balance", "", "", "", "", "", inr(t["credit_balance_paise"]), ""])

    # UTF-8 BOM so ₹ renders correctly in Excel
    csv_text = "\ufeff" + buf.getvalue()
    return Response(csv_text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=chankarts-fee-statement.csv"})


# ==================================================================
# Collections report (admin)
# ==================================================================
@router.get("/reports/collections")
async def collections_report(
    billing_month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Month collection report: charges raised, money in by method, exam
    reimbursements kept separate from tuition, credits and outstanding."""
    invoices = (await db.execute(
        select(Invoice).where(Invoice.billing_month == billing_month))).scalars().all()
    year, month = (int(x) for x in billing_month.split("-"))
    import calendar
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])

    payments = (await db.execute(
        select(Payment).where(
            Payment.status == "verified",
            Payment.paid_at >= datetime(year, month, 1),
            Payment.paid_at < datetime.combine(last, datetime.max.time()),
        ))).scalars().all()

    by_method = {}
    for p in payments:
        by_method.setdefault(p.method or p.provider, {"count": 0, "amount_paise": 0})
        by_method[p.method or p.provider]["count"] += 1
        by_method[p.method or p.provider]["amount_paise"] += p.amount_paise

    by_charge_type = {}
    for i in invoices:
        t = i.charge_type or "tuition"
        by_charge_type.setdefault(t, {"charged_paise": 0, "paid_paise": 0, "outstanding_paise": 0, "count": 0})
        by_charge_type[t]["charged_paise"] += i.amount_paise
        by_charge_type[t]["paid_paise"] += i.amount_paid_paise or 0
        by_charge_type[t]["outstanding_paise"] += max(i.amount_paise - (i.amount_paid_paise or 0), 0)
        by_charge_type[t]["count"] += 1

    exam_fees = (await db.execute(
        select(ExamFee).where(ExamFee.updated_at >= first))).scalars().all()
    credits = (await db.execute(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.created_at >= first,
            CreditLedgerEntry.created_at < datetime.combine(last, datetime.max.time()),
        ))).scalars().all()

    return {
        "billing_month": billing_month,
        "charges_by_type": by_charge_type,
        "collections_by_method": by_method,
        "totals": {
            "charged_paise": sum(i.amount_paise for i in invoices),
            "collected_paise": sum(p.amount_paise for p in payments),
            "outstanding_paise": sum(max(i.amount_paise - (i.amount_paid_paise or 0), 0) for i in invoices),
            "exam_academy_paid_paise": sum(f.academy_paid_paise for f in exam_fees),
            "exam_reimbursed_paise": sum(f.reimbursed_paise for f in exam_fees),
            "credit_added_paise": sum(c.amount_paise for c in credits if c.amount_paise > 0),
            "credit_used_paise": sum(-c.amount_paise for c in credits if c.amount_paise < 0),
        },
    }


# ==================================================================
# Checkout verification (server-side; never trust the browser alone)
# ==================================================================
@router.post("/payments/verify")
async def verify_checkout_payment(
    body: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify a Razorpay Checkout response server-side.

    The HMAC signature is checked against the server secret — a client-supplied
    success message is never trusted on its own. When Razorpay API credentials
    are configured, the payment is additionally confirmed with Razorpay
    directly before it is marked verified."""
    signature_ok = razorpay_service.verify_payment_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    )
    if not signature_ok:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    order_result = await db.execute(
        select(PaymentOrder).where(PaymentOrder.order_id == body.razorpay_order_id))
    payment_order = order_result.scalar_one_or_none()
    if not payment_order:
        raise HTTPException(status_code=404, detail="Unknown payment order")

    # defence in depth: confirm the payment with Razorpay when credentials exist
    if razorpay_service.enabled:
        try:
            remote = await razorpay_service.fetch_payment(body.razorpay_payment_id)
            if remote and remote.get("status") not in ("captured", "paid", "authorized"):
                raise HTTPException(status_code=400, detail=f"Payment status is {remote.get('status')}")
        except PaymentGatewayError:
            raise HTTPException(status_code=502, detail="Could not confirm the payment with Razorpay")

    dup = await db.execute(
        select(Payment).where(
            Payment.provider == "razorpay",
            Payment.provider_payment_id == body.razorpay_payment_id,
        ))
    existing = dup.scalar_one_or_none()
    if existing:
        return {"status": "already_recorded", "payment": _serialize_payment(existing)}

    invoice_result = await db.execute(select(Invoice).where(Invoice.id == payment_order.invoice_id))
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice missing for order")

    payer_uid = None
    payer_row = (await db.execute(select(Student).where(Student.id == invoice.student_id))).scalar_one_or_none()
    if payer_row:
        payer_uid = payer_row.user_id

    # Manual fee confirmation: the payment is RECORDED here (signature checked,
    # provider ids preserved) but stays "pending_verification" — the fee status
    # changes only when an authorised admin confirms the transaction.
    payment = Payment(
        provider="razorpay",
        provider_payment_id=body.razorpay_payment_id,
        order_id=body.razorpay_order_id,
        invoice_id=invoice.id,
        payer_user_id=payer_uid,
        amount_paise=payment_order.amount_paise,
        currency=payment_order.currency or "INR",
        method="online",
        status="pending_verification",
        paid_at=datetime.utcnow(),
        verified_at=None,
        notes="Checkout signature verified — awaiting manual confirmation by the academy",
        source="online",
    )
    db.add(payment)
    await db.flush()
    await record_audit(
        db,
        action="payment.reported",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary="Online payment reported (checkout signature verified) — awaiting manual confirmation",
        after_data={"provider_payment_id": body.razorpay_payment_id,
                    "amount_paise": payment.amount_paise, "invoice": invoice.invoice_number},
    )
    await db.flush()
    return {"status": "pending_verification", "payment": _serialize_payment(payment)}


# ==================================================================
# Manual fee confirmation (student-reported & gateway-recorded payments)
# ==================================================================
class ReportPaymentRequest(BaseModel):
    """A student/parent reporting a payment made outside the portal flow
    (payment button, bank transfer, counter receipt, ...)."""
    student_id: UUID
    amount_paise: int = Field(..., gt=0)
    method: str = Field(..., min_length=2)
    reference: Optional[str] = None
    paid_at: Optional[str] = None
    notes: Optional[str] = None


class ConfirmPaymentRequest(BaseModel):
    """Admin confirmation of a pending payment. Optional explicit allocations;
    otherwise the payment is applied to its linked charge where possible."""
    allocations: Optional[List[AllocationSpec]] = None
    note: Optional[str] = None


@router.post("/payments/report", status_code=status.HTTP_201_CREATED)
async def report_payment(
    body: ReportPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Report a payment for verification. The payment is shown to the family
    as Pending Verification and the fee stays unpaid until an authorised
    admin confirms the transaction."""
    if current_user.role == UserRole.INSTRUCTOR:
        raise HTTPException(status_code=403, detail="Billing is not available for this account")
    await require_student_access(db, current_user, body.student_id)

    reference = (body.reference or "").strip() or None
    if reference:
        dup = (await db.execute(
            select(Payment).where(
                Payment.provider == "reported",
                Payment.provider_payment_id == reference,
            ))).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="This payment reference has already been submitted")

    student = (await db.execute(select(Student).where(Student.id == body.student_id))).scalar_one_or_none()
    payment = Payment(
        provider="reported",
        provider_payment_id=reference or f"REPORTED-{uuid4().hex[:10].upper()}",
        payer_user_id=student.user_id if student else current_user.id,
        payer_name=student.full_name if student else current_user.username,
        amount_paise=body.amount_paise,
        currency="INR",
        method=body.method,
        status="pending_verification",
        paid_at=datetime.fromisoformat(body.paid_at) if body.paid_at else datetime.utcnow(),
        verified_at=None,
        recorded_by=current_user.id if current_user.role == UserRole.ADMIN else None,
        notes=body.notes,
        source="reported",
    )
    db.add(payment)
    await db.flush()
    await record_audit(
        db,
        action="payment.reported",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Payment reported ({body.method}, {body.amount_paise} paise) — awaiting manual confirmation",
        after_data={"student_id": str(body.student_id), "reference": reference},
    )
    await db.flush()
    return {"status": "pending_verification", "payment": _serialize_payment(payment)}


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(
    payment_id: UUID,
    body: Optional[ConfirmPaymentRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Authorised admin confirms a pending payment after checking the
    transaction. This is the ONLY path that marks a fee paid for
    gateway/reported payments — it is idempotent-safe (double confirmation is
    refused) and records the verification action, timestamp and admin."""
    payment = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "verified":
        raise HTTPException(status_code=409, detail="This payment has already been confirmed")
    if payment.status in ("failed", "refunded", "disputed"):
        raise HTTPException(status_code=400, detail=f"A {payment.status} payment cannot be confirmed")

    before_status = payment.status
    payment.status = "verified"
    payment.verified_at = datetime.utcnow()
    payment.recorded_by = payment.recorded_by or current_user.id
    if body and body.note:
        payment.notes = ((payment.notes or "") + f" | Confirmed: {body.note}").strip(" |")
    db.add(payment)
    await db.flush()
    receipt_number = await _issue_receipt(db, payment, current_user.id)

    # allocations: explicit, the linked charge, or (for reported payments) the
    # payer's oldest outstanding charges — deterministically, never beyond the
    # payment amount or the charge itself
    applied = []
    specs = (body.allocations if body and body.allocations else None)
    if specs is None:
        specs = []
        if payment.invoice_id:
            targets = [(await db.execute(
                select(Invoice).where(Invoice.id == payment.invoice_id))).scalar_one_or_none()]
        else:
            payer_student = (await db.execute(
                select(Student).where(Student.user_id == payment.payer_user_id))).scalar_one_or_none()
            if payer_student:
                targets = (await db.execute(
                    select(Invoice).where(
                        Invoice.student_id == payer_student.id,
                        Invoice.status.in_(("pending", "partially_paid")),
                    ).order_by(Invoice.billing_month.asc()))).scalars().all()
            else:
                targets = []
        remaining = payment.amount_paise
        for invoice in targets:
            if remaining <= 0:
                break
            if not invoice or invoice.status == "void":
                continue
            existing = (await db.execute(
                select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
                    PaymentAllocation.invoice_id == invoice.id))).scalar_one() or 0
            take = min(remaining, max(invoice.amount_paise - existing, 0))
            if take > 0:
                specs.append(AllocationSpec(invoice_id=invoice.id, amount_paise=take))
                remaining -= take

    for spec in (specs or []):
        invoice = (await db.execute(select(Invoice).where(Invoice.id == spec.invoice_id))).scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail=f"Invoice {spec.invoice_id} not found")
        existing_to_invoice = (await db.execute(
            select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
                PaymentAllocation.invoice_id == invoice.id))).scalar_one() or 0
        if existing_to_invoice + spec.amount_paise > invoice.amount_paise:
            raise HTTPException(
                status_code=400,
                detail=f"Allocation exceeds the invoice charge on {invoice.invoice_number}",
            )
        db.add(PaymentAllocation(
            payment_id=payment.id,
            invoice_id=invoice.id,
            enrollment_id=invoice.enrollment_id,
            student_id=invoice.student_id,
            amount_paise=spec.amount_paise,
            allocated_by=current_user.id,
            reason=(body.note if body else None) or "Confirmed by academy administration",
        ))
        await _apply_allocation(db, invoice, spec.amount_paise)
        await _sync_exam_reimbursement(db, invoice)
        applied.append({"invoice": invoice.invoice_number, "amount_paise": spec.amount_paise})

    await record_audit(
        db,
        action="payment.confirmed_by_admin",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=(body.note if body and body.note else "Payment verified by administration") +
                f" (receipt {receipt_number})",
        before_data={"status": before_status},
        after_data={"status": "verified", "verified_at": payment.verified_at.isoformat(),
                    "verified_by": current_user.username, "allocations": applied},
    )
    if payment.payer_user_id:
        await notify_user(
            db,
            user_id=payment.payer_user_id,
            type="payment.confirmed",
            title="Payment confirmed",
            body=f"Your payment of {payment.amount_paise / 100:.2f} {payment.currency} has been verified by "
                 f"the academy and applied to your fee account.",
            dedupe_key=f"payment.confirmed:{payment.id}",
            related_entity_type="payment",
            related_entity_id=str(payment.id),
        )
    await db.flush()
    out = _serialize_payment(payment)
    out["allocations"] = applied
    return out


# ==================================================================
# Payment-claim rejection / clarification (admin, manual verification)
# ==================================================================
_CLAIM_REASONS_FALLBACK = "Payment claim rejected"


async def _resolve_claim_subject(db: AsyncSession, payment):
    """Deterministic student for a claim: invoice link first, then the payer.
    Returns (student, invoice) — student may be None (flagged, never guessed)."""
    inv = None
    if payment.invoice_id:
        inv = (await db.execute(select(Invoice).where(Invoice.id == payment.invoice_id))).scalar_one_or_none()
    student = None
    if inv and inv.student_id:
        student = (await db.execute(select(Student).where(Student.id == inv.student_id))).scalar_one_or_none()
    if student is None and payment.payer_user_id:
        student = (await db.execute(select(Student).where(Student.user_id == payment.payer_user_id))).scalar_one_or_none()
    return student, inv


async def _claim_support_thread(db: AsyncSession, current_user: User, student,
                                subject: str, message: str, file: Optional[UploadFile]):
    """Link the academy's response to the student through the existing support
    conversation system (visible + replyable from the student portal)."""
    if student is None:
        return None
    req = SupportRequest(
        sender_user_id=current_user.id,
        sender_role="admin",
        subject=subject[:200],
        message=(message or subject)[:4000],
        related_student_id=student.id,
        status="open",
    )
    db.add(req)
    await db.flush()
    if file is not None and getattr(file, "filename", ""):
        stored, ctype, size, _ = await save_upload(
            file, subdir="support", allowed_types=PAYMENT_EVIDENCE_TYPES)
        db.add(SupportAttachment(
            request_id=req.id,
            uploaded_by=current_user.id,
            filename=safe_filename(file.filename),
            stored_name=stored,
            content_type=ctype,
            size_bytes=size,
        ))
        await db.flush()
    return req


@router.post("/payments/{payment_id}/reject")
async def reject_payment_claim(
    payment_id: UUID,
    reason: str = Form(...),
    message: str = Form(""),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Reject an unverified payment claim with a reason, a personalised
    message and optional evidence attachment.

    Rejection never touches invoices, allocations, receipts or collected
    totals — a claim and a verified payment stay distinct.  Idempotent:
    repeating a rejection is refused with a clear conflict.
    """
    payment = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status == "rejected":
        raise HTTPException(status_code=409, detail="This claim has already been rejected")
    if payment.status == "verified":
        raise HTTPException(status_code=409,
                            detail="This payment is already verified — rejecting would erase a confirmed payment; "
                                   "record a correction instead")
    if payment.status not in ("pending_verification", "pending", "reported"):
        raise HTTPException(status_code=400,
                            detail=f"Only pending claims can be rejected (current status: {payment.status})")

    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A rejection reason is required")
    message = (message or "").strip()

    payment.status = "rejected"
    payment.notes = ((payment.notes or "") + f" | Rejected [{reason}]: {message or reason}").strip(" |")
    db.add(payment)
    await db.flush()

    student, _inv = await _resolve_claim_subject(db, payment)
    thread = await _claim_support_thread(
        db, current_user, student,
        subject=f"Payment claim rejected — {reason}",
        message=message or f"Your payment claim ({payment.amount_paise / 100:.2f} {payment.currency}) was "
                           f"not accepted: {reason}. Please contact the Academy if you need help.",
        file=file,
    )
    await record_audit(
        db,
        action="payment.claim_rejected",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Rejected payment claim {payment.provider_payment_id or payment.id}: [{reason}]"
                + (f" — {message[:80]}" if message else ""),
        after_data={"status": "rejected", "reason": reason},
    )
    await db.flush()
    return {"rejected": True, "status": "rejected",
            "support_request_id": str(thread.id) if thread else None,
            "claim_unlinked": student is None}


@router.post("/payments/{payment_id}/clarify")
async def clarify_payment_claim(
    payment_id: UUID,
    message: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Request clarification on a pending claim WITHOUT changing its status —
    the student sees the question (and any attachment) in their portal."""
    payment = (await db.execute(select(Payment).where(Payment.id == payment_id))).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status not in ("pending_verification", "pending", "reported"):
        raise HTTPException(status_code=400,
                            detail=f"Clarification applies only to pending claims (current status: {payment.status})")
    message = (message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="A clarification message is required")

    payment.notes = ((payment.notes or "") + f" | Clarification requested: {message}").strip(" |")
    db.add(payment)
    await db.flush()

    student, _inv = await _resolve_claim_subject(db, payment)
    thread = await _claim_support_thread(
        db, current_user, student,
        subject="Clarification requested — payment claim",
        message=message,
        file=file,
    )
    await record_audit(
        db,
        action="payment.claim_clarification_requested",
        entity_type="payment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Clarification requested on claim {payment.provider_payment_id or payment.id}: {message[:100]}",
    )
    await db.flush()
    return {"status": payment.status, "support_request_id": str(thread.id) if thread else None,
            "claim_unlinked": student is None}
