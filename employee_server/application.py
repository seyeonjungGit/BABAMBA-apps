import os
import jwt
import time
import json
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from prometheus_fastapi_instrumentator import Instrumentator
import httpx
from io import BytesIO

from common import config
from common import database
import util 
from common.models import Employee, EmployeePublic, EmployeesListResponse 
from common.redis_config import get_cache_redis, get_session_redis

app = FastAPI()

# Prometheus 설정
Instrumentator().instrument(app).expose(app)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = config.JWT_SECRET_KEY
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

@app.on_event("startup")
async def on_startup():
    database.create_db_and_tables()

# [인증] JWT는 필수, Redis 세션은 옵션
async def get_current_user_info(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1️⃣ JWT 검증 (절대 기준)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("user")
        user_id: int = payload.get("id")

        if username is None or user_id is None:
            raise credentials_exception

        # 2️⃣ Redis 세션 체크 (Best Effort)
        try:
            r_session = get_session_redis()
            if not r_session.exists(f"session:{user_id}"):
                # 로그만 남기고 통과
                print(f"[WARN] Redis session missing for user_id={user_id}")
        except Exception as e:
            # Sentinel 장애 / 네트워크 문제
            print(f"[WARN] Redis session check failed: {e}")

        # 3️⃣ 정상 통과
        return {"username": username, "id": user_id}

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었습니다.",
        )
    except jwt.PyJWTError:
        raise credentials_exception


def get_photo_url_for_fastapi(object_key: str):
    return f"/static/uploads/{object_key}"

# --- API 엔드포인트 ---

@app.get("/employees", response_model=EmployeesListResponse)
async def get_employees(user: dict = Depends(get_current_user_info)):
    start_time = time.time()
    user_id = user["id"]
    cache_key = f"employees_list_cache:{user_id}"
    
    # 캐시용 Redis 가져오기 (만약 None이면 캐시 기능 건너뜀)
    r = get_cache_redis()

    # 1. Redis 캐시 확인
    if r:
        try:
            cached_data = r.get(cache_key)
            if cached_data:
                execution_time = (time.time() - start_time) * 1000
                print(f"🚀 [HIT] Redis Cache for User {user_id}: {execution_time:.2f} ms")
                return json.loads(cached_data)
        except Exception as e:
            print(f"⚠️ Redis Error: {e}")

    # 2. 캐시 없거나 Redis 비활성화 시 DB 조회
    employees: List[Employee] = database.list_employees(owner_id=user_id)
    
    employees_public_data = []
    for employee in employees:
        emp_public = EmployeePublic.from_orm(employee)
        if employee.object_key:
            emp_public.photo_url = get_photo_url_for_fastapi(employee.object_key)
        employees_public_data.append(emp_public)
    
    # 3. Redis에 결과 저장 (r이 활성화된 경우만)
    if r:
        try:
            r.setex(cache_key, 300, json.dumps([e.dict() for e in employees_public_data]))
        except Exception as e:
            print(f"⚠️ Redis Write Error: {e}")

    execution_time = (time.time() - start_time) * 1000
    print(f"🐌 [MISS] DB Query for User {user_id}: {execution_time:.2f} ms")
    return employees_public_data

@app.get("/employee/{employee_id}", response_model=EmployeePublic)
async def get_employee(employee_id: int):
    start_time = time.time()
    r = get_cache_redis()
    cache_key = f"emp_cache:{employee_id}"

    if r:
        try:
            cached_emp = r.get(cache_key)
            if cached_emp:
                print(f"🚀 [HIT] Redis Cache for ID {employee_id}")
                return json.loads(cached_emp)
        except Exception as e:
            print(f"⚠️ Redis Error: {e}")

    employee: Optional[Employee] = database.load_employee(employee_id)
    if employee:
        emp_public = EmployeePublic.from_orm(employee)
        if employee.object_key:
            emp_public.photo_url = get_photo_url_for_fastapi(employee.object_key)
        
        if r:
            try: r.setex(cache_key, 600, json.dumps(emp_public.dict()))
            except: pass
            
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
    if photo and photo.filename:
        photo_bytes = await photo.read()
        image_bytes = util.resize_image(BytesIO(photo_bytes), (120, 160))
        if image_bytes:
            try:
                files = {'file': (photo.filename, image_bytes, photo.content_type)}
                response = await client.post(f"{config.PHOTO_SERVICE_URL}/upload", files=files)
                response.raise_for_status()
                key = response.json().get("object_key")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Image Upload Failed: {e}")

    employee_data = Employee(
        id=employee_id, object_key=key, full_name=full_name,
        location=location, job_title=job_title, badges=badges, owner_id=user_id
    )

    if employee_id:
        if key:
            old_employee = database.load_employee(employee_id)
            if old_employee and old_employee.object_key:
                try: await client.delete(f"{config.PHOTO_SERVICE_URL}/photos/{old_employee.object_key}")
                except: pass
        
        updated = database.update_employee(employee_id, employee_data)
        if updated:
            if r:
                try:
                    r.delete(f"emp_cache:{employee_id}")
                    r.delete(user_list_cache)
                except: pass
            return updated
        raise HTTPException(status_code=404, detail="Employee not found")
    
    else:
        new_emp = database.add_employee(employee_data)
        if r:
            try: r.delete(user_list_cache)
            except: pass
        return new_emp

@app.delete("/employee/{employee_id}")
async def delete_employee_route(employee_id: int, user: dict = Depends(get_current_user_info)):
    user_id = user["id"]
    employee = database.load_employee(employee_id)
    
    if not employee or employee.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Unauthorized")

    if employee.object_key:
        try: await client.delete(f"{config.PHOTO_SERVICE_URL}/photos/{employee.object_key}")
        except: pass

    database.delete_employee(employee_id)

    r = get_cache_redis()
    if r:
        try:
            r.delete(f"emp_cache:{employee_id}")
            r.delete(f"employees_list_cache:{user_id}")
        except: pass
    
    return JSONResponse(status_code=200, content={"success": True})


@app.get("/health")
def health():
    return {"status": "ok"}
