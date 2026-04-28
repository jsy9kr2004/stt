"""거래대금 상위 종목 유니버스 선정 (point-in-time).

특정 일자 기준으로 KRX 전 종목 중 단타 적합 보통주만 추려
거래대금 상위 N개를 반환한다.

설계 메모
---------
- pykrx 호출 (네트워크 I/O) 은 ``fetch_market_snapshot`` 에 격리.
- 필터 로직 (``is_common_stock`` / ``is_spac`` / ``filter_universe``) 은 순수 함수
  → 단위 테스트는 pykrx mock 없이 가능.
- 종목명 조회는 비용이 크므로 1차 정량 필터 후 ``annotate_names`` 에서 일괄 조회.
- 관리종목·VI 필터는 pykrx 단독으로 정확히 안 되므로 best-effort 휴리스틱 + TODO.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterable


# ─── 기본 임계값 ──────────────────────────────────────────────────────────────
DEFAULT_TOP_N: int = 200
"""백테스트용 기본 유니버스 사이즈 (plan.md: 200~300)."""

DEFAULT_MIN_MARKET_CAP: int = 50_000_000_000
"""기본 최소 시가총액: 500억원 (CLAUDE.md 기준)."""

SCALPING_MIN_MARKET_CAP: int = 30_000_000_000
"""단타 한정 완화 기준: 300억원."""

_CANDIDATE_OVERSAMPLE: float = 1.5
"""이름 기반 2차 필터에서 탈락할 가능성을 감안한 후보 오버샘플링 배율."""


# ─── 입력 정규화 ──────────────────────────────────────────────────────────────
def _to_yyyymmdd(d: date | datetime | str) -> str:
    """날짜를 pykrx가 받는 ``YYYYMMDD`` 8자리 문자열로 정규화.

    ``"YYYY-MM-DD"`` / ``"YYYYMMDD"`` / ``date`` / ``datetime`` 입력을 허용.
    """
    if isinstance(d, datetime):
        return d.strftime("%Y%m%d")
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    if isinstance(d, str):
        s = d.replace("-", "")
        if len(s) != 8 or not s.isdigit():
            raise ValueError(f"date 문자열은 YYYYMMDD 또는 YYYY-MM-DD 형식이어야 함: {d!r}")
        return s
    raise TypeError(f"지원하지 않는 date 타입: {type(d).__name__}")


# ─── 종목 분류 휴리스틱 (순수 함수) ───────────────────────────────────────────
def is_common_stock(ticker: str) -> bool:
    """보통주 여부.

    KRX 종목코드 6자리 중 마지막 자리가 0이면 보통주, 그 외(5/7/9 등)는 우선주.
    """
    return len(ticker) == 6 and ticker.isdigit() and ticker.endswith("0")


def is_spac(name: str) -> bool:
    """이름에 '스팩' 이 포함되면 SPAC 으로 판단."""
    return "스팩" in name


def is_managed_heuristic(name: str) -> bool:
    """이름 기반 관리·투자경고 휴리스틱 (best-effort).

    KRX 정식 관리종목 리스트는 별도 API 가 필요. 여기서는 종목명에 마커가
    드러나는 케이스만 거른다.

    TODO: KRX 정식 관리종목·투자경고·환기 API 또는 KIND CSV 연동.
    """
    markers = ("관리", "투자경고", "투자위험", "환기")
    return any(m in name for m in markers)


# ─── 필터 (순수 함수) ─────────────────────────────────────────────────────────
def filter_quantitative(
    df: pd.DataFrame,
    *,
    min_market_cap: int,
    excluded_tickers: Iterable[str] | None = None,
) -> pd.DataFrame:
    """이름이 필요 없는 1차 정량 필터.

    Args:
        df: ``ticker``, ``market_cap``, ``trading_value`` 컬럼 보유.
        min_market_cap: 최소 시가총액 (원).
        excluded_tickers: 추가 배제할 ticker 집합 (ETF/ETN 등).
    """
    excluded = set(excluded_tickers or ())
    mask = (
        df["ticker"].map(is_common_stock)
        & (df["market_cap"] >= min_market_cap)
        & ~df["ticker"].isin(excluded)
    )
    return df[mask].copy()


def filter_by_name(df: pd.DataFrame) -> pd.DataFrame:
    """이름 기반 2차 필터 (스팩, 관리종목 휴리스틱)."""
    mask = ~df["name"].map(is_spac) & ~df["name"].map(is_managed_heuristic)
    return df[mask].copy()


def rank_by_trading_value(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """거래대금 내림차순 정렬 후 상위 N개."""
    return (
        df.sort_values("trading_value", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


# ─── pykrx I/O 래퍼 ───────────────────────────────────────────────────────────
def fetch_market_snapshot(yyyymmdd: str) -> pd.DataFrame:
    """pykrx 로 특정 일자의 전 종목 시장 스냅샷을 결합한다.

    Returns:
        ``ticker``, ``close``, ``volume``, ``trading_value``, ``market_cap`` 컬럼 보유.
        휴장일이면 빈 DataFrame.
    """
    from pykrx import stock

    ohlcv = stock.get_market_ohlcv_by_ticker(yyyymmdd, market="ALL")
    cap = stock.get_market_cap_by_ticker(yyyymmdd, market="ALL")

    if ohlcv is None or len(ohlcv) == 0 or cap is None or len(cap) == 0:
        return pd.DataFrame(
            columns=["ticker", "close", "volume", "trading_value", "market_cap"],
        )

    etf_set = set(stock.get_etf_ticker_list(yyyymmdd))
    etn_set = set(stock.get_etn_ticker_list(yyyymmdd))
    excluded = etf_set | etn_set

    merged = ohlcv[["종가", "거래량", "거래대금"]].join(
        cap[["시가총액"]], how="inner"
    )
    merged = merged[~merged.index.isin(excluded)]

    out = merged.reset_index()
    out.columns = ["ticker", "close", "volume", "trading_value", "market_cap"]
    return out


def annotate_names(df: pd.DataFrame) -> pd.DataFrame:
    """``ticker`` 에 대응하는 종목명 컬럼을 추가한다."""
    from pykrx import stock

    out = df.copy()
    out["name"] = out["ticker"].map(stock.get_market_ticker_name)
    return out


# ─── 공개 API ─────────────────────────────────────────────────────────────────
def select_universe(
    date_: date | datetime | str,
    *,
    top_n: int = DEFAULT_TOP_N,
    min_market_cap: int = DEFAULT_MIN_MARKET_CAP,
) -> pd.DataFrame:
    """거래대금 상위 종목 유니버스 (point-in-time).

    Args:
        date_: 기준 일자. 휴장일이면 빈 DataFrame 반환 (호출자가 영업일 처리).
        top_n: 반환할 종목 수.
        min_market_cap: 최소 시가총액 필터 (원). 기본 500억.

    Returns:
        ``ticker``, ``name``, ``close``, ``volume``, ``trading_value``,
        ``market_cap`` 컬럼을 가진 DataFrame. 거래대금 내림차순.
    """
    if top_n <= 0:
        raise ValueError(f"top_n 은 양수여야 함: {top_n}")
    if min_market_cap < 0:
        raise ValueError(f"min_market_cap 은 0 이상이어야 함: {min_market_cap}")

    yyyymmdd = _to_yyyymmdd(date_)
    logger.info(
        f"universe 선정 시작: 일자={yyyymmdd}, top_n={top_n}, "
        f"min_cap={min_market_cap:,}원"
    )

    snapshot = fetch_market_snapshot(yyyymmdd)
    if snapshot.empty:
        logger.warning(f"universe: 시장 데이터 없음 ({yyyymmdd}) — 휴장일 가능성")
        return pd.DataFrame(
            columns=[
                "ticker",
                "name",
                "close",
                "volume",
                "trading_value",
                "market_cap",
            ]
        )

    quant = filter_quantitative(snapshot, min_market_cap=min_market_cap)
    candidate_n = max(top_n + 10, int(top_n * _CANDIDATE_OVERSAMPLE))
    candidates = rank_by_trading_value(quant, top_n=candidate_n)

    named = annotate_names(candidates)
    final = filter_by_name(named)
    final = final.head(top_n).reset_index(drop=True)

    logger.info(
        f"universe 선정 완료: {len(final)}종목 (전체 {len(snapshot)} → "
        f"정량필터 {len(quant)} → 후보 {len(candidates)} → 최종 {len(final)})"
    )
    return final[["ticker", "name", "close", "volume", "trading_value", "market_cap"]]
