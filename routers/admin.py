from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
from models import User, Umbrella, UmbrellaZone, Shift, InspectionRule, UmbrellaStatus
from schemas import (
    UmbrellaCreate, UmbrellaUpdate, UmbrellaOut,
    ZoneCreate, ZoneOut,
    ShiftCreate, ShiftOut,
    InspectionRuleCreate, InspectionRuleUpdate, InspectionRuleOut,
)
from auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["管理员"])


@router.post("/zones", response_model=ZoneOut)
def create_zone(req: ZoneCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    existing = db.query(UmbrellaZone).filter(UmbrellaZone.name == req.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分区名称已存在")
    zone = UmbrellaZone(name=req.name, description=req.description)
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.get("/zones", response_model=List[ZoneOut])
def list_zones(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return db.query(UmbrellaZone).all()


@router.put("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(zone_id: int, req: ZoneCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    zone = db.query(UmbrellaZone).filter(UmbrellaZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分区不存在")
    zone.name = req.name
    zone.description = req.description
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    zone = db.query(UmbrellaZone).filter(UmbrellaZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分区不存在")
    linked = db.query(Umbrella).filter(Umbrella.zone_id == zone_id).count()
    if linked > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该分区下存在雨伞，无法删除")
    db.delete(zone)
    db.commit()
    return {"detail": "删除成功"}


@router.post("/shifts", response_model=ShiftOut)
def create_shift(req: ShiftCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    existing = db.query(Shift).filter(Shift.name == req.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="班次名称已存在")
    shift = Shift(name=req.name, start_time=req.start_time, end_time=req.end_time, description=req.description)
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.get("/shifts", response_model=List[ShiftOut])
def list_shifts(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return db.query(Shift).all()


@router.put("/shifts/{shift_id}", response_model=ShiftOut)
def update_shift(shift_id: int, req: ShiftCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班次不存在")
    shift.name = req.name
    shift.start_time = req.start_time
    shift.end_time = req.end_time
    shift.description = req.description
    db.commit()
    db.refresh(shift)
    return shift


@router.delete("/shifts/{shift_id}")
def delete_shift(shift_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="班次不存在")
    linked = db.query(Umbrella).filter(Umbrella.shift_id == shift_id).count()
    if linked > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该班次下存在雨伞，无法删除")
    db.delete(shift)
    db.commit()
    return {"detail": "删除成功"}


@router.post("/umbrellas", response_model=UmbrellaOut)
def create_umbrella(req: UmbrellaCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    existing = db.query(Umbrella).filter(Umbrella.code == req.code).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞编号已存在")
    if req.zone_id:
        zone = db.query(UmbrellaZone).filter(UmbrellaZone.id == req.zone_id).first()
        if not zone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="伞架分区不存在")
    if req.shift_id:
        shift = db.query(Shift).filter(Shift.id == req.shift_id).first()
        if not shift:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="责任班次不存在")
    umbrella = Umbrella(
        code=req.code,
        color=req.color,
        zone_id=req.zone_id,
        shift_id=req.shift_id,
        estimated_dry_minutes=req.estimated_dry_minutes,
        status=UmbrellaStatus.pending,
        created_at=datetime.now(),
    )
    db.add(umbrella)
    db.commit()
    db.refresh(umbrella)
    return umbrella


@router.get("/umbrellas", response_model=List[UmbrellaOut])
def list_umbrellas(
    zone_id: Optional[int] = Query(None),
    shift_id: Optional[int] = Query(None),
    status: Optional[UmbrellaStatus] = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    q = db.query(Umbrella)
    if zone_id is not None:
        q = q.filter(Umbrella.zone_id == zone_id)
    if shift_id is not None:
        q = q.filter(Umbrella.shift_id == shift_id)
    if status is not None:
        q = q.filter(Umbrella.status == status)
    return q.all()


@router.get("/umbrellas/{umbrella_id}", response_model=UmbrellaOut)
def get_umbrella(umbrella_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    return umbrella


@router.put("/umbrellas/{umbrella_id}", response_model=UmbrellaOut)
def update_umbrella(umbrella_id: int, req: UmbrellaUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    if req.code is not None:
        existing = db.query(Umbrella).filter(Umbrella.code == req.code, Umbrella.id != umbrella_id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="雨伞编号已存在")
        umbrella.code = req.code
    if req.color is not None:
        umbrella.color = req.color
    if req.zone_id is not None:
        zone = db.query(UmbrellaZone).filter(UmbrellaZone.id == req.zone_id).first()
        if not zone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="伞架分区不存在")
        umbrella.zone_id = req.zone_id
    if req.shift_id is not None:
        shift = db.query(Shift).filter(Shift.id == req.shift_id).first()
        if not shift:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="责任班次不存在")
        umbrella.shift_id = req.shift_id
    if req.estimated_dry_minutes is not None:
        umbrella.estimated_dry_minutes = req.estimated_dry_minutes
    if req.status is not None:
        umbrella.status = req.status
    if req.deactivate_reason is not None:
        umbrella.deactivate_reason = req.deactivate_reason
    db.commit()
    db.refresh(umbrella)
    return umbrella


@router.delete("/umbrellas/{umbrella_id}")
def delete_umbrella(umbrella_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    umbrella = db.query(Umbrella).filter(Umbrella.id == umbrella_id).first()
    if not umbrella:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="雨伞不存在")
    db.delete(umbrella)
    db.commit()
    return {"detail": "删除成功"}


@router.post("/inspection-rules", response_model=InspectionRuleOut)
def create_inspection_rule(req: InspectionRuleCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    if req.zone_id:
        zone = db.query(UmbrellaZone).filter(UmbrellaZone.id == req.zone_id).first()
        if not zone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="伞架分区不存在")
    rule = InspectionRule(
        name=req.name,
        zone_id=req.zone_id,
        interval_minutes=req.interval_minutes,
        check_wetness=req.check_wetness,
        check_handle=req.check_handle,
        check_status=req.check_status,
        is_active=req.is_active,
        description=req.description,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/inspection-rules", response_model=List[InspectionRuleOut])
def list_inspection_rules(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return db.query(InspectionRule).all()


@router.put("/inspection-rules/{rule_id}", response_model=InspectionRuleOut)
def update_inspection_rule(rule_id: int, req: InspectionRuleUpdate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    rule = db.query(InspectionRule).filter(InspectionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡查规则不存在")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/inspection-rules/{rule_id}")
def delete_inspection_rule(rule_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    rule = db.query(InspectionRule).filter(InspectionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡查规则不存在")
    db.delete(rule)
    db.commit()
    return {"detail": "删除成功"}
