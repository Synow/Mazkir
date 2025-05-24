"""Maze generation and representation for the Simple Maze Game."""

class Maze:
    """Represents the maze structure, agent, and target."""

    def __init__(self, width: int, height: int, agent_start_pos: tuple[int, int], target_pos: tuple[int, int], obstacles: list[tuple[int, int]] = None):
        """
        Initializes the Maze.

        Args:
            width: The width of the maze.
            height: The height of the maze.
            agent_start_pos: The agent's starting (x,y) position.
            target_pos: The target's (x,y) position.
            obstacles: A list of (x,y) tuples representing obstacle locations. Defaults to an empty list.
        """
        if not (0 <= agent_start_pos[0] < width and 0 <= agent_start_pos[1] < height):
            raise ValueError("Agent start position is outside maze boundaries.")
        if not (0 <= target_pos[0] < width and 0 <= target_pos[1] < height):
            raise ValueError("Target position is outside maze boundaries.")

        self.width = width
        self.height = height
        self.agent_pos = agent_start_pos
        self.target_pos = target_pos
        self.obstacles = obstacles if obstacles else []

        if self.target_pos in self.obstacles:
            raise ValueError("Target position cannot be an obstacle.")
        if self.agent_pos in self.obstacles:
            # This might be allowed if the game wants to make it impossible from the start,
            # but generally, agent should not start in an obstacle.
            # For this simple game, let's raise an error.
            raise ValueError("Agent start position cannot be an obstacle.")


    def set_agent_position(self, x: int, y: int):
        """Updates the agent's current position."""
        self.agent_pos = (x, y)

    def get_agent_position(self) -> tuple[int, int]:
        """Returns the agent's current (x,y) position."""
        return self.agent_pos

    def get_target_position(self) -> tuple[int, int]:
        """Returns the target's (x,y) position."""
        return self.target_pos

    def is_valid_move(self, x: int, y: int) -> bool:
        """
        Checks if the given (x,y) coordinates are a valid move for the agent.

        Args:
            x: The x-coordinate of the potential move.
            y: The y-coordinate of the potential move.

        Returns:
            True if the move is valid, False otherwise.
        """
        # Check bounds
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        # Check obstacles
        if (x, y) in self.obstacles:
            return False
        return True

    def calculate_manhattan_distance(self, pos1: tuple[int, int], pos2: tuple[int, int]) -> int:
        """
        Calculates the Manhattan distance between two points.

        Args:
            pos1: The first (x,y) tuple.
            pos2: The second (x,y) tuple.

        Returns:
            The Manhattan distance.
        """
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

if __name__ == '__main__':
    # Example Usage and Basic Tests
    print("Testing Maze Class...")
    try:
        maze = Maze(width=5, height=5, agent_start_pos=(0,0), target_pos=(4,4), obstacles=[(1,1), (2,2)])
        print(f"Agent at: {maze.get_agent_position()}, Target at: {maze.get_target_position()}")
        assert maze.get_agent_position() == (0,0)
        assert maze.get_target_position() == (4,4)

        # Test valid moves
        assert maze.is_valid_move(0,1) == True, "Move (0,1) should be valid"
        assert maze.is_valid_move(1,0) == True, "Move (1,0) should be valid"

        # Test invalid moves (out of bounds)
        assert maze.is_valid_move(-1,0) == False, "Move (-1,0) should be invalid (bounds)"
        assert maze.is_valid_move(0,-1) == False, "Move (0,-1) should be invalid (bounds)"
        assert maze.is_valid_move(5,4) == False, "Move (5,4) should be invalid (bounds)"
        assert maze.is_valid_move(4,5) == False, "Move (4,5) should be invalid (bounds)"

        # Test invalid moves (obstacles)
        assert maze.is_valid_move(1,1) == False, "Move (1,1) should be invalid (obstacle)"
        assert maze.is_valid_move(2,2) == False, "Move (2,2) should be invalid (obstacle)"

        maze.set_agent_position(1,0)
        assert maze.get_agent_position() == (1,0), "set_agent_position failed"
        print(f"Agent moved to: {maze.get_agent_position()}")

        # Test Manhattan distance
        dist = maze.calculate_manhattan_distance((0,0), (4,4))
        assert dist == 8, f"Manhattan distance (0,0) to (4,4) should be 8, got {dist}"
        dist_agent_target = maze.calculate_manhattan_distance(maze.get_agent_position(), maze.get_target_position())
        assert dist_agent_target == 7, f"Manhattan distance agent (1,0) to target (4,4) should be 7, got {dist_agent_target}"
        print(f"Distance from agent (1,0) to target (4,4): {dist_agent_target}")

        # Test initialization errors
        try:
            Maze(5,5, (5,5), (4,4)) # Agent out of bounds
            assert False, "Agent out of bounds error not raised"
        except ValueError as e:
            print(f"Caught expected error: {e}")

        try:
            Maze(5,5, (0,0), (1,1), obstacles=[(1,1)]) # Target in obstacle
            assert False, "Target in obstacle error not raised"
        except ValueError as e:
            print(f"Caught expected error: {e}")
        
        try:
            Maze(5,5, (1,1), (4,4), obstacles=[(1,1)]) # Agent start in obstacle
            assert False, "Agent start in obstacle error not raised"
        except ValueError as e:
            print(f"Caught expected error: {e}")


        print("Maze Class tests passed!")

    except Exception as e:
        print(f"An error occurred during Maze class testing: {e}")

    print("\nTesting Maze with no obstacles...")
    maze_no_obs = Maze(width=3, height=3, agent_start_pos=(0,0), target_pos=(2,2))
    assert maze_no_obs.is_valid_move(1,1) == True, "Move (1,1) should be valid in no-obstacle maze"
    print("No obstacle maze test passed.")
