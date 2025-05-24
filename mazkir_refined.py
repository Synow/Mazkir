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

# Load environment variables from .env file
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
MAZKIR_MEMORY_FILE = os.getenv("MAZKIR_MEMORY_FILE", "mazkir_memory.json")
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
    """Processes user input using LLM and available tools with native tool calling."""

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

    prompt = f"""User input: "{user_input}"

Based on the user input, decide if a tool should be used to manage tasks (get tasks, add a task, or update task status).
If a tool is appropriate, use it by calling the function. Otherwise, respond in natural language.

Current tasks (first 3 for context only, do not modify directly):
{json.dumps(memory_data.get('tasks', [])[:3], indent=2)}
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
                    tool_result = perform_file_action(action_dict, memory_data)
                    results.append(tool_result)
                except ToolExecutionError as e:
                    logger.error(f"ToolExecutionError for action {function_name}: {e}", exc_info=True)
                    results.append({"error": f"Error executing {function_name}: {str(e)}"})
                except Exception as e: # Catch unexpected errors from perform_file_action
                    logger.error(f"Unexpected error during execution of {function_name}: {e}", exc_info=True)
                    results.append({"error": f"Unexpected error in {function_name}: {str(e)}"})
            
            # Instead of returning results directly, pass them back to the LLM for a summary
            
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
                {"role": "user", "content": user_input}, # The raw user input text
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
    # --- Run Interactive Mode ---
    run_interactive_mode()
