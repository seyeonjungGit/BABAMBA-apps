# 부하테스트(Load Testing) 정리 (BABAMBA Apps)

이 문서는 `BABAMBA-apps`(애플리케이션 코드/이미지) 기준으로, **k6 기반 부하테스트를 수행할 때 알아야 하는 요소**를 한 곳에 모아 정리합니다.  
실제 배포/라우팅/관측 리소스는 주로 `BABAMBA-gitops-refactor`에서 관리됩니다.

## 1) “배포 기준” 트래픽 흐름(왜 Gateway 경유가 필요한가)

운영 배포에서는 보통 클라이언트가 `employee_server` Pod/Service에 직접 접속하지 않고, **클러스터 앞단(Envoy Gateway)** 을 통해 들어옵니다.

```text
Client
  └─→ Cloudflare (DNS/GSLB)
        ├─ (On-Prem) cloudflared(Cloudflare Tunnel) ─→ Kubernetes ─→ Envoy Gateway(Gateway API)
        └─ (Cloud)   (예: AWS NLB)                   ─→ EKS        ─→ Envoy Gateway(Gateway API)
                                                          └─→ HTTPRoute 규칙으로 백엔드 서비스로 전달
```

- **cloudflared**: `BABAMBA-gitops-refactor`에 `cloudflared` Deployment 및 Tunnel 토큰(`cf-tunnel-token`) 기반 실행 구성이 존재합니다.
- **Envoy Gateway / Gateway API + HTTPRoute**: `/auth`, `/employee`, `/photo` 같은 경로를 보고 각 백엔드로 라우팅합니다.
- **(On-Prem) MetalLB**: Envoy Gateway의 `LoadBalancer` 서비스 외부 IP 할당에 사용될 수 있습니다.

## 2) Prefix rewrite란? (`/employee/*` vs 백엔드 실제 경로)

Gateway API의 HTTPRoute는 외부 경로를 예쁘게 유지하면서, 백엔드에는 다른 경로로 전달할 수 있습니다.  
이를 **prefix rewrite**라고 부릅니다.

예시:

```text
외부 요청:  GET /employee/employees
HTTPRoute:  /employee prefix를 / 로 rewrite
백엔드 수신: GET /employees   (employee_server가 실제로 가진 엔드포인트)
```

즉, k6에서 `/employee/employees`를 때려도, `employee_server` 입장에서는 `/employees`(목록 조회)가 들어옵니다.

## 3) 인증 흐름(부하테스트가 401로 터지는 1순위)

### 3.1 JWT 전달 방식(왜 `Authorization: Bearer <JWT>`가 필요한가)

`employee_server`의 주요 API는 보호되어 있으므로, 부하테스트 요청에 아래 헤더가 필요합니다.

- `Authorization: Bearer <JWT>`

이 헤더가 없으면 대부분 **401**이 발생하고, 그러면 DB/캐시/비즈니스 로직이 거의 실행되지 않아 **의미 있는 부하/스케일링 패턴이 나오지 않습니다.**

### 3.2 (seyeon 브랜치) Redis(Sentinel) 세션 체크(왜 필요한가)

`seyeon` 기준 `employee_server`는 **JWT 검증 후** Redis(Sentinel)에 `session:{user_id}`가 존재하는지도 확인합니다.

- 장점: 로그아웃 시 Redis 세션을 지우면 **토큰 만료 전이라도 즉시 차단** 가능(강제 무효화)
- 단점: 요청마다 Redis 조회가 추가되고, Sentinel/Redis 장애 시 인증이 흔들릴 수 있음

따라서 `seyeon` 기준으로는 다음이 전제입니다.

- 로그인 시 Auth가 `session:{user_id}`를 생성해야 함
- Sentinel/Redis가 정상이어야 함

### 3.3 JWT 서명키(SECRET) 정합성

Auth가 발급한 JWT는 Employee가 같은 키로 검증해야 합니다.

- 현재는 **Auth/Employee 모두 `common/config.py`의 `JWT_SECRET_KEY`(환경변수 `JWT_SECRET_KEY`)** 를 사용하도록 통일하는 것이 안전합니다.
- 환경에서 `JWT_SECRET_KEY`를 변경했다면 **모든 관련 서비스가 동일한 값**을 쓰는지 확인하세요.

## 4) GET/WRITE 분리의 의미 (GitOps 배포 기준)

`BABAMBA-gitops-refactor`의 `charts/employee/templates`에는 GET과 WRITE가 분리되어 있습니다.

- **GET 트래픽**: `GET` 메서드만 매칭하는 HTTPRoute → `...-get` Rollout/Service로 라우팅
- **WRITE 트래픽**: `POST/PUT/DELETE`만 매칭하는 HTTPRoute → `...-write` Rollout/Service로 라우팅

의미:

- 읽기(대량 트래픽)와 쓰기(위험/부하 특성 상이)를 **서로 다른 배포/카나리/스케일링 정책**으로 제어
- k6로 GET만 때리면 **GET 쪽만 스케일**시키는 실험이 가능

## 5) k6 부하 시나리오(기본 GET vs WRITE)

### 5.1 기본(GET) 부하: 목록 조회

일반적으로 k6는 “가장 빈번한 트래픽”을 대표하는 **목록 조회**를 때립니다.

- 외부(게이트웨이 기준): `GET /employee/employees`
- 백엔드(리라이트 후): `GET /employees`

### 5.2 WRITE 부하: 생성/수정/삭제

WRITE 부하를 만들려면 k6가 `POST/PUT/DELETE` 요청을 보내야 합니다.

현재 `employee_server`는 (게이트웨이 리라이트 후 기준으로) 대략 아래 형태를 가집니다.

- 생성/수정: `POST /employee` (FormData 기반)
- 단건 조회: `GET /employee/{employee_id}`
- 삭제: `DELETE /employee/{employee_id}`

게이트웨이 경유 외부 경로는 보통 `/employee/...` prefix가 붙습니다.

> 주의: WRITE 부하는 DB/사진 업로드/캐시 무효화 등 부수효과가 많아, 테스트 데이터/정리 전략(삭제, 전용 계정, 전용 DB 등)을 먼저 정하는 것이 안전합니다.

### 5.3 k6 스크립트 위치

기존 “한 방” 스크립트는 GitOps 리포에 있습니다.

- `BABAMBA-gitops-refactor/gitops-structure/hpa-test/k6-employees.sh`

이 스크립트는:

- Auth에 `/auth/login` 호출로 JWT 발급
- Gateway 경유 `/employee/employees` 호출
- 필요 시 `Host` 헤더를 넣어 HTTPRoute hostnames 매칭을 보장

## 6) 관측(Observability): Loki / Fluent Bit / duration_ms 로그

### 6.1 employee_server access log (duration_ms)

`seyeon` 기준 `employee_server`에는 요청 처리 시간을 남기는 access log 미들웨어가 있습니다.

- 예: `access method=GET path=/employees status=200 duration_ms=12.34`

### 6.2 Loki로 로그가 들어가는 경로(배포 기준)

GitOps 구성에서는 보통 **Fluent Bit(DaemonSet)** 이 `/var/log/containers/*.log`를 tail 하여 Loki로 전송합니다.

### 6.3 Loki에서 빠르게 찾는 키워드

- 요청 지연 로그 필터: `duration_ms=`
- 로거 이름(필요 시): `employee.access`

## 7) 자주 나는 에러와 진단 포인트

- **401 / `로그아웃된 세션입니다.`**
  - (seyeon) Redis 세션(`session:{user_id}`)이 없거나 만료/누락
  - Auth/Employee 조합이 섞였거나(로그인은 했는데 세션이 안 찍힘), Sentinel/Redis 장애일 수 있음
- **401 / `Could not validate credentials`**
  - JWT 서명키 불일치(`JWT_SECRET_KEY` 다름), Bearer 헤더 누락, 토큰 형식 문제 등
- **404**
  - Gateway/HTTPRoute host/path 매칭 실패(Host 헤더, PathPrefix, rewrite 설정 확인)

## 8) 부하테스트 전 체크리스트(추천)

- [ ] Auth/Employee가 같은 `JWT_SECRET_KEY`를 사용 중인가?
- [ ] (seyeon) Redis Sentinel/세션 Redis가 정상인가? (로그인 시 `session:{user_id}` 생성 확인)
- [ ] Gateway API(Envoy Gateway) + HTTPRoute가 배포되어 있고 host/path가 맞는가? (필요 시 Host 헤더 포함)
- [ ] 테스트가 “200 트래픽”을 충분히 만들고 있는가? (401이 대부분이면 부하의 의미가 약함)
- [ ] Loki에서 `duration_ms=` 로그가 보이는가? (Fluent Bit → Loki 파이프라인 확인)

