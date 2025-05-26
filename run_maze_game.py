"""Main script to run the Simple Maze Game."""
"""LLM Agent logic for the Lost Expedition game."""

import json
import litellm
import os # For potential API key management
from dotenv import load_dotenv
load_dotenv()

DEFAULT_LLM_MODEL="vertex_ai/gemini-2.5-flash-preview-04-17"

from openinference.instrumentation.litellm import LiteLLMInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

load_dotenv()

# Configure OpenTelemetry for Arize Phoenix
# Ensure your Phoenix instance is running and accessible at the specified endpoint.
# For local Docker setup, endpoint is typically http://localhost:4317 or http://0.0.0.0:4317
phoenix_tracer_provider = trace.get_tracer_provider()
if not isinstance(phoenix_tracer_provider, TracerProvider): # Check if a provider is already configured
    phoenix_tracer_provider = TracerProvider()
    trace.set_tracer_provider(phoenix_tracer_provider)
else:
    print("TracerProvider already configured.") # Or log this

# Configure the OTLP exporter
# Make sure your Phoenix collector is running at http://0.0.0.0:4317 (or your actual endpoint)
otlp_exporter = OTLPSpanExporter(
    endpoint="http://0.0.0.0:4317",  # Default for local Phoenix. Adjust if necessary.
    insecure=True  # Use insecure=True for HTTP. For HTTPS, set to False and configure certs.
)

# Add the OTLP exporter to the tracer provider
phoenix_tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Instrument LiteLLM
LiteLLMInstrumentor().instrument(tracer_provider=phoenix_tracer_provider)

print("Arize Phoenix LiteLLM Instrumentor configured.") # Add a print statement to confirm execution



import argparse
import json
from simple_maze_game.agent import play_maze_game
from simple_maze_game.config import (
    DEFAULT_LLM_MODEL,
    DEFAULT_MAZE_WIDTH,
    DEFAULT_MAZE_HEIGHT,
    DEFAULT_MAX_TURNS,
    DEFAULT_AGENT_START,
    DEFAULT_TARGET_POS,
    DEFAULT_OBSTACLES
)

def parse_pos(pos_str: str) -> tuple[int, int] | None:
    """Converts an 'x,y' string to a tuple of integers (x, y)."""
    try:
        parts = pos_str.split(',')
        if len(parts) == 2:
            return (int(parts[0].strip()), int(parts[1].strip()))
        else:
            raise argparse.ArgumentTypeError(f"Position '{pos_str}' must be in 'x,y' format.")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Position '{pos_str}' must contain valid integers.")

def main():
    """
    Parses command-line arguments and starts the Simple Maze Game.
    """
    parser = argparse.ArgumentParser(description="Run the Simple Maze Game with an LLM agent.")

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_LLM_MODEL,
        help=f"The LLM model to use (e.g., 'gpt-3.5-turbo'). Defaults to '{DEFAULT_LLM_MODEL}'."
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_MAZE_WIDTH,
        help=f"Width of the maze. Defaults to {DEFAULT_MAZE_WIDTH}."
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_MAZE_HEIGHT,
        help=f"Height of the maze. Defaults to {DEFAULT_MAZE_HEIGHT}."
    )
    parser.add_argument(
        "--agent_start",
        type=parse_pos, # Use custom type for parsing
        default=DEFAULT_AGENT_START,
        help=f"Agent's starting position in 'x,y' format. Defaults to '{DEFAULT_AGENT_START[0]},{DEFAULT_AGENT_START[1]}'."
    )
    parser.add_argument(
        "--target_pos",
        type=parse_pos, # Use custom type for parsing
        # Default target needs to be dynamic based on width/height if they are changed
        # So, we'll handle its default later if not provided by user
        default=None, # Will set to (width-1, height-1) if not specified
        help=f"Target position in 'x,y' format. Defaults to (width-1,height-1)."
    )
    parser.add_argument(
        "--obstacles",
        type=str, # Input as JSON string
        default=json.dumps(DEFAULT_OBSTACLES), # Default as JSON string
        help=f"Obstacle locations as a JSON string of a list of [x,y] tuples (e.g., '[[1,1],[2,2]]'). Defaults to a predefined list."
    )
    parser.add_argument(
        "--max_turns",
        type=int,
        default=10, # Changed default to 10
        help=f"Maximum number of game turns. Defaults to 10." # Updated help text
    )
    parser.add_argument(
        "--log_file",
        type=str,
        default="maze_game_log.jsonl",
        help="The name of the JSONL file to log game events. Defaults to 'maze_game_log.jsonl'."
    )

    args = parser.parse_args()

    # Handle default target_pos based on potentially user-defined width/height
    parsed_target_pos = args.target_pos
    if parsed_target_pos is None:
        parsed_target_pos = (args.width - 1, args.height - 1)

    # Parse obstacles from JSON string
    parsed_obstacles = []
    try:
        obstacles_list = json.loads(args.obstacles)
        if not isinstance(obstacles_list, list):
            raise ValueError("Obstacles JSON must be a list.")
        for obs in obstacles_list:
            if not (isinstance(obs, list) and len(obs) == 2 and isinstance(obs[0], int) and isinstance(obs[1], int)):
                raise ValueError("Each obstacle must be a list/tuple of two integers [x,y].")
            parsed_obstacles.append(tuple(obs)) # Convert to list of tuples
    except json.JSONDecodeError as e:
        parser.error(f"Invalid JSON format for --obstacles: {e}. Example: '[[1,1],[2,2]]'")
    except ValueError as e:
        parser.error(f"Invalid structure for --obstacles: {e}. Example: '[[1,1],[2,2]]'")


    print("--- Starting Simple Maze Game ---")
    print(f"Configuration:")
    print(f"  Model: '{args.model}'")
    print(f"  Maze Dimensions: {args.width}x{args.height}")
    print(f"  Agent Start: {args.agent_start}")
    print(f"  Target Position: {parsed_target_pos}")
    print(f"  Max Turns: {args.max_turns}")
    print(f"  Log File: '{args.log_file}'")
    # print(f"  Obstacles: {parsed_obstacles}") # Can be very long

    try:
        play_maze_game(
            llm_model=args.model,
            width=args.width,
            height=args.height,
            agent_start=args.agent_start,
            target_pos=parsed_target_pos,
            obstacles=parsed_obstacles,
            max_turns=args.max_turns,
            log_filename=args.log_file
        )
    except Exception as e:
        print(f"\nAn critical error occurred during game execution: {e}")
        # Consider logging this to a more persistent error log if needed
    finally:
        print("\n--- Simple Maze Game session finished. ---")
        print(f"Game log potentially saved to: {args.log_file}")

if __name__ == "__main__":
    main()
