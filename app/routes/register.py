import asyncio
import io
import os

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session
import face_recognition
import numpy as np

from app.database import get_db

IS_VERCEL = os.getenv("VERCEL", "") == "1"
_PHOTO_ROOT = "/tmp" if IS_VERCEL else "app/static"
from app.models.user import User
from app.models.organization import Admin
from app.auth import get_current_admin

router = APIRouter(tags=["Members"])

DUPLICATE_THRESHOLD = 0.45  # Faces closer than this are considered the same person


def _get_face_encodings(image_data: bytes) -> list[np.ndarray]:
    """Blocking function to get face encodings from image data."""
    image = face_recognition.load_image_file(io.BytesIO(image_data))
    return face_recognition.face_encodings(image)


def _check_duplicate_face(encoding: np.ndarray, existing_encodings: list[np.ndarray],
                          existing_names: list[str]) -> str | None:
    """Check if the encoding matches any existing member. Returns name if duplicate."""
    if not existing_encodings:
        return None
    distances = face_recognition.face_distance(existing_encodings, encoding)
    best_idx = int(np.argmin(distances))
    if distances[best_idx] <= DUPLICATE_THRESHOLD:
        return existing_names[best_idx]
    return None


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    name: str = Form(...),
    file: UploadFile = File(...),
    email: str = Form(None),
    phone: str = Form(None),
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Register a new member with their face photo. Checks for duplicate faces."""
    if db.query(User).filter(User.name == name, User.org_id == admin.org_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Member '{name}' already exists.",
        )

    image_data = await file.read()
    face_encodings = await asyncio.to_thread(_get_face_encodings, image_data)

    if len(face_encodings) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No face detected in the uploaded image. Please upload a clear photo.",
        )

    if len(face_encodings) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple faces detected. Please upload a photo with only one face.",
        )

    new_encoding = face_encodings[0]

    # Check for duplicate face across all members in this org
    all_users = db.query(User).filter(User.org_id == admin.org_id).all()
    existing_encodings = []
    existing_names = []
    for u in all_users:
        enc = np.frombuffer(u.face_embedding, dtype=np.float64)
        if np.any(enc != 0):
            existing_encodings.append(enc)
            existing_names.append(u.name)

    dup_name = await asyncio.to_thread(
        _check_duplicate_face, new_encoding, existing_encodings, existing_names
    )
    if dup_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This face closely matches existing member '{dup_name}'. "
                   f"The same face cannot be registered twice with a different name. "
                   f"If this is a twin or different person, please contact an admin to override.",
        )

    import uuid
    photo_dir = f"{_PHOTO_ROOT}/photos/{admin.org_id}"
    os.makedirs(photo_dir, exist_ok=True)
    photo_filename = f"{uuid.uuid4().hex}.jpg"
    photo_path = f"{photo_dir}/{photo_filename}"
    with open(photo_path, "wb") as f:
        f.write(image_data)

    face_embedding = new_encoding.tobytes()
    new_user = User(
        org_id=admin.org_id,
        name=name,
        face_embedding=face_embedding,
        profile_photo=f"/static/photos/{admin.org_id}/{photo_filename}",
        email=email,
        phone=phone,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": f"Member '{name}' registered successfully.", "id": new_user.id}
