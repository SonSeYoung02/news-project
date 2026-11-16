# 뉴스 뷰어 — Frontend

크롤링된 국내외 IT·AI 뉴스(영문 기사는 한국어 번역문 우선)를 브라우저에서 탐색하는 React SPA입니다.  
FastAPI 백엔드(`news-viewer/backend`)가 제공하는 REST API를 소비합니다.

## 시작하기

```bash
npm install
npm run dev
```

브라우저에서 http://127.0.0.1:5173 (또는 http://localhost:5173) 접속. **백엔드 서버가 먼저 실행되어 있어야 합니다.**

개발 서버(`npm run dev`)와 빌드 미리보기(`npm run preview`)는 보안상 기본으로 loopback(`127.0.0.1`)에만 바인딩됩니다.

### 백엔드 실행 (별도 터미널)

```bash
cd ../backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## 주요 기능

- **카테고리 필터** — API가 반환하는 카테고리와 건수 표시
- **출처 필터** — 네이버뉴스 / Google News / GeekNews / Reddit AI / GitHub Trending / Hugging Face / arXiv / dev.to
- **키워드 검색** — 원문·번역 제목, 본문, 요약 대상 (Enter 또는 검색 버튼, `<form onSubmit>` 단일 처리)
- **기사 상세 보기** — 한국어 번역문/원문 본문(Markdown 서식 지원), LLM 요약(있는 경우), 태그, 원문 링크
- **페이지네이션** — 페이지당 20건
- **반응형 화면** — 1,024px 이상은 3단 구성, 작은 화면은 접이식 필터와 기사 목록·상세 전환

## 화면 디자인

밝은 중립 배경의 읽기 중심 뉴스 리더 UI입니다(#22).

- **색상**: 강조색은 녹색 계열(`ACCENT` `#258347`, `ACCENT_DARK` `#1e6837`, `ACCENT_LIGHT` `#edf5ef`)이며 `src/styles/theme.js`에서 관리합니다. 본문·보조 텍스트는 WCAG AA(4.5:1) 이상의 대비를 유지합니다.
- **출처 배지**: 출처별 약어와 색상(`SOURCE_MARKS`)으로 목록과 상세 화면에서 출처를 구분합니다. 새 출처를 추가하면 `SOURCE_FILTERS`와 `SOURCE_MARKS`를 함께 갱신합니다.
- **정보 위계**: 출처·카테고리·날짜 → 제목 → 요약 → 태그 순으로 배치하고, 카드 테두리·그림자 대신 구분선과 선택 강조로 목록을 구분합니다.
- **사이드바**: 보기·카테고리·출처 항목에 기사 수 배지를 표시합니다.
- **키보드 접근성**: `index.css`의 `:focus-visible`로 녹색 포커스 링을 표시합니다.
- 현재 화면 스크린샷은 `review/issue-22/`에 있습니다.

## 휴대폰에서 접속하기 (명시적 LAN 실행)

기본 실행(`npm run dev`, `npm run preview`)은 `127.0.0.1` loopback에만 바인딩되므로 같은 Wi-Fi의 다른 기기에서 접근할 수 없습니다. 휴대폰 등 LAN 기기에서 테스트할 때만 `--host` 플래그로 명시적으로 네트워크 바인딩을 허용하세요.

1. PC와 휴대폰을 같은 Wi-Fi에 연결하고 PC에서 백엔드를 실행합니다.
2. 프론트엔드 디렉터리에서 `--host`를 지정해 명시적으로 LAN 수신 모드로 실행합니다.

```bash
npm run dev -- --host
# 개발 포트가 사용 중이거나 별도 worktree를 실행할 때
npm run dev -- --host --port 5180
# 프로덕션 빌드 미리보기(preview)를 LAN에서 확인할 때
npm run preview -- --host
```

3. PC의 내부 IPv4 주소를 확인하고 휴대폰에서 `http://<PC의 내부 IP>:5173` (미리보기는 `:4173`)에 접속합니다. 휴대폰의 `localhost`는 PC를 가리키지 않습니다.
4. Vite가 LAN 인터페이스에서 수신하며 `/api` 요청을 PC 내부의 `http://127.0.0.1:8000`으로 전달하므로 백엔드를 외부 인터페이스에 노출할 필요가 없습니다.

> 신뢰할 수 있는 내부 네트워크에서만 `--host`(또는 `--host 0.0.0.0`)를 사용하고 확인이 끝나면 서버를 종료하세요. 호스트 방화벽 또는 공유기의 무선 기기 격리 설정이 접속을 막을 수 있으며, 앱은 방화벽이나 공유기 설정을 자동 변경하지 않습니다. 기본 포트가 사용 중이면 실행을 중단하므로 `--port`로 다른 포트를 지정할 수 있습니다.

## 운영 배포의 API 연결

프론트엔드는 같은 출처의 `/api`를 호출합니다. 개발 서버와 `npm run preview`에는 프록시가 구성되어 있지만, `dist/`를 정적 호스팅할 때는 웹 서버에서 `/api/*`를 백엔드의 `/*`로 전달하는 리버스 프록시를 별도로 구성해야 합니다. `npm run preview`는 로컬 빌드 확인용(기본 `127.0.0.1` 바인딩)이며 운영 서버로 사용하지 않습니다. Cloudflare Tunnel만 연결한다고 API 경로가 자동 구성되지는 않습니다.

## 빌드

```bash
npm run build            # dist/ 디렉토리에 프로덕션 번들 생성
npm run preview          # 프로덕션 빌드 로컬 미리보기 (기본 127.0.0.1)
npm run preview -- --host  # 프로덕션 빌드 미리보기 (명시적 LAN 바인딩)
```

## 기술 스택

| 항목 | 내용 |
|------|------|
| 프레임워크 | React 18 |
| 번들러 | Vite 8 |
| 스타일 | 인라인 스타일 (CSS-in-JS 없음) |
| API | 같은 출처 `/api` → FastAPI `http://127.0.0.1:8000` |

## 프로젝트 구조

```
frontend/
├── index.html          # HTML 진입점 (#app 마운트)
├── vite.config.js      # Vite + React 플러그인 설정
├── src/
│   ├── main.jsx            # ReactDOM.createRoot 부트스트랩
│   ├── App.jsx             # 레이아웃 조립, 보기(브리핑/기사) 전환, 자동 선택
│   ├── api/client.js       # API 기본 경로(/api), fetchJSON
│   ├── features/
│   │   ├── articles/       # 기사 피드: 목록·카드·상세·본문·페이지네이션, 상태 리듀서, useArticles
│   │   └── briefing/       # 오늘의 AI 브리핑: 목록, useBriefing
│   ├── layout/             # Sidebar, Topbar(+ 모바일 읽기 헤더)
│   ├── components/         # 여러 기능이 공유하는 UI (SourceMark)
│   ├── hooks/              # 범용 hook (useMediaQuery)
│   ├── styles/             # theme.js(색상 토큰), shared.js(공용 인라인 스타일), index.css(전역 스타일)
│   └── utils/              # formatDate
├── test/
│   ├── empty-state.test.mjs   # 기사 상태 리듀서 회귀 테스트 (node --test)
│   └── article-body.test.mjs  # 본문 렌더링 회귀 테스트
├── review/issue-22/    # 현재 화면 스크린샷 (루트 README에서 사용)
└── public/
    └── favicon.svg
```

## 참고

- `@vitejs/plugin-react` 6.x는 Vite 8을 기본 지원합니다. `.npmrc`의 `legacy-peer-deps=true`는 JavaScript 프로젝트에서 `react-markdown`의 `@types/react` peer dependency가 불필요하게 자동 설치되는 것을 막기 위해 유지합니다.
- 브라우저는 프론트와 같은 출처의 `/api`만 호출하므로 LAN 접속을 위해 백엔드 CORS 허용 목록을 넓힐 필요가 없습니다.

## 오늘의 AI 브리핑

첫 화면은 최근 24시간의 AI 소식 최대 5개를 보여줍니다. 주제·출처 다양성, 최신순을 반영한 규칙 기반 선정이며 조회 시각을 한국 시간으로 표시합니다.

- 사이드바의 `오늘의 AI 브리핑` / `전체 기사`로 보기를 전환합니다. 모바일에서는 `필터`를 열어 전환합니다.
- 검색·카테고리·출처 선택 시 기사 목록으로 자동 전환됩니다.
- 브리핑 기사 선택 시 3단 뷰어의 읽기 영역에서 본문(번역 완료 기사는 한국어 번역문 우선)과 상세 정보를 확인합니다.
- 로딩·최근 기사 없음·요청 실패를 구분하고 새로고침과 재시도를 제공합니다.
- 백엔드 #23의 `GET /briefing`과 연동하여 한국어 번역문/원문 기사 및 다양성 브리핑을 제공합니다.

기사 카드와 읽기 영역은 번역 파이프라인에서 제공하는 한국어 번역문과 본문(Markdown 서식 지원)을 자연스럽게 표시하며, LLM 요약이 있는 경우 요약 카드도 함께 제공합니다.
