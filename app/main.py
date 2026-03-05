from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import engine, Base
from app.routes import register, recognize, attendance_routes, members, auth_routes, import_routes, visitor_routes, meeting_routes

# Create all DB tables
Base.metadata.create_all(bind=engine)

# Import new models so they get created
from app.models.organization import Organization, Admin  # noqa
from app.models.visitor import Visitor  # noqa
from app.models.meeting import Meeting  # noqa

# Recreate tables including new ones
Base.metadata.create_all(bind=engine)

# Auto-migrate: add new columns to existing tables if they don't exist (SQLite)
import sqlalchemy
with engine.connect() as conn:
    inspector = sqlalchemy.inspect(engine)
    attendance_cols = [c["name"] for c in inspector.get_columns("attendance")]
    if "profile_photo" not in attendance_cols:
        conn.execute(sqlalchemy.text("ALTER TABLE attendance ADD COLUMN profile_photo VARCHAR"))
        conn.commit()
    if "member_type" not in attendance_cols:
        conn.execute(sqlalchemy.text("ALTER TABLE attendance ADD COLUMN member_type VARCHAR DEFAULT 'member'"))
        conn.commit()
    if "meeting_id" not in attendance_cols:
        conn.execute(sqlalchemy.text("ALTER TABLE attendance ADD COLUMN meeting_id INTEGER"))
        conn.commit()
    if "meeting_name" not in attendance_cols:
        conn.execute(sqlalchemy.text("ALTER TABLE attendance ADD COLUMN meeting_name VARCHAR"))
        conn.commit()

app = FastAPI(
    title="@ttend - Smart Attendance System",
    description="AI-powered face recognition attendance system",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_routes.router, prefix="/api")
app.include_router(register.router, prefix="/api")
app.include_router(recognize.router, prefix="/api")
app.include_router(attendance_routes.router, prefix="/api")
app.include_router(members.router, prefix="/api")
app.include_router(import_routes.router, prefix="/api")
app.include_router(visitor_routes.router, prefix="/api")
app.include_router(meeting_routes.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Church Attendance System is running"}


@app.get("/")
async def landing():
    return FileResponse("app/static/landing.html")


@app.get("/app")
async def dashboard():
    return FileResponse("app/static/app.html")


# Mount static files last
app.mount("/static", StaticFiles(directory="app/static"), name="static")

