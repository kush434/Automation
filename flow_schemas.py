from pydantic import BaseModel, Field
class ClickRequest(BaseModel):
    x: int = Field(ge=0, le=5000)
    y: int = Field(ge=0, le=5000)
class TypeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
class KeyRequest(BaseModel):
    key: str = Field(min_length=1, max_length=40)
class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
