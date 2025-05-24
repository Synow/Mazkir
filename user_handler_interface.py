from abc import ABC, abstractmethod
from typing import Any, Callable

class BaseHandler(ABC):
    """
    Abstract base class for user interaction handlers.
    """

    def __init__(self, process_user_input_func: Callable[[str, str], str]):
        """
        Initializes the handler.

        Args:
            process_user_input_func: A callable that takes a user input string
                                     and a user_id string, and returns the assistant's
                                     response string. This is typically the 
                                     `process_user_input` function from mazkir.py.
        """
        self.process_user_input_func = process_user_input_func

    @abstractmethod
    def start(self) -> None:
        """
        Starts the handler (e.g., begins a CLI loop, starts polling for messages).
        """
        pass

    @abstractmethod
    async def send_message(self, user_id: str, message: str) -> None:
        """
        Sends a message to the specified user.
        For async handlers, this should be an async method.
        For sync handlers, this can be a regular method.
        """
        pass

    @abstractmethod
    def get_user_identifier(self, event: Any) -> str:
        """
        Extracts a unique user identifier from an incoming event or context.

        Args:
            event: The incoming event object (e.g., a Telegram update, a CLI session detail).

        Returns:
            A string representing the unique user identifier.
        """
        pass
