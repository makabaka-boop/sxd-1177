from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import User, Umbrella, UmbrellaOperation, UmbrellaStatus, WetnessLevel, RecheckResult
from schemas import (
    CheckoutRequest, ReturnRequest, DryStartRequest, RecheckRequest,
    DeactivateRequest, OperationOut, UmbrellaOut,
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
    ).order_by(UmbrellaOperation.id.desc()).first()
    if not op:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未找到对应的归还记录")
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
