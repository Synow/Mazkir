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
        "You are an agent navigating a maze. Your goal is to reach the target location ('T') within 10 turns. "
        "The game has a strict 10-turn limit. Manage your moves carefully. "
        "Each turn consists of two steps: "
        "1. Commentary: You will first provide a brief (one sentence) assessment of your current situation, "
        "including your planned move direction (e.g., 'up', 'down', 'left', 'right'). Do not call any tools at this stage. "
        "2. Action: After providing commentary, you will be prompted again to make your move. At this point, "
        "you must use the 'move' tool with your chosen direction. "
        "You will be given your current position ('A'), the target position ('T'), and your current score "
        "(closer to target is better, score is negative Manhattan distance). "
        "The maze is a grid, 0-indexed. (0,0) is top-left. 'X' represents obstacles, '.' is empty space."
    )
    conversation_history.append({"role": "system", "content": system_prompt})

    last_action_result = {"message": f"Game started. Agent at {game.maze.get_agent_position()}, Target at {game.maze.get_target_position()}. You have {game.max_turns} turns to reach the target."}

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
        
        # Prune history (optional, good for very long games)
        MAX_HISTORY_MESSAGES = 15 # Increased slightly due to 2-phase interaction
        if len(conversation_history) > MAX_HISTORY_MESSAGES:
            conversation_history = [conversation_history[0]] + conversation_history[-(MAX_HISTORY_MESSAGES-1):]

        print(f"\n--- Turn {current_status['turn_count']} ---")
        print(f"Agent: {current_status['agent_position']}, Target: {current_status['target_position']}, Score: {current_status['score']}")
        print(f"Last Result: {last_action_result.get('message', 'N/A')}")
        print("Maze:\n" + maze_representation)

        # Phase 1: Get Commentary
        prompt_for_commentary = (
            f"Turn {current_status['turn_count']}/{current_status['max_turns']}. Score: {current_status['score']}.\n"
            f"Agent at {current_status['agent_position']}, Target at {current_status['target_position']}.\n"
            f"Last move result: {last_action_result.get('message', 'N/A')}\n"
            "Maze:\n"
            f"{maze_representation}\n"
            "Provide a brief (one sentence) commentary on your situation and your planned move direction (up, down, left, or right). Do not use tools."
        )
        conversation_history.append({"role": "user", "content": prompt_for_commentary})
        
        llm_commentary = "No commentary received."
        llm_commentary_response_obj = None
        commentary_error = False

        try:
            print("LLM is thinking (for commentary)...")
            commentary_response = litellm.completion(
                model=llm_model_to_use,
                messages=conversation_history
                # No tools or tool_choice here
            )
            llm_commentary_response_obj = commentary_response # For logging
            if commentary_response.choices and commentary_response.choices[0].message.content:
                llm_commentary = commentary_response.choices[0].message.content.strip()
                print(f"LLM Commentary: {llm_commentary}")
            else:
                llm_commentary = "LLM provided no commentary text."
                print(f"Warning: {llm_commentary}")
                commentary_error = True # Counts as a minor error, LLM didn't follow instructions
            conversation_history.append({"role": "assistant", "content": llm_commentary})
        except Exception as e:
            print(f"Error getting LLM commentary: {e}")
            llm_commentary = f"Error obtaining commentary: {e}"
            commentary_error = True
            # Add a placeholder assistant message for the error to keep history consistent
            conversation_history.append({"role": "assistant", "content": llm_commentary})


        # Phase 2: Get Move Action
        chosen_tool_name = "None"
        chosen_params = {}
        llm_move_response_obj = None

        if commentary_error: # If commentary failed, we might still try to get a move or penalize
            last_action_result = game.tool_move("error_during_commentary_phase")
            last_action_result["message"] = f"Skipped move due to error in commentary phase. Commentary: {llm_commentary}"
            print(last_action_result["message"])
        else:
            prompt_for_move = (
                f"Your commentary: \"{llm_commentary}\"\n"
                "Now, execute your planned move using the 'move' tool."
            )
            conversation_history.append({"role": "user", "content": prompt_for_move})
            
            try:
                print("LLM is thinking (for move)...")
                move_response = litellm.completion(
                    model=llm_model_to_use,
                    messages=conversation_history,
                    tools=LLM_TOOLS_MAZE,
                    tool_choice="auto" 
                )
                llm_move_response_obj = move_response # For logging

                if move_response.choices and move_response.choices[0].message.tool_calls:
                    tool_call = move_response.choices[0].message.tool_calls[0]
                    chosen_tool_name = tool_call.function.name
                    arguments_str = tool_call.function.arguments
                    
                    try:
                        chosen_params = json.loads(arguments_str)
                    except json.JSONDecodeError as e:
                        print(f"Error: LLM provided malformed JSON arguments for move: {arguments_str}. Error: {e}")
                        last_action_result = game.tool_move("invalid_direction_due_to_json_error")
                        last_action_result["message"] = f"LLM error (malformed JSON for move): {arguments_str}. Move failed."
                        chosen_tool_name = "error_json_decode_move"
                    
                    if chosen_tool_name == "move":
                        direction = chosen_params.get("direction")
                        if direction:
                            print(f"LLM chose: move, Direction: {direction}")
                            last_action_result = game.tool_move(direction)
                        else:
                            print(f"LLM chose 'move' but no direction provided. Args: {arguments_str}")
                            last_action_result = game.tool_move("invalid_direction_due_to_missing_param")
                            last_action_result["message"] = "LLM chose 'move' but did not specify a direction. Move failed."
                    elif chosen_tool_name != "error_json_decode_move":
                        print(f"LLM called unexpected tool for move: {chosen_tool_name}")
                        last_action_result = game.tool_move("invalid_tool_call_for_move")
                        last_action_result["message"] = f"LLM called an unexpected tool for move: {chosen_tool_name}. Move failed."

                    # Add LLM's tool call and game's response to history
                    assistant_move_message = {"role": "assistant", "tool_calls": move_response.choices[0].message.tool_calls}
                    if move_response.choices[0].message.content: # If LLM includes text
                        assistant_move_message["content"] = move_response.choices[0].message.content
                    conversation_history.append(assistant_move_message)
                    
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": chosen_tool_name,
                        "content": json.dumps(last_action_result)
                    })

                else: # No tool call for move
                    llm_text_response_move = move_response.choices[0].message.content if move_response.choices else "LLM did not choose a tool for move."
                    print(f"LLM response (no tool call for move): {llm_text_response_move}")
                    last_action_result = game.tool_move("no_tool_call_from_llm_for_move")
                    last_action_result["message"] = f"LLM did not choose a tool for move. Response: '{llm_text_response_move}'. Move failed."
                    conversation_history.append({"role": "assistant", "content": llm_text_response_move})

            except litellm.RateLimitError as e:
                print(f"Error: LiteLLM Rate Limit Error during move: {e}")
                last_action_result = {"message": "Rate limit hit. Game cannot continue.", "error": "Rate limit"}
                game.game_over = True 
            except litellm.APIConnectionError as e:
                print(f"Error: LiteLLM API Connection Error during move: {e}")
                last_action_result = {"message": "API connection error. Game cannot continue.", "error": "API connection error"}
                game.game_over = True
            except Exception as e:
                print(f"Error: An unexpected error occurred during move phase: {e}")
                last_action_result = {"message": f"An unexpected error during move phase: {e}. Game cannot continue.", "error": "Unexpected error"}
                game.game_over = True

        # Logging
        final_status_for_log = game.get_status()
        log_entry = {
            "turn": current_status['turn_count'], # Turn number at the start of this iteration
            "agent_position_before": current_status['agent_position'],
            "score_before": current_status['score'],
            "prompt_for_commentary": prompt_for_commentary,
            "llm_commentary_response_obj": llm_commentary_response_obj.model_dump_json() if llm_commentary_response_obj else None,
            "llm_commentary_text": llm_commentary,
            "prompt_for_move": prompt_for_move if not commentary_error else "N/A (skipped due to commentary error)",
            "llm_move_response_obj": llm_move_response_obj.model_dump_json() if llm_move_response_obj else None,
            "chosen_tool_for_move": chosen_tool_name,
            "tool_params_for_move": chosen_params,
            "action_result_message": last_action_result.get("message"),
            "action_result_full": last_action_result,
            "agent_position_after": final_status_for_log['agent_position'],
            "score_after": final_status_for_log['score'],
            "game_over_after": final_status_for_log['game_over'],
            "turn_after_action": final_status_for_log['turn_count'] 
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
