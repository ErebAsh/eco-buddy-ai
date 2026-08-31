import os
import logging
import json
import math
from datetime import datetime, timezone
import calendar
from typing import Any

logger = logging.getLogger(__name__)
from src.carbon.data_lineage import LineageBuilder, CategoryLineage
from src.core.config import (
    ECO_SCORE_BASELINE, ECO_SCORE_SENSITIVITY, CATEGORY_WEIGHTS,
    VALID_TRANSPORT, VALID_DIET, VALID_REGIONS,
    MAX_DISTANCE, MAX_ELECTRICITY, MAX_FLIGHTS,
    TRANSPORT_EMISSION_FACTORS, DIET_EMISSION_FACTORS,
    normalize_diet,
)
from src.core.cache import cached
from src.core.cache_config import TTL_EXTERNAL_API, CACHE_CATEGORY_API
from src.carbon.emission_factors import provenance_block, resolve_factor_set, factor_uncertainty_percent
from src.core.dependency_graph import DependencyGraph
from src.core.incremental_calculator import IncrementalCalculator
@cached(ttl=TTL_EXTERNAL_API, category=CACHE_CATEGORY_API)
def fetch_emission_factors(region: str) -> dict:
    """
    Fetches dynamic emission factors from a third-party Carbon API.
    Provides graceful fallback to static factors if the API fails.
    """
    # Static fallbacks
    factors = {
        "electricity": 0.82, # kg CO2 per kWh
        "flight": 250.0,     # kg CO2 per flight
        "is_dynamic": False
    }
    
    api_key = os.environ.get("CARBON_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return factors
        
    try:
        import requests
        from src.core.request_logging import log_api_request
        url = "https://api.climatiq.io/data/v1/estimate"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        payload = {
            "emission_factor": {
                "activity_id": "electricity-energy_source_grid_mix",
                "region": region if region != "Global" else "earth"
            },
            "parameters": {"energy": 1, "energy_unit": "kWh"}
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        log_api_request("POST", url, headers=headers, status_code=response.status_code)
        if response.status_code == 200:
            data = response.json()
            factors["electricity"] = data.get("co2e", factors["electricity"])
            factors["is_dynamic"] = True
            
        flight_payload = {
            "emission_factor": {
                "activity_id": "passenger_flight-route_type_domestic",
                "region": region if region != "Global" else "earth"
            },
            "parameters": {"passengers": 1}
        }
        f_response = requests.post(url, json=flight_payload, headers=headers, timeout=5)
        log_api_request("POST", url, headers=headers, status_code=f_response.status_code)
        if f_response.status_code == 200:
            f_data = f_response.json()
            factors["flight"] = f_data.get("co2e", factors["flight"])
            factors["is_dynamic"] = True
            
    except Exception:
        logger.exception("API Error, falling back to static factors")        
    return factors


def validate_footprint_inputs(transport: str, distance: float, electricity: float, diet: str,
                              flights: int, region: str) -> tuple[str, float, float, int, str]:
    """
    Validates and normalizes footprint calculation parameters.

    Returns:
        tuple: (normalized_diet, distance_float, electricity_float, flights_int, validated_region)
    """
    diet = normalize_diet(diet)

    if transport not in TRANSPORT_EMISSION_FACTORS:
        raise ValueError(
            f"Invalid transport '{transport}'. Must be one of: {', '.join(sorted(TRANSPORT_EMISSION_FACTORS.keys()))}"
        )
    if diet not in DIET_EMISSION_FACTORS:
        raise ValueError(
            f"Invalid diet '{diet}'. Must be one of: {', '.join(sorted(DIET_EMISSION_FACTORS.keys()))}"
        )

    if region not in VALID_REGIONS:
        region = "Global"

    try:
        distance = float(distance)
    except (TypeError, ValueError):
        raise ValueError("distance must be a number")
    distance = max(0.0, min(distance, MAX_DISTANCE))

    try:
        electricity = float(electricity)
    except (TypeError, ValueError):
        raise ValueError("electricity must be a number")
    electricity = max(0.0, min(electricity, MAX_ELECTRICITY))

    try:
        flights = int(flights)
    except (TypeError, ValueError):
        raise ValueError("flights must be an integer")
    flights = max(0, min(flights, MAX_FLIGHTS))

    return diet, distance, electricity, flights, region


def calculate_category_emissions(transport: str, distance: float, electricity: float, diet: str,
                                 flights: int,
                                 dynamic_factors: dict[str, Any],
                                 confidence_tracker: Any = None,
                                 lineage_builder: Any = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Calculates carbon emissions per activity category (Transport, Electricity, Diet, Flights).

    Returns:
        tuple: (contributors_dict, raw_emissions_dict, emission_factors_dict)
    """
    transport_factor = TRANSPORT_EMISSION_FACTORS[transport]
    
    # Build lineage for transport
    transport_input_node = lineage_builder.create_input_node(
        "transport", distance, "km/day", f"Daily distance by {transport}"
    )
    transport_factor_node = lineage_builder.create_factor_lookup_node(
        "transport", transport_factor, "kg CO2/km", "static-v1", "EcoBuddy-builtin",
        f"Transport factor for {transport}"
    )
    transport_calc_node = lineage_builder.create_calculation_node(
        "transport", transport_factor * distance * 365, "daily_km * factor * 365",
        [transport_input_node, transport_factor_node],
        f"{distance} km/day * {transport_factor} * 365 days"
    )
    transport_lineage = lineage_builder.build_category_lineage(
        "transport", distance, "km/day", transport_factor * distance * 365,
        transport_factor, "kg CO2/km", "static-v1", "EcoBuddy-builtin",
        [transport_input_node, transport_factor_node, transport_calc_node]
    )
    category_lineages["transport"] = transport_lineage
    
    transport_emission = transport_factor * distance * 365
    elec_factor = dynamic_factors["electricity"]
    
    # Build lineage for electricity
    elec_input_node = lineage_builder.create_input_node(
        "electricity", electricity, "kWh/month", "Monthly electricity consumption"
    )
    elec_factor_node = lineage_builder.create_factor_lookup_node(
        "electricity", elec_factor, "kg CO2/kWh", dynamic_factors.get("factor_version", "static-v1"),
        "Climatiq API" if dynamic_factors.get("is_dynamic") else "EcoBuddy-builtin",
        f"Electricity emission factor"
    )
    elec_calc_node = lineage_builder.create_calculation_node(
        "electricity", electricity * elec_factor * 12, "monthly_kWh * factor * 12",
        [elec_input_node, elec_factor_node],
        f"{electricity} kWh/month * {elec_factor} * 12 months"
    )
    elec_lineage = lineage_builder.build_category_lineage(
        "electricity", electricity, "kWh/month", electricity * elec_factor * 12,
        elec_factor, "kg CO2/kWh", 
        dynamic_factors.get("factor_version", "static-v1"),
        "Climatiq API" if dynamic_factors.get("is_dynamic") else "EcoBuddy-builtin",
        [elec_input_node, elec_factor_node, elec_calc_node]
    )
    category_lineages["electricity"] = elec_lineage
    
    electricity_emission = electricity * elec_factor * 12

    diet_factor = DIET_EMISSION_FACTORS[diet]
    
    # Build lineage for diet
    diet_input_node = lineage_builder.create_input_node(
        "diet", 1.0, "year", f"Diet type: {diet}"
    )
    diet_factor_node = lineage_builder.create_factor_lookup_node(
        "diet", diet_factor, "kg CO2/year", "static-v1", "EcoBuddy-builtin",
        f"Annual {diet} diet emissions"
    )
        # Track calculation state if provided
    if assessment_state:
        assessment_state.set_input("input_distance", distance)
        assessment_state.set_input("input_electricity", electricity)
        assessment_state.set_input("input_flights", flights)
        assessment_state.set_input("input_diet", diet)
    diet_lineage = lineage_builder.build_category_lineage(
        "diet", 1.0, "year", diet_factor,
        diet_factor, "kg CO2/year", "static-v1", "EcoBuddy-builtin",
        [diet_input_node, diet_factor_node]
    )
    category_lineages["diet"] = diet_lineage
    
    diet_emission = diet_factor

    flight_factor = dynamic_factors["flight"]
    
    # Build lineage for flights
    flight_input_node = lineage_builder.create_input_node(
        "flights", flights, "flights/year", "Annual number of flights"
    )
    flight_factor_node = lineage_builder.create_factor_lookup_node(
        "flights", flight_factor, "kg CO2/flight", dynamic_factors.get("factor_version", "static-v1"),
        "Climatiq API" if dynamic_factors.get("is_dynamic") else "EcoBuddy-builtin",
        "Flight emission factor"
    )
    flight_calc_node = lineage_builder.create_calculation_node(
        "flights", flights * flight_factor, "flights * factor",
        [flight_input_node, flight_factor_node],
        f"{flights} flights * {flight_factor} kg CO2/flight"
    )
    flight_lineage = lineage_builder.build_category_lineage(
        "flights", flights, "flights/year", flights * flight_factor,
        flight_factor, "kg CO2/flight",
        dynamic_factors.get("factor_version", "static-v1"),
        "Climatiq API" if dynamic_factors.get("is_dynamic") else "EcoBuddy-builtin",
        [flight_input_node, flight_factor_node, flight_calc_node]
    )
    category_lineages["flights"] = flight_lineage
    
    flight_emission = flights * flight_factor

    contributors = {
        "Transport": round(transport_emission, 2),
        "Electricity": round(electricity_emission, 2),
        "Diet": diet_emission,
        "Flights": flight_emission,
    }

    raw_emissions = {
        "transport": transport_emission,
        "electricity": electricity_emission,
        "diet": diet_emission,
        "flights": flight_emission,
    }

    factors = {
        "transport": transport_factor,
        "electricity": elec_factor,
        "diet": diet_factor,
        "flights": flight_factor,
    }

    for lineage in category_lineages.values():
        lineage_builder.lineage_graph.add_category_lineage(lineage)
    
    # Store calculation metadata for dependency tracking
    calc_metadata = {
        "transport_result": contributors.get("Transport", 0),
        "electricity_result": contributors.get("Electricity", 0),
        "diet_result": contributors.get("Diet", 0),
        "flights_result": contributors.get("Flights", 0),
    }

    return contributors, raw_emissions, factors, confidence_data, category_lineages, calc_metadata
    # Store results in assessment state
    if assessment_state:
        assessment_state.put_result("calc_transport", contributors.get("Transport", 0))
        assessment_state.put_result("calc_electricity", contributors.get("Electricity", 0))
        assessment_state.put_result("calc_diet", contributors.get("Diet", 0))
        assessment_state.put_result("calc_flights", contributors.get("Flights", 0))
def calculate_footprint(
    transport: str,
    distance: float,
    electricity: float,
    diet: str,
    flights: int,
    region: str = "Global",
    return_audit: bool = False,
    return_lineage: bool = False,
    assessment_state: Any = None
) -> tuple[float, dict[str, Any]] | tuple[float, dict[str, Any], dict[str, Any]] | tuple[float, dict[str, Any], dict[str, Any], Any]:
    """
    Calculates annual carbon footprint (in kg CO2) across user activities.
    
    Optionally returns audit log for full calculation reproducibility.
    """
    diet, distance, electricity, flights, region = validate_footprint_inputs(
        transport, distance, electricity, diet, flights, region
    )

    dynamic_factors = fetch_emission_factors(region)
    factor_version = resolve_factor_set(region=region, api_factors=dynamic_factors)

    lineage_builder = LineageBuilder(f"footprint_{datetime.now().timestamp()}")
    
    contributors, raw_emissions, factors, confidence_data, category_lineages = calculate_category_emissions(
        transport, distance, electricity, diet, flights, dynamic_factors, confidence_tracker, lineage_builder
    )
    
    lineage_builder.lineage_graph.total_emissions = sum(contributors.values())
    total = sum(contributors.values())
    total_rounded = round(total, 2)

    audit_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "is_dynamic_api_used": dynamic_factors.get("is_dynamic", False),
        "factor_version": factor_version,
        "provenance": provenance_block(factor_version),
        "inputs": {
            "transport": transport,
            "daily_distance_km": distance,
            "monthly_electricity_kwh": electricity,
            "diet": diet,
            "annual_flights": flights,
        },
        "emission_factors": {
            "transport_kg_co2_per_km": factors["transport"],
            "electricity_kg_co2_per_kwh": factors["electricity"],
            "diet_kg_co2_per_year": factors["diet"],
            "flight_kg_co2_per_flight": factors["flights"],
        },
        "intermediate_calculations": {
            "Transport": {
                "formula": "daily_distance_km * transport_factor * 365 days",
                "expression": f"{distance} km * {factors['transport']} kg/km * 365",
                "raw_result": raw_emissions["transport"],
                "rounded_result_kg": contributors["Transport"]
            },
            "Electricity": {
                "formula": "monthly_kwh * electricity_factor * 12 months",
                "expression": f"{electricity} kWh * {factors['electricity']} kg/kWh * 12",
                "raw_result": raw_emissions["electricity"],
                "rounded_result_kg": contributors["Electricity"]
            },
            "Diet": {
                "formula": "annual_diet_emission_factor",
                "expression": f"{factors['diet']} kg/year ({diet})",
                "raw_result": raw_emissions["diet"],
                "rounded_result_kg": contributors["Diet"]
            },
            "Flights": {
                "formula": "annual_flights * flight_factor",
                "expression": f"{flights} flights * {factors['flights']} kg/flight",
                "raw_result": raw_emissions["flights"],
                "rounded_result_kg": contributors["Flights"]
            }
        },
        "total_emissions_kg_co2": total_rounded
    }

    if return_audit:
        return total_rounded, contributors, audit_log
    return total_rounded, contributors


def apply_uncertainty_bounds(raw_emissions: dict[str, float], uncertainty_percent: float) -> dict[str, dict[str, float]]:
    """
    Turns raw per-category emissions into lower/central/upper bounds using a
    single uncertainty percentage (the documented uncertainty of the
    emission-factor set that produced them).

    Returns a dict keyed by category with `low_kg`, `central_kg`, `high_kg`,
    and `range_kg` (the width of the interval, used to rank uncertainty
    contributors).
    """
    fraction = max(0.0, float(uncertainty_percent)) / 100.0
    bounds = {}
    for category, value in raw_emissions.items():
        low = value * (1 - fraction)
        high = value * (1 + fraction)
        bounds[category] = {
            "low_kg": round(low, 2),
            "central_kg": round(value, 2),
            "high_kg": round(high, 2),
            "range_kg": round(high - low, 2),
        }
    return bounds


def rank_uncertainty_contributors(category_bounds: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """
    Ranks categories by how much of the total uncertainty range they
    contribute, largest first, so the UI can point out which input drives
    the estimate's imprecision the most.
    """
    total_range = sum(bound["range_kg"] for bound in category_bounds.values())
    ranked = []
    for category, bound in category_bounds.items():
        share = (bound["range_kg"] / total_range * 100.0) if total_range > 0 else 0.0
        ranked.append({
            "category": category,
            "range_kg": bound["range_kg"],
            "share_percent": round(share, 2),
        })
    ranked.sort(key=lambda item: item["range_kg"], reverse=True)
    return ranked

    if return_lineage:
        return total_rounded, contributors, lineage_builder.lineage_graph
def calculate_footprint_range(
    transport: str,
    distance: float,
    electricity: float,
    diet: str,
    flights: int,
    region: str = "Global",
) -> dict[str, Any]:
    """
    Uncertainty-aware companion to `calculate_footprint()`.

    Produces lower, central and upper annual footprint estimates instead of
    a single number, using the uncertainty percentage documented for the
    emission-factor set the calculation resolves to. Purely additive:
    existing callers of `calculate_footprint()` are unaffected.
    """
    diet, distance, electricity, flights, region = validate_footprint_inputs(
        transport, distance, electricity, diet, flights, region
    )

    dynamic_factors = fetch_emission_factors(region)
    factor_version = resolve_factor_set(region=region, api_factors=dynamic_factors)
    uncertainty_percent = factor_uncertainty_percent(factor_version)

    _, raw_emissions, _ = calculate_category_emissions(
        transport, distance, electricity, diet, flights, dynamic_factors
    )

    category_bounds = apply_uncertainty_bounds(raw_emissions, uncertainty_percent)
    contributors = rank_uncertainty_contributors(category_bounds)

    total_low = round(sum(bound["low_kg"] for bound in category_bounds.values()), 2)
    total_central = round(sum(bound["central_kg"] for bound in category_bounds.values()), 2)
    total_high = round(sum(bound["high_kg"] for bound in category_bounds.values()), 2)

    return {
        "low_kg": total_low,
        "central_kg": total_central,
        "high_kg": total_high,
        "uncertainty_percent": uncertainty_percent,
        "factor_version": factor_version,
        "provenance": provenance_block(factor_version),
        "category_bounds": category_bounds,
        "top_uncertainty_contributors": contributors,
    }


def calculate_eco_score(total_footprint: float, contributors: dict[str, Any] | None = None,                        return_audit: bool = False) -> int | tuple[int, dict[str, Any]]:
    """
    Higher score = better sustainability
    Calculates a continuous score based on a sigmoid function.
    Supports per-category weighting if contributors are provided.
    Optionally returns audit log for score calculation.
    """
    audit = {
        "baseline": ECO_SCORE_BASELINE,
        "sensitivity": ECO_SCORE_SENSITIVITY,
        "category_weights": CATEGORY_WEIGHTS,
        "category_scores": {}
    }

    if contributors:
        weighted_score = 0.0
        for category, cat_total in contributors.items():
            weight = CATEGORY_WEIGHTS.get(category, 0.0)
            if weight > 0:
                cat_baseline = ECO_SCORE_BASELINE * weight
                cat_sensitivity = ECO_SCORE_SENSITIVITY * weight
                cat_score = 100 / (1 + math.exp((cat_total - cat_baseline) / cat_sensitivity))
                weighted_score += weight * cat_score
                audit["category_scores"][category] = {
                    "cat_total_kg": cat_total,
                    "weight": weight,
                    "cat_baseline": cat_baseline,
                    "cat_sensitivity": cat_sensitivity,
                    "raw_cat_score": cat_score,
                    "weighted_component": weight * cat_score
                }
        final_score = int(round(weighted_score))
        audit["final_weighted_score"] = weighted_score
        audit["final_score"] = final_score
    else:
        score = 100 / (1 + math.exp((total_footprint - ECO_SCORE_BASELINE) / ECO_SCORE_SENSITIVITY))
        final_score = int(round(score))
        audit["unweighted_raw_score"] = score
        audit["final_score"] = final_score

    if return_audit:
        return final_score, audit
    return final_score

    category_lineages = {}
    if lineage_builder is None:
        lineage_builder = LineageBuilder("standalone_calculation")
def generate_full_audit_log(transport: str, distance: float, electricity: float, diet: str,
                            flights: int, region: str = "Global") -> dict:
    """
    Generates a comprehensive audit log dictionary including both carbon footprint
    and eco score intermediate calculation steps.
    """
    total, contributors, footprint_audit = calculate_footprint(
        transport, distance, electricity, diet, flights, region, return_audit=True
    )
    eco_score, eco_score_audit = calculate_eco_score(total, contributors, return_audit=True)
    
    return {
        "footprint_audit": footprint_audit,
        "eco_score_audit": eco_score_audit,
        "summary": {
            "total_footprint_kg_co2": total,
            "eco_score": eco_score,
            "contributors": contributors,
            "factor_version": footprint_audit["factor_version"],
            "factor_citation": footprint_audit["provenance"]["citation"],
        }
    }


def get_factor_version(region: str = "Global") -> str:
    """
    The factor set version a calculation for this region would currently use.

    Exposed so the page layer can stamp `save_assessment(..., factor_version=...)`
    without having to request a full audit log.
    """
    return resolve_factor_set(region=region, api_factors=fetch_emission_factors(region))


def export_audit_log_json(audit_log: dict, indent: int = 2) -> str:
    """Exports an audit log dictionary into a formatted JSON string."""
    return json.dumps(audit_log, indent=indent)
def calculate_remaining_budget(budget_limit: float, current_emission: float) -> float:
    """
    Returns remaining carbon budget.
    """

    return max(0, budget_limit - current_emission)
def calculate_budget_progress(budget_limit: float, current_emission: float) -> float:
    """
    Returns percentage of budget used.
    """

    if budget_limit == 0:
        return 0

    return min(current_emission / budget_limit, 1.0)
def forecast_monthly_emission(current_emission: float) -> float:
    """
    Estimate end-of-month src.carbon.emissions.
    """

    today = datetime.datetime.today()

    days_elapsed = today.day

    total_days = calendar.monthrange(
        today.year,
        today.month
    )[1]

    average = current_emission / days_elapsed

    return round(
        average * total_days,
        2
    )
def budget_status(progress: float) -> str:

    if progress >= 0.90:
        return "Critical"

    elif progress >= 0.70:
        return "Warning"

    return "Safe"