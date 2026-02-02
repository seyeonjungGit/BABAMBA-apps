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
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "local").lower()
PHOTOS_DIR = "/app/static/uploads"

# AWS S3 설정
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
S3_BUCKET_NAME = os.environ.get("AWS_S3_BUCKET")

# 로컬 디렉토리 생성
os.makedirs(PHOTOS_DIR, exist_ok=True)

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

# -------------------------------------------------
# [변경 포인트 1] 라우터 우선순위 조절
# mount보다 @app.get을 먼저 정의해야 리다이렉트가 작동합니다.
# -------------------------------------------------

@app.get("/static/uploads/{object_key}")
@app.get("/photos/{object_key}")
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
            # 사용자를 S3 URL로 리다이렉트 (404 방지)
            return RedirectResponse(url=presigned_url)
        except Exception as e:
            raise HTTPException(status_code=404, detail="Photo not found in S3")
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(file_path)

# [변경 포인트 2] S3 모드일 때는 mount를 피하는 것이 안전합니다.
if STORAGE_TYPE != "s3":
    app.