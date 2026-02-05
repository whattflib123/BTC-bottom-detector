# BTC Bottom Detector (Daily)

This tool detects potential bottom signals using Binance `BTCUSDT` **daily** candles and sends results to a Telegram group.  
Entry prices are displayed in a bullet list format.

Logic overview:
- 🔹 MA50 below MA200 (`MA200 > MA50`) is treated as a classic bear-market structure, where bottom-fishing setups are more meaningful.
- 🔹 Abnormal volume often appears near major tops/bottoms.

## Features

- On each run, it checks whether the **latest closed daily candle** triggers a bottom signal.
- All results (signal / no signal) are sent to one Telegram group.
- If a signal is triggered, the message includes:
  - First entry price (the signal candle close)
  - Second entry prices (up to two weekly V-point levels)
  - Take-profit prices (up to three weekly reversal highs)

## Strategy and Entry Conditions

### Daily Bottom Signal Conditions

1. Abnormal volume: `volume > SMA20(volume) * 2.0`
2. Close below MA200: `close < MA200`
3. Bearish MA structure: `MA200 > MA50`

### Second Entry (Weekly V-Point) Logic

This applies SNR (support/resistance) ideas: weekly open/close levels are often strong support zones, so pending orders near these areas may catch rebounds or reversals.

- V definition: `one bearish weekly candle + next bullish weekly candle`
- Candidate level: close of the bearish weekly candle

### Take-Profit (Weekly Reversal High) Logic

- Displayed only when the full bottom signal is triggered, in the same Telegram message
- Candidate definition: `one bullish weekly candle + next bearish weekly candle`
- Candidate level: close of the bullish weekly candle
- Up to three take-profit levels, with a default minimum spacing of `5%`
- If fewer than three levels are found with the 5% rule, the rule is relaxed to fill more levels
- If still none are found, show: `Price is making new highs; use MA50 trailing take-profit`

## Project Files

- `main.py`: main script
- `requirements.txt`: dependencies
- `.env.example`: environment variable template

## Environment Setup

```bash
cd btc-bottom-detector-release
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables

Create `.env` first:

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:your_bot_token
TELEGRAM_CHAT_ID=-1001234567890
BINANCE_SYMBOL=BTCUSDT
```

Load env and run:

```bash
set -a
source .env
set +a
python3 main.py
```

## Telegram Setup Notes

- Add your bot to the target group first.
- Make sure the bot has permission to send messages.
- `TELEGRAM_CHAT_ID`: group that receives all signal results

## Scheduling Recommendation (Important)

Schedule the script in **your own timezone**, and run it a bit after the daily close to avoid unstable just-closed data.

- Binance daily candles close at `UTC 00:00`
- In Taipei time (UTC+8), that is around `08:00`
- Recommended run time: after `08:01` (for example `08:03`)

## crontab Example (Taipei Timezone)

```bash
CRON_TZ=Asia/Taipei
3 8 * * * cd /path/to/btc-bottom-detector-release && set -a && source .env && set +a && /path/to/btc-bottom-detector-release/.venv/bin/python main.py >> detector.log 2>&1
```

## Disclaimer

- This tool is for signal notifications only and is **not** financial advice.
