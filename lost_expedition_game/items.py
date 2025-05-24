"""Item definitions and management."""

CRAFTABLE_ITEMS = {
    "shelter": {"fiber": 10, "metal": 5},
    "water_purifier": {"metal": 5, "crystal": 3, "fiber": 5},
    "scanner_upgrade": {"crystal": 10, "metal": 8},
    "beacon_component": {"metal": 15, "crystal": 10, "fiber": 5},
    # Basic tools
    "makeshift_axe": {"metal": 3, "fiber": 2}, # Helps gather fiber/wood (not explicitly a resource yet)
    "makeshift_pickaxe": {"metal": 4, "fiber": 2}, # Helps gather metal/crystal
}

USABLE_ITEMS = {
    "food_ration": {"hunger_restored": 20},
    "purified_water": {"thirst_restored": 20},
    "medkit": {"health_restored": 30},
    # Special items, effects to be defined in game logic
    "artifact_data": {"description": "Contains data from an alien artifact."},
    "beacon_component": {"description": "A component for the rescue beacon."},
}

# Placeholder for items that might be gathered directly, not crafted or "used" in the typical sense
# but are resources for crafting.
RESOURCE_ITEMS = [
    "food", # raw, needs processing or implies "edible found food"
    "water", # raw, needs purification
    "metal",
    "crystal",
    "fiber",
]

if __name__ == '__main__':
    print("Craftable Items:")
    for item, recipe in CRAFTABLE_ITEMS.items():
        print(f"  {item}: {recipe}")

    print("\nUsable Items:")
    for item, effect in USABLE_ITEMS.items():
        print(f"  {item}: {effect}")

    print("\nResource Items:")
    print(f"  {RESOURCE_ITEMS}")
