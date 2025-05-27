import pytest
from unittest.mock import patch, MagicMock
import json
import os
import tempfile
from datetime import datetime, timezone

# Assuming mazkir.py is in the same directory or accessible in PYTHONPATH
import mazkir

# --- Fixtures ---

@pytest.fixture
def temp_memory_file():
    """Create a temporary, empty JSON file for memory and yield its path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w') as f:
        json.dump({}, f)  # Initialize with an empty JSON object for multi-user structure
    yield path
    os.remove(path)

@pytest.fixture
def mock_user_id():
    """Provide a standard mock user ID."""
    return "test_user_telegram_12345"

# --- Helper Function to Create Mock LLM Responses ---

def create_mock_llm_tool_call_response(tool_call_id: str, function_name: str, function_args_str: str, content: str = None):
    """Creates a mock LLM response that requests a tool call."""
    mock_response = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.id = tool_call_id
    mock_tool_call.type = "function"
    mock_tool_call.function.name = function_name
    mock_tool_call.function.arguments = function_args_str
    
    mock_message = MagicMock()
    mock_message.tool_calls = [mock_tool_call]
    mock_message.content = content # Can be None if only tool call is made
    
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_message
    return mock_response

def create_mock_llm_summary_response(summary_content: str):
    """Creates a mock LLM response that provides a direct content summary."""
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.tool_calls = None
    mock_message.content = summary_content
    
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = mock_message
    return mock_response

# --- Tests for add_task with Reminder Parameters ---

@patch('mazkir.litellm.completion')
def test_add_task_with_reminder_at(mock_litellm_completion, temp_memory_file, mock_user_id):
    """Test adding a task with a specific 'reminder_at' time."""
    user_input = "Add task: Buy milk, remind me tomorrow at 10am"
    task_description = "Buy milk"
    # For consistent testing, let's define a fixed datetime for reminder_at
    # In a real LLM interaction, this would be parsed from "tomorrow at 10am"
    reminder_at_iso = datetime(2024, 8, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat()
    
    tool_call_id = "call_add_milk_reminder_at"
    llm_tool_args_str = json.dumps({
        "description": task_description,
        "reminder_at": reminder_at_iso
    })
    llm_summary = f"Okay, I've added '{task_description}' with a reminder for {reminder_at_iso}."

    # Mock the sequence of LLM calls
    mock_litellm_completion.side_effect = [
        create_mock_llm_tool_call_response(tool_call_id, "add_task", llm_tool_args_str),
        create_mock_llm_summary_response(llm_summary)
    ]

    # Patch MAZKIR_MEMORY_FILE to use the temp file for this test
    with patch('mazkir.MAZKIR_MEMORY_FILE', temp_memory_file):
        final_response = mazkir.process_user_input(user_id=mock_user_id, user_input_text=user_input)

    # Assertions
    assert final_response == llm_summary
    
    # Verify memory content
    with open(temp_memory_file, 'r') as f:
        memory_data = json.load(f)
    
    user_tasks = memory_data.get(mock_user_id, {}).get("tasks", [])
    assert len(user_tasks) == 1
    added_task = user_tasks[0]
    
    assert added_task["description"] == task_description
    assert added_task["reminder_at"] == reminder_at_iso
    assert "due_date" not in added_task # Not specified
    assert added_task["reminder_interval"] == "" # Should be default empty
    assert added_task["last_reminded_at"] == "" # Should be default empty
    assert added_task["status"] == "pending"
    assert "created_at" in added_task
    assert memory_data[mock_user_id]["next_task_id"] == added_task["id"] + 1

@patch('mazkir.litellm.completion')
def test_add_task_with_reminder_interval(mock_litellm_completion, temp_memory_file, mock_user_id):
    """Test adding a task with a 'reminder_interval' (e.g., daily)."""
    user_input = "Add task: Check emails daily"
    task_description = "Check emails"
    reminder_interval = "daily"
    
    tool_call_id = "call_add_emails_interval"
    llm_tool_args_str = json.dumps({
        "description": task_description,
        "reminder_interval": reminder_interval
    })
    llm_summary = f"Okay, I've added '{task_description}' with a {reminder_interval} reminder."

    mock_litellm_completion.side_effect = [
        create_mock_llm_tool_call_response(tool_call_id, "add_task", llm_tool_args_str),
        create_mock_llm_summary_response(llm_summary)
    ]

    with patch('mazkir.MAZKIR_MEMORY_FILE', temp_memory_file):
        final_response = mazkir.process_user_input(user_id=mock_user_id, user_input_text=user_input)

    assert final_response == llm_summary
    
    with open(temp_memory_file, 'r') as f:
        memory_data = json.load(f)
    
    user_tasks = memory_data.get(mock_user_id, {}).get("tasks", [])
    assert len(user_tasks) == 1
    added_task = user_tasks[0]
    
    assert added_task["description"] == task_description
    assert added_task["reminder_interval"] == reminder_interval
    assert added_task["reminder_at"] == "" # Should be default empty
    assert "due_date" not in added_task
    assert added_task["last_reminded_at"] == ""
    assert added_task["status"] == "pending"

@patch('mazkir.litellm.completion')
def test_add_task_with_all_params(mock_litellm_completion, temp_memory_file, mock_user_id):
    """Test adding a task with description, due_date, reminder_at, and reminder_interval."""
    user_input = "Add task: Project deadline on 2024-12-31, remind me daily starting 2024-12-01T09:00:00"
    task_description = "Project deadline"
    due_date_iso = "2024-12-31"
    reminder_at_iso = "2024-12-01T09:00:00Z" # Explicit UTC for testing
    reminder_interval = "daily"
    
    tool_call_id = "call_add_project_all_params"
    llm_tool_args_str = json.dumps({
        "description": task_description,
        "due_date": due_date_iso,
        "reminder_at": reminder_at_iso,
        "reminder_interval": reminder_interval
    })
    llm_summary = (f"Okay, I've added '{task_description}' due on {due_date_iso}, "
                   f"with a {reminder_interval} reminder starting {reminder_at_iso}.")

    mock_litellm_completion.side_effect = [
        create_mock_llm_tool_call_response(tool_call_id, "add_task", llm_tool_args_str),
        create_mock_llm_summary_response(llm_summary)
    ]

    with patch('mazkir.MAZKIR_MEMORY_FILE', temp_memory_file):
        final_response = mazkir.process_user_input(user_id=mock_user_id, user_input_text=user_input)

    assert final_response == llm_summary
    
    with open(temp_memory_file, 'r') as f:
        memory_data = json.load(f)
        
    user_tasks = memory_data.get(mock_user_id, {}).get("tasks", [])
    assert len(user_tasks) == 1
    added_task = user_tasks[0]
    
    assert added_task["description"] == task_description
    assert added_task["due_date"] == due_date_iso
    assert added_task["reminder_at"] == reminder_at_iso
    assert added_task["reminder_interval"] == reminder_interval
    assert added_task["last_reminded_at"] == ""
    assert added_task["status"] == "pending"

# --- Placeholder for other test categories if needed ---
# For example, tests for get_tasks, update_task_status, direct LLM answers, error handling etc.
# would be structured similarly, using pytest fixtures and unittest.mock.patch.
# The old unittest.TestCase structure would be fully replaced.
#
# Example of how a get_tasks test might look (simplified):
# @patch('mazkir.litellm.completion')
# def test_get_tasks_flow(mock_litellm_completion, temp_memory_file, mock_user_id):
#     # 1. Setup: Add a task directly to memory for testing get_tasks
#     task_desc = "Initial task for get_tasks test"
#     initial_task = {
#         "id": 1, "description": task_desc, "status": "pending", 
#         "created_at": datetime.now(timezone.utc).isoformat(),
#         "reminder_at": "", "reminder_interval": "", "last_reminded_at": ""
#     }
#     initial_memory = {
#         mock_user_id: {
#             "tasks": [initial_task],
#             "next_task_id": 2,
#             "preferences": {"tone": "neutral", "daily_reminder_time": "09:00"}
#         }
#     }
#     with open(temp_memory_file, 'w') as f:
#         json.dump(initial_memory, f)

#     # 2. Mock LLM responses for get_tasks flow
#     user_input = "Show my tasks"
#     tool_call_id = "call_get_tasks_test"
#     llm_tool_args_str_get = json.dumps({}) # get_tasks takes no args
#     llm_summary_get = f"Here is your task: {task_desc}"

#     mock_litellm_completion.side_effect = [
#         create_mock_llm_tool_call_response(tool_call_id, "get_tasks", llm_tool_args_str_get),
#         create_mock_llm_summary_response(llm_summary_get)
#     ]
    
#     # 3. Run process_user_input
#     with patch('mazkir.MAZKIR_MEMORY_FILE', temp_memory_file):
#         final_response = mazkir.process_user_input(user_id=mock_user_id, user_input_text=user_input)
    
#     # 4. Assertions
#     assert final_response == llm_summary_get
#     # Add more assertions if needed, e.g., mock_litellm_completion call args
#     # Perform_file_action is implicitly tested by checking the final summary and memory (for add/update)
