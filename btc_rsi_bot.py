import asyncio
import logging
import os
import requests
import pandas as pd
import ta
from datetime import datetime
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes

# ─────────────────────────────────────────────
#  CONFIGURACIÓN — Variables de entorno
# ─────────────────────────────────────────────
BOT_TOKEN  = ("7795736140:AAHDondXqsAKh6OQ8H8q9QHE5DOsWyaAck8")
CHAT_ID    = ("1589330152")

RSI_PERIOD      = 14
RSI_OVERSOLD    = 30
RSI_OVERBOUGHT  = 70
CHECK_INTERVAL  = 300
# ─────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

last_alert = None
monitoring = False


def get_rsi():
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc"
    params = {"vs_currency": "usd", "days": "1"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()

    data = r.json()
    closes = pd.Series([c[4] for c in data])

    rsi = ta.momentum.RSIIndicator(close=closes, window=RSI_PERIOD).rsi()
    return round(rsi.iloc[-1], 2), round(closes.iloc[-1], 2)


def emoji_rsi(rsi):
    if rsi <= RSI_OVERSOLD:
        return "🟢"
    if rsi >= RSI_OVERBOUGHT:
        return "🔴"
    return "🟡"


async def send_alert(bot, rsi, price, kind):
    icons = {"oversold": "🟢📉", "overbought": "🔴📈"}
    titles = {
        "oversold":   "SEÑAL DE COMPRA — RSI en SOBREVENTA",
        "overbought": "SEÑAL DE VENTA — RSI en SOBRECOMPRA",
    }
    msg = (
        f"{icons[kind]}  *{titles[kind]}*\n\n"
        f"Precio BTC:  *${price:,.2f} USDT*\n"
        f"RSI ({RSI_PERIOD}):     *{rsi}*\n"
        f"Hora:       {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}\n\n"
        f"_Esto no es consejo financiero_ 🤖"
    )
    await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
    log.info("Alerta enviada: %s | RSI=%.2f | BTC=$%.2f", kind, rsi, price)


async def monitor_loop(bot):
    global last_alert, monitoring

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
                last_alert = None

        except Exception as exc:
            log.error("Error obteniendo RSI: %s", exc)

        await asyncio.sleep(CHECK_INTERVAL)


async def cmd_start(update, context):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 *Bot RSI Bitcoin activo*\n\n"
        f"Tu Chat ID es: `{chat_id}`\n\n"
        f"Comandos disponibles:\n"
        f"/status — Ver RSI y precio actual\n"
        f"/monitor — Iniciar monitoreo continuo\n"
        f"/stop — Detener el monitoreo\n"
        f"/config — Ver configuracion actual",
        parse_mode="Markdown"
    )


async def cmd_status(update, context):
    try:
        rsi, price = get_rsi()
        e = emoji_rsi(rsi)
        if rsi <= RSI_OVERSOLD:
            zona = "SOBREVENTA (posible compra)"
        elif rsi >= RSI_OVERBOUGHT:
            zona = "SOBRECOMPRA (posible venta)"
        else:
            zona = "ZONA NEUTRAL"
        await update.message.reply_text(
            f"{e} *Estado actual de BTC*\n\n"
            f"Precio:    *${price:,.2f} USDT*\n"
            f"RSI ({RSI_PERIOD}):  *{rsi}*\n"
            f"Zona:      {zona}\n"
            f"Actualizado: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode="Markdown"
        )
    except Exception as exc:
        await update.message.reply_text(f"Error: {exc}")


async def cmd_monitor(update, context):
    global monitoring
    if monitoring:
        await update.message.reply_text("El monitoreo ya esta activo.")
        return
    monitoring = True
    await update.message.reply_text(
        f"*Monitoreo iniciado*\n"
        f"Revisare el RSI cada {CHECK_INTERVAL // 60} minutos.\n"
        f"Usa /stop para detenerlo.",
        parse_mode="Markdown"
    )
    asyncio.create_task(monitor_loop(context.bot))


async def cmd_stop(update, context):
    global monitoring
    monitoring = False
    await update.message.reply_text("Monitoreo detenido.")


async def cmd_config(update, context):
    await update.message.reply_text(
        f"*Configuracion actual*\n\n"
        f"Periodo RSI:     {RSI_PERIOD}\n"
        f"Sobreventa:      {RSI_OVERSOLD}\n"
        f"Sobrecompra:     {RSI_OVERBOUGHT}\n"
        f"Intervalo check: {CHECK_INTERVAL}s",
        parse_mode="Markdown"
    )


def main():
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
