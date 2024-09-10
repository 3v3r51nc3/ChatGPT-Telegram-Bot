# chatgpt.py
import asyncio
import logging

import g4f.models
import requests.exceptions
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionMiddleware, ChatActionSender
from aiogram.utils.i18n import gettext as _
from g4f import ChatCompletion, Provider
from config import admin_ids

from bot.middlewares import DatabaseMiddleware, ObservedFieldRestrictionMiddleware
from bot_instance import bot
from database.database import db

"""logging.basicConfig(
    filename='chatgpt.log',  # Specify the log file
    level=logging.ERROR,  # Set the logging level to capture ERROR and above
    format='%(asctime)s - %(levelname)s - %(message)s',
)"""


# Define the ChatGPT class for handling chat responses
class ChatGPT:
    def __init__(self):
        # Initialize message history and initial settings
        self.message_history = {}
        self.initial_settings = {"role": "system",
                                 "content": "You are a kind and sensible assistant. "
                                            "You must answer the questions with the language which user speaks."}

    # Get or initialize user message history
    async def get_history(self, user_id):
        if user_id not in self.message_history:
            self.message_history[user_id] = [self.initial_settings]
        return self.message_history[user_id]

    # Erase user message history
    async def erase_history(self, user_id):
        if user_id in self.message_history:
            self.message_history[user_id] = [self.initial_settings]
            return True
        else:
            return False

    # Add response to message history
    async def add_response(self, user_id, message):
        history = await self.get_history(user_id)
        history.append(message)

    # Create ChatCompletion using the GPT model
    async def make_request(self, messages, provider: Provider):
        response = await ChatCompletion.create_async(
            model=g4f.models.gpt_35_turbo,
            messages=messages,
            provider=provider,
        )
        return response

    # Get response from ChatGPT
    async def get_response(self, user_id, text):
        # Adding user's message to the message history
        history = await self.get_history(user_id)
        history.append({"role": "user", "content": text})
        response = await self.make_request(history, Provider.HuggingChat)

        # Check for incomplete code blocks and fix them
        if "```" in response and response.count("```") % 2 != 0:
            response += "```"
        history.append({'role': "assistant", 'content': response})
        return response


# Create an instance of the ChatGPT class
chatgpt = ChatGPT()
gptrouter = Router()

# Apply middlewares for chat handling
gptrouter.message.middleware(ObservedFieldRestrictionMiddleware())
gptrouter.message.middleware(ChatActionMiddleware())
gptrouter.message.middleware(DatabaseMiddleware(request_type="text_requests"))


# Define a handler for text messages
@gptrouter.message(F.text)
async def chat(msg: Message, state: FSMContext):
    # Send a "Generating..." message
    mes = await bot.send_message(msg.chat.id, _("Generating..."), parse_mode="Markdown",
                                 reply_to_message_id=msg.message_id)

    await reply(msg, mes)

async def reply(msg: Message, mes: Message, retry=0):
    if retry > 3:
        await bot.edit_message_text(chat_id=mes.chat.id, message_id=mes.message_id,
                                    text=_("Sorry, no provider has responded."))
        return

    if msg.reply_to_message and msg.reply_to_message.text:
        request_text = (f"User replies to this message:\n\n{msg.reply_to_message.text}\n\n"
                        f"with this request:\n\n"
                        f"{msg.text}")
    else:
        request_text = msg.text

    async with ChatActionSender(bot=bot, chat_id=msg.chat.id):
        # Get response from ChatGPT
        try:
            response = await chatgpt.get_response(msg.from_user.id, request_text)
            # Delete the "Generating..." message and send the response
            mes = await bot.edit_message_text(chat_id=mes.chat.id, message_id=mes.message_id, text=response)
            await db.log_message(mes)
            return

        # Handle HTTP errors from the GPT model
        except requests.exceptions.HTTPError as e:
            retry += 1
            if e.response.status_code == 429 or 401:
                await bot.edit_message_text(chat_id=mes.chat.id, message_id=mes.message_id,
                                            text=_("Too many requests. Try again later"))
                return await reply(msg, mes, retry)
            else:
                response = _("Sorry, your message wasn't handled properly. Please retry or try to clear your history.")
                logging.error(f"Exception occurred: {str(e)}")

        except Exception as e:
            logging.error(f"Exception occurred: {str(e)}")
            for user_id in admin_ids:
                await bot.send_message(user_id, str(e))
            # Handle exceptions, e.g., message too long
            if "MESSAGE_TOO_LONG" in str(e):
                midpoint = len(response) / 2
                await bot.edit_message_text(chat_id=mes.chat.id, message_id=mes.message_id,
                                            text=response[:midpoint])
                await msg.answer(response[midpoint:], reply_to_message_id=mes.message_id)
                return
            else:
                retry += 1
                await bot.edit_message_text(chat_id=mes.chat.id, message_id=mes.message_id,
                                            text=_(
                                                "Sorry, some problem occurred."))
                return await reply(msg, mes, retry)
