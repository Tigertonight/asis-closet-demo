"""Private, persistent user feedback and administrator review."""
import io
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from app.auth import get_admin_user, get_optional_user

router = APIRouter(tags=['feedback'])
STORE = Path(__file__).resolve().parents[1] / 'outputs' / 'feedback'


def connect():
    STORE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STORE / 'feedback.sqlite3', timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, user_id TEXT, description TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL, photo BLOB)')
    return db


@router.post('/api/v1/selfit/feedback')
async def submit_feedback(description: str = Form(...), request_id: str = Form(...), source: str = Form(''),
                          photo: UploadFile | None = File(None), user=Depends(get_optional_user)):
    description = description.strip()
    if not 1 <= len(description) <= 2000:
        raise HTTPException(422, '请填写问题说明，最多 2000 字。')
    try:
        request_id = str(uuid.UUID(request_id))
    except ValueError:
        raise HTTPException(422, '提交标识无效，请重新打开反馈页。')
    content = None
    if photo is not None and photo.filename:
        raw = await photo.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(413, '照片不能超过 10MB。')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 25_000_000:
                    raise ValueError()
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1600,1600))
                buffer = io.BytesIO(); image.save(buffer, 'WEBP', quality=90)
                content = buffer.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(422, '请上传有效的 JPG、PNG 或 WebP 照片。')
    user_id = user.get('user_id') if user else None
    # Only retain a screen label, never URL query tokens or personal photo links.
    source = source[:100].split('?')[0]
    db = connect()
    try:
        with db:
            existing = db.execute('SELECT user_id FROM feedback WHERE id=?',(request_id,)).fetchone()
            if existing is not None and existing['user_id'] != user_id:
                raise HTTPException(409, '提交标识已使用，请重新打开反馈页。')
            db.execute('INSERT OR IGNORE INTO feedback VALUES (?,?,?,?,?,?)',
                (request_id,user_id,description,source,datetime.now(timezone.utc).isoformat(),content))
    finally:
        db.close()
    return {'id':request_id, 'message':'反馈已收到，谢谢你的帮助。'}


@router.get('/admin/api/feedback')
def list_feedback(offset: int = Query(0,ge=0), limit: int = Query(30,ge=1,le=100), admin=Depends(get_admin_user)):
    db=connect()
    try:
        total=db.execute('SELECT count(*) FROM feedback').fetchone()[0]
        rows=db.execute('SELECT id,user_id,description,source,created_at,photo IS NOT NULL AS has_photo FROM feedback ORDER BY created_at DESC LIMIT ? OFFSET ?', (limit,offset)).fetchall()
        return {'total':total, 'items':[dict(row) for row in rows]}
    finally:
        db.close()


@router.get('/admin/api/feedback/{feedback_id}/photo')
def feedback_photo(feedback_id: str, admin=Depends(get_admin_user)):
    from fastapi.responses import Response
    db=connect()
    try:
        row=db.execute('SELECT photo FROM feedback WHERE id=?',(feedback_id,)).fetchone()
        if row is None or row['photo'] is None:
            raise HTTPException(404, '没有找到反馈照片。')
        return Response(bytes(row['photo']),media_type='image/webp',headers={'Cache-Control':'private, no-store'})
    finally:
        db.close()
