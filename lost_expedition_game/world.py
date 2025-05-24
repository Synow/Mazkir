"""World representation and generation."""
import random

BIOMES = {
    "CrashSite": {
        "resources": {"metal": 10, "fiber": 5, "food_ration": 2, "water_bottle": 2}, # Specific initial supplies
        "dangers": [],
        "artifact_chance": 0.1,
        "description": "The wreckage of your ship, a grim reminder of your predicament."
    },
    "Forest": {
        "resources": {"food": 4, "water": 2, "fiber": 5, "metal": 1},
        "dangers": ["wildlife_encounter", "thick_undergrowth"],
        "artifact_chance": 0.15,
        "description": "A dense forest, teeming with unknown life. Resources might be plentiful, but so are dangers."
    },
    "Desert": {
        "resources": {"crystal": 3, "metal": 2, "food": 1}, # Water is scarce or non-existent
        "dangers": ["sandstorm", "extreme_heat"],
        "artifact_chance": 0.2,
        "description": "A vast, arid desert. Survival here will be a true test."
    },
    "Mountains": {
        "resources": {"metal": 4, "crystal": 5, "water": 1}, # Food is scarce
        "dangers": ["rock_slide", "treacherous_paths", "cold_nights"],
        "artifact_chance": 0.25,
        "description": "Towering mountains that are difficult to traverse but may hold valuable crystals."
    },
    "River": {
        "resources": {"water": 5, "food": 3, "fiber": 2},
        "dangers": ["strong_currents", "water_predators"],
        "artifact_chance": 0.1,
        "description": "A flowing river, a vital source of water, but potentially hazardous."
    },
    "Plains": {
        "resources": {"food": 3, "fiber": 3, "metal": 1},
        "dangers": ["predator_packs"],
        "artifact_chance": 0.12,
        "description": "Open plains, offering good visibility but also making you an easy target."
    }
}

def generate_world_map(width: int, height: int) -> list[list[dict]]:
    """
    Creates a 2D list (grid) of location dictionaries representing the game world.

    Args:
        width: The width of the map.
        height: The height of the map.

    Returns:
        A list of lists, where each inner list is a row and each element
        is a dictionary representing a location.
    """
    if width <= 0 or height <= 0:
        raise ValueError("Map dimensions must be positive integers.")

    world_map = [[{} for _ in range(width)] for _ in range(height)]
    available_biomes = list(BIOMES.keys())
    available_biomes.remove("CrashSite") # CrashSite is special

    # Place CrashSite (e.g., near the center)
    crash_site_x = width // 2
    crash_site_y = height // 2

    for r in range(height):
        for c in range(width):
            location = {}
            if r == crash_site_y and c == crash_site_x:
                biome_name = "CrashSite"
            else:
                biome_name = random.choice(available_biomes)

            biome_data = BIOMES[biome_name]
            location["biome_name"] = biome_name
            location["description"] = biome_data["description"] # Add biome description

            # Randomize resources for the location based on biome defaults
            location_resources = {}
            for resource, max_qty in biome_data["resources"].items():
                if max_qty > 0 : # only add if there's a chance of finding it
                    location_resources[resource] = random.randint(0, max_qty)
            location["resources"] = location_resources

            location["has_artifact"] = random.random() < biome_data["artifact_chance"]
            location["artifact_analyzed_here"] = False
            location["visited"] = False # Will be set to True when player visits
            location["dangers"] = list(biome_data["dangers"]) # Copy dangers

            # Determine exits
            exits = []
            if r > 0:
                exits.append("north")
            if r < height - 1:
                exits.append("south")
            if c > 0:
                exits.append("west")
            if c < width - 1:
                exits.append("east")
            location["exits"] = exits

            world_map[r][c] = location

    return world_map

if __name__ == '__main__':
    test_map = generate_world_map(5, 5)
    for r_idx, row in enumerate(test_map):
        for c_idx, loc in enumerate(row):
            print(f"Location ({c_idx}, {r_idx}): Biome: {loc['biome_name']}, Resources: {loc['resources']}, Exits: {loc['exits']}, Artifact: {loc['has_artifact']}")
    print(f"\nCrash Site Details: {test_map[2][2]}")

    test_map_small = generate_world_map(1,1) # Edge case
    print(f"\nLocation (0,0) small map: Biome: {test_map_small[0][0]['biome_name']}, Exits: {test_map_small[0][0]['exits']}")

    try:
        generate_world_map(0,0)
    except ValueError as e:
        print(f"\nError for 0,0 map: {e}")
