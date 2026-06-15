from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
from models import (
    User, UserRole, Umbrella, UmbrellaZone, Shift,
    TransferOrder, TransferStatus, UmbrellaStatus,
)
from schemas import (
    TransferOrderCreate, TransferOrderOut, TransferOrderListResponse,
)
from auth import require_admin, require_staff

admin_router = APIRouter(prefix="/api/admin/transfers", tags=["管理员-雨伞调拨"])
ops_router = APIRouter(prefix="/api/operations/transfers", tags=["现场操作-雨伞调拨"])


def _enrich_transfer_order(order: TransferOrder) -> TransferOrderOut:
    return TransferOrderOut(
        id=order.id,
        umbrella_id=order.umbrella_id,
        umbrella_code=order.umbrella.code if order.umbrella else None,
        from_zone_id=order.from_zone_id,
        from_zone_name=order.from_zone.name if order.from_zone else None,
        to_zone_id=order.to_zone_id,
        to_zone_name=order.to_zone.name if order.to_zone else None,
        from_shift_id=order.from_shift_id,
        from_shift_name=order.from_shift.name if order.from_shift else None,
        to_shift_id=order.to_shift_id,
        to_shift_name=order.to_shift.name if order.to_shift else None,
        creator_id=order.creator_id,
        creator_username=order.creator.username if order.creator else None,
        receiver_id=order.receiver_id,
        receiver_username=order.receiver.username if order.receiver else None,
        reason=order.reason,
        status=order.status,
        created_at=order.created_at,
        completed_at=order.completed_at,
    )


def _validate_umbrella_transferable(db: Session, umbrella_id: int) -> Umbrella:
    umbrella = db.query(Umbrella).filter(Umbrella.id == umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status == UmbrellaStatus.in_use:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞正在使用中，不可调拨")
    if umbrella.status == UmbrellaStatus.deactivated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞已停用，不可调拨")
    pending = db.query(TransferOrder).filter(
        TransferOrder.umbrella_id == umbrella_id,
        TransferOrder.status == TransferStatus.pending,
    ).first()
    if pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该雨伞已有待接收的调拨单")
    return umbrella


@admin_router.post("", response_model=TransferOrderOut)
def create_transfer_order(
    req: TransferOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    umbrella = _validate_umbrella_transferable(db, req.umbrella_id)

    to_zone = db.query(UmbrellaZone).filter(UmbrellaZone.id == req.to_zone_id).first()
    if not to_zone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标分区不存在")

    to_shift = db.query(Shift).filter(Shift.id == req.to_shift_id).first()
    if not to_shift:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标班次不存在")

    receiver = db.query(User).filter(User.id == req.receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="接收人不存在")
    if not receiver.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="接收人已停用")
    if receiver.role != UserRole.staff and receiver.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="接收人无效")

    if umbrella.zone_id == req.to_zone_id and umbrella.shift_id == req.to_shift_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标分区和班次与当前相同，无需调拨")

    now = datetime.now()
    order = TransferOrder(
        umbrella_id=req.umbrella_id,
        from_zone_id=umbrella.zone_id,
        to_zone_id=req.to_zone_id,
        from_shift_id=umbrella.shift_id,
        to_shift_id=req.to_shift_id,
        creator_id=current_user.id,
        receiver_id=req.receiver_id,
        reason=req.reason,
        status=TransferStatus.pending,
        created_at=now,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _enrich_transfer_order(order)


@admin_router.get("", response_model=TransferOrderListResponse)
def list_transfer_orders(
    umbrella_id: Optional[int] = Query(None),
    from_zone_id: Optional[int] = Query(None),
    to_zone_id: Optional[int] = Query(None),
    from_shift_id: Optional[int] = Query(None),
    to_shift_id: Optional[int] = Query(None),
    receiver_id: Optional[int] = Query(None),
    status: Optional[TransferStatus] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    q = db.query(TransferOrder)
    if umbrella_id is not None:
        q = q.filter(TransferOrder.umbrella_id == umbrella_id)
    if from_zone_id is not None:
        q = q.filter(TransferOrder.from_zone_id == from_zone_id)
    if to_zone_id is not None:
        q = q.filter(TransferOrder.to_zone_id == to_zone_id)
    if from_shift_id is not None:
        q = q.filter(TransferOrder.from_shift_id == from_shift_id)
    if to_shift_id is not None:
        q = q.filter(TransferOrder.to_shift_id == to_shift_id)
    if receiver_id is not None:
        q = q.filter(TransferOrder.receiver_id == receiver_id)
    if status is not None:
        q = q.filter(TransferOrder.status == status)
    if date_from is not None:
        q = q.filter(TransferOrder.created_at >= date_from)
    if date_to is not None:
        q = q.filter(TransferOrder.created_at <= date_to)
    total = q.count()
    orders = q.order_by(TransferOrder.created_at.desc()).all()
    items = [_enrich_transfer_order(o) for o in orders]
    return TransferOrderListResponse(items=items, total=total)


@admin_router.get("/{order_id}", response_model=TransferOrderOut)
def get_transfer_order(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    order = db.query(TransferOrder).filter(TransferOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调拨单不存在")
    return _enrich_transfer_order(order)


@admin_router.put("/{order_id}/cancel", response_model=TransferOrderOut)
def cancel_transfer_order(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    order = db.query(TransferOrder).filter(TransferOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调拨单不存在")
    if order.status != TransferStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {order.status.value} 不可取消",
        )
    order.status = TransferStatus.cancelled
    db.commit()
    db.refresh(order)
    return _enrich_transfer_order(order)


@ops_router.get("/my-pending", response_model=TransferOrderListResponse)
def list_my_pending_transfers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    q = db.query(TransferOrder).filter(
        TransferOrder.receiver_id == current_user.id,
        TransferOrder.status == TransferStatus.pending,
    )
    total = q.count()
    orders = q.order_by(TransferOrder.created_at.desc()).all()
    items = [_enrich_transfer_order(o) for o in orders]
    return TransferOrderListResponse(items=items, total=total)


@ops_router.put("/{order_id}/receive", response_model=TransferOrderOut)
def receive_transfer_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    order = db.query(TransferOrder).filter(TransferOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调拨单不存在")
    if order.receiver_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权接收该调拨单")
    if order.status != TransferStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {order.status.value} 不可接收",
        )

    umbrella = db.query(Umbrella).filter(Umbrella.id == order.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if umbrella.status == UmbrellaStatus.in_use:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞正在使用中，无法完成调拨")
    if umbrella.status == UmbrellaStatus.deactivated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞已停用，无法完成调拨")

    now = datetime.now()
    umbrella.zone_id = order.to_zone_id
    umbrella.shift_id = order.to_shift_id
    order.status = TransferStatus.completed
    order.completed_at = now

    db.commit()
    db.refresh(order)
    return _enrich_transfer_order(order)


@ops_router.get("/{order_id}", response_model=TransferOrderOut)
def get_transfer_order_ops(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    order = db.query(TransferOrder).filter(TransferOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调拨单不存在")
    if order.creator_id != current_user.id and order.receiver_id != current_user.id:
        if current_user.role != UserRole.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该调拨单")
    return _enrich_transfer_order(order)
