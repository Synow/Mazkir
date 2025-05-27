import logging
from typing import Callable, Any
from datetime import datetime

from user_handler_interface import BaseHandler
# Actual imports from mazkir.py (assuming mazkir.py is in PYTHONPATH)
from mazkir import (
    load_memory, 
    save_memory, 
    add_task, 
    MemoryOperationError, 
    ToolExecutionError, 
    logger as mazkir_logger, # Use Mazkir's configured logger
    MAZKIR_MEMORY_FILE as DEFAULT_MAZKIR_MEMORY_FILE, # Default if not in config
    MAZKIR_LLM_MODEL as DEFAULT_MAZKIR_LLM_MODEL # Default if not in config
)

# Use Mazkir's logger
logger = mazkir_logger


class CliHandler(BaseHandler):
    """
    Command Line Interface handler for Mazkir.
    """

    def __init__(self, 
                 process_user_input_func: Callable[[str, str], str],
                 mazkir_instance_config: dict = None): # mazkir_instance_config can hold MAZKIR_LLM_MODEL, MAZKIR_MEMORY_FILE
        super().__init__(process_user_input_func)
        self.cli_user_id = "cli_user" # Default user for CLI
        
        # Use defaults from mazkir.py if not provided in mazkir_instance_config
        if mazkir_instance_config:
            self.mazkir_memory_file = mazkir_instance_config.get("MAZKIR_MEMORY_FILE", DEFAULT_MAZKIR_MEMORY_FILE)
            self.mazkir_llm_model = mazkir_instance_config.get("MAZKIR_LLM_MODEL", DEFAULT_MAZKIR_LLM_MODEL)
        else:
            self.mazkir_memory_file = DEFAULT_MAZKIR_MEMORY_FILE
            self.mazkir_llm_model = DEFAULT_MAZKIR_LLM_MODEL
        
        # These are the actual functions from mazkir.py
        self._load_memory = load_memory
        self._save_memory = save_memory
        self._add_task = add_task


    def get_user_identifier(self, event: Any = None) -> str:
        """
        Returns the predefined user identifier for the CLI.
        Optionally, could be enhanced to ask for a username.
        """
        # For CLI, the event is not really used, user is fixed or pre-determined.
        return self.cli_user_id

    async def send_message(self, user_id: str, message: str) -> None:
        """
        Sends a message to the CLI user (prints to console).
        Marked async to match the base class, but print is synchronous.
        """
        if user_id == self.cli_user_id: # Ensure message is for the correct CLI user
            print(f"Assistant: {message}")
        else:
            # This case should ideally not happen if user_id is correctly managed.
            logger.warning(f"CliHandler received send_message for unexpected user_id: {user_id}")

    def send_proactive_message(self, user_id: str, message: str) -> bool:
        """
        Sends a proactive message to the CLI user (prints to console).
        Matches the abstract method, but print is synchronous.
        """
        if user_id == self.cli_user_id:
            print(f"\n[PROACTIVE MESSAGE for User {user_id} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]: {message}")
            print(f"You: ", end="") # Print the prompt again for seamless interaction
            return True
        logger.warning(f"CliHandler received send_proactive_message for unexpected user_id: {user_id}")
        return False

    def start(self) -> None:
        """
        Starts the CLI interaction loop.
        This method incorporates the logic from the original run_interactive_mode.
        """
        logger.info(f"Starting Mazkir CLI Handler. Model: {self.mazkir_llm_model}, Memory File: {self.mazkir_memory_file}")
        
        user_id = self.get_user_identifier() # Should be self.cli_user_id

        try:
            user_data = self._load_memory(user_id, filepath=self.mazkir_memory_file)
            logger.info(f"Successfully loaded data for '{user_id}' in CLI mode.")
        except MemoryOperationError as e:
            logger.critical(f"Failed to load initial memory for '{user_id}': {e}. CLI handler cannot start.", exc_info=True)
            print(f"Fatal Error: Could not load memory for CLI user. Check logs. Exiting.")
            return
        except Exception as e_global:
            logger.critical(f"An unexpected error occurred loading memory for '{user_id}': {e_global}. CLI handler cannot start.", exc_info=True)
            print(f"Fatal Error: An unexpected error occurred loading memory for CLI user. Exiting.")
            return

        if not user_data.get("tasks"):
            logger.info(f"User '{user_id}' has no tasks. Adding a sample task for demonstration.")
            try:
                self._add_task(user_data,
                               {"description": "Review Mazkir setup via CLI", "due_date": datetime.now().strftime("%Y-%m-%d")},
                               user_id_for_save=user_id) # This will also call save_memory
            except (MemoryOperationError, ToolExecutionError) as e:
                logger.error(f"Failed to add initial sample task for user '{user_id}' during CLI setup: {e}", exc_info=True)
                print(f"Notice: Could not add a sample task for user '{user_id}' during setup. Continuing.")

        print("\nMazkir CLI Assistant")
        print("Type 'exit' or 'quit' to end the session.")
        print("------------------------------------")

        while True:
            try:
                user_input_text = input("You: ").strip()

                if user_input_text.lower() in ['exit', 'quit']:
                    logger.info(f"User '{user_id}' initiated exit from CLI loop.")
                    # The send_message method is async, so if we were in an async context we'd await.
                    # For CLI, printing directly is fine.
                    print("Assistant: Goodbye!") 
                    break
                
                if not user_input_text:
                    continue

                # Call the core processing function passed during initialization
                assistant_response = self.process_user_input_func(user_id, user_input_text)

                # Use the send_message method (even though it's simple for CLI)
                # In a truly async application, one might `asyncio.run(self.send_message(...))` or handle it differently.
                # For this synchronous start() loop, direct print or a synchronous wrapper is okay.
                # To strictly adhere to the async signature for this example, we'll just call it.
                # In a real async app, start() itself would be async.
                print(f"Assistant: {assistant_response}") # Direct print for simplicity here.
                                                        # If send_message had complex sync logic, we'd call it.

            except KeyboardInterrupt:
                logger.info(f"User '{user_id}' interrupted session with Ctrl+C.")
                print("\nAssistant: Session interrupted. Type 'exit' or 'quit' to leave.")
            except MemoryOperationError as e:
                logger.error(f"A memory operation error occurred during CLI processing: {e}", exc_info=True)
                print(f"Assistant: Error: A problem occurred with memory storage: {e}")
            except ToolExecutionError as e:
                logger.error(f"A tool execution error occurred: {e}", exc_info=True)
                print(f"Assistant: Error: A problem occurred while performing an action: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred in the CLI loop: {e}", exc_info=True)
                print(f"Assistant: Error: An unexpected issue occurred: {e}")

        logger.info(f"CLI session for user '{user_id}' ended.")
        try:
            logger.info(f"Attempting final save of memory for user '{user_id}' on exit from CLI mode.")
            self._save_memory(user_id, user_data, filepath=self.mazkir_memory_file)
        except MemoryOperationError as e:
            logger.error(f"Failed to save memory for user '{user_id}' on exiting CLI mode: {e}", exc_info=True)
            print(f"Warning: Could not save memory for user '{user_id}' on exit: {e}")

# Example of how it might be instantiated and run (this would typically be in a main script)
if __name__ == '__main__':
    # This __main__ block is for testing CliHandler independently or as a separate entry point.
    # It now correctly imports process_user_input from mazkir.
    
    # Ensure mazkir.py is in PYTHONPATH or in the same directory for this to work.
    try:
        from mazkir import process_user_input, MAZKIR_MEMORY_FILE, MAZKIR_LLM_MODEL
    except ImportError:
        logger.critical("Failed to import components from mazkir.py. Ensure it is in PYTHONPATH.")
        # Define mock_process_user_input for the handler to be instantiated for basic testing
        def process_user_input(user_id: str, user_input_text: str) -> str: # type: ignore
            logger.error("Using MOCK process_user_input due to import error from mazkir.py")
            return "Error: Mazkir core function not loaded."
        # Define MAZKIR_MEMORY_FILE and MAZKIR_LLM_MODEL if not imported
        MAZKIR_MEMORY_FILE = "mock_mazkir_memory.json" # type: ignore
        MAZKIR_LLM_MODEL = "mock_llm_model" # type: ignore


    # Configure basic logging IF mazkir_logger wasn't successfully imported and configured
    # Typically, mazkir.py (which configures mazkir_logger) should handle this.
    if 'mazkir_logger' not in globals() or not mazkir_logger.handlers:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger.warning("CLI Handler's __main__ using fallback basicConfig for logging.")
    
    logger.info("Starting CLI Handler example from cli_handler.py's __main__.")
    
    # Config for CliHandler, using values imported from mazkir.py
    config = {
        "MAZKIR_MEMORY_FILE": MAZKIR_MEMORY_FILE, 
        "MAZKIR_LLM_MODEL": MAZKIR_LLM_MODEL    
    }

    cli_handler_instance = CliHandler(process_user_input_func=process_user_input, mazkir_instance_config=config)
    cli_handler_instance.start()
    
    logger.info("CLI Handler example finished.")
