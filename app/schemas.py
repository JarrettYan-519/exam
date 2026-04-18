from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    resume: str = Field(..., min_length=10, max_length=20000)
    jd: str = Field(..., min_length=10, max_length=10000)


class OptimizeRequest(AnalyzeRequest):
    analysis: str = Field(..., min_length=10, max_length=20000)


class ParseResponse(BaseModel):
    filename: str
    text: str
