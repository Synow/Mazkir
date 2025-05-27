import json
import os
import time
from datetime import datetime, timedelta, time as dt_time
import threading
import logging
import asyncio

# Assuming mazkir.py is in the same directory or accessible in PYTHONPATH
# It's important that these imports work correctly for the scheduler to function with actual data.
# The dummy implementations are only for isolated testing if mazkir.py is not available.
try:
    from mazkir import load_memory, save_memory, MAZKIR_MEMORY_FILE, MemoryOperationError
except ImportError:
    scheduler_logger.critical("Failed to import from mazkir.py. Scheduler may not function correctly with user data.")
    MAZKIR_MEMORY_FILE = "mazkir_users_memory.json"  # Fallback path
    
    class MemoryOperationError(Exception): # pragma: no cover
        pass

    def load_memory(user_id, filepath=None): # pragma: no cover
        scheduler_logger.error(f"Using DUMMY load_memory for user {user_id} due to import error.")
        # Simulate loading structure for testing the scheduler's iteration logic
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f: # Added encoding
                    data = json.load(f)
                # For _load_all_users_data, we need to return the whole dict, not just one user's part
                # This dummy load_memory is not directly used by _load_all_users_data, which opens the file itself.
                # However, if save_memory uses it, this needs to be consistent.
                # The current _load_all_users_data in the class opens the file directly.
                # This dummy load_memory would be for other potential uses if mazkir.py is missing.
                return data.get(user_id, {"tasks": [], "preferences": {}}) 
            except Exception as e:
                scheduler_logger.error(f"DUMMY load_memory failed to read/parse {filepath}: {e}")
                pass # Fall through to returning empty
        return {"tasks": [], "preferences": {}} # Minimal structure
        
    def save_memory(user_id, user_data, filepath=None): # pragma: no cover
        scheduler_logger.error(f"Using DUMMY save_memory for user {user_id} due to import error.")
        # Simulate saving for testing
        if filepath:
            all_data = {}
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f: # Added encoding
                        all_data = json.load(f)
                except Exception: # More specific: json.JSONDecodeError, FileNotFoundError
                    pass # Ignore if file is corrupt or not json
            all_data[user_id] = user_data
            try:
                with open(filepath, 'w', encoding='utf-8') as f: # Added encoding
                    json.dump(all_data, f, indent=4)
            except Exception as e:
                scheduler_logger.error(f"DUMMY save_memory failed: {e}")
        pass

scheduler_logger = logging.getLogger(__name__)
# Basic configuration for the logger if it's not configured elsewhere
if not scheduler_logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class Scheduler:
    def __init__(self, bot_token=None, message_sender=None):
        """
        Initializes the Scheduler.

        Args:
            bot_token (str, optional): The bot token (e.g., for Telegram). Defaults to None.
            message_sender (callable, optional): A function or method to send messages. 
                                                 Example: telegram_handler.send_message. Defaults to None.
        """
        self.bot_token = bot_token
        self.message_sender = message_sender
        self.memory_file = MAZKIR_MEMORY_FILE
        self.stop_event = threading.Event()
        self.thread = None
        scheduler_logger.info("Scheduler initialized.")

    def _load_all_users_data(self):
        """
        Loads all users' data from the memory file.

        Returns:
            dict: A dictionary containing all users' data, or an empty dictionary if an error occurs.
        """
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                all_users_data = json.load(f)
            scheduler_logger.debug(f"Successfully loaded data for all users from {self.memory_file}")
            return all_users_data
        except FileNotFoundError:
            scheduler_logger.warning(f"Memory file {self.memory_file} not found. Returning empty data.")
            return {}
        except json.JSONDecodeError as e:
            scheduler_logger.error(f"Error decoding JSON from {self.memory_file}: {e}. Returning empty data.")
            return {}
        except Exception as e:
            scheduler_logger.error(f"Unexpected error loading all users data: {e}", exc_info=True)
            return {}

    def _check_and_send_reminders(self):
        """
        Checks and sends reminders for all users based on their tasks and preferences.
        This includes specific time reminders, daily interval reminders, and daily digests.
        """
        scheduler_logger.info("Scheduler: Checking for reminders...")
        all_users_data = self._load_all_users_data()
        
        if not all_users_data:
            scheduler_logger.info("Scheduler: No user data found or failed to load.")
            return

        now = datetime.now()
        today_date_iso = now.date().isoformat()
        # Define a fixed time for daily interval reminders (e.g., 09:00 AM)
        DAILY_REMINDER_FIXED_TIME = dt_time(9, 0, 0) 

        for user_id, user_data in all_users_data.items():
            scheduler_logger.debug(f"Processing reminders for user_id: {user_id}")
            tasks = user_data.get("tasks", [])
            preferences = user_data.get("preferences", {})
            user_modified_in_loop = False # Flag to track if user_data needs saving

            chat_id = None
            if user_id.startswith("telegram_"):
                try:
                    chat_id = user_id.split("_", 1)[1]
                    if not chat_id: # Ensure chat_id is not empty string
                        scheduler_logger.error(f"Empty chat_id parsed from user_id: {user_id}")
                        chat_id = None # Treat as invalid
                except IndexError:
                    scheduler_logger.error(f"Could not parse chat_id from user_id: {user_id}")
                # Continue processing user even if chat_id is None, as some logic might not need it,
                # or to handle non-Telegram users if logic is extended later.
            
            # Common check for message sending capability
            can_send_message = self.message_sender and chat_id

            # 1. Specific Time Reminders
            for task in tasks:
                if task.get("reminder_at"): # Check if not empty or None
                    try:
                        reminder_at_dt = datetime.fromisoformat(task["reminder_at"])
                        if now >= reminder_at_dt:
                            message = f"Reminder: Your task \"{task.get('description', 'N/A')}\" was due at {task['reminder_at']}."
                            scheduler_logger.info(f"Specific time reminder due for user {user_id}, task ID {task.get('id')}: {message}")
                            if can_send_message:
                                try:
                                    asyncio.run(self.message_sender.send_message((user_id, chat_id), message))
                                    scheduler_logger.info(f"Sent specific reminder to user {user_id} (chat_id: {chat_id}) for task {task.get('id')}")
                                except Exception as e:
                                    scheduler_logger.error(f"Error sending specific reminder to user {user_id} (chat_id: {chat_id}) for task {task.get('id')}: {e}", exc_info=True)
                            else:
                                scheduler_logger.warning(f"Cannot send specific reminder for task {task.get('id')} to user {user_id}: No message_sender or chat_id.")
                            
                            task["reminder_at"] = "" # Clear reminder
                            task["last_reminded_at"] = now.isoformat()
                            user_modified_in_loop = True
                    except ValueError as ve:
                        scheduler_logger.error(f"Invalid reminder_at format for task {task.get('id')} user {user_id}: '{task['reminder_at']}'. Error: {ve}")
                    except Exception as e: # Catch any other unexpected error during processing this task
                        scheduler_logger.error(f"Unexpected error processing specific reminder for task {task.get('id')} user {user_id}: {e}", exc_info=True)
            
            # 2. Interval Reminders ("daily") for pending tasks
            for task in tasks:
                if task.get("reminder_interval") == "daily" and task.get("status", "pending") == "pending":
                    last_reminded_at_dt = None
                    if task.get("last_reminded_at"):
                        try:
                            last_reminded_at_dt = datetime.fromisoformat(task["last_reminded_at"])
                        except ValueError:
                            scheduler_logger.warning(f"Invalid last_reminded_at format for task {task.get('id')} user {user_id}. Treating as never reminded for daily check.")

                    should_remind_daily = False
                    # Condition 1: Reminded before, but not today, and it's past the fixed reminder time.
                    if last_reminded_at_dt and last_reminded_at_dt.date() < now.date() and now.time() >= DAILY_REMINDER_FIXED_TIME:
                        should_remind_daily = True
                    # Condition 2: Never reminded before, and it's past the fixed reminder time.
                    # Also, ensure task wasn't just created today after the reminder time.
                    elif not last_reminded_at_dt and now.time() >= DAILY_REMINDER_FIXED_TIME:
                        created_at_dt = None
                        if task.get("created_at"):
                            try:
                                created_at_dt = datetime.fromisoformat(task.get("created_at"))
                                if created_at_dt.date() < now.date() or \
                                   (created_at_dt.date() == now.date() and created_at_dt.time() < DAILY_REMINDER_FIXED_TIME):
                                    should_remind_daily = True
                                else:
                                    scheduler_logger.debug(f"Daily reminder for new task {task.get('id')} user {user_id} not due yet (created after reminder time today).")
                            except ValueError: # Invalid created_at, assume eligible if time is past
                                scheduler_logger.warning(f"Invalid created_at format for task {task.get('id')} user {user_id}. Assuming eligible for daily reminder if time is past.")
                                should_remind_daily = True
                        else: # No created_at, assume eligible if time is past
                             should_remind_daily = True

                    if should_remind_daily:
                        message = f"Daily Reminder: You have a pending task \"{task.get('description', 'N/A')}\"."
                        scheduler_logger.info(f"Daily interval reminder due for user {user_id}, task ID {task.get('id')}: {message}")
                        if can_send_message:
                            try:
                                asyncio.run(self.message_sender.send_message((user_id, chat_id), message))
                                scheduler_logger.info(f"Sent daily interval reminder to user {user_id} (chat_id: {chat_id}) for task {task.get('id')}")
                            except Exception as e:
                                scheduler_logger.error(f"Error sending daily interval reminder to user {user_id} (chat_id: {chat_id}) for task {task.get('id')}: {e}", exc_info=True)
                        else:
                            scheduler_logger.warning(f"Cannot send daily interval reminder for task {task.get('id')} to user {user_id}: No message_sender or chat_id.")

                        task["last_reminded_at"] = now.isoformat()
                        user_modified_in_loop = True
                    elif last_reminded_at_dt and last_reminded_at_dt.date() == now.date():
                        scheduler_logger.debug(f"Daily reminder for task {task.get('id')} user {user_id} already processed/sent today.")

            # 3. General Daily Digest
            daily_reminder_pref_time_str = preferences.get("daily_reminder_time") # e.g., "09:00"
            last_daily_digest_sent_date_str = preferences.get("last_daily_digest_sent_date")

            if daily_reminder_pref_time_str: # Only process if user has this preference
                try:
                    pref_time = datetime.strptime(daily_reminder_pref_time_str, "%H:%M").time()
                    
                    if now.time() >= pref_time and last_daily_digest_sent_date_str != today_date_iso:
                        pending_tasks_for_digest = [t for t in tasks if t.get("status", "pending") == "pending"]
                        
                        if pending_tasks_for_digest:
                            digest_message_intro = f"Good {('morning' if now.hour < 12 else 'afternoon' if now.hour < 18 else 'evening')}! "
                            digest_message_intro += "Here's your daily digest of pending tasks:\n"
                            tasks_summary_lines = []
                            for i, task_item in enumerate(pending_tasks_for_digest):
                                tasks_summary_lines.append(f"{i+1}. {task_item.get('description', 'N/A')}")
                                if len(tasks_summary_lines) >= 10 : # Limit number of tasks in digest
                                    tasks_summary_lines.append("...and more.")
                                    break
                            
                            digest_message = digest_message_intro + "\n".join(tasks_summary_lines)
                            scheduler_logger.info(f"Daily digest due for user {user_id}: {len(pending_tasks_for_digest)} pending tasks.")

                            if can_send_message:
                                try:
                                    asyncio.run(self.message_sender.send_message((user_id, chat_id), digest_message))
                                    scheduler_logger.info(f"Sent daily digest to user {user_id} (chat_id: {chat_id})")
                                except Exception as e:
                                    scheduler_logger.error(f"Error sending daily digest to user {user_id} (chat_id: {chat_id}): {e}", exc_info=True)
                            else:
                                scheduler_logger.warning(f"Cannot send daily digest to user {user_id}: No message_sender or chat_id.")
                            
                            preferences["last_daily_digest_sent_date"] = today_date_iso
                            user_modified_in_loop = True
                        else:
                            scheduler_logger.info(f"Daily digest due for user {user_id}, but no pending tasks. Marking as 'sent'.")
                            preferences["last_daily_digest_sent_date"] = today_date_iso 
                            user_modified_in_loop = True 
                    elif last_daily_digest_sent_date_str == today_date_iso:
                         scheduler_logger.debug(f"Daily digest for user {user_id} already sent today or preference time not yet reached ({now.time()} vs {pref_time}).")

                except ValueError as ve: # For strptime
                    scheduler_logger.error(f"Invalid daily_reminder_time format for user {user_id}: '{daily_reminder_pref_time_str}'. Error: {ve}")
                except Exception as e: # Catch any other unexpected error during digest processing
                    scheduler_logger.error(f"Unexpected error processing daily digest for user {user_id}: {e}", exc_info=True)

            if user_modified_in_loop:
                try:
                    # Ensure preferences dictionary exists in user_data if it was modified
                    if "preferences" not in user_data and "last_daily_digest_sent_date" in preferences:
                        user_data["preferences"] = preferences
                    save_memory(user_id, user_data, self.memory_file)
                    scheduler_logger.info(f"User data saved for {user_id} after reminder processing.")
                except MemoryOperationError as moe: # Catch specific error from mazkir's save_memory
                    scheduler_logger.error(f"MemoryOperationError saving data for user {user_id}: {moe}", exc_info=True)
                except Exception as e: 
                    scheduler_logger.error(f"Unexpected error saving memory for user {user_id} after processing reminders: {e}", exc_info=True)

    def run(self):
        """
        The main loop for the scheduler.
        Continuously checks for reminders until the stop_event is set.
        """
        scheduler_logger.info("Scheduler run loop started.")
        while not self.stop_event.is_set():
            self._check_and_send_reminders()
            # Wait for 60 seconds, or until stop_event is set
            # This makes the loop interruptible
            interrupted = self.stop_event.wait(60) 
            if interrupted:
                scheduler_logger.info("Scheduler run loop interrupted by stop_event.")
                break 
        scheduler_logger.info("Scheduler run loop stopped.")

    def start(self):
        """
        Starts the scheduler in a new daemon thread.
        """
        if self.thread is not None and self.thread.is_alive():
            scheduler_logger.warning("Scheduler thread is already running.")
            return

        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.setName("SchedulerThread") # Set a name for easier identification
        try:
            self.thread.start()
            scheduler_logger.info("Scheduler thread started successfully.")
        except Exception as e:
            scheduler_logger.error(f"Failed to start scheduler thread: {e}", exc_info=True)


    def stop(self):
        """
        Stops the scheduler thread gracefully.
        """
        scheduler_logger.info("Attempting to stop scheduler thread...")
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            scheduler_logger.info("Waiting for scheduler thread to join...")
            self.thread.join(timeout=10) # Add a timeout for join
            if self.thread.is_alive():
                scheduler_logger.warning("Scheduler thread did not join in time.")
            else:
                scheduler_logger.info("Scheduler thread joined successfully.")
        else:
            scheduler_logger.info("Scheduler thread was not running or already stopped.")
        self.thread = None # Clear the thread object


if __name__ == "__main__": # pragma: no cover
    # This is a simple test block to run the scheduler standalone for demonstration
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s')
    scheduler_logger.info("Starting scheduler standalone test...")

    # Create a dummy memory file for testing _load_all_users_data
    # More comprehensive dummy data for testing
    now_for_test = datetime.now()
    dummy_memory_content = {
        "telegram_user_123": { # User with telegram_ prefix for chat_id extraction
            "tasks": [
                {"id": 1, "description": "Specific time task (due now)", "status": "pending", "reminder_at": (now_for_test - timedelta(seconds=10)).isoformat(), "created_at": (now_for_test - timedelta(days=1)).isoformat(), "last_reminded_at": "", "reminder_interval": ""},
                {"id": 2, "description": "Specific time task (future)", "status": "pending", "reminder_at": (now_for_test + timedelta(days=1)).isoformat(), "created_at": (now_for_test - timedelta(days=1)).isoformat(), "last_reminded_at": "", "reminder_interval": ""},
                {"id": 3, "description": "Daily interval task (due today)", "status": "pending", "reminder_at": "", "created_at": (now_for_test - timedelta(days=2)).isoformat(), "last_reminded_at": (now_for_test - timedelta(days=1)).isoformat(), "reminder_interval": "daily"}, # last_reminded yesterday
                {"id": 4, "description": "Daily interval task (already reminded today)", "status": "pending", "reminder_at": "", "created_at": (now_for_test - timedelta(days=2)).isoformat(), "last_reminded_at": (now_for_test - timedelta(hours=1)).isoformat(), "reminder_interval": "daily"}, # last_reminded today
                {"id": 5, "description": "Pending task for digest 1", "status": "pending", "created_at": (now_for_test - timedelta(days=1)).isoformat()},
            ],
            "next_task_id": 6,
            "preferences": {
                "tone": "neutral", 
                "daily_reminder_time": (now_for_test - timedelta(minutes=1)).strftime("%H:%M"), # Digest time just passed
                "last_daily_digest_sent_date": (now_for_test - timedelta(days=1)).date().isoformat() # Digest sent yesterday
            }
        },
        "telegram_user_456": { # Another telegram user
            "tasks": [
                {"id": 1, "description": "Pending task for digest 2", "status": "pending", "created_at": (now_for_test - timedelta(hours=2)).isoformat()}
            ],
            "next_task_id": 2,
            "preferences": {
                "tone": "friendly", 
                "daily_reminder_time": "23:59", # Digest time far in future
                "last_daily_digest_sent_date": now_for_test.date().isoformat() # Digest already sent today
            }
        },
        "user_789_no_telegram": { # User without telegram_ prefix
             "tasks": [{"id": 1, "description": "Task for non-telegram user (due)", "status": "pending", "reminder_at": (now_for_test - timedelta(hours=1)).isoformat(), "created_at": (now_for_test - timedelta(days=1)).isoformat()}],
             "next_task_id": 2,
             "preferences": {}
        }
    }
    try:
        with open(MAZKIR_MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(dummy_memory_content, f, indent=4)
        scheduler_logger.info(f"Dummy memory file created at {MAZKIR_MEMORY_FILE}")
    except Exception as e:
        scheduler_logger.error(f"Could not create dummy memory file: {e}")

    # Dummy message sender (object with an async method) for testing
    class DummyMessageSender:
        async def send_message(self, user_chat_id_tuple, message):
            user_id, chat_id = user_chat_id_tuple
            scheduler_logger.info(f"DUMMY_SENDER: To user_id='{user_id}', chat_id='{chat_id}': \"{message}\"")
            # Simulate network delay or async operation
            await asyncio.sleep(0.01) # Very short sleep

    scheduler = Scheduler(bot_token="dummy_token", message_sender=DummyMessageSender())
    
    scheduler_logger.info("Starting scheduler for a short test run (approx 10 seconds)...")
    scheduler.start()

    # Let the scheduler run for a short period.
    # The internal loop of scheduler.run() waits for 60 seconds.
    # To test effectively without waiting that long, we'd ideally make that wait configurable.
    # For now, we'll run it for a short time, expecting it to do one pass of _check_and_send_reminders.
    # Then we stop it.
    
    # Wait for a brief moment to allow the first check to run if the timing is right,
    # or for a longer time if we expect the 60s loop to cycle.
    # For a quick test of one cycle, if the 60s wait is problematic, one might temporarily
    # reduce it in the run() method for testing purposes.
    # Assuming the first check runs almost immediately after start:
    time.sleep(10) # Allow some time for the first _check_and_send_reminders to complete

    scheduler_logger.info("Test duration over. Signaling scheduler to stop...")
    scheduler.stop()
    
    scheduler_logger.info("Waiting for scheduler thread to clean up completely...")
    if scheduler.thread is not None and scheduler.thread.is_alive():
        scheduler.thread.join(timeout=15) # Wait a bit longer for thread to join
        if scheduler.thread.is_alive():
            scheduler_logger.warning("Scheduler thread did not join cleanly after stop signal.")
    
    scheduler_logger.info("Scheduler standalone test finished.")
    
    # Clean up dummy memory file (optional, good for repeated tests)
    try:
        if os.path.exists(MAZKIR_MEMORY_FILE):
            # os.remove(MAZKIR_MEMORY_FILE)
            scheduler_logger.info(f"Dummy memory file {MAZKIR_MEMORY_FILE} NOT removed for inspection.")
    except Exception as e:
        scheduler_logger.error(f"Could not remove dummy memory file: {e}")

# Example of how this scheduler might be integrated (remains for context)
#
# from telegram_handler import TelegramHandler # Assuming you have this
#
# if __name__ == "__main__":
#     # Initialize logging, configurations, etc.
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     
#     # Setup Telegram Handler (or other message sender)
#     # This is a simplified example; actual handler setup might be more complex
#     # bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
#     # if not bot_token:
#     #     logger.critical("TELEGRAM_BOT_TOKEN not set. Exiting.")
#     #     exit()
#     #
#     # def process_input_function_placeholder(user_id, text, history):
#     #     return "Placeholder response" # Replace with actual mazkir.process_user_input
#     #
#     # telegram_handler = TelegramHandler(process_user_input_func=process_input_function_placeholder)
#
#     # Initialize and start the Scheduler
#     # scheduler = Scheduler(bot_token=bot_token, message_sender=telegram_handler.send_message_to_user) # Pass appropriate sender method
#     # scheduler.start()
#
#     # Start the Telegram bot polling (or webhook)
#     # telegram_handler.start() # This would typically block, or you'd run it in its own thread
#
#     # Keep the main application running
#     # try:
#     #     while True:
#     #         time.sleep(1) # Keep main thread alive
#     # except KeyboardInterrupt:
#     #     logger.info("Application shutting down...")
#     # finally:
#     #     scheduler.stop()
#     #     # Any other cleanup
#     #     logger.info("Application stopped.")
