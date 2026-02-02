import os
import shutil
import uuid
import boto3  # AWS SDK 추가
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
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "local").lower() # "s3" or "local"
PHOTOS_DIR = "/app/static/uploads"

# AWS S3 설정 (Helm에서 주입된 값 사용)
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
S3_BUCKET_NAME = os.environ.get("AWS_S3_BUCKET")

# 로컬 디렉토리 생성 (S3 모드여도 임시 저장 등을 위해 생성해둠)
os.makedirs(PHOTOS_DIR, exist_ok=True)

# 정적 파일 마운트 (로컬 모드일 때 사용)
app.mount("/static/uploads", StaticFiles(directory=PHOTOS_DIR), name="photos")

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

    # -------------------------------------------------
    # [CASE A] S3 업로드
    # -------------------------------------------------
    if STORAGE_TYPE == "s3":
        s3 = get_s3_client()
        try:
            # 파일 포인터를 S3로 바로 업로드
            s3.upload_fileobj(
                file.file,
                S3_BUCKET_NAME,
                object_key,
                ExtraArgs={"ContentType": file.content_type}
            )
            return JSONResponse(status_code=200, content={"object_key": object_key, "storage": "s3"})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 Upload Failed: {str(e)}")

    # -------------------------------------------------
    # [CASE B] 로컬 업로드 (기존 로직)
    # -------------------------------------------------
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            return JSONResponse(status_code=200, content={"object_key": object_key, "storage": "local"})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Local Upload Failed: {str(e)}")

@app.get("/photos/{object_key}")
async def get_photo(object_key: str):
    # -------------------------------------------------
    # [CASE A] S3 다운로드 (Presigned URL 리다이렉트)
    # -------------------------------------------------
    if STORAGE_TYPE == "s3":
        s3 = get_s3_client()
        try:
            # S3에서 직접 다운로드 가능한 임시 URL 생성 (1시간 유효)
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': object_key},
                ExpiresIn=3600
            )
            # 사용자를 S3 URL로 토스 (307 Redirect)
            return RedirectResponse(url=presigned_url)
        except Exception as e:
            raise HTTPException(status_code=404, detail="Photo not found in S3")

    # -------------------------------------------------
    # [CASE B] 로컬 다운로드 (기존 로직)
    # -------------------------------------------------
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(file_path)

@app.delete("/photos/{object_key}")
async def delete_photo(object_key: str):
    # -------------------------------------------------
    # [CASE A] S3 삭제
    # -------------------------------------------------
    if STORAGE_TYPE == "s3":
        s3 = get_s3_client()
        try:
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=object_key)
            return JSONResponse(status_code=200, content={"message": f"Deleted {object_key} from S3"})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 Delete Failed: {str(e)}")

    # -------------------------------------------------
    # [CASE B] 로컬 삭제
    # -------------------------------------------------
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Photo not found")
        os.remove(file_path)
        return JSONResponse(status_code=200, content={"message": f"Deleted {object_key} locally"})