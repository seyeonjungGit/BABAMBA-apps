from redis.sentinel import Sentinel
import redis
import os

# [1] 안전하게 환경 변수를 읽어오는 헬퍼 함수
def get_env_port(name, default):
    val = os.getenv(name, str(default))
    if "tcp://" in val:
        return int(val.split(":")[-1])
    return int(val)

# [2] 전역 변수 설정 (기본값 확실히 지정)
REDIS_SENTINEL_HOST = os.getenv("REDIS_SENTINEL_HOST") or "redis-sentinel-service"
REDIS_SENTINEL_PORT = get_env_port("REDIS_SENTINEL_PORT", 26379)
REDIS_MASTER_NAME = os.getenv("REDIS_MASTER_NAME") or "mymaster"

REDIS_CACHE_HOST = os.getenv("REDIS_CACHE_HOST") or "redis-cache-service"
REDIS_CACHE_PORT = get_env_port("REDIS_CACHE_PORT", 6379)

# [3] 세션용 Redis (Sentinel 방식)
def get_session_redis():
    # 상단에서 정의한 안전한 전역 변수를 사용합니다.
    sentinel = Sentinel(
        [(REDIS_SENTINEL_HOST, REDIS_SENTINEL_PORT)], 
        socket_timeout=0.5
    )
    return sentinel.master_for(
        REDIS_MASTER_NAME, 
        socket_timeout=0.5, 
        decode_responses=True
    )

# [4] 캐시용 Redis (단독 방식)
def get_cache_redis():
    return redis.Redis(
        host=REDIS_CACHE_HOST, 
        port=REDIS_CACHE_PORT,
        decode_responses=True
    )