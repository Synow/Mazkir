import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Attempt to import from mazkir_refined. If not found, this bot won't work.
try:
    from mazkir_refined import (
        load_memory,
        save_memory,
        process_user_input,
        MemoryOperationError,
        ToolExecutionError,
        logger as mazkir_logger # Use Mazkir's logger if available
    )
except ImportError as e:
    # If mazkir_refined is not found, we need to set up a placeholder logger
    # and the bot will not be fully functional.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    mazkir_logger = logging.getLogger(__name__)
    mazkir_logger.critical(f"CRITICAL: Failed to import 'mazkir_refined'. Ensure it's in PYTHONPATH. Error: {e}")
    # Define dummy functions/exceptions if mazkir_refined is not available, so the bot can start
    # but will warn about missing core functionality.
    def load_memory(filepath=None): raise MemoryOperationError("Dummy load_memory: mazkir_refined not found")
    def save_memory(data, filepath=None): raise MemoryOperationError("Dummy save_memory: mazkir_refined not found")
    def process_user_input(text, memory_data): return "Error: Mazkir core logic not available."
    class MemoryOperationError(Exception): pass
    class ToolExecutionError(Exception): pass


# --- Global In-Memory Store for Mazkir Data ---
# This will hold the data loaded from Mazkir's memory file.
# It's crucial that this is updated correctly and saved after modifications.
MEMORY_DATA = None

# --- Configuration (from Environment Variables) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_TELEGRAM_USER_ID_STR = os.getenv("AUTHORIZED_TELEGRAM_USER_ID")
AUTHORIZED_TELEGRAM_USER_ID = None

# Use Mazkir's logger if imported, otherwise use the local one.
logger = mazkir_logger if 'mazkir_logger' in globals() else logging.getLogger(__name__)
if 'mazkir_logger' not in globals(): # If we are using the local fallback logger
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# --- Telegram Bot Message Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming text messages from users."""
    global MEMORY_DATA # Ensure we are using the global memory store

    user_id = update.effective_user.id
    text = update.message.text

    logger.info(f"Received message from user_id: {user_id} (Content length: {len(text)})")

    # --- Authorization Check ---
    if AUTHORIZED_TELEGRAM_USER_ID is None:
        logger.error("AUTHORIZED_TELEGRAM_USER_ID is not configured. Cannot process messages.")
        await update.message.reply_text("Bot configuration error. Please contact the administrator.")
        return
        
    if user_id != AUTHORIZED_TELEGRAM_USER_ID:
        logger.warning(f"Unauthorized access attempt by user_id: {user_id}")
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    if MEMORY_DATA is None:
        logger.error("Memory not loaded. Cannot process user input.")
        await update.message.reply_text("Error: Mazkir memory is not loaded. Please contact the administrator.")
        return

    logger.info(f"Authorized user {user_id} sent command: {text[:50]}...") # Log a snippet

    response_text = "An unexpected error occurred." # Default error message
    try:
        # --- Processing User Input ---
        # process_user_input is expected to interact with MEMORY_DATA and potentially modify it
        # (e.g., if it calls perform_file_action which then calls add_task).
        assistant_response = process_user_input(text, MEMORY_DATA)
        logger.debug(f"Mazkir process_user_input response: {assistant_response}")
        
        # --- CRUCIAL: Save Memory After Processing ---
        # Any modifications made to MEMORY_DATA by process_user_input (via its tools)
        # need to be persisted back to the file.
        try:
            save_memory(MEMORY_DATA)
            logger.info(f"Memory saved successfully after processing input for user {user_id}.")
        except MemoryOperationError as e_save:
            logger.error(f"CRITICAL: Failed to save memory after processing for user {user_id}: {e_save}", exc_info=True)
            # Decide if we should inform the user. This is a critical backend error.
            # For a PoC, we might send a generic error, but in production, this needs careful handling.
            await update.message.reply_text("Error: Could not save task data. Please try again or contact support.")
            return # Exit if we can't save, to prevent further data inconsistency

        response_text = assistant_response

    except MemoryOperationError as e_mem: # Errors from process_user_input related to memory (e.g. if a tool tries to load/save)
        logger.error(f"MemoryOperationError during user input processing: {e_mem}", exc_info=True)
        response_text = f"Error: A problem occurred with memory storage: {e_mem}"
    except ToolExecutionError as e_tool: # Errors from tools called by process_user_input
        logger.error(f"ToolExecutionError during user input processing: {e_tool}", exc_info=True)
        response_text = f"Error: A problem occurred while performing an action: {e_tool}"
    except Exception as e_general: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error during user input processing: {e_general}", exc_info=True)
        response_text = f"Error: An unexpected issue occurred: {e_general}"
    
    # --- Reply to User ---
    try:
        await update.message.reply_text(response_text)
    except Exception as e_reply:
        logger.error(f"Failed to send reply to user {user_id}: {e_reply}", exc_info=True)


# --- Main Bot Application Setup ---
def main():
    """Starts the Telegram bot and initializes Mazkir memory."""
    global MEMORY_DATA
    global AUTHORIZED_TELEGRAM_USER_ID

    logger.info("Starting Mazkir Telegram Bot...")

    # --- Configuration Validation ---
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        return
    if not AUTHORIZED_TELEGRAM_USER_ID_STR:
        logger.critical("FATAL: AUTHORIZED_TELEGRAM_USER_ID environment variable not set. Exiting.")
        return
    
    try:
        AUTHORIZED_TELEGRAM_USER_ID = int(AUTHORIZED_TELEGRAM_USER_ID_STR)
    except ValueError:
        logger.critical(f"FATAL: AUTHORIZED_TELEGRAM_USER_ID ('{AUTHORIZED_TELEGRAM_USER_ID_STR}') is not a valid integer. Exiting.")
        return

    logger.info(f"Authorized User ID set to: {AUTHORIZED_TELEGRAM_USER_ID}")
    logger.info(f"Mazkir memory file used: {os.getenv('MAZKIR_MEMORY_FILE', 'mazkir_memory.json')}") # Log which memory file is used
    logger.info(f"Mazkir LLM model used: {os.getenv('MAZKIR_LLM_MODEL', 'gpt-3.5-turbo')}") # Log which model is used by core

    # --- Initial Memory Load ---
    logger.info("Attempting to load initial Mazkir memory...")
    try:
        MEMORY_DATA = load_memory()
        if MEMORY_DATA is None: # Should not happen if load_memory returns default on error, but defensive check.
             logger.critical("FATAL: load_memory returned None. This should not happen. Exiting.")
             return
        logger.info("Mazkir memory loaded successfully at startup.")
    except MemoryOperationError as e:
        logger.critical(f"FATAL: Failed to load initial Mazkir memory: {e}. Bot cannot start.", exc_info=True)
        # In a real deployment, you might have a fallback or alert mechanism here.
        return # Exit if memory can't be loaded
    except Exception as e_load_general: # Catch any other unexpected error during load
        logger.critical(f"FATAL: An unexpected error occurred during initial memory load: {e_load_general}. Bot cannot start.", exc_info=True)
        return


    # --- Telegram Application Setup ---
    try:
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

        # Handler for text messages (excluding commands)
        message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        application.add_handler(message_handler)

        logger.info("Telegram bot application built and message handler added.")
        logger.info("Bot is now polling for messages...")

        # Start the Bot
        application.run_polling()

    except Exception as e_app:
        logger.critical(f"FATAL: Error setting up or running Telegram application: {e_app}", exc_info=True)
    finally:
        # --- Graceful Shutdown ---
        logger.info("Mazkir Telegram Bot is shutting down...")
        if MEMORY_DATA is not None:
            try:
                logger.info("Attempting to save Mazkir memory on shutdown...")
                save_memory(MEMORY_DATA)
                logger.info("Mazkir memory saved successfully on shutdown.")
            except MemoryOperationError as e_shutdown_save:
                logger.error(f"Error saving Mazkir memory during shutdown: {e_shutdown_save}", exc_info=True)
            except Exception as e_shutdown_general:
                 logger.error(f"An unexpected error occurred during shutdown memory save: {e_shutdown_general}", exc_info=True)
        else:
            logger.warning("No memory data was loaded; skipping save on shutdown.")
        logger.info("Shutdown complete.")


if __name__ == '__main__':
    # This check is important if, for example, mazkir_refined.py itself tried to import this file.
    # For this setup, it's mainly good practice.
    if 'mazkir_logger' not in globals() or mazkir_logger.name == __name__:
        # If mazkir_refined was not imported, or if the logger is the root logger (fallback)
        # re-initialize basicConfig for this script's context if it hasn't been properly set.
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger.info("Initialized logging for standalone bot execution (or if mazkir_refined import failed).")

    main()
