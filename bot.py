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


def get_market_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": VS_CURRENCY,
        "days": DAYS,
        "interval": "hourly"
    }

    headers = {
        "User-Agent": "RadarCriptoIA"
    }

    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    prices = [float(x[1]) for x in data.get("prices", [])]
    volumes = [float(x[1]) for x in data.get("total_volumes", [])]

    if len(prices) < 50:
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
    suporte = min(recentes)
    resistencia = max(recentes)
    return suporte, resistencia


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
        score -= 10
        motivos.append("EMA 21 abaixo da EMA 50")

    if rsi14 < 30:
        score += 12
        motivos.append("RSI em sobrevenda")
    elif rsi14 > 70:
        score -= 15
        motivos.append("RSI em sobrecompra")
    elif 40 <= rsi14 <= 65:
        score += 8
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

    if volume_strength > 1.25:
        score += 6
        motivos.append("Volume acima da média")
    elif volume_strength < 0.70:
        score -= 6
        motivos.append("Volume fraco")

    if variation_24h > 3:
        score += 5
        motivos.append("Alta forte nas últimas 24h")
    elif variation_24h < -3:
        score -= 5
        motivos.append("Queda forte nas últimas 24h")

    score = max(0, min(100, score))

    if score >= 80:
        sinal = "🟢 COMPRA FORTE"
    elif score >= 65:
        sinal = "🟢 COMPRA MODERADA"
    elif score <= 25:
        sinal = "🔴 VENDA FORTE"
    elif score <= 40:
        sinal = "🟠 VENDA / REDUZIR"
    else:
        sinal = "⚪ AGUARDAR"

    stop = suporte
    alvo1 = price + ((resistencia - suporte) * 0.5)
    alvo2 = resistencia

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "sinal": sinal,
        "rsi": rsi14,
        "variation": variation_24h,
        "volume": volume_strength,
        "suporte": suporte,
        "resistencia": resistencia,
        "stop": stop,
        "alvo1": alvo1,
        "alvo2": alvo2,
        "motivos": motivos,
    }


def money(value):
    if value < 10:
        return f"${value:,.4f}"
    return f"${value:,.2f}"


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
        linhas.append(f"{i}. {item['symbol']} - {item['sinal']} | Score {item['score']}/100")

    linhas.append("")
    linhas.append("⚠️ MAIORES RISCOS")
    for i, item in enumerate(riscos, 1):
        linhas.append(f"{i}. {item['symbol']} - {item['sinal']} | Score {item['score']}/100")

    linhas.append("")
    linhas.append("📌 DETALHES")

    for item in validos:
        linhas.append("")
        linhas.append(f"🪙 {item['symbol']}")
        linhas.append(f"Sinal: {item['sinal']}")
        linhas.append(f"Score: {item['score']}/100")
        linhas.append(f"Preço: {money(item['price'])}")
        linhas.append(f"RSI: {item['rsi']:.2f}")
        linhas.append(f"Variação 24h: {item['variation']:.2f}%")
        linhas.append(f"Volume: {item['volume']:.2f}x")
        linhas.append(f"Suporte: {money(item['suporte'])}")
        linhas.append(f"Resistência: {money(item['resistencia'])}")
        linhas.append(f"🛑 Stop: {money(item['stop'])}")
        linhas.append(f"🎯 Alvo 1: {money(item['alvo1'])}")
        linhas.append(f"🎯 Alvo 2: {money(item['alvo2'])}")
        linhas.append(f"Motivos: {'; '.join(item['motivos'][:4])}")

    if erros:
        linhas.append("")
        linhas.append("❌ ERROS")
        for item in erros:
            linhas.append(f"{item['symbol']}: {item['erro']}")

    linhas.append("")
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
            "text": msg
        },
        timeout=30
    )

    r.raise_for_status()


def main():
    resultados = []

    for coin_id, symbol in COINS.items():
        try:
            resultado = analisar(coin_id, symbol)
            resultados.append(resultado)
            time.sleep(2)
        except Exception as erro:
            resultados.append({
                "symbol": symbol,
                "erro": str(erro)
            })

    relatorio = montar_relatorio(resultados)
    enviar_telegram(relatorio)


if __name__ == "__main__":
    main()
