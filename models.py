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
