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
    params = {
        "vs_currency": VS_CURRENCY,
        "days": DAYS,
        "interval": "hourly"
    }
    headers = {"User-Agent": "RadarCriptoIA"}

    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    prices = [float(x[1]) for x in data.get("prices", [])]
    volumes = [float(x[1]) for x in data.get("total_volumes", [])]

    if len(prices) < 80:
        raise Exception("Poucos dados retornados pela CoinGecko")

    return prices, volumes



def get_fear_greed():
    """
    Busca o Fear & Greed Index do mercado cripto.
    Se a API falhar, o bot continua funcionando normalmente.
    """
    url = "https://api.alternative.me/fng/"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()

        item = data.get("data", [{}])[0]
        value = int(item.get("value", 50))
        classification = item.get("value_classification", "Neutro")

        return {
            "value": value,
            "classification": classification
        }

    except Exception as erro:
        print(f"Erro ao buscar Fear & Greed: {erro}")
        return {
            "value": None,
            "classification": "Indisponível"
        }


def traduzir_fear_greed(classification):
    mapa = {
        "Extreme Fear": "Medo Extremo",
        "Fear": "Medo",
        "Neutral": "Neutro",
        "Greed": "Ganância",
        "Extreme Greed": "Ganância Extrema",
    }
    return mapa.get(classification, classification)


def sentimento_geral(fear_greed, status_mercado):
    valor = fear_greed.get("value") if fear_greed else None

    if valor is None:
        if "QUEDA" in status_mercado or "PROTEÇÃO" in status_mercado:
            return "🔴 BAIXISTA"
        if "FAVORÁVEL" in status_mercado:
            return "🟢 ALTISTA"
        return "🟡 NEUTRO"

    if valor <= 25:
        return "🔴 MEDO EXTREMO / BAIXISTA"
    if valor <= 45:
        return "🟠 MEDO / CAUTELA"
    if valor <= 60:
        return "🟡 NEUTRO"
    if valor <= 75:
        return "🟢 OTIMISTA"
    return "🟢🟢 GANÂNCIA EXTREMA / CUIDADO COM FOMO"

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


def variacao_periodos(values, periodos):
    if len(values) <= periodos:
        return 0

    valor_anterior = values[-periodos - 1]

    if valor_anterior == 0:
        return 0

    return ((values[-1] - valor_anterior) / valor_anterior) * 100


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

        ha.append({
            "open": ha_open,
            "close": ha_close
        })

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
    if score >= 90:
        return "🟢🟢 LONG EXTREMO"

    if score >= 80:
        return "🟢 LONG FORTE"

    if score >= 70:
        return "🟢 LONG MODERADO"

    if score >= 55:
        return "⚪ AGUARDAR"

    if score >= 40:
        return "🔴 SHORT MODERADO"

    return "🔴 SHORT FORTE"


def calcular_alvos(price, suporte, resistencia, score):
    if score >= 55:
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


def analisar(coin_id, symbol, fear_greed=None):
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

    momentum_1h = variacao_periodos(prices, 1)
    momentum_3h = variacao_periodos(prices, 3)
    ema9_anterior = ema(prices[:-1], 9)
    ema21_anterior = ema(prices[:-1], 21)

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
    elif variation_24h < -3:
        score -= 8
        motivos.append("Queda forte nas últimas 24h")

    if (
        ema9 < ema21
        and ema21 < ema50
        and macd_line is not None
        and macd_signal is not None
        and macd_line < macd_signal
    ):
        score -= 15
        motivos.append("Tendência de baixa confirmada")

    if variation_24h < -5 and volume_strength > 1.20:
        score -= 10
        motivos.append("Pressão vendedora forte")

    if (
        ema9 < ema21
        and ema21 < ema50
        and macd_line is not None
        and macd_signal is not None
        and macd_line < macd_signal
        and rsi14 < 40
    ):
        score -= 20
        motivos.append("Setup SHORT forte: EMA, MACD e RSI confirmados")

    if rsi14 < 35 and macd_line is not None and macd_signal is not None and macd_line < macd_signal:
        score -= 8
        motivos.append("RSI fraco com MACD vendedor")

    if fear_greed and fear_greed.get("value") is not None:
        fg_value = fear_greed["value"]

        if fg_value <= 25:
            score -= 5
            motivos.append("Fear & Greed em medo extremo")
        elif fg_value >= 75:
            score += 3
            motivos.append("Fear & Greed em ganância elevada")

    # Filtro de reversão imediata calibrado:
    # reduz LONG forte quando o ativo começa a cair, mas sem derrubar o score para zero.
    penalizacao_reversao = 0

    if momentum_1h <= -4:
        penalizacao_reversao += 12
        motivos.append("Reversão agressiva na última hora")
    elif momentum_1h <= -2:
        penalizacao_reversao += 8
        motivos.append("Queda forte na última hora")
    elif momentum_1h <= -1:
        penalizacao_reversao += 4
        motivos.append("Pressão vendedora recente")

    if momentum_3h <= -5:
        penalizacao_reversao += 10
        motivos.append("Queda forte nas últimas 3h")
    elif momentum_3h <= -3:
        penalizacao_reversao += 6
        motivos.append("Momentum de 3h enfraquecendo")
    elif momentum_3h <= -1.5:
        penalizacao_reversao += 3
        motivos.append("Momentum de 3h perdendo força")

    if ema9_anterior is not None and ema9 is not None and ema9 < ema9_anterior:
        penalizacao_reversao += 4
        motivos.append("EMA 9 perdeu inclinação")

    if ema21_anterior is not None and ema21 is not None and ema21 < ema21_anterior:
        penalizacao_reversao += 2
        motivos.append("EMA 21 perdendo força")

    if len(prices) >= 3 and prices[-1] < prices[-2] < prices[-3]:
        penalizacao_reversao += 4
        motivos.append("Três períodos consecutivos de queda")

    if heikin_status == "ALTA" and ema9 is not None and price < ema9:
        penalizacao_reversao += 5
        motivos.append("Preço contrariando Heikin Ashi")

    # Limite máximo da penalização por reversão.
    # Assim o bot evita LONG atrasado, mas não transforma correção curta em SHORT FORTE automaticamente.
    penalizacao_reversao = min(18, penalizacao_reversao)
    score -= penalizacao_reversao

    if score >= 70 and momentum_1h <= -1.5:
        score -= 6
        motivos.append("Filtro anti-reversão reduziu sinal LONG")

    score = max(0, min(100, score))

    stop, alvo1, alvo2 = calcular_alvos(price, suporte, resistencia, score)

    return {
        "symbol": symbol,
        "price": price,
        "score": score,
        "rsi": rsi14,
        "variation": variation_24h,
        "momentum_1h": momentum_1h,
        "momentum_3h": momentum_3h,
        "volume": volume_strength,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
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
            if btc_score < 55 and item["score"] >= 70:
                item["score"] -= 12
                item["motivos"].append("Filtro BTC: BTC sem força para validar altcoin")

            if modo_protecao:
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
    if value is None:
        return "N/A"
    if value < 10:
        return f"${value:,.4f}"
    return f"${value:,.2f}"


def number(value):
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def montar_relatorio(resultados, market_index, status_mercado, fear_greed):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    validos = [r for r in resultados if "erro" not in r]
    erros = [r for r in resultados if "erro" in r]

    oportunidades = sorted(validos, key=lambda x: x["score"], reverse=True)[:3]
    riscos = sorted(validos, key=lambda x: x["score"])[:3]

    linhas = []
    linhas.append("📊 Radar Cripto IA 3.3")
    linhas.append(f"🕒 Atualização: {now}")
    linhas.append("")
    linhas.append(f"🌎 Mercado: {status_mercado}")
    linhas.append(f"📈 Radar Market Index: {market_index}/100")

    fg_value = fear_greed.get("value") if fear_greed else None
    fg_class = traduzir_fear_greed(fear_greed.get("classification", "Indisponível")) if fear_greed else "Indisponível"

    if fg_value is not None:
        linhas.append(f"😱 Fear & Greed: {fg_value}/100 ({fg_class})")
    else:
        linhas.append("😱 Fear & Greed: Indisponível")

    linhas.append(f"🧭 Sentimento Geral: {sentimento_geral(fear_greed, status_mercado)}")
    linhas.append("")
    linhas.append("⚠️ Análise automatizada. Não é recomendação financeira.")
    linhas.append("")

    linhas.append("🏆 TOP OPORTUNIDADES")
    for i, item in enumerate(oportunidades, 1):
        linhas.append(f"{i}. {item['symbol']} - {item['sinal']} | Score {item['score']}/100")

    linhas.append("")
    linhas.append("⚠️ MAIORES RISCOS / SHORT")
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
        linhas.append(f"MACD: {number(item['macd_line'])}")
        linhas.append(f"MACD Sinal: {number(item['macd_signal'])}")
        linhas.append(f"EMA 9: {money(item['ema9'])}")
        linhas.append(f"EMA 21: {money(item['ema21'])}")
        linhas.append(f"EMA 50: {money(item['ema50'])}")
        linhas.append(f"Heikin Ashi: {item['heikin']}")
        linhas.append(f"Variação 24h: {item['variation']:.2f}%")
        linhas.append(f"Momentum 1h: {item['momentum_1h']:.2f}%")
        linhas.append(f"Momentum 3h: {item['momentum_3h']:.2f}%")
        linhas.append(f"Volume: {item['volume']:.2f}x")
        linhas.append(f"Suporte: {money(item['suporte'])}")
        linhas.append(f"Resistência: {money(item['resistencia'])}")
        linhas.append(f"🛑 Stop: {money(item['stop'])}")
        linhas.append(f"🎯 Alvo 1: {money(item['alvo1'])}")
        linhas.append(f"🎯 Alvo 2: {money(item['alvo2'])}")
        linhas.append(f"Motivos: {'; '.join(item['motivos'][:5])}")

    if erros:
        linhas.append("")
        linhas.append("❌ ERROS")
        for item in erros:
            linhas.append(f"{item['symbol']}: {item['erro']}")

    linhas.append("")
    linhas.append("⚠️ Gestão de risco: máx. 10x isolado | risco até 2%.")

    return "\n".join(linhas)



def montar_alertas_extremos(resultados):
    validos = [r for r in resultados if "erro" not in r]

    extremos = [
        r for r in validos
        if r["score"] >= 90 or r["score"] <= 25
    ]

    if not extremos:
        return None

    extremos = sorted(
        extremos,
        key=lambda x: x["score"],
        reverse=True
    )

    linhas = []
    linhas.append("🚨 ALERTAS EXTREMOS - Radar Cripto IA 3.3")

    for item in extremos:
        linhas.append("")
        linhas.append(f"🪙 {item['symbol']} - {item['sinal']}")
        linhas.append(f"Score: {item['score']}/100")
        linhas.append(f"Preço: {money(item['price'])}")
        linhas.append(f"RSI: {item['rsi']:.2f} | 1h: {item['momentum_1h']:.2f}% | 3h: {item['momentum_3h']:.2f}% | Vol: {item['volume']:.2f}x")
        linhas.append(f"Stop: {money(item['stop'])}")
        linhas.append(f"Alvos: {money(item['alvo1'])} / {money(item['alvo2'])}")
        linhas.append(f"Motivos: {'; '.join(item['motivos'][:4])}")

    linhas.append("")
    linhas.append("⚠️ Gestão de risco: máx. 10x isolado | risco até 2%.")

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
    fear_greed = get_fear_greed()

    for coin_id, symbol in COINS.items():
        try:
            resultado = analisar(coin_id, symbol, fear_greed)
            resultados.append(resultado)
            time.sleep(SLEEP_BETWEEN_COINS)
        except Exception as erro:
            resultados.append({
                "symbol": symbol,
                "erro": str(erro)
            })

    resultados, market_index, status_mercado = aplicar_contexto_mercado(resultados)
    relatorio = montar_relatorio(resultados, market_index, status_mercado, fear_greed)
    enviar_telegram(relatorio)

    alertas = montar_alertas_extremos(resultados)
    if alertas:
        enviar_telegram(alertas)


if __name__ == "__main__":
    main()
