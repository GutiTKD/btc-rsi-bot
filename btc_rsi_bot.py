"""
Bot de Telegram - Alertas RSI Bitcoin
======================================
Requisitos:
    pip install python-telegram-bot requests pandas ta

Configuración:
    1. Crea un bot en Telegram con @BotFather y copia el TOKEN
    2. Escríbele al bot /start para obtener tu CHAT_ID
    3. Rellena BOT_TOKEN y CHAT_ID abajo
"""

import asyncio
import logging
import requests
import pandas as pd
import ta
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
#  CONFIGURACIÓN  (edita estos valores)
# ─────────────────────────────────────────────
BOT_TOKEN  = "TU_TOKEN_AQUI"       # Token de @BotFather
CHAT_ID    = "TU_CHAT_ID_AQUI"     # Tu chat ID (usa /start para verlo)

RSI_PERIOD      = 14        # Período del RSI (estándar = 14)
RSI_OVERSOLD    = 30        # Nivel de sobreventa  → señal de COMPRA
RSI_OVERBOUGHT  = 70        # Nivel de sobrecompra → señal de VENTA
CHECK_INTERVAL  = 300       # Segundos entre cada chequeo (300 = 5 min)
TIMEFRAME       = "5m"      # Vela: 1m, 5m, 15m, 1h, 4h, 1d
CANDLES         = 100       # Velas a descargar para calcular RSI
# ─────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ── Estado global ──────────────────────────────
last_alert: str | None = None   # Evita repetir la misma alerta
monitoring  = False             # Bandera on/off


def get_rsi() -> tuple[float, float]:
    """
    Descarga velas de BTC/USDT desde Binance y calcula el RSI.
    Retorna (rsi_actual, precio_actual).
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": TIMEFRAME,
        "limit": CANDLES,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()

    data = r.json()
    closes = pd.Series([float(c[4]) for c in data])   # close price

    rsi = ta.momentum.RSIIndicator(close=closes, window=RSI_PERIOD).rsi()
    return round(rsi.iloc[-1], 2), round(closes.iloc[-1], 2)


def emoji_rsi(rsi: float) -> str:
    if rsi <= RSI_OVERSOLD:
        return "🟢"
    if rsi >= RSI_OVERBOUGHT:
        return "🔴"
    return "🟡"


async def send_alert(bot: Bot, rsi: float, price: float, kind: str) -> None:
    icons = {"oversold": "🟢📉", "overbought": "🔴📈"}
    titles = {
        "oversold":   "⚡ SEÑAL DE COMPRA — RSI en SOBREVENTA",
        "overbought": "⚡ SEÑAL DE VENTA — RSI en SOBRECOMPRA",
    }
    msg = (
        f"{icons[kind]}  *{titles[kind]}*\n\n"
        f"• Precio BTC:  *${price:,.2f} USDT*\n"
        f"• RSI ({RSI_PERIOD}):     *{rsi}*\n"
        f"• Timeframe:  `{TIMEFRAME}`\n"
        f"• Hora:       `{datetime.now().strftime('%H:%M:%S %d/%m/%Y')}`\n\n"
        f"_Esto no es consejo financiero_ 🤖"
    )
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
    log.info("Alerta enviada: %s | RSI=%.2f | BTC=$%.2f", kind, rsi, price)


async def monitor_loop(bot: Bot) -> None:
    """Bucle principal de monitoreo."""
    global last_alert, monitoring

    log.info("Monitoreo iniciado — intervalo=%ds  TF=%s", CHECK_INTERVAL, TIMEFRAME)

    while monitoring:
        try:
            rsi, price = get_rsi()
            log.info("RSI=%.2f | BTC=$%.2f", rsi, price)

            if rsi <= RSI_OVERSOLD and last_alert != "oversold":
                await send_alert(bot, rsi, price, "oversold")
                last_alert = "oversold"

            elif rsi >= RSI_OVERBOUGHT and last_alert != "overbought":
                await send_alert(bot, rsi, price, "overbought")
                last_alert = "overbought"

            elif RSI_OVERSOLD < rsi < RSI_OVERBOUGHT:
                last_alert = None   # Reset cuando vuelve a zona neutral

        except Exception as exc:
            log.error("Error obteniendo RSI: %s", exc)

        await asyncio.sleep(CHECK_INTERVAL)


# ── Comandos de Telegram ───────────────────────

async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 *Bot RSI Bitcoin activo*\n\n"
        f"Tu Chat ID es: `{chat_id}`\n\n"
        f"Comandos disponibles:\n"
        f"• /status — Ver RSI y precio actual\n"
        f"• /monitor — Iniciar monitoreo continuo\n"
        f"• /stop — Detener el monitoreo\n"
        f"• /config — Ver configuración actual",
        parse_mode="Markdown"
    )


async def cmd_status(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        rsi, price = get_rsi()
        e = emoji_rsi(rsi)
        zona = (
            "SOBREVENTA 📉 (posible compra)" if rsi <= RSI_OVERSOLD
            else "SOBRECOMPRA 📈 (posible venta)" if rsi >= RSI_OVERBOUGHT
            else "ZONA NEUTRAL"
        )
        await update.message.reply_text(
            f"{e} *Estado actual de BTC*\n\n"
            f"• Precio:    *${price:,.2f} USDT*\n"
            f"• RSI ({RSI_PERIOD}):  *{rsi}*\n"
            f"• Zona:      _{zona}_\n"
            f"• Timeframe: `{TIMEFRAME}`\n"
            f"• Actualizado: `{datetime.now().strftime('%H:%M:%S')}`",
            parse_mode="Markdown"
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {exc}")


async def cmd_monitor(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global monitoring
    if monitoring:
        await update.message.reply_text("⚠️ El monitoreo ya está activo.")
        return
    monitoring = True
    await update.message.reply_text(
        f"✅ *Monitoreo iniciado*\n"
        f"Revisaré el RSI cada *{CHECK_INTERVAL // 60} minutos*.\n"
        f"Usa /stop para detenerlo.",
        parse_mode="Markdown"
    )
    asyncio.create_task(monitor_loop(context.bot))


async def cmd_stop(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global monitoring
    monitoring = False
    await update.message.reply_text("🛑 Monitoreo detenido.")


async def cmd_config(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"⚙️ *Configuración actual*\n\n"
        f"• Timeframe:       `{TIMEFRAME}`\n"
        f"• Período RSI:     `{RSI_PERIOD}`\n"
        f"• Sobreventa (<):  `{RSI_OVERSOLD}`\n"
        f"• Sobrecompra (>): `{RSI_OVERBOUGHT}`\n"
        f"• Intervalo check: `{CHECK_INTERVAL}s`",
        parse_mode="Markdown"
    )


# ── Main ───────────────────────────────────────

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("monitor", cmd_monitor))
    app.add_handler(CommandHandler("stop",    cmd_stop))
    app.add_handler(CommandHandler("config",  cmd_config))

    log.info("Bot arrancado. Esperando comandos...")
    app.run_polling()


if __name__ == "__main__":
    main()
