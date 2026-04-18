from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AnalyzeRequest(BaseModel):
    resume: str = Field(..., min_length=10, max_length=20000)
    jd: str = Field(..., min_length=10, max_length=10000)


class OptimizeRequest(AnalyzeRequest):
    analysis: str = Field(..., min_length=10, max_length=20000)


class ParseResponse(BaseModel):
    filename: str
    text: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=5000)


class RefineRequest(BaseModel):
    mode: Literal["analysis", "resume"]
    resume: str = Field(min_length=10, max_length=20000)
    jd: str = Field(min_length=10, max_length=10000)
    analysis: str | None = Field(default=None, max_length=20000)
    current_content: str = Field(min_length=10, max_length=20000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)
    instruction: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def resume_mode_requires_analysis(self):
        if self.mode == "resume" and not self.analysis:
            raise ValueError("analysis is required when mode is 'resume'")
        return self
