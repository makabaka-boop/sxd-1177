from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from models import (
    User, Umbrella, UmbrellaOperation, UmbrellaZone,
    UmbrellaStatus, WetnessLevel, RepairOrder, RepairStatus,
)
from schemas import (
    UmbrellaOut, OperationOut,
    TurnoverItem, TurnoverRanking,
    PendingRecheckItem, PendingRecheckList,
    ZoneAnomalyItem, ZoneAnomalyStats,
    RepairOverviewResponse, ZoneRepairStatsItem, RecentAnomalyUmbrellaItem,
)
from auth import require_staff

router = APIRouter(prefix="/api/stats", tags=["查询统计"])


@router.get("/umbrellas", response_model=list[UmbrellaOut])
def query_umbrellas(
    zone_id: Optional[int] = Query(None),
    shift_id: Optional[int] = Query(None),
    status: Optional[UmbrellaStatus] = Query(None),
    wetness: Optional[WetnessLevel] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    q = db.query(Umbrella)
    if zone_id is not None:
        q = q.filter(Umbrella.zone_id == zone_id)
    if shift_id is not None:
        q = q.filter(Umbrella.shift_id == shift_id)
    if status is not None:
        q = q.filter(Umbrella.status == status)
    if wetness is not None or date_from is not None or date_to is not None:
        op_sub = db.query(UmbrellaOperation.umbrella_id).filter(
            UmbrellaOperation.return_time.isnot(None)
        )
        if wetness is not None:
            op_sub = op_sub.filter(UmbrellaOperation.wetness == wetness)
        if date_from is not None:
            op_sub = op_sub.filter(UmbrellaOperation.return_time >= date_from)
        if date_to is not None:
            op_sub = op_sub.filter(UmbrellaOperation.return_time <= date_to)
        umbrella_ids = op_sub.distinct().subquery()
        q = q.filter(Umbrella.id.in_(umbrella_ids))
    return q.all()


@router.get("/operations", response_model=list[OperationOut])
def query_operations(
    zone_id: Optional[int] = Query(None),
    shift_id: Optional[int] = Query(None),
    status: Optional[UmbrellaStatus] = Query(None),
    wetness: Optional[WetnessLevel] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    q = db.query(UmbrellaOperation)
    if wetness is not None:
        q = q.filter(UmbrellaOperation.wetness == wetness)
    if date_from is not None:
        q = q.filter(UmbrellaOperation.checkout_time >= date_from)
    if date_to is not None:
        q = q.filter(UmbrellaOperation.checkout_time <= date_to)
    if zone_id is not None or shift_id is not None or status is not None:
        umbrella_q = db.query(Umbrella.id)
        if zone_id is not None:
            umbrella_q = umbrella_q.filter(Umbrella.zone_id == zone_id)
        if shift_id is not None:
            umbrella_q = umbrella_q.filter(Umbrella.shift_id == shift_id)
        if status is not None:
            umbrella_q = umbrella_q.filter(Umbrella.status == status)
        umbrella_ids = umbrella_q.subquery()
        q = q.filter(UmbrellaOperation.umbrella_id.in_(umbrella_ids))
    return q.order_by(UmbrellaOperation.id.desc()).all()


@router.get("/turnover-ranking", response_model=TurnoverRanking)
def turnover_ranking(
    limit: int = Query(10, ge=1, le=100),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    q = db.query(
        UmbrellaOperation.umbrella_id,
        Umbrella.code,
        func.count(UmbrellaOperation.id).label("turnover_count"),
    ).join(Umbrella, UmbrellaOperation.umbrella_id == Umbrella.id)
    if date_from is not None:
        q = q.filter(UmbrellaOperation.checkout_time >= date_from)
    if date_to is not None:
        q = q.filter(UmbrellaOperation.checkout_time <= date_to)
    q = q.group_by(UmbrellaOperation.umbrella_id, Umbrella.code).order_by(
        func.count(UmbrellaOperation.id).desc()
    ).limit(limit)
    rows = q.all()
    items = [TurnoverItem(umbrella_id=r.umbrella_id, code=r.code, turnover_count=r.turnover_count) for r in rows]
    return TurnoverRanking(ranking=items)


@router.get("/pending-recheck", response_model=PendingRecheckList)
def pending_recheck_list(
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    umbrellas = db.query(Umbrella).filter(Umbrella.status == UmbrellaStatus.pending_recheck).all()
    items = []
    for u in umbrellas:
        op = db.query(UmbrellaOperation).filter(
            UmbrellaOperation.umbrella_id == u.id,
        ).order_by(UmbrellaOperation.id.desc()).first()
        items.append(PendingRecheckItem(
            umbrella_id=u.id,
            code=u.code,
            color=u.color,
            zone_id=u.zone_id,
            dry_start_time=op.dry_start_time if op else None,
        ))
    return PendingRecheckList(items=items, total=len(items))


@router.get("/zone-anomaly", response_model=ZoneAnomalyStats)
def zone_anomaly_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    zones = db.query(UmbrellaZone).all()
    items = []
    for z in zones:
        total = db.query(Umbrella).filter(Umbrella.zone_id == z.id).count()
        deactivated = db.query(Umbrella).filter(
            Umbrella.zone_id == z.id,
            Umbrella.status == UmbrellaStatus.deactivated,
        ).count()
        pending_dry = db.query(Umbrella).filter(
            Umbrella.zone_id == z.id,
            Umbrella.status == UmbrellaStatus.pending_dry,
        ).count()
        pending_recheck = db.query(Umbrella).filter(
            Umbrella.zone_id == z.id,
            Umbrella.status == UmbrellaStatus.pending_recheck,
        ).count()
        anomaly = deactivated + pending_dry + pending_recheck
        rate = round(anomaly / total, 4) if total > 0 else 0.0
        items.append(ZoneAnomalyItem(
            zone_id=z.id,
            zone_name=z.name,
            total_umbrellas=total,
            deactivated_count=deactivated,
            pending_dry_count=pending_dry,
            pending_recheck_count=pending_recheck,
            anomaly_rate=rate,
        ))
    return ZoneAnomalyStats(zones=items)


@router.get("/repair-overview", response_model=RepairOverviewResponse)
def repair_overview(
    limit_recent: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    pending_count = db.query(RepairOrder).filter(
        RepairOrder.status.in_([RepairStatus.pending, RepairStatus.assigned, RepairStatus.in_progress])
    ).count()

    completed_count = db.query(RepairOrder).filter(
        RepairOrder.status == RepairStatus.completed
    ).count()

    total_count = pending_count + completed_count + db.query(RepairOrder).filter(
        RepairOrder.status == RepairStatus.closed
    ).count()

    repair_completion_rate = round(completed_count / total_count, 4) if total_count > 0 else 0.0

    zones = db.query(UmbrellaZone).all()
    zone_anomaly_stats = []
    for z in zones:
        anomaly_count = db.query(RepairOrder).join(
            Umbrella, RepairOrder.umbrella_id == Umbrella.id
        ).filter(
            Umbrella.zone_id == z.id,
            RepairOrder.status.in_([RepairStatus.pending, RepairStatus.assigned, RepairStatus.in_progress]),
        ).count()
        zone_anomaly_stats.append(ZoneRepairStatsItem(
            zone_id=z.id,
            zone_name=z.name,
            anomaly_order_count=anomaly_count,
        ))

    recent_orders = db.query(RepairOrder).order_by(
        RepairOrder.created_at.desc()
    ).limit(limit_recent).all()

    recent_anomaly_umbrellas = []
    for order in recent_orders:
        umbrella = order.umbrella
        if umbrella:
            recent_anomaly_umbrellas.append(RecentAnomalyUmbrellaItem(
                umbrella_id=umbrella.id,
                code=umbrella.code,
                color=umbrella.color,
                zone_id=umbrella.zone_id,
                anomaly_description=order.anomaly_description,
                created_at=order.created_at,
            ))

    return RepairOverviewResponse(
        pending_count=pending_count,
        completed_count=completed_count,
        zone_anomaly_stats=zone_anomaly_stats,
        repair_completion_rate=repair_completion_rate,
        recent_anomaly_umbrellas=recent_anomaly_umbrellas,
    )
