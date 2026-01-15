# CI/CD 사용 가이드 (BABAMBA-apps → GHCR → GitOps)

---

## 1) 목적

- **레지스트리**: `ghcr.io` (GitHub Container Registry)
- **GitOps**: `BABAMBA-gitops` 매니페스트의 `image:` 태그를 자동 갱신
- **브랜치 매핑**
  - `BABAMBA-apps:dev` push → `BABAMBA-gitops:dev`에서 태그 갱신 커밋
  - `BABAMBA-apps:main` push → `BABAMBA-gitops:main`에서 태그 갱신 커밋

---

## 2) 필요한 GitHub 설정

### 2-1. GHCR 푸시 권한
워크플로우는 `GITHUB_TOKEN`으로 GHCR에 푸시합니다.
- 워크플로우에 `permissions: packages: write`가 필요합니다.

### 2-2. GitOps 저장소 커밋/푸시 토큰(필수)
`BABAMBA-gitops`가 private인 경우, `BABAMBA-apps` 저장소에 아래 시크릿이 필요합니다.
- **`TOKEN_GIT`**: `BABAMBA-gitops`에 commit/push 가능한 토큰

#### Fine-grained PAT (권장 / 최소 권한)
1. GitHub → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained tokens* → **Generate new token**
2. **Repository access**: *Only selected repositories* → `BABAMBA-gitops`만 선택
3. **Repository permissions**:
   - **Contents: Read and write**
4. 생성된 토큰을 `BABAMBA-apps` → *Settings* → *Secrets and variables* → *Actions* → `TOKEN_GIT`에 등록


---

## 3) 동작 방식(요약)

### PR(`pull_request`)
- 변경된 서비스만 **빌드**
- **푸시/배포(GHCR, GitOps)는 하지 않음**
- 워크플로우 파일이 변경되면 `workflow-lint`로 문법 검사

### dev/main push
- 변경된 서비스만 **빌드 + GHCR 푸시**
- `dev`/`main` 브랜치 push이면 GitOps도 수행:
  - `BABAMBA-gitops` 동일 브랜치의 매니페스트 `image:`를 `sha-<7자리>`로 변경
  - 커밋/푸시

---

## 4) 이미지/태그 규칙

- 이미지 경로: `ghcr.io/<OWNER>/<service>`
- 태그:
  - 브랜치 태그: `dev`, `main`
  - 고정 태그: `sha-<7자리>` (**GitOps 매니페스트에서 사용**)

---

## 5) GitOps 매니페스트 갱신 대상

서비스별 대상 파일(첫 번째 `image:` 라인 교체):
- `auth_server` → `workloads/k8s/auth.yaml`
- `employee_server` → `workloads/k8s/employee.yaml`
- `gateway` → `workloads/k8s/gateway.yaml`
- `photo_service` → `workloads/k8s/photo.yaml`
- `frontend` → `workloads/k8s/nginx.yaml`

---

## 6) 테스트 절차(권장)

### 6-1. “변경된 서비스만 빌드” 확인
1. `frontend/index.html`에 주석 1줄 추가
2. `dev`에 push
3. Actions에서 `detect-changes` Summary 확인 → `frontend=true`만 뜨는지
4. `build-and-push(frontend)`만 생성되는지 확인

### 6-2. GitOps 태그 갱신 확인(dev)
1. 위 테스트를 `dev`에 push로 수행
2. `BABAMBA-gitops`의 `dev` 브랜치에서 커밋 생성 여부 확인
3. `workloads/k8s/nginx.yaml`의 `image:`가 `sha-...`로 변경되었는지 확인
4. (Argo CD Auto-Sync ON이면) 배포 반영 여부 확인

---

## 7) 트러블슈팅

- **`remote: Repository not found` / 404**: `TOKEN_GIT` 권한 부족(특히 private gitops)
- **GitOps 단계에서 rebase 에러**: 브랜치 보호/권한/동시 업데이트 충돌 가능
- **Packages에 안 보임**: PR은 푸시를 안 하므로 정상(푸시 이벤트에서만 GHCR 업로드)

