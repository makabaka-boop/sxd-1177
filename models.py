import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    staff = "staff"


class UmbrellaStatus(str, enum.Enum):
    pending = "pending"
    in_use = "in_use"
    pending_dry = "pending_dry"
    pending_recheck = "pending_recheck"
    available = "available"
    deactivated = "deactivated"


class WetnessLevel(str, enum.Enum):
    dry = "dry"
    slight = "slight"
    moderate = "moderate"
    heavy = "heavy"


class RecheckResult(str, enum.Enum):
    passed = "passed"
    failed = "failed"


class RepairSourceType(str, enum.Enum):
    inspection = "inspection"
    staff_deactivate = "staff_deactivate"
    recheck_failed = "recheck_failed"


class RepairStatus(str, enum.Enum):
    pending = "pending"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    closed = "closed"


class RepairResult(str, enum.Enum):
    fixed = "fixed"
    scrapped = "scrapped"
    cannot_repair = "cannot_repair"


class TransferStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.staff)
    is_active = Column(Boolean, default=True)

    operations = relationship("UmbrellaOperation", back_populates="operator")


class UmbrellaZone(Base):
    __tablename__ = "umbrella_zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    umbrellas = relationship("Umbrella", back_populates="zone")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)
    description = Column(Text, nullable=True)

    umbrellas = relationship("Umbrella", back_populates="shift")


class Umbrella(Base):
    __tablename__ = "umbrellas"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    color = Column(String(50), nullable=False)
    zone_id = Column(Integer, ForeignKey("umbrella_zones.id"), nullable=True)
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    status = Column(Enum(UmbrellaStatus), nullable=False, default=UmbrellaStatus.pending)
    estimated_dry_minutes = Column(Integer, nullable=True, default=60)
    deactivate_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)

    zone = relationship("UmbrellaZone", back_populates="umbrellas")
    shift = relationship("Shift", back_populates="umbrellas")
    operations = relationship("UmbrellaOperation", back_populates="umbrella", order_by="UmbrellaOperation.id.desc()")


class UmbrellaOperation(Base):
    __tablename__ = "umbrella_operations"

    id = Column(Integer, primary_key=True, index=True)
    umbrella_id = Column(Integer, ForeignKey("umbrellas.id"), nullable=False, index=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    checkout_time = Column(DateTime, nullable=True)
    return_time = Column(DateTime, nullable=True)
    wetness = Column(Enum(WetnessLevel), nullable=True)
    handle_looseness = Column(Text, nullable=True)
    dry_start_time = Column(DateTime, nullable=True)
    recheck_result = Column(Enum(RecheckResult), nullable=True)
    deactivate_reason = Column(Text, nullable=True)

    umbrella = relationship("Umbrella", back_populates="operations")
    operator = relationship("User", back_populates="operations")


class InspectionRule(Base):
    __tablename__ = "inspection_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    zone_id = Column(Integer, ForeignKey("umbrella_zones.id"), nullable=True)
    interval_minutes = Column(Integer, nullable=False, default=120)
    check_wetness = Column(Boolean, default=True)
    check_handle = Column(Boolean, default=True)
    check_status = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    zone = relationship("UmbrellaZone")
    records = relationship("InspectionRecord", back_populates="rule")


class InspectionRecord(Base):
    __tablename__ = "inspection_records"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("inspection_rules.id"), nullable=False)
    zone_id = Column(Integer, ForeignKey("umbrella_zones.id"), nullable=True)
    inspector_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    inspected_at = Column(DateTime, nullable=False)
    total_checked = Column(Integer, default=0)
    anomaly_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)

    rule = relationship("InspectionRule", back_populates="records")
    zone = relationship("UmbrellaZone")
    inspector = relationship("User")
    items = relationship("InspectionItem", back_populates="record", cascade="all, delete-orphan")


class InspectionItem(Base):
    __tablename__ = "inspection_items"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, ForeignKey("inspection_records.id"), nullable=False)
    umbrella_id = Column(Integer, ForeignKey("umbrellas.id"), nullable=False)
    wetness_ok = Column(Boolean, nullable=True)
    handle_ok = Column(Boolean, nullable=True)
    status_ok = Column(Boolean, nullable=True)
    is_anomaly = Column(Boolean, default=False)
    anomaly_detail = Column(Text, nullable=True)

    record = relationship("InspectionRecord", back_populates="items")
    umbrella = relationship("Umbrella")


class RepairOrder(Base):
    __tablename__ = "repair_orders"

    id = Column(Integer, primary_key=True, index=True)
    umbrella_id = Column(Integer, ForeignKey("umbrellas.id"), nullable=False, index=True)
    source_type = Column(Enum(RepairSourceType), nullable=False)
    anomaly_description = Column(Text, nullable=False)
    status = Column(Enum(RepairStatus), nullable=False, default=RepairStatus.pending)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    handler_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    handle_remark = Column(Text, nullable=True)
    repair_result = Column(Enum(RepairResult), nullable=True)

    umbrella = relationship("Umbrella")
    creator = relationship("User", foreign_keys=[creator_id])
    handler = relationship("User", foreign_keys=[handler_id])


class TransferOrder(Base):
    __tablename__ = "transfer_orders"

    id = Column(Integer, primary_key=True, index=True)
    umbrella_id = Column(Integer, ForeignKey("umbrellas.id"), nullable=False, index=True)
    from_zone_id = Column(Integer, ForeignKey("umbrella_zones.id"), nullable=True)
    to_zone_id = Column(Integer, ForeignKey("umbrella_zones.id"), nullable=False)
    from_shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True)
    to_shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(Enum(TransferStatus), nullable=False, default=TransferStatus.pending)
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    umbrella = relationship("Umbrella")
    from_zone = relationship("UmbrellaZone", foreign_keys=[from_zone_id])
    to_zone = relationship("UmbrellaZone", foreign_keys=[to_zone_id])
    from_shift = relationship("Shift", foreign_keys=[from_shift_id])
    to_shift = relationship("Shift", foreign_keys=[to_shift_id])
    creator = relationship("User", foreign_keys=[creator_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
