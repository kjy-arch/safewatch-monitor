from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from app.core.database import supabase
from app.services.batch.doc_service import (
    extract_text_from_pdf,
    extract_text_from_url,
    save_official_doc,
)

router = APIRouter(prefix="/docs", tags=["docs"])


@router.post("", status_code=201)
async def upload_doc(
    title: str = Form(...),
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="파일 또는 URL 중 하나는 필수입니다.")

    if file:
        content_bytes = await file.read()
        try:
            content = extract_text_from_pdf(content_bytes)
        except Exception:
            raise HTTPException(status_code=422, detail="PDF 파싱에 실패했습니다.")
        if not content.strip():
            raise HTTPException(status_code=422, detail="PDF에서 텍스트를 추출할 수 없습니다.")
        doc = save_official_doc(title, "pdf", content, file.filename)
    else:
        try:
            content = extract_text_from_url(url)
        except Exception:
            raise HTTPException(status_code=422, detail=f"URL 내용을 가져올 수 없습니다: {url}")
        doc = save_official_doc(title, "url", content, url)

    return {
        "id": doc["id"],
        "title": doc["title"],
        "doc_type": doc["doc_type"],
        "source": doc["source"],
        "content_length": len(content),
        "message": f"공식 문서 등록 완료 ({len(content)}자 추출)",
    }


@router.get("")
def list_docs():
    result = supabase.table("official_docs").select(
        "id, title, doc_type, source, created_at"
    ).order("created_at", desc=True).execute()
    return result.data


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: str):
    supabase.table("official_docs").delete().eq("id", doc_id).execute()
