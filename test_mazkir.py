import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import os
import tempfile
from datetime import datetime

# Adjust import path if mazkir_refined is in a different directory
import mazkir_refined

# Suppress logging during tests to keep output clean
# You might want to enable it for debugging specific tests
mazkir_refined.logger.setLevel(logging.CRITICAL + 1)


class TestMazkirRefined(unittest.TestCase):

    def setUp(self):
        """Setup common test data."""
        self.initial_task_id = 1
        self.sample_task_1 = {"id": self.initial_task_id, "description": "Test task 1", "status": "pending", "created_at": datetime.now().isoformat()}
        self.sample_task_2 = {"id": self.initial_task_id + 1, "description": "Test task 2", "status": "pending", "created_at": datetime.now().isoformat()}
        
        self.mock_memory_base = {
            "tasks": [],
            "next_task_id": self.initial_task_id
        }

    # --- Tests for perform_file_action ---
    @patch('mazkir_refined.save_memory') # Mock save_memory for most action tests
    def test_perform_action_get_tasks_empty(self, mock_save_memory):
        memory_data = {"tasks": [], "next_task_id": 1}
        action_dict = {"action": "get_tasks"}
        result = mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertEqual(result, [])
        mock_save_memory.assert_not_called() # get_tasks should not save

    @patch('mazkir_refined.save_memory')
    def test_perform_action_get_tasks_populated(self, mock_save_memory):
        tasks = [self.sample_task_1, self.sample_task_2]
        memory_data = {"tasks": tasks, "next_task_id": 3}
        action_dict = {"action": "get_tasks"}
        result = mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertEqual(result, tasks)
        mock_save_memory.assert_not_called()

    @patch('mazkir_refined.save_memory')
    def test_perform_action_add_task_valid(self, mock_save_memory):
        memory_data = {"tasks": [], "next_task_id": 1}
        task_description = "New laundry task"
        action_dict = {"action": "add_task", "params": {"description": task_description}}
        
        result = mazkir_refined.perform_file_action(action_dict, memory_data)
        
        self.assertEqual(result["description"], task_description)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["id"], 1)
        self.assertEqual(memory_data["tasks"][-1]["description"], task_description)
        self.assertEqual(memory_data["next_task_id"], 2)
        mock_save_memory.assert_called_once_with(memory_data)

    @patch('mazkir_refined.save_memory')
    def test_perform_action_add_task_missing_description(self, mock_save_memory):
        memory_data = {"tasks": [], "next_task_id": 1}
        action_dict = {"action": "add_task", "params": {}} # Missing description
        
        with self.assertRaises(mazkir_refined.ToolExecutionError) as context:
            mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertIn("Task description is required", str(context.exception))
        mock_save_memory.assert_not_called()

    @patch('mazkir_refined.save_memory')
    def test_perform_action_update_task_status_valid(self, mock_save_memory):
        tasks = [dict(self.sample_task_1), dict(self.sample_task_2)] # Use copies
        memory_data = {"tasks": tasks, "next_task_id": 3}
        task_id_to_update = self.sample_task_1["id"]
        new_status = "completed"
        action_dict = {"action": "update_task_status", "params": {"task_id": task_id_to_update, "status": new_status}}
        
        result = mazkir_refined.perform_file_action(action_dict, memory_data)
        
        self.assertEqual(result["id"], task_id_to_update)
        self.assertEqual(result["status"], new_status)
        self.assertIn("updated_at", result)
        
        updated_task_in_memory = next(t for t in memory_data["tasks"] if t["id"] == task_id_to_update)
        self.assertEqual(updated_task_in_memory["status"], new_status)
        mock_save_memory.assert_called_once_with(memory_data)

    @patch('mazkir_refined.save_memory')
    def test_perform_action_update_task_status_non_existent_id(self, mock_save_memory):
        memory_data = {"tasks": [self.sample_task_1], "next_task_id": 2}
        action_dict = {"action": "update_task_status", "params": {"task_id": 999, "status": "completed"}}
        
        result = mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])
        mock_save_memory.assert_not_called()

    @patch('mazkir_refined.save_memory')
    def test_perform_action_update_task_status_invalid_id_format(self, mock_save_memory):
        memory_data = {"tasks": [self.sample_task_1], "next_task_id": 2}
        action_dict = {"action": "update_task_status", "params": {"task_id": "abc", "status": "completed"}}
        
        with self.assertRaises(mazkir_refined.ToolExecutionError) as context:
            mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertIn("Invalid task_id format", str(context.exception))
        mock_save_memory.assert_not_called()
        
    @patch('mazkir_refined.save_memory')
    def test_perform_action_unknown_action(self, mock_save_memory):
        memory_data = {"tasks": [], "next_task_id": 1}
        action_dict = {"action": "non_existent_action", "params": {}}
        result = mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertIn("error", result)
        self.assertIn("Unknown action", result["error"])
        mock_save_memory.assert_not_called()

    @patch('mazkir_refined.save_memory')
    def test_perform_action_missing_action_key(self, mock_save_memory):
        memory_data = {"tasks": [], "next_task_id": 1}
        action_dict = {"params": {}} # Missing "action" key
        with self.assertRaises(mazkir_refined.ToolExecutionError) as context:
            mazkir_refined.perform_file_action(action_dict, memory_data)
        self.assertIn("missing required key", str(context.exception).lower())
        mock_save_memory.assert_not_called()


    # --- Tests for process_user_input ---
    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.perform_file_action') # We don't need load_memory mock if process_user_input takes memory_data
    def test_process_input_direct_llm_answer(self, mock_perform_action, mock_litellm_completion):
        memory_data = self.mock_memory_base.copy()
        user_message = "Hello, how are you?"
        llm_response_content = "I am fine, thank you!"
        
        mock_llm_response = MagicMock()
        mock_llm_response.choices[0].message.content = llm_response_content
        mock_litellm_completion.return_value = mock_llm_response
        
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        self.assertEqual(result, f"LLM response: {llm_response_content}")
        mock_litellm_completion.assert_called_once()
        mock_perform_action.assert_not_called()

    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.perform_file_action')
    def test_process_input_llm_requests_get_tasks(self, mock_perform_action, mock_litellm_completion):
        memory_data = self.mock_memory_base.copy()
        user_message = "Show my tasks"
        action_json = '{"action": "get_tasks"}'
        tool_result_data = [{"id": 1, "description": "A task"}]
        
        # Simulate LLM returning action JSON
        mock_llm_response_action = MagicMock()
        mock_llm_response_action.choices[0].message.content = action_json
        mock_litellm_completion.return_value = mock_llm_response_action
        
        # Simulate perform_file_action returning tasks
        mock_perform_action.return_value = tool_result_data
        
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        expected_action_dict = json.loads(action_json)
        mock_perform_action.assert_called_once_with(expected_action_dict, memory_data)
        self.assertEqual(result, f"Action result: {json.dumps(tool_result_data)}")

    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.perform_file_action')
    def test_process_input_llm_requests_add_task(self, mock_perform_action, mock_litellm_completion):
        memory_data = self.mock_memory_base.copy()
        user_message = "Add task: Buy milk"
        action_json = '{"action": "add_task", "params": {"description": "Buy milk"}}'
        tool_result_data = {"id": 1, "description": "Buy milk", "status": "pending"}

        mock_llm_response_action = MagicMock()
        mock_llm_response_action.choices[0].message.content = action_json
        mock_litellm_completion.return_value = mock_llm_response_action
        mock_perform_action.return_value = tool_result_data
        
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        expected_action_dict = json.loads(action_json)
        mock_perform_action.assert_called_once_with(expected_action_dict, memory_data)
        self.assertEqual(result, f"Action result: {json.dumps(tool_result_data)}")

    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.perform_file_action')
    def test_process_input_malformed_json_from_llm(self, mock_perform_action, mock_litellm_completion):
        memory_data = self.mock_memory_base.copy()
        user_message = "Do something strange"
        malformed_json_response = "{'action': 'get_tasks', 'params': {}" # Missing closing brace
        
        mock_llm_response = MagicMock()
        mock_llm_response.choices[0].message.content = malformed_json_response
        mock_litellm_completion.return_value = mock_llm_response
        
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        self.assertEqual(result, f"LLM response: {malformed_json_response}")
        mock_perform_action.assert_not_called()

    @patch('mazkir_refined.litellm.completion')
    @patch('mazkir_refined.perform_file_action')
    def test_process_input_llm_api_error(self, mock_perform_action, mock_litellm_completion):
        memory_data = self.mock_memory_base.copy()
        user_message = "Trigger API error"
        
        # Simulate litellm.completion raising an APIError
        # Note: litellm.exceptions.APIError needs to be available or use a generic Exception for testing
        # For this example, let's assume litellm.exceptions.APIError exists and can be imported
        # If not, you might need to mock litellm.exceptions itself or use a more generic error
        try:
            from litellm.exceptions import APIError as LiteLLMAPIError
        except ImportError:
            # If litellm is not fully installed or this specific exception path is different,
            # we use a generic Exception and check for its message.
            # This makes the test less specific but more resilient to litellm's internal structure.
            LiteLLMAPIError = Exception # Fallback to generic Exception
            print("\nWarning: litellm.exceptions.APIError not found, using generic Exception for LLM API error test.")

        mock_litellm_completion.side_effect = LiteLLMAPIError("Simulated API Error")
        
        result = mazkir_refined.process_user_input(user_message, memory_data)
        
        self.assertIn("Error: LLM API interaction failed", result)
        self.assertIn("Simulated API Error", result)
        mock_perform_action.assert_not_called()

    # --- Tests for load_memory and save_memory (File I/O) ---
    def test_save_and_load_memory_integration(self):
        """Test saving and then loading memory using a temporary file."""
        temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix=".json")
        os.close(temp_file_descriptor) # Close the descriptor, we just need the path

        try:
            # Test save_memory
            data_to_save = {
                "tasks": [self.sample_task_1],
                "next_task_id": self.initial_task_id + 1
            }
            mazkir_refined.save_memory(data_to_save, filepath=temp_file_path)

            # Verify file content (optional, but good for confidence)
            with open(temp_file_path, 'r') as f:
                content_on_disk = json.load(f)
            self.assertEqual(content_on_disk["tasks"][0]["description"], self.sample_task_1["description"])
            self.assertEqual(content_on_disk["next_task_id"], self.initial_task_id + 1)

            # Test load_memory
            loaded_data = mazkir_refined.load_memory(filepath=temp_file_path)
            self.assertEqual(len(loaded_data["tasks"]), 1)
            self.assertEqual(loaded_data["tasks"][0]["description"], self.sample_task_1["description"])
            self.assertEqual(loaded_data["next_task_id"], self.initial_task_id + 1)

        finally:
            os.remove(temp_file_path) # Clean up

    def test_load_memory_file_not_found(self):
        """Test load_memory when the file does not exist."""
        # Using a non-existent file path
        non_existent_path = os.path.join(tempfile.gettempdir(), "non_existent_mazkir_mem.json")
        if os.path.exists(non_existent_path): # Ensure it doesn't exist
             os.remove(non_existent_path)

        loaded_data = mazkir_refined.load_memory(filepath=non_existent_path)
        
        # Should return default structure
        self.assertEqual(loaded_data["tasks"], [])
        self.assertEqual(loaded_data["next_task_id"], 1)
    
    def test_load_memory_json_decode_error(self):
        """Test load_memory with a corrupted JSON file."""
        temp_file_descriptor, temp_file_path = tempfile.mkstemp(suffix=".json")
        
        try:
            # Write malformed JSON to the temp file
            with os.fdopen(temp_file_descriptor, 'w') as f:
                f.write("{'tasks': [") # Malformed JSON

            loaded_data = mazkir_refined.load_memory(filepath=temp_file_path)
            
            # Should return default structure due to JSONDecodeError
            self.assertEqual(loaded_data["tasks"], [])
            self.assertEqual(loaded_data["next_task_id"], 1)
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    def test_save_memory_io_error(self):
        """Test save_memory when an IOError occurs (e.g., read-only path)."""
        # This is harder to reliably simulate cross-platform without admin rights
        # Mocking open to raise IOError is a more controlled way for a unit test
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.side_effect = IOError("Simulated Disk Full")
            data_to_save = {"tasks": [], "next_task_id": 1}
            
            with self.assertRaises(mazkir_refined.MemoryOperationError) as context:
                # Use default path which will be mocked
                mazkir_refined.save_memory(data_to_save, filepath="/non_existent_dir/some_file.json") 
            self.assertIn("IOError saving memory", str(context.exception))


if __name__ == '__main__':
    # This allows running tests directly from the command line
    # You might need to adjust Python's path if mazkir_refined is not directly importable
    # e.g., by setting PYTHONPATH or modifying sys.path
    # For simplicity, this assumes mazkir_refined.py is in the same directory or PYTHONPATH
    
    # If litellm is not installed, some tests might behave differently or fail
    # The mock for litellm.exceptions.APIError tries to handle this gracefully.
    try:
        import litellm
    except ImportError:
        print("Warning: litellm library not found. LLM-related tests might be affected or use generic fallbacks.")
        # Mock litellm globally if it's not found, so imports don't break
        # This is a bit heavy-handed but can help tests run for non-LLM parts.
        # litellm = MagicMock()
        # litellm.exceptions = MagicMock()
        # litellm.exceptions.APIError = type('APIError', (Exception,), {})


    # Setup logging for tests - can be useful for debugging
    # logging.basicConfig(level=logging.DEBUG) # Or INFO
    # mazkir_refined.logger.setLevel(logging.DEBUG) # Set level for the module's logger
    
    unittest.main()
