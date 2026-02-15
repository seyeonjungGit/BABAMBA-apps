import jwt
import datetime
import os
import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.security import OAuth2PasswordBearer
from common import config
# DB 관련 모듈 (기존 파일 유지)
from common.database import get_user_by_username, add_user
from common.models import User

# 로깅 설정
logger = logging.getLogger(__name__)

app = FastAPI()

# Prometheus 설정
Instrumentator().instrument(app).expose(app)

# CORS 설정
origins = [
    "https://yxngjxe.store",
    "https://ehanadul.store",
    "https://yongun.shop"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth/Employee 간 JWT 발급/검증 불일치 방지를 위해 공통 설정을 사용합니다.
# (환경변수 JWT_SECRET_KEY가 있으면 그 값을 사용하고, 없으면 dev-jwt-secret 기본값)
SECRET_KEY = config.JWT_SECRET_KEY
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- 데이터 모델 정의 ---
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str = None
    email: str = None

# --- [API 1] 회원가입 (Register) ---
@app.post('/auth/register')
async def register(req: RegisterRequest):
    # 1. 중복 체크
    existing_user = get_user_by_username(req.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

    # 2. DB 객체 생성 및 저장 (비밀번호는 현재 평문 저장 방식 유지)
    new_user_data = User(
        username=req.username,
        password=req.password,
        full_name=req.full_name,
        email=req.email
    )
    
    saved_user = add_user(new_user_data)
    return {"message": "회원가입 성공!", "id": saved_user.id}

# --- [API 2] 로그인 (Login) ---
@app.post('/auth/login')
async def login(req: LoginRequest):
    # 1. 사용자 확인
    user = get_user_by_username(req.username)
    if not user or req.password != user.password:
        raise HTTPException(status_code=401, detail="인증 실패")

    # 2. JWT 토큰 생성
    payload = {
        'user': user.username,
        'id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # Redis 세션 저장 로직 삭제 (타임아웃 원인 제거)
    logger.info(f"[Auth] User {user.username} logged in successfully (JWT only).")

    return {'token': token}

# --- [API 3] 로그아웃 (Logout) ---
@app.post('/auth/logout')
async def logout(token: str = Depends(oauth2_scheme)):
    try:
        # 토큰 유효성만 검사 (Redis 세션 삭제 로직 제거)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")

        if user_id is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        return {"message": "로그아웃 성공"}

    except jwt.ExpiredSignatureError:
        return {"message": "이미 만료된 토큰입니다."}
    except jwt.PyJWTError as e:
        logger.error(f"[Logout Error] {e}")
        raise HTTPException(status_code=400, detail="로그아웃 처리 중 오류가 발생했습니다.")

# --- [API 4] 헬스체크 ---
@app.get("/health")
def health():
    return {"status": "ok"}