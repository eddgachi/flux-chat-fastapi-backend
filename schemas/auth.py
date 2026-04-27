from pydantic import BaseModel, Field


class OTPRequest(BaseModel):
    phone_number: str = Field(..., pattern="^\\+?[1-9]\\d{1,14}$")


class OTPVerify(BaseModel):
    phone_number: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
