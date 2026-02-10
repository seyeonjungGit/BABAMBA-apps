# BABAMBA Apps

## 프로젝트 소개

**로그인한 사용자가 직원(프로필) 정보를 등록·조회·수정·삭제(CRUD)하고, 직원 사진은 별도 서비스로 업로드/관리하는 마이크로서비스 기반 웹 애플리케이션**입니다.

- **사용자 가치**: “직원 디렉토리(프로필) 관리”를 웹에서 쉽게 운영
- **운영 관점**: 인증/직원/사진을 분리하고 **Gateway API 기반 라우팅**으로 배포/확장/관측(메트릭·로그)을 고려

## 주요 기능

- **인증(Auth)**: 회원가입 / 로그인(JWT 발급) / 로그아웃(세션 무효화)
- **직원(Employee)**: 직원 목록/단건 조회, 생성/수정/삭제, (옵션) Redis 캐시
- **사진(Photo)**: 업로드/삭제/제공(직원 프로필 사진)
- **Gateway API 라우팅(배포 기준)**: Kubernetes **Gateway API(Envoy Gateway) + HTTPRoute**로 `auth/employee/photo` 트래픽을 라우팅
  - (온프렘) `LoadBalancer` 서비스의 외부 IP는 **MetalLB**로 할당 가능
- **Frontend(UI)**: 브라우저 UI에서 로그인 후 직원 관리(정적 파일은 Nginx로 서빙)
  - `BABAMBA-gitops-refactor` 배포에서는 프론트가 **별도 Nginx 워크로드(Deployment/Service)** 로 배포될 수 있습니다. (예: NodePort로 노출)

## 아키텍처 개요

```text
Browser(Frontend)
  └─(HTTP/S)→ Envoy Gateway (Gateway API)
              └─(HTTPRoute)→ auth_server / employee_server / photo_service
```

### 외부 트래픽 유입(멀티클러스터, 배포 기준)

`BABAMBA-gitops-refactor` 구성에서는 외부 트래픽 유입에 **Cloudflare + cloudflared(Cloudflare Tunnel)** 를 사용합니다.
(`workloads/cloudflared.platform`에 `cloudflared` Deployment가 있으며, `cf-tunnel-token` Secret의 토큰으로 Tunnel을 구동)

```text
Cloudflare (DNS/GSLB)
  ├─ (On-Prem) cloudflared Tunnel → Kubernetes → Envoy Gateway → HTTPRoute → Services
  └─ (Cloud)   (예: AWS NLB)      → EKS        → Envoy Gateway → HTTPRoute → Services
```

## 레포 구성

- **`auth_server`**: 회원가입, 로그인, 로그아웃(JWT/세션)
- **`employee_server`**: 직원 정보 CRUD + (옵션) 캐시/세션검증 + access log
- **`photo_service`**: 사진 업로드/삭제/제공
- **`gateway`**: (레거시/로컬용) 애플리케이션 레벨 리버스 프록시  
  - `BABAMBA-gitops-refactor` 배포에서는 주로 **Gateway API(Envoy Gateway)**로 라우팅합니다.
- **`frontend`**: 웹 UI 소스 + Nginx 설정(이미지 빌드 대상)
- **`common`**: 공통 설정/DB/모델/Redis 연결 등


## k6 부하테스트 관련 (seyeon 브랜치 기준)

`seyeon` 브랜치는 **k6 부하테스트 시나리오**를 위해 `employee_server`의 동작을 다음처럼 맞춘 버전입니다.

### 변경 요약

- **세션 검증 방식**: `employee_server`가 JWT 검증 후 **Redis(Sentinel) 세션(`session:{user_id}`) 존재**까지 확인합니다.
  - 즉, **Auth에서 로그인 호출로 세션이 만들어져야** `/employees` 같은 API가 200을 반환합니다.
- **Redis 캐시(옵션)**: 직원 목록/단건 조회 캐시를 `get_cache_redis()`로 사용하며, `USE_REDIS_CACHE=false`면 캐시를 건너뜁니다.
- **Access log(지표 보조)**: `duration_ms=` 형태로 남기는 간단한 access log 미들웨어가 추가되었습니다. (Loki/LogQL 집계용)

### 부하테스트 전제조건(중요)

- **Auth/Employee 조합 일치**
  - `seyeon`의 `employee_server`는 세션 Redis 체크가 켜져있으므로,
  - **로그인 시 Redis에 세션을 저장하는 `auth_server`**와 함께 써야 합니다.
- **JWT 서명키(SECRET) 정합성**
  - **Auth/Employee 모두 `common/config.py`의 `JWT_SECRET_KEY`(환경변수 `JWT_SECRET_KEY`)를 사용**하도록 통일했습니다.
  - 배포에서 `JWT_SECRET_KEY`를 바꿨다면 **모든 서비스가 동일한 값**을 쓰는지 확인하세요. (불일치 시 401)
- **Gateway 라우팅**
  - GitOps(HTTPRoute)에서 `/employee` prefix를 백엔드에 전달할 때 `/`로 rewrite 하는 구성이 필요합니다.
  - 이 경우 외부 호출은 `/employee/employees` → 백엔드(`employee_server`)에는 `/employees`로 전달됩니다.

### k6 스크립트(참고)

부하는 GitOps 리포지토리의 스크립트를 사용합니다.

- `BABAMBA-gitops-refactor/gitops-structure/hpa-test/k6-employees.sh`

스크립트 동작 개요:
- Auth에 `/auth/login` 호출 → JWT 발급
- Gateway 경유로 `/employee/employees`에 `Authorization: Bearer <JWT>` 포함하여 k6 부하

### 자주 발생하는 실패(401) 체크 포인트

- **`로그아웃된 세션입니다.`**: Auth에서 세션이 저장되지 않았거나 Redis 세션이 만료/누락된 경우
- **`Could not validate credentials`**: JWT 서명키 불일치(SECRET 다름), 토큰 형식/헤더 누락 등

### Loki에서 부하 로그 보기 (employee_server)

`seyeon`의 `employee_server`에는 요청 처리 시간을 `duration_ms=`로 남기는 **access log 미들웨어**가 들어있습니다.
이 로그는 일반적으로 **stdout**으로 출력되며, `BABAMBA-gitops-refactor` 구성에서는 보통 **Fluent Bit(DaemonSet)** 이 컨테이너 로그를 수집해 Loki로 전송합니다.
  - (참고) Fluentd가 아니라 Fluent Bit 기반으로 보입니다.

- **로그 형태 예시**:
  - `access method=GET path=/employees status=200 duration_ms=12.34`
- **로그 레벨**:
  - 기본 `INFO`
  - 필요 시 환경변수 `LOG_LEVEL`로 조절 (예: `LOG_LEVEL=INFO`)

Loki에서 아래 키워드로 검색하면 부하 중 요청 처리시간 로그만 빠르게 필터링할 수 있습니다.

- **추천 검색 키워드**: `duration_ms=`
- **추가 키워드**: `employee.access` (로거 이름)

