# EconScope

> 복잡한 경제지표를 비교하고, 변화의 이유와 앞으로의 흐름을 쉽게 이해하세요.

EconScope는 한국은행 ECOS의 원/달러 환율, 기준금리, 소비자물가지수(CPI)를 분석해 경제 초보자에게 쉬운 말로 설명하는 데이터 기반 AI 웹 서비스입니다. 두 기간의 수치를 직접 비교하고, AI가 저장된 데이터 요약과 외부 경제자료를 바탕으로 가능한 변화 배경을 설명합니다.

미래의 정확한 수치나 매수·매도 추천을 제공하지 않습니다. 전망은 상승·유지·하락 방향, 확신 수준, 세 가지 시나리오로 제시합니다.

## 주요 기능

- 최신 환율·기준금리·CPI와 최근 3개월 추세 대시보드
- 기간 A와 B의 평균·최고·최저·전체 변화·최대 월간 변화 비교
- 지표 선택형 시계열 그래프와 기간 비교 그래프
- 데이터 요약을 문맥으로 사용하는 AI 경제 채팅
- 기본 답변과 `자세히 분석` 답변
- 방향성 전망, 확신 수준, 접이식 상승·기준·하락 시나리오
- 외부 자료 제목·기관·날짜·링크 표시
- 경제 데이터 추가·수정·소프트 삭제·개별 및 전체 복원
- ECOS 데이터 하루 한 번 자동 확인 및 수동 갱신
- 대화 자동 저장·목록 조회·불러오기·삭제
- CSV·JSON 내보내기와 다크 모드

## 데이터

초기 데이터는 M1-1에서 수집·검증한 2015년 1월~2025년 12월 월별 자료입니다.

| 지표 | ECOS 통계표 | 단위 | 초기 관측 수 |
|---|---|---|---:|
| 원/달러 환율 | `731Y004` | 원/USD, 공식 월평균 | 132 |
| 한국은행 기준금리 | `722Y001` | 연 % | 132 |
| 소비자물가지수(CPI) | `901Y009` | 2020=100 | 132 |

초기 데이터는 [economic_indicators_monthly.csv](./backend/data/economic_indicators_monthly.csv)에 포함되어 있습니다. 앱이 처음 시작될 때 Firestore 또는 로컬 개발 저장소에 지표별 레코드 396개를 준비합니다.

## 기술 스택

### 프론트엔드

- HTML5
- CSS3
- Vanilla JavaScript
- 프레임워크나 차트 라이브러리 없이 SVG 그래프 구현
- Vercel 배포 설정

### 백엔드

- Python 3.10+
- FastAPI / Pydantic
- Firebase Admin SDK / Firestore
- OpenAI Responses API
- 한국은행 ECOS Open API
- Render 배포 설정

OpenAI 연동은 새로운 앱에 권장되는 Responses API를 사용합니다. `ENABLE_WEB_SEARCH=true`일 때 Responses API의 `web_search` 도구를 활성화하며, 검색 결과가 없거나 호출이 실패하면 저장 데이터와 일반 경제 원리로 답변합니다. 참고: [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create), [Web search](https://developers.openai.com/api/docs/guides/tools-web-search)

## 프로젝트 구조

```text
M1-2/
├── backend/
│   ├── app/
│   │   ├── routers/             # 데이터·대화·채팅 API
│   │   ├── services/            # 분석·ECOS·OpenAI·대화 로직
│   │   ├── config.py            # 환경 변수
│   │   ├── models.py            # Pydantic 검증 모델
│   │   ├── repository.py        # Firestore와 로컬 저장소
│   │   └── main.py              # FastAPI 앱과 CORS
│   ├── data/                     # M1-1 초기 시계열 데이터
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── public/                   # HTML·CSS·JavaScript 소스
│   ├── build.mjs                 # API_BASE_URL 주입 빌드
│   ├── package.json
│   └── vercel.json
├── .env.example
├── render.yaml
└── ECONSCOPE_PRODUCT_SPEC.md
```

## 로컬 실행

### 1. 환경 변수

```bash
cp .env.example .env
```

Firestore나 OpenAI 키 없이 화면과 CRUD, 통계, 로컬 데이터 기반 채팅을 실행하려면 다음 값을 유지합니다.

```dotenv
USE_LOCAL_DB=true
ENABLE_WEB_SEARCH=false
```

### 2. 백엔드

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn main:app --reload
```

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- 상태 확인: `http://localhost:8000/health`

### 3. 프론트엔드

새 터미널에서 실행합니다.

```bash
cd frontend
npm run dev
```

브라우저에서 `http://localhost:3000`에 접속합니다.

## 환경 변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | 배포 시 권장 | OpenAI API 키. 없으면 로컬 분석 답변 사용 |
| `OPENAI_MODEL` | 아니요 | 기본값 `gpt-4.1-mini` |
| `ENABLE_WEB_SEARCH` | 아니요 | `true`이면 답변 생성 시 필요에 따라 외부 근거 검색 |
| `ECOS_API_KEY` | 배포 시 권장 | 한국은행 ECOS API 키. `sample`도 가능하지만 호출당 행 수 제한 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firestore 사용 시 | 서비스 계정 JSON 전체 문자열 |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | 로컬 대안 | 서비스 계정 JSON 파일 경로 |
| `USE_LOCAL_DB` | 아니요 | `true`이면 로컬 JSON 저장소 사용 |
| `AUTO_SYNC` | 아니요 | 앱 시작 시 24시간 경과 여부를 확인해 ECOS 자동 갱신 |
| `ALLOWED_ORIGINS` | 배포 시 필수 | 쉼표로 구분한 프론트엔드 허용 주소 |
| `API_BASE_URL` | 프론트 배포 시 필수 | Vercel 빌드에 주입할 Render API 주소 |

API 키와 Firebase 서비스 계정은 저장소에 커밋하지 않습니다.

## Firestore 컬렉션

### `data`

```json
{
  "id": "cpi_2025-12",
  "date": "2025-12",
  "indicator": "cpi",
  "value": 117.57,
  "memo": "한국은행 ECOS 초기 데이터",
  "source": "ecos",
  "status": "official",
  "original_value": 117.57,
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

`status`는 `official`, `user`, `modified`, `deleted` 중 하나입니다. 삭제는 실제 문서를 제거하지 않는 소프트 삭제이며, 수정된 공식 데이터는 `original_value`로 복원합니다.

### `conversations`

```json
{
  "id": "generated-id",
  "title": "최근 물가 흐름을 설명해줘",
  "messages": [
    { "role": "user", "content": "...", "created_at": "ISO-8601" },
    { "role": "assistant", "content": "...", "metadata": {} }
  ],
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### `meta`

초기 적재와 ECOS 갱신 시각·결과를 저장합니다.

## API

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/data` | 데이터 목록과 필터 조회 |
| `POST` | `/api/data` | 사용자 데이터 추가 |
| `PUT` | `/api/data/{id}` | 데이터 수정 |
| `DELETE` | `/api/data/{id}` | 데이터 소프트 삭제 |
| `POST` | `/api/data/{id}/restore` | 개별 데이터 복원 |
| `POST` | `/api/data/restore-all` | 전체 원본 복원 |
| `GET` | `/api/data/summary` | 통계·최근 추세 요약 |
| `GET` | `/api/data/compare` | 두 기간 비교 |
| `GET` | `/api/data/export` | CSV 또는 JSON 내보내기 |
| `POST` | `/api/data/sync` | ECOS 최신 데이터 확인 |
| `GET` | `/api/data/sync-status` | 마지막 갱신 상태 |
| `POST` | `/api/chat` | 문맥 주입 AI 답변과 자동 저장 |
| `POST` | `/api/conversations` | 대화 저장 |
| `GET` | `/api/conversations` | 대화 목록 |
| `GET` | `/api/conversations/{id}` | 전체 메시지 불러오기 |
| `DELETE` | `/api/conversations/{id}` | 대화 삭제 |

## 테스트

```bash
source .venv/bin/activate
cd backend
pytest -q
```

테스트는 다음을 확인합니다.

- 초기 데이터 396개 적재와 요약 통계
- 데이터 추가·수정·삭제·복원
- 두 기간 비교 결과
- 키가 없을 때의 데이터 기반 채팅
- 전망 형식과 투자 추천 거절
- 주요 API와 대화 자동 저장

## Render 배포

1. GitHub 저장소를 Render에 연결합니다.
2. 저장소 루트의 `render.yaml`을 사용하는 Blueprint를 생성합니다.
3. `OPENAI_API_KEY`, `ECOS_API_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `ALLOWED_ORIGINS`를 등록합니다.
4. 배포 후 `/health`와 `/docs`를 확인합니다.

무료 인스턴스는 비활성 상태 이후 첫 요청이 느릴 수 있습니다. 프론트엔드는 응답이 2.5초 이상 걸리면 서버를 준비하고 있다는 안내를 표시합니다.

## Vercel 배포

1. `frontend` 디렉터리를 Vercel 프로젝트의 Root Directory로 지정합니다.
2. `API_BASE_URL`에 Render 백엔드 주소를 등록합니다.
3. Vercel 배포 주소를 백엔드의 `ALLOWED_ORIGINS`에 추가합니다.
4. 다시 배포하여 대시보드와 채팅 연결을 확인합니다.

빌드 과정에서 환경 변수 `API_BASE_URL`이 정적 `config.js`에 주입됩니다. 프론트엔드는 바닐라 HTML/CSS/JavaScript이며 프레임워크를 사용하지 않습니다.

## 배포 URL

- 프론트엔드: 배포 후 입력
- 백엔드 API: 배포 후 입력
- Swagger UI: 배포 후 입력

## 제출 스크린샷

배포 후 다음 화면을 `docs/screenshots/`에 저장합니다.

- 데이터 요약과 질문·답변이 보이는 AI 채팅
- 수정됨 배지 또는 복원 동작이 보이는 데이터 관리
- 저장된 대화를 다시 불러온 대화 기록
- 기간 비교 그래프
- 방향과 확신 수준이 보이는 전망 답변

## 해석 및 책임 범위

EconScope는 경제 학습과 정보 제공을 위한 서비스이며 투자 조언이 아닙니다. 상관관계는 인과관계를 의미하지 않습니다. 외부 자료를 찾지 못한 경우 그 사실을 안내하고, 저장 데이터와 일반적인 경제 원리를 바탕으로 가능한 설명만 제공합니다.

상세 제품 기준은 [EconScope 최종 서비스 기획서](./ECONSCOPE_PRODUCT_SPEC.md)를 참고하세요.
