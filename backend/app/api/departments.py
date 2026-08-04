from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core.database import supabase

router = APIRouter(prefix="/departments", tags=["departments"])


class DepartmentCreate(BaseModel):
    name: str
    keywords: List[str] = []


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    keywords: Optional[List[str]] = None


@router.get("")
def list_departments():
    result = supabase.table("departments").select("*").order("name").execute()
    return result.data


@router.post("", status_code=201)
def create_department(body: DepartmentCreate):
    result = supabase.table("departments").insert({
        "name": body.name,
        "keywords": body.keywords,
    }).execute()
    return result.data[0]


@router.put("/{dept_id}")
def update_department(dept_id: str, body: DepartmentUpdate):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")
    result = supabase.table("departments").update(patch).eq("id", dept_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")
    return result.data[0]


@router.delete("/{dept_id}", status_code=204)
def delete_department(dept_id: str):
    supabase.table("departments").delete().eq("id", dept_id).execute()
