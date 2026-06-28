from mcp.server.fastmcp import FastMCP

mcp = FastMCP("nutripulse-mcp")

@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> str:
    """Calculate Body Mass Index (BMI) and health category."""
    if height_m <= 0:
        return "Height must be greater than 0."
    bmi = weight_kg / (height_m ** 2)
    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal weight"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"
    return f"BMI: {bmi:.1f} ({category})"

@mcp.tool()
def get_macronutrient_targets(goal: str, calories: int) -> str:
    """Calculate daily protein, carbs, and fat targets based on fitness goal and target calories."""
    goal_clean = goal.lower().strip()
    if goal_clean in ["muscle_gain", "bulking"]:
        p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
    elif goal_clean in ["fat_loss", "cutting"]:
        p_pct, c_pct, f_pct = 0.40, 0.30, 0.30
    else:
        p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    
    p_g = int((calories * p_pct) / 4)
    c_g = int((calories * c_pct) / 4)
    f_g = int((calories * f_pct) / 9)
    return f"Target Macros for {calories} kcal ({goal_clean}): Protein {p_g}g, Carbs {c_g}g, Fat {f_g}g."

@mcp.tool()
def search_recipes(dietary_preference: str, max_calories: int) -> str:
    """Search healthy recipe ideas matching dietary preferences and calorie ceiling."""
    recipes = [
        {"name": "Mediterranean Quinoa Salad", "diet": "vegetarian", "cals": 420, "protein": "14g"},
        {"name": "Grilled Salmon with Asparagus", "diet": "pescatarian", "cals": 510, "protein": "42g"},
        {"name": "High-Protein Chicken & Avocado Wrap", "diet": "high-protein", "cals": 480, "protein": "38g"},
        {"name": "Tofu Vegetable Stir-Fry", "diet": "vegan", "cals": 360, "protein": "18g"}
    ]
    matching = [r for r in recipes if r["cals"] <= max_calories]
    if not matching:
        return f"No recipes found under {max_calories} kcal. Try increasing calorie limit."
    return f"Recommended Recipes: {matching}"

@mcp.tool()
def log_daily_water_intake(liters: float) -> str:
    """Log daily hydration intake in liters and verify against daily target of 2.5L."""
    remaining = 2.5 - liters
    status = "Daily hydration goal achieved!" if remaining <= 0 else f"Progress: {liters}L logged. Drink {remaining:.1f}L more today."
    return status

if __name__ == "__main__":
    mcp.run()
