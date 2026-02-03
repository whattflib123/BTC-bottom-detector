#!/usr/bin/env python3
import os
import sys
import time
from typing import Dict, List

import requests


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
TELEGRAM_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"


def env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    return value


def sma(values: List[float], period: int, index: int) -> float:
    if index + 1 < period:
        raise ValueError(f"Not enough data for SMA{period} at index {index}")
    start = index + 1 - period
    window = values[start : index + 1]
    return sum(window) / period


def fetch_klines(
    symbol: str, interval: str, limit: int = 260, timeout: int = 15
) -> List[List]:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise RuntimeError("Binance API returned empty or invalid kline data.")
    return data


def latest_closed_index(klines: List[List], now_ms: int) -> int:
    # A candle is closed when its close_time is in the past.
    for i in range(len(klines) - 1, -1, -1):
        close_time_ms = int(klines[i][6])
        if close_time_ms < now_ms:
            return i
    raise RuntimeError("No closed daily candle found in fetched data.")


def evaluate_signal(klines: List[List], idx: int) -> Dict:
    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    close = closes[idx]
    volume = volumes[idx]
    ma50 = sma(closes, 50, idx)
    ma200 = sma(closes, 200, idx)
    vol_sma20 = sma(volumes, 20, idx)
    vol_threshold = vol_sma20 * 2.0

    cond_daily = True  # Fixed by design: this script only uses daily candles.
    cond_abnormal_vol = volume > vol_threshold
    cond_close_below_ma200 = close < ma200
    cond_ma200_above_ma50 = ma200 > ma50

    signal = (
        cond_daily
        and cond_abnormal_vol
        and cond_close_below_ma200
        and cond_ma200_above_ma50
    )

    return {
        "signal": signal,
        "close": close,
        "volume": volume,
        "ma50": ma50,
        "ma200": ma200,
        "vol_sma20": vol_sma20,
        "vol_threshold": vol_threshold,
        "conditions": {
            "is_daily_or_above": cond_daily,
            "abnormal_volume": cond_abnormal_vol,
            "close_below_ma200": cond_close_below_ma200,
            "ma200_above_ma50": cond_ma200_above_ma50,
        },
    }


def kline_date_utc(close_time_ms: int) -> str:
    ts = close_time_ms / 1000.0
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def had_recent_signal(klines: List[List], idx: int, lookback_days: int = 10) -> bool:
    start = max(200, idx - lookback_days)
    for i in range(start, idx):
        if evaluate_signal(klines, i)["signal"]:
            return True
    return False


def find_weekly_v_entries(
    weekly_klines: List[List],
    latest_idx: int,
    current_price: float,
    max_count: int = 2,
    min_gap_pct: float = 0.05,
) -> List[Dict]:
    # V point definition:
    # one bearish weekly candle + next bullish weekly candle
    # and use the bearish week's close as the V-point entry price.
    # Keep only V points below current price, and return nearest recent N points.
    entries: List[Dict] = []
    threshold_price = current_price * (1.0 - min_gap_pct)
    for i in range(latest_idx - 1, 0, -1):
        wk_open = float(weekly_klines[i][1])
        wk_close = float(weekly_klines[i][4])
        next_open = float(weekly_klines[i + 1][1])
        next_close = float(weekly_klines[i + 1][4])

        is_down_week = wk_close < wk_open
        is_up_week = next_close > next_open
        if not (is_down_week and is_up_week):
            continue

        candidate_price = wk_close
        # Skip levels that are too close to first entry; require at least 5% lower.
        if candidate_price < threshold_price:
            # Also require each second-entry level to be at least 5% lower than
            # the previously accepted second-entry level.
            if entries:
                prev_price = entries[-1]["price"]
                if candidate_price > prev_price * (1.0 - min_gap_pct):
                    continue
            entries.append(
                {
                "price": candidate_price,
                "v_week_close_time_ms": int(weekly_klines[i][6]),
                }
            )
            if len(entries) >= max_count:
                break

    return entries


def format_message(
    symbol: str,
    close_time_ms: int,
    result: Dict,
    is_repeat: bool,
    weekly_entries: List[Dict],
) -> str:
    ok = "✅"
    no = "❌"
    c = result["conditions"]
    price = lambda v: f"{v:,.2f}"
    vol = lambda v: f"{v:,.4f}"

    failed_reasons = []
    if not c["abnormal_volume"]:
        failed_reasons.append("成交量未達爆量門檻")
    if not c["close_below_ma200"]:
        failed_reasons.append("收盤價未跌破 MA200")
    if not c["ma200_above_ma50"]:
        failed_reasons.append("均線結構非 MA200 > MA50")

    lines = [
        "📊 BTC 抄底監控（日線）",
        f"交易對：{symbol}",
        f"K線日期（UTC）：{kline_date_utc(close_time_ms)}",
        "",
        f"結論：{'✅ 觸發抄底訊號' if result['signal'] else '❌ 未觸發抄底訊號'}",
    ]

    if result["signal"] and is_repeat:
        lines.append("⚠️ 提醒：10 天內曾出現抄底訊號，屬於重複抄底。")

    if result["signal"]:
        lines.extend(["", "進場價位：", f"- {price(result['close'])}"])
        if weekly_entries:
            for entry in weekly_entries:
                lines.append(f"- {price(entry['price'])}")
        else:
            lines.append("- 暫無可用第二進場價位")

    if not result["signal"]:
        lines.extend(
            [
                "未通過條件：",
                f"- {'；'.join(failed_reasons) if failed_reasons else '無'}",
            ]
        )

    lines.extend(
        [
        "",
        "條件檢查：",
        (
            f"- {ok if c['abnormal_volume'] else no} 爆量成立："
            f"{vol(result['volume'])} > 2 × {vol(result['vol_sma20'])}"
        ),
        (
            f"- {ok if c['close_below_ma200'] else no} 跌破長期均線："
            f"{price(result['close'])} < {price(result['ma200'])}"
        ),
        (
            f"- {ok if c['ma200_above_ma50'] else no} 空頭均線結構："
            f"MA200 {price(result['ma200'])} > MA50 {price(result['ma50'])}"
        ),
        ]
    )
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str, timeout: int = 15) -> None:
    url = TELEGRAM_SEND_URL.format(token=token)
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram API error: {body}")


def main() -> int:
    symbol = env("BINANCE_SYMBOL", "BTCUSDT")
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return 1

    try:
        klines = fetch_klines(symbol=symbol, interval="1d", limit=260)
        weekly_klines = fetch_klines(symbol=symbol, interval="1w", limit=260)
        now_ms = int(time.time() * 1000)
        idx = latest_closed_index(klines, now_ms)
        weekly_idx = latest_closed_index(weekly_klines, now_ms)
        if idx < 200:
            raise RuntimeError("Not enough historical candles for MA200 calculation.")

        close_time_ms = int(klines[idx][6])
        result = evaluate_signal(klines, idx)
        is_repeat = had_recent_signal(klines, idx, lookback_days=10)
        weekly_entries = find_weekly_v_entries(
            weekly_klines, weekly_idx, current_price=result["close"], max_count=2
        )
        message = format_message(symbol, close_time_ms, result, is_repeat, weekly_entries)
        send_telegram(token, chat_id, message)

        print("Message sent to Telegram.")
        print(
            "Signal:",
            "YES" if result["signal"] else "NO",
            "| Date(UTC):",
            kline_date_utc(close_time_ms),
        )
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
