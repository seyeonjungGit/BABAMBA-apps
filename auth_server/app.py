import jwt
import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
# 우리가 만든 db.py와 models.py에서 필요한 것들을 가져옵니다.
from common.database import get_user_by_username, add_user
from common.models import User
from common.redis_config import get_session_redis
# 1. 비밀번호 암호화 도구 설정 (bcrypt 알고리즘 사용)
#pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI()

# Set up Prometheus instrumentation
Instrumentator().instrument(app).expose(app)

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
    # 1. 중복 체크 (DB에 이미 이 아이디가 있는지 확인)
    existing_user = get_user_by_username(req.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")

    # 2. 비밀번호 해싱 (C++의 암호화 함수 호출과 같습니다)
    # 사용자가 친 '1234'를 '$2b$12$...' 형태의 암호문으로 바꿉니다.
    #hashed_password = pwd_context.hash(req.password)

    # 3. DB 객체 생성 및 저장
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

    # 2. Redis(Sentinel)에 세션 저장
    r_session = get_session_redis()
    # 유저 ID를 키로 저장 (토큰 유효기간과 동일하게 1시간 설정)
    r_session.setex(f"session:{user.id}", 3600, "active") 

    return {'token': token}

@app.post('/auth/logout')
async def logout(token: str = Depends(oauth2_scheme)):
    try:
        # 1. 토큰 해독 (Auth Server의 SECRET_KEY 사용)
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("id")
        
        if user_id is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

        # 2. Redis(Sentinel)에서 세션 삭제
        r_session = get_session_redis()
        r_session.delete(f"session:{user_id}")
        
        return {"message": "로그아웃 성공"}
        
    except jwt.ExpiredSignatureError:
        # 이미 만료된 토큰이라도 로그아웃 요청이 들어오면 성공으로 쳐주거나 무시해도 됩니다.
        return {"message": "이미 만료된 세션입니다."}
    except (jwt.PyJWTError, Exception) as e:
        print(f"Logout Error: {e}")
        raise HTTPException(status_code=400, detail="로그아웃 처리 중 오류가 발생했습니다.")