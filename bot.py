import os
import time
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

COINS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "avalanche-2": "AVAX",
    "chainlink": "LINK",
    "litecoin": "LTC",
    "polkadot": "DOT",
}

VS_CURRENCY = "usd"
DAYS = 30
SLEEP_BETWEEN_COINS = 20


def get_market_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": VS_CURRENCY, "days": DAYS, "interval": "hourly"}
    headers = {"User-Agent": "RadarCriptoIA"}

    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    prices = [float(x[1]) for x in data.get("prices", [])]
    volumes = [float(x[1]) for x in data.get("total_volumes", [])]

    if len(prices) < 80:
        raise Exception("Poucos dados retornados pela CoinGecko")

    return prices, volumes


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

    history = []
    for i in range(26, len(values)):
        e12 = ema(values[:i + 1], 12)
        e26 = ema(values[:i + 1], 26)

        if e12 is not None and e26 is not None:
            history.append(e12 - e26)

    signal = ema(history, 9) if len(history) >= 9 else None
    return macd_line, signal


def suporte_resistencia(values):
    recentes = values[-72:]
    return min(recentes), max(recentes)


def heikin_ashi_signal(values):
    if len(values) < 10:
        return "NEUTRO", 0

    candles = []

    for i in range(1, len(values)):
        open_price = values[i - 1]
        close_price = values[i]
        high_price = max(open_price, close_price)
        low_price = min(open_price, close_price)

        candles.append({
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price
        })

    ha = []

    for i, c in enumerate(candles):
        ha_close = (c["open"] + c["high"] + c["low"] + c["close"]) / 4

        if i == 0:
            ha_open = (c["open"] + c["close"]) / 2
        else:
            ha_open = (ha[-1]["open"] + ha[-1]["close"]) / 2

        ha.append({"open": ha_open, "close": ha_close})

    last = ha[-1]
    prev = ha[-2]

    if last["close"] > last["open"] and prev["close"] > prev["open"]:
        return "ALTA", 10

    if last["close"] < last["open"] and prev["close"] < prev["open"]:
        return "BAIXA", -10

    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        return "VIRANDO PARA ALTA", 8

    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        return "VIRANDO PARA BAIXA", -8

    return "NEUTRO", 0


def definir_sinal(score):
    if score >= 80:
        return "🟢 LONG FORTE"
    if score >= 65:
        return "🟢 COMPRA / LONG"
    if score >= 45:
        return "⚪ AGUARDAR"
    if score >= 30:
        return "🔴 VENDA / SHORT"
    return "🔴 SHORT FORTE"


def calcular_alvos(price, suporte, resistencia, score):
    if score >= 45:
        stop = suporte
        risco = price - stop

        if risco <= 0:
            risco = price * 0.03

        alvo1 = price + (risco * 1.5)
        alvo2 = price + (risco * 2.5)

    else:
        stop = resistencia
        risco = stop - price

        if risco <= 0:
            risco = price * 0.03

        alvo1 = price - (risco * 1.5)
        alvo2 = price - (risco * 2.5)

    return stop, alvo1, alvo2


def analisar(coin_id, symbol):
    prices, volumes = get_market_data(coin_id)

    price = prices[-1]
    variation_24h = ((prices[-1] - prices[-24]) / prices[-24]) * 100 if len(prices) >= 24 else 0

    ema9 = ema(prices, 9)
    ema21 = ema(prices, 21)
    ema50 = ema(prices, 50)
    rsi14 = rsi(prices, 14)
    macd_line, macd_signal = macd(prices)
    suporte, resistencia = suporte_resistencia(prices)
    heikin_status, heikin_score = heikin_ashi_signal(prices)

    avg_volume = sum(volumes[-72:]) / 72 if len(volumes) >= 72 else sum(volumes) / len(volumes)
    volume_strength = volumes[-1] / avg_volume if avg_volume else 1

    score = 50
    motivos = []

    if ema9 > ema21:
        score += 12
        motivos.append("EMA 9 acima da EMA 21")
    else:
        score -= 12
        motivos.append("EMA 9 abaixo da EMA 21")

    if ema21 > ema50:
        score += 12
        motivos.append("EMA 21 acima da EMA 50")
    else:
        score -= 12
        motivos.append("EMA 21 abaixo da EMA 50")

    if rsi14 < 30:
        score += 8
        motivos.append("RSI em sobrevenda")
    elif rsi14 > 70:
        score -= 15
        motivos.append("RSI em sobrecompra")
    elif rsi14 < 45:
        score -= 8
        motivos.append("RSI fraco")
    elif 45 <= rsi14 <= 65:
        score += 6
        motivos.append("RSI saudável")
    else:
        motivos.append("RSI neutro")

    if macd_line is not None and macd_signal is not None:
        if macd_line > macd_signal:
            score += 12
            motivos.append("MACD positivo")
        else:
            score -= 12
            motivos.append("MACD negativo")

    score += heikin_score
    motivos.append(f"Heikin Ashi {heikin_status}")

    if volume_strength > 1.25:
        score += 6
        motivos.append("Volume acima da média")
    elif volume_strength < 0.70:
        score -= 6
        motivos.append("Volume fraco")

    if variation_24h > 8:
        score -= 10
        motivos.append("Anti-FOMO: alta muito forte em 24h")
    elif variation_24h > 3:
        score += 5
        motivos.append("Alta positiva nas últimas 24h")
    elif variation_24h < -2:
        score -= 12
        motivos.append("Queda forte nas últimas 24h")

    if (
        ema9 < ema21
        and ema21 < ema50
        and macd_line is not None
        and macd_signal is not None
        and macd_line < macd_signal
        and rsi14 < 50
    ):
        score -= 18
        motivos.append("Setup SHORT confirmado")

    if variation_24h < -4 and volume_strength > 1.20:
        score -= 10
        motivos.append("Pressão vendedora com volume")

    score = max(0, min(100, score))

    stop, alvo1, alvo2 = calcular_alvos(price, suporte, resistencia, score)

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "rsi": rsi14,
        "variation": variation_24h,
        "volume": volume_strength,
        "heikin": heikin_status,
        "suporte": suporte,
        "resistencia": resistencia,
        "stop": stop,
        "alvo1": alvo1,
        "alvo2": alvo2,
        "motivos": motivos,
    }


def aplicar_contexto_mercado(resultados):
    validos = [r for r in resultados if "erro" not in r]

    if not validos:
        return resultados, 0, "SEM DADOS"

    btc = next((r for r in validos if r["symbol"] == "BTC"), None)
    btc_score = btc["score"] if btc else 50

    media_mercado = sum(r["score"] for r in validos) / len(validos)
    moedas_fracas = len([r for r in validos if r["score"] < 45])
    modo_protecao = btc_score < 45 or moedas_fracas >= 6

    if modo_protecao:
        status_mercado = "🔴 MODO PROTEÇÃO / VIÉS DE QUEDA"
    elif media_mercado >= 70:
        status_mercado = "🟢 MERCADO FAVORÁVEL"
    elif media_mercado >= 55:
        status_mercado = "🟡 MERCADO NEUTRO"
    else:
        status_mercado = "🟠 MERCADO FRACO"

    for item in validos:
        if item["symbol"] != "BTC":
            if btc_score < 55 and item["score"] >= 65:
                item["score"] -= 12
                item["motivos"].append("Filtro BTC: BTC sem força")

            if modo_protecao and item["score"] >= 45:
                item["score"] -= 10
                item["motivos"].append("Modo proteção ativo")

        item["score"] = max(0, min(100, item["score"]))
        item["sinal"] = definir_sinal(item["score"])

        stop, alvo1, alvo2 = calcular_alvos(
            item["price"],
            item["suporte"],
            item["resistencia"],
            item["score"]
        )

        item["stop"] = stop
        item["alvo1"] = alvo1
        item["alvo2"] = alvo2

    return resultados, round(media_mercado, 1), status_mercado


def money(value):
    if value < 10:
        return f"${value:,.4f}"
    return f"${value:,.2f}"


def montar_relatorio(resultados, market_index, status_mercado):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    validos = [r for r in resultados if "erro" not in r]
    erros = [r for r in resultados if "erro" in r]

    longs = sorted([r for r in validos if r["score"] >= 65], key=lambda x: x["score"], reverse=True)[:3]
    shorts = sorted([r for r in validos if r["score"] < 45], key=lambda x: x["score"])[:3]

    linhas = []
    linhas.append("📊 Radar Cripto IA 3.1")
    linhas.append(f"🕒 {now}")
    linhas.append(f"🌎 Mercado: {status_mercado}")
    linhas.append(f"📈 Market Index: {market_index}/100")
    linhas.append("⚠️ Análise automatizada. Não é recomendação financeira.")
    linhas.append("")

    linhas.append("🟢 TOP LONG")
    if longs:
        for i, item in enumerate(longs, 1):
            linhas.append(f"{i}. {item['symbol']} | {item['sinal']} | Score {item['score']}/100")
    else:
        linhas.append("Sem entrada LONG forte agora.")

    linhas.append("")
    linhas.append("🔴 TOP SHORT")
    if shorts:
        for i, item in enumerate(shorts, 1):
            linhas.append(f"{i}. {item['symbol']} | {item['sinal']} | Score {item['score']}/100")
    else:
        linhas.append("Sem entrada SHORT forte agora.")

    linhas.append("")
    linhas.append("📌 DETALHES")

    for item in validos:
        linhas.append("")
        linhas.append(f"🪙 {item['symbol']} - {item['sinal']}")
        linhas.append(f"Score: {item['score']}/100 | Preço: {money(item['price'])}")
        linhas.append(f"RSI: {item['rsi']:.2f} | 24h: {item['variation']:.2f}% | Vol: {item['volume']:.2f}x")
        linhas.append(f"Stop: {money(item['stop'])}")
        linhas.append(f"Alvos: {money(item['alvo1'])} / {money(item['alvo2'])}")
        linhas.append(f"Motivos: {'; '.join(item['motivos'][:3])}")

    if erros:
        linhas.append("")
        linhas.append("❌ ERROS")
        for item in erros:
            linhas.append(f"{item['symbol']}: {item['erro']}")

    linhas.append("")
    linhas.append("⚠️ Gestão de risco: máx. 10x isolado.")

    return "\n".join(linhas)


def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    limite = 3800
    partes = [msg[i:i + limite] for i in range(0, len(msg), limite)]

    for parte in partes:
        r = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": parte
            },
            timeout=30
        )

        r.raise_for_status()
        time.sleep(1)


def main():
    resultados = []

    for coin_id, symbol in COINS.items():
        try:
            resultado = analisar(coin_id, symbol)
            resultados.append(resultado)
            time.sleep(SLEEP_BETWEEN_COINS)
        except Exception as erro:
            resultados.append({
                "symbol": symbol,
                "erro": str(erro)
            })

    resultados, market_index, status_mercado = aplicar_contexto_mercado(resultados)
    relatorio = montar_relatorio(resultados, market_index, status_mercado)
    enviar_telegram(relatorio)


if __name__ == "__main__":
    main()
