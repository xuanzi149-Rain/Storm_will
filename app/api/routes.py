from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.support import answer
from app.services.schools import beijing_schools

router = APIRouter()


class QueryRequest(BaseModel):
    school: str = ""
    question: str = Field(min_length=1, max_length=2000)
    attempts: str = Field(default="", max_length=2000)


class Source(BaseModel):
    title: str
    page: Optional[int] = None
    authority: str
    url: str = ""


class QueryResponse(BaseModel):
    status: str
    category: str
    answer: str
    sources: list[Source]
    repair_summary: str


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    try:
        return QueryResponse(**answer(request.question, request.attempts, request.school))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/schools", response_model=list[str])
def schools():
    return list(beijing_schools())
