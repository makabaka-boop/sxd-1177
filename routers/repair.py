from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
from models import (
    User, Umbrella, RepairOrder, RepairStatus, RepairSourceType, RepairResult,
    UmbrellaZone, UmbrellaStatus,
)
from schemas import (
    RepairOrderCreate, RepairOrderAssign, RepairOrderHandle,
    RepairOrderOut, RepairOrderListResponse,
)
from auth import require_admin, require_staff

router = APIRouter(prefix="/api/repair", tags=["维修工单"])


def _enrich_repair_order(order: RepairOrder) -> RepairOrderOut:
    return RepairOrderOut(
        id=order.id,
        umbrella_id=order.umbrella_id,
        umbrella_code=order.umbrella.code if order.umbrella else None,
        source_type=order.source_type,
        anomaly_description=order.anomaly_description,
        status=order.status,
        creator_id=order.creator_id,
        creator_username=order.creator.username if order.creator else None,
        handler_id=order.handler_id,
        handler_username=order.handler.username if order.handler else None,
        created_at=order.created_at,
        completed_at=order.completed_at,
        handle_remark=order.handle_remark,
        repair_result=order.repair_result,
    )


@router.post("/orders", response_model=RepairOrderOut)
def create_repair_order(
    req: RepairOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    umbrella = db.query(Umbrella).filter(Umbrella.id == req.umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    now = datetime.now()
    order = RepairOrder(
        umbrella_id=req.umbrella_id,
        source_type=req.source_type,
        anomaly_description=req.anomaly_description,
        status=RepairStatus.pending,
        creator_id=current_user.id,
        created_at=now,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _enrich_repair_order(order)


@router.get("/orders", response_model=RepairOrderListResponse)
def list_repair_orders(
    zone_id: Optional[int] = Query(None),
    umbrella_id: Optional[int] = Query(None),
    status: Optional[RepairStatus] = Query(None),
    source_type: Optional[RepairSourceType] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    q = db.query(RepairOrder)
    if umbrella_id is not None:
        q = q.filter(RepairOrder.umbrella_id == umbrella_id)
    if status is not None:
        q = q.filter(RepairOrder.status == status)
    if source_type is not None:
        q = q.filter(RepairOrder.source_type == source_type)
    if zone_id is not None:
        q = q.join(Umbrella, RepairOrder.umbrella_id == Umbrella.id).filter(
            Umbrella.zone_id == zone_id
        )
    total = q.count()
    orders = q.order_by(RepairOrder.created_at.desc()).all()
    items = [_enrich_repair_order(o) for o in orders]
    return RepairOrderListResponse(items=items, total=total)


@router.get("/orders/my-pending", response_model=RepairOrderListResponse)
def list_my_pending_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    q = db.query(RepairOrder).filter(
        RepairOrder.handler_id == current_user.id,
        RepairOrder.status.in_([RepairStatus.assigned, RepairStatus.in_progress]),
    )
    total = q.count()
    orders = q.order_by(RepairOrder.created_at.desc()).all()
    items = [_enrich_repair_order(o) for o in orders]
    return RepairOrderListResponse(items=items, total=total)


@router.get("/orders/{order_id}", response_model=RepairOrderOut)
def get_repair_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="维修工单不存在")
    return _enrich_repair_order(order)


@router.put("/orders/{order_id}/assign", response_model=RepairOrderOut)
def assign_repair_order(
    order_id: int,
    req: RepairOrderAssign,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="维修工单不存在")
    if order.status == RepairStatus.closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已关闭的工单无法指派")
    handler = db.query(User).filter(User.id == req.handler_id).first()
    if not handler:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="处理人不存在")
    if not handler.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="处理人已停用")
    order.handler_id = req.handler_id
    order.status = RepairStatus.assigned
    db.commit()
    db.refresh(order)
    return _enrich_repair_order(order)


@router.put("/orders/{order_id}/start", response_model=RepairOrderOut)
def start_repair_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="维修工单不存在")
    if order.handler_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能处理指派给自己的工单")
    if order.status != RepairStatus.assigned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {order.status.value} 不可开始处理")
    order.status = RepairStatus.in_progress
    db.commit()
    db.refresh(order)
    return _enrich_repair_order(order)


@router.put("/orders/{order_id}/complete", response_model=RepairOrderOut)
def complete_repair_order(
    order_id: int,
    req: RepairOrderHandle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="维修工单不存在")
    if order.handler_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能处理指派给自己的工单")
    if order.status != RepairStatus.in_progress:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {order.status.value} 不可完成处理")
    now = datetime.now()
    order.repair_result = req.repair_result
    order.handle_remark = req.handle_remark
    order.completed_at = now
    order.status = RepairStatus.completed

    umbrella = db.query(Umbrella).filter(Umbrella.id == order.umbrella_id).first()
    if umbrella:
        if req.repair_result == RepairResult.fixed:
            umbrella.status = UmbrellaStatus.available
            umbrella.deactivate_reason = None
        elif req.repair_result in (RepairResult.scrapped, RepairResult.cannot_repair):
            umbrella.status = UmbrellaStatus.deactivated
            if not umbrella.deactivate_reason:
                umbrella.deactivate_reason = req.handle_remark or "维修后无法使用"

    db.commit()
    db.refresh(order)
    return _enrich_repair_order(order)


@router.put("/orders/{order_id}/close", response_model=RepairOrderOut)
def close_repair_order(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="维修工单不存在")
    if order.status not in (RepairStatus.completed, RepairStatus.pending, RepairStatus.assigned, RepairStatus.in_progress):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {order.status.value} 不可关闭")
    order.status = RepairStatus.closed
    db.commit()
    db.refresh(order)
    return _enrich_repair_order(order)


@router.put("/orders/{order_id}/reopen", response_model=RepairOrderOut)
def reopen_repair_order(
    order_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="维修工单不存在")
    if order.status != RepairStatus.closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前状态 {order.status.value} 不可重新打开")
    order.status = RepairStatus.pending
    order.completed_at = None
    order.repair_result = None
    order.handle_remark = None
    db.commit()
    db.refresh(order)
    return _enrich_repair_order(order)
