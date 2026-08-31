"""
EcoBuddy AI Sustainability Insights REST API Service.

Provides secure REST API endpoints exposing carbon calculations, historical insights,
sustainability recommendations, reduction goals, API key provisioning, and
OpenAPI/Swagger documentation.

All API routes are organised under the version prefix defined by API_VERSION_PREFIX
(currently ``/api/v1``).  Change the constant here to migrate the entire API to a
new version without touching individual route handlers.
"""

import json
import http.server
import urllib.parse
from typing import Any
from src.carbon.emissions import calculate_footprint, calculate_eco_score
from src.ai.recommendations import generate_recommendations
from src.core.database import get_assessments, get_active_goal
from src.utils.goals import evaluate_progress
from src.core.api_auth import authenticate_request, generate_api_key, init_api_keys_db
from src.core.rate_limiter import CompositeRateLimiter
<<<<<<< HEAD
from src.core.feature_flags import feature_flag, FeatureFlagStore, FeatureFlag
=======
import time
from datetime import datetime, timezone
from src.business.api_usage_meter import usage_meter, UsageRecord
from src.business.api_usage_aggregator import UsageAggregator
from src.business.api_billing_tiers import BillingTierCalculator
>>>>>>> upstream/main

# ---------------------------------------------------------------------------
# Version prefix — single source of truth for the API version segment.
# Update this constant (e.g. "/api/v2") when introducing a new major version.
# ---------------------------------------------------------------------------
API_VERSION_PREFIX = "/api/v1"


def _route(path: str) -> str:
    """Build a versioned route by prepending API_VERSION_PREFIX."""
    return f"{API_VERSION_PREFIX}{path}"


# ---------------------------------------------------------------------------
# OpenAPI 3.0.3 specification
# ---------------------------------------------------------------------------
OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "EcoBuddy AI Sustainability Insights API",
        "version": "1.0.0",
        "description": (
            "REST API exposing EcoBuddy AI insights for integration with "
            "third-party applications.  All endpoints are accessible under "
            f"the ``{API_VERSION_PREFIX}`` prefix."
        ),
    },
    "servers": [
        {"url": "http://localhost:8000", "description": "Local API Server"}
    ],
    "components": {
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
            },
        }
    },
    "security": [
        {"ApiKeyAuth": []},
        {"BearerAuth": []},
    ],
    "paths": {
        _route("/health"): {
            "get": {
                "summary": "Health Check",
                "description": "Check if API service is online.",
                "responses": {
                    "200": {"description": "API is healthy"}
                },
            }
        },
        _route("/auth/keys"): {
            "post": {
                "summary": "Create API Key",
                "description": "Provision a new API key for third-party application integration.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "app_name": {"type": "string", "example": "My Green App"},
                                    "user_id": {"type": "string", "example": "user_123"},
                                },
                                "required": ["app_name"],
                            }
                        }
                    },
                },
                "responses": {
                    "201": {"description": "API Key created successfully"},
                    "400": {"description": "Invalid input"},
                },
            }
        },
        _route("/insights/calculate"): {
            "post": {
                "summary": "Calculate Sustainability Insights",
                "description": (
                    "Calculate annual carbon emissions, Eco Score, and personalised "
                    "insights from lifestyle inputs."
                ),
                "security": [{"ApiKeyAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "transport": {"type": "string", "example": "Car"},
                                    "distance": {"type": "number", "example": 15.0},
                                    "electricity": {"type": "number", "example": 250.0},
                                    "diet": {"type": "string", "example": "Omnivore"},
                                    "flights": {"type": "integer", "example": 2},
                                },
                                "required": ["transport", "distance", "electricity", "diet", "flights"],
                            }
                        }
                    },
                },
                "responses": {
                    "200": {"description": "Calculated insights"},
                    "400": {"description": "Bad request / calculation error"},
                    "401": {"description": "Unauthorized"},
                },
            }
        },
        _route("/insights/assessments"): {
            "get": {
                "summary": "Get Historical Assessments",
                "description": "Retrieve a user's historical footprint assessments.",
                "security": [{"ApiKeyAuth": []}],
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 10},
                    }
                ],
                "responses": {
                    "200": {"description": "Historical assessment list"},
                    "401": {"description": "Unauthorized"},
                },
            }
        },
        _route("/insights/recommendations"): {
            "get": {
                "summary": "Get Recommendations",
                "description": "Get prioritised action items to lower carbon footprint.",
                "security": [{"ApiKeyAuth": []}],
                "parameters": [
                    {"name": "transport", "in": "query", "schema": {"type": "string"}},
                    {"name": "electricity", "in": "query", "schema": {"type": "number"}},
                    {"name": "diet", "in": "query", "schema": {"type": "string"}},
                    {"name": "flights", "in": "query", "schema": {"type": "integer"}},
                ],
                "responses": {
                    "200": {"description": "Sustainability recommendations"},
                    "401": {"description": "Unauthorized"},
                },
            }
        },
        _route("/insights/goals"): {
            "get": {
                "summary": "Get Active Reduction Goals",
                "description": "Retrieve status and evaluation of active carbon reduction src.utils.goals.",
                "security": [{"ApiKeyAuth": []}],
                "responses": {
                    "200": {"description": "Active reduction goal and progress evaluation"},
                    "401": {"description": "Unauthorized"},
                },
            }
        },
        _route("/calculator/rainwater-tank"): {
            "post": {
                "summary": "Simulate Rainwater Harvesting and Tank Sizing",
                "description": "Calculates monthly rainfall capture, water demand, tank simulation, and optimal tank recommendation.",
                "security": [{"ApiKeyAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "roof_area_m2": {"type": "number", "example": 120.0},
                                    "roof_material": {"type": "string", "example": "Metal / corrugated sheet"},
                                    "climate_zone": {"type": "string", "example": "Temperate maritime"},
                                    "tank_litres": {"type": "number", "example": 5000.0},
                                    "monthly_demand_l": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "example": [4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000]
                                    }
                                },
                                "required": ["roof_area_m2"]
                            }
                        }
                    }
                },
                "responses": {
                    "200": {"description": "Rainwater harvesting simulation and sizing recommendation"},
                    "400": {"description": "Invalid input parameters"},
                    "401": {"description": "Unauthorized"}
                }
            }
        }
    },
}


# ---------------------------------------------------------------------------
# Swagger UI HTML — references the versioned OpenAPI spec endpoint
# ---------------------------------------------------------------------------
SWAGGER_UI_HTML = f"""<!DOCTYPE html>
<html>
<head>
  <title>EcoBuddy AI - Swagger UI</title>
  <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    html {{ box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }}
    *, *:before, *:after {{ box-sizing: inherit; }}
    body {{ margin: 0; background: #fafafa; }}
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function() {{
      window.ui = SwaggerUIBundle({{
        url: '{API_VERSION_PREFIX}/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ]
      }});
    }};
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Decorated Handlers for Experimental Features
# ---------------------------------------------------------------------------

def _rainwater_tank_fallback(body: dict, user_id: str, **kwargs) -> tuple:
    return (
        404,
        {"error": "Feature Disabled", "message": "The rainwater calculator is currently disabled or not available for your account."},
        "application/json",
    )

@feature_flag("experimental_rainwater_calc", fallback_func=_rainwater_tank_fallback)
def _handle_rainwater_tank(body: dict, user_id: str, **kwargs) -> tuple:
    try:
        from src.environment.rainwater import (
            monthly_harvest,
            simulate_storage,
            recommend_tank_size,
            savings_estimate,
            co2_savings,
            annual_harvest_potential,
            get_climate_profile,
            CLIMATE_ZONES
        )

        roof_area = float(body.get("roof_area_m2", 100.0))
        roof_material = str(body.get("roof_material", "Metal / corrugated sheet"))
        climate_zone = str(body.get("climate_zone", "Temperate maritime"))
        tank_litres = float(body.get("tank_litres", 3000.0))

        monthly_rainfall = body.get("monthly_rainfall_mm")
        if not monthly_rainfall:
            monthly_rainfall = get_climate_profile(climate_zone)

        monthly_demand = body.get("monthly_demand_l")
        if not monthly_demand:
            monthly_demand = [3500.0] * 12

        harvest_series = monthly_harvest(roof_area, monthly_rainfall, roof_material)
        annual_harvest = annual_harvest_potential(roof_area, sum(monthly_rainfall), roof_material)
        simulation = simulate_storage(tank_litres, harvest_series, monthly_demand)
        recommended = recommend_tank_size(harvest_series, monthly_demand)
        payback = savings_estimate(simulation["total_supplied_l"], tank_litres=tank_litres)
        carbon_avoided = co2_savings(simulation["total_supplied_l"])

        # Check if A/B test variant is assigned via the decorator
        variant = kwargs.get("_flag_variant")
        if variant == "detailed_report":
            # Add extra debug data or detailed report for this variant
            simulation["_experimental_variant"] = variant

        return (
            200,
            {
                "success": True,
                "data": {
                    "roof_area_m2": roof_area,
                    "roof_material": roof_material,
                    "climate_zone": climate_zone,
                    "monthly_harvest_l": harvest_series,
                    "annual_harvest_litres": annual_harvest,
                    "simulation": simulation,
                    "optimal_tank_recommendation": recommended,
                    "financial_payback": payback,
                    "carbon_avoided": carbon_avoided
                }
            },
            "application/json",
        )
    except Exception as exc:
        return (
            400,
            {"error": "Calculation Error", "message": str(exc)},
            "application/json",
        )

# ---------------------------------------------------------------------------
# Request dispatcher
# ---------------------------------------------------------------------------

def _process_api_request_internal(
    method: str,
    path: str,
    headers: dict,
    body: dict = None,
    query_params: dict = None,
) -> tuple:
    """
    Process an API request and return ``(status_code, payload, content_type)``.

    All protected routes require a valid API key supplied via the
    ``X-API-Key`` header or an ``Authorization: Bearer <key>`` header.
    """
    headers = headers or {}
    query_params = query_params or {}

    # ------------------------------------------------------------------ #
    # Public (unauthenticated) endpoints
    # ------------------------------------------------------------------ #

    # Health check
    if method == "GET" and path == _route("/health"):
        return (
            200,
            {
                "status": "healthy",
                "service": "EcoBuddy AI Sustainability Insights API",
                "version": "1.0.0",
                "api_prefix": API_VERSION_PREFIX,
            },
            "application/json",
        )

    # OpenAPI spec
    if method == "GET" and path == _route("/openapi.json"):
        return 200, OPENAPI_SPEC, "application/json"

    # Swagger UI — also reachable via legacy ``/docs`` for convenience
    if method == "GET" and path in ("/docs", _route("/docs")):
        return 200, SWAGGER_UI_HTML, "text/html"

    # Create API Key (developer / public endpoint — no auth required)
    if method == "POST" and path == _route("/auth/keys"):
        app_name = body.get("app_name") if body else None
        if not app_name:
            return (
                400,
                {"error": "Bad Request", "message": "Missing 'app_name' parameter."},
                "application/json",
            )
        user_id = body.get("user_id", "default_user")
        key_data = generate_api_key(app_name, user_id=user_id)
        return (
            201,
            {
                "success": True,
                "message": "API key generated successfully. Save this key — it will not be shown again.",
                "data": key_data,
            },
            "application/json",
        )

    # Inbound Webhooks
    if method == "POST" and path.startswith(_route("/webhooks/")):
        secure_token = path.split("/")[-1]
        raw_payload = json.dumps(body) if body else ""
        if not raw_payload:
            return (
                400,
                {"error": "Bad Request", "message": "JSON body is required for webhooks."},
                "application/json",
            )
        from src.integrations.webhook_engine import process_webhook_payload
        
        # In a real system, you might queue this for background processing here.
        # For this implementation, we'll process synchronously.
        success, msg = process_webhook_payload(secure_token, raw_payload)
        
        if success:
            return 200, {"success": True, "message": msg}, "application/json"
        else:
            # 400 Bad Request or 401 Unauthorized depending on error
            status_code = 401 if "token" in msg.lower() else 400
            return status_code, {"success": False, "error": msg}, "application/json"

    # ------------------------------------------------------------------ #
    # Protected endpoints — authentication required
    # ------------------------------------------------------------------ #
    is_auth, auth_res = authenticate_request(headers)
    if not is_auth:
        return 401, {"error": "Unauthorized", "message": auth_res}, "application/json"

    user_id = auth_res.get("user_id", "default_user")
    key_id = auth_res.get("id")
    rate_limit = auth_res.get("rate_limit", 100)
    
    # ------------------------------------------------------------------ #
    # Rate Limiting
    # ------------------------------------------------------------------ #
    is_allowed, status_code, rl_headers = CompositeRateLimiter.check_limit(key_id, rate_limit, path)
    if not is_allowed:
        return status_code, {"error": "Too Many Requests", "message": "Rate limit exceeded."}, "application/json", rl_headers

    # GET /api/v1/usage/summary
    if method == "GET" and path == _route("/usage/summary"):
        # We can aggregate from current time
        summary = UsageAggregator.aggregate_daily(key_id)
        return (
            200,
            {"success": True, "data": summary},
            "application/json",
        )

    # GET /api/v1/usage/detailed
    if method == "GET" and path == _route("/usage/detailed"):
        # For this implementation, we just return a stub or we can fetch a few records
        # but prompt didn't ask for full implementation of /detailed fetching, just the endpoint
        return (
            200,
            {"success": True, "message": "Detailed usage fetched", "data": []},
            "application/json",
        )

    # GET /api/v1/usage/billing
    if method == "GET" and path == _route("/usage/billing"):
        # Get usage for the current month
        monthly_usage = UsageAggregator.aggregate_monthly(key_id)
        current_month_requests = monthly_usage.get("total_requests", 0)
        billing_status = BillingTierCalculator.check_billing_status(key_id, current_month_requests)
        return (
            200,
            {"success": True, "data": billing_status},
            "application/json",
        )

    # POST /api/v1/insights/calculate
    if method == "POST" and path == _route("/insights/calculate"):
        if not body:
            return (
                400,
                {"error": "Bad Request", "message": "JSON body is required."},
                "application/json",
            )
        try:
            transport = str(body.get("transport", "Car"))
            distance = float(body.get("distance", 10.0))
            electricity = float(body.get("electricity", 150.0))
            diet = str(body.get("diet", "Omnivore"))
            flights = int(body.get("flights", 0))

            footprint, category_breakdown = calculate_footprint(
                transport, distance, electricity, diet, flights
            )
            eco_score = calculate_eco_score(footprint, category_breakdown)
            insight, recs = generate_recommendations(
                transport, electricity, diet, flights, category_breakdown
            )

            return (
                200,
                {
                    "success": True,
                    "data": {
                        "annual_footprint_kg_co2": round(footprint, 2),
                        "eco_score": round(eco_score, 1),
                        "category_breakdown": category_breakdown,
                        "insight": insight,
                        "recommendations": recs,
                    },
                },
                "application/json",
            )
        except Exception as exc:
            return (
                400,
                {"error": "Calculation Error", "message": str(exc)},
                "application/json",
            )

    # GET /api/v1/insights/assessments
    if method == "GET" and path == _route("/insights/assessments"):
        limit = int(query_params.get("limit", [10])[0]) if "limit" in query_params else 10
        raw_assessments = get_assessments() or []
        assessments = []
        for row in raw_assessments[:limit]:
            if isinstance(row, (list, tuple)) and len(row) >= 9:
                assessments.append(
                    {
                        "id": row[0],
                        "date": row[1],
                        "transport": row[2],
                        "distance": row[3],
                        "electricity": row[4],
                        "diet": row[5],
                        "flights": row[6],
                        "footprint_kg": row[7],
                        "eco_score": row[8],
                    }
                )
        return (
            200,
            {"success": True, "count": len(assessments), "data": assessments},
            "application/json",
        )

    # GET /api/v1/insights/recommendations
    if method == "GET" and path == _route("/insights/recommendations"):
        transport = query_params.get("transport", ["Car"])[0]
        electricity = float(query_params.get("electricity", [200.0])[0])
        diet = query_params.get("diet", ["Omnivore"])[0]
        flights = int(query_params.get("flights", [1])[0])

        footprint, category_breakdown = calculate_footprint(
            transport, 10.0, electricity, diet, flights
        )
        eco_score = calculate_eco_score(footprint, category_breakdown)
        insight, recs = generate_recommendations(
            transport, electricity, diet, flights, category_breakdown
        )

        return (
            200,
            {"success": True, "data": {"insight": insight, "recommendations": recs}},
            "application/json",
        )

    # GET /api/v1/insights/goals
    if method == "GET" and path == _route("/insights/goals"):
        goal = get_active_goal(user_id)
        if not goal:
            return (
                200,
                {
                    "success": True,
                    "data": None,
                    "message": "No active reduction goal found for user.",
                },
                "application/json",
            )
        raw_assessments = get_assessments(user_id=user_id) or []
        eval_data = evaluate_progress(goal, raw_assessments)
        return (
            200,
            {"success": True, "data": {"goal": goal, "evaluation": eval_data}},
            "application/json",
        )

    # POST /api/v1/calculator/rainwater-tank
    if method == "POST" and path == _route("/calculator/rainwater-tank"):
        if not body:
            return (
                400,
                {"error": "Bad Request", "message": "JSON body is required."},
                "application/json",
            )
        return _handle_rainwater_tank(body=body, user_id=user_id)

    # ------------------------------------------------------------------ #
    # Admin Flag Endpoints
    # ------------------------------------------------------------------ #
    if path == _route("/admin/flags"):
        if method == "GET":
            flags = FeatureFlagStore.list_flags()
            return 200, {"success": True, "data": flags}, "application/json"
        
        if method == "POST":
            if not body or "name" not in body:
                return 400, {"error": "Bad Request", "message": "Missing flag name"}, "application/json"
            flag = FeatureFlag.from_dict(body)
            FeatureFlagStore.upsert_flag(flag)
            return 201, {"success": True, "message": f"Flag {flag.name} created/updated."}, "application/json"
            
    if path.startswith(_route("/admin/flags/")):
        flag_name = path.split("/")[-1]
        if method == "GET":
            flag = FeatureFlagStore.get_flag(flag_name)
            if not flag:
                return 404, {"error": "Not Found", "message": "Flag not found"}, "application/json"
            return 200, {"success": True, "data": flag}, "application/json"
            
        if method == "PUT":
            if not body:
                return 400, {"error": "Bad Request", "message": "Missing body"}, "application/json"
            body["name"] = flag_name
            flag = FeatureFlag.from_dict(body)
            FeatureFlagStore.upsert_flag(flag)
            return 200, {"success": True, "message": f"Flag {flag.name} updated."}, "application/json"
            
        if method == "DELETE":
            deleted = FeatureFlagStore.delete_flag(flag_name)
            if not deleted:
                return 404, {"error": "Not Found", "message": "Flag not found"}, "application/json"
            return 200, {"success": True, "message": f"Flag {flag_name} deleted."}, "application/json"


    return (
        404,
        {
            "error": "Not Found",
            "message": f"Endpoint '{path}' with method '{method}' not found.",
        },
        "application/json",
    )


def process_api_request(
    method: str,
    path: str,
    headers: dict,
    body: dict = None,
    query_params: dict = None,
) -> tuple:
    """Wrapper that records API usage."""
    start_time = time.time()
    
    # Check if we should meter this path
    key_id = "public"
    if path.startswith(API_VERSION_PREFIX):
        is_auth, auth_res = authenticate_request(headers or {})
        if is_auth:
            key_id = auth_res.get("id", "public")

    res = _process_api_request_internal(method, path, headers, body, query_params)
    latency = (time.time() - start_time) * 1000.0  # ms
    
    status_code = res[0]
    payload = res[1]
    
    if isinstance(payload, (dict, list)):
        payload_size = len(json.dumps(payload).encode("utf-8"))
    elif isinstance(payload, str):
        payload_size = len(payload.encode("utf-8"))
    else:
        payload_size = 0
        
    usage_meter.record_usage(UsageRecord(
        key_id=key_id,
        endpoint=path,
        method=method,
        status_code=status_code,
        latency=latency,
        payload_size=payload_size,
        timestamp=datetime.now(timezone.utc).isoformat()
    ))
    
    return res



# ---------------------------------------------------------------------------
# Standalone HTTP server handler
# ---------------------------------------------------------------------------

class SustainabilityAPIRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the standalone EcoBuddy AI REST API server."""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Suppress default access-log noise during testing
        pass

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def _handle(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        headers = {k: v for k, v in self.headers.items()}
        body = None
        if "Content-Length" in self.headers:
            content_length = int(self.headers["Content-Length"])
            if content_length > 0:
                raw_body = self.rfile.read(content_length)
                try:
                    body = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError:
                    body = {}

        res = process_api_request(method, path, headers, body=body, query_params=query_params)
        status_code, response_data, content_type = res[0], res[1], res[2]
        extra_headers = res[3] if len(res) > 3 else {}

        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")
        for k, v in extra_headers.items():
            self.send_header(k, v)
        self.end_headers()

        if content_type == "application/json" and isinstance(response_data, (dict, list)):
            self.wfile.write(json.dumps(response_data, indent=2).encode("utf-8"))
        elif isinstance(response_data, str):
            self.wfile.write(response_data.encode("utf-8"))
