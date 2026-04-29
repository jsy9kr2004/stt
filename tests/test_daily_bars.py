"""``stt.collectors.daily_bars`` 단위 테스트.

pykrx 호출은 monkeypatch 로 교체. Parquet I/O 는 ``tmp_path`` 위에서 검증.
"""

from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stt.collectors import daily_bars


# ─── 헬퍼: pykrx 시뮬레이션 ───────────────────────────────────────────────────
def _make_pykrx_frame(
    days: list[str],
    *,
    open_: int = 100,
    high: int = 110,
    low: int = 90,
    close: int = 105,
    volume: int = 10_000,
    trading_value: int = 1_000_000,
    change: float = 0.5,
) -> pd.DataFrame:
    """pykrx 출력 모사: 한글 컬럼 + DatetimeIndex."""
    idx = pd.to_datetime(days)
    return pd.DataFrame(
        {
            "시가": [open_] * len(days),
            "고가": [high] * len(days),
            "저가": [low] * len(days),
            "종가": [close] * len(days),
            "거래량": [volume] * len(days),
            "거래대금": [trading_value] * len(days),
            "등락률": [change] * len(days),
        },
        index=idx,
    )


class _FakeStock:
    def __init__(self, frame: pd.DataFrame, calls: list[tuple[str, str, str]]) -> None:
        self.frame = frame
        self.calls = calls

    def get_market_ohlcv(self, fromdate: str, todate: str, ticker: str) -> pd.DataFrame:
        self.calls.append((fromdate, todate, ticker))
        # 호출 범위에 해당하는 부분만 반환
        if self.frame.empty:
            return self.frame
        f = pd.to_datetime(fromdate)
        t = pd.to_datetime(todate)
        return self.frame.loc[(self.frame.index >= f) & (self.frame.index <= t)].copy()


@pytest.fixture
def fake_pykrx(monkeypatch: pytest.MonkeyPatch):
    """pykrx 모듈을 가짜로 교체. 픽스처 자체가 (frame setter, calls list) 컨테이너."""
    state: dict = {"calls": []}

    def install(frame: pd.DataFrame) -> list[tuple[str, str, str]]:
        fake = _FakeStock(frame, state["calls"])
        pykrx_pkg = types.ModuleType("pykrx")
        pykrx_pkg.stock = fake  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pykrx", pykrx_pkg)
        monkeypatch.setitem(sys.modules, "pykrx.stock", fake)
        return state["calls"]

    return install


# ─── 정규화 ───────────────────────────────────────────────────────────────────
class TestNormalize:
    def test_columns_and_dtypes(self) -> None:
        raw = _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        out = daily_bars._normalize_pykrx_frame(raw)
        assert list(out.columns) == daily_bars.COLUMNS
        assert pd.api.types.is_datetime64_any_dtype(out["date"])
        assert len(out) == 2

    def test_empty_passthrough_via_fetch(self, fake_pykrx) -> None:
        fake_pykrx(pd.DataFrame())
        out = daily_bars.fetch_daily_bars("005930", "20260101", "20260131")
        assert out.empty
        assert list(out.columns) == daily_bars.COLUMNS


# ─── merge ────────────────────────────────────────────────────────────────────
class TestMerge:
    def test_dedupe_keeps_new(self) -> None:
        old = daily_bars._normalize_pykrx_frame(
            _make_pykrx_frame(["2026-01-02", "2026-01-03"], close=100)
        )
        new = daily_bars._normalize_pykrx_frame(
            _make_pykrx_frame(["2026-01-03", "2026-01-04"], close=999)
        )
        merged = daily_bars.merge_bars(old, new)
        assert len(merged) == 3
        # 2026-01-03 은 new 의 close=999 가 우선
        row = merged.loc[merged["date"] == pd.Timestamp("2026-01-03")].iloc[0]
        assert row["close"] == 999

    def test_sort(self) -> None:
        a = daily_bars._normalize_pykrx_frame(_make_pykrx_frame(["2026-01-05"]))
        b = daily_bars._normalize_pykrx_frame(_make_pykrx_frame(["2026-01-02"]))
        merged = daily_bars.merge_bars(a, b)
        assert list(merged["date"]) == [
            pd.Timestamp("2026-01-02"),
            pd.Timestamp("2026-01-05"),
        ]

    def test_both_empty(self) -> None:
        out = daily_bars.merge_bars(
            pd.DataFrame(columns=daily_bars.COLUMNS),
            pd.DataFrame(columns=daily_bars.COLUMNS),
        )
        assert out.empty
        assert list(out.columns) == daily_bars.COLUMNS


# ─── validate ─────────────────────────────────────────────────────────────────
class TestValidate:
    def _good(self) -> pd.DataFrame:
        return daily_bars._normalize_pykrx_frame(
            _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        )

    def test_clean(self) -> None:
        assert daily_bars.validate_bars(self._good()) == []

    def test_empty(self) -> None:
        assert daily_bars.validate_bars(pd.DataFrame(columns=daily_bars.COLUMNS)) == []

    def test_missing_column(self) -> None:
        df = self._good().drop(columns=["high"])
        errors = daily_bars.validate_bars(df)
        assert any("missing columns" in e for e in errors)

    def test_high_lt_low(self) -> None:
        df = self._good()
        df.loc[0, "high"] = 1
        df.loc[0, "low"] = 100
        assert "high < low" in daily_bars.validate_bars(df)

    def test_negative_volume(self) -> None:
        df = self._good()
        df.loc[0, "volume"] = -1
        assert "negative volume" in daily_bars.validate_bars(df)

    def test_duplicate_date(self) -> None:
        df = self._good()
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        errors = daily_bars.validate_bars(df)
        assert "duplicate dates present" in errors


# ─── Parquet I/O ──────────────────────────────────────────────────────────────
class TestParquetIO:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        df = daily_bars._normalize_pykrx_frame(
            _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        )
        path = daily_bars.save_daily_bars(df, "005930", root=tmp_path)
        assert path.exists()
        loaded = daily_bars.load_existing("005930", root=tmp_path)
        assert len(loaded) == 2
        assert list(loaded.columns) == daily_bars.COLUMNS
        assert pd.api.types.is_datetime64_any_dtype(loaded["date"])

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        loaded = daily_bars.load_existing("999990", root=tmp_path)
        assert loaded.empty
        assert list(loaded.columns) == daily_bars.COLUMNS


# ─── update_daily_bars ────────────────────────────────────────────────────────
class TestUpdateDailyBars:
    def test_initial_fetch_uses_history_years(
        self, tmp_path: Path, fake_pykrx
    ) -> None:
        frame = _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        calls = fake_pykrx(frame)

        daily_bars.update_daily_bars(
            "005930",
            target_date="2026-01-03",
            history_years=1,
            root=tmp_path,
        )
        assert len(calls) == 1
        from_d, to_d, ticker = calls[0]
        assert ticker == "005930"
        assert to_d == "20260103"
        assert from_d == "20250103"  # 1년 전

    def test_incremental_only_fetches_gap(
        self, tmp_path: Path, fake_pykrx
    ) -> None:
        # 1차 수집
        first_frame = _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        calls = fake_pykrx(first_frame)
        daily_bars.update_daily_bars(
            "005930",
            target_date="2026-01-03",
            history_years=1,
            root=tmp_path,
        )
        calls.clear()

        # 2차: 2026-01-06 까지 — 1/04 부터만 fetch (재수집되면 close 가 덮어써짐을 검증)
        second_frame = _make_pykrx_frame(
            ["2026-01-02", "2026-01-03", "2026-01-06"],
            open_=200,
            high=220,
            low=180,
            close=210,
        )
        fake_pykrx(second_frame)
        merged = daily_bars.update_daily_bars(
            "005930",
            target_date="2026-01-06",
            history_years=1,
            root=tmp_path,
        )
        assert len(calls) == 1
        from_d, to_d, _ = calls[0]
        assert from_d == "20260104"
        assert to_d == "20260106"
        assert len(merged) == 3
        # 기존 1/02·1/03 은 close=105 유지 (재수집 안 됨), 1/06 은 close=210
        assert merged.loc[merged["date"] == pd.Timestamp("2026-01-03"), "close"].iloc[0] == 105
        assert merged.loc[merged["date"] == pd.Timestamp("2026-01-06"), "close"].iloc[0] == 210

    def test_skip_when_already_up_to_date(
        self, tmp_path: Path, fake_pykrx
    ) -> None:
        frame = _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        calls = fake_pykrx(frame)
        daily_bars.update_daily_bars(
            "005930",
            target_date="2026-01-03",
            root=tmp_path,
        )
        calls.clear()
        # 동일 target — fetch 호출되지 않아야 함
        daily_bars.update_daily_bars(
            "005930",
            target_date="2026-01-03",
            root=tmp_path,
        )
        assert calls == []

    def test_validation_failure_raises(
        self, tmp_path: Path, fake_pykrx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        frame = _make_pykrx_frame(["2026-01-02"], high=10, low=100)  # high < low
        fake_pykrx(frame)
        with pytest.raises(ValueError, match="검증 실패"):
            daily_bars.update_daily_bars(
                "005930",
                target_date="2026-01-02",
                root=tmp_path,
            )
        # 검증 실패 시 파일 저장 안 됨
        assert not daily_bars.daily_parquet_path("005930", tmp_path).exists()


# ─── update_many ──────────────────────────────────────────────────────────────
class TestUpdateMany:
    def test_summary_counts(self, tmp_path: Path, fake_pykrx) -> None:
        frame = _make_pykrx_frame(["2026-01-02", "2026-01-03"])
        fake_pykrx(frame)
        summary = daily_bars.update_many(
            ["005930", "000660"],
            target_date="2026-01-03",
            root=tmp_path,
        )
        assert summary == {"005930": 2, "000660": 2}

    def test_failure_marked_negative(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # fetch_daily_bars 가 한 ticker 에서만 예외 던지도록
        original = daily_bars.fetch_daily_bars

        def flaky(ticker: str, fromdate: str, todate: str) -> pd.DataFrame:
            if ticker == "BAD":
                raise RuntimeError("boom")
            return daily_bars._normalize_pykrx_frame(
                _make_pykrx_frame(["2026-01-02"])
            )

        monkeypatch.setattr(daily_bars, "fetch_daily_bars", flaky)
        try:
            summary = daily_bars.update_many(
                ["005930", "BAD"],
                target_date="2026-01-02",
                root=tmp_path,
            )
        finally:
            monkeypatch.setattr(daily_bars, "fetch_daily_bars", original)
        assert summary["005930"] == 1
        assert summary["BAD"] == -1


# ─── 날짜 유틸 ────────────────────────────────────────────────────────────────
class TestDateUtils:
    def test_years_back_normal(self) -> None:
        assert daily_bars._years_back(date(2026, 4, 28), 1) == date(2025, 4, 28)

    def test_years_back_leap_to_non_leap(self) -> None:
        # 2024-02-29 → 2023-02-28
        assert daily_bars._years_back(date(2024, 2, 29), 1) == date(2023, 2, 28)
