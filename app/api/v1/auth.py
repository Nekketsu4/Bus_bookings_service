from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit_auth
from app.core.security import hash_password, verify_password, create_access_token
from app.db.database import get_db
from app.repositories.user_repo import UserRepository
from app.schemas.user_schemas import UserOut, UserRegister, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    dependencies=[Depends(rate_limit_auth)],
)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user_data = payload.model_dump(exclude={"password"})
    user_data["hashed_password"] = hash_password(payload.password)
    user = await repo.create(**user_data)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Obtain JWT token",
    dependencies=[Depends(rate_limit_auth)],
)
async def login(
    payload: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    repo = UserRepository(db)
    user = await repo.get_by_email(payload.username)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive"
        )
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)
