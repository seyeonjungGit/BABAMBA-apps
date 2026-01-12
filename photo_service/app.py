import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

# 1. 저장 경로를 아예 마운트 경로와 일치시킵니다.
PHOTOS_DIR = "/app/static/uploads"

# PHOTOS_DIR이 없으면 생성
os.makedirs(PHOTOS_DIR, exist_ok=True)

app = FastAPI()

# Set up Prometheus instrumentation
Instrumentator().instrument(app).expose(app)

# 정적 파일 제공 (저장된 사진을 직접 제공)
# 이 마운트는 /photos/{object_key} 엔드포인트와 충돌하지 않도록 주의해야 합니다.
# FileResponse를 사용하여 직접 파일을 제공하는 것이 더 유연합니다.
# app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")

# 2. 스태틱 마운트도 동일하게 설정 (이미 되어있다면 확인만)
app.mount("/static/uploads", StaticFiles(directory=PHOTOS_DIR), name="photos")

@app.post("/upload")
async def upload_photo(file: UploadFile = File(...)):
    """
    사진을 업로드하고 고유한 object_key를 반환합니다.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    # 고유한 파일 이름 생성 (S3 object_key와 유사)
    file_extension = file.filename.split(".")[-1] if "." in file.filename else "bin"
    object_key = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(PHOTOS_DIR, object_key)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not upload file: {e}")

    return JSONResponse(status_code=status.HTTP_200_OK, content={"object_key": object_key})

@app.get("/photos/{object_key}")
async def get_photo(object_key: str):
    """
    object_key를 사용하여 저장된 사진을 제공합니다.
    """
    file_path = os.path.join(PHOTOS_DIR, object_key)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Photo not found")
    
    return FileResponse(file_path)

@app.delete("/photos/{object_key}")
async def delete_photo(object_key: str):
    """
    object_key를 사용하여 사진을 삭제합니다.
    """
    file_path = os.path.join(PHOTOS_DIR, object_key)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Photo not found")
    
    try:
        os.remove(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not delete file: {e}")
    
    return JSONResponse(status_code=status.HTTP_200_OK, content={"message": f"Photo {object_key} deleted."})

# The if __name__ == '__main__': block is removed as Uvicorn will run the app directly.
# Example command to run with Uvicorn: uvicorn app:app --host 0.0.0.0 --port 5003 --reload
