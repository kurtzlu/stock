@echo off
:: 台股資料每日抓取排程
:: 建議設定時間：每天 08:15（開盤前）

:: Python 路徑（如果 python 不在 PATH，請改成完整路徑，如 C:\Python312\python.exe）
set PYTHON=python

:: Script 路徑（請改成你實際存放的位置）
set SCRIPT=%USERPROFILE%\stock_data\fetch_stock_data.py

:: 執行
%PYTHON% "%SCRIPT%" >> "%USERPROFILE%\stock_data\logs\run.log" 2>&1
