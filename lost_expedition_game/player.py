"""Player class and related functions."""

class Player:
    """Represents the player in the Lost Expedition game."""

    def __init__(self, location_x: int, location_y: int, health: int = 100, hunger: int = 100, thirst: int = 100):
        """
        Initializes the Player.

        Args:
            location_x: The player's starting x-coordinate.
            location_y: The player's starting y-coordinate.
            health: The player's starting health (default 100).
            hunger: The player's starting hunger (default 100).
            thirst: The player's starting thirst (default 100).
        """
        self.health = health
        self.hunger = hunger
        self.thirst = thirst
        self.location_x = location_x
        self.location_y = location_y
        self.inventory = {}  # e.g., {"food_ration": 2, "water_bottle": 1}

        self.max_health = 100
        self.max_hunger = 100
        self.max_thirst = 100

    def change_health(self, amount: int):
        """
        Changes the player's health by the given amount.
        Health is capped between 0 and max_health.
        """
        self.health += amount
        if self.health > self.max_health:
            self.health = self.max_health
        elif self.health < 0:
            self.health = 0

    def change_hunger(self, amount: int):
        """
        Changes the player's hunger by the given amount.
        Hunger is capped between 0 and max_hunger.
        """
        self.hunger += amount
        if self.hunger > self.max_hunger:
            self.hunger = self.max_hunger
        elif self.hunger < 0:
            self.hunger = 0

    def change_thirst(self, amount: int):
        """
        Changes the player's thirst by the given amount.
        Thirst is capped between 0 and max_thirst.
        """
        self.thirst += amount
        if self.thirst > self.max_thirst:
            self.thirst = self.max_thirst
        elif self.thirst < 0:
            self.thirst = 0

    def add_to_inventory(self, item_name: str, quantity: int):
        """Adds a given quantity of an item to the player's inventory."""
        if quantity <= 0:
            return
        self.inventory[item_name] = self.inventory.get(item_name, 0) + quantity

    def remove_from_inventory(self, item_name: str, quantity: int) -> bool:
        """
        Removes a given quantity of an item from the player's inventory.

        Args:
            item_name: The name of the item to remove.
            quantity: The quantity to remove.

        Returns:
            True if the item was successfully removed, False otherwise (e.g., not enough items).
        """
        if quantity <= 0:
            return True # Nothing to remove
        if item_name not in self.inventory or self.inventory[item_name] < quantity:
            return False  # Not enough items or item not present

        self.inventory[item_name] -= quantity
        if self.inventory[item_name] == 0:
            del self.inventory[item_name]
        return True

    def __str__(self):
        return (f"Player Status: HP={self.health}/{self.max_health}, "
                f"Hunger={self.hunger}/{self.max_hunger}, Thirst={self.thirst}/{self.max_thirst}\n"
                f"Location: ({self.location_x}, {self.location_y})\n"
                f"Inventory: {self.inventory}")

if __name__ == '__main__':
    # Example Usage
    player = Player(location_x=0, location_y=0)
    print(player)
    assert player.health == 100 and player.hunger == 100 and player.thirst == 100, "Initial stats incorrect"

    player.change_health(-10)
    player.change_hunger(-20)
    assert player.health == 90, "Health decrease failed"
    assert player.hunger == 80, "Hunger decrease failed"
    print(player)

    player.add_to_inventory("food_ration", 3)
    player.add_to_inventory("water_bottle", 2)
    assert player.inventory["food_ration"] == 3, "Add inventory failed"
    print(player)

    player.remove_from_inventory("food_ration", 1)
    assert player.inventory["food_ration"] == 2, "Remove inventory failed"
    print(player)

    player.change_thirst(30) # Drink
    assert player.thirst == 100, "Thirst increase and cap failed (expected 100)" # Was 100, add 30, should cap at 100
    print(player)

    # Test capping at max
    player.change_health(200) # Overheal
    assert player.health == player.max_health, f"Health not capped at max_health. Got {player.health}"
    player.change_hunger(50)
    assert player.hunger == player.max_hunger, f"Hunger not capped at max_hunger. Got {player.hunger}"
    player.change_thirst(50)
    assert player.thirst == player.max_thirst, f"Thirst not capped at max_thirst. Got {player.thirst}"
    print(player)

    # Test capping at 0
    player.change_health(-200)
    assert player.health == 0, "Health not capped at 0"
    player.change_hunger(-200)
    assert player.hunger == 0, "Hunger not capped at 0"
    player.change_thirst(-200)
    assert player.thirst == 0, "Thirst not capped at 0"
    print(f"After capping at 0: {player}")


    # Test inventory removal edge cases
    removed_non_existent = player.remove_from_inventory("non_existent_item", 1)
    assert not removed_non_existent, "Should not remove non_existent_item"
    assert "non_existent_item" not in player.inventory, "non_existent_item should not be in inventory"

    player.add_to_inventory("test_item", 2)
    removed_too_many = player.remove_from_inventory("test_item", 5) # Not enough
    assert not removed_too_many, "Should not remove more items than present"
    assert player.inventory["test_item"] == 2, "test_item quantity should be unchanged after failed removal"
    
    removed_all = player.remove_from_inventory("test_item", 2)
    assert removed_all, "Should successfully remove all items"
    assert "test_item" not in player.inventory, "test_item should be deleted from inventory after removing all"
    print(player)
    print("\nPlayer class tests passed!")
