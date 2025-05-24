"""Agent logic for the Simple Maze Game."""

import json
import litellm
import os

from .game import MazeGame
from .config import LLM_TOOLS_MAZE, DEFAULT_LLM_MODEL, \
                    DEFAULT_MAZE_WIDTH, DEFAULT_MAZE_HEIGHT, \
                    DEFAULT_MAX_TURNS, DEFAULT_OBSTACLES, \
                    DEFAULT_AGENT_START, DEFAULT_TARGET_POS

# API Key setup (example for OpenAI)
# litellm.api_key = os.environ.get("OPENAI_API_KEY")

def format_maze_for_llm(maze_game: MazeGame) -> str:
    """Creates a string representation of the maze for the LLM."""
    grid = []
    maze_width = maze_game.maze.width
    maze_height = maze_game.maze.height
    agent_pos = maze_game.maze.get_agent_position()
    target_pos = maze_game.maze.get_target_position()
    obstacles = maze_game.maze.obstacles

    for y in range(maze_height):
        row_str = []
        for x in range(maze_width):
            if (x,y) == agent_pos:
                row_str.append('A')
            elif (x,y) == target_pos:
                row_str.append('T')
            elif (x,y) in obstacles:
                row_str.append('X')
            else:
                row_str.append('.')
        grid.append(" ".join(row_str)) # Add spaces for better visual separation
    return "\n".join(grid)

def play_maze_game(
    llm_model: str = None, # Will default to DEFAULT_LLM_MODEL if None
    width: int = None,
    height: int = None,
    agent_start: tuple = None,
    target_pos: tuple = None,
    obstacles: list = None,
    max_turns: int = None,
    log_filename: str = "maze_game_log.jsonl"
):
    """
    Manages the main game loop for the Simple Maze Game.
    """
    # Use defaults from config if parameters are None
    llm_model_to_use = llm_model if llm_model is not None else DEFAULT_LLM_MODEL
    maze_width = width if width is not None else DEFAULT_MAZE_WIDTH
    maze_height = height if height is not None else DEFAULT_MAZE_HEIGHT
    game_max_turns = max_turns if max_turns is not None else DEFAULT_MAX_TURNS
    
    # Handle None for positions and obstacles carefully before passing to MazeGame
    # MazeGame constructor has its own defaults/error handling for positions if they are out of bounds
    # but we need to provide *some* value or let MazeGame use its internal defaults if we pass None.
    # The prompt asks for agent_start and target_pos to be passed, so we use config defaults if None.
    
    current_agent_start = agent_start if agent_start is not None else DEFAULT_AGENT_START
    # Adjust default target if maze dimensions are different from default config dimensions
    if target_pos is None:
        current_target_pos = (maze_width -1, maze_height -1)
    else:
        current_target_pos = target_pos
        
    current_obstacles = obstacles if obstacles is not None else DEFAULT_OBSTACLES


    game = MazeGame(
        width=maze_width,
        height=maze_height,
        agent_start=current_agent_start,
        target_pos=current_target_pos,
        obstacles=current_obstacles
    )
    game.max_turns = game_max_turns # Set max_turns for the game instance

    conversation_history = []
    system_prompt = (
        "You are an agent navigating a maze. Your goal is to reach the target location ('T'). "
        "You will be given your current position ('A'), the target position, and your current score "
        "(closer to target is better, score is negative Manhattan distance). Use the 'move' tool to navigate. "
        "The maze is a grid, 0-indexed. (0,0) is top-left. 'X' represents obstacles, '.' is empty space."
    )
    conversation_history.append({"role": "system", "content": system_prompt})

    last_action_result = {"message": f"Game started. Agent at {game.maze.get_agent_position()}, Target at {game.maze.get_target_position()}. Max turns: {game.max_turns}."}

    # Clear log file
    with open(log_filename, "w") as f:
        pass

    print(f"--- Starting Simple Maze Game ---")
    print(f"Model: {llm_model_to_use}, Maze: {maze_width}x{maze_height}, Max Turns: {game.max_turns}")
    print(f"Agent: {game.maze.get_agent_position()}, Target: {game.maze.get_target_position()}")
    print(f"Obstacles: {game.maze.obstacles}")
    print(f"Initial score: {game.score}")
    print(f"Initial message: {last_action_result['message']}\n")


    while not game.game_over:
        current_status = game.get_status()
        maze_representation = format_maze_for_llm(game)

        user_prompt_content = (
            f"Turn: {current_status['turn_count']}/{current_status['max_turns']}\n"
            f"Agent Position ('A'): {current_status['agent_position']}\n"
            f"Target Position ('T'): {current_status['target_position']}\n"
            f"Current Score: {current_status['score']}\n"
            f"Last Move Result: {last_action_result.get('message', 'N/A')}\n\n"
            "Maze Layout:\n"
            f"{maze_representation}\n\n"
            "Choose your next move ('up', 'down', 'left', 'right')."
        )
        
        # Prune history (optional, good for very long games)
        MAX_HISTORY_MESSAGES = 10 
        if len(conversation_history) > MAX_HISTORY_MESSAGES:
            conversation_history = [conversation_history[0]] + conversation_history[-(MAX_HISTORY_MESSAGES-1):]

        conversation_history.append({"role": "user", "content": user_prompt_content})
        
        llm_response_obj = None
        chosen_tool_name = "None"
        chosen_params = {}

        log_entry_pre_action = {
            "turn": current_status['turn_count'],
            "agent_position_before": current_status['agent_position'],
            "score_before": current_status['score'],
            "llm_prompt": user_prompt_content,
        }

        try:
            print(f"\n--- Turn {current_status['turn_count']} ---")
            print(f"Agent: {current_status['agent_position']}, Target: {current_status['target_position']}, Score: {current_status['score']}")
            print(f"Last Result: {last_action_result.get('message', 'N/A')}")
            print("Maze:\n" + maze_representation)
            print("LLM is thinking...")

            response = litellm.completion(
                model=llm_model_to_use,
                messages=conversation_history,
                tools=LLM_TOOLS_MAZE,
                tool_choice="auto" # Could be "required"
            )
            llm_response_obj = response # For logging

            if response.choices and response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                chosen_tool_name = tool_call.function.name
                arguments_str = tool_call.function.arguments
                
                try:
                    chosen_params = json.loads(arguments_str)
                except json.JSONDecodeError as e:
                    print(f"Error: LLM provided malformed JSON arguments: {arguments_str}. Error: {e}")
                    last_action_result = game.tool_move("invalid_direction_due_to_json_error") # Penalize turn
                    last_action_result["message"] = f"LLM error (malformed JSON): {arguments_str}. Move failed." # Overwrite message
                    conversation_history.append({"role": "assistant", "content": response.choices[0].message.content or "", "tool_calls": response.choices[0].message.tool_calls})
                    chosen_tool_name = "error_json_decode"
                
                if chosen_tool_name == "move":
                    direction = chosen_params.get("direction")
                    if direction:
                        print(f"LLM chose: move, Direction: {direction}")
                        last_action_result = game.tool_move(direction)
                    else:
                        print(f"LLM chose 'move' but no direction provided. Args: {arguments_str}")
                        # Penalize turn, treat as invalid move
                        last_action_result = game.tool_move("invalid_direction_due_to_missing_param") 
                        last_action_result["message"] = "LLM chose 'move' but did not specify a direction. Move failed."
                    
                    # Add LLM's tool call and game's response to history
                    assistant_message_content = {"role": "assistant", "tool_calls": response.choices[0].message.tool_calls}
                    if response.choices[0].message.content: # If LLM includes text along with tool call
                        assistant_message_content["content"] = response.choices[0].message.content
                    conversation_history.append(assistant_message_content)
                    
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": chosen_tool_name,
                        "content": json.dumps(last_action_result)
                    })
                elif chosen_tool_name != "error_json_decode": # Some other tool was called?
                    print(f"LLM called unexpected tool: {chosen_tool_name}")
                    last_action_result = game.tool_move("invalid_tool_call") # Penalize turn
                    last_action_result["message"] = f"LLM called an unexpected tool: {chosen_tool_name}. Move failed."

            else: # No tool call
                llm_text_response = response.choices[0].message.content if response.choices else "LLM did not choose a tool."
                print(f"LLM response (no tool call): {llm_text_response}")
                # Penalize turn, as no valid game action was taken
                last_action_result = game.tool_move("no_tool_call_from_llm") 
                last_action_result["message"] = f"LLM did not choose a tool. Response: '{llm_text_response}'. Move failed."
                conversation_history.append({"role": "assistant", "content": llm_text_response})

        except litellm.RateLimitError as e:
            print(f"Error: LiteLLM Rate Limit Error: {e}")
            last_action_result = {"message": "Rate limit hit. Game cannot continue.", "error": "Rate limit"}
            game.game_over = True # End game if API fails critically
        except litellm.APIConnectionError as e:
            print(f"Error: LiteLLM API Connection Error: {e}")
            last_action_result = {"message": "API connection error. Game cannot continue.", "error": "API connection error"}
            game.game_over = True
        except Exception as e:
            print(f"Error: An unexpected error occurred: {e}")
            last_action_result = {"message": f"An unexpected error: {e}. Game cannot continue.", "error": "Unexpected error"}
            game.game_over = True # End game on other critical errors

        # Logging
        final_status_for_log = game.get_status()
        log_entry = {
            **log_entry_pre_action,
            "llm_full_response": llm_response_obj.model_dump_json() if llm_response_obj else None,
            "chosen_tool": chosen_tool_name,
            "tool_params": chosen_params,
            "action_result_message": last_action_result.get("message"),
            "action_result_full": last_action_result,
            "agent_position_after": final_status_for_log['agent_position'],
            "score_after": final_status_for_log['score'],
            "game_over_after": final_status_for_log['game_over'],
            "turn_after_action": final_status_for_log['turn_count'] # Turn count from game state after action
        }
        with open(log_filename, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        print(f"Action Result: {last_action_result.get('message', 'N/A')}")
        if "error" in last_action_result:
            print(f"Error detail for last action: {last_action_result['error']}")


    # After loop: Game is over
    print(f"\n--- Simple Maze Game Over ---")
    final_status = game.get_status()
    print(f"Final Status: Agent at {final_status['agent_position']}, Target at {final_status['target_position']}")
    print(f"Score: {final_status['score']}, Turns: {final_status['turn_count']}/{final_status['max_turns']}")
    if final_status['agent_position'] == final_status['target_position']:
        print("Outcome: Agent successfully reached the target!")
    elif final_status['turn_count'] >= final_status['max_turns']:
        print("Outcome: Max turns reached. Agent did not reach the target.")
    else:
        print(f"Outcome: Game ended for other reasons. Last message: {last_action_result.get('message', 'N/A')}")
    
    print(f"Log file saved to: {log_filename}")


if __name__ == '__main__':
    # Ensure API key is set (e.g. OPENAI_API_KEY environment variable)
    # For local models via Ollama, LiteLLM might not require an explicit key
    # if os.environ.get("OPENAI_API_KEY") is None and DEFAULT_LLM_MODEL not in ["ollama/mistral"]:
    #    print("Warning: OPENAI_API_KEY not set. The game might fail if using OpenAI models.")

    print("Running Simple Maze Game with default settings...")
    play_maze_game(max_turns=20) # Short game for default test

    print("\nRunning a slightly more complex game (5x5, 15 turns, some obstacles)...")
    custom_obstacles = [(1,1), (2,1), (3,1), (1,3), (2,3)]
    play_maze_game(
        width=5, 
        height=5, 
        agent_start=(0,0), 
        target_pos=(4,4), 
        obstacles=custom_obstacles, 
        max_turns=15, 
        log_filename="maze_game_custom_log.jsonl"
    )

    print("\nRunning a small impossible game (max turns too low)...")
    play_maze_game(
        width=3,
        height=3,
        agent_start=(0,0),
        target_pos=(2,2),
        obstacles=[(1,0),(0,1),(1,2),(2,1)], # Box in agent
        max_turns=3, # Agent needs at least 4 moves if clear
        log_filename="maze_game_impossible_log.jsonl"
    )
