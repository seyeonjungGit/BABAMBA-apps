import os
import shutil
import uuid
import boto3
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)

# 환경 변수
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "local").lower()
PHOTOS_DIR = "/app/static/uploads"
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
S3_BUCKET_NAME = os.environ.get("AWS_S3_BUCKET")

os.makedirs(PHOTOS_DIR, exist_ok=True)

def get_s3_client():
    if not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
        raise HTTPException(status_code=500, detail="AWS Credentials missing")
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 Bucket name missing")
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    )

# 1. 사진 가져오기 라우터 (S3 리다이렉트 포함)
@app.get("/static/uploads/{object_key}")
@app.get("/photos/{object_key}")
async def get_photo(object_key: str):
    if STORAGE_TYPE == "s3":
        try:
            s3 = get_s3_client()
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': object_key},
                ExpiresIn=3600
            )
            return RedirectResponse(url=presigned_url)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"S3 Error: {str(e)}")
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(file_path)

# 2. 업로드 기능
@app.post("/upload")
async def upload_photo(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    object_key = f"{uuid.uuid4()}.{ext}"

    if STORAGE_TYPE == "s3":
        try:
            s3 = get_s3_client()
            s3.upload_fileobj(file.file, S3_BUCKET_NAME, object_key, ExtraArgs={"ContentType": file.content_type})
            return {"object_key": object_key, "storage": "s3"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"object_key": object_key, "storage": "local"}

# 3. 삭제 기능
@app.delete("/photos/{object_key}")
async def delete_photo(object_key: str):
    if STORAGE_TYPE == "s3":
        try:
            s3 = get_s3_client()
            s3.delete_object(Bucket=S3_BUCKET_NAME, Key=object_key)
            return {"message": "Deleted from S3"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 Delete Error: {str(e)}")
    else:
        file_path = os.path.join(PHOTOS_DIR, object_key)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"message": "Deleted locally"}
        raise HTTPException(status_code=404)

@app.get("/health")
def health():
    return {"status": "ok", "storage": STORAGE_TYPE}

# S3가 아닐 때만 정적 파일 마운트 (충돌 방지)
if STORAGE_TYPE != "s3":
    app.mount("/static/uploads", StaticFiles(directory=PHOTOS_DIR), name="static")