### Mazkir: Your Personal Task Assistant

**Mazkir** is a Python-based personal task assistant that uses a Large Language Model (LLM) to help you manage your tasks. It can be accessed via Telegram or a command-line interface (CLI). Each user's tasks are stored separately.

### Features
*   Add, view, and update tasks using natural language.
*   Interface via Telegram or CLI.
*   User-specific task lists.
*   Modular handler design for potential future platform integrations.
*   Powered by LiteLLM, supporting various LLM providers.

### Project Structure
```
.
├── .env                # For environment variables (you need to create this)
├── mazkir.py           # Core logic for task processing & main entry point for Telegram bot
├── cli_handler.py      # Handles Command Line Interface interaction
├── telegram_handler.py # Handles Telegram bot interaction
├── user_handler_interface.py # Defines the interface for handlers
├── mazkir_users_memory.json # Stores user-specific tasks and preferences (created automatically)
├── requirements.txt    # Python dependencies
├── test_mazkir.py      # Test file (may need updates)
├── plan.md             # Original planning document
└── README.md           # This file
```

### Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Create a Python Virtual Environment:**
    It's recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    Create a file named `.env` in the root of the project. Add the following variables, replacing the placeholder values with your actual credentials:

    ```env
    # --- Telegram Configuration ---
    TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"

    # --- LLM Configuration (using LiteLLM) ---
    # Example for OpenAI:
    OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
    # MAZKIR_LLM_MODEL="gpt-3.5-turbo" # Optional: defaults to a Gemini model in mazkir.py, but you can override

    # Example for Anthropic:
    # ANTHROPIC_API_KEY="YOUR_ANTHROPIC_API_KEY"
    # MAZKIR_LLM_MODEL="claude-2"

    # Example for Google Vertex AI (Gemini)
    # Ensure you are authenticated with gcloud and have the necessary permissions.
    # GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json" # Only if not running in a GCP env
    # MAZKIR_LLM_MODEL="vertex_ai/gemini-pro" # Or other Gemini models

    # --- LiteLLM General Settings (Optional) ---
    # LITELLM_LOG="INFO" # To see LiteLLM logs
    ```
    *   **`TELEGRAM_BOT_TOKEN`**: Your token for the Telegram bot from BotFather.
    *   **LLM API Keys**: Provide the API key for your chosen LLM provider (e.g., `OPENAI_API_KEY`). `mazkir.py` defaults to a Gemini model (`vertex_ai/gemini-1.5-flash-preview-04-17` as of last check in the code, but this might change, or you can set `MAZKIR_LLM_MODEL` in `.env`). LiteLLM will automatically pick up environment variables for many providers (OpenAI, Cohere, Anthropic, etc.). For Google Vertex AI, ensure your environment is authenticated (`gcloud auth application-default login`) or provide `GOOGLE_APPLICATION_CREDENTIALS`.

### Running the Application

**1. Telegram Bot:**
   To start the Telegram bot, run:
   ```bash
   python mazkir.py
   ```
   This will start the Telegram handler, and you can interact with your bot on Telegram. Each Telegram user will have their own separate task list.

**2. Command-Line Interface (CLI):**
   To use the CLI version (tasks will be stored for a generic "cli_user"):
   ```bash
   python cli_handler.py
   ```
   This will start an interactive session in your terminal.

### How it Works
The application uses an LLM to understand your requests. It can perform actions like:
*   `get_tasks`: To retrieve your current tasks.
*   `add_task`: To add a new task to your list.
*   `update_task_status`: To change the status of an existing task (e.g., to "completed").

User data is stored in `mazkir_users_memory.json`, with each user (identified by their Telegram ID or "cli_user" for the command line) having a separate section for their tasks and preferences.

The core task processing logic is in `mazkir.py`. Different user interaction methods (Telegram, CLI) are implemented as "handlers" that use this core logic.

### Development Notes
*   The system is designed to be modular. You can create new handlers (e.g., for WhatsApp, Discord) by implementing the `BaseHandler` interface from `user_handler_interface.py`.
*   The LLM interaction uses LiteLLM, making it easy to switch between different LLM providers.
*   Tracing with Arize Phoenix was previously included but has been commented out in `mazkir.py` for simplification. You can uncomment it if needed.
*   `test_mazkir.py` contains tests, which may need updating to reflect the latest changes to the multi-user and handler-based architecture.
