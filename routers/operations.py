from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
from models import (
    User, Umbrella, UmbrellaOperation, UmbrellaStatus, WetnessLevel, RecheckResult,
    InspectionRule, InspectionRecord, InspectionItem,
    RepairOrder, RepairSourceType, RepairStatus,
)
from schemas import (
    CheckoutRequest, ReturnRequest, DryStartRequest, RecheckRequest,
    DeactivateRequest, OperationOut, UmbrellaOut,
    InspectionExecute, InspectionRecordOut, InspectionItemCreate,
)
from auth import require_staff, require_admin

router = APIRouter(prefix="/api/operations", tags=["现场操作"])


@router.post("/checkout", response_model=OperationOut)
def checkout(req: CheckoutRequest, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == req.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status not in (UmbrellaStatus.pending, UmbrellaStatus.available):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {umbrella.status.value} 不可领出")
    now = datetime.now()
    op = UmbrellaOperation(
        umbrella_id=umbrella.id,
        operator_id=current_user.id,
        checkout_time=now,
    )
    umbrella.status = UmbrellaStatus.in_use
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


@router.post("/return", response_model=OperationOut)
def return_umbrella(req: ReturnRequest, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == req.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status != UmbrellaStatus.in_use:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {umbrella.status.value} 不可归还")
    op = db.query(UmbrellaOperation).filter(
        UmbrellaOperation.umbrella_id == umbrella.id,
        UmbrellaOperation.return_time.is_(None),
    ).order_by(UmbrellaOperation.id.desc()).first()
    if not op:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未找到对应的领出记录")
    now = datetime.now()
    op.return_time = now
    op.wetness = req.wetness
    op.handle_looseness = req.handle_looseness
    if req.wetness in (WetnessLevel.slight, WetnessLevel.moderate, WetnessLevel.heavy):
        umbrella.status = UmbrellaStatus.pending_dry
    else:
        umbrella.status = UmbrellaStatus.available
    db.commit()
    db.refresh(op)
    return op


@router.post("/dry-start", response_model=OperationOut)
def start_drying(req: DryStartRequest, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == req.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status != UmbrellaStatus.pending_dry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {umbrella.status.value} 不可开始晾干")
    op = db.query(UmbrellaOperation).filter(
        UmbrellaOperation.umbrella_id == umbrella.id,
        UmbrellaOperation.dry_start_time.is_(None),
        UmbrellaOperation.wetness.isnot(None),
    ).order_by(UmbrellaOperation.id.desc()).first()
    if not op:
        op = db.query(UmbrellaOperation).filter(
            UmbrellaOperation.umbrella_id == umbrella.id,
            UmbrellaOperation.wetness.isnot(None),
            UmbrellaOperation.recheck_result == RecheckResult.failed,
        ).order_by(UmbrellaOperation.id.desc()).first()
        if not op:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未找到对应的归还或复查失败记录")
        op.recheck_result = None
    now = datetime.now()
    op.dry_start_time = now
    umbrella.status = UmbrellaStatus.pending_recheck
    db.commit()
    db.refresh(op)
    return op


@router.post("/recheck", response_model=OperationOut)
def recheck(req: RecheckRequest, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == req.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status != UmbrellaStatus.pending_recheck:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {umbrella.status.value} 不可复查")
    op = db.query(UmbrellaOperation).filter(
        UmbrellaOperation.umbrella_id == umbrella.id,
        UmbrellaOperation.recheck_result.is_(None),
    ).order_by(UmbrellaOperation.id.desc()).first()
    if not op:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未找到对应的晾干记录")
    op.recheck_result = req.recheck_result
    if req.recheck_result == RecheckResult.passed:
        umbrella.status = UmbrellaStatus.available
    else:
        umbrella.status = UmbrellaStatus.pending_dry
        existing_order = db.query(RepairOrder).filter(
            RepairOrder.umbrella_id == umbrella.id,
            RepairOrder.status.in_([RepairStatus.pending, RepairStatus.assigned, RepairStatus.in_progress]),
        ).first()
        if not existing_order:
            now = datetime.now()
            repair_order = RepairOrder(
                umbrella_id=umbrella.id,
                source_type=RepairSourceType.recheck_failed,
                anomaly_description="雨伞晾干复查失败，需要维修处理",
                status=RepairStatus.pending,
                creator_id=current_user.id,
                created_at=now,
            )
            db.add(repair_order)
    db.commit()
    db.refresh(op)
    return op


@router.post("/deactivate", response_model=UmbrellaOut)
def deactivate(req: DeactivateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == req.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status == UmbrellaStatus.deactivated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞已处于停用状态")
    umbrella.status = UmbrellaStatus.deactivated
    umbrella.deactivate_reason = req.deactivate_reason
    op = db.query(UmbrellaOperation).filter(
        UmbrellaOperation.umbrella_id == umbrella.id,
    ).order_by(UmbrellaOperation.id.desc()).first()
    if op:
        op.deactivate_reason = req.deactivate_reason
    existing_order = db.query(RepairOrder).filter(
        RepairOrder.umbrella_id == umbrella.id,
        RepairOrder.status.in_([RepairStatus.pending, RepairStatus.assigned, RepairStatus.in_progress]),
    ).first()
    if not existing_order:
        now = datetime.now()
        repair_order = RepairOrder(
            umbrella_id=umbrella.id,
            source_type=RepairSourceType.staff_deactivate,
            anomaly_description=req.deactivate_reason,
            status=RepairStatus.pending,
            creator_id=current_user.id,
            created_at=now,
        )
        db.add(repair_order)
    db.commit()
    db.refresh(umbrella)
    return umbrella


@router.post("/reactivate/{umbrella_id}", response_model=UmbrellaOut)
def reactivate(umbrella_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status != UmbrellaStatus.deactivated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞未处于停用状态")
    umbrella.status = UmbrellaStatus.available
    umbrella.deactivate_reason = None
    db.commit()
    db.refresh(umbrella)
    return umbrella


@router.get("/history/{umbrella_id}", response_model=list[OperationOut])
def operation_history(umbrella_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    ops = db.query(UmbrellaOperation).filter(UmbrellaOperation.umbrella_id == umbrella_id).order_by(UmbrellaOperation.id.desc()).all()
    return ops


@router.post("/inspection", response_model=InspectionRecordOut)
def execute_inspection(
    req: InspectionExecute,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    rule = db.query(InspectionRule).filter(InspectionRule.id == req.rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡查规则不存在")
    if not rule.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该巡查规则已停用")
    now = datetime.now()
    record = InspectionRecord(
        rule_id=rule.id,
        zone_id=rule.zone_id,
        inspector_id=current_user.id,
        inspected_at=now,
        total_checked=len(req.items),
        anomaly_count=sum(1 for it in req.items if it.is_anomaly),
        notes=req.notes,
    )
    db.add(record)
    db.flush()
    for it in req.items:
        umbrella = db.query(Umbrella).filter(Umbrella.id == it.umbrella_id).first()
        if not umbrella:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"雨伞ID {it.umbrella_id} 不存在")
        if rule.zone_id and umbrella.zone_id != rule.zone_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"雨伞 {umbrella.code} 不在规则指定的分区内",
            )
        item = InspectionItem(
            record_id=record.id,
            umbrella_id=it.umbrella_id,
            wetness_ok=it.wetness_ok if rule.check_wetness else None,
            handle_ok=it.handle_ok if rule.check_handle else None,
            status_ok=it.status_ok if rule.check_status else None,
            is_anomaly=it.is_anomaly,
            anomaly_detail=it.anomaly_detail,
        )
        db.add(item)
        if it.is_anomaly and it.anomaly_detail:
            if umbrella.status not in (UmbrellaStatus.deactivated, UmbrellaStatus.pending_dry, UmbrellaStatus.pending_recheck):
                umbrella.status = UmbrellaStatus.pending_dry
            existing_order = db.query(RepairOrder).filter(
                RepairOrder.umbrella_id == umbrella.id,
                RepairOrder.status.in_([RepairStatus.pending, RepairStatus.assigned, RepairStatus.in_progress]),
            ).first()
            if not existing_order:
                repair_order = RepairOrder(
                    umbrella_id=umbrella.id,
                    source_type=RepairSourceType.inspection,
                    anomaly_description=it.anomaly_detail,
                    status=RepairStatus.pending,
                    creator_id=current_user.id,
                    created_at=now,
                )
                db.add(repair_order)
    db.commit()
    db.refresh(record)
    return record


@router.get("/inspection", response_model=List[InspectionRecordOut])
def list_inspection_records(
    rule_id: Optional[int] = Query(None),
    zone_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    only_anomaly: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    q = db.query(InspectionRecord)
    if rule_id is not None:
        q = q.filter(InspectionRecord.rule_id == rule_id)
    if zone_id is not None:
        q = q.filter(InspectionRecord.zone_id == zone_id)
    if date_from is not None:
        q = q.filter(InspectionRecord.inspected_at >= date_from)
    if date_to is not None:
        q = q.filter(InspectionRecord.inspected_at <= date_to)
    if only_anomaly:
        q = q.filter(InspectionRecord.anomaly_count > 0)
    return q.order_by(InspectionRecord.inspected_at.desc()).all()


@router.get("/inspection/due", response_model=List[dict])
def list_due_inspections(db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    now = datetime.now()
    rules = db.query(InspectionRule).filter(InspectionRule.is_active == True).all()
    result = []
    for rule in rules:
        last = (
            db.query(InspectionRecord)
            .filter(InspectionRecord.rule_id == rule.id)
            .order_by(InspectionRecord.inspected_at.desc())
            .first()
        )
        last_at = last.inspected_at if last else None
        is_due = True
        if last_at:
            next_due = last_at + timedelta(minutes=rule.interval_minutes)
            is_due = now >= next_due
        result.append({
            "rule_id": rule.id,
            "rule_name": rule.name,
            "zone_id": rule.zone_id,
            "interval_minutes": rule.interval_minutes,
            "last_inspected_at": last_at,
            "is_due": is_due,
        })
    return result


@router.get("/inspection/{record_id}", response_model=InspectionRecordOut)
def get_inspection_record(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff)):
    record = db.query(InspectionRecord).filter(InspectionRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡查记录不存在")
    return record
