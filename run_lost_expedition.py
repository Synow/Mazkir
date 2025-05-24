"""Main script to run the Lost Expedition game."""

import argparse
from lost_expedition_game.agent import play_game
from lost_expedition_game.config import DEFAULT_LLM_MODEL # For default value in parser

def main():
    """
    Parses command-line arguments and starts the Lost Expedition game.
    """
    parser = argparse.ArgumentParser(description="Run the Lost Expedition game with an LLM agent.")
    
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_LLM_MODEL,
        help=f"The LLM model to use for the agent (e.g., 'gpt-3.5-turbo', 'claude-3-haiku-20240307'). Defaults to '{DEFAULT_LLM_MODEL}'."
    )
    parser.add_argument(
        "--max_turns",
        type=int,
        default=100, # Defaulting to 100 turns
        help="The maximum number of turns the game will run. Defaults to 100."
    )
    parser.add_argument(
        "--log_file",
        type=str,
        default="game_log.jsonl",
        help="The name of the JSONL file to log game events. Defaults to 'game_log.jsonl'."
    )

    args = parser.parse_args()

    print("--- Starting Lost Expedition ---")
    print(f"Configuration: Model='{args.model}', Max Turns='{args.max_turns}', Log File='{args.log_file}'")
    
    try:
        play_game(
            llm_model=args.model,
            max_turns=args.max_turns,
            log_filename=args.log_file
        )
    except Exception as e:
        print(f"An error occurred during game execution: {e}")
        # Optionally, log this critical error to a separate error log or the main log if possible
    finally:
        print("\n--- Lost Expedition game session finished. ---")
        print(f"Game log saved to: {args.log_file}")

if __name__ == "__main__":
    main()
