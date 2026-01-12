# Python 3.9를 베이스 이미지로 사용
FROM python:3.9-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY employee_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y iproute2 && rm -rf /var/lib/apt/lists/*

# 1. 공통 폴더 복사 (컨테이너 내부 /app/common 위치에 저장됨)
COPY common /app/common

# 2. employee_server 내부의 소스 코드 복사
COPY employee_server /app

# 3. 파이썬이 /app 폴더를 루트로 인식하게 하여 'import common'이 가능하게 함
ENV PYTHONPATH=/app

# Uvicorn 서버 실행
CMD ["uvicorn", "application:app", "--host", "0.0.0.0", "--port", "5002"]
