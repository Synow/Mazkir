import json
import os
import litellm
import logging
from datetime import datetime

from dotenv import load_dotenv
# TODO: User request to remove Arize Phoenix integration for simplification.
# from openinference.instrumentation.litellm import LiteLLMInstrumentor
# from opentelemetry import trace
# from opentelemetry.sdk.trace import TracerProvider
# from opentelemetry.sdk.trace.export import BatchSpanProcessor
# from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Load environment variables from .env file
load_dotenv()

# TODO: User request to remove Arize Phoenix integration for simplification.
# # Configure OpenTelemetry for Arize Phoenix
# # Ensure your Phoenix instance is running and accessible at the specified endpoint.
# # For local Docker setup, endpoint is typically http://localhost:4317 or http://0.0.0.0:4317
# phoenix_tracer_provider = trace.get_tracer_provider()
# if not isinstance(phoenix_tracer_provider, TracerProvider): # Check if a provider is already configured
#     phoenix_tracer_provider = TracerProvider()
#     trace.set_tracer_provider(phoenix_tracer_provider)
# else:
#     print("TracerProvider already configured.") # Or log this
#
# # Configure the OTLP exporter
# # Make sure your Phoenix collector is running at http://0.0.0.0:4317 (or your actual endpoint)
# otlp_exporter = OTLPSpanExporter(
#     endpoint="http://0.0.0.0:4317",  # Default for local Phoenix. Adjust if necessary.
#     insecure=True  # Use insecure=True for HTTP. For HTTPS, set to False and configure certs.
# )
#
# # Add the OTLP exporter to the tracer provider
# phoenix_tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
#
# # Instrument LiteLLM
# LiteLLMInstrumentor().instrument(tracer_provider=phoenix_tracer_provider)
#
# print("Arize Phoenix LiteLLM Instrumentor configured.") # Add a print statement to confirm execution

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
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/sivan/.config/gcloud/service-account-key.json" # Removed problematic hardcoded path
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
    new_task = {
        "id": task_id,
        "description": params["description"],
        "status": "pending",
        "created_at": datetime.now().isoformat()
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
    
    for task in user_data["tasks"]:
        if task["id"] == task_id_to_update:
            task["status"] = new_status
            task["updated_at"] = datetime.now().isoformat()
            task_found = True
            updated_task_details = task
            break # Found the task, no need to continue loop
            
    if task_found:
        if user_id_for_save: # If user_id is provided, save the memory
            save_memory(user_id_for_save, user_data)
            logger.info(f"Task {task_id_to_update} status updated to {new_status} for user {user_id_for_save}")
        else:
            logger.warning(f"Task {task_id_to_update} status updated in user_data, but not saved to file as user_id_for_save was not provided.")
        return updated_task_details
    else:
        logger.warning(f"update_task_status: Task with id {task_id_to_update} not found for user.")
        return {"error": f"Task with id {task_id_to_update} not found."}


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
        "get_tasks": get_tasks, # get_tasks doesn't modify data, so doesn't need user_id_for_save
        "add_task": lambda data, params: add_task(data, params, user_id_for_save=user_id_for_save),
        "update_task_status": lambda data, params: update_task_status(data, params, user_id_for_save=user_id_for_save)
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
def process_user_input(user_id: str, user_input_text: str):
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
        }
    ]

    prompt = f"""User input: "{user_input_text}"

Based on the user input, decide if a tool should be used to manage tasks (get tasks, add a task, or update task status).
If a tool is appropriate, use it by calling the function. Otherwise, respond in natural language.

Current tasks (first 3 for context only, do not modify directly):
{json.dumps(user_data.get('tasks', [])[:3], indent=2)} 
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
        raw_tool_calls = message.tool_calls
        logger.info(f"LLM raw message content: '{raw_message_content}'")

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
                    # Note: perform_file_action (and the tools it calls like add_task, update_task_status)
                    # are now responsible for saving the modified user_data using user_id.
                    # If a tool that doesn't modify data (like get_tasks) was called, user_data remains unchanged here.
                    # If a tool modified user_data, it should have been saved to file already.
                    # We might need to reload user_data if the tool modified it and we want the absolute latest state
                    # for the second LLM call's context, but tools return the result of their action,
                    # which is usually sufficient for the summarization.
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
            # user_input_text is the original text from the user.
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
            
            logger.info(f"Preparing for second LLM call. Messages: {json.dumps(messages_for_summary_llm, indent=2)}")

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
                # Fall through to the 'else' block below
            else:
                logger.info("LLM output was natural language.")
                return llm_output # Return direct output

        # This block is reached if no tool_calls AND (message.content is None/empty OR message.content was only whitespace)
        logger.warning("LLM response had no tool_calls and no meaningful content.")
        return "I didn't receive a valid response from the model. Please try again." # Return direct message

    except litellm.exceptions.APIError as e: # More specific litellm error
        logger.error(f"LiteLLM APIError: {e}", exc_info=True)
        return f"Error: LLM API issue: {e}"
    except Exception as e: # General errors during litellm.completion or response processing
        logger.error(f"Unexpected error processing user input: {e}", exc_info=True)
        return f"Error: Could not get response from LLM or process it: {e}"


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
