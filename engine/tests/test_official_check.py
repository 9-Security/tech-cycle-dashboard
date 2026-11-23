import json

import pandas as pd
import pytest

from tcd.official_check import OfficialConfig, compare
from tcd.sources import twofficial as tw
from tcd.sources.http import FetchError


def test_roc_date_and_venue():
    assert tw.roc_date("115/11/02") == pd.Timestamp("2026-11-02")
    assert tw.venue("2330.TW") == "TWSE" and tw.venue("3324.TWO") == "TPEx" and tw.venue("AAPL") is None
    with pytest.raises(ValueError):
        tw.roc_date("2026-11-02")


def test_parse_twse_and_tpex():
    twse = {"stat": "OK", "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數", "註記"],
            "data": [["115/11/02", "1", "1", "2,310.00", "2,345.00", "2,310.00", "2,330.00", "-40.00", "1", ""],
                     ["115/11/03", "0", "0", "--", "--", "--", "--", " 0.00", "0", ""]]}
    s = tw.parse_twse(json.dumps(twse).encode())
    assert s[pd.Timestamp("2026-11-02")] == 2330.0 and s[pd.Timestamp("2026-11-03")] is None
    tpex = {"tables": [{"data": [["115/11/02", "4,696", "6,419,093", "1,280.00", "1,430.00", "1,280.00", "1,395.00", "65.00", "7,622"]]}]}
    assert tw.parse_tpex(json.dumps(tpex).encode())[pd.Timestamp("2026-11-02")] == 1395.0
    with pytest.raises(FetchError):
        tw.parse_twse(json.dumps({"stat": "查詢日期大於今日"}).encode())
    with pytest.raises(FetchError):
        tw.parse_twse(b"<html>blocked</html>")
    assert tw.parse_twse(json.dumps({"stat": "很抱歉，沒有符合條件的資料!"}).encode()).empty


def test_compare_categories():
    d = pd.bdate_range("2026-11-02", periods=6)
    official = pd.Series({d[0]: 100.0, d[1]: 101.0, d[2]: None, d[3]: 103.0, d[4]: 104.0}, dtype=object)
    yahoo = pd.Series([100.0, 101.0, 101.0, 110.0, 104.0, 105.0], index=d)  # d2 stale bar, d3 wrong, d5 not yet official
    yahoo = yahoo.drop(d[4]).reindex(d.delete(4))
    official[d[4]] = 104.0
    r = compare(yahoo, official, OfficialConfig())
    assert r["status"] == "warn"
    assert r["n_mismatch"] == 1 and r["mismatches"][0]["date"] == str(d[3].date())
    assert r["extra"] == [str(d[2].date())] and r["missing"] == [str(d[4].date())]
    assert r["not_yet"] == [str(d[5].date())]
    ok = compare(pd.Series([100.0, 101.0], index=d[:2]), pd.Series({d[0]: 100.0, d[1]: 101.2}, dtype=object), OfficialConfig())
    assert ok["status"] == "ok" and ok["compared"] == 2
