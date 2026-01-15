# CI 개발일지 (BABAMBA-apps)

---

## 현재 동작 요약(요즘 기준)

- **PR(`pull_request`)**: 변경된 서비스만 **빌드(푸시/배포 없음)**
- **push(`dev`, `main`)**: 변경된 서비스만 **빌드 + GHCR(ghcr.io) 푸시**  
  - 그리고 **GitOps(`BABAMBA-gitops`)의 동일 브랜치(dev/main)** 에서 매니페스트 `image:` 태그를 **`sha-<7자리>`로 갱신 커밋/푸시**
- **Workflow 변경 PR**: `workflow-lint`가 `actionlint`로 워크플로우 문법 검사
- **변경 감지(detect-changes)**: `dorny/paths-filter`로 “이번 PR/이번 push 범위”만 비교해서 서비스 선택

---

## 버전별(주요 커밋) 변경 요약

### v0.1 — 초기 CI 파이프라인 추가
- Docker 이미지 빌드/푸시 + GitOps 매니페스트 태그 갱신(초기 형태)

### v0.2 — GHCR 전환 + dev/main 브랜치 매핑 GitOps 갱신
- 레지스트리 **`docker.io` → `ghcr.io`** 전환
  - `BABAMBA-apps`의 **dev/main push**에 맞춰 `BABAMBA-gitops`의 **동일 브랜치(dev/main)** 매니페스트 태그 갱신
  - PR에서는 **푸시/배포 금지**(빌드만)

### v0.3 — Private GitOps 권한 이슈 문서화
- private `BABAMBA-gitops` 접근 시 `TOKEN_GIT`(PAT) 권한 부족하면 404처럼 보이는 에러가 나는 점을 문서에 반영
- Fine-grained PAT 최소 권한(Contents RW) 가이드

### v0.4 — "변경된 서비스만 빌드" 최적화 도입
  - `detect-changes` job 추가: 경로 기반으로 변경된 서비스만 매트릭스로 구성
  - `common/**` 변경 시 영향 서비스 매핑(예: auth/employee)
  - PR에서도 "전체 5개 빌드"가 아니라 **변경된 것만 빌드**

### v0.5 — GitOps 매니페스트 경로 설정 로직 리팩토링
  - GitOps 매니페스트 파일 경로 설정 로직 간소화
  - 서비스명 → GitOps 디렉토리명 매핑을 별도 `case` 문으로 분리

---

## 다음 Step(개선 아이디어)

시간이 허락한다면 아래 개선을 단계적으로 진행할 수 있습니다.

### 1) Job 병렬 처리(빌드 시간 단축)
- 현재는 `max-parallel: 1`이라 서비스가 여러 개 바뀌면 **순차 빌드**됩니다.
- 개선안:
  - `max-parallel`을 2~5로 올려 **동시에 여러 서비스 빌드**

### 2) Self-hosted Runner(우리 서버)로 빌드 서버 전환
- GitHub-hosted runner(`ubuntu-latest`) 대신, 우리 서버에 **self-hosted runner**를 설치해 빌드하면:
  - CPU/RAM/디스크를 원하는 만큼 확보 가능
  - 캐시를 로컬 디스크로 유지해 빌드 속도 개선 여지 큼



## 운영 체크포인트(팀 공통)

- **필수 시크릿**
  - `TOKEN_GIT`: `BABAMBA-gitops`(private) 접근/푸시 가능한 PAT(Contents: Read/Write)
- **Argo CD 자동배포**
  - `BABAMBA-gitops`의 `dev`/`main` 브랜치를 바라보는 Application에서 Auto-Sync ON이면, 매니페스트 커밋 감지 후 자동 배포

