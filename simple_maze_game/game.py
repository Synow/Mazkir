"""Main game logic for the Simple Maze Game."""
from .maze import Maze

class MazeGame:
    """Manages the game state and core mechanics for the Simple Maze Game."""

    def __init__(self, width: int = 10, height: int = 10, agent_start: tuple[int,int] = (0,0), target_pos: tuple[int,int] = (9,9), obstacles: list[tuple[int,int]] = None):
        """
        Initializes the Maze Game.

        Args:
            width: Width of the maze.
            height: Height of the maze.
            agent_start: Starting (x,y) position for the agent.
            target_pos: Target (x,y) position.
            obstacles: A list of (x,y) tuples for obstacle locations.
        """
        # Ensure target_pos is within bounds for default calculation
        actual_target_pos = target_pos
        if not (0 <= target_pos[0] < width and 0 <= target_pos[1] < height):
            print(f"Warning: Provided target_pos {target_pos} is out of bounds for width {width} and height {height}. Using ({width-1}, {height-1}) instead.")
            actual_target_pos = (width - 1, height - 1)
            
        self.maze = Maze(width, height, agent_start, actual_target_pos, obstacles if obstacles else [])
        self.turn_count = 0
        self.game_over = False
        self.max_turns = width * height * 2 # Sensible default
        
        # Initial score calculation
        self.score = -self.maze.calculate_manhattan_distance(self.maze.get_agent_position(), self.maze.get_target_position())

    def tool_move(self, direction: str) -> dict:
        """
        Attempts to move the agent in the specified direction.

        Args:
            direction: A string, one of 'up', 'down', 'left', 'right'.

        Returns:
            A dictionary containing the result of the move.
        """
        if self.game_over:
            return {
                "message": "Game is over. Cannot move.", 
                "new_position": self.maze.get_agent_position(), 
                "score": self.score, 
                "turn": self.turn_count, 
                "game_over": self.game_over
            }

        curr_x, curr_y = self.maze.get_agent_position()
        new_x, new_y = curr_x, curr_y

        if direction == 'up':
            new_y -= 1
        elif direction == 'down':
            new_y += 1
        elif direction == 'left':
            new_x -= 1
        elif direction == 'right':
            new_x += 1
        else:
            message = f"Invalid direction: {direction}. Choose from 'up', 'down', 'left', 'right'."
            # No turn penalty for invalid direction string, as it's a command formation error
            return {"message": message, "new_position": (curr_x, curr_y), "score": self.score, "turn": self.turn_count, "game_over": self.game_over}

        if self.maze.is_valid_move(new_x, new_y):
            self.maze.set_agent_position(new_x, new_y)
            self.score = -self.maze.calculate_manhattan_distance(self.maze.get_agent_position(), self.maze.get_target_position())
            message = f"Moved {direction} to ({new_x},{new_y}). Current score: {self.score}."

            if self.maze.get_agent_position() == self.maze.get_target_position():
                self.game_over = True
                message += " Congratulations! You reached the target!"
        else:
            message = f"Cannot move {direction} from ({curr_x},{curr_y}). Path blocked or out of bounds."
            # Score does not change if move is invalid

        self.turn_count += 1
        if self.turn_count >= self.max_turns and not self.game_over:
            self.game_over = True
            message += " Max turns reached. Game Over."
            # Recalculate score just in case, though it shouldn't change if move was invalid
            self.score = -self.maze.calculate_manhattan_distance(self.maze.get_agent_position(), self.maze.get_target_position())


        return {"message": message, "new_position": self.maze.get_agent_position(), "score": self.score, "turn": self.turn_count, "game_over": self.game_over}

    def get_status(self) -> dict:
        """
        Returns the current status of the game.
        """
        return {
            "agent_position": self.maze.get_agent_position(),
            "target_position": self.maze.get_target_position(),
            "score": self.score,
            "turn_count": self.turn_count,
            "game_over": self.game_over,
            "max_turns": self.max_turns,
            "maze_dimensions": (self.maze.width, self.maze.height),
            "obstacles": list(self.maze.obstacles) # Return a copy
        }

if __name__ == '__main__':
    print("Testing MazeGame Class...")
    
    # Test basic initialization
    game = MazeGame(width=5, height=5, agent_start=(0,0), target_pos=(4,4), obstacles=[(1,0)])
    status = game.get_status()
    assert status["agent_position"] == (0,0), "Initial agent position incorrect"
    assert status["target_position"] == (4,4), "Initial target position incorrect"
    assert status["score"] == -8, f"Initial score incorrect, expected -8, got {status['score']}" # Manhattan dist for (0,0) to (4,4) is 8
    assert status["turn_count"] == 0, "Initial turn count incorrect"
    assert not status["game_over"], "Game should not be over initially"
    assert status["maze_dimensions"] == (5,5), "Maze dimensions incorrect"
    assert status["obstacles"] == [(1,0)], "Obstacles incorrect"
    print("Initial status:", status)

    # Test valid move
    print("\nTesting valid move...")
    result = game.tool_move('down') # (0,0) -> (0,1)
    print("Move result:", result)
    assert result["new_position"] == (0,1), "Agent position not updated after valid move"
    assert result["score"] == -7, f"Score not updated correctly. Expected -7, got {result['score']}" # (0,1) to (4,4) is 7
    assert result["turn"] == 1, "Turn count not incremented"
    assert not result["game_over"], "Game should not be over"

    # Test invalid move (into obstacle)
    print("\nTesting invalid move (obstacle)...")
    result = game.tool_move('right') # Try to move from (0,1) to (1,1), but (1,0) is obstacle, this is actually (0,1) to (1,1)
    # Correction: previous move was to (0,1). Obstacle is (1,0). Moving 'right' from (0,1) is to (1,1). This should be valid.
    # Let's make the test clearer:
    # Agent is at (0,1). Obstacle at (1,0).
    # Try to move 'up' from (0,1) to (0,0) - valid
    # Try to move 'right' from (0,0) to (1,0) - invalid due to obstacle
    game.maze.set_agent_position((0,0)) # Reset agent for clarity
    game.turn_count = 1 # Simulate one move already made
    game.score = -game.maze.calculate_manhattan_distance(game.maze.get_agent_position(), game.maze.get_target_position())
    print(f"Reset agent to (0,0), score {game.score}, turn {game.turn_count}")

    result = game.tool_move('right') # Try to move from (0,0) to (1,0) - obstacle
    print("Move result (obstacle):", result)
    assert result["new_position"] == (0,0), "Agent position should not change after invalid move"
    assert result["score"] == -8, "Score should not change after invalid move" # Score from (0,0)
    assert result["turn"] == 2, "Turn count should increment even on invalid move"
    assert "Cannot move right" in result["message"], "Message incorrect for blocked move"

    # Test invalid move (out of bounds)
    print("\nTesting invalid move (bounds)...")
    result = game.tool_move('up') # From (0,0)
    print("Move result (bounds):", result)
    assert result["new_position"] == (0,0), "Agent position should not change after out of bounds move"
    assert result["score"] == -8, "Score should not change after out of bounds move"
    assert result["turn"] == 3, "Turn count should increment"
    assert "Cannot move up" in result["message"], "Message incorrect for out of bounds move"
    
    # Test invalid direction string
    print("\nTesting invalid direction string...")
    turn_before_invalid_dir = game.turn_count
    score_before_invalid_dir = game.score
    result = game.tool_move('diagonal')
    print("Move result (invalid direction):", result)
    assert result["new_position"] == (0,0), "Agent position should not change"
    assert result["score"] == score_before_invalid_dir, "Score should not change"
    assert result["turn"] == turn_before_invalid_dir, "Turn count should NOT increment for invalid direction string"
    assert "Invalid direction: diagonal" in result["message"], "Message incorrect for invalid direction"


    # Test reaching target
    print("\nTesting reaching target...")
    game_to_win = MazeGame(width=3, height=3, agent_start=(0,0), target_pos=(0,1))
    print("Initial win-game status:", game_to_win.get_status())
    result = game_to_win.tool_move('down')
    print("Move result (win):", result)
    assert result["new_position"] == (0,1), "Agent should be at target"
    assert result["score"] == 0, "Score should be 0 at target"
    assert result["game_over"], "Game should be over upon reaching target"
    assert "Congratulations! You reached the target!" in result["message"], "Win message incorrect"

    # Test max turns
    print("\nTesting max turns...")
    game_max_turns = MazeGame(width=2, height=1, agent_start=(0,0), target_pos=(1,0)) # Max turns = 2*1*2 = 4
    print(f"Max turns for this game: {game_max_turns.max_turns}")
    game_max_turns.tool_move('up') # Turn 1, invalid
    game_max_turns.tool_move('up') # Turn 2, invalid
    game_max_turns.tool_move('up') # Turn 3, invalid
    assert not game_max_turns.game_over, "Game should not be over before max turns"
    result = game_max_turns.tool_move('up') # Turn 4, invalid
    print("Move result (max_turns):", result)
    assert result["game_over"], "Game should be over after max turns"
    assert "Max turns reached" in result["message"], "Max turns message incorrect"
    assert result["turn"] == 4

    # Test moving when game is already over
    print("\nTesting move when game over...")
    assert game_to_win.game_over # game_to_win is already over
    pos_before = game_to_win.maze.get_agent_position()
    score_before = game_to_win.score
    turn_before = game_to_win.turn_count
    result = game_to_win.tool_move('up')
    print("Move result (already over):", result)
    assert result["new_position"] == pos_before, "Position should not change"
    assert result["score"] == score_before, "Score should not change"
    assert result["turn"] == turn_before, "Turn should not change"
    assert "Game is over. Cannot move." in result["message"], "Message for move when over incorrect"


    # Test target position adjustment if out of bounds in constructor
    print("\nTesting target position adjustment in constructor...")
    game_adj_target = MazeGame(width=5, height=5, agent_start=(0,0), target_pos=(10,10))
    status_adj = game_adj_target.get_status()
    assert status_adj["target_position"] == (4,4), f"Target position not adjusted. Expected (4,4), got {status_adj['target_position']}"
    print(f"Adjusted target position: {status_adj['target_position']}")

    print("\nMazeGame Class tests passed!")
