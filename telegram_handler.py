import os
import logging
from typing import Callable, Any, Tuple

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from user_handler_interface import BaseHandler
# Actual imports from mazkir.py (assuming mazkir.py is in PYTHONPATH)
from mazkir import (
    process_user_input, # This is the function to be passed to the handler
    MemoryOperationError, 
    ToolExecutionError, 
    logger as mazkir_logger # Use Mazkir's configured logger
)

# Use Mazkir's logger
logger = mazkir_logger

class TelegramHandler(BaseHandler):
    """
    Telegram Bot handler for Mazkir.
    """

    def __init__(self, 
                 process_user_input_func: Callable[[str, str], str],
                 telegram_bot_token: str = None):
        super().__init__(process_user_input_func)
        
        self.bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.bot_token:
            logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set and not provided to constructor. TelegramHandler cannot start.")
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured.")

        self.application = ApplicationBuilder().token(self.bot_token).build()
        logger.info("Telegram Application built.")
        self.user_message_history: dict[str, list[str]] = {}


    def get_user_identifier(self, update: Update) -> str:
        """
        Extracts a unique user identifier from a Telegram Update object.
        The identifier is prefixed with "telegram_" to namespace it.
        """
        if not update or not update.effective_user or not update.effective_user.id:
            logger.error("Could not extract user ID from Telegram update.")
            # Return a default or raise an error, depending on desired handling
            return "telegram_unknown_user" 
        return f"telegram_{update.effective_user.id}"

    async def send_message(self, user_id_chat_id_tuple: Tuple[str, int], message: str) -> None:
        """
        Sends a message to the specified Telegram chat.

        Args:
            user_id_chat_id_tuple: A tuple containing (internal_user_id, chat_id).
                                   chat_id is used by Telegram to send the message.
            message: The text message to send.
        """
        internal_user_id, chat_id = user_id_chat_id_tuple
        try:
            await self.application.bot.send_message(chat_id=chat_id, text=message)
            logger.debug(f"Message sent to chat_id {chat_id} (internal user {internal_user_id})")
        except Exception as e:
            logger.error(f"Failed to send message to chat_id {chat_id} (internal user {internal_user_id}): {e}", exc_info=True)
            # Depending on the error, might try to inform the user via other means or re-raise.

    async def send_proactive_message(self, user_id: str, message: str) -> bool:
        """
        Sends a proactive message to the specified Telegram user.

        Args:
            user_id: The internal user identifier (e.g., "telegram_123456789").
            message: The message text to send.

        Returns:
            True if successful, False otherwise.
        """
        if not user_id.startswith("telegram_"):
            logger.error(f"send_proactive_message: Invalid user_id format for Telegram: {user_id}")
            return False

        try:
            chat_id_str = user_id.split("_", 1)[1]
            chat_id = int(chat_id_str)
            await self.application.bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"Proactive message sent to user_id {user_id} (chat_id {chat_id})")
            return True
        except ValueError:
            logger.error(f"send_proactive_message: Could not parse chat_id from user_id: {user_id}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"send_proactive_message: Failed to send message to user_id {user_id}: {e}", exc_info=True)
            return False

    async def _handle_telegram_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handles incoming text messages from Telegram users.
        This method is called by the Telegram library's dispatcher.
        """
        if not update or not update.message or not update.message.text:
            logger.debug("Received an update with no message text, ignoring.")
            return
        
        chat_id = update.effective_chat.id
        user_id_internal = self.get_user_identifier(update) # e.g., "telegram_12345"
        text = update.message.text

        logger.info(f"Received message from internal_user_id: {user_id_internal} (chat_id: {chat_id}, content snippet: '{text[:50]}...')")
        # Retrieve message history
        user_history = self.user_message_history.get(user_id_internal, [])
        user_history.append(text)
        # Keep only the last 10 messages
        self.user_message_history[user_id_internal] = user_history[-10:]
        logger.debug(f"Updated message history for {user_id_internal}. History length: {len(self.user_message_history[user_id_internal])}")


        assistant_response = "An error occurred while processing your request." # Default error
        try:
            # Call the core processing function (e.g., mazkir.process_user_input)
            # This function is expected to handle its own exceptions regarding memory/tool use
            # and return a string response.
            assistant_response = self.process_user_input_func(
                user_id_internal, 
                text, 
                message_history=self.user_message_history.get(user_id_internal, [])
            )
            logger.debug(f"Core processing for {user_id_internal} returned: '{assistant_response[:100]}...'")

        except MemoryOperationError as e_mem: # Should be caught by process_user_input, but as a fallback
            logger.error(f"MemoryOperationError during processing for {user_id_internal}: {e_mem}", exc_info=True)
            assistant_response = f"Error: A problem occurred with data storage: {e_mem}"
        except ToolExecutionError as e_tool: # Should be caught by process_user_input, but as a fallback
            logger.error(f"ToolExecutionError during processing for {user_id_internal}: {e_tool}", exc_info=True)
            assistant_response = f"Error: A problem occurred while performing an action: {e_tool}"
        except Exception as e_general: # Catch-all for unexpected errors in process_user_input_func
            logger.error(f"Unexpected error during processing for {user_id_internal}: {e_general}", exc_info=True)
            assistant_response = f"Error: An unexpected issue occurred: {e_general}"
        
        # Send the response back to the user
        try:
            await self.send_message((user_id_internal, chat_id), assistant_response)
        except Exception as e_send:
            # send_message already logs, but we can add context here if needed
            logger.error(f"Further error context: Failed to send assistant's response to {user_id_internal} (chat_id: {chat_id}). Original error in send_message was: {e_send}", exc_info=True)
            # No easy way to inform user if sending itself fails.

    def start(self) -> None:
        """
        Starts the Telegram bot: sets up handlers and begins polling.
        """
        # Ensure logging is configured. If this handler is run as the main script,
        # basicConfig might be needed here. If imported, the importing module should set up logging.
        # For robustness, we can ensure a basic config if no handlers are present.
        if not logging.getLogger().hasHandlers():
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            logger.info("Basic logging configured by TelegramHandler.start() as no handlers were found.")

        logger.info(f"TelegramHandler starting with token: {'******' if self.bot_token else 'NOT SET'}")

        # Create a message handler for text messages (excluding commands)
        # It calls self._handle_telegram_message for processing.
        message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_telegram_message)
        self.application.add_handler(message_handler)
        logger.info("Telegram message handler added.")

        logger.info("Bot is now starting to poll for messages...")
        try:
            self.application.run_polling()
        except Exception as e:
            logger.critical(f"FATAL: Error running Telegram application polling: {e}", exc_info=True)
            # Depending on the error, might need specific cleanup or restart logic.
        finally:
            logger.info("TelegramHandler polling has stopped.")
            # Any other shutdown tasks specific to the Telegram bot (not memory saving, as that's per-message)
            # e.g., await self.application.bot.close() if needed and if start() were async.

# Example of how it might be instantiated and run (this would typically be in a main script like mazkir.py)
if __name__ == '__main__':
    # This __main__ block is for testing TelegramHandler independently.
    # It requires TELEGRAM_BOT_TOKEN to be set in the environment.

    # Ensure mazkir.py is in PYTHONPATH or in the same directory for this to work.
    try:
        # process_user_input is already imported at the top from mazkir
        pass 
    except ImportError:
        logger.critical("Failed to import 'process_user_input' from mazkir.py for __main__ test. Ensure it is in PYTHONPATH.")
        # Define a mock for the handler to be instantiated if import fails
        def process_user_input(user_id: str, user_input_text: str) -> str: # type: ignore 
            logger.error("Using MOCK process_user_input due to import error from mazkir.py for TelegramHandler test")
            return "Error: Mazkir core function not loaded for Telegram."

    # Configure basic logging IF mazkir_logger wasn't successfully imported and configured
    if 'mazkir_logger' not in globals() or not mazkir_logger.handlers:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger.warning("Telegram Handler's __main__ using fallback basicConfig for logging.")
        
    logger.info("Starting Telegram Handler example (independent test mode from telegram_handler.py's __main__).")
    
    try:
        # Use the imported process_user_input from mazkir.py
        telegram_handler_instance = TelegramHandler(process_user_input_func=process_user_input)
        telegram_handler_instance.start()
    except ValueError as e: # Catch token configuration error from TelegramHandler init
        logger.critical(f"Failed to start TelegramHandler in test mode: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in TelegramHandler test mode: {e}", exc_info=True)
    
    logger.info("Telegram Handler example finished.")
