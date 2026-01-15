import os # 운영체제 기능(파일 경로 등)을 위한 모듈 ###
import jwt # JWT(JSON Web Token) 처리를 위한 라이브러리 (PyJWT)
import time # 시간 측정을 위한 모듈
import json
from typing import List, Optional # 타입 힌트를 위한 모듈
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status # FastAPI 프레임워크 관련 모듈
from fastapi.middleware.cors import CORSMiddleware # CORS(교차 출처 리소스 공유) 미들웨어
from fastapi.responses import JSONResponse # JSON 응답을 위한 모듈
from fastapi.routing import APIRoute # API 라우팅을 위한 모듈
from fastapi.staticfiles import StaticFiles # 정적 파일 제공을 위한 모듈
from pydantic import BaseModel # 데이터 유효성 검사를 위한 Pydantic 모델
from fastapi.security import OAuth2PasswordBearer # OAuth2 Bearer 토큰 인증을 위한 모듈
from prometheus_fastapi_instrumentator import Instrumentator
import httpx # 비동기 HTTP 요청을 위한 라이브러리

from common import config   # import common.config 대신
from common import database # import common.database 대신
import util 
from common.models import Employee, EmployeePublic, EmployeesListResponse 
from common.redis_config import get_cache_redis, get_session_redis

app = FastAPI() # FastAPI 애플리케이션 인스턴스 생성

# Set up Prometheus instrumentation
Instrumentator().instrument(app).expose(app)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 출처 허용
    allow_credentials=True, # 자격 증명(쿠키, HTTP 인증 등) 허용
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 HTTP 헤더 허용
)

# JWT 인증 의존성 설정
SECRET_KEY = config.JWT_SECRET_KEY
ALGORITHM = "HS256" # JWT 서명 알고리즘
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# httpx 클라이언트 초기화
client = httpx.AsyncClient()


@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

async def get_current_user_info(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 1. JWT 토큰 해독
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("user")
        user_id: int = payload.get("id")

        # 2. Redis 세션 존재 여부 확인 (Sentinel)
        r_session = get_session_redis() 
        if not r_session.exists(f"session:{user_id}"):
            raise HTTPException(status_code=401, detail="로그아웃된 세션입니다. 다시 로그인하세요.")

        # 3. 유저 정보 유효성 검사
        if username is None or user_id is None:
            raise credentials_exception
            
        return {"username": username, "id": user_id}
        
    except (jwt.ExpiredSignatureError, jwt.PyJWTError):
        raise credentials_exception

def get_photo_url_for_fastapi(object_key: str):
    return f"/static/uploads/{object_key}"

@app.on_event("startup")
async def on_startup():
    """앱 시작 시 데이터베이스 테이블이 생성되도록 합니다."""
    database.create_db_and_tables()

@app.get("/employees", response_model=EmployeesListResponse)
async def get_employees(user: dict = Depends(get_current_user_info)):
    """모든 직원의 목록을 JSON 배열로 반환합니다. (Redis 캐싱 적용)"""
    start_time = time.time()
    r = get_cache_redis()

    user_id = user["id"]
    cache_key = f"employees_list_cache:{user_id}"

   # 1. Redis 캐시 확인
    cached_data = r.get(cache_key)
    if cached_data:
        execution_time = (time.time() - start_time) * 1000
        print(f"🚀 Redis Cache Hit for User {user_id}: in {execution_time:.2f} ms")
        return json.loads(cached_data)

    # 2. 캐시 없으면 DB 조회 (수정된 database.list_employees 함수 사용 필요)
    # database.py에서 list_employees(owner_id=user_id) 로 수정되어야 함
    employees: List[Employee] = database.list_employees(owner_id=user_id)
    
    employees_public_data = []
    for employee in employees:
        emp_public = EmployeePublic.from_orm(employee)
        if employee.object_key:
            emp_public.photo_url = get_photo_url_for_fastapi(employee.object_key)
        employees_public_data.append(emp_public)
    
    # 3. Redis에 유저별 결과 저장
    r.setex(cache_key, 300, json.dumps([e.dict() for e in employees_public_data]))

    execution_time = (time.time() - start_time) * 1000
    print(f"🐌 DB Query (Cache Miss) for User {user_id}: in {execution_time:.2f} ms")
    return employees_public_data

@app.get("/employee/{employee_id}", response_model=EmployeePublic, responses={404: {"description": "Employee not found"}})
async def get_employee(employee_id: int):
    """단일 직원 조회 (Redis 캐싱 적용)"""
    start_time = time.time()
    r = get_cache_redis()
    cache_key = f"emp_cache:{employee_id}"

    # 1. Redis 확인
    cached_emp = r.get(cache_key)
    if cached_emp:
        execution_time = (time.time() - start_time) * 1000
        print(f"🚀 Redis Cache Hit: get_employee({employee_id}) in {execution_time:.2f} ms")
        return json.loads(cached_emp)

    # 2. DB 조회
    employee: Optional[Employee] = database.load_employee(employee_id)
    if employee:
        emp_public = EmployeePublic.from_orm(employee)
        if employee.object_key:
            emp_public.photo_url = get_photo_url_for_fastapi(employee.object_key)
        
        # 3. 캐시에 저장
        r.setex(cache_key, 600, json.dumps(emp_public.dict()))
        return emp_public
    
    raise HTTPException(status_code=404, detail="Employee not found")

@app.post("/employee", response_model=Employee)
async def save_employee(
    full_name: str = Form(...),
    location: str = Form(...),
    job_title: str = Form(...),
    badges: str = Form(""),
    employee_id: Optional[int] = Form(None),
    photo: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user_info)
):

    user_id = user["id"]
    r = get_cache_redis()
    user_list_cache = f"employees_list_cache:{user_id}"

    key = None
    if photo and photo.filename != '':
        # 이미지 업로드 로직 (기존과 동일)
        image_bytes = util.resize_image(photo.file, (120, 160))
        if image_bytes:
            try:
                files = {'file': (photo.filename, image_bytes, photo.content_type)}
                response = await client.post(f"{config.PHOTO_SERVICE_URL}/upload", files=files)
                response.raise_for_status()
                upload_result = response.json()
                key = upload_result.get("object_key")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Could not upload image: {e}")

    # [수정] Employee 객체 생성 시 owner_id 명시
    employee_data = Employee(
        id=employee_id,
        object_key=key,
        full_name=full_name,
        location=location,
        job_title=job_title,
        badges=badges,
        owner_id=user_id # 현재 로그인한 유저를 주인으로 설정
    )

    if employee_id:
        # 수정 로직
        if key:
            old_employee = database.load_employee(employee_id)
            if old_employee and old_employee.object_key:
                try: await client.delete(f"{config.PHOTO_SERVICE_URL}/photos/{old_employee.object_key}")
                except Exception as e: print(f"Error: {e}")
        
        updated_employee = database.update_employee(employee_id, employee_data)
        if updated_employee:
            r.delete(f"emp_cache:{employee_id}")
            r.delete(user_list_cache) # 본인 리스트 캐시만 삭제
            return updated_employee
        raise HTTPException(status_code=404, detail="Employee not found")
    
    else:
        # 신규 추가
        new_employee = database.add_employee(employee_data)
        r.delete(user_list_cache) # 본인 리스트 캐시만 삭제
        return new_employee

@app.delete("/employee/{employee_id}")
async def delete_employee_route(employee_id: int, user: dict = Depends(get_current_user_info)):
    user_id = user["id"]
    employee = database.load_employee(employee_id)
    
    # [보안] 본인 데이터인지 확인
    if not employee or employee.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Employee not found or unauthorized")

    if employee.object_key:
        try: await client.delete(f"{config.PHOTO_SERVICE_URL}/photos/{employee.object_key}")
        except Exception as e: print(f"Error: {e}")

    database.delete_employee(employee_id)

    r = get_cache_redis()
    r.delete(f"emp_cache:{employee_id}")
    r.delete(f"employees_list_cache:{user_id}")
    
    return JSONResponse(status_code=200, content={"success": True, "message": f"Employee {employee_id} deleted."})