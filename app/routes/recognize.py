import asyncio
import io
import os
import uuid
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Depends, Form
from sqlalchemy.orm import Session
import face_recognition
import numpy as np
import cv2

from app.database import get_db
from app.models.user import User
from app.models.attendance import Attendance
from app.models.visitor import Visitor
from app.models.meeting import Meeting
from app.models.organization import Admin
from app.auth import get_current_admin

router = APIRouter(tags=["Recognition"])

UNKNOWN_FACES_DIR = Path("app/static/unknown_faces")
UNKNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)


def _recognize_faces(
    image_data: bytes,
    known_encodings: list[np.ndarray],
    known_names: list[str],
    known_photos: list[str],
    visitor_encodings: list[np.ndarray],
    visitor_ids: list[int],
    org_id: int,
):
    """
    Face recognition with bounding boxes drawn on the image.
    Returns annotated JPEG bytes + per-face detail list.
    """
    image = face_recognition.load_image_file(io.BytesIO(image_data))
    locations = face_recognition.face_locations(image)
    encodings = face_recognition.face_encodings(image, locations)
    h, w = image.shape[:2]

    faces = []
    annotated = image.copy()

    for encoding, (top, right, bottom, left) in zip(encodings, locations):
        face_info = {
            "box": {"top": top, "right": right, "bottom": bottom, "left": left},
            "box_pct": {
                "top": round(top / h * 100, 2),
                "right": round(right / w * 100, 2),
                "bottom": round(bottom / h * 100, 2),
                "left": round(left / w * 100, 2),
            },
        }

        matched = False
        if known_encodings:
            distances = face_recognition.face_distance(known_encodings, encoding)
            best_idx = int(np.argmin(distances))
            if distances[best_idx] <= 0.5:
                face_info["type"] = "member"
                face_info["name"] = known_names[best_idx]
                face_info["confidence"] = round(1.0 - float(distances[best_idx]), 2)
                face_info["photo"] = known_photos[best_idx] or ""
                matched = True
                cv2.rectangle(annotated, (left, top), (right, bottom), (37, 211, 102), 2)
                label = known_names[best_idx]
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(annotated, (left, top - th - 10), (left + tw + 6, top), (37, 211, 102), -1)
                cv2.putText(annotated, label, (left + 3, top - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        if not matched:
            visitor_match_id = None
            if visitor_encodings:
                v_dists = face_recognition.face_distance(visitor_encodings, encoding)
                v_best = int(np.argmin(v_dists))
                if v_dists[v_best] <= 0.55:
                    visitor_match_id = visitor_ids[v_best]

            pad = 20
            crop_t, crop_b = max(0, top - pad), min(h, bottom + pad)
            crop_l, crop_r = max(0, left - pad), min(w, right + pad)
            face_crop = image[crop_t:crop_b, crop_l:crop_r]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"visitor_{org_id}_{ts}_{uuid.uuid4().hex[:6]}.jpg"
            cv2.imwrite(str(UNKNOWN_FACES_DIR / filename),
                        cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR))

            face_info["type"] = "visitor"
            face_info["name"] = "Unknown"
            face_info["face_crop"] = f"/static/unknown_faces/{filename}"
            face_info["_encoding"] = encoding.tobytes()
            face_info["visitor_match_id"] = visitor_match_id

            cv2.rectangle(annotated, (left, top), (right, bottom), (255, 159, 10), 2)
            (tw, th), _ = cv2.getTextSize("NEW?", cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(annotated, (left, top - th - 10), (left + tw + 6, top), (255, 159, 10), -1)
            cv2.putText(annotated, "NEW?", (left + 3, top - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        faces.append(face_info)

    annotated_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
    _, buf = cv2.imencode(".jpg", annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes(), faces


@router.post("/recognize")
async def recognize_face(
    file: UploadFile = File(...),
    meeting_id: Optional[int] = Form(None),
    admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Recognize faces, draw bounding boxes, capture unknown visitors."""
    image_data = await file.read()

    # Resolve meeting if provided
    meeting = None
    meeting_name = None
    if meeting_id:
        meeting = db.query(Meeting).filter(
            Meeting.id == meeting_id, Meeting.org_id == admin.org_id
        ).first()
        if meeting:
            meeting_name = meeting.name

    users = db.query(User).filter(User.org_id == admin.org_id).all()
    known_encodings, known_names, known_photos = [], [], []
    for u in users:
        enc = np.frombuffer(u.face_embedding, dtype=np.float64)
        if np.any(enc != 0):
            known_encodings.append(enc)
            known_names.append(u.name)
            known_photos.append(u.profile_photo)

    visitors = db.query(Visitor).filter(Visitor.org_id == admin.org_id).all()
    visitor_encodings, visitor_ids = [], []
    for v in visitors:
        if v.face_embedding:
            visitor_encodings.append(np.frombuffer(v.face_embedding, dtype=np.float64))
            visitor_ids.append(v.id)

    annotated_jpg, faces = await asyncio.to_thread(
        _recognize_faces, image_data,
        known_encodings, known_names, known_photos,
        visitor_encodings, visitor_ids, admin.org_id,
    )

    recognized_members = []
    member_photo_map = {}  # name -> profile_photo
    new_visitors = []

    for face in faces:
        if face["type"] == "member":
            if face["name"] not in recognized_members:
                recognized_members.append(face["name"])
                member_photo_map[face["name"]] = face.get("photo", "")
        elif face["type"] == "visitor":
            raw_enc = face.pop("_encoding", None)
            vmid = face.get("visitor_match_id")
            if vmid:
                v = db.query(Visitor).filter(Visitor.id == vmid).first()
                if v:
                    v.visit_count += 1
                    v.last_seen = datetime.utcnow()
                    new_visitors.append({
                        "id": v.id, "face_photo": v.face_photo,
                        "label": v.label, "visit_count": v.visit_count,
                        "is_returning": True,
                    })
            else:
                v = Visitor(
                    org_id=admin.org_id,
                    face_photo=face["face_crop"],
                    face_embedding=raw_enc,
                )
                db.add(v)
                db.flush()
                new_visitors.append({
                    "id": v.id, "face_photo": face["face_crop"],
                    "label": None, "visit_count": 1,
                    "is_returning": False,
                })

    # Only mark attendance for members not already marked today (per meeting)
    already_marked_today = []
    newly_marked = []
    if recognized_members:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for n in recognized_members:
            dup_q = (
                db.query(Attendance)
                .filter(
                    Attendance.org_id == admin.org_id,
                    Attendance.name == n,
                    Attendance.time >= today_start,
                )
            )
            # If a meeting is selected, only check duplicates within that meeting
            if meeting_id:
                dup_q = dup_q.filter(Attendance.meeting_id == meeting_id)
            existing = dup_q.first()

            if existing:
                already_marked_today.append(n)
            else:
                db.add(Attendance(
                    org_id=admin.org_id, name=n, time=now,
                    profile_photo=member_photo_map.get(n, ""),
                    member_type="member",
                    meeting_id=meeting_id if meeting else None,
                    meeting_name=meeting_name,
                ))
                newly_marked.append(n)

    db.commit()

    clean_faces = []
    for f in faces:
        c = {"box": f["box"], "box_pct": f["box_pct"], "type": f["type"], "name": f.get("name", "Unknown")}
        if f["type"] == "member":
            c["confidence"] = f.get("confidence", 0)
            c["photo"] = f.get("photo", "")
        else:
            c["face_crop"] = f.get("face_crop", "")
            c["visitor_match_id"] = f.get("visitor_match_id")
        clean_faces.append(c)

    return {
        "total_faces": len(faces),
        "recognized": [f["name"] for f in faces],
        "attendance_marked": newly_marked,
        "already_marked_today": already_marked_today,
        "annotated_image": base64.b64encode(annotated_jpg).decode("ascii"),
        "faces": clean_faces,
        "new_visitors": new_visitors,
    }
