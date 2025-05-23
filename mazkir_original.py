import json
import os
import litellm
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

# --- Custom Exceptions ---
class MemoryOperationError(Exception):
    """Custom exception for memory load/save errors."""
    pass

class ToolExecutionError(Exception):
    """Custom exception for errors during tool execution."""
    pass

# --- Memory Functions ---
def load_memory():
    """Loads tasks from the JSON memory file."""
    logger.debug(f"Attempting to load memory from {MAZKIR_MEMORY_FILE}")
    try:
        with open(MAZKIR_MEMORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Memory loaded successfully from {MAZKIR_MEMORY_FILE}")
            # Validate structure
            if not isinstance(data.get("tasks"), list):
                logger.warning(f"'tasks' key missing or not a list in {MAZKIR_MEMORY_FILE}. Initializing with empty list.")
                data["tasks"] = []
            if not isinstance(data.get("next_task_id"), int):
                logger.warning(f"'next_task_id' key missing or not an int in {MAZKIR_MEMORY_FILE}. Initializing to 1.")
                data["next_task_id"] = 1
            return data
    except FileNotFoundError:
        logger.warning(f"Memory file {MAZKIR_MEMORY_FILE} not found. Initializing with default structure.")
        return {"tasks": [], "next_task_id": 1}
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {MAZKIR_MEMORY_FILE}: {e}. Returning default structure.")
        # Depending on desired robustness, could raise MemoryOperationError here
        return {"tasks": [], "next_task_id": 1}
    except Exception as e:
        logger.error(f"Unexpected error loading memory from {MAZKIR_MEMORY_FILE}: {e}", exc_info=True)
        raise MemoryOperationError(f"Failed to load memory due to unexpected error: {e}")


def save_memory(data):
    """Saves tasks to the JSON memory file."""
    logger.debug(f"Attempting to save memory to {MAZKIR_MEMORY_FILE}")
    try:
        with open(MAZKIR_MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Memory saved successfully to {MAZKIR_MEMORY_FILE}")
    except IOError as e:
        logger.error(f"IOError saving memory to {MAZKIR_MEMORY_FILE}: {e}", exc_info=True)
        raise MemoryOperationError(f"IOError saving memory: {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving memory to {MAZKIR_MEMORY_FILE}: {e}", exc_info=True)
        raise MemoryOperationError(f"Failed to save memory due to unexpected error: {e}")

# --- Tool/Action Functions ---
def get_tasks(memory_data, params=None):
    """Tool to get all tasks."""
    logger.info(f"Executing tool: get_tasks with params: {params}")
    return memory_data.get("tasks", [])

def add_task(memory_data, params=None):
    """Tool to add a new task."""
    logger.info(f"Executing tool: add_task with params: {params}")
    if not params or "description" not in params:
        logger.error("add_task failed: 'description' missing in params.")
        raise ToolExecutionError("Task description is required for add_task.")
    
    task_id = memory_data.get("next_task_id", 1)
    new_task = {
        "id": task_id,
        "description": params["description"],
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    if "due_date" in params:
        new_task["due_date"] = params["due_date"]
        
    memory_data["tasks"].append(new_task)
    memory_data["next_task_id"] = task_id + 1
    save_memory(memory_data) # Save after modification
    logger.info(f"Task {task_id} added: {params['description']}")
    return new_task

def update_task_status(memory_data, params=None):
    """Tool to update a task's status."""
    logger.info(f"Executing tool: update_task_status with params: {params}")
    if not params or "task_id" not in params or "status" not in params:
        logger.error("update_task_status failed: 'task_id' or 'status' missing in params.")
        raise ToolExecutionError("task_id and status are required for update_task_status.")
    
    try:
        task_id_to_update = int(params["task_id"])
    except ValueError:
        logger.error(f"update_task_status failed: invalid task_id format '{params['task_id']}'. Must be an integer.")
        raise ToolExecutionError(f"Invalid task_id format: '{params['task_id']}'. Must be an integer.")

    new_status = params["status"]
    
    for task in memory_data["tasks"]:
        if task["id"] == task_id_to_update:
            task["status"] = new_status
            task["updated_at"] = datetime.now().isoformat()
            save_memory(memory_data) # Save after modification
            logger.info(f"Task {task_id_to_update} status updated to {new_status}")
            return task
            
    logger.warning(f"update_task_status: Task with id {task_id_to_update} not found.")
    return {"error": f"Task with id {task_id_to_update} not found."} # Or raise ToolExecutionError

def perform_file_action(action_dict, memory_data):
    """Performs an action based on the action_dict from LLM."""
    try:
        action_name = action_dict["action"] # Expect 'action' key
        action_params = action_dict.get("params", {}) # 'params' is optional
    except KeyError as e:
        logger.error(f"perform_file_action failed: Missing key '{e}' in action_dict: {action_dict}", exc_info=True)
        raise ToolExecutionError(f"Action dictionary is missing required key: {e}")

    logger.info(f"Attempting to perform action: {action_name} with params: {action_params}")
    
    tool_map = {
        "get_tasks": get_tasks,
        "add_task": add_task,
        "update_task_status": update_task_status
    }

    if action_name in tool_map:
        try:
            return tool_map[action_name](memory_data, action_params)
        except ToolExecutionError as e: # Catch errors from specific tools
            logger.error(f"Error executing tool {action_name}: {e}", exc_info=True)
            return {"error": f"Error in {action_name}: {str(e)}"} # Propagate error message
        except Exception as e: # Catch unexpected errors from tools
            logger.error(f"Unexpected error executing tool {action_name}: {e}", exc_info=True)
            return {"error": f"Unexpected error in {action_name}: {str(e)}"}
    else:
        logger.error(f"Unknown action requested: {action_name}")
        return {"error": f"Unknown action: {action_name}"}

# --- LLM Interaction ---
def process_user_input(user_input, memory_data):
    """Processes user input using LLM and available tools."""
    logger.debug(f"Processing user input: '{user_input}'")

    prompt = f"""User input: "{user_input}"
Available tools:
1. get_tasks: Get all tasks. (JSON: {{"action": "get_tasks"}})
2. add_task: Add a new task. (JSON: {{"action": "add_task", "params": {{"description": "task description", "due_date": "YYYY-MM-DD" (optional)}}}})
3. update_task_status: Update a task's status. (JSON: {{"action": "update_task_status", "params": {{"task_id": 123, "status": "completed|pending|deferred"}}}})

Based on the user input, decide if a tool should be used.
If yes, respond with a JSON object describing the action and its parameters.
If no tool is needed, or if you need clarification, respond with a natural language message.
Example action JSON: {{"action": "add_task", "params": {{"description": "Buy groceries"}}}}

Current tasks (first 3 for context only, do not modify directly):
{json.dumps(memory_data.get('tasks', [])[:3], indent=2)} 

Respond with ONLY the JSON action or a natural language message."""
    logger.debug(f"Prompt for LLM:\n{prompt}")

    try:
        # Check for common API keys for litellm
        api_key_present = any(os.getenv(key) for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "REPLICATE_API_TOKEN"]) # Add more as needed
        if not api_key_present:
             logger.warning("No common LLM API key (e.g., OPENAI_API_KEY, ANTHROPIC_API_KEY) found in environment. LiteLLM call may fail or use a fallback/mock.")
        
        response = litellm.completion(
            model=MAZKIR_LLM_MODEL,
            messages=[{"content": prompt, "role": "user"}]
        )
        llm_output = response.choices[0].message.content.strip()
        logger.debug(f"Raw LLM Output: {llm_output}")
    except litellm.exceptions.APIError as e:
        logger.error(f"LiteLLM APIError: {e}", exc_info=True)
        return f"Error: LLM API interaction failed: {e}"
    except Exception as e:
        logger.error(f"Unexpected error calling LiteLLM: {e}", exc_info=True)
        return f"Error: Could not get response from LLM: {e}"

    try:
        action_dict = json.loads(llm_output)
        logger.debug(f"LLM output parsed as JSON: {action_dict}")
        if "action" in action_dict:
            tool_result = perform_file_action(action_dict, memory_data)
            return f"Action result: {json.dumps(tool_result)}"
        else:
            logger.info("LLM output was JSON but not an action, treating as natural language.")
            return f"LLM response: {llm_output}" # Valid JSON, but not an action dict
    except json.JSONDecodeError:
        logger.info("LLM output was not JSON, treating as natural language response.")
        return f"LLM response: {llm_output}" # Not JSON
    except ToolExecutionError as e: # Catch errors from perform_file_action if it raises them directly
        logger.error(f"Error during tool execution triggered by LLM: {e}", exc_info=True)
        return f"Error executing requested action: {e}"
    except Exception as e:
        logger.error(f"Error processing LLM response or executing action: {e}", exc_info=True)
        return f"Error processing LLM response: {e}"

# --- Main Loop ---
def main():
    logger.info(f"Starting Mazkir Assistant. Model: {MAZKIR_LLM_MODEL}, Memory File: {MAZKIR_MEMORY_FILE}")
    
    try:
        memory = load_memory()
    except MemoryOperationError as e:
        logger.critical(f"Failed to load initial memory: {e}. Mazkir cannot start.", exc_info=True)
        return

    # Example: Add a task if memory is empty for demonstration
    if not memory.get("tasks"): # Check if tasks list is empty or missing
        logger.info("Memory is empty or tasks list missing. Adding a sample task for demonstration.")
        try:
            add_task(memory, {"description": "Setup Mazkir for the first time", "due_date": datetime.now().strftime("%Y-%m-%d")})
        except (MemoryOperationError, ToolExecutionError) as e:
             logger.error(f"Failed to add initial sample task: {e}", exc_info=True)
             # Continue without the sample task if it fails

    try:
        while True:
            user_input = input("\nYou (type 'exit' to quit): ")
            if user_input.lower() in ['exit', 'quit']:
                logger.info("User requested exit.")
                break
            
            response = process_user_input(user_input, memory)
            print(f"\nMazkir: {response}") # Keep print for user interaction
            
    except KeyboardInterrupt:
        logger.info("User interrupted session with Ctrl+C.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
    finally:
        logger.info("Mazkir session ended. Attempting to save final memory state.")
        try:
            if 'memory' in locals(): # Ensure memory was loaded
                 save_memory(memory)
        except MemoryOperationError as e:
            logger.error(f"Failed to save memory on exit: {e}", exc_info=True)
        logger.info("Mazkir shutdown complete.")

if __name__ == "__main__":
    logger.info("Mazkir script initiated by user.")
    
    # LiteLLM specific: API keys are typically set as environment variables.
    # e.g., OPENAI_API_KEY, ANTHROPIC_API_KEY, COHERE_API_KEY, etc.
    # The script will warn if common keys are not found.
    
    # Mocking LiteLLM for environments without API keys (for basic testing)
    # This should ideally be handled by LiteLLM's own fallback/mocking if available and configured.
    # For this exercise, we keep a simplified mock for demonstration if no keys are found.
    if not any(os.getenv(key) for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "REPLICATE_API_TOKEN"]):
        logger.warning("No common LLM API keys detected. Using MOCK LiteLLM completion for this session.")
        def mock_litellm_completion(*args, **kwargs):
            # pylint: disable=unused-argument
            logger.debug(f"Mock LLM called with messages: {kwargs.get('messages')}")
            class MockChoice:
                def __init__(self):
                    self.message = MockMessage()
            class MockMessage:
                def __init__(self):
                    user_msg_content = kwargs.get("messages", [{}])[0].get("content", "")
                    if "add test task" in user_msg_content.lower():
                        self.content = '{"action": "add_task", "params": {"description": "Test task from mock"}}'
                        logger.debug("Mock LLM: Simulating 'add_task' action.")
                    elif "show tasks" in user_msg_content.lower() or "get tasks" in user_msg_content.lower():
                         self.content = '{"action": "get_tasks"}'
                         logger.debug("Mock LLM: Simulating 'get_tasks' action.")
                    elif "update task" in user_msg_content.lower():
                        # Basic mock for update, assumes task_id 1
                        self.content = '{"action": "update_task_status", "params": {"task_id": 1, "status": "completed from mock"}}'
                        logger.debug("Mock LLM: Simulating 'update_task_status' action for task_id 1.")
                    else:
                        self.content = "This is a mock LLM response as no API key was detected. Please ask to 'add test task', 'show tasks', or 'update task'."
                        logger.debug("Mock LLM: Providing default assistance message.")
            class MockResponse:
                def __init__(self):
                    self.choices = [MockChoice()]
            return MockResponse()
        litellm.completion = mock_litellm_completion
        # litellm.set_verbose = True # Useful for debugging litellm itself

    main()
