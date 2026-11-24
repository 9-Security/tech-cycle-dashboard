import json
from datetime import datetime, timezone

import pytest

from tcd import close_fill
from tcd.sources import yahoo
from tcd.sources.http import FetchError

OFF = -18000  # EST
DAY = [datetime(2026, 11, d, 14, 30, tzinfo=timezone.utc) for d in (19, 20, 23)]
END_23 = int(datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc).timestamp())


def payload(last_close=None, mtime=END_23, price=162.38, events=None):
    return json.dumps({"chart": {"result": [{
        "timestamp": [int(d.timestamp()) for d in DAY],
        "meta": {"gmtoffset": OFF, "regularMarketPrice": price, "regularMarketTime": mtime,
                 "currentTradingPeriod": {"regular": {"start": END_23 - 23400, "end": END_23}}},
        "indicators": {"quote": [{"close": [160.69, 149.01, last_close]}],
                       "adjclose": [{"adjclose": [160.69, 149.01, last_close]}]},
        **({"events": events} if events else {})}]}}).encode()


def nasdaq(price="$162.35", when="Closed at Nov 23, 2026 4:00 PM ET"):
    return json.dumps({"data": {"secondaryData": {"lastSalePrice": price, "lastTradeTimestamp": when}}}).encode()


class Store:
    def __init__(self, body=None, fail=False):
        self.body, self.fail, self.calls = body, fail, 0

    def get(self, name, url, headers=None, params=None):
        self.calls += 1
        if self.fail:
            raise FetchError("down")
        return self.body


@pytest.fixture(autouse=True)
def _reset():
    close_fill.reset()


def test_fills_when_nasdaq_confirms_the_same_day():
    df = yahoo.parse_chart(payload(), "XLK", Store(nasdaq()))
    assert str(df.index[-1].date()) == "2026-11-23" and df["adjclose"].iloc[-1] == 162.38
    assert close_fill.LOG[0]["filled"] and close_fill.LOG[0]["nasdaq"] == 162.35


@pytest.mark.parametrize("store,reason", [
    (Store(nasdaq(price="$165.00")), "differs"),
    (Store(nasdaq(when="Closed at Nov 20, 2026 4:00 PM ET")), "2026-11-20"),
    (Store(fail=True), "unavailable"),
    (None, "no store"),
])
def test_fail_closed_without_agreement(store, reason):
    df = yahoo.parse_chart(payload(), "XLK", store)
    assert str(df.index[-1].date()) == "2026-11-20"
    assert not close_fill.LOG[0]["filled"] and reason in close_fill.LOG[0]["reason"]


def test_no_fill_during_the_session_or_for_non_us_or_on_event_days():
    s = Store(nasdaq())
    assert str(yahoo.parse_chart(payload(mtime=END_23 - 3600), "XLK", s).index[-1].date()) == "2026-11-20"
    assert close_fill.LOG == [] and s.calls == 0  # session not over: not even attempted
    yahoo.parse_chart(payload(), "^NDX", s)
    yahoo.parse_chart(payload(), "2330.TW", s)
    ev = {"dividends": {"x": {"date": int(DAY[2].timestamp()), "amount": 0.2}}}
    yahoo.parse_chart(payload(events=ev), "XLK", s)
    assert [r["filled"] for r in close_fill.LOG] == [False] * 3 and s.calls == 0


def test_complete_bar_is_untouched():
    s = Store(nasdaq())
    df = yahoo.parse_chart(payload(last_close=162.0), "XLK", s)
    assert df["close"].iloc[-1] == 162.0 and close_fill.LOG == [] and s.calls == 0


def test_closed_market_view_is_accepted_only_for_the_same_day():
    closed = lambda day: json.dumps({"data": {"marketStatus": "Closed", "secondaryData": None,  # noqa: E731
                                              "primaryData": {"lastSalePrice": "$162.35", "lastTradeTimestamp": day}}}).encode()
    assert str(yahoo.parse_chart(payload(), "XLK", Store(closed("Nov 23, 2026"))).index[-1].date()) == "2026-11-23"
    assert str(yahoo.parse_chart(payload(), "XLK", Store(closed("Nov 20, 2026"))).index[-1].date()) == "2026-11-20"
    assert "2026-11-20" in close_fill.LOG[-1]["reason"]
