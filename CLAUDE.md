# CLAUDE.md — STT 프로젝트 작업 규칙

> 이 파일은 Claude 세션이 시작될 때 자동으로 로드됩니다. 프로젝트의 불변 컨텍스트와 작업 규칙을 담습니다.

## 프로젝트 정체성

**STT (Short Term Trading)** — 한국 주식 단타 ML 보조 시스템

- 자동매매 아님. 사용자가 직접 매매. 시스템은 buy/hold/sell 의견을 실시간 전달.
- 핵심 정체성: **개인 트레이딩 연구실 + 실시간 신호 보조**
- 상세 설계: `plan.md` 참조

## 현재 상태 확인

작업 시작 전 반드시 다음 순서로 확인:

1. `STATE.md` — 현재 마일스톤·진행 상황·다음 태스크
2. `git log --oneline -10` — 최근 커밋 흐름
3. `git status` — 작업 트리 상태

## 실행 환경

- **개발·운영 환경**: WSL (Ubuntu)
- 데이터·코드는 **WSL 리눅스 파일시스템**(`~/stt`)에 위치 권장
  - `/mnt/c/...` 경유는 디스크 IO 병목 + 권한 이슈 발생 가능
- Python·shell 명령은 모두 Linux 기준으로 작성

## 기술 스택 (확정)

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| 백엔드 | FastAPI + Uvicorn + asyncio |
| ML | LightGBM (메인), scikit-learn (보조) |
| 기술적 지표 | pandas-ta |
| 데이터 처리 | pandas, polars, numpy |
| 데이터 저장 | **Parquet** (SQLite 아님) |
| 데이터 소스 | KIS API (실시간), pykrx (과거), DART (공시·Phase 3) |
| 프론트엔드 | React + Vite + TailwindCSS (Phase 2 이후) |
| 차트 | TradingView Lightweight Charts |
| 외부 접근 | Tailscale VPN |
| 알림 | Web Push API (VAPID) |

## 디렉토리 구조 (src layout)

```
stt/
├── data/                # 수집 데이터 (gitignore)
│   ├── raw/             # pykrx 원본
│   ├── features/        # 피처 엔지니어링 결과
│   └── labels/          # Triple Barrier 라벨
├── src/
│   └── stt/             # 메인 패키지 (import 시 `from stt.X import ...`)
│       ├── __init__.py
│       ├── config.py        # pydantic-settings 기반 설정
│       ├── logging_setup.py # loguru 기본 설정
│       ├── collectors/      # KIS, pykrx, DART 데이터 수집
│       ├── features/        # 피처 엔지니어링
│       ├── labels/          # Triple Barrier 라벨링
│       ├── models/          # 학습·추론
│       ├── backtest/        # 워크포워드 백테스트
│       ├── api/             # FastAPI 서버 (Phase 2)
│       └── notifier/        # 웹푸시 (Phase 2)
├── notebooks/           # 분석·실험 (.gitkeep)
├── tests/               # pytest
├── frontend/            # React 앱 (Phase 2)
├── pyproject.toml       # 의존성·도구 설정
├── .env.example         # 환경 변수 템플릿
├── .gitignore
├── README.md
├── plan.md              # 전체 설계 문서
├── STATE.md             # 현재 진행 상황 (반드시 갱신)
└── CLAUDE.md            # 이 파일
```

> **Import 규칙**: 항상 `from stt.<sub> import <X>` 형태. `from src...` 금지.

## 작업 규칙

### 절대 규칙 (위반 금지)

1. **`main` 브랜치에 직접 푸시 금지**. 항상 작업 브랜치에서.
2. **테스트 실패 시 커밋·푸시 금지**. 막힌 지점은 STATE.md에 기록.
3. **자동매매 코드 작성 금지**. 시스템은 신호 생성·표시까지만.
4. **API 키·계좌정보 커밋 금지**. `.env` 사용, `.gitignore` 필수.
5. **데이터 누설(look-ahead bias) 금지**. 시점 t의 피처는 시점 t 이전 정보만 사용.
6. **백테스트는 워크포워드 방식**. 단순 train/test split 금지.
7. **거래 비용 반영**. 수수료 + 세금(0.18%) + 슬리피지 누락 금지.

### 강한 권장 사항

- **각 모듈은 단위 테스트와 함께** 작성. 테스트 없는 코드는 신뢰 불가.
- **타입 힌트 적극 사용**. 특히 데이터 형태(DataFrame 컬럼 명세).
- **함수는 짧게**. 한 함수가 한 가지 일만.
- **상수·설정은 `stt.config.settings`에** 모아두기. 매직 넘버 금지.
- **로깅은 loguru**로 통일.
- **새 의존성 추가 시 STATE.md에 기록**.

### 코드 스타일

- 포맷터: **ruff** (black 호환)
- 린터: **ruff**
- import 정렬: ruff
- 한 줄 길이: 100자
- docstring: Google 스타일 (필요한 경우만, 자명한 함수에는 불필요)

### 커밋 규칙

- 메시지 형식: `<type>: <한국어 요약>`
  - type: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `data`
  - 예: `feat: pykrx 분봉 수집기 구현`
- **한 커밋은 한 가지 변경**. 무관한 변경 섞지 않기.
- 작업 완료 시 항상 STATE.md 갱신 커밋도 함께.

### 브랜치 전략

- 메인 작업 브랜치: 현재 진행 중인 브랜치 확인 후 사용
- 기능별 작업: `feat/<기능명>` (예: `feat/pykrx-collector`)
- 자동 실행 작업: `auto/<날짜>-<태스크>` 형태로 분리

## 데이터 관련 주의사항

- **거래대금 상위 종목은 매일 동적 재선정** (point-in-time)
- **Survivorship bias 회피**: 상장폐지·관리종목 history 포함
- **시총 500억 이상** 필터 (단타 한정 시 300억까지 허용)
- **제외 대상**: 관리·투자경고·VI 발동·우선주·스팩·ETF·ETN·신규상장 1개월 이내
- **유니버스 사이즈**: 실시간 100 / 백테스트 200~300 / 워치리스트 30~50

## 모델 관련 주의사항

- **LightGBM 우선**, LSTM·Transformer·강화학습은 비추 (과적합)
- **Triple Barrier Method**로 라벨링 (BUY/HOLD/SELL)
- **3개 시간대 병렬 학습**: 1분봉(스캘핑) / 5분봉(데이트레이딩) / 30분봉(스윙)
- **SHAP**으로 피처 중요도 확인, 노이즈 피처 제거
- **하이퍼파라미터 튜닝**: Optuna

## 자동 실행 모드 (헤드리스 작업)

이 프로젝트는 Pro 플랜 5시간 윈도우 갱신마다 자동 실행될 수 있음.
헤드리스 모드(`claude -p ...`)에서 동작 시 추가 규칙:

1. **한 번 실행 = 1개 마이크로 태스크만**. 욕심내지 말 것.
2. STATE.md의 "다음 태스크" 1순위만 처리.
3. 막히거나 모호하면 즉시 중단 + STATE.md에 막힌 지점 상세 기록.
4. 새 라이브러리·API 첫 사용은 자동 실행에서 회피, 사람 리뷰 대기.
5. 결과는 별도 브랜치에 푸시. main·작업 브랜치 직접 변경 금지.
6. 비용 의식: 불필요한 탐색·반복 실행 금지.

## 문서 갱신 의무

작업 종료 시 반드시 갱신:
- **STATE.md**: 진행 상황·다음 태스크·결정 사항
- 큰 결정이 있으면 **plan.md**도 갱신

## 참고 문서

- `plan.md`: 전체 설계 (Phase 1/2/3, 마일스톤, 리스크)
- `STATE.md`: 현재 진행 상황 (자주 갱신)
- KIS Developers: https://apiportal.koreainvestment.com/
- pykrx: https://github.com/sharebook-kr/pykrx
- DART OpenAPI: https://opendart.fss.or.kr/
