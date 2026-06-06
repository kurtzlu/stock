#!/usr/bin/env python3

import json
import os
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
import concurrent.futures

# =========================
# SSL
# =========================

SSL_UNVERIFIED = ssl.create_default_context()
SSL_UNVERIFIED.check_hostname = False
SSL_UNVERIFIED.verify_mode = ssl.CERT_NONE

# =========================
# 路徑
# =========================

if os.environ.get("GITHUB_ACTIONS"):
    DATA_DIR = Path(__file__).parent / "data"
else:
    DATA_DIR = Path.home() / "stock_data"

REV_DIR = DATA_DIR / "revenue"
INC_DIR = DATA_DIR / "income"
LOG_DIR = DATA_DIR / "logs"

# =========================
# API
# =========================

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

REVENUE_APIS = {
    "listed": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "otc": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
    "emerging": "https://www.tpex.org.tw/openapi/v1/t187ap05_R",
}

INCOME_APIS = {
    "listed": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "otc": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ciA",
    "emerging": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_U_ci",
}

# =========================
# 工具
# =========================

def fetch_json(url):

    req = urllib.request.Request(
        url,
        headers=HEADERS
    )

    ctx = SSL_UNVERIFIED if "twse.com.tw" in url else None

    with urllib.request.urlopen(
        req,
        timeout=30,
        context=ctx
    ) as r:

        return json.loads(
            r.read().decode("utf-8-sig")
        )


def save_json(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def save_latest(folder, filename):

    save_json(
        folder / "latest.json",
        {
            "updated_at":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            "latest_file":
                filename
        }
    )


def log(msg):

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    ts = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line = f"[{ts}] {msg}"

    print(line)

    with open(
        LOG_DIR / "fetch.log",
        "a",
        encoding="utf-8"
    ) as f:

        f.write(line + "\n")

# =========================
# 月營收
# =========================

def fetch_revenue(today):

    ym = today.strftime("%Y_%m")

    result = {}

    for market, url in REVENUE_APIS.items():

        try:

            data = fetch_json(url)

            result[market] = data

            log(
                f"Revenue {market} OK "
                f"{len(data)}"
            )

        except Exception as e:

            result[market] = []

            log(
                f"Revenue {market} ERROR "
                f"{e}"
            )

    filename = f"revenue_{ym}.json"

    save_json(
        REV_DIR / filename,
        {
            "fetch_date":
                today.strftime("%Y-%m-%d"),
            "year_month":
                ym,
            **result
        }
    )

    save_latest(
        REV_DIR,
        filename
    )

    log(
        f"Revenue saved -> {filename}"
    )

# =========================
# 損益表
# =========================

def fetch_income(today):

    q = (today.month - 1) // 3 + 1

    yq = f"{today.year}_Q{q}"

    result = {}

    for market, url in INCOME_APIS.items():

        try:

            data = fetch_json(url)

            result[market] = data

            log(
                f"Income {market} OK "
                f"{len(data)}"
            )

        except Exception as e:

            result[market] = []

            log(
                f"Income {market} ERROR "
                f"{e}"
            )

    filename = f"income_{yq}.json"

    save_json(
        INC_DIR / filename,
        {
            "fetch_date":
                today.strftime("%Y-%m-%d"),
            "quarter":
                yq,
            **result
        }
    )

    save_latest(
        INC_DIR,
        filename
    )

    log(
        f"Income saved -> {filename}"
    )

# =========================
# 主程式
# =========================

def main():

    today = datetime.today()

    log(
        f"===== START "
        f"{today.strftime('%Y-%m-%d')} ====="
    )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=2
    ) as executor:

        f1 = executor.submit(
            fetch_revenue,
            today
        )

        f2 = executor.submit(
            fetch_income,
            today
        )

        concurrent.futures.wait(
            [f1, f2]
        )

    log("===== DONE =====")

    log(
        f"DATA_DIR = {DATA_DIR}"
    )


if __name__ == "__main__":
    main()
