from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from schemas.auth import Token
from utils.security import create_access_token, verify_password
# from crud import user as crud_user

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # user = await crud_user.get_by_email(db, email=form_data.username)
    # if not user or not verify_password(form_data.password, user.hashed_password):
    #     raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    # Dummy login for structure purposes
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
