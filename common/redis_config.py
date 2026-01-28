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
REDIS_SENTINEL_HOSTS = os.getenv("REDIS_SENTINEL_HOST") or "redis-sentinel-service"
REDIS_SENTINEL_PORT = get_env_port("REDIS_SENTINEL_PORT", 26379)
REDIS_MASTER_NAME = os.getenv("REDIS_MASTER_NAME") or "mymaster"
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or "kosa1004"

REDIS_CACHE_HOST = os.getenv("REDIS_CACHE_HOST") or "redis-cache-service"
REDIS_CACHE_PORT = get_env_port("REDIS_CACHE_PORT", 6379)
# 환경변수에 따라 캐시 사용 여부 결정
USE_REDIS_CACHE = os.getenv("USE_REDIS_CACHE", "true").lower() == "true"

# [3] 세션용 Redis (Sentinel 방식)
def get_session_redis():
    # 1. 쉼표로 구분된 문자열을 리스트로 쪼갭니다.
    host_list = REDIS_SENTINEL_HOSTS.split(",")
    
    # 2. Sentinel이 인식할 수 있는 [(ip, port), (ip, port)...] 형식으로 변환합니다.
    sentinels = [(host.strip(), REDIS_SENTINEL_PORT) for host in host_list]
    
    # 3. 변환된 리스트를 넣어줍니다.
    sentinel = Sentinel(
        sentinels,  # <--- 여기가 포인트!
        socket_timeout=10.0,
        socket_connect_timeout=10.0,
        password=REDIS_PASSWORD
    )
    
    return sentinel.master_for(
        REDIS_MASTER_NAME, 
        socket_timeout=10.0, 
        socket_connect_timeout=10.0,
        decode_responses=True,
        password=REDIS_PASSWORD
    )

# [4] 캐시용 Redis (단독 방식)
def get_cache_redis():
    if not USE_REDIS_CACHE:
        return None
    return redis.Redis(
        host=REDIS_CACHE_HOST, 
        port=REDIS_CACHE_PORT,
        decode_responses=True
    )
