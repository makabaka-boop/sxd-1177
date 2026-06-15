from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import engine, Base, SessionLocal
from models import User, UserRole
from auth import get_password_hash
from routers import auth, admin, operations, stats, repair, transfer


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    existing = db.query(User).filter(User.username == "admin").first()
    if not existing:
        admin_user = User(
            username="admin",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.admin,
        )
        db.add(admin_user)
        db.commit()
    db.close()
    yield


app = FastAPI(
    title="景区雨伞管理系统 API",
    description="管理景区临时借用雨伞的领出、归还、晾干和复查过程",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(operations.router)
app.include_router(stats.router)
app.include_router(repair.router)
app.include_router(transfer.admin_router)
app.include_router(transfer.ops_router)


@app.get("/")
def root():
    return {"message": "景区雨伞管理系统 API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8111, reload=True)
