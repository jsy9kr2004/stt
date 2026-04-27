# STT — Short Term Trading

한국 주식 단타 ML 보조 시스템.

자동매매가 아닌 **buy / hold / sell 의견을 실시간으로 전달하는 보조 도구**입니다.
사용자는 시스템 알림을 보고 직접 매매를 실행합니다.

## 주요 문서

| 파일 | 내용 |
|------|------|
| [`plan.md`](plan.md) | 전체 설계 (Phase 1/2/3, 마일스톤, 리스크) |
| [`STATE.md`](STATE.md) | 현재 진행 상황 및 다음 태스크 |
| [`CLAUDE.md`](CLAUDE.md) | 작업 규칙 및 코딩 컨벤션 |

## 기술 스택

- **Python 3.11+**
- **ML**: LightGBM, scikit-learn, SHAP, Optuna
- **데이터**: pykrx (과거), 한국투자증권 KIS API (실시간)
- **저장**: Parquet
- **백엔드**: FastAPI + WebSocket (Phase 2)
- **프론트**: React + Vite + TailwindCSS (Phase 2)
- **외부 접근**: Tailscale VPN

## 빠른 시작

> 메인 개발 환경: **WSL (Ubuntu)**. 데이터 파일은 WSL 리눅스 파일시스템(`~/...`)에 두기를 권장 (`/mnt/c/...`는 디스크 IO가 느림).

```bash
# 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate            # WSL / macOS / Linux
# .venv\Scripts\activate             # (Windows 네이티브 시)

# 의존성 설치 (편집 가능 모드)
pip install -e ".[dev]"

# 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 KIS API 키 등을 입력

# 스모크 테스트
pytest
```

## 진행 단계

- [x] Phase 0 — 프로젝트 셋업
- [ ] Phase 1 — 연구 인프라 (데이터·피처·라벨·모델·백테스트)
- [ ] Phase 2 — 실시간 신호 시스템 + 대시보드
- [ ] Phase 3 — 운영 및 고도화

상세는 [`plan.md`](plan.md) 참조.

## 주의

- 본 시스템은 **개인 연구·학습 용도**의 매매 보조 도구입니다.
- 실거래에 사용하기 전 충분한 모의 매매 검증이 필요합니다.
- 투자 손실에 대한 책임은 전적으로 사용자에게 있습니다.
