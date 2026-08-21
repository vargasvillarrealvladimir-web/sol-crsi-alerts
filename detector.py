import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

URL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

def send_telegram(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=15
    )
    r.raise_for_status()

def calcular_crsi(close):
    n = len(close)
    L = 10

    chg = np.diff(close, prepend=close[0])
    u = np.maximum(chg, 0)
    dn = np.maximum(-chg, 0)

    up = np.zeros(n)
    down = np.zeros(n)

    up[L-1] = u[:L].mean()
    down[L-1] = dn[:L].mean()

    for i in range(L, n):
        up[i] = (up[i-1] * 9 + u[i]) / L
        down[i] = (down[i-1] * 9 + dn[i]) / L

    rsi = np.zeros(n)
    rsi[:L-1] = 50

    rsi[L-1:] = np.where(
        down[L-1:] == 0,
        100,
        np.where(
            up[L-1:] == 0,
            0,
            100 - 100 / (1 + up[L-1:] / down[L-1:])
        )
    )

    cr = np.zeros(n)
    cr[0] = rsi[0]

    torque = 2 / 11

    for i in range(1, n):
        cr[i] = (
            torque * (2 * rsi[i] - rsi[i-4])
            + (1 - torque) * cr[i-1]
        )

    return cr

def calcular_canal(cr):
    n = len(cr)
    mem = 40

    low = np.full(n, np.nan)
    high = np.full(n, np.nan)

    for j in range(mem - 1, n):
        x = cr[j-mem+1:j+1]

        mn = x.min()
        mx = x.max()
        step = (mx - mn) / 100

        low[j] = next(
            (
                mn + step * s
                for s in range(101)
                if np.mean(x < mn + step * s) >= 0.10
            ),
            mn
        )

        high[j] = next(
            (
                mx - step * s
                for s in range(101)
                if np.mean(x >= mx - step * s) >= 0.10
            ),
            mx
        )

    return low, high

def main():

    data = requests.get(
        URL,
        params={
            "symbol": "SOL-USDT",
            "interval": "15m",
            "limit": 1000
        },
        timeout=15
    ).json()["data"]

    df = pd.DataFrame(data)

    df["time"] = pd.to_datetime(
        df["time"],
        unit="ms",
        utc=True
    ).dt.tz_convert("America/La_Paz")

    df = (
        df.sort_values("time")
        .reset_index(drop=True)
        .iloc[:-1]
    )

    close = df["close"].astype(float).to_numpy()

    cr = calcular_crsi(close)
    low, high = calcular_canal(cr)

    signals = []

    for i in range(40, len(close)):

        if (
            cr[i-1] <= low[i-1]
            and cr[i] > low[i]
        ):
            signals.append(
                ("LONG", i)
            )

        elif (
            cr[i-1] >= high[i-1]
            and cr[i] < high[i]
        ):
            signals.append(
                ("SHORT", i)
            )

    if not signals:
        print("Sin señales.")
        return

    signal, i = signals[-1]

    signal_time = str(df.iloc[i]["time"])

    state_file = Path("last_signal.txt")

    previous = ""

    if state_file.exists():
        previous = state_file.read_text().strip()

    signal_id = signal + "|" + signal_time

    if signal_id == previous:
        print("Señal ya enviada:", signal_id)
        return

    if signal == "LONG":

        message = (
            "🟢 LONG cRSI\n"
            "SOL-USDT 15m\n"
            "🇧🇴 " + signal_time + "\n"
            "Precio: " + str(round(close[i], 3)) + "\n"
            "cRSI: " + str(round(cr[i], 2)) + "\n"
            "LowBand: " + str(round(low[i], 2))
        )

    else:

        message = (
            "🔴 SHORT cRSI\n"
            "SOL-USDT 15m\n"
            "🇧🇴 " + signal_time + "\n"
            "Precio: " + str(round(close[i], 3)) + "\n"
            "cRSI: " + str(round(cr[i], 2)) + "\n"
            "HighBand: " + str(round(high[i], 2))
        )

    send_telegram(message)

    state_file.write_text(signal_id)

    print("SEÑAL ENVIADA:", signal_id)

if __name__ == "__main__":
    main()
