import jwt
import datetime
from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi.security import OAuth2PasswordBearer
# 공통 모듈 임포트
from common.database import get_user_by_username, add_user
from common.models import User
from common.redis_config import get_session_redis

app = FastAPI()

# Prometheus 설정 (정상 작동 확인)
Instrumentator().instrument(app).expose(app)

# CORS 설정: 브라우저 404/422 방지를 위해 모든 경로 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = 'dev-jwt-secret'
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- 데이터 모델 정의 (가장 안전한 구버전 문법 사용) ---
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str = None  # None 기본값 할당 (Optional 대신 모든 파이썬 버전 호환)
    email: str = None

# --- [API 1] 회원가입 (Register) ---
@app.post('/auth/register')
async def register(req: RegisterRequest = Body(...)): # Body(...) 명시로 422 에러 강제 해결
    # 1. 중복 체크
    existing_user = get_user_by_username(req.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

    # 2. DB 객체 생성 및 저장
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
async def login(req: LoginRequest = Body(...)):
    user = get_user_by_username(req.username)
    if not user or req.password != user.password:
        raise HTTPException(status_code=401, detail="인증 실패")

    # 1. JWT 토큰 발행
    payload = {
        'user': user.username,
        'id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    # 2. Redis에 세션 저장
    r_session = get_session_redis()
    r_session.setex(f"session:{user.id}", 3600, "active") 

    return {'token': token}

# --- [API 3] 로그아웃 (Logout) ---
@app.post('/auth/logout')
async def logout(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("id")
        
        if user_id is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        r_session = get_session_redis()
        r_session.delete(f"session:{user_id}")
        return {"message": "로그아웃 성공!"}
        
    except Exception as e:
        print(f"Logout Error: {e}")
        raise HTTPException(status_code=400, detail="로그아웃 처리 중 오류 발생")
