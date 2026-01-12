FROM nginx:latest

# 기존 설정 파일 삭제 (혹시 모를 충돌 방지)
RUN rm /etc/nginx/conf.d/default.conf

# 소스 복사
COPY . /var/www/frontend/

# 우리 설정 복사
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 권한 부여 (이미지 내 정적 파일 읽기용)
RUN chmod -R 755 /var/www/frontend