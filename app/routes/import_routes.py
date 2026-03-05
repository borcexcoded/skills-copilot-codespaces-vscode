"""Bulk import routes – CSV and file-based member registration."""

import csv
import io
import os
import uuid
import asyncio

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import face_recognition
import numpy as np

from app.database import get_db
from app.models.user import User
from app.models.organization import Admin
from app.auth import get_current_admin

router = APIRouter(tags=["Import"])


def _encode_face(image_data: bytes) -> np.ndarray | None:
    """Get first face encoding from image bytes."""
    try:
        image = face_recognition.load_image_file(io.BytesIO(image_data))
        encodings = face_recognition.face_encodings(image)
        return encodings[0] if encodings else None
    except Exception:
        return None


@router.post("/members/import-csv")
async def import_members_csv(
    file: UploadFile = File(...),
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Import members from CSV.
    CSV must have a 'name' column. Optional columns: email, phone.
    Members imported via CSV won't have face data until a photo is uploaded.
    """
    content = await file.read()
    text = content.decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))

    imported = []
    skipped = []
    errors = []

    for i, row in enumerate(reader, start=2):
        name = (row.get("name") or row.get("Name") or "").strip()
        if not name:
            errors.append(f"Row {i}: missing name")
            continue

        email = (row.get("email") or row.get("Email") or "").strip() or None
        phone = (row.get("phone") or row.get("Phone") or "").strip() or None

        # Check duplicate
        if db.query(User).filter(User.name == name, User.org_id == admin.org_id).first():
            skipped.append(name)
            continue

        # Create a dummy 128-d zero encoding (placeholder – needs photo later)
        dummy_encoding = np.zeros(128, dtype=np.float64).tobytes()

        user = User(
            org_id=admin.org_id,
            name=name,
            face_embedding=dummy_encoding,
            email=email,
            phone=phone,
        )
        db.add(user)
        imported.append(name)

    db.commit()

    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "errors": len(errors),
        "imported_names": imported,
        "skipped_names": skipped,
        "error_details": errors,
    }


@router.get("/members/export-csv")
def export_members_csv(admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Export members as CSV."""
    from fastapi.responses import StreamingResponse
    from datetime import datetime

    users = db.query(User).filter(User.org_id == admin.org_id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Phone"])
    for u in users:
        writer.writerow([u.id, u.name, u.email or "", u.phone or ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=members_{datetime.utcnow().strftime('%Y%m%d')}.csv"},
    )


@router.post("/members/{member_id}/photo")
async def update_member_photo(
    member_id: int,
    file: UploadFile = File(...),
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Upload/update a member's face photo and re-encode their face."""
    user = db.query(User).filter(User.id == member_id, User.org_id == admin.org_id).first()
    if not user:
        raise HTTPException(404, "Member not found")

    image_data = await file.read()
    encoding = await asyncio.to_thread(_encode_face, image_data)
    if encoding is None:
        raise HTTPException(400, "No face detected in the photo")

    photo_dir = f"app/static/photos/{admin.org_id}"
    os.makedirs(photo_dir, exist_ok=True)
    photo_filename = f"{uuid.uuid4().hex}.jpg"
    photo_path = f"{photo_dir}/{photo_filename}"
    with open(photo_path, "wb") as f:
        f.write(image_data)

    user.face_embedding = encoding.tobytes()
    user.profile_photo = f"/static/photos/{admin.org_id}/{photo_filename}"
    db.commit()

    return {"message": f"Photo updated for {user.name}", "profile_photo": user.profile_photo}
