"""``stt.collectors.universe`` 단위 테스트.

pykrx 의존 부분은 monkeypatch 로 교체하여 네트워크 없이 검증한다.
순수 필터 함수는 별도 픽스처 없이 직접 호출.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from stt.collectors import universe


# ─── _to_yyyymmdd ─────────────────────────────────────────────────────────────
class TestToYyyymmdd:
    def test_dash_form(self) -> None:
        assert universe._to_yyyymmdd("2026-04-27") == "20260427"

    def test_compact_form(self) -> None:
        assert universe._to_yyyymmdd("20260427") == "20260427"

    def test_date_object(self) -> None:
        assert universe._to_yyyymmdd(date(2026, 4, 27)) == "20260427"

    def test_datetime_object(self) -> None:
        assert universe._to_yyyymmdd(datetime(2026, 4, 27, 9, 30)) == "20260427"

    @pytest.mark.parametrize("bad", ["2026/04/27", "26-04-27", "2026-4-27", "abcd1234"])
    def test_invalid_string(self, bad: str) -> None:
        with pytest.raises(ValueError):
            universe._to_yyyymmdd(bad)

    def test_invalid_type(self) -> None:
        with pytest.raises(TypeError):
            universe._to_yyyymmdd(20260427)  # type: ignore[arg-type]


# ─── 분류 휴리스틱 ────────────────────────────────────────────────────────────
class TestIsCommonStock:
    @pytest.mark.parametrize("ticker", ["005930", "000660", "035720"])
    def test_common(self, ticker: str) -> None:
        assert universe.is_common_stock(ticker)

    @pytest.mark.parametrize("ticker", ["005935", "005937", "005939"])
    def test_preferred(self, ticker: str) -> None:
        assert not universe.is_common_stock(ticker)

    @pytest.mark.parametrize("bad", ["", "12345", "1234567", "00593A", "abcdef"])
    def test_invalid_format(self, bad: str) -> None:
        assert not universe.is_common_stock(bad)


def test_is_spac() -> None:
    assert universe.is_spac("미래에셋비전스팩1호")
    assert not universe.is_spac("삼성전자")


def test_is_managed_heuristic() -> None:
    assert universe.is_managed_heuristic("XXX(관리)")
    assert universe.is_managed_heuristic("YYY(투자경고)")
    assert not universe.is_managed_heuristic("삼성전자")


# ─── 필터·랭킹 ────────────────────────────────────────────────────────────────
@pytest.fixture
def sample_snapshot() -> pd.DataFrame:
    """가공이 끝난 시장 스냅샷 (이름 미부착)."""
    return pd.DataFrame(
        [
            # ticker, close, volume, trading_value, market_cap
            ("005930", 80_000, 1_000_000, 80_000_000_000, 500_000_000_000_000),  # 삼성전자
            ("000660", 130_000, 800_000, 100_000_000_000, 100_000_000_000_000),  # SK하이닉스
            ("005935", 70_000, 500_000, 30_000_000_000, 50_000_000_000_000),  # 우선주
            ("123450", 5_000, 200_000, 50_000_000_000, 60_000_000_000),  # 시총 600억 보통주
            ("234560", 1_000, 100_000, 10_000_000_000, 10_000_000_000),  # 시총 100억 (탈락)
            ("345670", 2_000, 300_000, 5_000_000_000, 80_000_000_000),  # 보통주이지만 거래대금 낮음
        ],
        columns=["ticker", "close", "volume", "trading_value", "market_cap"],
    )


class TestFilterQuantitative:
    def test_excludes_preferred_and_low_cap(
        self, sample_snapshot: pd.DataFrame
    ) -> None:
        out = universe.filter_quantitative(sample_snapshot, min_market_cap=50_000_000_000)
        assert set(out["ticker"]) == {"005930", "000660", "123450", "345670"}

    def test_excluded_tickers_dropped(self, sample_snapshot: pd.DataFrame) -> None:
        out = universe.filter_quantitative(
            sample_snapshot,
            min_market_cap=50_000_000_000,
            excluded_tickers={"123450"},
        )
        assert "123450" not in set(out["ticker"])

    def test_min_cap_strict_inequality(self, sample_snapshot: pd.DataFrame) -> None:
        out = universe.filter_quantitative(
            sample_snapshot, min_market_cap=80_000_000_001
        )
        assert "345670" not in set(out["ticker"])  # 정확히 800억은 컷아웃


def test_filter_by_name_drops_spac_and_managed() -> None:
    df = pd.DataFrame(
        {
            "ticker": ["005930", "111110", "222220"],
            "name": ["삼성전자", "에이비스팩2호", "XXX(관리)"],
            "trading_value": [100, 50, 30],
        }
    )
    out = universe.filter_by_name(df)
    assert set(out["ticker"]) == {"005930"}


def test_rank_by_trading_value_returns_topn(sample_snapshot: pd.DataFrame) -> None:
    out = universe.rank_by_trading_value(sample_snapshot, top_n=2)
    assert list(out["ticker"]) == ["000660", "005930"]
    assert len(out) == 2


# ─── select_universe (pykrx mock 통합) ────────────────────────────────────────
class _FakePykrxStock:
    """pykrx.stock 의 일부 함수를 흉내내는 가짜 모듈."""

    def __init__(
        self,
        ohlcv: pd.DataFrame,
        cap: pd.DataFrame,
        names: dict[str, str],
        etf: list[str] | None = None,
        etn: list[str] | None = None,
    ) -> None:
        self._ohlcv = ohlcv
        self._cap = cap
        self._names = names
        self._etf = etf or []
        self._etn = etn or []

    def get_market_ohlcv_by_ticker(self, _date: str, market: str = "ALL") -> pd.DataFrame:
        return self._ohlcv

    def get_market_cap_by_ticker(self, _date: str, market: str = "ALL") -> pd.DataFrame:
        return self._cap

    def get_etf_ticker_list(self, _date: str) -> list[str]:
        return list(self._etf)

    def get_etn_ticker_list(self, _date: str) -> list[str]:
        return list(self._etn)

    def get_market_ticker_name(self, ticker: str) -> str:
        return self._names.get(ticker, ticker)


@pytest.fixture
def mock_pykrx(monkeypatch: pytest.MonkeyPatch) -> _FakePykrxStock:
    """전형적 시장 스냅샷을 흉내내는 pykrx mock."""
    ohlcv = pd.DataFrame(
        {
            "종가": [80_000, 130_000, 70_000, 5_000, 1_000, 2_000, 8_000, 9_000],
            "거래량": [
                1_000_000,
                800_000,
                500_000,
                200_000,
                100_000,
                300_000,
                400_000,
                700_000,
            ],
            "거래대금": [
                80_000_000_000,
                100_000_000_000,
                30_000_000_000,
                50_000_000_000,
                10_000_000_000,
                5_000_000_000,
                70_000_000_000,
                90_000_000_000,
            ],
        },
        index=pd.Index(
            ["005930", "000660", "005935", "123450", "234560", "345670", "111110", "999990"],
            name="티커",
        ),
    )
    cap = pd.DataFrame(
        {
            "시가총액": [
                500_000_000_000_000,  # 005930 — 통과
                100_000_000_000_000,  # 000660 — 통과
                50_000_000_000_000,   # 005935 — 우선주
                60_000_000_000,       # 123450 — 600억 보통주
                10_000_000_000,       # 234560 — 100억 (시총 컷)
                80_000_000_000,       # 345670 — 800억, 거래대금 낮음
                70_000_000_000,       # 111110 — 스팩 (이름 컷)
                200_000_000_000,      # 999990 — ETF (excluded)
            ],
        },
        index=pd.Index(
            ["005930", "000660", "005935", "123450", "234560", "345670", "111110", "999990"],
            name="티커",
        ),
    )
    names = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "005935": "삼성전자우",
        "123450": "어떤보통주",
        "234560": "소형주",
        "345670": "다른보통주",
        "111110": "에이비스팩2호",
        "999990": "ETF상품",
    }
    fake = _FakePykrxStock(ohlcv=ohlcv, cap=cap, names=names, etf=["999990"], etn=[])

    import sys
    import types

    pykrx_pkg = types.ModuleType("pykrx")
    pykrx_pkg.stock = fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pykrx", pykrx_pkg)
    monkeypatch.setitem(sys.modules, "pykrx.stock", fake)
    return fake


def test_select_universe_filters_and_ranks(mock_pykrx: _FakePykrxStock) -> None:
    result = universe.select_universe(
        "2026-04-27",
        top_n=10,
        min_market_cap=universe.DEFAULT_MIN_MARKET_CAP,
    )

    # 보통주 + 시총통과 + ETF 제외 + 스팩 제외 → 005930, 000660, 123450, 345670
    assert set(result["ticker"]) == {"005930", "000660", "123450", "345670"}
    # 거래대금 정렬 검증
    assert list(result["ticker"]) == ["000660", "005930", "123450", "345670"]
    # 컬럼 명세 검증
    assert list(result.columns) == [
        "ticker",
        "name",
        "close",
        "volume",
        "trading_value",
        "market_cap",
    ]
    assert result.loc[result["ticker"] == "005930", "name"].iloc[0] == "삼성전자"


def test_select_universe_top_n_truncates(mock_pykrx: _FakePykrxStock) -> None:
    result = universe.select_universe("20260427", top_n=2)
    assert len(result) == 2
    assert list(result["ticker"]) == ["000660", "005930"]


def test_select_universe_empty_on_holiday(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePykrxStock(
        ohlcv=pd.DataFrame(),
        cap=pd.DataFrame(),
        names={},
    )
    import sys
    import types

    pykrx_pkg = types.ModuleType("pykrx")
    pykrx_pkg.stock = fake  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pykrx", pykrx_pkg)
    monkeypatch.setitem(sys.modules, "pykrx.stock", fake)

    result = universe.select_universe("20260101")
    assert result.empty
    assert list(result.columns) == [
        "ticker",
        "name",
        "close",
        "volume",
        "trading_value",
        "market_cap",
    ]


def test_select_universe_invalid_args() -> None:
    with pytest.raises(ValueError):
        universe.select_universe("20260427", top_n=0)
    with pytest.raises(ValueError):
        universe.select_universe("20260427", min_market_cap=-1)
