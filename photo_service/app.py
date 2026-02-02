import os
import shutil
import uuid
import boto3
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

# Prometheus 설정
Instrumentator().instrument(app).expose(app)

# ==========================================
# [설정 로드] 환경변수 읽기
# ==========================================
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "local").lower()  # "s3" 또는 "local"
PHOTOS_DIR = "/app/static/uploads"

# AWS S3 설정
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
S3_BUCKET_NAME = os.environ.get("AWS_S3_BUCKET")

# 로컬 디렉토리 생성
os.makedirs(PHOTOS_DIR, exist_ok=True)

# [중요] /static/uploads 경로로 들어오는 요청을 처리하기 위한 설정
# S3 모드일 때도 기존 경로 형식을 유지하기 위해 mount와 get_photo를 통합 관리합니다.
app.mount("/static/uploads", StaticFiles(directory=PHOTOS_DIR), name="static_photos")

# S3 클라이언트 생성 함수
def get_s3_client():
    if not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
        raise HTTPException(status_code=500, detail="AWS Credentials not found")
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    )

@app.post("/upload")
async def upload_photo(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    file_extension = file.filename.split(".")[-1] if "." in file.filename else "bin"
    object_key = f"{uuid.uuid4()}.{file_extension}"

    if STORAGE_TYPE == "s3":
        s3 = get_s3_client()
        try:
            s3.upload_fileobj(
                file.file,
                S3_BUCKET_NAME,
                object_key,
                ExtraArgs={"ContentType": file.content_type}
            )
            return JSONResponse(status_code=200, content={"object_key": object_key, "storage": "s3"})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 Upload Failed: {str(e)}")
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            return JSONResponse(status_code=200, content={"object_key": object_key, "storage": "local"})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Local Upload Failed: {str(e)}")

# [해결 포인트] 
# 브라우저가 /photos/파일명 또는 /static/uploads/파일명으로 접근할 때 
# S3 URL로 리다이렉트 시켜줘야 사진이 보입니다.
@app.get("/photos/{object_key}")
@app.get("/static/uploads/{object_key}")  # 두 경로 모두 처리
async def get_photo(object_key: str):
    if STORAGE_TYPE == "s3":
        s3 = get_s3_client()
        try:
            # S3 임시 다운로드 URL 생성
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': object_key},
                ExpiresIn=3600
            )
            # 사진 파일을 직접 주는 대신 S3 주소로 리다이렉트
            return RedirectResponse(url=presigned_url)
        except Exception as e:
            raise HTTPException(status_code=404, detail="Photo not found in S3")
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(file_path)

@app.delete("/photos/{object_key}")
async def delete_photo(object_key: str):
    if STORAGE_TYPE == "s3":
        s3 = get_s3_client()
        try:
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=object_key)
            return JSONResponse(status_code=200, content={"message": f"Deleted {object_key} from S3"})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 Delete Failed: {str(e)}")
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Photo not found")
        os.remove(file_path)
        return JSONResponse(status_code=200, content={"message": f"Deleted {object_key} locally"})

@app.get("/health")
def health():
    return {"status": "ok", "storage": STORAGE_TYPE}
