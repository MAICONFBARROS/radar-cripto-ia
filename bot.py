import os
import time
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COINS = {
    "BTC-USD": "BTC",
    "ETH-USD": "ETH",
    "SOL-USD": "SOL",
    "XRP-USD": "XRP",
    "ADA-USD": "ADA",
    "DOGE-USD": "DOGE",
    "AVAX-USD": "AVAX",
    "LINK-USD": "LINK",
    "LTC-USD": "LTC",
    "DOT-USD": "DOT",
}

INTERVAL = "4h"
LIMIT = 120


def get_candles(symbol):
    end = int(time.time())
    start = end - (14400 * 120)

    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"

    params = {
        "granularity": 14400,
        "start": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "end": datetime.fromtimestamp(end, timezone.utc).isoformat()
    }

    headers = {
        "User-Agent": "RadarCriptoIA"
    }

    r = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=30
    )

    r.raise_for_status()

    data = r.json()
    data = sorted(data, key=lambda x: x[0])

    candles = []

    for c in data[-120:]:
        candles.append({
            "open": float(c[3]),
            "high": float(c[2]),
            "low": float(c[1]),
            "close": float(c[4]),
            "volume": float(c[5])
        })

    return candles


def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    result = sum(values[:period]) / period
    for price in values[period:]:
        result = price * k + result * (1 - k)
    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values):
    ema12 = ema(values, 12)
    ema26 = ema(values, 26)

    if ema12 is None or ema26 is None:
        return None, None

    macd_line = ema12 - ema26

    macd_history = []
    for i in range(26, len(values)):
        e12 = ema(values[:i + 1], 12)
        e26 = ema(values[:i + 1], 26)
        if e12 is not None and e26 is not None:
            macd_history.append(e12 - e26)

    signal = ema(macd_history, 9) if len(macd_history) >= 9 else None
    return macd_line, signal


def bollinger(values, period=20):
    if len(values) < period:
        return None, None, None

    recent = values[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = variance ** 0.5

    upper = middle + 2 * std
    lower = middle - 2 * std

    return upper, middle, lower


def atr(candles, period=14):
    if len(candles) <= period:
        return None

    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    return sum(trs[-period:]) / period


def heikin_ashi(candles):
    ha = []

    for i, c in enumerate(candles):
        ha_close = (c["open"] + c["high"] + c["low"] + c["close"]) / 4

        if i == 0:
            ha_open = (c["open"] + c["close"]) / 2
        else:
            ha_open = (ha[-1]["open"] + ha[-1]["close"]) / 2

        ha.append({
            "open": ha_open,
            "close": ha_close,
            "high": max(c["high"], ha_open, ha_close),
            "low": min(c["low"], ha_open, ha_close),
        })

    last = ha[-1]
    prev = ha[-2]

    if last["close"] > last["open"] and prev["close"] > prev["open"]:
        return "ALTA"
    if last["close"] < last["open"] and prev["close"] < prev["open"]:
        return "BAIXA"
    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        return "VIRANDO PARA ALTA"
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        return "VIRANDO PARA BAIXA"

    return "NEUTRO"


def suporte_resistencia(candles):
    recentes = candles[-30:]
    suporte = min(c["low"] for c in recentes)
    resistencia = max(c["high"] for c in recentes)
    return suporte, resistencia


def analisar(symbol, name):
    candles = get_candles(symbol)

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]

    price = closes[-1]
    rsi14 = rsi(closes)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)
    macd_line, macd_signal = macd(closes)
    bb_upper, bb_middle, bb_lower = bollinger(closes)
    atr_value = atr(candles)
    ha = heikin_ashi(candles)
    suporte, resistencia = suporte_resistencia(candles)

    avg_volume = sum(volumes[-30:]) / 30
    volume_strength = volumes[-1] / avg_volume if avg_volume else 1

    score = 0
    motivos = []

    if ema9 > ema21:
        score += 2
        motivos.append("EMA 9 acima da EMA 21")
    else:
        score -= 2
        motivos.append("EMA 9 abaixo da EMA 21")

    if ema21 > ema50:
        score += 2
        motivos.append("EMA 21 acima da EMA 50")
    else:
        score -= 1
        motivos.append("EMA 21 abaixo da EMA 50")

    if rsi14 is not None:
        if rsi14 < 30:
            score += 2
            motivos.append("RSI em sobrevenda")
        elif rsi14 > 70:
            score -= 2
            motivos.append("RSI em sobrecompra")
        elif 40 <= rsi14 <= 65:
            score += 1
            motivos.append("RSI saudável")
        else:
            motivos.append("RSI neutro")

    if macd_line is not None and macd_signal is not None:
        if macd_line > macd_signal:
            score += 2
            motivos.append("MACD positivo")
        else:
            score -= 2
            motivos.append("MACD negativo")

    if ha in ["ALTA", "VIRANDO PARA ALTA"]:
        score += 2
        motivos.append(f"Heikin Ashi {ha}")
    elif ha in ["BAIXA", "VIRANDO PARA BAIXA"]:
        score -= 2
        motivos.append(f"Heikin Ashi {ha}")

    if volume_strength > 1.2:
        score += 1
        motivos.append("Volume acima da média")
    elif volume_strength < 0.7:
        score -= 1
        motivos.append("Volume fraco")

    if bb_upper and bb_lower:
        if price <= bb_lower:
            score += 1
            motivos.append("Preço perto da banda inferior")
        elif price >= bb_upper:
            score -= 1
            motivos.append("Preço perto da banda superior")

    if score >= 7:
        sinal = "🟢 COMPRA FORTE"
    elif score >= 4:
        sinal = "🟢 COMPRA MODERADA"
    elif score <= -7:
        sinal = "🔴 VENDA FORTE"
    elif score <= -4:
        sinal = "🟠 VENDA / REDUZIR"
    else:
        sinal = "⚪ AGUARDAR"

    confianca = min(95, max(35, 50 + abs(score) * 6))

    stop = price - atr_value * 1.5 if atr_value else suporte
    alvo1 = price + atr_value * 2 if atr_value else resistencia
    alvo2 = price + atr_value * 3 if atr_value else resistencia

    return {
        "symbol": name,
        "price": price,
        "sinal": sinal,
        "confianca": confianca,
        "score": score,
        "rsi": rsi14,
        "heikin": ha,
        "volume": volume_strength,
        "suporte": suporte,
        "resistencia": resistencia,
        "stop": stop,
        "alvo1": alvo1,
        "alvo2": alvo2,
        "motivos": motivos,
    }


def dinheiro(valor):
    if valor < 10:
        return f"${valor:,.4f}"
    return f"${valor:,.2f}"


def montar_relatorio(resultados):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    validos = [r for r in resultados if "erro" not in r]
    erros = [r for r in resultados if "erro" in r]

    oportunidades = sorted(validos, key=lambda x: x["score"], reverse=True)[:3]
    riscos = sorted(validos, key=lambda x: x["score"])[:3]

    linhas = []
    linhas.append("📊 Radar Cripto IA 2.0")
    linhas.append(f"🕒 Atualização: {now}")
    linhas.append("")
    linhas.append("⚠️ Análise automatizada. Não é recomendação financeira.")
    linhas.append("")

    linhas.append("🏆 TOP OPORTUNIDADES")
    for i, item in enumerate(oportunidades, 1):
        linhas.append(f"{i}. {item['symbol']} - {item['sinal']} ({item['confianca']}%)")

    linhas.append("")
    linhas.append("⚠️ MAIORES RISCOS")
    for i, item in enumerate(riscos, 1):
        linhas.append(f"{i}. {item['symbol']} - {item['sinal']} ({item['confianca']}%)")

    linhas.append("")
    linhas.append("📌 DETALHES")
    linhas.append("")

    for item in validos:
        linhas.append(f"🪙 {item['symbol']}")
        linhas.append(f"Sinal: {item['sinal']}")
        linhas.append(f"Confiança: {item['confianca']}%")
        linhas.append(f"Preço: {dinheiro(item['price'])}")
        linhas.append(f"RSI: {item['rsi']:.2f}")
        linhas.append(f"Heikin Ashi: {item['heikin']}")
        linhas.append(f"Volume: {item['volume']:.2f}x")
        linhas.append(f"Suporte: {dinheiro(item['suporte'])}")
        linhas.append(f"Resistência: {dinheiro(item['resistencia'])}")
        linhas.append(f"🛑 Stop: {dinheiro(item['stop'])}")
        linhas.append(f"🎯 Alvo 1: {dinheiro(item['alvo1'])}")
        linhas.append(f"🎯 Alvo 2: {dinheiro(item['alvo2'])}")
        linhas.append(f"Motivos: {'; '.join(item['motivos'][:4])}")
        linhas.append("")

    if erros:
        linhas.append("❌ ERROS")
        for item in erros:
            linhas.append(f"{item['symbol']}: {item['erro']}")

    linhas.append("✅ Use stop loss. Evite alavancagem sem experiência.")

    texto = "\n".join(linhas)

    if len(texto) > 3900:
        texto = texto[:3900] + "\n\nMensagem reduzida pelo limite do Telegram."

    return texto


def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    r = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": msg,
        },
        timeout=30
    )

    r.raise_for_status()


def main(): 
    resultados = []

    for symbol, name in COINS.items():
        try:
            resultado = analisar(symbol, name)
            resultados.append(resultado)
            time.sleep(1)
        except Exception as erro:
            resultados.append({
                "symbol": name,
                "erro": str(erro)
            })

    relatorio = montar_relatorio(resultados)
    enviar_telegram(relatorio)


if __name__ == "__main__":
    main()
