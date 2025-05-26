import json
import os
import litellm
import logging
from datetime import datetime

from dotenv import load_dotenv
from openinference.instrumentation.litellm import LiteLLMInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

load_dotenv()

# Configure OpenTelemetry for Arize Phoenix
# Ensure your Phoenix instance is running and accessible at the specified endpoint.
# For local Docker setup, endpoint is typically http://localhost:4317 or http://0.0.0.0:4317
phoenix_tracer_provider = trace.get_tracer_provider()
if not isinstance(phoenix_tracer_provider, TracerProvider): # Check if a provider is already configured
    phoenix_tracer_provider = TracerProvider()
    trace.set_tracer_provider(phoenix_tracer_provider)
else:
    print("TracerProvider already configured.") # Or log this

# Configure the OTLP exporter
# Make sure your Phoenix collector is running at http://0.0.0.0:4317 (or your actual endpoint)
otlp_exporter = OTLPSpanExporter(
    endpoint="http://0.0.0.0:4317",  # Default for local Phoenix. Adjust if necessary.
    insecure=True  # Use insecure=True for HTTP. For HTTPS, set to False and configure certs.
)

# Add the OTLP exporter to the tracer provider
phoenix_tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Instrument LiteLLM
LiteLLMInstrumentor().instrument(tracer_provider=phoenix_tracer_provider)

print("Arize Phoenix LiteLLM Instrumentor configured.") # Add a print statement to confirm execution

# --- Configuration ---
# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # Outputs to console
        # logging.FileHandler("mazkir.log") # Optionally log to a file
    ]
)
logger = logging.getLogger(__name__)

# Environment variable configuration
MAZKIR_MEMORY_FILE = os.getenv("MAZKIR_MEMORY_FILE", "mazkir_users_memory.json") # Updated for multi-user
MAZKIR_LLM_MODEL = os.getenv("MAZKIR_LLM_MODEL", "vertex_ai/gemini-2.5-flash-preview-04-17")
os.environ["LITELLM_LOG"] = "INFO"



# --- Custom Exceptions ---
class MemoryOperationError(Exception):
    """Custom exception for memory load/save errors."""
    pass

class ToolExecutionError(Exception):
    """Custom exception for errors during tool execution."""
    pass

# --- Memory Functions ---
def _get_default_user_data():
    """Returns the default data structure for a new user."""
    return {
        "tasks": [],
        "archived_tasks": [],
        "next_task_id": 1,
        "preferences": {"tone": "neutral"}
    }

def load_memory(user_id: str, filepath=None):
    """Loads a specific user's data from the JSON memory file."""
    file_to_load = filepath or MAZKIR_MEMORY_FILE
    logger.debug(f"Attempting to load memory for user '{user_id}' from {file_to_load}")
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            all_users_data = json.load(f)
        
        if user_id in all_users_data:
            logger.info(f"Memory for user '{user_id}' loaded successfully from {file_to_load}")
            user_data = all_users_data[user_id]
            # Validate structure for the specific user
            if not isinstance(user_data.get("tasks"), list):
                logger.warning(f"'tasks' key missing or not a list for user '{user_id}'. Initializing with empty list.")
                user_data["tasks"] = []
            if not isinstance(user_data.get("next_task_id"), int):
                logger.warning(f"'next_task_id' key missing or not an int for user '{user_id}'. Initializing to 1.")
                user_data["next_task_id"] = 1
            if not isinstance(user_data.get("preferences"), dict):
                logger.warning(f"'preferences' key missing or not a dict for user '{user_id}'. Initializing with default.")
                user_data["preferences"] = {"tone": "neutral"}
            
            # Ensure new fields exist for existing users
            user_data.setdefault("archived_tasks", [])
            for task_list_key in ["tasks", "archived_tasks"]:
                if task_list_key in user_data:
                    for task in user_data[task_list_key]:
                        task.setdefault("reminder_settings", {})
                        task.setdefault("status_history", [])
            return user_data
        else:
            logger.warning(f"User '{user_id}' not found in {file_to_load}. Returning default new user structure.")
            return _get_default_user_data()
            
    except FileNotFoundError:
        logger.warning(f"Memory file {file_to_load} not found. Returning default new user structure for user '{user_id}'.")
        return _get_default_user_data()
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {file_to_load}: {e}. Returning default new user structure for user '{user_id}'.")
        return _get_default_user_data() # Or raise MemoryOperationError
    except Exception as e:
        logger.error(f"Unexpected error loading memory for user '{user_id}' from {file_to_load}: {e}", exc_info=True)
        raise MemoryOperationError(f"Failed to load memory for user '{user_id}' due to unexpected error: {e}")


def save_memory(user_id: str, user_data: dict, filepath=None):
    """Saves a specific user's data to the JSON memory file."""
    file_to_save = filepath or MAZKIR_MEMORY_FILE
    logger.debug(f"Attempting to save memory for user '{user_id}' to {file_to_save}")
    
    all_users_data = {}
    try:
        # Try to load existing data first
        with open(file_to_save, 'r', encoding='utf-8') as f:
            all_users_data = json.load(f)
    except FileNotFoundError:
        logger.info(f"Memory file {file_to_save} not found. Will create a new one.")
    except json.JSONDecodeError as e:
        logger.warning(f"Error decoding JSON from {file_to_save}: {e}. Will overwrite with new data structure if possible.")
        # Depending on desired robustness, could raise MemoryOperationError or backup the corrupt file.
        # For now, we'll proceed to overwrite with a structure containing the current user's data.
        all_users_data = {} # Reset to empty if corrupt, to avoid propagating corruption.

    # Update the specific user's data
    all_users_data[user_id] = user_data
    
    try:
        with open(file_to_save, 'w', encoding='utf-8') as f:
            json.dump(all_users_data, f, indent=4)
        logger.info(f"Memory for user '{user_id}' saved successfully to {file_to_save}")
    except IOError as e:
        logger.error(f"IOError saving memory for user '{user_id}' to {file_to_save}: {e}", exc_info=True)
        raise MemoryOperationError(f"IOError saving memory for user '{user_id}': {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving memory for user '{user_id}' to {file_to_save}: {e}", exc_info=True)
        raise MemoryOperationError(f"Failed to save memory for user '{user_id}' due to unexpected error: {e}")

# --- Tool/Action Functions ---
# The tool functions (get_tasks, add_task, update_task_status) now operate on user_data (user-specific data).
# The calling function (perform_file_action) is responsible for ensuring that user_data is loaded
# for the correct user and that any modifications are saved back using save_memory with the user_id.

def get_tasks(user_data, params=None):
    """Tool to get all tasks for the current user."""
    logger.info(f"Executing tool: get_tasks with params: {params} for user")
    return user_data.get("tasks", [])

def add_task(user_data, params=None, user_id_for_save=None): # Add user_id_for_save for explicit save
    """Tool to add a new task for the current user."""
    logger.info(f"Executing tool: add_task with params: {params} for user")
    if not params or "description" not in params:
        logger.error("add_task failed: 'description' missing in params.")
        raise ToolExecutionError("Task description is required for add_task.")
    
    task_id = user_data.get("next_task_id", 1)
    current_time = datetime.now().isoformat()
    initial_status = "pending"
    new_task = {
        "id": task_id,
        "description": params["description"],
        "status": initial_status,
        "created_at": current_time,
        "reminder_settings": {},
        "status_history": [{"status": initial_status, "timestamp": current_time}]
    }
    if "due_date" in params:
        new_task["due_date"] = params["due_date"]
        
    user_data["tasks"].append(new_task)
    user_data["next_task_id"] = task_id + 1
    
    if user_id_for_save: # If user_id is provided, save the memory
        save_memory(user_id_for_save, user_data)
        logger.info(f"Task {task_id} added for user {user_id_for_save}: {params['description']}")
    else:
        # This case should be handled by the calling function, which should explicitly save.
        logger.warning(f"Task {task_id} added to user_data in memory, but not saved to file as user_id_for_save was not provided.")

    return new_task

def update_task_status(user_data, params=None, user_id_for_save=None): # Add user_id_for_save
    """Tool to update a task's status for the current user."""
    logger.info(f"Executing tool: update_task_status with params: {params} for user")
    if not params or "task_id" not in params or "status" not in params:
        logger.error("update_task_status failed: 'task_id' or 'status' missing in params.")
        raise ToolExecutionError("task_id and status are required for update_task_status.")
    
    try:
        task_id_to_update = int(params["task_id"])
    except ValueError:
        logger.error(f"update_task_status failed: invalid task_id format '{params['task_id']}'. Must be an integer.")
        raise ToolExecutionError(f"Invalid task_id format: '{params['task_id']}'. Must be an integer.")

    new_status = params["status"]
    task_found = False
    updated_task_details = None
    task_index = -1

    for i, task in enumerate(user_data["tasks"]):
        if task["id"] == task_id_to_update:
            task_index = i
            break
            
    if task_index != -1:
        task = user_data["tasks"][task_index]
        task["status"] = new_status
        task["updated_at"] = datetime.now().isoformat()
        task.setdefault("status_history", [])
        task["status_history"].append({"status": new_status, "timestamp": task["updated_at"]})
        updated_task_details = task.copy() # Keep a copy before it's moved

        if new_status in ["completed", "discarded"]:
            logger.info(f"Task {task_id_to_update} status changing to '{new_status}'. Archiving task.")
            archived_task = user_data["tasks"].pop(task_index)
            user_data.setdefault("archived_tasks", []) # Ensure archived_tasks list exists
            user_data["archived_tasks"].insert(0, archived_task) # Add to the beginning

            # Enforce 100-item limit on archived_tasks
            if len(user_data["archived_tasks"]) > 100:
                user_data["archived_tasks"] = user_data["archived_tasks"][:100]
            task_found = True # Task was found and processed
        else:
            # For other statuses, task remains in the main "tasks" list
            task_found = True

        if user_id_for_save:
            save_memory(user_id_for_save, user_data)
            logger.info(f"Task {task_id_to_update} status updated to {new_status} for user {user_id_for_save}. Memory saved.")
        else:
            logger.warning(f"Task {task_id_to_update} status updated in user_data, but not saved to file as user_id_for_save was not provided.")
        return updated_task_details # Return the (potentially archived) task's details
    else:
        logger.warning(f"update_task_status: Task with id {task_id_to_update} not found in active tasks for user.")
        return {"error": f"Task with id {task_id_to_update} not found in active tasks."}

def discard_task(user_data, params=None, user_id_for_save=None):
    """Tool to discard a task and move it to archives for the current user."""
    logger.info(f"Executing tool: discard_task with params: {params} for user")
    if not params or "task_id" not in params:
        logger.error("discard_task failed: 'task_id' missing in params.")
        raise ToolExecutionError("task_id is required for discard_task.")

    # Reuse update_task_status logic by setting the status to "discarded"
    update_params = {"task_id": params["task_id"], "status": "discarded"}
    return update_task_status(user_data, update_params, user_id_for_save)

# --- Reminder Checking Logic ---
def check_due_reminders(user_data):
    """
    Checks all pending tasks for a user and returns messages for any due reminders.
    Modifies task's reminder_settings in-place if a reminder is triggered (e.g., updates last_reminded_at).
    The caller is responsible for saving the user_data.
    """
    due_reminders_messages = []
    # TIMEZONE_NOTE: All datetime operations currently assume server's local timezone or naive datetimes.
    # For robust applications, ensure consistent timezone handling (e.g., by using UTC for all internal storage and processing).
    # datetime.now(timezone.utc) would be a way to get timezone-aware current time in UTC.
    # datetime.fromisoformat() can parse ISO strings with timezone offsets.
    current_time = datetime.now() 
    today_date_iso = current_time.date().isoformat()

    for task in user_data.get("tasks", []):
        if task.get("status") == "pending" and task.get("reminder_settings"):
            reminder_settings = task["reminder_settings"]
            reminder_type = reminder_settings.get("type")
            task_description = task.get("description", "N/A")
            task_id = task.get("id")

            try:
                if reminder_type == "specific_time":
                    if not reminder_settings.get("specific_time_triggered", False):
                        reminder_time_str = reminder_settings.get("time")
                        if reminder_time_str:
                            # TIMEZONE_NOTE: Parsing ISO string. If it includes offset, datetime_obj will be offset-aware.
                            # If no offset, it's naive. Comparison with current_time (naive) should be consistent.
                            reminder_time_obj = datetime.fromisoformat(reminder_time_str)
                            # If reminder_time_obj is offset-aware, make current_time offset-aware for comparison or vice-versa.
                            # For simplicity, if reminder_time_obj has tzinfo, we'll convert current_time to that timezone.
                            # This is a basic approach; a more robust solution uses UTC everywhere.
                            if reminder_time_obj.tzinfo:
                                current_time_for_comparison = current_time.astimezone(reminder_time_obj.tzinfo)
                            else:
                                # If reminder_time_obj is naive, current_time is also naive.
                                current_time_for_comparison = current_time

                            if current_time_for_comparison >= reminder_time_obj:
                                due_reminders_messages.append(
                                    f"REMINDER (Task ID: {task_id}): Task '{task_description}' was due at {reminder_time_str}."
                                )
                                reminder_settings["specific_time_triggered"] = True
                                task["updated_at"] = current_time.isoformat() # Mark task as updated

                elif reminder_type == "daily":
                    time_of_day_str = reminder_settings.get("time_of_day") # "HH:MM"
                    last_reminded_daily_iso = reminder_settings.get("last_reminded_daily_at")

                    if time_of_day_str:
                        # Create a datetime object for today at the specified time_of_day
                        hour, minute = map(int, time_of_day_str.split(':'))
                        # TIMEZONE_NOTE: current_time.replace makes a naive datetime if current_time is naive.
                        reminder_time_today = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)

                        if current_time >= reminder_time_today and last_reminded_daily_iso != today_date_iso:
                            due_reminders_messages.append(
                                f"REMINDER (Task ID: {task_id}): Daily reminder for task '{task_description}' at {time_of_day_str}."
                            )
                            reminder_settings["last_reminded_daily_at"] = today_date_iso
                            task["updated_at"] = current_time.isoformat()

                elif reminder_type == "interval":
                    interval_hours = reminder_settings.get("hours")
                    last_reminded_at_str = reminder_settings.get("last_reminded_at")

                    if interval_hours and last_reminded_at_str:
                        # TIMEZONE_NOTE: Similar to specific_time, handle naive/aware comparison.
                        last_reminded_at_obj = datetime.fromisoformat(last_reminded_at_str)
                        
                        # Calculate next reminder time
                        # from datetime import timedelta (ensure timedelta is imported if not already)
                        from datetime import timedelta # Added here for safety, though usually at top
                        next_reminder_time = last_reminded_at_obj + timedelta(hours=float(interval_hours))

                        current_time_for_comparison = current_time
                        if last_reminded_at_obj.tzinfo: # If last_reminded was tz-aware
                             current_time_for_comparison = current_time.astimezone(last_reminded_at_obj.tzinfo)
                        
                        if current_time_for_comparison >= next_reminder_time:
                            due_reminders_messages.append(
                                f"REMINDER (Task ID: {task_id}): Interval reminder for task '{task_description}' (every {interval_hours} hours)."
                            )
                            reminder_settings["last_reminded_at"] = current_time.isoformat() # Update to current time (potentially with offset)
                            task["updated_at"] = current_time.isoformat()
            except ValueError as e:
                logger.error(f"Error processing reminder for task ID {task_id} ('{task_description}'): {e}", exc_info=True)
            except Exception as e: # Catch any other unexpected error during reminder processing for a task
                logger.error(f"Unexpected error processing reminder for task ID {task_id} ('{task_description}'): {e}", exc_info=True)
                # Optionally, add a generic error message to due_reminders_messages or handle differently
                # due_reminders_messages.append(f"ERROR processing reminder for task '{task_description}'.")


    return due_reminders_messages

# --- Tool/Action Functions ---

def set_reminder(user_data, params=None, user_id_for_save=None):
    """Tool to set a reminder for a task."""
    logger.info(f"Executing tool: set_reminder with params: {params} for user")
    if not params or "task_id" not in params or "reminder_type" not in params or "details" not in params:
        logger.error("set_reminder failed: 'task_id', 'reminder_type', or 'details' missing in params.")
        raise ToolExecutionError("task_id, reminder_type, and details are required for set_reminder.")

    try:
        task_id = int(params["task_id"])
    except ValueError:
        logger.error(f"set_reminder failed: invalid task_id format '{params['task_id']}'. Must be an integer.")
        raise ToolExecutionError(f"Invalid task_id format: '{params['task_id']}'. Must be an integer.")

    reminder_type = params["reminder_type"]
    details = params["details"]
    
    valid_reminder_types = ["specific_time", "interval", "daily"]
    if reminder_type not in valid_reminder_types:
        logger.error(f"set_reminder failed: invalid reminder_type '{reminder_type}'.")
        raise ToolExecutionError(f"Invalid reminder_type: {reminder_type}. Must be one of {valid_reminder_types}.")

    reminder_setting = {"type": reminder_type}
    current_time_iso = datetime.now().isoformat()

    if reminder_type == "specific_time":
        if "time" not in details or not isinstance(details["time"], str):
            raise ToolExecutionError("For 'specific_time' reminder, 'details' must include a 'time' string (ISO format).")
        try:
            # Validate ISO format by attempting to parse it
            datetime.fromisoformat(details["time"])
            reminder_setting["time"] = details["time"]
        except ValueError:
            raise ToolExecutionError("Invalid time format for 'specific_time'. Must be YYYY-MM-DDTHH:MM:SS.")
    elif reminder_type == "interval":
        if "hours" not in details or not isinstance(details["hours"], (int, float)) or details["hours"] <= 0:
            raise ToolExecutionError("For 'interval' reminder, 'details' must include 'hours' (positive number).")
        reminder_setting["hours"] = details["hours"]
        if "start_time" in details:
            if not isinstance(details["start_time"], str):
                 raise ToolExecutionError("For 'interval' reminder, 'start_time' must be a string (ISO format).")
            try:
                datetime.fromisoformat(details["start_time"])
                reminder_setting["start_time"] = details["start_time"]
                reminder_setting["last_reminded_at"] = details["start_time"] # Start from the specified time
            except ValueError:
                raise ToolExecutionError("Invalid start_time format for 'interval'. Must be YYYY-MM-DDTHH:MM:SS.")
        else:
            reminder_setting["last_reminded_at"] = current_time_iso # Start from now
    elif reminder_type == "daily":
        if "time_of_day" not in details or not isinstance(details["time_of_day"], str):
            raise ToolExecutionError("For 'daily' reminder, 'details' must include 'time_of_day' (HH:MM string).")
        try:
            # Validate HH:MM format
            datetime.strptime(details["time_of_day"], "%H:%M")
            reminder_setting["time_of_day"] = details["time_of_day"]
        except ValueError:
            raise ToolExecutionError("Invalid time_of_day format for 'daily'. Must be HH:MM.")

    task_found = False
    for task in user_data.get("tasks", []):
        if task["id"] == task_id:
            task["reminder_settings"] = reminder_setting
            task["updated_at"] = current_time_iso
            task_found = True
            break
    
    if task_found:
        if user_id_for_save:
            save_memory(user_id_for_save, user_data)
            logger.info(f"Reminder set for task {task_id} for user {user_id_for_save}.")
        else:
            logger.warning(f"Reminder set for task {task_id} in user_data, but not saved as user_id_for_save was not provided.")
        return {"success": True, "message": f"Reminder set for task {task_id}.", "reminder_settings": reminder_setting}
    else:
        logger.warning(f"set_reminder: Task with id {task_id} not found for user.")
        raise ToolExecutionError(f"Task with id {task_id} not found.")

def get_reminders(user_data, params=None, user_id_for_save=None): # user_id_for_save is unused but part of lambda
    """Tool to get reminders, either for a specific task or all tasks."""
    logger.info(f"Executing tool: get_reminders with params: {params} for user")
    
    task_id_filter = params.get("task_id") if params else None

    if task_id_filter is not None:
        try:
            task_id_to_find = int(task_id_filter)
        except ValueError:
            logger.error(f"get_reminders failed: invalid task_id format '{task_id_filter}'. Must be an integer.")
            raise ToolExecutionError(f"Invalid task_id format: '{task_id_filter}'. Must be an integer.")
        
        for task in user_data.get("tasks", []):
            if task["id"] == task_id_to_find:
                return task.get("reminder_settings", {})
        # Also check archived tasks, as per potential future requirements, though current spec implies active tasks.
        # For now, let's stick to active tasks based on current context.
        logger.warning(f"get_reminders: Task with id {task_id_to_find} not found for user.")
        raise ToolExecutionError(f"Task with id {task_id_to_find} not found.")
    else:
        all_reminders = []
        for task in user_data.get("tasks", []):
            if task.get("reminder_settings"):
                all_reminders.append({
                    "task_id": task["id"],
                    "description": task["description"],
                    "reminder_settings": task["reminder_settings"]
                })
        return all_reminders

# The user_id must be passed to this function from the caller (e.g. process_user_input)
def perform_file_action(action_dict, user_data, user_id_for_save):
    """Performs an action based on the action_dict from LLM, for a specific user."""
    try:
        action_name = action_dict["action"] # Expect 'action' key
        action_params = action_dict.get("params", {}) # 'params' is optional
    except KeyError as e:
        logger.error(f"perform_file_action failed for user {user_id_for_save}: Missing key '{e}' in action_dict: {action_dict}", exc_info=True)
        raise ToolExecutionError(f"Action dictionary is missing required key: {e}")

    logger.info(f"Attempting to perform action for user {user_id_for_save}: {action_name} with params: {action_params}")
    
    tool_map = {
        "get_tasks": get_tasks, 
        "add_task": lambda data, params: add_task(data, params, user_id_for_save=user_id_for_save),
        "update_task_status": lambda data, params: update_task_status(data, params, user_id_for_save=user_id_for_save),
        "discard_task": lambda data, params: discard_task(data, params, user_id_for_save=user_id_for_save),
        "set_reminder": lambda data, params: set_reminder(data, params, user_id_for_save=user_id_for_save),
        "get_reminders": lambda data, params: get_reminders(data, params, user_id_for_save=user_id_for_save) # user_id_for_save not used by get_reminders
    }

    if action_name in tool_map:
        try:
            # Pass user_data (which is specific to the user) to the tool
            return tool_map[action_name](user_data, action_params)
        except ToolExecutionError as e: 
            logger.error(f"Error executing tool {action_name} for user {user_id_for_save}: {e}", exc_info=True)
            return {"error": f"Error in {action_name}: {str(e)}"} 
        except Exception as e: 
            logger.error(f"Unexpected error executing tool {action_name} for user {user_id_for_save}: {e}", exc_info=True)
            return {"error": f"Unexpected error in {action_name}: {str(e)}"}
    else:
        logger.error(f"Unknown action requested for user {user_id_for_save}: {action_name}")
        return {"error": f"Unknown action: {action_name}"}

# --- LLM Interaction ---
# This function now requires user_id to load/save correct data and to pass for tool saving.
def process_user_input(user_id: str, user_input_text: str, message_history: list[str] = None):
    """Processes user input using LLM and available tools for a specific user."""
    
    # Load the specific user's data
    try:
        user_data = load_memory(user_id)
    except MemoryOperationError as e:
        logger.error(f"Could not load memory for user {user_id} in process_user_input: {e}", exc_info=True)
        return f"Error: Could not load your data: {e}"

    tools_list = [
        {
            "type": "function",
            "function": {
                "name": "get_tasks",
                "description": "Get all tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_task",
                "description": "Add a new task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "The description of the task."
                        },
                        "due_date": {
                            "type": "string",
                            "description": "The due date of the task (e.g., YYYY-MM-DD). Optional."
                        }
                    },
                    "required": ["description"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_task_status",
                "description": "Update a task's status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to update."
                        },
                        "status": {
                            "type": "string",
                            "description": "The new status of the task (e.g., pending, completed, deferred)."
                        }
                    },
                    "required": ["task_id", "status"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "discard_task",
                "description": "Discard a task and move it to the archive.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to discard."
                        }
                    },
                    "required": ["task_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_reminder",
                "description": "Set a reminder for a specific task. `details` object structure depends on `reminder_type`.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to set a reminder for."
                        },
                        "reminder_type": {
                            "type": "string",
                            "description": "Type of reminder.",
                            "enum": ["specific_time", "interval", "daily"]
                        },
                        "details": {
                            "type": "object",
                            "description": "Object containing reminder details. For 'specific_time', requires {'time': 'YYYY-MM-DDTHH:MM:SS'}. For 'interval', requires {'hours': N, 'start_time': 'YYYY-MM-DDTHH:MM:SS' (optional, defaults to now)}. For 'daily', requires {'time_of_day': 'HH:MM'}.",
                            "properties": {
                                "time": {"type": "string", "format": "date-time"},
                                "hours": {"type": "number"},
                                "start_time": {"type": "string", "format": "date-time"},
                                "time_of_day": {"type": "string", "pattern": "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"}
                            }
                            # 'required' for details sub-properties depends on reminder_type,
                            # which is handled in the function logic.
                        }
                    },
                    "required": ["task_id", "reminder_type", "details"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_reminders",
                "description": "Get reminders. If task_id is provided, gets reminders for that task. Otherwise, gets all active reminders.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "The ID of the task to get reminders for (optional)."
                        }
                    }
                }
            }
        }
    ]

    history_prompt_segment = ""
    if message_history:
        history_prompt_segment = "Previous messages:\n"
        # Assuming message_history is a list of user messages as per current TelegramHandler
        # If assistant messages were also stored, the formatting would need to differentiate.
        for msg in message_history:
            history_prompt_segment += f"- User: {msg}\n" # Corrected to use 'User:' as per example
        history_prompt_segment += "\n"

    # Prepare a snippet of current tasks for the prompt
    # Showing only a few tasks helps keep the prompt concise.
    # The LLM should rely on get_tasks for comprehensive task listing if needed.
    tasks_for_prompt = []
    active_tasks = user_data.get('tasks', [])
    if active_tasks:
        tasks_for_prompt = active_tasks[:3] # Show first 3 active tasks
    else: # If no active tasks, maybe show first few archived if they exist
        archived_tasks_preview = user_data.get('archived_tasks', [])[:1]
        if archived_tasks_preview:
            tasks_for_prompt = archived_tasks_preview # Show 1 archived task as an example
    
    tasks_snippet_for_prompt = json.dumps(tasks_for_prompt, indent=2)
    if not tasks_for_prompt:
        tasks_snippet_for_prompt = "No tasks found for the user yet."


    prompt = f"""You are Mazkir, a helpful AI assistant for managing tasks and reminders.
Your user's preferred tone is: {user_data.get("preferences", {}).get("tone", "neutral")}. Please adapt your responses accordingly.

{history_prompt_segment}Current user input: "{user_input_text}"

Key Task Management Information:
- Tasks can have statuses: "pending", "completed", "deferred", or "discarded".
- When a task is marked "completed" or "discarded", it is moved to an archive.
- You can use tools to manage tasks:
    - `add_task`: To create a new task.
    - `update_task_status`: To change a task's status (e.g., to "completed", "pending", "deferred").
    - `discard_task`: To directly discard a task, which also moves it to the archive.
    - `get_tasks`: To retrieve a list of current tasks.

Reminder Capabilities:
- You can set reminders for tasks using the `set_reminder` tool. This requires the `task_id`.
  - Reminder Types:
    - "specific_time": For a one-time reminder at a specific date and time (e.g., "Remind me on 2024-01-01 at 10:00 AM").
    - "daily": For a recurring daily reminder at a specific time of day (e.g., "Remind me daily at 8 AM").
    - "interval": For a recurring reminder at a set interval of hours (e.g., "Remind me every 3 hours for this task"). You can also specify a start date and time for interval reminders.
  - How to ask for reminders:
    - For "specific_time": "Set a reminder for task 123 on July 15th at 2 PM."
    - For "daily": "Set a daily reminder for task 456 at 7:30 AM."
    - For "interval": "Remind me every 4 hours for task 789, starting tomorrow at 9 AM." or "Remind me every 2 hours for task 101." (starts now if no start time).
- You can view reminders using `get_reminders`. This tool can show reminders for one task (if `task_id` is given) or all active tasks.
- IMPORTANT: I will automatically check for any due reminders each time you talk to me and will inform you if any are due. If you explicitly ask to "check reminders" or similar, I will provide the reminder information as the main response.

Your Goal:
Based on the user input, decide if a tool should be used.
- If a tool is appropriate, call the function with the correct parameters.
- If multiple steps are needed (e.g., creating a task then setting a reminder), call the necessary tools sequentially.
- After tool use (or if no tool is needed), respond to the user in natural language.
- Summarize your actions clearly (e.g., "Okay, I've added task 'Buy milk' and set a reminder for tomorrow at 9 AM.").
- If a tool call results in an error (e.g., task not found), communicate this clearly.

Current state of some tasks (for context only, use `get_tasks` for full list if needed):
{tasks_snippet_for_prompt}

Respond now.
"""

    try:
        response = litellm.completion(
            model=MAZKIR_LLM_MODEL,
            messages=[{"content": prompt, "role": "user"}],
            tools=tools_list,
            tool_choice="auto"
        )

        if not response.choices or not response.choices[0].message:
            logger.error("LLM response is missing choices or message object.")
            return "Error: Received a malformed response from the LLM provider."

        message = response.choices[0].message

        # Log raw message details
        raw_message_content = message.content
        logger.info(f"-------------------")
        logger.info(f"LLM raw message content: '{raw_message_content}'")
        logger.info(f"-------------------")

        tool_calls = message.tool_calls

        if tool_calls:
            results = []
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON arguments for tool {function_name}: {tool_call.function.arguments}. Error: {e}", exc_info=True)
                    results.append({"error": f"Invalid arguments for {function_name}: {e}"})
                    continue

                action_dict = {"action": function_name, "params": function_args}
                try:
                    # Pass user_data and user_id for saving to perform_file_action
                    tool_result = perform_file_action(action_dict, user_data, user_id_for_save=user_id)
                    results.append(tool_result)
                except ToolExecutionError as e:
                    logger.error(f"ToolExecutionError for action {function_name} for user {user_id}: {e}", exc_info=True)
                    results.append({"error": f"Error executing {function_name}: {str(e)}"})
                except Exception as e: 
                    logger.error(f"Unexpected error during execution of {function_name} for user {user_id}: {e}", exc_info=True)
                    results.append({"error": f"Unexpected error in {function_name}: {str(e)}"})
            
            # After tool execution, user_data in memory *might* have been changed by the tool.
            # The save_memory call *within* the tool (add_task, update_task_status) should persist this.
            # The 'results' list contains what the tools returned.
            
            # Pass them back to the LLM for a summary
            
            # Construct messages for the second LLM call
            # user_input is the original text from the user.
            # 'message' is response.choices[0].message from the first LLM call.
            # It needs to be converted to a dictionary to be JSON serializable.

            assistant_message_dict = {"role": message.role} # message.role is typically "assistant"
            
            # Preserve content (None, empty string, or actual content)
            # LiteLLM examples show "content": None for messages that primarily trigger tool calls.
            assistant_message_dict["content"] = message.content 
            
            if message.tool_calls:
                assistant_message_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type, # Usually "function"
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments # This is already a JSON string
                        }
                    } for tc in message.tool_calls
                ]
            
            messages_for_summary_llm = [
                {"role": "user", "content": user_input_text}, # The raw user input text
                assistant_message_dict  # Use the converted dictionary
            ]

            # Append the results of the tool calls
            # 'tool_calls' variable is already message.tool_calls from before this conversion
            for i, tool_call_obj in enumerate(tool_calls): # tool_calls is message.tool_calls
                # Ensure results[i] is a JSON string for the 'content' field
                tool_result_content = json.dumps(results[i])
                
                messages_for_summary_llm.append({
                    "role": "tool",
                    "tool_call_id": tool_call_obj.id, 
                    "name": tool_call_obj.function.name,
                    "content": tool_result_content
                })
            

            try:
                # Second call to LLM to generate a natural language response based on tool execution
                final_response_obj = litellm.completion(
                    model=MAZKIR_LLM_MODEL,
                    messages=messages_for_summary_llm
                    # No tools or tool_choice needed here, we want a direct natural language response
                )

                if final_response_obj.choices and final_response_obj.choices[0].message and final_response_obj.choices[0].message.content:
                    final_llm_output = final_response_obj.choices[0].message.content.strip()
                    logger.info(f"LLM summary response after tool execution: '{final_llm_output}'")
                    return final_llm_output
                else:
                    logger.error("LLM response after tool execution was empty or malformed.")
                    # Fallback to returning raw tool results if summarization fails
                    if len(results) == 1:
                        return f"Action performed. Result: {json.dumps(results[0])} (LLM summary failed)"
                    return f"Actions performed. Results: {json.dumps(results)} (LLM summary failed)"

            except litellm.exceptions.APIError as e:
                logger.error(f"LiteLLM APIError on second call (summarization): {e}", exc_info=True)
                return f"Error: LLM API issue after tool execution: {e}. Raw results: {json.dumps(results)}"
            except Exception as e:
                logger.error(f"Unexpected error during second LLM call (summarization): {e}", exc_info=True)
                # Fallback to returning raw tool results
                if len(results) == 1:
                    return f"Action performed. Result: {json.dumps(results[0])}. Error during summarization: {e}"
                return f"Actions performed. Results: {json.dumps(results)}. Error during summarization: {e}"

        elif message.content: # Natural language response from the first LLM call
            llm_output = message.content.strip()
            if not llm_output: # Content was whitespace or effectively empty
                logger.warning("LLM message.content was present but effectively empty after stripping.")
                final_response_str = "I didn't have a specific action to take, but I've checked your reminders."
            else:
                logger.info("LLM output was natural language.")
                final_response_str = llm_output
        else: # No tool_calls and no message.content
            logger.warning("LLM response had no tool_calls and no meaningful content. Defaulting reminder check message.")
            final_response_str = "I've checked your reminders." # Default response when LLM gives no specific instruction but we proceed to check reminders

        # --- Reminder Checking ---
        # This happens after LLM response/tool execution and potential summarization
        user_data_modified_by_reminders = False
        try:
            due_reminder_messages = check_due_reminders(user_data)
            if due_reminder_messages:
                user_data_modified_by_reminders = True # Mark that user_data was changed
                reminder_report = "\n\n--- Upcoming Reminders ---\n" + "\n".join(due_reminder_messages)
                final_response_str += reminder_report
                logger.info(f"Due reminders found for user {user_id}: {due_reminder_messages}")
            else:
                # Optionally, add a message if no reminders are due, if final_response_str is minimal
                if final_response_str == "I've checked your reminders.": # Only if no other LLM output
                     final_response_str += "\nNo reminders are currently due."
                logger.info(f"No due reminders for user {user_id}.")

        except Exception as e:
            logger.error(f"Error during check_due_reminders for user {user_id}: {e}", exc_info=True)
            final_response_str += "\nError: Could not check reminders due to an internal issue."
            # Do not set user_data_modified_by_reminders to True here, as the check failed.

        # --- Save memory if check_due_reminders modified it ---
        # This is crucial because check_due_reminders modifies user_data in-place (e.g. specific_time_triggered, last_reminded_at)
        # and these changes need to be saved even if no tools that explicitly save memory were called.
        if user_data_modified_by_reminders:
            try:
                save_memory(user_id, user_data) # MAZKIR_MEMORY_FILE is used by default
                logger.info(f"Memory saved for user {user_id} after reminder check modified user_data.")
            except MemoryOperationError as e:
                logger.error(f"Failed to save memory for user {user_id} after reminder check: {e}", exc_info=True)
                # Append to response or handle as critical error?
                final_response_str += "\nWarning: Could not save updated reminder status."
        
        return final_response_str

    except litellm.exceptions.APIError as e: # More specific litellm error
        logger.error(f"LiteLLM APIError in process_user_input for user {user_id}: {e}", exc_info=True)
        # Attempt to check reminders even if LLM fails, as a fallback
        final_response_str = f"Error: LLM API issue: {e}."
        user_data_modified_by_reminders = False
        try:
            due_reminder_messages = check_due_reminders(user_data)
            if due_reminder_messages:
                user_data_modified_by_reminders = True
                reminder_report = "\n\n--- Upcoming Reminders ---\n" + "\n".join(due_reminder_messages)
                final_response_str += reminder_report
            if user_data_modified_by_reminders:
                 save_memory(user_id, user_data)
        except Exception as re: # Reminder Exception
            logger.error(f"Error during fallback reminder check for user {user_id}: {re}", exc_info=True)
            final_response_str += "\nAdditionally, could not check reminders."
        return final_response_str

    except Exception as e: # General errors during litellm.completion or response processing
        logger.error(f"Unexpected error in process_user_input for user {user_id}: {e}", exc_info=True)
        # Attempt to check reminders even if other processing fails
        final_response_str = f"Error: Could not fully process your request: {e}."
        user_data_modified_by_reminders = False
        try:
            due_reminder_messages = check_due_reminders(user_data)
            if due_reminder_messages:
                user_data_modified_by_reminders = True
                reminder_report = "\n\n--- Upcoming Reminders ---\n" + "\n".join(due_reminder_messages)
                final_response_str += reminder_report
            if user_data_modified_by_reminders:
                save_memory(user_id, user_data)
        except Exception as re: # Reminder Exception
            logger.error(f"Error during fallback reminder check for user {user_id}: {re}", exc_info=True)
            final_response_str += "\nAdditionally, could not check reminders."
        return final_response_str


# --- Main Interactive Loop ---
# run_interactive_mode has been moved to cli_handler.py as CliHandler.start()

if __name__ == "__main__":
    # --- Setup Phase ---
    logger.info("Mazkir script initiated by user.")
    
    # --- Determine Mode (Example: Use an environment variable or command-line arg) ---
    # For now, this example defaults to starting the Telegram handler.
    # You could use argparse or check os.getenv("MAZKIR_MODE") to switch between "telegram", "cli", etc.
    
    # Make sure TELEGRAM_BOT_TOKEN is set in the environment for TelegramHandler to work
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        logger.warning("TELEGRAM_BOT_TOKEN is not set. TelegramHandler may not start.")
        # Depending on desired behavior, could exit or try to run CLI mode as fallback.
        # For now, we'll let TelegramHandler raise its own error if token is missing.

    logger.info("Defaulting to start TelegramHandler.")

    # These imports are here because this __main__ block is part of mazkir.py
    # If this were a separate main.py, imports would be like:
    # from mazkir_core.mazkir import process_user_input
    # from mazkir_handlers.telegram_handler import TelegramHandler
    
    from telegram_handler import TelegramHandler 
    # process_user_input is already defined in this file (mazkir.py)
    
    try:
        # process_user_input is a function defined in this (mazkir.py) file.
        # TELEGRAM_BOT_TOKEN will be read from environment by the handler itself.
        telegram_handler_instance = TelegramHandler(process_user_input_func=process_user_input)
        telegram_handler_instance.start()
    except ValueError as e: # Catch errors from TelegramHandler init (e.g., missing token)
        logger.critical(f"Could not start TelegramHandler: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred when trying to start TelegramHandler: {e}", exc_info=True)

    # To run CLI mode, you would do something like:
    # from cli_handler import CliHandler
    # config = {
    #     "MAZKIR_MEMORY_FILE": MAZKIR_MEMORY_FILE,
    #     "MAZKIR_LLM_MODEL": MAZKIR_LLM_MODEL
    # }
    # cli_handler_instance = CliHandler(process_user_input_func=process_user_input, mazkir_instance_config=config)
    # cli_handler_instance.start()
