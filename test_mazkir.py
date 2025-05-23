import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import os
import tempfile
from datetime import datetime
import logging

import mazkir_refined # The module we are testing
import litellm.exceptions # For mocking specific LiteLLM errors

# Suppress most logging during tests to keep output clean
mazkir_refined.logger.setLevel(logging.CRITICAL + 1)


class TestMazkirRefined(unittest.TestCase):

    def setUp(self):
        """Setup common test data for each test method."""
        self.initial_task_id = 1
        self.sample_task_1_desc = "Test task 1"
        self.sample_task_1 = {
            "id": self.initial_task_id, 
            "description": self.sample_task_1_desc,
            "status": "pending", 
            "created_at": datetime.now().isoformat()
        }
        
        # Base memory structure, deepcopy in tests if modified
        self.memory_data_base = {
            "tasks": [],
            "metadata": {"last_task_id": 0},
            "history": [],
            "preferences": {"tone": "neutral"}
        }

    # --- Tests for Dedicated Tool Execution Functions ---
    
    def test_execute_get_tasks_empty(self):
        memory_data = {"tasks": [], "metadata": {}, "history": []} # Minimal valid structure
        result = mazkir_refined._execute_get_tasks(memory_data)
        self.assertEqual(result, [])

    def test_execute_get_tasks_populated(self):
        memory_data = {"tasks": [self.sample_task_1], "metadata": {}, "history": []}
        result = mazkir_refined._execute_get_tasks(memory_data)
        self.assertEqual(result, [self.sample_task_1])

    def test_execute_add_task_valid(self):
        memory_data = {
            "tasks": [], 
            "metadata": {"last_task_id": 0}, 
            "history": []
        }
        desc = "New laundry task"
        due = "2024-12-31"
        
        new_task = mazkir_refined._execute_add_task(memory_data, desc, due)
        
        self.assertEqual(new_task["description"], desc)
        self.assertEqual(new_task["due_date"], due)
        self.assertEqual(new_task["status"], "pending")
        self.assertEqual(new_task["id"], 1)
        self.assertEqual(memory_data["tasks"][-1]["description"], desc)
        self.assertEqual(memory_data["metadata"]["last_task_id"], 1)
        self.assertEqual(len(memory_data["history"]), 1)
        self.assertEqual(memory_data["history"][0]["action"], "add_task")

    def test_execute_add_task_no_due_date(self):
        memory_data = {"tasks": [], "metadata": {"last_task_id": 5}, "history": []}
        desc = "Simple task"
        new_task = mazkir_refined._execute_add_task(memory_data, desc)
        self.assertEqual(new_task["description"], desc)
        self.assertNotIn("due_date", new_task)
        self.assertEqual(new_task["id"], 6) # last_task_id was 5
        self.assertEqual(memory_data["metadata"]["last_task_id"], 6)

    def test_execute_add_task_missing_description_raises_error(self):
        memory_data = {"tasks": [], "metadata": {"last_task_id": 0}, "history": []}
        with self.assertRaises(mazkir_refined.ToolExecutionError) as context:
            mazkir_refined._execute_add_task(memory_data, description="") # Empty description
        self.assertIn("Task description cannot be empty", str(context.exception))

    def test_execute_update_task_status_valid(self):
        task_to_update = dict(self.sample_task_1) # Make a copy
        memory_data = {"tasks": [task_to_update], "metadata": {"last_task_id": 1}, "history": []}
        new_status = "completed"
        
        updated_task = mazkir_refined._execute_update_task_status(memory_data, self.initial_task_id, new_status)
        
        self.assertEqual(updated_task["status"], new_status)
        self.assertIn("updated_at", updated_task)
        self.assertIn("completed_at", updated_task) # Specific to "completed"
        self.assertEqual(memory_data["tasks"][0]["status"], new_status)
        self.assertEqual(len(memory_data["history"]), 1)
        self.assertEqual(memory_data["history"][0]["details"], f"Task ID {self.initial_task_id} status updated to '{new_status}'.")

    def test_execute_update_task_status_non_existent_id(self):
        memory_data = {"tasks": [self.sample_task_1], "metadata": {}, "history": []}
        result = mazkir_refined._execute_update_task_status(memory_data, 999, "completed")
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Task with ID 999 not found", result["error"])

    def test_execute_update_task_status_invalid_status(self):
        memory_data = {"tasks": [self.sample_task_1], "metadata": {}, "history": []}
        result = mazkir_refined._execute_update_task_status(memory_data, self.initial_task_id, "invalid_status_string")
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("Invalid status: invalid_status_string", result["error"])

    # --- Tests for process_user_input (Structured Tool Calling) ---

    @patch('mazkir_refined.litellm.completion')
    def test_process_input_direct_llm_answer(self, mock_litellm_completion):
        memory_data = self.memory_data_base.copy()
        user_message = "Just a friendly chat."
        llm_direct_answer = "Hello there! How can I help you today?"

        # Mock first and only LLM call
        mock_response1 = MagicMock()
        mock_response1.choices[0].message.tool_calls = None # No tool calls
        mock_response1.choices[0].message.content = llm_direct_answer
        mock_litellm_completion.return_value = mock_response1
        
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        self.assertEqual(result, llm_direct_answer)
        mock_litellm_completion.assert_called_once() # Only one call expected

    @patch('mazkir_refined._execute_add_task')
    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.save_memory') # Mock save_memory to prevent actual file writes during this test
    def test_process_input_successful_tool_call_add_task(self, mock_save_memory, mock_litellm_completion, mock_execute_add_task):
        memory_data = self.memory_data_base.copy()
        user_message = "Add a task: Buy groceries tomorrow"
        
        # 1. Mock first LLM call (requests tool use)
        mock_llm_response1 = MagicMock()
        tool_call_id = "call_123"
        tool_arguments_str = '{"description": "Buy groceries", "due_date": "tomorrow"}'
        mock_llm_response1.choices[0].message.tool_calls = [MagicMock()]
        mock_llm_response1.choices[0].message.tool_calls[0].id = tool_call_id
        mock_llm_response1.choices[0].message.tool_calls[0].function.name = "add_task"
        mock_llm_response1.choices[0].message.tool_calls[0].function.arguments = tool_arguments_str
        mock_llm_response1.choices[0].message.content = None # Often None when tool_calls are present
        
        # 2. Mock the tool execution function
        tool_execution_result = {"id": 1, "description": "Buy groceries", "due_date": "tomorrow", "status": "pending"}
        mock_execute_add_task.return_value = tool_execution_result
        
        # 3. Mock second LLM call (summarizes tool result)
        mock_llm_response2 = MagicMock()
        final_summary = "Okay, I've added 'Buy groceries' due tomorrow to your tasks."
        mock_llm_response2.choices[0].message.content = final_summary
        
        # Set up side_effect for multiple calls to litellm.completion
        mock_litellm_completion.side_effect = [mock_llm_response1, mock_llm_response2]
        
        # --- Act ---
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        # --- Assert ---
        self.assertEqual(mock_litellm_completion.call_count, 2)
        
        # Assert call to _execute_add_task
        mock_execute_add_task.assert_called_once_with(
            memory_data, 
            description="Buy groceries", 
            due_date="tomorrow"
        )
        
        # Assert messages for the second LLM call
        args_second_call, kwargs_second_call = mock_litellm_completion.call_args_list[1]
        messages_for_second_call = kwargs_second_call['messages']
        
        self.assertEqual(len(messages_for_second_call), 3) # System, User, Assistant (with tool_call), Tool Result
        self.assertEqual(messages_for_second_call[2]["role"], "assistant") # Assistant's first response
        self.assertTrue(hasattr(messages_for_second_call[2], 'tool_calls')) # Check if it's a MagicMock with tool_calls

        self.assertEqual(messages_for_second_call[-1]["role"], "tool")
        self.assertEqual(messages_for_second_call[-1]["tool_call_id"], tool_call_id)
        self.assertEqual(messages_for_second_call[-1]["name"], "add_task")
        self.assertEqual(messages_for_second_call[-1]["content"], json.dumps(tool_execution_result))
        
        # Assert final result
        self.assertEqual(result, final_summary)
        mock_save_memory.assert_called_once_with(memory_data) # Check if memory was saved

    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.save_memory')
    def test_process_input_tool_arg_parsing_error(self, mock_save_memory, mock_litellm_completion):
        memory_data = self.memory_data_base.copy()
        user_message = "Call a tool with bad args"

        # 1. Mock first LLM call (requests tool use with malformed args)
        mock_llm_response1 = MagicMock()
        tool_call_id = "call_bad_args"
        malformed_tool_arguments_str = '{"description": "Buy milk", "due_date": tomorrow_no_quotes}' # Malformed
        mock_llm_response1.choices[0].message.tool_calls = [MagicMock()]
        mock_llm_response1.choices[0].message.tool_calls[0].id = tool_call_id
        mock_llm_response1.choices[0].message.tool_calls[0].function.name = "add_task"
        mock_llm_response1.choices[0].message.tool_calls[0].function.arguments = malformed_tool_arguments_str
        mock_llm_response1.choices[0].message.content = None

        # 2. Mock second LLM call (should receive error info)
        mock_llm_response2 = MagicMock()
        final_error_summary = "It seems there was an issue with the arguments for adding the task."
        mock_llm_response2.choices[0].message.content = final_error_summary
        
        mock_litellm_completion.side_effect = [mock_llm_response1, mock_llm_response2]

        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        self.assertEqual(mock_litellm_completion.call_count, 2)
        args_second_call, kwargs_second_call = mock_litellm_completion.call_args_list[1]
        messages_for_second_call = kwargs_second_call['messages']
        
        tool_result_message = messages_for_second_call[-1]
        self.assertEqual(tool_result_message["role"], "tool")
        self.assertIn("error", tool_result_message["content"].lower())
        self.assertIn("invalid arguments", tool_result_message["content"].lower())
        
        self.assertEqual(result, final_error_summary)
        mock_save_memory.assert_not_called() # Save should not happen if tool parsing fails

    @patch('mazkir_refined._execute_update_task_status')
    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.save_memory')
    def test_process_input_internal_tool_execution_error(self, mock_save_memory, mock_litellm_completion, mock_execute_update_task_status):
        memory_data = self.memory_data_base.copy()
        user_message = "Update task 999 to completed"

        # 1. Mock first LLM call
        mock_llm_response1 = MagicMock()
        tool_call_id = "call_tool_fail"
        tool_arguments_str = '{"task_id": 999, "status": "completed"}'
        mock_llm_response1.choices[0].message.tool_calls = [MagicMock()]
        mock_llm_response1.choices[0].message.tool_calls[0].id = tool_call_id
        mock_llm_response1.choices[0].message.tool_calls[0].function.name = "update_task_status"
        mock_llm_response1.choices[0].message.tool_calls[0].function.arguments = tool_arguments_str
        
        # 2. Mock tool execution to return an error
        tool_error_result = {"error": "Task with ID 999 not found."}
        mock_execute_update_task_status.return_value = tool_error_result
        
        # 3. Mock second LLM call
        mock_llm_response2 = MagicMock()
        final_error_summary = "I couldn't update task 999 as it was not found."
        mock_llm_response2.choices[0].message.content = final_error_summary
        
        mock_litellm_completion.side_effect = [mock_llm_response1, mock_llm_response2]

        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        self.assertEqual(mock_litellm_completion.call_count, 2)
        mock_execute_update_task_status.assert_called_once_with(memory_data, 999, "completed")
        
        args_second_call, kwargs_second_call = mock_litellm_completion.call_args_list[1]
        messages_for_second_call = kwargs_second_call['messages']
        tool_result_message = messages_for_second_call[-1]
        self.assertEqual(tool_result_message["role"], "tool")
        self.assertEqual(tool_result_message["content"], json.dumps(tool_error_result))
        
        self.assertEqual(result, final_error_summary)
        mock_save_memory.assert_not_called() # Save should not occur if the tool indicates an error that prevents state change

    # --- Tests for load_memory and save_memory (File I/O) ---
    # These tests remain largely the same as they are not directly affected by tool calling logic.
    def test_save_and_load_memory_integration(self):
        temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix=".json")
        os.close(temp_file_descriptor)
        try:
            data_to_save = {
                "tasks": [self.sample_task_1],
                "metadata": {"last_task_id": self.initial_task_id + 1},
                "history": [{"action": "test"}],
                "preferences": {"tone": "witty"}
            }
            mazkir_refined.save_memory(data_to_save, filepath=temp_file_path)
            loaded_data = mazkir_refined.load_memory(filepath=temp_file_path)
            self.assertEqual(loaded_data, data_to_save)
        finally:
            os.remove(temp_file_path)

    def test_load_memory_file_not_found(self):
        non_existent_path = os.path.join(tempfile.gettempdir(), "non_existent_mazkir_mem.json")
        if os.path.exists(non_existent_path): os.remove(non_existent_path)
        loaded_data = mazkir_refined.load_memory(filepath=non_existent_path)
        self.assertEqual(loaded_data, {"tasks": [], "next_task_id": 1}) # Default structure

    def test_load_memory_json_decode_error(self):
        temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(temp_file_descriptor, 'w') as f: f.write("{'tasks': [") # Malformed
            loaded_data = mazkir_refined.load_memory(filepath=temp_file_path)
            self.assertEqual(loaded_data, {"tasks": [], "next_task_id": 1}) # Default
        finally:
            if os.path.exists(temp_file_path): os.remove(temp_file_path)

    def test_save_memory_io_error(self):
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.side_effect = IOError("Simulated Disk Full")
            data_to_save = {"tasks": [], "metadata": {}, "history": []}
            with self.assertRaises(mazkir_refined.MemoryOperationError) as context:
                mazkir_refined.save_memory(data_to_save, filepath="/read_only_path/mem.json")
            self.assertIn("IOError saving memory", str(context.exception))

if __name__ == '__main__':
    unittest.main()
