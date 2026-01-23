import jwt
import datetime
from fastapi import FastAPI, HTTPException, Depends, Body  # Body 추가
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # Field 추가
from prometheus_fastapi_instrumentator import Instrumentator
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from common.database import get_user_by_username, add_user
from common.models import User
from common.redis_config import get_session_redis

app = FastAPI()

# Prometheus 설정 (그대로 유지)
Instrumentator().instrument(app).expose(app)

# --- [수정 1] CORS 설정 최적화 ---
# 테스트 단계에서는 "*"로 열어두는 것이 가장 확실합니다.
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

# --- [수정 2] 데이터 모델 정의 (Optional 필드 명시) ---
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    # 기본값을 None으로 명시하고 타입을 확실히 합니다.
    full_name: str | None = None 
    email: str | None = None

# --- [수정 3] 회원가입 API (Body 명시) ---
@app.post('/auth/register')
async def register(req: RegisterRequest = Body(...)): # Body(...)를 써서 강제로 바디에서 읽게 함
    # 중복 체크
    existing_user = get_user_by_username(req.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

    # DB 저장 (req.full_name 등이 None이어도 User 모델에서 처리됨)
    new_user_data = User(
        username=req.username,
        password=req.password,
        full_name=req.full_name,
        email=req.email
    )
    
    saved_user = add_user(new_user_data)
    
    return {"message": "회원가입 성공!", "id": saved_user.id}

# --- [API 2] 로그인 (Login - 그대로 유지) ---
@app.post('/auth/login')
async def login(req: LoginRequest = Body(...)):
    user = get_user_by_username(req.username)
    if not user or req.password != user.password:
        raise HTTPException(status_code=401, detail="인증 실패")

    payload = {
        'user': user.username,
        'id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

    r_session = get_session_redis()
    r_session.setex(f"session:{user.id}", 3600, "active") 

    return {'token': token}

# --- [API 3] 로그아웃 (Logout - 그대로 유지) ---
@app.post('/auth/logout')
async def logout(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("id")
        
        if user_id is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        r_session = get_session_redis()
        r_session.delete(f"session:{user_id}")
        
        return {"message": "로그아웃 성공!!"}
        
    except jwt.ExpiredSignatureError:
        return {"message": "이미 만료된 세션입니다."}
    except (jwt.PyJWTError, Exception) as e:
        print(f"Logout Error: {e}")
        raise HTTPException(status_code=400, detail="로그아웃 처리 중 오류가 발생했습니다.")
