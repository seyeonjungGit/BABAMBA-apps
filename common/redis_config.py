from redis.sentinel import Sentinel
import redis
import os
import logging

logger = logging.getLogger(__name__)

# -----------------------------
# 환경변수 헬퍼
# -----------------------------
def get_env_port(name, default):
    val = os.getenv(name, str(default))
    if "tcp://" in val:
        return int(val.split(":")[-1])
    return int(val)

# -----------------------------
# 환경변수
# -----------------------------
REDIS_SENTINEL_HOSTS = os.getenv("REDIS_SENTINEL_HOST")
REDIS_SENTINEL_PORT = get_env_port("REDIS_SENTINEL_PORT", 26379)
REDIS_MASTER_NAME = os.getenv("REDIS_MASTER_NAME") or "mymaster"
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or "kosa1004"

REDIS_CACHE_HOST = os.getenv("REDIS_CACHE_HOST") or "redis-cache-service"
REDIS_CACHE_PORT = get_env_port("REDIS_CACHE_PORT", 6379)
USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "true").lower() == "true"

# -----------------------------
# 세션용 Redis (Sentinel)
# -----------------------------
def get_session_redis():
    """
    - Sentinel 전체 조회
    - 살아있는 Sentinel 탐색
    - 현재 Master 조회
    - Master ping()으로 실제 사용 가능 여부 검증
    - 실패 시 None 반환 (서비스 보호)
    """
    try:
        # 1. Sentinel 목록 생성
        sentinels = [
            (host.strip(), REDIS_SENTINEL_PORT)
            for host in REDIS_SENTINEL_HOSTS.split(",")
            if host.strip()
        ]

        # 2. Sentinel 객체 생성
        sentinel = Sentinel(
            sentinels,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            password=REDIS_PASSWORD
        )

        # 3. Master Redis 객체 획득
        redis_conn = sentinel.master_for(
            REDIS_MASTER_NAME,
            socket_timeout=1.0,
            decode_responses=True,
            password=REDIS_PASSWORD
        )

        # 4. ⭐ 실제 연결 검증 (핵심)
        redis_conn.ping()

        return redis_conn

    except Exception as e:
        logger.warning(
            f"[Redis] Sentinel/Master 접속 실패 → Redis 비활성화: {e}"
        )
        return None

# -----------------------------
# 캐시용 Redis (단독)
# -----------------------------
def get_cache_redis():
    """
    - 캐시는 장애 나도 서비스에 영향 없어야 함
    - 실패 시 None 반환
    """
    if not USE_REDIS_CACHE:
        return None

    try:
        r = redis.Redis(
            host=REDIS_CACHE_HOST,
            port=REDIS_CACHE_PORT,
            password=REDIS_PASSWORD,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=True
        )
        r.ping()
        return r

    except Exception as e:
        logger.warning(f"[Redis] Cache 접속 실패 → 캐시 비활성화: {e}")
        return None
