"""API 请求/响应模型"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    project_id: str = Field(..., min_length=1, description="项目ID")


class SubChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    project_id: str = Field(..., min_length=1, description="项目ID")
    section_name: str = Field(..., min_length=1, description="章节名称")
    content: str = Field("", description="当前章节内容")


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="项目名称")
    topic: str = Field("", max_length=500, description="研究主题")


class SectionCreate(BaseModel):
    project_id: str = Field(..., min_length=1, description="项目ID")
    name: str = Field(..., min_length=1, max_length=100, description="章节名称")


class SectionUpdate(BaseModel):
    content: str = Field(..., description="章节内容")


class ExtractionRequest(BaseModel):
    project_id: str = Field(..., min_length=1, description="项目ID")
    fields: list[str] = Field(..., min_length=1, description="提取字段列表")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="搜索查询")


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="TTS文本")


class FieldsRequest(BaseModel):
    fields: list[str] = Field(..., min_length=1, description="字段列表")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class ApiKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1, description="API Key")


class ApiKeyVerifyRequest(BaseModel):
    api_key: str = Field(..., min_length=1, description="API Key")
    provider: str = Field("zhipu", description="供应商 ID")
    base_url: str = Field("", description="自定义 Base URL")
