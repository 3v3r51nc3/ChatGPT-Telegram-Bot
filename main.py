# main.py

# Import necessary modules and libraries
import asyncio
import datetime
import logging

import aiogram
from aiogram import Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.modules.ChatGPT.chatgpt import chatgpt
from bot.scheduled import scheduler
from bot_instance import bot
from config import DEBUG_MODE
from database.database import db
from dispatcher_instance import dp

# Configure logging
if DEBUG_MODE:
    logging.basicConfig(
        filename='bot.log',  # Specify the log file
        level=logging.ERROR,  # Set the logging level to capture ERROR and above
        format='%(asctime)s - %(levelname)s - %(message)s',
    )


def register_routers(dp: Dispatcher) -> None:
    """Registers routers"""
    # Import routers from different modules
    from bot.modules.yt.youtube import ytrouter
    from bot.modules.tiktok.tiktok import ttrouter
    from bot.commands import cmdrouter
    from bot.modules.ChatGPT.chatgpt import gptrouter
    from bot.modules.images.image_generation import imgenrouter
    from bot.modules.audio.audio import avrouter
    from bot.modules.images.images_handler import imgrouter
    from bot.modules.images.text_recognition import txtrcgrouter
    from bot.settings import settings

    # Append routers with commands in a specific order
    dp.include_routers(imgenrouter, settings, cmdrouter, ytrouter, ttrouter, imgrouter, gptrouter,
                       avrouter, txtrcgrouter)


async def on_startup(bot: aiogram.Bot):
    # Start the scheduler and create database tables on bot startup
    scheduler.start()
    await db.create_tables()

    print(f"{datetime.datetime.now().strftime('(%Y-%m-%d)  %H:%M.%S')} >> Bot Started")


async def polling(dp, bot):
    await dp.start_polling(bot)


def main(dp) -> None:
    # Register routers and set up startup logic
    register_routers(dp)
    dp.startup.register(on_startup)

    asyncio.run(polling(dp, bot))


if __name__ == "__main__":
    main(dp)
