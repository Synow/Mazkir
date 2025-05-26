**Note: The core task management, archiving, and reminder features described in this plan have been implemented in `mazkir.py` as of [current date/version, placeholder for actual date]. This document reflects the initial design and considerations. For the latest implementation details, please refer to the `mazkir.py` script and its associated tests.**

## Overview of the Mazkir System

Mazkir is a local personal assistant that uses a Large Language Model (LLM) to help manage and organize tasks. It is designed as an LLM-based agent that can **reason, plan, and use tools (in this case, a local memory file)** to keep track of tasks and user preferences. This aligns with the emerging trend of AI assistants becoming proactive, context-aware agents that combine LLM capabilities with reasoning, planning, tool calls, and memory. The core components of Mazkir include:

* **LLM (via LiteLLM):** The “brain” of the assistant, providing natural language understanding and generation.
* **Tool Interface (Memory File Access):** A mechanism that allows the LLM to read/write a local plain-text file as its persistent **memory** for tasks, history, and preferences.
* **Persistent Memory Store:** A local file (e.g. JSON) on the user’s machine where Mazkir stores the to-do list, task history, user preferences (tone, reminder frequency, etc.), and internal metadata. This provides long-term state and personalization beyond a single LLM session.
* **Local Execution:** The entire system runs on the user’s machine, ensuring the user’s data (tasks and notes) remains local. Only LLM API calls go out to the cloud (unless a local model is used), and all tool actions (file reads/writes) occur locally.

In essence, Mazkir behaves like a specialized LLM agent that can remember past tasks and act on them. It receives user instructions (e.g. *“add a new task”* or *“what’s on my to-do list?”*), possibly invokes the memory tool to fulfill the request, and then responds in natural language. The design emphasizes privacy (data stored locally), personalization (user-specific tone and preferences), and not relying on heavy frameworks – the implementation is in pure Python for clarity and control.

## Tool Access: MCP Server vs. Custom Integration

A key design decision is how the LLM will interact with the external tool (the local memory file). We consider two approaches: using the **Model Context Protocol (MCP)** and using a **direct custom tool invocation** mechanism. Both approaches enable the LLM to perform read/write operations on the file, but they differ in architecture and trade-offs.

**Using MCP (Model Context Protocol):** MCP is an open standard (essentially JSON-RPC over HTTP) for connecting AI agents to tools and data sources. In this approach, we would run a lightweight **MCP server** that exposes file operations (read, write, append, etc.) via a standardized interface. The LLM (via an MCP client) can call the server’s APIs to interact with the file. Notably, the MCP project provides pre-built servers for common capabilities; for example, a **Filesystem** server offers secure file operations with configurable access controls. Mazkir could leverage such a server (pointing it to the allowed task file directory) or a custom MCP server implemented in Python.

* **Pros (MCP approach):**

  * *Standardized interface:* MCP provides a universal protocol for tool use, replacing fragmented custom integrations with a single standard. This means any MCP-compatible LLM client can connect to any MCP server tool. Tool builders can create reusable MCP servers, and agent developers can leverage them without reimplementing functionality.
  * *Separation of concerns:* The task logic (file read/write) is handled by the MCP server, decoupled from the agent code. This fosters modularity and reuse – e.g., you could swap in a different MCP server (for a database, cloud storage, etc.) with minimal changes.
  * *Security and control:* MCP servers can enforce access policies. For instance, the filesystem MCP server can be configured to restrict which directory or files are accessible. This reduces the risk of the LLM reading or writing beyond its scope. MCP’s design is being adopted with security in mind; Windows 11 is even previewing native support for MCP as a secure way for agents to take actions. Using MCP means embracing an ecosystem that is actively being secured and standardized for agent-tool interactions.
  * *Community and future-proofing:* Since Anthropic open-sourced MCP in late 2024, dozens of MCP servers have been built across domains (GitHub, Slack, Google Drive, etc.). By using MCP, Mazkir could in the future tap into this growing ecosystem (for example, adding a calendar MCP server for scheduling) without bespoke coding.

* **Cons (MCP approach):**

  * *Additional infrastructure:* Running an MCP server introduces an extra component. The user would need to install or run the server package (which might be a Node.js, Go, or Python program, depending on the implementation). This adds complexity to the setup. For example, one guide shows compiling a TypeScript MCP server to Node and running it as a separate process – a higher barrier than a single Python script.
  * *Overhead and latency:* Communication happens over HTTP JSON-RPC. While generally lightweight, it is still slightly slower and more resource-intensive than a direct function call in Python. For frequent small operations (like reading/writing a file), this overhead might be noticeable.
  * *Early technology considerations:* MCP is fairly new (open-sourced in late 2024) and still evolving. Early users noted some rough edges and “flakiness” in examples. Documentation and community support, while growing, might not be as extensive as more mature direct methods. In contrast, direct function calling in LLM APIs is a well-trodden path.
  * *Security configuration:* Misconfiguring an MCP server could expose vulnerabilities – for instance, if it’s not properly restricted to localhost or allowed paths. The flexibility of MCP means developers must carefully secure each server (prompt injection or malicious inputs could otherwise exploit the tool). Essentially, with great power comes great responsibility in locking down the MCP server’s capabilities.

**Using a Custom Direct Tool Invocation:** This approach foregoes the MCP layer and instead implements tool usage logic within our Python code (the “host” application). We manually prompt the LLM about the available tool (the memory file) and handle the LLM’s tool requests ourselves. This can be done by adopting a pattern like ReAct (Reason+Act) or utilizing the LLM’s native function-calling API if available. In practice, we instruct the model (via the prompt) on how to ask for a file read/write, then parse the model’s response. For example, Mazkir’s prompt can say: *“You have access to a memory file. To use it, output a JSON like `{"action": "add_task", "task": "..."}.`”* The Python code will detect this JSON, perform the action on the file, and then provide the result back to the LLM before getting the final answer. This loop continues until the model produces a final answer to the user, similar to how ReAct agents alternate between reasoning and acting.

* **Pros (custom approach):**

  * *Simplicity for a narrow scope:* For a single-user, single-tool scenario (just managing a local task file), a custom approach is straightforward. We can directly call Python functions to read/write the file without running an HTTP server or adhering to an external schema. The entire agent logic resides in one process, making it easier to understand and debug for this specific use case.
  * *No additional dependencies:* The solution remains **pure Python**, as requested, using only standard libraries (e.g. `json` for the file) and the LiteLLM SDK for LLM calls. We avoid heavy agent frameworks or servers, reducing the maintenance burden. The code can be easily modified by the user since it’s all in one place.
  * *Leverage model-specific features:* If using a cloud LLM like OpenAI’s GPT-4 or Anthropic’s Claude, we can take advantage of built-in function calling or tool-use formats. For instance, OpenAI’s API allows defining functions that the model can call (with the API returning a structured function call object). This can eliminate parsing errors and let the model handle tool decisions autonomously. Our custom integration could simply register a `read_file` and `write_file` function via the API and let the model invoke them as needed – making tool use robust and native when supported by the model. (LiteLLM can interface with such APIs while maintaining a unified interface.)
  * *Performance:* Direct function calls in-process will generally be faster than an HTTP round-trip. Also, we can optimize when to include memory context. For example, if the user asks *“List my tasks”*, we might feed the tasks directly to the prompt (avoiding an extra LLM loop). If the user says *“Add a task”*, we can proceed to tool usage. This fine-grained control can save tokens and latency in simple cases.

* **Cons (custom approach):**

  * *Lack of standardization:* A one-off solution means if we later wanted to integrate another tool or share Mazkir’s capabilities with another system, we’d have to write new code. There is no plug-and-play ability like MCP’s standardized servers. Essentially, the approach might not scale elegantly beyond this specific project – each new integration (say adding a calendar or email tool) would require custom coding.
  * *Manual parsing and potential errors:* If not using a model’s structured function calling, we rely on prompt instructions and parsing the model’s text output. LLMs can sometimes produce outputs that deviate from the expected format or contain partial answers mixed with tool calls. This requires careful prompt design and error handling. Our agent needs to handle cases like the model not obeying the format, or gracefully recover from a failed tool action. These are solvable problems, but the onus is on the developer to implement robust parsing/validation.
  * *Security & safety checks:* In a custom approach, we must manually enforce any constraints. For example, we should ensure the file path the model provides is exactly the allowed memory file (to prevent the model from reading arbitrary files on the system). We also need to guard against prompt-injection attacks in user input that might trick the agent into revealing the memory or performing unintended actions. Established frameworks or MCP might eventually provide standardized mitigations, whereas a custom solution means we must stay vigilant and update the agent as new best practices emerge.
  * *Reinventing the wheel:* Tool use and long-term memory management are active areas of development in 2025. By going custom, we might miss out on some advanced patterns or optimizations that frameworks provide (e.g., automatic context management, vector-store memory, etc.). We have to implement features like summarizing the task list if it grows too large for the prompt, on our own. This is acceptable for Mazkir’s scope now, but could become a maintenance challenge as the assistant’s knowledge grows.

In summary, **MCP** is ideal if we anticipate using a broad ecosystem of tools or want a future-proof, standardized agent. It shines in multi-tool scenarios and when security and interoperability are top priorities. The **custom approach** is perfectly suitable for a self-contained personal assistant, keeping things simple and entirely under the user’s control. For Mazkir, we can actually start with the custom approach (quick to implement and iterate on), and keep the door open to migrate to MCP later if needed. The two approaches are not mutually exclusive – for instance, one could implement a minimal MCP server that wraps our file read/write functions if we ever want to expose them in a standard way. But given the requirements (pure Python, local execution, minimal deps), the custom in-process tool invocation is a pragmatic choice for the initial design.

## Memory Persistence and File Design

Long-term **memory** is what allows Mazkir to maintain context across sessions and provide personalized assistance. In LLM applications, memory can refer to any mechanism for storing information between interactions. Here, we specifically need persistent storage for the to-do list and related data. By using a local file, Mazkir achieves **persisted state** – data that lives outside the LLM’s ephemeral conversation context and remains available even after a restart. This persisted memory is essential for a personal task manager; without it, the assistant would forget tasks or settings once the chat context resets or the program stops.

We recommend structuring the memory file in a **simple, structured text format** (e.g. JSON) for easy parsing and editing. JSON strikes a good balance: it’s human-readable (the user can open the file in a text editor to inspect or manually tweak data if needed) and machine-friendly (Python can parse JSON into data structures with one call). Many DIY personal assistant projects start with a JSON file as a lightweight database, migrating to a more complex database only if needed. Given the scope of Mazkir (a single user’s tasks and preferences), a JSON file is sufficient and incurs minimal overhead.

**Proposed file structure (`mazkir_memory.json`):**

```json
{
  "tasks": [
    { "id": 1, "description": "Buy groceries", "status": "pending", "created": "2025-05-22T14:00:00" },
    { "id": 2, "description": "Finish project report", "status": "done", "completed": "2025-05-20T18:30:00" }
  ],
  "preferences": {
    "tone": "friendly",
    "reminder_frequency": "daily"
  },
  "history": [
    { "time": "2025-05-20T18:31:00", "action": "completed_task", "task_id": 2 }
  ],
  "metadata": {
    "last_task_id": 2
  }
}
```

Let's break down the components:

* **`tasks`:** A list of task objects. Each task has an `id` (unique identifier), a text `description`, and a `status` (e.g. "pending" or "done"). We can also store timestamps like when the task was created or completed, and any other attributes (priority, tags, due date) as needed. Using numeric IDs is helpful for referencing tasks (e.g., “mark task 3 as done”) without relying on full text matches. The assistant can refer to task IDs internally.
* **`preferences`:** A dictionary of user preferences and settings. For Mazkir, this could include the desired communication `tone` (casual, formal, humorous, etc.) and `reminder_frequency` (how often the user wants to be reminded or prompted about tasks, e.g. daily, weekly, or “none” if only on-demand). The assistant will use these to adjust its behavior – for example, using more formal language if `tone` is "formal", or deciding whether to proactively say something like “Here’s your daily task update” based on the frequency setting. Storing preferences in the file means they persist and can be adjusted by the user through commands (e.g. "Set my tone to casual") which the assistant would handle by updating this section.
* **`history`:** (Optional) A log of important events or past interactions, such as tasks added or completed, or significant assistant actions. This serves two purposes: (1) it provides an **audit trail** (the user can inspect what was done and when), and (2) it can feed into the LLM’s context if needed to remind it of prior actions. For example, if the user asks “why did you mark task 2 as done?”, Mazkir could consult this history. In practice, this could also record conversation snippets or summaries if we wanted to maintain conversational memory, but for a task list, a simple log of actions suffices.
* **`metadata`:** Miscellaneous internal metadata the system might need. In the example, `last_task_id` is stored to know what the next task ID should be when adding a new task (to avoid collisions). We could also keep other info here, like a pointer to a summary if we implement memory summarization for very long task lists, etc. This section is mainly for the program’s use and less about user queries.

Using JSON makes it easy to load this file into a Python dict and manipulate it. We will load the file at startup (or create it if it doesn’t exist) and write back to it whenever tasks or preferences change. One best practice is to always flush the file to disk after an update (so changes aren’t lost if the program crashes) and possibly to make backup copies in case of corruption.

**Parsing and using the file:** When the LLM needs to access memory, we have two strategies:

1. **Proactive context injection:** For questions like “What tasks do I have?”, the system can pre-load the relevant memory content and include it in the LLM prompt (either as part of the system message or as an assistant observation). This gives the model direct knowledge of tasks without an extra tool call. It’s simple (just reading the file before calling the LLM) but can be inefficient if the file is large or if the model doesn’t always need that data. In Mazkir’s case, the tasks list is usually small, so injecting it is fine. We could include, say, a summary or the first few tasks in the prompt. If the list grows, we might summarize or paginate it.
2. **On-demand tool use:** The alternative is to not include the tasks by default, and let the model explicitly ask for them via the tool interface (e.g., output `{"action": "get_tasks"}`). This way, if the user’s question doesn’t require memory (e.g., “Tell me a joke”), the model won’t spend context on it. If the user does ask for something requiring memory, the model will issue a read action, and our code will fetch the data and supply it. This approach treats the file truly as an external resource the model must pull when needed, and fits the general agent tool-use paradigm. It’s more token-efficient for queries not needing memory, at the cost of an extra LLM roundtrip when it does need it.

Mazkir can actually support both modes. For reliability, we might do a mix: inject key info (like number of pending tasks or other frequently needed snippets) into the prompt, but use explicit tool calls for full data when necessary. In the code sample, we will demonstrate the on-demand approach to highlight the agent’s tool-using behavior.

## LLM Integration via LiteLLM

We use **LiteLLM**, a Python SDK, to interface with the LLM. LiteLLM provides a unified interface to call over **100+ different models** (OpenAI, Anthropic, HuggingFace models, etc.) with a consistent API. This means the user can configure whichever cloud (or local) model they prefer via environment variables, and Mazkir’s code does not need to change. For example, by setting `OPENAI_API_KEY` and choosing `model="gpt-3.5-turbo"` or `model="gpt-4"`, the assistant will use OpenAI. Or the user could set up an Anthropic Claude API, or even a local model via Ollama or HuggingFace pipeline; LiteLLM will handle the specifics of each provider behind the scenes. This flexibility is great for a personal assistant: one can start with free/cheap models and upgrade to more powerful ones as needed, without altering the code.

**Basic usage:** After installing `litellm` (via pip) and setting the appropriate environment variables (for API keys or local endpoints), calling an LLM is as simple as:

```python
from litellm import completion
response = completion(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello"}])
print(response['choices'][0]['message']['content'])
```

LiteLLM follows the OpenAI Chat Completion format, where you pass a list of messages with roles (system, user, assistant). It ensures the output is normalized such that the text content is always at `response['choices'][0]['message']['content']`. This uniform output structure simplifies our parsing of the model’s answer or tool call.

**System prompt & instructions:** We will craft a system prompt instructing the model about Mazkir’s role and how to use the memory tool. For example, the system message may say: *“You are Mazkir, an AI assistant that manages tasks for the user. You have a memory file to store tasks and preferences. You can use the file by outputting a JSON command when needed. Only use the file if it’s necessary to answer the user’s request. Do not reveal the file content unless asked,”* etc. We’ll define the exact format for tool use (like the JSON structure with `"action"` keys as discussed) in this system prompt, along with the user’s preferences (tone, etc.) to guide the style of responses. By including the user’s preferred tone from the memory in the prompt, we ensure consistency (e.g., if tone is friendly, perhaps include a note like "*Tone: use a friendly, casual style.*").

**Running locally:** The Python module will be executable on the user’s machine. Other than network calls to the LLM API (which require internet unless using a local model), everything happens locally: reading the memory file, updating it, etc. The user will need to have their API keys configured (as environment variables) for cloud models. We deliberately avoid any server or cloud storage – the design keeps user data in the user’s hands. This local-by-default approach is aligned with privacy best practices: sensitive task data isn’t sent anywhere except transiently to the LLM during a prompt (and even that can be mitigated by using a local model if the user is uncomfortable sending task details to an API).

Because Mazkir can be configured to run with offline models (via LiteLLM’s support for local backends), a tech-savvy user could run the entire assistant fully offline – ensuring no data ever leaves their machine. For most users, a cloud model will be used, so we note that any task content included in a prompt will be seen by the model provider. If tasks are highly sensitive, using an open-source local model is an option.

**Ensuring safe tool usage:** In our integration, we implement a **allowlist** for file operations. The code will only permit the LLM to read or write the specific `mazkir_memory.json` (or a designated directory). This prevents malicious or accidental attempts by the model to access other files on the system. This is an important safeguard, as giving an LLM uncontrolled filesystem access could be dangerous. We also constrain the types of actions – e.g., we implement only read tasks and add task (and maybe mark done) actions. There is no direct arbitrary code execution or shell command tool exposed. This principle of least privilege (giving the agent only the minimum capabilities it needs) is echoed in current best practices for AI agent design to limit potential harm.

Finally, we incorporate **robustness** measures recommended in the latest agent design guides. For example, we monitor the format of the LLM’s responses. If the model returns a malformed JSON or an unexpected output when a tool use was expected, our code can catch the error and, for instance, reprompt the model or fall back to a safe behavior (perhaps just apologize and not execute anything uncertain). It’s noted that LLMs sometimes make formatting mistakes or stray from instructions when using tools, so being prepared for that improves reliability. We also ensure that after any tool action, the model is given any necessary feedback (like the result of a read, or a confirmation that a write succeeded) before it produces the final answer. This aligns with the ReAct pattern of providing observations back to the model, and helps the model formulate accurate and informed responses.

## Example Workflow

To illustrate how Mazkir operates, let's walk through two typical scenarios: **listing tasks** and **adding a new task**. This demonstrates the interaction between the user, the LLM, and the memory file tool.

1. **User asks for their tasks:** The user inputs, "*What are my pending tasks?*".
   **LLM Processing:** Mazkir's system prompt has already told the model about the memory file. The assistant knows it needs the task list to answer. It outputs a JSON action, e.g. `{"action": "get_tasks"}` (and nothing else), indicating it wants to read the tasks from memory.
   **Tool Action:** The Python code sees this and loads the `tasks` list from `mazkir_memory.json`. It then supplies that data back to the model. For example, it might append an assistant message like: "*Memory: 3 tasks found – 1. Buy groceries (pending), 2. Finish report (done), 3. Call mom (pending).*" (This is not shown to the user, but given to the model as context.)
   **LLM Final Answer:** Now with the tasks info, the model can answer the user’s question. It might respond with something like, "*You have 2 pending tasks: (1) Buy groceries, (3) Call mom. Task 2 (Finish report) is already done.*" formatted according to the user's tone preference. This final answer is then returned to the user.
   *(Behind the scenes, the model’s chain of thought might have looked like: "User asked for pending tasks -> I need the task list -> \[Action: get\_tasks] -> (gets list) -> Now I have the list, filter pending and answer.")* The user only sees the final answer.

2. **User adds a new task:** The user inputs, "*Add 'Schedule dentist appointment' to my to-do list.*"
   **LLM Processing:** The model parses the instruction and decides a tool action is needed to add a task. It outputs something like `{"action": "add_task", "task": "Schedule dentist appointment"}` as its response.
   **Tool Action:** The Python code intercepts this JSON. It updates the memory file – assigning a new ID (say 4) to the task, adding `{"id": 4, "description": "Schedule dentist appointment", "status": "pending", "created": "...now..."}` to the `tasks` list, and incrementing `last_task_id`. It saves the file. It then provides a confirmation back to the LLM, for example by appending a message like: "*Memory updated: task 'Schedule dentist appointment' added (ID 4).*"
   **LLM Final Answer:** With the knowledge that the task was successfully added, the model now produces a user-facing message. For instance, following a friendly tone, it might say: "*Sure, I've added 'Schedule dentist appointment' to your to-do list. Good luck!*". This message is returned to the user. The user can later confirm by asking to list tasks, and the new task will appear (since it's in memory now).

In both cases, the pattern is **user -> LLM (tool request) -> tool action -> LLM (final answer)**. If no tool use is needed (e.g., user asks a general question or just chats), the model will directly produce an answer without the JSON action step. Mazkir essentially extends the LLM’s capabilities with a form of *controlled autonomy*: the LLM can take certain actions (modify/read a file) but through our supervision and within safe bounds. This approach is inspired by contemporary LLM agent architectures that cycle through thought, action, and observation while keeping the user in control. Notably, we could require user confirmation for certain actions (like deleting a task) to build trust, since fully autonomous agents are still a new concept and user trust in them is developing. For now, adding and listing tasks are low-risk enough to perform directly as instructed.

With the high-level design and workflow established, we can proceed to the implementation. Below is a self-contained Python module for Mazkir, incorporating the custom tool-use architecture with LiteLLM and the described memory file structure. The code is heavily commented to explain each part of the process.

## Sample Python Implementation

```python
import os
import json
from datetime import datetime
from litellm import completion  # LiteLLM SDK for calling the LLM

# Path to the local memory file
MEMORY_FILE = "mazkir_memory.json"

# Ensure the memory file exists with an initial structure
if not os.path.exists(MEMORY_FILE):
    initial_data = {
        "tasks": [],
        "preferences": {"tone": "neutral", "reminder_frequency": "none"},
        "history": [],
        "metadata": {"last_task_id": 0}
    }
    with open(MEMORY_FILE, "w") as f:
        json.dump(initial_data, f, indent=2)

def load_memory():
    """Load the memory JSON file into a Python dict."""
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    """Save the Python dict back to the memory JSON file."""
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def perform_file_action(action_dict):
    """
    Execute the requested file action (read/write) on the memory.
    Returns a string describing the result or data for the LLM.
    """
    memory = load_memory()
    action = action_dict.get("action")

    if action == "get_tasks":
        # Prepare a summary of tasks (e.g., all tasks or just pending tasks)
        tasks = memory.get("tasks", [])
        if not tasks:
            return "No tasks in the list."
        # Format the tasks in a simple list string
        lines = []
        for t in tasks:
            status = t.get("status", "pending")
            desc = t.get("description", "")
            tid = t.get("id", "?")
            lines.append(f"{tid}. {desc} [{status}]")
        return "Tasks:\n" + "\n".join(lines)

    elif action == "add_task":
        task_desc = action_dict.get("task", "")
        if not task_desc:
            return "Error: no task description provided."
        # Create a new task entry
        new_id = memory["metadata"]["last_task_id"] + 1
        new_task = {
            "id": new_id,
            "description": task_desc,
            "status": "pending",
            "created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        memory["tasks"].append(new_task)
        memory["metadata"]["last_task_id"] = new_id
        # Log history
        memory["history"].append({
            "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "action": "added_task",
            "task_id": new_id,
            "description": task_desc
        })
        save_memory(memory)
        return f"Task added (ID {new_id})."

    elif action == "complete_task":
        task_id = action_dict.get("task_id")
        if task_id is None:
            return "Error: no task_id provided."
        # Mark the task as done if it exists
        found = False
        for t in memory.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = "done"
                t["completed"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                found = True
                # Log history
                memory["history"].append({
                    "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "action": "completed_task",
                    "task_id": task_id
                })
                break
        if not found:
            return f"Error: task with ID {task_id} not found."
        save_memory(memory)
        return f"Task {task_id} marked as completed."

    else:
        return f"Error: unknown action '{action}'."

def process_user_input(user_message):
    """
    Core function to process user input through the LLM.
    It manages the prompt, interprets tool requests, and returns the assistant's response.
    """
    # Load preferences to incorporate tone or other settings into the system prompt
    memory = load_memory()
    tone = memory.get("preferences", {}).get("tone", "neutral")
    # You can use tone to adjust instructions or style. For simplicity, we just mention it.
    system_prompt = (
        "You are Mazkir, a personal task assistant AI. "
        f"Respond in a {tone} tone. "  # incorporate user preferred tone
        "You have access to a memory file storing the user's tasks and preferences. "
        "If needed to answer the user, you can use the memory tool by outputting a JSON like:\n"
        '{"action": "get_tasks"} or {"action": "add_task", "task": "..."} or {"action": "complete_task", "task_id": 123}.\n'
        "Only use this format when you need to read or write tasks. Do NOT reveal the JSON or the memory content directly to the user unless asked.\n"
        "After using a tool, wait for the result before giving the final answer. If no tool is needed, answer directly.\n"
    )
    # Assemble the message list for the conversation
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    # Loop to allow the LLM to use tools and then answer
    for _ in range(3):  # safety limit: max 3 tool uses per query to avoid infinite loops
        # Call the LLM via LiteLLM
        response = completion(model="gpt-3.5-turbo", messages=messages)
        assistant_reply = response["choices"][0]["message"]["content"].strip()

        # Try to interpret the assistant reply as a tool action (JSON)
        if assistant_reply.startswith('{'):
            try:
                action_dict = json.loads(assistant_reply)
            except json.JSONDecodeError:
                # If parsing fails, treat the reply as the final answer (fallback)
                return assistant_reply
            # We have a valid JSON action
            tool_result = perform_file_action(action_dict)
            # Append the tool result as a new message for the LLM
            messages.append({"role": "assistant", "content": tool_result})
            # Append an empty user prompt to encourage the model to continue with an answer
            messages.append({"role": "user", "content": "Please continue."})
            # Loop continues to get the next completion (which should ideally be the final answer)
            continue
        else:
            # The assistant reply is not a JSON action, so it's presumably the final answer
            return assistant_reply

    # If we exit the loop without a final answer (shouldn't normally happen), return whatever last reply is
    return assistant_reply

# Example usage:
if __name__ == "__main__":
    # Set your API key as an environment variable before running, e.g., OPENAI_API_KEY for OpenAI models.
    user_input = "Add 'Call the bank' to my task list."
    answer = process_user_input(user_input)
    print("Assistant:", answer)
```

**Explanation of the code:**

* We begin by ensuring the memory file exists. If not, we create it with a default structure (empty tasks, default neutral preferences, etc.). This allows the assistant to start fresh if no data is present, and also means the first run sets up the file automatically.
* The `perform_file_action` function encapsulates the logic for tool actions. We implemented three actions for demonstration: `"get_tasks"` (read all tasks), `"add_task"` (add a new task with a description), and `"complete_task"` (mark a task done by ID). Each action loads the memory, modifies or reads it, updates the file if needed, and returns a result string. This returned string is what we’ll feed back into the LLM as the “observation” or outcome of the tool use. For example, `get_tasks` returns a formatted list of tasks (or a message saying no tasks), `add_task` returns a confirmation that includes the new task ID, and `complete_task` returns either a success message or an error if the ID was not found.

  * We make sure to update `last_task_id` and append to `history` for add/complete actions to keep the memory consistent. Timestamps are recorded using `datetime.now()` (formatted in ISO string for readability).
  * Notice the safeguards: if an unknown action is received, we return an error string; if required parameters are missing (no task description or task\_id), we also return an error string. These will go back to the LLM, which ideally has been instructed not to do those things – but if it does, it will “see” the error and (hopefully) adjust its behavior in the next output. This is a simple way to handle misformatted tool requests.
* The `process_user_input` function orchestrates the conversation with the LLM. It sets up the system prompt (including tone and tool instruction guidelines) and the initial user message. The prompt explicitly describes how the model should respond when it needs to use the memory tool – by outputting a JSON with `action`. We also emphasize not to reveal internal JSON or memory content directly, to prevent it from spitting out raw data unprompted.

  * We then enter a loop, allowing the LLM to possibly go through multiple tool uses. In each iteration, we call `completion(...)` from LiteLLM with the current message list. We parse out the assistant's reply.
  * We check if the reply looks like a JSON (starts with `{`). If so, we attempt to `json.loads` it. If parsing fails (the model output was invalid JSON), we break and return that output as-is (this is a fail-safe – in practice, with good prompting, the model should output proper JSON or not at all in this design).
  * When we successfully parse a JSON and find an `action`, we call `perform_file_action` with it. We get a `tool_result` (string). We then append this as an assistant message in the dialogue history. We follow it with a user message "Please continue." – this is a cue to the LLM to continue the conversation now that it has the tool result. The model will see the memory tool’s output in the conversation and, given the instructions, ideally incorporate that into its next answer.
  * We then loop back and call the LLM again. On this second pass (or maybe third, if more actions), the model hopefully produces a natural language answer rather than another JSON. When the assistant’s reply is not starting with `{`, we assume it’s the final answer to the user and return it.
  * The loop is capped at 3 iterations just in case the model gets stuck in an unexpected loop of tool requests (though with our prompts and use-cases, it shouldn’t need more than 1 tool action before answering).
* In the `__main__` block, we show an example usage: sending a command to add a task. In a real setting, this could be replaced by an interactive loop reading `input()` from the user and printing outputs, or integrated into a chat UI. The example is just to illustrate how to call `process_user_input()`.

**Note:** The model name `"gpt-3.5-turbo"` is used in `completion()`. This assumes an OpenAI API key is set (since that model is an OpenAI model). The user can change this to any model supported by LiteLLM, and as long as it’s a capable chat model that follows the instructions, the system will work. The system prompt is critical – it may need tweaking for different models to behave correctly. For instance, some models might require more explicit formatting instructions or examples of the JSON usage (few-shot examples) to reliably output the correct JSON. As a best practice, one could include an example in the prompt like: *“For example, if the user says 'list tasks', you might output `{"action": "get_tasks"}`.”* This helps the model understand the expected behavior. We omitted detailed examples here to keep the prompt concise, but they can be added if needed for model compliance.

## Conclusion and Best Practices

We have designed Mazkir as a focused, local-first personal assistant that demonstrates how to integrate an LLM with tool-use capabilities without heavy frameworks. To recap the key points and best practices from recent guidance:

* **Use of Tools:** Equipping LLMs with tools (like file access) greatly extends their utility, allowing them to act rather than just chat. The ReAct paradigm (reason → act → observe) is a powerful pattern to implement this. Mazkir uses a simplified ReAct loop: the LLM reasons about needing the task list or to update it, acts by outputting a tool command, observes the result, and then responds to the user. This grounded approach helps reduce hallucinations and keeps the LLM’s outputs tied to real data.
* **MCP vs Custom:** We evaluated using the Model Context Protocol versus a custom solution. MCP offers standardization and future-proof integration of tools, which is why it’s gaining traction in the industry. However, for a single-user local app, a custom approach is easier to implement and control, avoiding the overhead of running additional servers. In either case, **security** is paramount: one must limit the agent’s abilities to the minimum required (as we did by scoping file access) and be aware of new threat vectors like prompt injection when giving an LLM tool access.
* **Memory and Personalization:** Storing state is vital for a personal assistant to be truly helpful. We chose a simple JSON file to persist tasks and preferences; this is a lightweight solution that works well for a moderate amount of data. The structure is human-editable and machine-readable. As the amount of information grows, consider techniques like summarization or using a database or vector store for efficiency – but only add complexity when necessary. The design prioritizes keeping it **local and simple** at first.
* **LiteLLM and Model Flexibility:** By using an abstraction like LiteLLM, Mazkir can switch between different LLM providers or even local models seamlessly. This is a best practice to avoid lock-in and to allow using the best model for the task (economically or performance-wise). Always keep API keys secure (we use environment variables), and be mindful of the data sent to third-party APIs (don’t send anything you wouldn’t be comfortable leaving your machine, unless using a local model).
* **User Experience:** Finally, in personal task management workflows, the assistant should be reliable and transparent. It should confirm important actions (e.g., “Task added”), handle ambiguous input gracefully (maybe ask for clarification if needed), and adopt the user’s preferred tone and style for responses (which we store and use). Given that fully autonomous virtual assistants are still gaining user trust, Mazkir is designed to be **assistive** rather than fully automatic – it acts on direct user requests and keeps the user in the loop. As a potential future improvement, one could add **notifications** (honoring `reminder_frequency`) where the assistant proactively says something if the user hasn’t checked in, but such actions should be configurable and not intrusive.

By adhering to these principles and using the latest best practices in LLM agent design, Mazkir provides a solid foundation for a personal assistant. It demonstrates how even without large frameworks, one can integrate an LLM with tool use, memory, and personalized behavior in a clear and maintainable way. The provided code offers a concise blueprint that can be extended or modified as needed – for example, adding more actions (editing tasks, deleting tasks), integrating scheduling tools, or hooking into other personal data sources in the future. With this architecture, Mazkir can grow alongside the advancements in LLM capabilities and user needs, all while running locally under the user’s control.

**Sources:**

* Anthropic, *Introducing the Model Context Protocol* (2024) – on MCP’s goal to standardize AI-tool integrations.
* Microsoft Windows Blog, *Securing the Model Context Protocol* (2025) – describes MCP (JSON-RPC over HTTP) and emphasizes security considerations for agentic tools.
* Neon Tech Blog, *What’s MCP all about?* (2025) – compares MCP to direct function calling, noting MCP’s standardized tool interface and reuse benefits.
* SuperAnnotate, *LLM Agents: The ultimate guide 2025* – explains LLM agent components like tool use and mentions formatting challenges when agents use tools.
* Arize AI Blog, *Memory and State in LLM Applications* (2025) – discusses the importance of persistent state for consistency and personalization in assistant apps.
* Dev Community post, *Two of My Favorite Custom MCP Tools* (2025) – highlights community experiences with MCP (flakiness of examples, etc.).
* Example personal assistant projects (2023-2025) – show use of JSON files for local data storage and the trend towards multi-step ReAct-style agents combining reasoning and actions.
* LiteLLM Documentation – describes the unified interface to numerous LLMs and consistent output format.
* Sam Armstrong (Medium, 2025), *Survey of LLM-Based Agents in Virtual Assistants* – overview of how LLM agents plan and use tools, and caution that user trust is still being established for autonomous behaviors.
