import json
import os
import litellm
import litellm.exceptions # For specific LiteLLM exceptions
import logging
from datetime import datetime

# --- Configuration ---
# Setup basic logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # Outputs to console
        # logging.FileHandler("mazkir.log") # Optionally log to a file
    ]
)
logger = logging.getLogger(__name__)

# Environment variable configuration
MAZKIR_MEMORY_FILE = os.getenv("MAZKIR_MEMORY_FILE", "mazkir_memory.json")
MAZKIR_LLM_MODEL = os.getenv("MAZKIR_LLM_MODEL", "gpt-3.5-turbo")

# --- Tool Schemas for LiteLLM ---
MAZKIR_TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Get all current tasks from the user's task list.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a new task to the user's task list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "The description of the task."
                    },
                    "due_date": {
                        "type": "string",
                        "description": "The due date for the task in YYYY-MM-DD format. Optional."
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
            "description": "Update the status of an existing task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The ID of the task to update."
                    },
                    "status": {
                        "type": "string",
                        "description": "The new status for the task.",
                        "enum": ["pending", "completed", "deferred"]
                    }
                },
                "required": ["task_id", "status"]
            }
        }
    }
]

# --- Custom Exceptions ---
class MemoryOperationError(Exception):
    """Custom exception for memory load/save errors."""
    pass

class ToolExecutionError(Exception):
    """Custom exception for errors during tool execution."""
    pass

# --- Memory Functions ---
def load_memory(filepath=None):
    """Loads tasks from the JSON memory file."""
    file_to_load = filepath or MAZKIR_MEMORY_FILE
    logger.debug(f"Attempting to load memory from {file_to_load}")
    try:
        with open(file_to_load, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Memory loaded successfully from {file_to_load}")
            # Validate structure
            if not isinstance(data.get("tasks"), list):
                logger.warning(f"'tasks' key missing or not a list in {file_to_load}. Initializing with empty list.")
                data["tasks"] = []
            if not isinstance(data.get("next_task_id"), int):
                logger.warning(f"'next_task_id' key missing or not an int in {file_to_load}. Initializing to 1.")
                data["next_task_id"] = 1
            return data
    except FileNotFoundError:
        logger.warning(f"Memory file {file_to_load} not found. Initializing with default structure.")
        return {"tasks": [], "next_task_id": 1}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {file_to_load}: {e}. Returning default structure.")
        # Depending on desired robustness, could raise MemoryOperationError here
        return {"tasks": [], "next_task_id": 1}
    except Exception as e:
        logger.error(f"Unexpected error loading memory from {file_to_load}: {e}", exc_info=True)
        raise MemoryOperationError(f"Failed to load memory due to unexpected error: {e}")


def save_memory(data, filepath=None):
    """Saves tasks to the JSON memory file."""
    file_to_save = filepath or MAZKIR_MEMORY_FILE
    logger.debug(f"Attempting to save memory to {file_to_save}")
    try:
        with open(file_to_save, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Memory saved successfully to {file_to_save}")
    except IOError as e:
        logger.error(f"IOError saving memory to {file_to_save}: {e}", exc_info=True)
        raise MemoryOperationError(f"IOError saving memory: {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving memory to {file_to_save}: {e}", exc_info=True)
        raise MemoryOperationError(f"Failed to save memory due to unexpected error: {e}")

# --- Dedicated Tool Execution Functions ---
def _execute_get_tasks(memory_data: dict) -> list:
    """
    Retrieves all tasks from memory.
    Returns a list of task objects.
    """
    logger.info("Executing internal tool: _execute_get_tasks")
    return memory_data.get("tasks", [])


def _execute_add_task(memory_data: dict, description: str, due_date: str = None) -> dict:
    """
    Adds a new task to memory.
    Updates metadata like last_task_id and history (if applicable).
    Returns the newly created task dictionary.
    Raises ToolExecutionError if 'description' is missing.
    """
    logger.info(f"Executing internal tool: _execute_add_task, Description: '{description}', Due Date: {due_date}")
    if not description: # Should be caught by schema, but defensive check
        logger.error("_execute_add_task failed: Description is empty or None.")
        raise ToolExecutionError("Task description cannot be empty.")

    # Ensure 'metadata' and 'history' keys exist, or initialize them
    if "metadata" not in memory_data:
        memory_data["metadata"] = {"last_task_id": 0} # Or other relevant defaults
    if "history" not in memory_data:
        memory_data["history"] = []

    last_task_id = memory_data["metadata"].get("last_task_id", 0)
    new_task_id = last_task_id + 1
    
    new_task = {
        "id": new_task_id,
        "description": description,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    if due_date:
        new_task["due_date"] = due_date
        
    if "tasks" not in memory_data: # Ensure 'tasks' list exists
        memory_data["tasks"] = []
    memory_data["tasks"].append(new_task)
    memory_data["metadata"]["last_task_id"] = new_task_id
    
    # Log action to history
    memory_data["history"].append({
        "timestamp": datetime.now().isoformat(),
        "action": "add_task",
        "task_id": new_task_id,
        "details": f"Task added: '{description}'"
    })
    
    logger.info(f"Task {new_task_id} added: '{description}'")
    return new_task


def _execute_update_task_status(memory_data: dict, task_id: int, status: str) -> dict | str:
    """
    Updates the status of an existing task.
    Updates 'completed_at' or 'updated_at' timestamps and logs to history.
    Returns the updated task dictionary if successful, or an error string/dict if not.
    """
    logger.info(f"Executing internal tool: _execute_update_task_status, Task ID: {task_id}, New Status: '{status}'")
    
    # Validate status (though schema should handle this)
    valid_statuses = ["pending", "completed", "deferred"]
    if status not in valid_statuses:
        logger.error(f"_execute_update_task_status failed: Invalid status '{status}' for task ID {task_id}.")
        return {"error": f"Invalid status: {status}. Must be one of {valid_statuses}."}

    task_found = False
    updated_task_details = None
    for task in memory_data.get("tasks", []):
        if task.get("id") == task_id:
            task["status"] = status
            task["updated_at"] = datetime.now().isoformat()
            if status == "completed":
                task["completed_at"] = datetime.now().isoformat()
            
            task_found = True
            updated_task_details = task
            
            # Log action to history
            if "history" not in memory_data: memory_data["history"] = []
            memory_data["history"].append({
                "timestamp": datetime.now().isoformat(),
                "action": "update_task_status",
                "task_id": task_id,
                "details": f"Task ID {task_id} status updated to '{status}'."
            })
            logger.info(f"Task {task_id} status updated to '{status}'.")
            break
            
    if not task_found:
        logger.warning(f"_execute_update_task_status: Task with ID {task_id} not found.")
        return {"error": f"Task with ID {task_id} not found."}
        
    return updated_task_details


# --- LLM Interaction ---
def process_user_input(user_input_text: str, memory_data: dict) -> str:
    """
    Processes user input using LiteLLM, deciding whether to call tools or respond directly.
    Implements structured tool calling if the LLM indicates a tool should be used.
    """
    logger.debug(f"Processing user input: '{user_input_text}'")

    # --- System Prompt Setup ---
    preferred_tone = memory_data.get('preferences', {}).get('tone', 'neutral')
    system_prompt = f"You are Mazkir, a helpful personal task assistant. Your tone should be {preferred_tone}."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input_text}
    ]
    logger.debug(f"Initial messages for LLM (model: {MAZKIR_LLM_MODEL}): {messages}")

    try:
        # --- First LiteLLM Call (Tool Decision) ---
        api_key_present = any(os.getenv(key) for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "REPLICATE_API_TOKEN", "GEMINI_API_KEY"])
        if not api_key_present and not getattr(litellm, 'mock_response', None):
            logger.warning("No common LLM API key found. LiteLLM call may fail or use fallback/mock.")

        logger.info(f"Sending first request to LiteLLM (model: {MAZKIR_LLM_MODEL}) for tool decision.")
        response = litellm.completion(
            model=MAZKIR_LLM_MODEL, messages=messages,
            tools=MAZKIR_TOOLS_SCHEMAS, tool_choice="auto"
        )
        assistant_message = response.choices[0].message
        messages.append(assistant_message)
        logger.debug(f"First LLM response from {MAZKIR_LLM_MODEL}: {assistant_message}")

        # --- Tool Call Handling ---
        if assistant_message.tool_calls:
            logger.info(f"LLM requested {len(assistant_message.tool_calls)} tool call(s).")
            tools_executed_successfully = True # Flag to track if all tools ran ok

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_arguments_str = tool_call.function.arguments
                tool_call_id = tool_call.id
                logger.info(f"Processing tool call: {tool_name}, ID: {tool_call_id}, Args (str): {tool_arguments_str}")

                try:
                    tool_arguments_dict = json.loads(tool_arguments_str)
                except json.JSONDecodeError as e_json:
                    logger.error(f"JSONDecodeError parsing arguments for tool {tool_name}: {e_json}. Args: {tool_arguments_str}", exc_info=True)
                    tool_function_result_str = json.dumps({"error": f"Invalid arguments for {tool_name}: {e_json}"})
                    tools_executed_successfully = False # Mark failure
                else:
                    try:
                        if tool_name == "get_tasks":
                            tool_function_result = _execute_get_tasks(memory_data)
                        elif tool_name == "add_task":
                            desc = tool_arguments_dict.get("description")
                            due = tool_arguments_dict.get("due_date")
                            if desc is None: # Schema should prevent, but defensive
                                raise ToolExecutionError("Missing required parameter: description for add_task")
                            tool_function_result = _execute_add_task(memory_data, desc, due)
                        elif tool_name == "update_task_status":
                            task_id = tool_arguments_dict.get("task_id")
                            status = tool_arguments_dict.get("status")
                            if task_id is None or status is None: # Schema should prevent
                                raise ToolExecutionError("Missing task_id or status for update_task_status")
                            # Schema defines task_id as integer, so direct use is fine if LLM adheres.
                            # Add explicit int conversion if strictness is needed here beyond schema.
                            tool_function_result = _execute_update_task_status(memory_data, int(task_id), status)
                        else:
                            logger.warning(f"Unknown tool name requested by LLM: {tool_name}")
                            tool_function_result = {"error": f"Unknown tool: {tool_name}"}
                            tools_executed_successfully = False # Mark failure
                        
                        # Ensure result is a string for the LLM
                        if not isinstance(tool_function_result, str):
                            tool_function_result_str = json.dumps(tool_function_result)
                        else: # If it's already a string (e.g. error string from update_task_status)
                            tool_function_result_str = tool_function_result 
                        
                        logger.info(f"Tool {tool_name} executed. Result (stringified): {tool_function_result_str[:200]}...")

                    except ToolExecutionError as e_tool_exec:
                        logger.error(f"ToolExecutionError for {tool_name}: {e_tool_exec}", exc_info=True)
                        tool_function_result_str = json.dumps({"error": f"Error executing {tool_name}: {e_tool_exec}"})
                        tools_executed_successfully = False # Mark failure
                    except Exception as e_tool_other:
                        logger.error(f"Unexpected error executing tool {tool_name}: {e_tool_other}", exc_info=True)
                        tool_function_result_str = json.dumps({"error": f"Unexpected error with {tool_name}: {e_tool_other}"})
                        tools_executed_successfully = False # Mark failure
                
                messages.append({"tool_call_id": tool_call_id, "role": "tool", "name": tool_name, "content": tool_function_result_str})
            
            # --- Save Memory After All Tool Executions for this turn ---
            if tools_executed_successfully: # Only save if all tools in the turn were successful (or if partial success is okay)
                try:
                    save_memory(memory_data)
                    logger.info("Memory saved successfully after tool executions.")
                except MemoryOperationError as e_save:
                    logger.error(f"CRITICAL: Failed to save memory after tool executions: {e_save}", exc_info=True)
                    return "Error: Could not save task data after performing actions. Please check logs."

            # --- Second LiteLLM Call (Final Response) ---
            logger.info(f"Sending second request to LiteLLM (model: {MAZKIR_LLM_MODEL}) for final response.")
            logger.debug(f"Messages for second LLM call: {messages}")
            response_final = litellm.completion(model=MAZKIR_LLM_MODEL, messages=messages)
            final_content = response_final.choices[0].message.content
            logger.debug(f"Second LLM response from {MAZKIR_LLM_MODEL}: {final_content}")
            return final_content.strip() if final_content else "Actions performed. No further comment from assistant."

        else: # No tool calls
            logger.info("No tool calls requested by LLM. Using direct response.")
            return assistant_message.content.strip() if assistant_message.content else ""

    except litellm.exceptions.APIError as e:
        logger.error(f"LiteLLM APIError (model: {MAZKIR_LLM_MODEL}): {e}", exc_info=True)
        return f"Error: The AI model API returned an error: {e}"
    except litellm.exceptions.TimeoutError as e:
        logger.error(f"LiteLLM TimeoutError (model: {MAZKIR_LLM_MODEL}): {e}", exc_info=True)
        return "Error: The request to the AI model timed out. Please try again later."
    except litellm.exceptions.ServiceUnavailableError as e:
        logger.error(f"LiteLLM ServiceUnavailableError (model: {MAZKIR_LLM_MODEL}): {e}", exc_info=True)
        return "Error: The AI model service is currently unavailable. Please try again later."
    except Exception as e:
        logger.error(f"Unexpected error in process_user_input (model: {MAZKIR_LLM_MODEL}): {e}", exc_info=True)
        return f"Error: Could not get response from LLM due to an unexpected issue: {e}"

# --- Main Interactive Loop ---
def run_interactive_mode():
    """Runs the Mazkir assistant in an interactive command-line loop."""
    logger.info(f"Starting Mazkir Assistant in Interactive Mode. Model: {MAZKIR_LLM_MODEL}, Memory File: {MAZKIR_MEMORY_FILE}")

    try:
        memory_data = load_memory()
    except MemoryOperationError as e:
        logger.critical(f"Failed to load initial memory: {e}. Mazkir cannot start interactive mode.", exc_info=True)
        print(f"Fatal Error: Could not load memory. Check logs at {MAZKIR_MEMORY_FILE}. Exiting.")
        return

    # Optional: Add a sample task if memory is empty (can be removed if not desired for interactive mode)
    if not memory_data.get("tasks"):
        logger.info("Memory is empty. Adding a sample task for demonstration.")
        try:
            # This call to add_task will use the loaded memory_data and save it internally.
            add_task(memory_data, {"description": "Review Mazkir setup", "due_date": datetime.now().strftime("%Y-%m-%d")})
        except (MemoryOperationError, ToolExecutionError) as e:
            logger.error(f"Failed to add initial sample task during setup: {e}", exc_info=True)
            print("Notice: Could not add a sample task during setup. Continuing.")


    print("\nMazkir Interactive Assistant")
    print("Type 'exit' or 'quit' to end the session.")
    print("------------------------------------")

    while True:
        try:
            user_input_text = input("You: ").strip()

            if user_input_text.lower() in ['exit', 'quit']:
                logger.info("User initiated exit from interactive loop.")
                print("Assistant: Goodbye!")
                break
            
            if not user_input_text: # Handle empty input
                continue

            assistant_response = process_user_input(user_input_text, memory_data)
            print(f"Assistant: {assistant_response}")

        except KeyboardInterrupt:
            logger.info("User interrupted session with Ctrl+C.")
            print("\nAssistant: Session interrupted. Type 'exit' or 'quit' to leave.")
            # Optionally, could exit here, but allowing continuation might be preferred.
        except MemoryOperationError as e: # Errors related to saving/loading during an operation
            logger.error(f"A memory operation error occurred during processing: {e}", exc_info=True)
            print(f"Assistant: Error: A problem occurred with memory storage: {e}")
        except ToolExecutionError as e: # Errors from tool execution
            logger.error(f"A tool execution error occurred: {e}", exc_info=True)
            print(f"Assistant: Error: A problem occurred while performing an action: {e}")
        except Exception as e: # Catch-all for other unexpected errors in the loop
            logger.error(f"An unexpected error occurred in the interactive loop: {e}", exc_info=True)
            print(f"Assistant: Error: An unexpected issue occurred: {e}")
            # Depending on severity, you might want to break or offer to reset.

    logger.info("Interactive session ended.")
    # Final save is handled by tools or if explicitly added here.
    # For robustness, a final save attempt might be good if memory_data could be stale.
    try:
        logger.info("Attempting final save of memory on exit from interactive mode.")
        save_memory(memory_data)
    except MemoryOperationError as e:
        logger.error(f"Failed to save memory on exiting interactive mode: {e}", exc_info=True)
        print(f"Warning: Could not save memory on exit: {e}")


if __name__ == "__main__":
    # --- Setup Phase ---
    logger.info("Mazkir script initiated by user.")
    
    # LiteLLM specific: API keys are typically set as environment variables.
    # The script will warn if common keys are not found.
    
    # Mocking LiteLLM for environments without API keys (for basic testing)
    if not any(os.getenv(key) for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "REPLICATE_API_TOKEN"]):
        logger.warning("No common LLM API keys detected. Using MOCK LiteLLM completion for this session.")
        
        # --- Mock LiteLLM Completion Function ---
        def mock_litellm_completion(*args, **kwargs):
            # pylint: disable=unused-argument
            logger.debug(f"Mock LLM called with messages: {kwargs.get('messages')}")
            
            class MockMessage:
                def __init__(self, content=""):
                    self.content = content
            
            class MockChoice:
                def __init__(self, content=""):
                    self.message = MockMessage(content)
            
            class MockResponse:
                def __init__(self, content=""):
                    self.choices = [MockChoice(content)]

            user_msg_content = kwargs.get("messages", [{}])[0].get("content", "").lower()
            
            if "add test task" in user_msg_content:
                logger.debug("Mock LLM: Simulating 'add_task' action.")
                return MockResponse('{"action": "add_task", "params": {"description": "Test task from mock"}}')
            elif "show tasks" in user_msg_content or "get tasks" in user_msg_content:
                logger.debug("Mock LLM: Simulating 'get_tasks' action.")
                return MockResponse('{"action": "get_tasks"}')
            elif "update task" in user_msg_content: # Basic mock for update
                logger.debug("Mock LLM: Simulating 'update_task_status' action for task_id 1.")
                return MockResponse('{"action": "update_task_status", "params": {"task_id": 1, "status": "completed from mock"}}')
            else:
                logger.debug("Mock LLM: Providing default assistance message.")
                return MockResponse("This is a mock LLM response as no API key was detected. Please ask to 'add test task', 'show tasks', or 'update task'.")
        
        litellm.completion = mock_litellm_completion
        # litellm.set_verbose = True # Useful for debugging litellm itself

    # --- Run Interactive Mode ---
    run_interactive_mode()
