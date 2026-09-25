# GitHub 업데이트 절차 — 현재 실행 보류

현재는 로컬 검토만 합니다. 아래 절차는 사용자가 배포 재개를 결정한 뒤 사용합니다. 이번 작업에서 원격 저장소나 온라인 앱은 변경하지 않았습니다.

## 먼저 로컬에서 확인

1. 전달받은 로컬 앱 주소를 엽니다. 기존 온라인 실행 버튼은 과거 공개판입니다.
2. LOT 직접 검색 → DEMO-0046 → 종합·예방보전 분석 실행을 누릅니다.
3. 제조사·형식 열이 없는지, 온도 음영·고온 Baking·AOI 지도가 유지되는지 확인합니다.
4. Library에서 개선 사례를 등록하고 전후 수량·그래프·보고서와 백업/복원을 확인합니다.
5. 실제 사내 자료는 공개 테스트에 사용하지 않습니다. Library/시료 운영 DB와 검토 JSON은 개인 백업만 합니다.

## 배포를 재개한 뒤: GitHub Desktop 방법

### 1. 기존 저장소 복제

1. https://desktop.github.com 에서 GitHub Desktop을 설치하고 Thisissun93 계정으로 로그인합니다.
2. File → Clone repository → URL을 선택합니다.
3. Repository URL에 `https://github.com/Thisissun93/Real_Manufacturing_AI`를 입력합니다.
4. Local path는 기존 작업 파일과 구분되는 새 폴더를 선택하고 Clone을 누릅니다.
5. 상단 Current repository가 Real_Manufacturing_AI, Current branch가 main인지 확인합니다.
6. Repository → Show in Explorer로 복제한 폴더를 엽니다. README.md와 src 폴더가 바로 보이는 위치가 루트입니다.

### 2. 업데이트 파일 덮어쓰기

1. `Real_Manufacturing_AI_Ver1.0_Update.zip`을 다른 임시 폴더에 압축 해제합니다.
2. 해제한 폴더 안의 README.md, src, assets, docs, tests, requirements.txt, BUILD.json, .github, .gitignore 등을 선택합니다.
3. 그 내용물을 복제한 저장소의 루트에 복사합니다. 동일 파일은 교체하고 폴더는 병합합니다.
4. 업데이트 폴더 자체를 한 단계 더 중첩해서 넣지 않습니다. 결과 경로가 `src/dashboard/app.py`여야 합니다.
5. 기존 .git 폴더는 건드리지 않습니다. 이 ZIP은 기존 저장소에 덮어쓰는 업데이트이며 단독 전체 프로젝트가 아닙니다.
6. instance, SQLite DB, 실제 도면, Library 백업, 원본 사내 자료는 복사하지 않습니다.
7. 탐색기 보기 → 표시 → 숨긴 항목을 켜면 .github/.gitignore도 확인할 수 있습니다.

### 3. 변경 확인과 전송

1. GitHub Desktop으로 돌아가 Changes 목록을 확인합니다.
2. README, 소스, 테스트, 문서, 글꼴, CI 설정 등 준비한 파일만 있는지 확인합니다.
3. Summary에 `Update investigation, maintenance and engineering library`를 입력합니다.
4. Commit to main을 누릅니다.
5. 상단 Push origin을 누릅니다. 여기부터 원격 저장소가 변경됩니다.
6. GitHub 저장소 Code에서 최신 커밋과 README가 보이는지 확인합니다.
7. Actions에서 Manufacturing Investigation Verification을 열고 초록색 성공 표시를 확인합니다. 실패하면 로그의 최초 오류를 확인한 후 진행합니다.

### 4. 기존 Streamlit 앱 확인

1. 기존 주소: https://realmanufacturingai-gqmhke2ybcjhdrsndjsh2e.streamlit.app/
2. GitHub와 연결된 Streamlit 앱은 변경 사항을 반영합니다. 반영되지 않으면 Manage app에서 Reboot를 실행합니다.
3. 저장소 Thisissun93/Real_Manufacturing_AI, main, 실행 파일 src/dashboard/app.py 연결을 확인합니다.
4. 새 배포가 필요한 경우 Python 3.12를 사용합니다. GitHub Pages로는 이 Python 앱을 실행할 수 없습니다.
5. 브라우저 Ctrl+Shift+R 후 새 빌드 시각, Library 탭과 종합 분석을 확인합니다.
6. 클라우드 파일시스템은 운영 DB 영구 보관소가 아닙니다. 인증과 영구 DB를 구축하기 전에는 공개 합성 시연에만 사용합니다.

## GitHub 웹사이트로 올리는 대안

1. 저장소 루트 → Add file → Upload files를 엽니다.
2. ZIP 자체가 아니라 해제한 폴더와 파일을 끌어 넣습니다. app.py만 루트에 올리지 말고 src 구조를 유지합니다.
3. 파일별 25 MiB 제한이 있으므로 큰 demo.json은 이번 ZIP에서 제외했습니다. 실행 때 자동 생성됩니다.
4. .github 업로드가 hidden으로 거절되면 Go to file에서 `.github/workflows/manufacturing._ai.yml`을 열고 연필 버튼 → 전체 선택 → 업데이트의 같은 파일 내용을 붙여 넣기 → Commit changes 합니다.
5. .gitignore도 같은 방법으로 기존 파일을 편집합니다. 없으면 Add file → Create new file → 정확한 이름을 입력합니다.
6. README.md는 기존 파일 열기 → 연필 → 전체 선택 → 전달된 README_교체본.md 내용 붙여넣기 → Commit changes 하면 됩니다. 부분만 붙여넣어 중복시키지 않습니다.
7. Actions와 Streamlit 확인은 위 절차와 같습니다. 여러 번의 커밋이 필요하므로 Desktop 방식을 권합니다.

## README 바로가기

이번 README에는 기존 앱 주소의 실행 버튼이 이미 들어 있습니다. 수동으로 HTML을 만들 필요가 없습니다. 현재 '배포 보류' 안내는 실제 재배포 완료를 확인한 뒤 제거합니다. 미구현 기능을 구현 완료로 바꾸지 마세요.

## 주의할 공개 이력

이번 파일에서 실제 제조사 식별정보를 제거했습니다. 이미 과거 커밋에 올린 정보가 있다면 최신 파일 교체만으로 Git 이력에서 사라지지는 않습니다. 실제 노출이 확인되면 별도 이력 정리가 필요합니다. 이번 작업은 원격 Git 이력 수정이나 삭제를 수행하지 않았습니다.

## 공식 도움말

- GitHub Desktop 복제: https://docs.github.com/en/desktop/adding-and-cloning-repositories/cloning-and-forking-repositories-from-github-desktop
- GitHub 파일 업로드: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
- Streamlit 앱 관리: https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app
