import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone # Added timedelta and timezone
import logging

# Adjust import path if mazkir.py is in a different directory or part of a package
import mazkir 

# Suppress most logging during tests to keep output clean
# You might want to enable it for debugging specific tests, e.g., logging.DEBUG
mazkir.logger.setLevel(logging.CRITICAL + 1) 


class TestMazkir(unittest.TestCase):

    def setUp(self):
        """Setup common test data and configurations."""
        self.user_id = "test_user_alpha"
        self.temp_file_descriptor, self.temp_file_path = tempfile.mkstemp(suffix=".json")
        
        # Initialize with an empty structure for the test user
        with os.fdopen(self.temp_file_descriptor, 'w') as f:
            json.dump({self.user_id: mazkir._get_default_user_data()}, f)
        
        # Use this temp file for MAZKIR_MEMORY_FILE during tests
        self.patcher = patch('mazkir.MAZKIR_MEMORY_FILE', self.temp_file_path)
        self.mock_memory_file = self.patcher.start()

        # Load fresh user data for each test
        self.user_data = mazkir.load_memory(self.user_id)

    def tearDown(self):
        """Clean up after tests."""
        self.patcher.stop() # Stop patching MAZKIR_MEMORY_FILE
        # The temp file is created with mkstemp, so fd is already closed by 'w' mode in setUp.
        # We just need to remove it.
        if os.path.exists(self.temp_file_path):
            os.remove(self.temp_file_path)

    def _add_sample_task(self, description="Sample Task", due_date=None):
        """Helper to add a task and return its ID."""
        params = {"description": description}
        if due_date:
            params["due_date"] = due_date
        task = mazkir.add_task(self.user_data, params, user_id_for_save=self.user_id)
        mazkir.save_memory(self.user_id, self.user_data) # Save after add
        return task["id"]

    # --- Archiving and Discarding Tests ---
    def test_update_task_status_completed_archives_task(self):
        task_id = self_add_sample_task("Task to complete")
        self.assertEqual(len(self.user_data["tasks"]), 1)
        self.assertEqual(len(self.user_data["archived_tasks"]), 0)

        mazkir.update_task_status(self.user_data, {"task_id": task_id, "status": "completed"}, user_id_for_save=self.user_id)
        
        self.assertEqual(len(self.user_data["tasks"]), 0, "Task should be removed from active tasks.")
        self.assertEqual(len(self.user_data["archived_tasks"]), 1, "Task should be added to archived tasks.")
        archived_task = self.user_data["archived_tasks"][0]
        self.assertEqual(archived_task["id"], task_id)
        self.assertEqual(archived_task["status"], "completed")
        self.assertTrue(any(hist["status"] == "completed" for hist in archived_task["status_history"]))

    def test_discard_task_archives_task(self):
        task_id = self_add_sample_task("Task to discard")
        mazkir.discard_task(self.user_data, {"task_id": task_id}, user_id_for_save=self.user_id)
        
        self.assertEqual(len(self.user_data["tasks"]), 0)
        self.assertEqual(len(self.user_data["archived_tasks"]), 1)
        archived_task = self.user_data["archived_tasks"][0]
        self.assertEqual(archived_task["id"], task_id)
        self.assertEqual(archived_task["status"], "discarded")
        self.assertTrue(any(hist["status"] == "discarded" for hist in archived_task["status_history"]))

    def test_archive_limit_fifo(self):
        # Add 105 tasks and complete them
        task_ids = []
        for i in range(105):
            task_ids.append(self._add_sample_task(f"Archive test task {i}"))
        
        for i, task_id in enumerate(task_ids):
            # Alternate between completed and discarded to test both
            status_to_set = "completed" if i % 2 == 0 else "discarded"
            mazkir.update_task_status(self.user_data, {"task_id": task_id, "status": status_to_set}, user_id_for_save=self.user_id)

        self.assertEqual(len(self.user_data["archived_tasks"]), 100, "Archived tasks should be capped at 100.")
        # The first 5 tasks added (task_ids[0] to task_ids[4]) should be gone.
        # The oldest remaining archived task should be task_ids[5].
        self.assertEqual(self.user_data["archived_tasks"][-1]["id"], task_ids[5], "Oldest tasks should be removed (FIFO).")
        self.assertEqual(self.user_data["archived_tasks"][0]["id"], task_ids[104], "Newest archived task should be at the start.")

    # --- Reminder Setting Tests ---
    def test_set_reminder_specific_time_valid(self):
        task_id = self._add_sample_task("Reminder specific time")
        reminder_time = (datetime.now() + timedelta(days=1)).isoformat()
        details = {"time": reminder_time}
        result = mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "specific_time", "details": details}, user_id_for_save=self.user_id)
        
        self.assertTrue(result["success"])
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id)
        self.assertEqual(task["reminder_settings"]["type"], "specific_time")
        self.assertEqual(task["reminder_settings"]["time"], reminder_time)

    def test_set_reminder_daily_valid(self):
        task_id = self._add_sample_task("Reminder daily")
        details = {"time_of_day": "09:00"}
        result = mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "daily", "details": details}, user_id_for_save=self.user_id)
        self.assertTrue(result["success"])
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id)
        self.assertEqual(task["reminder_settings"]["type"], "daily")
        self.assertEqual(task["reminder_settings"]["time_of_day"], "09:00")

    def test_set_reminder_interval_valid(self):
        task_id = self._add_sample_task("Reminder interval")
        details = {"hours": 5}
        result = mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "interval", "details": details}, user_id_for_save=self.user_id)
        self.assertTrue(result["success"])
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id)
        self.assertEqual(task["reminder_settings"]["type"], "interval")
        self.assertEqual(task["reminder_settings"]["hours"], 5)
        self.assertIn("last_reminded_at", task["reminder_settings"]) # Should be set to now

    def test_set_reminder_invalid_task_id(self):
        with self.assertRaises(mazkir.ToolExecutionError) as context:
            mazkir.set_reminder(self.user_data, {"task_id": 999, "reminder_type": "daily", "details": {"time_of_day": "10:00"}}, user_id_for_save=self.user_id)
        self.assertIn("Task with id 999 not found", str(context.exception))

    def test_set_reminder_invalid_type(self):
        task_id = self._add_sample_task("Invalid reminder type test")
        with self.assertRaises(mazkir.ToolExecutionError) as context:
            mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "weekly", "details": {}}, user_id_for_save=self.user_id)
        self.assertIn("Invalid reminder_type: weekly", str(context.exception))

    def test_get_reminders_single_task(self):
        task_id = self._add_sample_task("Task with reminder")
        reminder_time = (datetime.now() + timedelta(days=2)).isoformat()
        mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "specific_time", "details": {"time": reminder_time}}, user_id_for_save=self.user_id)
        
        reminders = mazkir.get_reminders(self.user_data, {"task_id": task_id})
        self.assertEqual(reminders["type"], "specific_time")
        self.assertEqual(reminders["time"], reminder_time)

    def test_get_reminders_all_tasks(self):
        task1_id = self._add_sample_task("Task 1 for get all")
        task2_id = self._add_sample_task("Task 2 for get all")
        mazkir.set_reminder(self.user_data, {"task_id": task1_id, "reminder_type": "daily", "details": {"time_of_day": "11:00"}}, user_id_for_save=self.user_id)
        mazkir.set_reminder(self.user_data, {"task_id": task2_id, "reminder_type": "interval", "details": {"hours": 3}}, user_id_for_save=self.user_id)

        all_reminders = mazkir.get_reminders(self.user_data)
        self.assertEqual(len(all_reminders), 2)
        self.assertTrue(any(r["task_id"] == task1_id and r["reminder_settings"]["type"] == "daily" for r in all_reminders))
        self.assertTrue(any(r["task_id"] == task2_id and r["reminder_settings"]["type"] == "interval" for r in all_reminders))

    # --- Reminder Logic Tests (check_due_reminders) ---
    @patch('mazkir.datetime') # Patch datetime within mazkir module
    def test_check_due_reminders_specific_time(self, mock_dt):
        task_id = self._add_sample_task("Specific time due test")
        
        # Reminder for 2 hours from "now"
        now_time = datetime(2023, 1, 1, 10, 0, 0) # Our "current" time
        reminder_set_time = (now_time + timedelta(hours=2)).isoformat() # Due at 12:00
        mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "specific_time", "details": {"time": reminder_set_time}}, user_id_for_save=self.user_id)

        # 1. Time is before reminder time
        mock_dt.now.return_value = now_time # Current time is 10:00
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 0, "Should not be due yet.")
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id)
        self.assertFalse(task["reminder_settings"].get("specific_time_triggered"))

        # 2. Time is after reminder time
        mock_dt.now.return_value = now_time + timedelta(hours=3) # Current time is 13:00 (due)
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 1)
        self.assertIn(f"Task '{task['description']}' was due at {reminder_set_time}", due_messages[0])
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id) # Re-fetch task
        self.assertTrue(task["reminder_settings"].get("specific_time_triggered"))

        # 3. Check again, should not re-trigger
        mock_dt.now.return_value = now_time + timedelta(hours=4) # Current time is 14:00
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 0, "Should not re-trigger specific time reminder.")

    @patch('mazkir.datetime')
    def test_check_due_reminders_daily(self, mock_dt):
        task_id = self._add_sample_task("Daily due test")
        mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "daily", "details": {"time_of_day": "09:30"}}, user_id_for_save=self.user_id)
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id)

        # Day 1, before reminder time
        mock_dt.now.return_value = datetime(2023, 1, 1, 8, 0, 0) # 08:00
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2023-01-01" # For today_date_iso
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 0)
        self.assertNotEqual(task["reminder_settings"].get("last_reminded_daily_at"), "2023-01-01")

        # Day 1, after reminder time
        mock_dt.now.return_value = datetime(2023, 1, 1, 10, 0, 0) # 10:00
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2023-01-01"
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 1)
        self.assertIn("Daily reminder for task 'Daily due test' at 09:30", due_messages[0])
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id) # Re-fetch
        self.assertEqual(task["reminder_settings"].get("last_reminded_daily_at"), "2023-01-01")

        # Day 1, after reminder time, check again (should not re-trigger for same day)
        mock_dt.now.return_value = datetime(2023, 1, 1, 11, 0, 0) # 11:00
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2023-01-01"
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 0)
        
        # Day 2, after reminder time (should trigger again)
        mock_dt.now.return_value = datetime(2023, 1, 2, 10, 0, 0) # Next day, 10:00
        mock_dt.now.return_value.date.return_value.isoformat.return_value = "2023-01-02"
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 1)
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id) # Re-fetch
        self.assertEqual(task["reminder_settings"].get("last_reminded_daily_at"), "2023-01-02")

    @patch('mazkir.datetime')
    def test_check_due_reminders_interval(self, mock_dt):
        task_id = self._add_sample_task("Interval due test")
        
        # Set initial time for "last_reminded_at" to be when reminder is set
        initial_set_time = datetime(2023, 1, 1, 10, 0, 0)
        mock_dt.now.return_value = initial_set_time
        
        mazkir.set_reminder(self.user_data, {"task_id": task_id, "reminder_type": "interval", "details": {"hours": 3}}, user_id_for_save=self.user_id)
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id)
        self.assertEqual(task["reminder_settings"]["last_reminded_at"], initial_set_time.isoformat())

        # 1. Time is less than interval
        mock_dt.now.return_value = initial_set_time + timedelta(hours=2) # Current time 12:00 (Interval 3h, so not due)
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 0)

        # 2. Time is more than interval
        mock_dt.now.return_value = initial_set_time + timedelta(hours=3, minutes=30) # Current time 13:30 (Due)
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 1)
        self.assertIn("Interval reminder for task 'Interval due test' (every 3 hours)", due_messages[0])
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id) # Re-fetch
        self.assertEqual(task["reminder_settings"]["last_reminded_at"], (initial_set_time + timedelta(hours=3, minutes=30)).isoformat())
        
        # 3. Check again after another interval (based on new last_reminded_at)
        new_last_reminded_time = datetime.fromisoformat(task["reminder_settings"]["last_reminded_at"])
        mock_dt.now.return_value = new_last_reminded_time + timedelta(hours=3, minutes=1) # Due again
        due_messages = mazkir.check_due_reminders(self.user_data)
        self.assertEqual(len(due_messages), 1)
        task = next(t for t in self.user_data["tasks"] if t["id"] == task_id) # Re-fetch
        self.assertEqual(task["reminder_settings"]["last_reminded_at"], (new_last_reminded_time + timedelta(hours=3, minutes=1)).isoformat())


if __name__ == '__main__':
    unittest.main()
