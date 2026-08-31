"""
Appliance Circularity Engine.
Models the degradation of appliance energy efficiency over time and calculates the replacement tipping point.
"""

from typing import Dict, Any, Optional
from src.services.embodied_carbon_tracker import EmbodiedCarbonTracker


class ApplianceCircularityEngine:
    """Analyzes the lifecycle carbon footprint of household appliances."""

    def __init__(self):
        self.tracker = EmbodiedCarbonTracker()
        # Annual efficiency degradation rate (e.g., 2% per year)
        self.degradation_rate = 0.02

    def evaluate_appliance(
        self, appliance_type: str, age_years: int, annual_usage_kwh: float
    ) -> Dict[str, Any]:
        """
        Evaluates an appliance's current carbon status and future trajectory.

        Args:
            appliance_type: The category of the appliance (e.g., "refrigerator").
            age_years: Current age of the appliance in years.
            annual_usage_kwh: Estimated annual energy consumption in kWh.
        """
        specs = self.tracker.get_appliance_specs(appliance_type)
        if not specs:
            raise ValueError(f"Unknown appliance type: {appliance_type}")

        # 1. Calculate current operational carbon (degraded efficiency)
        # As appliance ages, it uses more energy for the same output
        current_efficiency_factor = 1.0 + (age_years * self.degradation_rate)
        current_annual_kwh = annual_usage_kwh * current_efficiency_factor
        current_annual_carbon_kg = (
            current_annual_kwh * self.tracker.grid_carbon_intensity
        )

        # 2. Calculate new appliance operational carbon
        new_annual_kwh = annual_usage_kwh * specs["new_efficiency_multiplier"]
        new_annual_carbon_kg = new_annual_kwh * self.tracker.grid_carbon_intensity

        # 3. Calculate annual operational savings if replaced
        annual_operational_savings_kg = current_annual_carbon_kg - new_annual_carbon_kg

        # 4. Calculate Tipping Point (Years to break even on embodied carbon)
        embodied_cost_kg = specs["embodied_carbon_kg"]
        if annual_operational_savings_kg > 0:
            tipping_point_years = embodied_cost_kg / annual_operational_savings_kg
        else:
            tipping_point_years = float("inf")  # Never breaks even

        # 5. Calculate Circularity Score (0-100)
        # Higher score = better to keep, Lower score = better to replace/recycle
        expected_lifespan = specs["expected_lifespan_years"]
        if age_years >= expected_lifespan:
            circularity_score = 20.0  # End of life
        elif tipping_point_years < (expected_lifespan - age_years):
            # If it will break even before the new one dies, it's a good time to replace
            circularity_score = 40.0
        else:
            # Keep it, it's still efficient enough
            remaining_life_ratio = (expected_lifespan - age_years) / expected_lifespan
            circularity_score = 40.0 + (remaining_life_ratio * 60.0)

        return {
            "appliance_type": appliance_type,
            "age_years": age_years,
            "current_annual_carbon_kg": round(current_annual_carbon_kg, 2),
            "new_annual_carbon_kg": round(new_annual_carbon_kg, 2),
            "annual_operational_savings_kg": round(annual_operational_savings_kg, 2),
            "embodied_carbon_cost_kg": embodied_cost_kg,
            "tipping_point_years": round(tipping_point_years, 1)
            if tipping_point_years != float("inf")
            else "Never",
            "circularity_score": round(circularity_score, 1),
            "recommendation": self._generate_recommendation(
                circularity_score, tipping_point_years, age_years, expected_lifespan
            ),
            "end_of_life_recycling_value_kg": specs["recycling_avoidance_kg"],
        }

    def _generate_recommendation(
        self, score: float, tipping_point: float, age: int, lifespan: int
    ) -> str:
        """Generates a human-readable recommendation based on the analysis."""
        if age >= lifespan:
            return "🔴 **End of Life:** This appliance has exceeded its expected lifespan. Prioritize certified recycling to recover materials and avoid landfill emissions."
        elif score < 50:
            return "🟡 **Consider Upgrading:** The operational inefficiency is high. Replacing it with a high-efficiency model will offset the embodied carbon within a reasonable timeframe."
        else:
            return "🟢 **Keep and Maintain:** This appliance is still operating efficiently. Focus on regular maintenance to prolong its lifespan and delay the embodied carbon cost of replacement."
