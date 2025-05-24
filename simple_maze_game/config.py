"""Configuration settings for the Simple Maze Game."""

DEFAULT_LLM_MODEL = "gpt-3.5-turbo"

LLM_TOOLS_MAZE = [
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "Move the agent in the maze. The agent tries to reach the target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "Direction to move the agent.",
                        "enum": ["up", "down", "left", "right"]
                    }
                },
                "required": ["direction"]
            }
        }
    }
]

# Default game settings
DEFAULT_MAZE_WIDTH = 10
DEFAULT_MAZE_HEIGHT = 10
DEFAULT_MAX_TURNS = 10 # Enforce a 10-turn limit
DEFAULT_AGENT_START = (0, 0) # Default start position
DEFAULT_TARGET_POS = (DEFAULT_MAZE_WIDTH -1, DEFAULT_MAZE_HEIGHT -1) # Default target position

# Example obstacles: [(1,1), (2,2), (3,1)]
# For a 10x10 maze, some example obstacles that create a bit of a challenge:
DEFAULT_OBSTACLES = [
    (1,0), (1,1), (1,2), (1,3), (1,4), (1,5), (1,6),
    (3,3), (3,4), (3,5), (3,6), (3,7), (3,8), (3,9),
    (5,0), (5,1), (5,2), (5,3), (5,4), (5,5),
    (7,2), (7,3), (7,4), (7,5), (7,6), (7,7), (7,8),
    (8,2) # Creates a narrow passage
]


if __name__ == '__main__':
    import json
    print(f"Default LLM Model: {DEFAULT_LLM_MODEL}")
    print("\nLLM Tools for Maze Game (JSON representation):")
    print(json.dumps(LLM_TOOLS_MAZE, indent=2))
    print(f"\nDefault Maze Width: {DEFAULT_MAZE_WIDTH}")
    print(f"Default Maze Height: {DEFAULT_MAZE_HEIGHT}")
    print(f"Default Max Turns: {DEFAULT_MAX_TURNS}")
    print(f"Default Agent Start: {DEFAULT_AGENT_START}")
    print(f"Default Target Position: {DEFAULT_TARGET_POS}") # Recalculated if width/height change
    print(f"Default Obstacles: {DEFAULT_OBSTACLES}")

    # Ensure default target is within default dimensions
    assert 0 <= DEFAULT_TARGET_POS[0] < DEFAULT_MAZE_WIDTH
    assert 0 <= DEFAULT_TARGET_POS[1] < DEFAULT_MAZE_HEIGHT
    # Ensure default start is within default dimensions
    assert 0 <= DEFAULT_AGENT_START[0] < DEFAULT_MAZE_WIDTH
    assert 0 <= DEFAULT_AGENT_START[1] < DEFAULT_MAZE_HEIGHT
    print("\nConfig settings appear consistent.")
