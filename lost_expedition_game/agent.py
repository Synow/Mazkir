"""LLM Agent logic for the Lost Expedition game."""

import json
import litellm
import os # For potential API key management

from .game import LostExpeditionGame
from .config import LLM_TOOLS, DEFAULT_LLM_MODEL
from .items import CRAFTABLE_ITEMS, USABLE_ITEMS # For prompt context
from .config import DEFAULT_LLM_MODEL # Make sure this is imported if used as default in runner

# Set API key if necessary (example for OpenAI, adapt as needed for other providers)
# litellm.api_key = os.environ.get("OPENAI_API_KEY")


def get_game_state_summary(game: LostExpeditionGame) -> dict:
    """
    Generates a concise summary of the current game state for the LLM.
    """
    player_status = game._tool_check_status()['status'] # Use existing tool for full status
    location_data = game.get_current_location_data()
    
    # Simplify resource display for the prompt
    resources_present_str = ", ".join([f"{name} ({qty})" for name, qty in location_data["resources"].items() if qty > 0])
    if not resources_present_str:
        resources_present_str = "None"

    # Inventory summary
    inventory_str = ", ".join([f"{name} ({qty})" for name, qty in player_status["inventory"].items()])
    if not inventory_str:
        inventory_str = "Empty"

    summary = {
        "turn_count": player_status["turn_count"],
        "health": f"{player_status['health']}/{player_status['max_health']}",
        "hunger": f"{player_status['hunger']}/{player_status['max_hunger']}",
        "thirst": f"{player_status['thirst']}/{player_status['max_thirst']}",
        "beacon_progress": f"{player_status['beacon_progress']}%",
        "artifacts_analyzed": player_status["artifacts_analyzed"],
        "inventory": inventory_str,
        "current_biome": location_data["biome_name"],
        "location_description": location_data["description"],
        "exits": ", ".join(location_data["exits"]) if location_data["exits"] else "None",
        "resources_at_location": resources_present_str,
        "artifact_present": "Yes" if location_data.get("has_artifact") and not location_data.get("artifact_analyzed_here") else "No",
        "artifact_analyzed_here": "Yes" if location_data.get("artifact_analyzed_here") else "No",
    }
    return summary

def format_recipes_for_prompt():
    """Formats craftable item recipes for the LLM prompt."""
    prompt_lines = ["Craftable Items and Recipes:"]
    for item, recipe in CRAFTABLE_ITEMS.items():
        ingredients = ", ".join([f"{qty} {res}" for res, qty in recipe.items()])
        prompt_lines.append(f"- {item}: requires {ingredients}")
    return "\n".join(prompt_lines)

def format_usable_items_for_prompt():
    """Formats usable item effects for the LLM prompt."""
    prompt_lines = ["Usable Items and Effects:"]
    for item, effects in USABLE_ITEMS.items():
        effect_descs = []
        if "hunger_restored" in effects: effect_descs.append(f"restores {effects['hunger_restored']} hunger")
        if "thirst_restored" in effects: effect_descs.append(f"restores {effects['thirst_restored']} thirst")
        if "health_restored" in effects: effect_descs.append(f"restores {effects['health_restored']} health")
        if "description" in effects: effect_descs.append(effects["description"]) # For items like artifacts
        prompt_lines.append(f"- {item}: {', '.join(effect_descs) if effect_descs else 'Special purpose'}")
    return "\n".join(prompt_lines)


def play_game(llm_model: str = DEFAULT_LLM_MODEL, max_turns: int = 50, log_filename: str = "game_log.jsonl"):
    """
    Manages the main game loop, interacting with the LLM agent.

    Args:
        llm_model: The language model to use.
        max_turns: The maximum number of turns for the game.
        log_filename: The name of the file to log game events to.
    """
    game = LostExpeditionGame()
    conversation_history = []

    system_prompt = (
        "You are a space explorer stranded on an alien planet. Your primary goal is to survive by managing your "
        "health, hunger, and thirst, and to build a rescue beacon to escape. You must gather resources, "
        "craft essential items and beacon components, and analyze alien artifacts to increase beacon progress. "
        "Interact with the world using ONLY the provided tools. Think step-by-step about your situation and what "
        "you need to do next to achieve your goals. Pay close attention to your inventory and available resources. "
        "Prioritize survival (hunger, thirst, health) but also make progress on the beacon. "
        "If you are low on a vital stat (e.g. hunger < 20), prioritize addressing it. "
        f"{format_recipes_for_prompt()}\n{format_usable_items_for_prompt()}"
    )
    conversation_history.append({"role": "system", "content": system_prompt})

    last_action_result = {
        "message": "You have crash-landed on an alien planet. Your ship is wrecked, but some initial supplies might be salvaged from the CrashSite biome. Good luck, explorer!"
    }
    
    # Clear log file at the start of a new game
    with open(log_filename, "w") as f: # Use parameterized log_filename
        pass # Clears the file

    print(f"--- Starting Lost Expedition ---")
    print(f"Model: {llm_model}, Max Turns: {max_turns}")
    print(f"Initial situation: {last_action_result['message']}\n")


    while True:
        game_over, game_over_message = game.check_game_over()
        if game_over:
            print(f"\n--- Game Over ---")
            print(game_over_message)
            print(f"Final Stats: {game._tool_check_status()['status']}")
            log_entry = {"turn": game.turn_count, "event": "game_over", "message": game_over_message, "final_status": game._tool_check_status()['status']}
            with open(log_filename, "a") as f: # Use parameterized log_filename
                f.write(json.dumps(log_entry) + "\n")
            break

        if game.turn_count >= max_turns:
            print(f"\n--- Max Turns Reached ({max_turns}) ---")
            print("The expedition is deemed lost to time...")
            print(f"Final Stats: {game._tool_check_status()['status']}")
            log_entry = {"turn": game.turn_count, "event": "max_turns_reached", "final_status": game._tool_check_status()['status']}
            with open(log_filename, "a") as f: # Use parameterized log_filename
                f.write(json.dumps(log_entry) + "\n")
            break

        current_status_summary = get_game_state_summary(game)
        
        user_prompt_content = (
            f"Turn: {current_status_summary['turn_count']}\n"
            f"Health: {current_status_summary['health']}, Hunger: {current_status_summary['hunger']}, Thirst: {current_status_summary['thirst']}\n"
            f"Beacon Progress: {current_status_summary['beacon_progress']}, Artifacts Analyzed: {current_status_summary['artifacts_analyzed']}\n"
            f"Inventory: {current_status_summary['inventory']}\n"
            f"Current Location: Biome: {current_status_summary['current_biome']} - {current_status_summary['location_description']}\n"
            f"Exits: {current_status_summary['exits']}\n"
            f"Resources Here: {current_status_summary['resources_at_location']}\n"
            f"Artifact Present (Unanalyzed): {current_status_summary['artifact_present']}\n"
            f"Last Action Result: {last_action_result.get('message', 'No message.')}\n\n"
            "Review your status, environment, and available tools. Choose your next action wisely to survive and complete the beacon."
        )
        
        # Prune history if it gets too long (simple strategy: keep system + last N interactions)
        # LiteLLM might handle token limits, but explicit control can be good.
        MAX_HISTORY_MESSAGES = 10 # System + 4 pairs of user/assistant + current user prompt
        if len(conversation_history) > MAX_HISTORY_MESSAGES:
            conversation_history = [conversation_history[0]] + conversation_history[-(MAX_HISTORY_MESSAGES-1):]

        conversation_history.append({"role": "user", "content": user_prompt_content})

        llm_response = None
        chosen_tool_name = "None"
        chosen_params = {}

        try:
            print(f"\n--- Turn {game.turn_count} ---")
            print(f"Player Status: H:{current_status_summary['health']} Hu:{current_status_summary['hunger']} T:{current_status_summary['thirst']}")
            print(f"Location: {current_status_summary['current_biome']} ({game.player.location_x},{game.player.location_y}) Inv: {current_status_summary['inventory']}")
            print(f"Last Result: {last_action_result.get('message', 'N/A')}")
            print("LLM is thinking...")

            response = litellm.completion(
                model=llm_model,
                messages=conversation_history,
                tools=LLM_TOOLS,
                tool_choice="auto" # Could be "required" if we always want a tool
            )
            llm_response = response # Save for logging

            if response.choices and response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                chosen_tool_name = tool_call.function.name
                arguments_str = tool_call.function.arguments
                
                try:
                    chosen_params = json.loads(arguments_str)
                except json.JSONDecodeError as e:
                    print(f"Error: LLM provided malformed JSON arguments: {arguments_str}. Error: {e}")
                    last_action_result = {"message": f"LLM provided malformed JSON arguments for {chosen_tool_name}. Turn skipped.", "error": "Malformed JSON arguments"}
                    # Add LLM's (malformed) response to history so it can learn
                    conversation_history.append({"role": "assistant", "content": response.choices[0].message.content or "", "tool_calls": response.choices[0].message.tool_calls}) # Log tool call attempt
                    chosen_tool_name = "error_json_decode" # for logging
                    # game.turn_count and passive costs are handled by execute_tool, but here we skip it.
                    # So, apply passive costs manually.
                    game.player.change_hunger(game.PASSIVE_HUNGER_COST)
                    game.player.change_thirst(game.PASSIVE_THIRST_COST)
                    game.turn_count +=1


                if chosen_tool_name != "error_json_decode": # If JSON was valid
                    print(f"LLM chose: {chosen_tool_name} with params: {chosen_params}")
                    last_action_result = game.execute_tool(chosen_tool_name, **chosen_params)
                    
                    # Add LLM's tool call and game's response to history
                    # Assistant message part (the tool call itself)
                    assistant_message = {"role": "assistant", "tool_calls": response.choices[0].message.tool_calls}
                    if response.choices[0].message.content: # If LLM includes text along with tool call
                        assistant_message["content"] = response.choices[0].message.content
                    conversation_history.append(assistant_message)

                    # Tool response part (simulating what OpenAI API expects for tool role)
                    # Note: LiteLLM's history format for tool calls might vary slightly or expect a specific structure.
                    # This format is based on OpenAI's typical tool use pattern.
                    conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": chosen_tool_name,
                        "content": json.dumps(last_action_result) # Game's response to the tool
                    })

            else: # No tool call from LLM
                llm_text_response = response.choices[0].message.content if response.choices else "LLM did not choose a tool or provide text."
                print(f"LLM response (no tool call): {llm_text_response}")
                last_action_result = {"message": f"LLM did not choose a tool. Response: '{llm_text_response}'. Turn effectively skipped."}
                # Add LLM's text response to history
                conversation_history.append({"role": "assistant", "content": llm_text_response})
                # Apply passive costs as turn is skipped in terms of game actions
                game.player.change_hunger(game.PASSIVE_HUNGER_COST)
                game.player.change_thirst(game.PASSIVE_THIRST_COST)
                game.turn_count +=1 # Increment turn as LLM used its "action"

        except litellm.RateLimitError as e:
            print(f"Error: LiteLLM Rate Limit Error: {e}")
            last_action_result = {"message": "Rate limit hit with the LLM API. Try again later.", "error": "Rate limit"}
            # Potentially pause or implement backoff here
            chosen_tool_name = "error_rate_limit"
            # Don't penalize player for API errors, maybe don't advance turn or apply costs
            # For now, for simplicity, we'll let the turn pass with no action
            game.turn_count += 1 
        except litellm.APIConnectionError as e:
            print(f"Error: LiteLLM API Connection Error: {e}")
            last_action_result = {"message": "Could not connect to the LLM API.", "error": "API connection error"}
            chosen_tool_name = "error_api_connection"
            game.turn_count += 1
        except Exception as e:
            print(f"Error: An unexpected error occurred during LLM interaction: {e}")
            last_action_result = {"message": f"An unexpected error occurred: {e}. Turn skipped.", "error": "Unexpected LLM error"}
            chosen_tool_name = "error_unexpected_llm"
            # Apply passive costs manually if execute_tool was skipped
            if not (chosen_tool_name in game.craftable_items or chosen_tool_name in game.usable_items or chosen_tool_name in ["scan_environment", "move_to_location", "gather_resource", "rest", "analyze_artifact", "check_status"]):
                 game.player.change_hunger(game.PASSIVE_HUNGER_COST)
                 game.player.change_thirst(game.PASSIVE_THIRST_COST)
                 game.turn_count +=1


        # Logging
        log_entry = {
            "turn": game.turn_count -1 if chosen_tool_name in ["error_json_decode", "error_unexpected_llm", "error_api_connection", "error_rate_limit"] else game.turn_count, # Adjust turn if it was incremented due to error
            "player_status_before_action": current_status_summary,
            "llm_prompt": user_prompt_content,
            "llm_response_obj": llm_response.model_dump_json() if llm_response else None, # Log full response object
            "chosen_tool": chosen_tool_name,
            "tool_params": chosen_params,
            "action_result": last_action_result,
            "player_status_after_action": get_game_state_summary(game) # Get fresh status
        }
        with open(log_filename, "a") as f: # Use parameterized log_filename
            f.write(json.dumps(log_entry) + "\n")
        
        print(f"Action Result: {last_action_result.get('message', 'N/A')}")
        if "error" in last_action_result:
            print(f"Error detail: {last_action_result['error']}")


if __name__ == '__main__':
    # Ensure you have an API key for your chosen model set, e.g., via environment variable OPENAI_API_KEY
    # For example, to run with a different model:
    # play_game(llm_model="claude-3-haiku-20240307", max_turns=50) 
    # play_game(llm_model="gpt-4-turbo-preview", max_turns=50)
    
    # Check if OPENAI_API_KEY is set, if not, print a warning and skip play_game
    # This is a common key, but other models might need different keys (e.g. ANTHROPIC_API_KEY)
    # LiteLLM handles many of these via its own environment variable checks.
    
    # A more generic check for some common API keys LiteLLM might use
    required_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"] # Add others as needed
    key_found = any(os.environ.get(key) for key in required_keys)

    if not key_found and DEFAULT_LLM_MODEL not in ["ollama/mistral"]: # ollama might not need a key
        print(f"Warning: No common API key (e.g., {', '.join(required_keys)}) found in environment variables.")
        print("The game might not run correctly if the selected LLM requires an API key.")
        print(f"Attempting to run with DEFAULT_LLM_MODEL='{DEFAULT_LLM_MODEL}' which might be a local model or require other setup.")
        # Decide if you want to prevent play_game() or let it try and fail
        # For now, let it try, LiteLLM will error out if needed.
    
    print(f"Attempting to play game with model: {DEFAULT_LLM_MODEL} and log to game_log.jsonl (default)")
    play_game(llm_model=DEFAULT_LLM_MODEL, max_turns=50, log_filename="game_log.jsonl")
