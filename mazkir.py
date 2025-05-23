import os
import openai
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Constants ---
DEFAULT_LLM_MODEL = "text-davinci-003"
REMINDER_FILE = "reminders.txt" # Default reminder file name

# --- Error Classes ---
class LLMError(Exception):
    """Custom exception for LLM related errors."""
    pass

class FileProcessingError(Exception):
    """Custom exception for file processing errors."""
    pass

# --- Core Functions ---
def get_reminder_summary(text: str, model_name: str) -> str | None:
    """
    Generates a summary for a given text using a placeholder for an LLM.
    Includes basic error handling for the (simulated) LLM interaction.
    """
    logging.info(f"Attempting to summarize using model {model_name}: '{text[:50]}...'")
    if not text:
        logging.error("No text provided for summarization.")
        return None

    # Simulate LLM API call and potential errors
    try:
        # In a real scenario, this is where you would call openai.Completion.create() or similar
        # For example:
        # if not openai.api_key:
        #     raise LLMError("OpenAI API key is not set. Cannot make API call.")
        # response = openai.Completion.create(engine=model_name, prompt=text, max_tokens=50)
        # summary = response.choices[0].text.strip()
        
        # Placeholder simulation
        if "fail_llm" in text.lower(): # Simulate a failure condition
            raise LLMError(f"Simulated LLM API error for model {model_name} with input: {text[:20]}")
        
        summary = f"Summary of '{text[:30]}...' (model: {model_name})"
        logging.info(f"Generated summary: {summary}")
        return summary
    except openai.error.OpenAIError as e: # Example of catching specific OpenAI errors
        logging.error(f"OpenAI API error during summarization: {e}")
        raise LLMError(f"OpenAI API error: {e}") from e
    except Exception as e:
        logging.error(f"Unexpected error during summarization: {e}")
        # For a real LLM call, you might want to raise LLMError here too.
        # For this placeholder, we'll return None for unexpected errors.
        return None


def read_reminders(filepath: str) -> list[str] | None:
    """
    Reads reminders from a specified file.
    Includes error handling for file operations.
    """
    logging.info(f"Attempting to read reminders from: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        if not content.strip():
            logging.warning(f"Reminder file '{filepath}' is empty.")
            return []
        reminders = [line for line in content.splitlines() if line.strip()]
        logging.info(f"Successfully read {len(reminders)} non-empty reminders from '{filepath}'.")
        return reminders
    except FileNotFoundError:
        logging.error(f"Reminder file not found: {filepath}")
        raise FileProcessingError(f"File not found: {filepath}")
    except IOError as e:
        logging.error(f"IOError reading reminder file {filepath}: {e}")
        raise FileProcessingError(f"IOError reading file {filepath}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while reading {filepath}: {e}")
        raise FileProcessingError(f"Unexpected error reading file {filepath}: {e}")


def main():
    """
    Main function to orchestrate the Mazkir script.
    """
    logging.info("Starting Mazkir script...")

    # --- Configuration ---
    openai_api_key = os.getenv("OPENAI_API_KEY")
    llm_model_name = os.getenv("MAZKIR_LLM_MODEL", DEFAULT_LLM_MODEL)
    reminder_filepath = os.getenv("MAZKIR_REMINDER_FILE", REMINDER_FILE)

    logging.info(f"Using LLM model: {llm_model_name}")
    logging.info(f"Reminder file path: {reminder_filepath}")

    if not openai_api_key:
        logging.warning(
            "OPENAI_API_KEY environment variable not set. "
            "Real LLM calls will fail. Placeholder functionality might still work."
        )
    else:
        openai.api_key = openai_api_key
        logging.info("OPENAI_API_KEY configured.")

    # --- Create a dummy reminders.txt for testing/demonstration ---
    try:
        logging.info(f"Attempting to create/update dummy reminder file: {reminder_filepath}")
        with open(reminder_filepath, "w", encoding='utf-8') as f:
            f.write("Remember to buy milk\n")
            f.write("Meeting with team at 3 PM\n")
            f.write("Call John about the project update\n")
            f.write("This is a reminder to fail_llm call for testing\n") # For testing LLM error
            f.write("\n") # Test empty line handling
            f.write("    Another reminder with leading spaces    \n")
        logging.info(f"Successfully created/updated dummy reminder file: {reminder_filepath}")
    except IOError as e:
        logging.error(f"Fatal: Could not write dummy reminder file '{reminder_filepath}': {e}. Exiting.")
        return # Exit if we can't create the dummy file for this example

    # --- Main Logic ---
    try:
        reminders = read_reminders(reminder_filepath)

        if reminders is None: # Indicates a fatal error from read_reminders already logged
            logging.error("Could not read reminders. Exiting.")
            return
        
        if not reminders: # Empty list
            logging.info("No reminders to process.")
        else:
            processed_summaries = 0
            for i, reminder_text in enumerate(reminders):
                try:
                    logging.info(f"Processing reminder #{i+1}: '{reminder_text}'")
                    summary = get_reminder_summary(reminder_text, model_name=llm_model_name)
                    if summary:
                        # In a real script, you might do something with the summary
                        # like sending it as a notification, saving it, etc.
                        logging.info(f"Successfully processed reminder #{i+1}. Summary: {summary}")
                        processed_summaries +=1
                    else:
                        logging.warning(f"Failed to get summary for reminder #{i+1}: '{reminder_text}'")
                except LLMError as e: # Catch errors from get_reminder_summary
                    logging.error(f"LLMError while processing reminder #{i+1} ('{reminder_text}'): {e}")
                except Exception as e: # Catch any other unexpected error for a specific reminder
                    logging.error(f"Unexpected error processing reminder #{i+1} ('{reminder_text}'): {e}")
            logging.info(f"Processed {processed_summaries}/{len(reminders)} reminders.")

    except FileProcessingError as e:
        logging.critical(f"A file processing error occurred: {e}. Mazkir cannot continue.")
    except Exception as e: # Catch-all for any other unexpected errors in main
        logging.critical(f"An unexpected critical error occurred in main: {e}", exc_info=True)
    finally:
        logging.info("Mazkir script finished.")

if __name__ == "__main__":
    main()
