#!/usr/bin/env python3
"""
台股資料每日自動抓取 script
執行時機：每個交易日，建議設定 08:00~08:30（開盤前）
"""

import json
import os
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
import concurrent.futures

# twse.com.tw 憑證有問題，建立忽略 SSL 驗證的 context
SSL_UNVERIFIED = ssl.create_default_context()
SSL_UNVERIFIED.check_hostname = False
SSL_UNVERIFIED.verify_mode = ssl.CERT_NONE

# ===== 設定區 =====
# 自動判斷執行環境：GitHub Actions 存在 repo 的 data/ 目錄，本機存在 ~/stock_data/
if os.environ.get("GITHUB_ACTIONS"):
    DATA_DIR = Path(__file__).parent / "data"
else:
    DATA_DIR = Path(os.path.expanduser("~")) / "stock_data"

# 子目錄
REV_DIR   = DATA_DIR / "revenue"      # 月營收
INC_DIR   = DATA_DIR / "income"       # 損益表
INST_DIR  = DATA_DIR / "institution"  # 三大法人
LOG_DIR   = DATA_DIR / "logs"         # 執行紀錄
PRICE_DIR = DATA_DIR / "price"        # 每日價量（風火輪用）

# 三大法人保留天數
KEEP_DAYS = 7  # 保留最近7個交易日（實際只用5日，多2天緩衝）

# ===== API 設定 =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.tpex.org.tw/openapi/"
}

REVENUE_APIS = {
    "listed":   "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "otc":      "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
    "emerging": "https://www.tpex.org.tw/openapi/v1/t187ap05_R",
}

INCOME_APIS = {
    "listed":   "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "otc":      "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ciA",
    "emerging": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_U_ci",
}

# ===== 工具函數 =====
def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    # twse.com.tw 憑證有缺漏，需略過 SSL 驗證
    ctx = SSL_UNVERIFIED if "twse.com.tw" in url else None
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return json.loads(r.read().decode("utf-8-sig"))

def fetch_csv_as_json(url):
    import csv, io
    req = urllib.request.Request(url, headers={**HEADERS, "Referer": "https://mopsfin.twse.com.tw/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(data))
    return list(reader)

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def log(msg):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_DIR / "fetch.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ===== 抓取函數 =====
def fetch_revenue(today):
    """月營收：每天覆蓋當月檔案，如 revenue_2026_05.json"""
    ym = today.strftime("%Y_%m")
    
    result = {}
    for market, url in REVENUE_APIS.items():
        try:
            data = fetch_json(url)
            result[market] = data
            log(f"月營收 [{market}] OK - {len(data)} 筆")
        except Exception as e:
            log(f"月營收 [{market}] ERROR - {e}")
            result[market] = []

    # 合併存檔
    path = REV_DIR / f"revenue_{ym}.json"
    save_json(path, {
        "fetch_date": today.strftime("%Y-%m-%d"),
        "year_month": ym,
        **result
    })
    log(f"月營收已存 → {path}")
    return result

def fetch_income(today):
    """損益表：每天覆蓋當季檔案，如 income_2026_Q1.json"""
    # 判斷當季
    q = (today.month - 1) // 3 + 1
    yq = f"{today.year}_Q{q}"
    
    result = {}
    for market, url in INCOME_APIS.items():
        try:
            data = fetch_json(url)
            result[market] = data
            log(f"損益表 [{market}] OK - {len(data)} 筆")
        except Exception as e:
            log(f"損益表 [{market}] ERROR - {e}")
            result[market] = []

    path = INC_DIR / f"income_{yq}.json"
    save_json(path, {
        "fetch_date": today.strftime("%Y-%m-%d"),
        "quarter": yq,
        **result
    })
    log(f"損益表已存 → {path}")
    return result

def fetch_institution(today):
    """三大法人：每天存日期檔，自動清理超過 KEEP_DAYS 的舊檔"""
    date_str = today.strftime("%Y%m%d")
    roc_date = f"{today.year - 1911}/{today.month:02d}/{today.day:02d}"
    roc_encoded = urllib.parse.quote(roc_date)
    
    result = {}

    # 上市（TWSE T86）— 抓到 0 筆視為限流，自動重試最多 4 次
    import time as _time
    result["listed"] = None
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
    for attempt in range(1, 5):
        try:
            data = fetch_json(url)
            stat = data.get("stat", "")
            rows = data.get("data", [])
            if stat == "OK" and len(rows) > 0:
                result["listed"] = {"fields": data.get("fields", []), "data": rows}
                log(f"法人上市 [{date_str}] OK - {len(rows)} 筆（第 {attempt} 次）")
                break
            elif "沒有符合條件" in stat or "無" in stat:
                log(f"法人上市 [{date_str}] 非交易日（{stat}）")
                break
            else:
                log(f"法人上市 [{date_str}] 第 {attempt} 次抓到 {len(rows)} 筆，重試中")
                if attempt < 4:
                    _time.sleep(15 * attempt)
        except Exception as e:
            log(f"法人上市 [{date_str}] 第 {attempt} 次 ERROR - {e}")
            if attempt < 4:
                _time.sleep(15 * attempt)
    if result["listed"] is None:
        log(f"法人上市 [{date_str}] 重試 4 次仍失敗 ❌")

    # 上櫃（TPEX 舊版）— 抓到 0 筆視為限流，自動重試最多 4 次
    result["otc"] = None
    otc_url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&se=EW&t=D&d={roc_encoded}"
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(otc_url, headers={"User-Agent": HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=20, context=SSL_UNVERIFIED) as r:
                data = json.loads(r.read().decode("utf-8"))
            tables = data.get("tables", [])
            rows = tables[0].get("data", []) if tables else []
            if rows and len(rows) > 0:
                result["otc"] = {"fields": tables[0].get("fields", []), "data": rows}
                log(f"法人上櫃 [{date_str}] OK - {len(rows)} 筆（第 {attempt} 次）")
                break
            else:
                log(f"法人上櫃 [{date_str}] 第 {attempt} 次抓到 0 筆，重試中")
                if attempt < 4:
                    _time.sleep(15 * attempt)
        except Exception as e:
            log(f"法人上櫃 [{date_str}] 第 {attempt} 次 ERROR - {e}")
            if attempt < 4:
                _time.sleep(15 * attempt)
    if result["otc"] is None:
        log(f"法人上櫃 [{date_str}] 重試 4 次仍失敗或非交易日 ❌")
    # 有資料才存檔（非交易日不存）
    if result.get("listed") or result.get("otc"):
        path = INST_DIR / f"institution_{date_str}.json"
        save_json(path, {
            "date": date_str,
            "roc_date": roc_date,
            **result
        })
        log(f"法人已存 → {path}")

        # 清理舊檔，保留最近 KEEP_DAYS 個交易日
        files = sorted(INST_DIR.glob("institution_*.json"), reverse=True)
        for old_file in files[KEEP_DAYS:]:
            old_file.unlink()
            log(f"已刪除舊法人檔 → {old_file.name}")
    else:
        log(f"法人 [{date_str}] 非交易日，不存檔")

def fetch_price(today):
    """每日價量：全市場收盤+量+TAIEX，存 data/price/price_YYYYMMDD.json（永久累積，不刪舊）。
    上市走 TWSE MI_INDEX（同一支即含 TAIEX），上櫃走 TPEX dailyQuotes（date 需帶斜線）。
    每天僅 2 個整批請求，不逐檔、不依賴 FinMind。"""
    import time as _time
    ymd = today.strftime("%Y%m%d")

    def _num(s):
        try: return float(str(s).replace(",", "").strip())
        except: return None
    def _vol(s):
        try: return int(float(str(s).replace(",", "").strip()))
        except: return None
    def _get_retry(url, tries=4):
        for i in range(tries):
            try:
                return fetch_json(url)
            except Exception as e:
                if i == tries - 1:
                    raise
                _time.sleep(2 * (i + 1))

    # ---- 上市 + TAIEX（TWSE MI_INDEX）----
    listed, taiex = [], None
    try:
        d = _get_retry(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json")
        if d.get("stat") == "OK":
            for t in d.get("tables", []):
                fields = t.get("fields", [])
                if taiex is None and any("指數" in str(x) for x in fields):
                    for r in t.get("data", []):
                        if "發行量加權股價指數" in str(r[0]):
                            taiex = _num(r[1]); break
                if any("收盤" in str(x) for x in fields) and len(t.get("data", [])) > 100:
                    for r in t["data"]:
                        code = str(r[0]).strip()
                        if len(code) == 4 and code.isdigit() and _num(r[8]) is not None:
                            listed.append({"code": code, "name": r[1].strip(), "close": _num(r[8]), "vol": _vol(r[2])})
            log(f"價量上市 [{ymd}] OK - {len(listed)} 筆 TAIEX={taiex}")
        else:
            log(f"價量上市 [{ymd}] 非交易日（stat={d.get('stat')}）")
    except Exception as e:
        log(f"價量上市 [{ymd}] ERROR - {e}")

    if not listed:
        log(f"價量 [{ymd}] 上市無資料，視為非交易日，不存檔")
        return

    # ---- 上櫃（TPEX dailyQuotes，date 帶斜線）----
    otc = []
    try:
        d = _get_retry(f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={today.year}/{today.month:02d}/{today.day:02d}&type=EW&response=json")
        if str(d.get("date", ""))[:8] == ymd and d.get("tables"):
            for r in d["tables"][0]["data"]:
                code = str(r[0]).strip()
                if len(code) == 4 and code.isdigit() and _num(r[2]) is not None:
                    otc.append({"code": code, "name": r[1].strip(), "close": _num(r[2]), "vol": _vol(r[8])})
            log(f"價量上櫃 [{ymd}] OK - {len(otc)} 筆")
        else:
            log(f"價量上櫃 [{ymd}] 日期不符或無資料（回傳 {d.get('date')}）")
    except Exception as e:
        log(f"價量上櫃 [{ymd}] ERROR - {e}")

    # ---- 存檔（compact，永久累積、不刪舊）----
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    path = PRICE_DIR / f"price_{ymd}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": ymd, "taiex": taiex, "listed": listed, "otc": otc}, f, ensure_ascii=False)
    log(f"價量已存 → {path}")

# ===== 主程式 =====
def main():
    today = datetime.today()
    log(f"===== 開始抓取 {today.strftime('%Y-%m-%d')} =====")

    # 平行下載月營收 + 損益表 + 法人
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f1 = executor.submit(fetch_revenue, today)
        f2 = executor.submit(fetch_income, today)
        f3 = executor.submit(fetch_institution, today)
        f4 = executor.submit(fetch_price, today)
        concurrent.futures.wait([f1, f2, f3, f4])

    log(f"===== 完成 =====")
    log(f"資料目錄: {DATA_DIR}")

if __name__ == "__main__":
    main()
