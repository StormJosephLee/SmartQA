from fastapi import APIRouter, Depends

from api.deps import get_current_user
from core.errors import unauthorized
from schemas.auth import LoginRequest, TokenResponse, UserInfo
from services.auth_service import AuthUser, authenticate, find_by_name, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="登录获取 JWT")
async def login(payload: LoginRequest) -> TokenResponse:
    user = authenticate(payload.username, payload.password)
    if user is None:
        raise unauthorized("用户名或密码错误")
    token, expires_in = issue_token(user)
    return TokenResponse(access_token=token, token_type="bearer", expires_in=expires_in)


@router.get("/me", response_model=UserInfo, summary="当前用户信息")
async def me(current: AuthUser = Depends(get_current_user)) -> UserInfo:
    db_user = find_by_name(current.name)
    if db_user is None:
        return UserInfo(id=current.id, name=current.name, role=current.role, dept=current.dept)
    return UserInfo(id=db_user.id, name=db_user.name, role=db_user.role, dept=db_user.dept)
