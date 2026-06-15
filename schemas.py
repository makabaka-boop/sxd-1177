from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from models import UserRole, UmbrellaStatus, WetnessLevel, RecheckResult


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.staff


class UserOut(BaseModel):
    id: int
    username: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class ZoneCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ZoneOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ShiftCreate(BaseModel):
    name: str
    start_time: str
    end_time: str
    description: Optional[str] = None


class ShiftOut(BaseModel):
    id: int
    name: str
    start_time: str
    end_time: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class UmbrellaCreate(BaseModel):
    code: str
    color: str
    zone_id: Optional[int] = None
    shift_id: Optional[int] = None
    estimated_dry_minutes: Optional[int] = 60


class UmbrellaUpdate(BaseModel):
    code: Optional[str] = None
    color: Optional[str] = None
    zone_id: Optional[int] = None
    shift_id: Optional[int] = None
    estimated_dry_minutes: Optional[int] = None
    status: Optional[UmbrellaStatus] = None
    deactivate_reason: Optional[str] = None


class UmbrellaOut(BaseModel):
    id: int
    code: str
    color: str
    zone_id: Optional[int] = None
    shift_id: Optional[int] = None
    status: UmbrellaStatus
    estimated_dry_minutes: Optional[int] = None
    deactivate_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
    umbrella_id: int


class ReturnRequest(BaseModel):
    umbrella_id: int
    wetness: WetnessLevel
    handle_looseness: Optional[str] = None


class DryStartRequest(BaseModel):
    umbrella_id: int


class RecheckRequest(BaseModel):
    umbrella_id: int
    recheck_result: RecheckResult


class DeactivateRequest(BaseModel):
    umbrella_id: int
    deactivate_reason: str


class OperationOut(BaseModel):
    id: int
    umbrella_id: int
    operator_id: int
    checkout_time: Optional[datetime] = None
    return_time: Optional[datetime] = None
    wetness: Optional[WetnessLevel] = None
    handle_looseness: Optional[str] = None
    dry_start_time: Optional[datetime] = None
    recheck_result: Optional[RecheckResult] = None
    deactivate_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class InspectionRuleCreate(BaseModel):
    name: str
    zone_id: Optional[int] = None
    interval_minutes: int = 120
    check_wetness: bool = True
    check_handle: bool = True
    check_status: bool = True
    is_active: bool = True
    description: Optional[str] = None


class InspectionRuleUpdate(BaseModel):
    name: Optional[str] = None
    zone_id: Optional[int] = None
    interval_minutes: Optional[int] = None
    check_wetness: Optional[bool] = None
    check_handle: Optional[bool] = None
    check_status: Optional[bool] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class InspectionRuleOut(BaseModel):
    id: int
    name: str
    zone_id: Optional[int] = None
    interval_minutes: int
    check_wetness: bool
    check_handle: bool
    check_status: bool
    is_active: bool
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class UmbrellaFilter(BaseModel):
    zone_id: Optional[int] = None
    shift_id: Optional[int] = None
    status: Optional[UmbrellaStatus] = None
    wetness: Optional[WetnessLevel] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class TurnoverItem(BaseModel):
    umbrella_id: int
    code: str
    turnover_count: int


class TurnoverRanking(BaseModel):
    ranking: List[TurnoverItem]


class PendingRecheckItem(BaseModel):
    umbrella_id: int
    code: str
    color: str
    zone_id: Optional[int] = None
    dry_start_time: Optional[datetime] = None


class PendingRecheckList(BaseModel):
    items: List[PendingRecheckItem]
    total: int


class ZoneAnomalyItem(BaseModel):
    zone_id: int
    zone_name: str
    total_umbrellas: int
    deactivated_count: int
    pending_dry_count: int
    pending_recheck_count: int
    anomaly_rate: float


class ZoneAnomalyStats(BaseModel):
    zones: List[ZoneAnomalyItem]


class InspectionItemCreate(BaseModel):
    umbrella_id: int
    wetness_ok: Optional[bool] = None
    handle_ok: Optional[bool] = None
    status_ok: Optional[bool] = None
    is_anomaly: bool = False
    anomaly_detail: Optional[str] = None


class InspectionItemOut(BaseModel):
    id: int
    record_id: int
    umbrella_id: int
    wetness_ok: Optional[bool] = None
    handle_ok: Optional[bool] = None
    status_ok: Optional[bool] = None
    is_anomaly: bool
    anomaly_detail: Optional[str] = None

    model_config = {"from_attributes": True}


class InspectionExecute(BaseModel):
    rule_id: int
    items: List[InspectionItemCreate]
    notes: Optional[str] = None


class InspectionRecordOut(BaseModel):
    id: int
    rule_id: int
    zone_id: Optional[int] = None
    inspector_id: int
    inspected_at: datetime
    total_checked: int
    anomaly_count: int
    notes: Optional[str] = None
    items: List[InspectionItemOut] = []

    model_config = {"from_attributes": True}


class InspectionRuleWithLastInspect(InspectionRuleOut):
    last_inspected_at: Optional[datetime] = None
    is_due: bool = False
