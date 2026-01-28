from redis.sentinel import Sentinel
import redis
import os
import logging

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

# 로그를 남겨서 나중에 왜 레디스가 안 됐는지 확인할 수 있게 합니다.
logger = logging.getLogger(__name__)

# [3] 세션용 Redis (Sentinel 방식)
def get_session_redis():
    try:
        # 1. 호스트 리스트 준비
        host_list = REDIS_SENTINEL_HOSTS.split(",")
        sentinels = [(host.strip(), REDIS_SENTINEL_PORT) for host in host_list]
        
        # 2. Sentinel 객체 생성
        # 타임아웃을 1.0초로 줄였습니다. (네트워크가 나빠도 1초만 기다리고 판단)
        sentinel = Sentinel(
            sentinels,
            socket_timeout=1.0,          # 데이터를 주고받을 때
            socket_connect_timeout=1.0,  # 처음 연결할 때
            password=REDIS_PASSWORD
        )
        
        # 3. 마스터 정보 가져오기
        # 여기서 실패하면 바로 except 구문으로 넘어갑니다.
        return sentinel.master_for(
            REDIS_MASTER_NAME, 
            socket_timeout=1.0, 
            decode_responses=True,
            password=REDIS_PASSWORD
        )

    except Exception as e:
        # 4. 접속 실패 시 에러를 내지 않고 None을 반환!
        # 서비스가 죽지 않게 하는 핵심 포인트입니다.
        logger.warning(f"Redis Sentinel 접속 실패 (None 반환): {e}")
        return None

# [4] 캐시용 Redis (단독 방식)
def get_cache_redis():
    if not USE_REDIS_CACHE:
        return None
    return redis.Redis(
        host=REDIS_CACHE_HOST, 
        port=REDIS_CACHE_PORT,
        decode_responses=True
    )
