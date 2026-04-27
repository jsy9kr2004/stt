# STATE.md — STT 프로젝트 진행 상태

> 이 파일은 **자주 갱신**되는 살아있는 문서입니다. 매 작업 종료 시 반드시 업데이트.

**마지막 갱신**: 2026-04-27 (Phase 1 진입 직전)
**현재 브랜치**: `claude/create-plan-document-mtQhj`

---

## 현재 위치

- **Phase**: 0 (프로젝트 셋업)
- **Milestone**: M0 (프로젝트 인프라 준비)
- **단계**: plan.md·CLAUDE.md·STATE.md 작성 완료, 코드 작성 직전

---

## 큰 그림 (Phase별 요약)

- [x] **Phase 0**: 프로젝트 셋업 (현재)
- [ ] **Phase 1**: 연구 인프라 — 데이터·피처·라벨·모델·백테스트
- [ ] **Phase 2**: 실시간 신호 시스템 — KIS API + 대시보드
- [ ] **Phase 3**: 운영 및 고도화

---

## Phase 1 마일스톤 (다가오는 작업)

상세 사항은 `plan.md` 참조.

- [ ] **M1**: 데이터 수집 파이프라인 + 거래대금 상위 200~300 종목 1년 분봉 확보
- [ ] **M2**: 피처 엔지니어링 + Triple Barrier 라벨링
- [ ] **M3**: 3개 시간대 LightGBM 모델 학습
- [ ] **M4**: 워크포워드 백테스트 엔진 + 첫 결과 분석
- [ ] **M5**: "내게 맞는 시간대·종목" 결정 (Phase 1 완료)

---

## 다음 태스크 (우선순위 순)

> 헤드리스 자동 실행은 **이 목록의 1순위 1개**만 처리.

### 🟢 즉시 진행 가능

1. **개발 환경 셋업**
   - Python 3.11+ 가상환경 (venv 또는 uv)
   - `pyproject.toml` 또는 `requirements.txt` 작성
   - 핵심 의존성 설치: `pykrx`, `lightgbm`, `pandas-ta`, `pandas`, `polars`, `loguru`, `pydantic`, `ruff`, `pytest`
   - `.gitignore` 작성 (data/, __pycache__/, .env, .venv 등)
   - `.env.example` 템플릿
   - 완료 기준: `python -c "import pykrx, lightgbm, pandas_ta"` 무오류

2. **프로젝트 디렉토리 구조 생성**
   - `src/{collectors,features,labels,models,backtest,api,notifier}/__init__.py`
   - `tests/` 동일 구조
   - `notebooks/` 디렉토리
   - `src/config.py` 빈 스켈레톤 (상수 모음 예정)
   - 완료 기준: `pytest` 실행 시 0 tests, 0 errors

3. **로깅·설정 인프라**
   - `src/config.py`: 데이터 경로·KIS API 환경변수 로드(pydantic-settings)
   - `src/logging_setup.py`: loguru 기본 설정
   - 완료 기준: 다른 모듈에서 `from src.config import settings` 동작

### 🟡 M1 본 작업

4. **종목 유니버스 선정 모듈** (`src/collectors/universe.py`)
   - pykrx로 거래대금 상위 N개 종목 선정
   - 시총·관리종목·우선주·ETF 등 필터링 적용
   - point-in-time 동작 (특정 일자 기준 유니버스 반환)
   - 단위 테스트 포함

5. **분봉 데이터 수집기** (`src/collectors/minute_bars.py`)
   - pykrx로 5분봉 1년치 수집
   - Parquet 저장 (종목별 또는 일자별 파티션)
   - 증분 갱신 지원
   - 결측·이상치 검증

6. **일봉/30분봉 수집기**
   - 동일 구조로 일봉, 30분봉 수집

### 🔴 후속 (M2 진입 후)

7. 피처 엔지니어링 파이프라인
8. Triple Barrier 라벨링
9. 학습 파이프라인
10. 워크포워드 백테스트 엔진

---

## 현재 막힌 지점 / 결정 보류

- [ ] **KIS API 앱키 발급**: 사용자가 한국투자증권 계좌·앱키 발급 필요 (Phase 2 시작 전까지)
- [ ] **자동화 인프라 셋업 시점**: SessionStart 훅·헤드리스 스케줄러 설정은 M1 일부 완료 후 결정
- [ ] **프론트엔드 프레임워크 최종 결정**: Phase 2 진입 시 결정 (React vs SvelteKit)

---

## 결정 로그 (Decision Log)

| 날짜 | 결정 | 근거 |
|------|------|------|
| 2026-04-27 | 데이터 저장: Parquet 확정 | 열 기반 압축, 분봉 read/write 성능 우위 |
| 2026-04-27 | 종목 유니버스: 거래대금 기반 동적 선정 | 한국 단타 업계 통설, 코스피200 같은 인덱스 기반은 단타에 부적합 |
| 2026-04-27 | 모델: LightGBM 메인 | 해석 가능성, 금융 ML 워크호스, 과적합 저항 |
| 2026-04-27 | 라벨링: Triple Barrier Method | Lopez de Prado 방법, BUY/HOLD/SELL 명확한 라벨 |
| 2026-04-27 | 시간대: 3개 병렬 (1분/5분/30분) | 사용자가 어떤 트레이딩 스타일이 맞는지 발견하기 위함 |
| 2026-04-27 | 데이터 소스: KIS API + pykrx | KIS는 실시간(WebSocket) + 크로스플랫폼, pykrx는 무료 과거 데이터 |
| 2026-04-27 | 외부 접근: Tailscale | 무료, 5분 셋업, 보안 우수 |

---

## 의존성·라이브러리 변경 이력

(추가 시 기록)

---

## 자동 실행 로그

(헤드리스 자동 작업 결과 기록)

| 일시 | 태스크 | 결과 | 브랜치 |
|------|--------|------|--------|
| - | - | - | - |

---

## 다음 세션 시작 시 체크리스트

1. [ ] 이 STATE.md 정독
2. [ ] `git log --oneline -10` 확인
3. [ ] `git status` 확인
4. [ ] "다음 태스크" 1순위 확인
5. [ ] 시작 전 사용자에게 한 줄 요약 보고
