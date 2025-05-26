"""Game configuration settings."""

DEFAULT_LLM_MODEL = "gpt-3.5-turbo" # Example, ensure this is accessible via litellm
DEFAULT_LLM_MODEL = "vertex_ai/gemini-2.5-flash-preview-04-17"  # Or any other preferred default model

LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "scan_environment",
            "description": "Scans the current location for biome type, description, resources, points of interest, and available exits.",
            "parameters": {
                 "type": "object",
                 "properties": {} # No parameters needed for scan_environment
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_to_location",
            "description": "Moves the player to a new location in the specified direction (north, south, east, west).",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "The direction to move (e.g., 'north', 'south', 'east', 'west').",
                        "enum": ["north", "south", "east", "west"]
                    }
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gather_resource",
            "description": "Gathers a specified resource from the current location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_name": {
                        "type": "string",
                        "description": "The name of the resource to gather (e.g., 'food', 'water', 'metal', 'crystal', 'fiber')."
                        # Consider adding enum here if resources are fixed and known
                    }
                },
                "required": ["resource_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "craft_item",
            "description": "Crafts an item using resources from the player's inventory. Check recipes before crafting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "The name of the item to craft (e.g., 'shelter', 'water_purifier', 'makeshift_axe')."
                        # Consider adding enum for craftable items
                    }
                },
                "required": ["item_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "use_item",
            "description": "Uses an item from the player's inventory. Check inventory for usable items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "The name of the item to use (e.g., 'food_ration', 'purified_water', 'medkit')."
                        # Consider adding enum for usable items
                    }
                },
                "required": ["item_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rest",
            "description": "Allows the player to rest, recovering some health but consuming hunger and thirst. Resting is more effective if a shelter is available.",
            "parameters": {
                "type": "object",
                "properties": {} # No parameters needed for rest
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_artifact",
            "description": "Analyzes an alien artifact found at the current location to gain knowledge for the rescue beacon.",
            "parameters": {
                "type": "object",
                "properties": {} # No parameters needed for analyze_artifact
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_status",
            "description": "Checks the player's current health, hunger, thirst, inventory, location, beacon progress, and artifacts analyzed.",
            "parameters": {
                "type": "object",
                "properties": {} # No parameters needed for check_status
            }
        }
    }
]

if __name__ == '__main__':
    import json
    print(f"Default LLM Model: {DEFAULT_LLM_MODEL}")
    print("\nLLM Tools (JSON representation):")
    print(json.dumps(LLM_TOOLS, indent=2))
    print(f"\nTotal tools: {len(LLM_TOOLS)}")

    # Validate that parameters are actual JSON objects if not empty
    for tool_def in LLM_TOOLS:
        func_name = tool_def["function"]["name"]
        params = tool_def["function"]["parameters"]
        if not isinstance(params, dict):
            print(f"Error: Parameters for {func_name} is not a dict: {params}")
        if "properties" not in params and params != {}: # Allow empty object for no params
             print(f"Warning: Parameters for {func_name} might be missing 'properties' field, currently: {params}")
        elif "properties" in params and not isinstance(params["properties"], dict):
            print(f"Error: 'properties' for {func_name} is not a dict: {params['properties']}")

    # Test that scan_environment has an empty properties object
    scan_tool = next(t for t in LLM_TOOLS if t['function']['name'] == 'scan_environment')
    assert scan_tool['function']['parameters']['properties'] == {}, "scan_environment params.properties should be empty object"
    assert scan_tool['function']['parameters']['type'] == "object", "scan_environment params.type should be object"

    rest_tool = next(t for t in LLM_TOOLS if t['function']['name'] == 'rest')
    assert rest_tool['function']['parameters']['properties'] == {}, "rest params.properties should be empty object"
    assert rest_tool['function']['parameters']['type'] == "object", "rest params.type should be object"

    analyze_tool = next(t for t in LLM_TOOLS if t['function']['name'] == 'analyze_artifact')
    assert analyze_tool['function']['parameters']['properties'] == {}, "analyze_artifact params.properties should be empty object"
    assert analyze_tool['function']['parameters']['type'] == "object", "analyze_tool params.type should be object"

    check_status_tool = next(t for t in LLM_TOOLS if t['function']['name'] == 'check_status')
    assert check_status_tool['function']['parameters']['properties'] == {}, "check_status params.properties should be empty object"
    assert check_status_tool['function']['parameters']['type'] == "object", "check_status_tool params.type should be object"

    print("\nConfig file structure seems valid.")
