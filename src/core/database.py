import os
import sqlite3
from datetime import datetime, timedelta
from src.core.database_connection import database_connection, execute_with_retry
from src.core.cache import cached
from src.core.cache_config import TTL_DB_READ, CACHE_CATEGORY_DB_READS
from src.core.event_bus import EventBus
from src.core.domain_events import (
    AssessmentSaved,
    AssessmentUndone,
    ApplianceChanged,
    SolarConfigSaved,
    ChallengeEnrolled,
    ChallengeProgressed,
    ChallengeCompleted,
    XPAwarded,
    BadgeUnlocked,
    SkillTreeUpdated,
    JourneySaved,
    JourneyDeleted,
    OffsetSaved,
    OffsetDeleted,
    OffsetCleared,
    WaterAssessmentSaved,
    ReductionGoalChanged,
    FreezeTokenChanged,
    TimeCapsuleChanged,
)
import streamlit as st
import bcrypt
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)
DB_NAME = os.getenv("ECO_BUDDY_DB", "eco_buddy.db")


def get_db_version(conn: sqlite3.Connection) -> int:
    """Get the current database schema version using PRAGMA user_version."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    return cursor.fetchone()[0]


def set_db_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the database schema version using PRAGMA user_version."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA user_version = {version}")
    conn.commit()


def migrate() -> tuple[bool, str]:
    """
    Apply pending database migrations.

    Returns:
        tuple: (success: bool, message: str)
    """
    import migrations

    try:
        with database_connection(DB_NAME) as conn:
            current_version = get_db_version(conn)

            if current_version >= migrations.CURRENT_VERSION:
                return True, (
                    f"Database is already at version {current_version}"
                )

            migrations_to_apply = range(
                current_version + 1,
                migrations.CURRENT_VERSION + 1,
            )
            for version in migrations_to_apply:
                migration_file = f"migrations/migrate_v{version}.py"
                if os.path.exists(migration_file):
                    module = __import__(
                        f"migrations.migrate_v{version}",
                        fromlist=["migrate"],
                    )
                    if hasattr(module, "migrate"):
                        module.migrate(conn)
                        set_db_version(conn, version)
                        print(f"Applied migration v{version}")

        return True, (
            f"Database migrated to version {migrations.CURRENT_VERSION}"
        )
    except Exception as exc:
        return False, f"Migration failed: {exc}"


def init_db() -> bool:
    """
    Initialize the database with core tables and run pending migrations.

    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    try:
        def initialize_schema() -> None:
            with database_connection(DB_NAME) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS virtual_water_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product TEXT,
                        quantity REAL,
                        region TEXT,
                        scarcity_weighted_l REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS event_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guest_count INTEGER,
                        catering_type TEXT,
                        total_emissions_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS p2p_simulations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        grid_price REAL,
                        p2p_price REAL,
                        total_volume_kwh REAL,
                        carbon_avoided_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS anomaly_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        alert_date TEXT,
                        carbon_kg REAL,
                        severity TEXT,
                        resolved BOOLEAN DEFAULT 0,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aviation_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        distance_km REAL,
                        cabin_class TEXT,
                        has_layover BOOLEAN,
                        total_emissions_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS biodiversity_projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        baseline_condition TEXT,
                        total_area_sqm REAL,
                        bng_percentage REAL,
                        total_bu_gained REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS carbon_banking_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        action_type TEXT,
                        amount REAL,
                        from_month TEXT,
                        to_month TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    CREATE TABLE IF NOT EXISTS eco_ledger_accounts (
                        user_id TEXT PRIMARY KEY,
                        balance REAL DEFAULT 0.0,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS policy_simulations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        footprint_tonnes REAL,
                        tax_rate REAL,
                        net_impact_usd REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS load_shifting_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        appliances TEXT,
                        preference TEXT,
                        carbon_saved_kg REAL,
                        money_saved_usd REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS commute_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        log_date TEXT,
                        distance_km REAL,
                        chosen_mode TEXT,
                        baseline_mode TEXT,
                        carbon_saved_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS eco_ledger_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender_id TEXT,
                        receiver_id TEXT,
                        amount REAL,
                        timestamp REAL,
                        previous_hash TEXT,
                        hash TEXT,
                        proof_data TEXT
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS skill_listings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        skill_name TEXT,
                        category TEXT,
                        difficulty TEXT,
                        karma_cost INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS skill_swaps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        learner_id TEXT,
                        teacher_id TEXT,
                        skill_name TEXT,
                        karma_transferred INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS eco_order_book (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        order_type TEXT,
                        amount REAL,
                        price REAL,
                        status TEXT DEFAULT 'OPEN',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS urban_cooling_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        baseline_temp REAL,
                        hvac_cost REAL,
                        cooling_effect_c REAL,
                        twenty_year_net_savings REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fitness_oauth_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        provider TEXT,
                        access_token TEXT,
                        refresh_token TEXT,
                        expires_at REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS regeneration_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        garden_area_sqm REAL,
                        crop_count INTEGER,
                        regeneration_score REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS eco_community_funds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_name TEXT,
                        target_amount REAL,
                        current_amount REAL DEFAULT 0.0,
                        description TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS appliance_registrations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        appliance_type TEXT,
                        age_years INTEGER,
                        annual_usage_kwh REAL,
                        circularity_score REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS health_transport_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        date TEXT,
                        activity_type TEXT,
                        duration_minutes REAL,
                        distance_km REAL,
                        calories_burned REAL,
                        avoided_co2_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS net_zero_roadmaps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scope1 REAL,
                        scope2 REAL,
                        scope3 REAL,
                        target_year INTEGER,
                        roadmap_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS relocation_analyses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        current_city TEXT,
                        target_city TEXT,
                        annual_delta_kg_co2e REAL,
                        result_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS efficacy_checkins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        anxiety_level INTEGER,
                        agency_level INTEGER,
                        action_taken BOOLEAN,
                        efficacy_score REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS renovation_estimates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        material_key TEXT,
                        volume_m3 REAL,
                        total_carbon_kg REAL,
                        low_carbon_score REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS offset_portfolios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT,
                        total_tonnes REAL,
                        total_cost REAL,
                        diversification_score REAL,
                        risk_rating TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ej_impact_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        zip_code TEXT,
                        activity TEXT,
                        quantity REAL,
                        impact_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS green_premium_analyses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_key TEXT,
                        utility_inflation REAL,
                        subsidy_usd REAL,
                        result_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pca_balances (
                        user_id TEXT PRIMARY KEY,
                        balance_kg REAL DEFAULT 500.0,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS avoided_emissions_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        activity_type TEXT,
                        quantity REAL,
                        avoided_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS neighborhood_scores (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        zip_code TEXT,
                        eco_score REAL,
                        carbon_saved_kg REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pca_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        buyer_id TEXT,
                        seller_id TEXT,
                        amount_kg REAL,
                        price_per_tonne REAL,
                        trade_type TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS digital_twin_forecasts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        current_footprint REAL,
                        target_goal REAL,
                        scenarios_applied TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS travel_itineraries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        legs_data TEXT,
                        optimization_report TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        anonymous_leaderboard INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS water_energy_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        household_size INTEGER,
                        grid_intensity REAL,
                        comparison_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS challenge_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scenario_id TEXT,
                        outcome TEXT,
                        final_carbon REAL,
                        final_cost REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pantry_inventory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT,
                        purchase_date TEXT,
                        storage_condition TEXT,
                        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS urban_mining_inventories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_list TEXT,
                        total_devices INTEGER,
                        carbon_avoided_kg REAL,
                        mining_score INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS weekly_challenges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        difficulty TEXT NOT NULL,
                        xp INTEGER NOT NULL,
                        category TEXT,
                        status TEXT DEFAULT 'Pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS green_finance_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        portfolio_value REAL,
                        deposit_amount REAL,
                        investment_results TEXT,
                        banking_results TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS textile_comparisons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        garment_data TEXT,
                        results_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                try:
                    cursor.execute(
                        """
                        ALTER TABLE users
                        ADD COLUMN anonymous_leaderboard INTEGER DEFAULT 0
                        """
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pcf_labels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        product_name TEXT,
                        label_data TEXT,
                        transparency_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER DEFAULT 1,
                        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        transport TEXT,
                        distance REAL,
                        electricity REAL,
                        diet TEXT,
                        flights INTEGER,
                        footprint REAL,
                        eco_score INTEGER,
                        trip_id TEXT
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS urban_health_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        time_allocation TEXT,
                        weekly_park_visits INTEGER,
                        tree_canopy_pct REAL,
                        exposure_data TEXT,
                        mitigation_data TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS carbon_budgets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        budget_type TEXT NOT NULL,
                        budget_limit REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )
                    """
                )

                try:
                    cursor.execute(
                        """
                        ALTER TABLE assessments
                        ADD COLUMN created_at
                        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        """
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise

                # Conflict-aware import/export support (#1311): a stable
                # cross-device identifier plus last-modified/source metadata,
                # so an import can tell new, unchanged, updated and
                # conflicting assessments apart instead of matching on the
                # local autoincrement id.
                for column_sql in (
                    "ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    "ADD COLUMN client_uuid TEXT",
                    "ADD COLUMN source_device TEXT",
                ):
                    try:
                        cursor.execute(f"ALTER TABLE assessments {column_sql}")
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise

                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_assessments_trip_id
                    ON assessments(trip_id)
                    WHERE trip_id IS NOT NULL
                    """
                )

                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_assessments_client_uuid
                    ON assessments(user_id, client_uuid)
                    WHERE client_uuid IS NOT NULL
                    """
                )
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scanned_receipts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        vendor TEXT,
                        date TEXT,
                        total_cost REAL,
                        energy_kwh REAL,
                        category TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessment_drafts (
                        user_id INTEGER PRIMARY KEY,
                        transport TEXT,
                        distance REAL,
                        electricity REAL,
                        diet TEXT,
                        flights INTEGER,
                        region TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS iot_devices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id TEXT,
                        device_name TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS iot_readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id INTEGER,
                        hour_index INTEGER,
                        power_watts REAL,
                        energy_kwh REAL,
                        FOREIGN KEY (device_id) REFERENCES iot_devices (id)
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS deleted_assessments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_id INTEGER,
                        user_id INTEGER DEFAULT 1,
                        date TIMESTAMP,
                        transport TEXT,
                        distance REAL,
                        electricity REAL,
                        diet TEXT,
                        flights INTEGER,
                        footprint REAL,
                        eco_score INTEGER,
                        deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS waste_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        total_weight_kg REAL,
                        efficiency_score REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessment_activity_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER DEFAULT 1,
                        assessment_id INTEGER,
                        action TEXT NOT NULL,
                        details TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS business_footprints (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        total_emissions REAL,
                        eco_score REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS food_scans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        meal_name TEXT NOT NULL,
                        items TEXT,
                        total_co2_kg REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ev_charging_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        battery_capacity REAL,
                        current_soc REAL,
                        target_soc REAL,
                        charging_rate REAL,
                        optimal_carbon REAL,
                        carbon_savings REAL,
                        cost_savings REAL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS equivalence_preferences (
                        user_id INTEGER PRIMARY KEY,
                        top_metrics TEXT,
                        region TEXT DEFAULT 'Global',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS monthly_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        month_year TEXT,
                        report_data TEXT,
                        pdf_path TEXT,
                        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

        execute_with_retry(initialize_schema)
        migrate()
        return True
    except sqlite3.Error as exc:
        logger.error("Database init error: %s", exc)
        return False


def create_user(
    username: str,
    email: str,
    password: str,
    anonymous_leaderboard: bool = False,
) -> bool:
    def insert_user() -> None:
        with database_connection(DB_NAME) as conn:
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")
            conn.execute(
                """
                INSERT INTO users (
                    username,
                    email,
                    password_hash,
                    anonymous_leaderboard
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    password_hash,
                    int(bool(anonymous_leaderboard)),
                ),
            )

    try:
        execute_with_retry(insert_user)
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as exc:
        logger.error("Database user creation error: %s", exc)
        return False


def verify_user(username: str, password: str) -> dict[str, Any] | None:
    def fetch_user() -> dict[str, Any] | None:
        with database_connection(DB_NAME) as conn:
            return conn.execute(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    anonymous_leaderboard
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

    try:
        user = execute_with_retry(fetch_user)

        if user and bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            return {
                "id": user["id"],
                "username": user["username"],
                "anonymous_leaderboard": bool(
                    user["anonymous_leaderboard"]
                ),
            }
        return None
    except sqlite3.Error as exc:
        logger.error("Database user verification error: %s", exc)
        return None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    def fetch_user() -> dict[str, Any] | None:
        with database_connection(DB_NAME) as conn:
            return conn.execute(
                """
                SELECT
                    id,
                    username,
                    email,
                    anonymous_leaderboard
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

    try:
        user = execute_with_retry(fetch_user)
        if not user:
            return None

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "anonymous_leaderboard": bool(
                user["anonymous_leaderboard"]
            ),
        }
    except sqlite3.Error as exc:
        logger.error("Database user lookup error: %s", exc)
        return None


def update_user_leaderboard_preference(user_id: int, anonymous_leaderboard: bool) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET anonymous_leaderboard = ? WHERE id = ?",
            (int(bool(anonymous_leaderboard)), user_id)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database update user preference error: {e}")
        return False


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_leaderboard(period: str = "all") -> list[tuple[str, int, int, int]]:
    """
    Retrieves community leaderboard rankings.
    Returns list of tuples: (display_name, max_eco_score, total_xp, completed_challenges)
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                u.id,
                u.username,
                u.anonymous_leaderboard,
                COALESCE(MAX(a.eco_score), 0) AS max_eco_score,
                COALESCE(SUM(x.amount), 0) AS total_xp,
                COUNT(DISTINCT c.challenge_id) AS completed_challenges
            FROM users u
            LEFT JOIN assessments a ON u.id = a.user_id
            LEFT JOIN xp_transactions x ON u.id = x.user_id
            LEFT JOIN user_challenges c ON u.id = c.user_id AND c.status = 'completed'
            GROUP BY u.id
            ORDER BY max_eco_score DESC, total_xp DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        leaderboard = []
        for row in rows:
            u_id, username, is_anon, eco_score, xp, challenges = row
            display_name = f"User #{u_id}" if is_anon else username
            leaderboard.append((display_name, eco_score, xp, challenges))

        return leaderboard
    except sqlite3.Error as e:
        print(f"Database get_leaderboard error: {e}")
        return []


def save_assessment(
    user_id: int,
    transport: str,
    distance: float,
    electricity: float,
    diet: str,
    flights: int,
    footprint: float,
    eco_score: int = 0,
    trip_id: str | None = None,
    date: str | None = None,
    factor_version: str | None = None
) -> bool:
    """
    Persist an assessment.

    `factor_version` records which emission factor set produced the footprint
    (see src.carbon.emission_factors.py). It is optional: rows written without it are read
    back as 'static-v1', which is exactly the factor set the app used before
    versioning existed.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Build the column list from whatever the caller actually supplied,
        # so the optional date / trip_id / factor_version columns keep their
        # database defaults when they are omitted.
        columns = [
            "user_id",
            "transport",
            "distance",
            "electricity",
            "diet",
            "flights",
            "footprint",
            "eco_score",
        ]
        values = [
            user_id,
            transport,
            distance,
            electricity,
            diet,
            flights,
            footprint,
            eco_score,
        ]

        if date is not None:
            columns.append("date")
            values.append(date)
        if trip_id is not None:
            columns.append("trip_id")
            values.append(trip_id)
        if factor_version is not None:
            columns.append("factor_version")
            values.append(factor_version)

        placeholders = ", ".join("?" for _ in columns)
        cursor.execute(
            f"INSERT INTO assessments ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values),
        )

        conn.commit()
        conn.close()
        EventBus.publish(AssessmentSaved())
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"Database save error: {e}")
        return False


def save_ev_charging_session(
    battery_capacity: float, current_soc: float, target_soc: float, 
    charging_rate: float, optimal_carbon: float, carbon_savings: float, cost_savings: float
) -> None:
    """Saves an EV charging optimization session to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ev_charging_sessions 
        (battery_capacity, current_soc, target_soc, charging_rate, optimal_carbon, carbon_savings, cost_savings, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (battery_capacity, current_soc, target_soc, charging_rate, optimal_carbon, carbon_savings, cost_savings))
    conn.commit()
    conn.close()

def get_ev_charging_history() -> list:
    """Retrieves all EV charging optimization sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ev_charging_sessions ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

# -------------------------------------------------------------------------

def save_business_footprint(total_emissions: float, eco_score: float) -> None:
    """Saves a business Scope 3 footprint assessment."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO business_footprints (total_emissions, eco_score, timestamp)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (total_emissions, eco_score))
    conn.commit()
    conn.close()

def get_business_footprint_history() -> list:
    """Retrieves historical business footprint assessments."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM business_footprints ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

# -------------------------------------------------------------------------
# Fitness Integration
# -------------------------------------------------------------------------

def save_fitness_oauth_token(user_id: str, provider: str, access_token: str, refresh_token: str, expires_at: float) -> None:
    conn = database_connection(DB_NAME)
    # Using the context manager database_connection yields the connection
    with conn as c:
        cursor = c.cursor()
        cursor.execute("DELETE FROM fitness_oauth_tokens WHERE user_id = ? AND provider = ?", (str(user_id), provider))
        cursor.execute("""
            INSERT INTO fitness_oauth_tokens (user_id, provider, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (str(user_id), provider, access_token, refresh_token, expires_at))

def get_fitness_oauth_token(user_id: str, provider: str) -> dict | None:
    with database_connection(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fitness_oauth_tokens WHERE user_id = ? AND provider = ?", (str(user_id), provider))
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
        return None

def save_health_transport_metric(user_id: str, date: str, activity_type: str, duration_minutes: float, distance_km: float, calories_burned: float, avoided_co2_kg: float) -> None:
    with database_connection(DB_NAME) as conn:
        cursor = conn.cursor()
        # Avoid duplicates for the same day/activity combination
        cursor.execute("DELETE FROM health_transport_metrics WHERE user_id = ? AND date = ? AND activity_type = ?", (str(user_id), date, activity_type))
        cursor.execute("""
            INSERT INTO health_transport_metrics (user_id, date, activity_type, duration_minutes, distance_km, calories_burned, avoided_co2_kg)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(user_id), date, activity_type, duration_minutes, distance_km, calories_burned, avoided_co2_kg))

def get_health_transport_metrics(user_id: str) -> list[dict]:
    with database_connection(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM health_transport_metrics WHERE user_id = ? ORDER BY date ASC", (str(user_id),))
        rows = cursor.fetchall()
        return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]
# -------------------------------------------------------------------------
# Assessment Timestamp Migration
#
# This migration introduces the `created_at` column to the assessments
# table to automatically record when each assessment is created.
#
# The column uses SQLite's `CURRENT_TIMESTAMP` as its default value,
# allowing every newly inserted record to receive an accurate creation
# timestamp without requiring manual handling in application code.
#
# The migration is wrapped in a try/except block to ensure backward
# compatibility with existing databases. If the column already exists,
# SQLite raises an OperationalError, which is safely ignored so the
# application can continue initializing without interruption.
#
# Storing creation timestamps enables future enhancements such as:
#   • Chronological sorting of assessments
#   • Activity history and audit trails
#   • Time-based analytics and reporting
#   • Date range filtering
#   • Exporting records with creation metadata
#
# Existing assessment functionality remains unchanged because SQLite
# automatically populates the timestamp whenever a new record is created.
# -------------------------------------------------------------------------
@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_assessments(user_id: int = 1) -> list[tuple[Any, ...]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, date,created_at, transport, distance, electricity, diet, flights, footprint, eco_score
            FROM assessments
            WHERE user_id = ?
            ORDER BY created_at  DESC, id DESC
        """, (user_id,))

        data = cursor.fetchall()

        conn.close()
        return data
    except sqlite3.Error as e:
        print(f"Database read error: {e}")
        return []


def save_waste_log(total_weight: float, efficiency_score: float) -> None:
    """Saves a waste analytics log to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO waste_logs (total_weight_kg, efficiency_score, timestamp)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (total_weight, efficiency_score))
    conn.commit()
    conn.close()

def get_waste_analytics_history() -> list:
    """Retrieves historical waste analytics logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM waste_logs ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_carbon_budget(user_id: int, budget_type: str, budget_limit: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM carbon_budgets WHERE user_id=?",
            (user_id,)
        )

        cursor.execute("""
            INSERT INTO carbon_budgets(user_id,budget_type,budget_limit)
            VALUES(?,?,?)
        """,(user_id,budget_type,budget_limit))

        conn.commit()
        conn.close()

        return True

    except sqlite3.Error as e:
        print(e)
        return False
def get_carbon_budget(user_id: int) -> tuple[str, float] | None:

    try:
        conn=sqlite3.connect(DB_NAME)
        cursor=conn.cursor()

        cursor.execute("""
        SELECT budget_type,budget_limit
        FROM carbon_budgets
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,(user_id,))

        row=cursor.fetchone()

        conn.close()

        return row

    except sqlite3.Error:
        return None


def save_iot_device(device_id: str, device_name: str) -> int:
    """Saves a connected IoT device and returns its DB ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO iot_devices (device_id, device_name, timestamp)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """, (device_id, device_name))
    conn.commit()
    device_db_id = cursor.lastrowid
    conn.close()
    return device_db_id

def save_iot_reading_batch(device_db_id: int, readings: list) -> None:
    """Saves a batch of hourly IoT readings."""
    conn = get_connection()
    cursor = conn.cursor()
    for r in readings:
        cursor.execute("""
            INSERT INTO iot_readings (device_id, hour_index, power_watts, energy_kwh)
            VALUES (?, ?, ?, ?)
        """, (device_db_id, r["hour_index"], r["power_watts"], r["energy_kwh"]))
    conn.commit()
    conn.close()

def get_iot_devices() -> list:
    """Retrieves all connected IoT devices."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM iot_devices ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]


def update_carbon_budget(user_id: int, budget_type: str, budget_limit: float) -> bool:

    try:

        conn=sqlite3.connect(DB_NAME)
        cursor=conn.cursor()

        cursor.execute("""
        UPDATE carbon_budgets
        SET budget_type=?,
            budget_limit=?
        WHERE user_id=?
        """,(budget_type,budget_limit,user_id))

        conn.commit()

        conn.close()

        return True

    except sqlite3.Error:

        return False


def save_scanned_receipt(vendor: str, date: str, total_cost: float, energy_kwh: Optional[float], category: str) -> None:
    """Saves a processed and confirmed scanned receipt/bill to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scanned_receipts (vendor, date, total_cost, energy_kwh, category, timestamp)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (vendor, date, total_cost, energy_kwh, category))
    conn.commit()
    conn.close()

def get_scanned_receipts_history() -> list:
    """Retrieves historical scanned receipts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scanned_receipts ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_assessments_with_factors(user_id: int = 1) -> list[tuple[Any, ...]]:
    """
    Assessments including the factor version each was computed under.

    Kept separate from get_assessments() so the existing nine-column tuple
    shape that every caller already unpacks stays untouched.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, transport,created_at, distance, electricity, diet, flights,
                   footprint, eco_score, factor_version
            FROM assessments
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
        """, (user_id,))
        return cursor.fetchall()
    except sqlite3.Error as exc:
        logger.error("Unable to read assessments with factor versions: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_all_assessments() -> list[tuple[Any, ...]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, date, created_at,transport, distance, electricity, diet, flights, footprint, eco_score
            FROM assessments
            ORDER BY date DESC
            LIMIT 100, id DESC
        """)

        data = cursor.fetchall()

        conn.close()
        return data
    except sqlite3.Error as e:
        print(f"Database read error: {e}")
        return []


def undo_last_assessment(user_id: int = 1) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Undo the user's most recent assessment record.
    Moves record to deleted_assessments table, logs action in activity log,
    and invalidates dependent caches.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Find latest assessment
        cursor.execute(
            """
            SELECT id, date, transport, distance, electricity, diet, flights, footprint, eco_score
            FROM assessments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No assessment found to undo.", None

        rec_id, date, transport, distance, electricity, diet, flights, footprint, eco_score = row

        # Backup into deleted_assessments
        cursor.execute(
            """
            INSERT INTO deleted_assessments (original_id, user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rec_id, user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
        )

        # Delete from assessments table
        cursor.execute("DELETE FROM assessments WHERE id = ?", (rec_id,))

        # Log activity
        details = f"Undone assessment #{rec_id} ({footprint:.1f} kg CO2, score {eco_score})"
        cursor.execute(
            """
            INSERT INTO assessment_activity_log (user_id, assessment_id, action, details)
            VALUES (?, ?, 'UNDO', ?)
            """,
            (user_id, rec_id, details)
        )

        conn.commit()
        conn.close()

        EventBus.publish(AssessmentUndone())
        record_dict = {
            "id": rec_id,
            "date": date,
            "transport": transport,
            "distance": distance,
            "electricity": electricity,
            "diet": diet,
            "flights": flights,
            "footprint": footprint,
            "eco_score": eco_score,
        }
        return True, f"Successfully undone assessment #{rec_id}.", record_dict
    except sqlite3.Error as e:
        logger.error("Undo assessment error: %s", e)
        return False, f"Database error during undo: {e}", None


def restore_last_deleted_assessment(user_id: int = 1) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Restore the user's most recently undone assessment.
    Re-inserts record into assessments table and logs action.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Find latest deleted assessment
        cursor.execute(
            """
            SELECT id, original_id, date, transport, distance, electricity, diet, flights, footprint, eco_score
            FROM deleted_assessments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No deleted assessment available to restore.", None

        del_id, orig_id, date, transport, distance, electricity, diet, flights, footprint, eco_score = row

        # Re-insert into assessments
        cursor.execute(
            """
            INSERT INTO assessments (user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
        )
        new_id = cursor.lastrowid

        # Delete from deleted_assessments
        cursor.execute("DELETE FROM deleted_assessments WHERE id = ?", (del_id,))

        # Log activity
        details = f"Restored assessment (formerly #{orig_id}, now #{new_id})"
        cursor.execute(
            """
            INSERT INTO assessment_activity_log (user_id, assessment_id, action, details)
            VALUES (?, ?, 'RESTORE', ?)
            """,
            (user_id, new_id, details)
        )

        conn.commit()
        conn.close()

        EventBus.publish(AssessmentSaved())
        return True, f"Successfully restored assessment #{new_id}.", {"id": new_id, "footprint": footprint}
    except sqlite3.Error as e:
        logger.error("Restore assessment error: %s", e)
        return False, f"Database error during restore: {e}", None


def get_last_undone_assessment(user_id: int = 1) -> dict[str, Any] | None:
    """Fetch the latest undone assessment for restore preview."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT original_id, date, transport, distance, electricity, diet, flights, footprint, eco_score, deleted_at
            FROM deleted_assessments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "original_id": row[0],
                "date": row[1],
                "transport": row[2],
                "distance": row[3],
                "electricity": row[4],
                "diet": row[5],
                "flights": row[6],
                "footprint": row[7],
                "eco_score": row[8],
                "deleted_at": row[9],
            }
        return None
    except sqlite3.Error:
        return None


def get_assessment_activity_history(user_id: int = 1) -> list[dict[str, Any]]:
    """Retrieve chronological activity log for assessment creations, undos, and restores."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, assessment_id, action, details, timestamp
            FROM assessment_activity_log
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "assessment_id": r[1],
                "action": r[2],
                "details": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]
    except sqlite3.Error:
        return []


def save_assessment_draft(
    user_id: int,
    transport: str,
    distance: float,
    electricity: float,
    diet: str,
    flights: int,
    region: str,
) -> bool:
    """Insert or update one unfinished assessment per user."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO assessment_drafts (
                user_id,
                transport,
                distance,
                electricity,
                diet,
                flights,
                region,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                transport = excluded.transport,
                distance = excluded.distance,
                electricity = excluded.electricity,
                diet = excluded.diet,
                flights = excluded.flights,
                region = excluded.region,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                transport,
                distance,
                electricity,
                diet,
                flights,
                region,
            ),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Database draft save error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def get_diet_history(user_id: int, limit: int = 7) -> list[tuple[Any, ...]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, diet FROM assessments
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 100 LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except sqlite3.Error as e:
        print(f"get_diet_history error: {e}")
        return []


def get_assessment_draft(user_id: int) -> dict[str, Any] | None:
    """Return the active user's unfinished assessment, if one exists."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                transport,
                distance,
                created_at,
                electricity,
                diet,
                flights,
                region,
                updated_at
            FROM assessment_drafts
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "transport": row[0],
            "distance": row[1],
            "electricity": row[3],
            "diet": row[4],
            "flights": row[5],
            "region": row[6],
            "updated_at": row[7],
        }
    except sqlite3.Error as exc:
        logger.error("Database draft read error: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


def delete_assessment_draft(user_id: int) -> bool:
    """Delete the active user's unfinished assessment."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM assessment_drafts WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Database draft delete error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def init_energy_db() -> bool:
    """
    Initialize energy-related tables (appliances, solar_configs).
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appliances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                name TEXT,
                category TEXT,
                quantity INTEGER,
                power_rating_watts REAL,
                hours_used_per_day REAL,
                standby_draw_watts REAL,
                usage_schedule TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solar_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                roof_space_m2 REAL,
                peak_sun_hours REAL,
                utility_rate_per_kwh REAL,
                panel_efficiency REAL,
                installation_cost_per_kw REAL,
                maintenance_cost_per_year REAL,
                annual_rate_increase REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database energy init error: {e}")
        return False


def add_appliance(user_id: int, name: str, category: str, quantity: int, power_rating: float, hours_used: float, standby_draw: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appliances (user_id, name, category, quantity, power_rating_watts, hours_used_per_day, standby_draw_watts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, name, category, quantity, power_rating, hours_used, standby_draw))
        conn.commit()
        conn.close()
        EventBus.publish(ApplianceChanged())
        return True
    except sqlite3.Error as e:
        print(f"Appliance save error: {e}")
        return False


def delete_appliance(app_id: int) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM appliances WHERE id = ?", (app_id,))
        conn.commit()
        conn.close()
        EventBus.publish(ApplianceChanged())
        return True
    except sqlite3.Error as e:
        return False


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_appliances(user_id: int = 1) -> list[dict[str, Any]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appliances WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []


def save_solar_config(user_id: int, roof_space: float, peak_sun_hours: float, utility_rate: float, panel_efficiency: float, install_cost: float, maint_cost: float, rate_inc: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM solar_configs WHERE user_id = ?", (user_id,))
        
        cursor.execute("""
            INSERT INTO solar_configs (
                user_id, roof_space_m2, peak_sun_hours, utility_rate_per_kwh, panel_efficiency, 
                installation_cost_per_kw, maintenance_cost_per_year, annual_rate_increase
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, roof_space, peak_sun_hours, utility_rate, panel_efficiency, install_cost, maint_cost, rate_inc))
        conn.commit()
        conn.close()
        EventBus.publish(SolarConfigSaved())
        return True
    except sqlite3.Error as e:
        return False


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_solar_config(user_id: int = 1) -> dict[str, Any] | None:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM solar_configs WHERE user_id = ? LIMIT 1", (user_id,))
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(zip(columns, row))
        return None
    except sqlite3.Error as e:
        return None


def init_gamification_db() -> bool:
    """
    Initialize gamification-related tables.
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                challenge_id TEXT NOT NULL,
                progress_value REAL DEFAULT 0.0,
                status TEXT DEFAULT 'enrolled',
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                xp_awarded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unlocked_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                badge_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                xp_awarded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS xp_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                xp_amount INTEGER NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, source_type, source_id)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_xp_user ON xp_transactions(user_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                card_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, card_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_tree_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                node_id TEXT NOT NULL,
                status TEXT DEFAULT 'Locked',
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, node_id)
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database gamification init error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def enroll_challenge(user_id: int, challenge_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM user_challenges WHERE user_id=? AND challenge_id=? AND status != 'expired'", (user_id, challenge_id))
        if cursor.fetchone():
            return False
            
        cursor.execute("""
            INSERT INTO user_challenges (user_id, challenge_id, status)
            VALUES (?, ?, 'enrolled')
        """, (user_id, challenge_id))
        conn.commit()
        EventBus.publish(ChallengeEnrolled())
        return True
    except sqlite3.Error as e:
        print(f"enroll_challenge error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def update_challenge_progress(user_id: int, challenge_id: str, progress_increment: float | None = None, set_progress: float | None = None) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        if progress_increment is not None:
            cursor.execute("""
                UPDATE user_challenges 
                SET progress_value = progress_value + ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND challenge_id = ? AND status = 'enrolled'
            """, (progress_increment, user_id, challenge_id))
        elif set_progress is not None:
             cursor.execute("""
                UPDATE user_challenges 
                SET progress_value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND challenge_id = ? AND status = 'enrolled'
            """, (set_progress, user_id, challenge_id))
            
        conn.commit()
        EventBus.publish(ChallengeEnrolled())
        return True
    except sqlite3.Error as e:
        print(f"update_challenge_progress error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def complete_challenge(user_id: int, challenge_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE user_challenges 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND challenge_id = ? AND status = 'enrolled'
        """, (user_id, challenge_id))
        
        conn.commit()
        EventBus.publish(ChallengeEnrolled())
        return True
    except sqlite3.Error as e:
        print(f"complete_challenge error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_user_challenges(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_challenges WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


def award_xp(user_id: int, source_type: str, source_id: str, xp_amount: int, description: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO xp_transactions (user_id, source_type, source_id, xp_amount, description)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, source_type, source_id, xp_amount, description))
        
        if source_type == 'challenge':
            cursor.execute("UPDATE user_challenges SET xp_awarded = 1 WHERE user_id = ? AND challenge_id = ?", (user_id, source_id))
            EventBus.publish(ChallengeEnrolled())
        elif source_type == 'badge':
            cursor.execute("UPDATE unlocked_badges SET xp_awarded = 1 WHERE user_id = ? AND badge_id = ?", (user_id, source_id))
            EventBus.publish(BadgeUnlocked())
            
        conn.commit()
        EventBus.publish(XPAwarded())
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"award_xp error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_xp(user_id: int) -> int:
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(xp_amount) FROM xp_transactions WHERE user_id = ?", (user_id,))
        total = cursor.fetchone()[0]
        return total if total else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


def unlock_badge_in_db(user_id: int, badge_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO unlocked_badges (user_id, badge_id)
            VALUES (?, ?)
        """, (user_id, badge_id))
        
        conn.commit()
        EventBus.publish(BadgeUnlocked())
        EventBus.publish(XPAwarded())
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"unlock_badge_in_db error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_unlocked_badges(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM unlocked_badges WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


def unlock_card_in_db(user_id: int, card_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO user_cards (user_id, card_id)
            VALUES (?, ?)
        """, (user_id, card_id))

        conn.commit()
        get_unlocked_cards.clear()
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"unlock_card_in_db error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@st.cache_data
def get_unlocked_cards(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_cards WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_skill_tree_progress(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skill_tree_progress WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


def update_skill_node_status(user_id: int, node_id: str, status: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM skill_tree_progress WHERE user_id=? AND node_id=?", (user_id, node_id))
        if cursor.fetchone():
            if status == 'Completed':
                cursor.execute("""
                    UPDATE skill_tree_progress 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND node_id = ?
                """, (status, user_id, node_id))
            else:
                cursor.execute("""
                    UPDATE skill_tree_progress 
                    SET status = ?
                    WHERE user_id = ? AND node_id = ?
                """, (status, user_id, node_id))
        else:
            if status == 'Completed':
                cursor.execute("""
                    INSERT INTO skill_tree_progress (user_id, node_id, status, completed_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, node_id, status))
            else:
                cursor.execute("""
                    INSERT INTO skill_tree_progress (user_id, node_id, status)
                    VALUES (?, ?, ?)
                """, (user_id, node_id, status))
                
        conn.commit()
        EventBus.publish(SkillTreeUpdated())
        return True
    except sqlite3.Error as e:
        print(f"update_skill_node_status error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def init_marketplace_db() -> bool:
    """
    Initialize marketplace-related tables (journey_profiles, offset_transactions).
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS journey_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                distance_km REAL NOT NULL,
                transport_mode TEXT NOT NULL,
                passenger_count INTEGER DEFAULT 1,
                trips_per_week INTEGER DEFAULT 1,
                is_commute BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS offset_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                project_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                offset_tonnes REAL NOT NULL,
                cost_per_tonne REAL NOT NULL,
                total_cost REAL NOT NULL,
                transaction_status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        return True
    except Exception as e:
        print(f'Database marketplace init error: {e}')
        return False
    finally:
        if conn:
            conn.close()


def save_journey_profile(user_id: int, name: str, distance_km: float, transport_mode: str, passenger_count: int, trips_per_week: int, is_commute: bool) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO journey_profiles (user_id, name, distance_km, transport_mode, passenger_count, trips_per_week, is_commute)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, distance_km, transport_mode, passenger_count, trips_per_week, is_commute))
        
        conn.commit()
        EventBus.publish(JourneySaved())
        return True
    except Exception as e:
        print(f'save_journey_profile error: {e}')
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_journey_profiles(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM journey_profiles WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def delete_journey_profile(profile_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM journey_profiles WHERE id = ?', (profile_id,))
        conn.commit()
        EventBus.publish(JourneySaved())
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def save_offset_transaction(user_id: int, project_id: str, project_name: str, offset_tonnes: float, cost_per_tonne: float, total_cost: float, transaction_status: str = 'completed') -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO offset_transactions (user_id, project_id, project_name, offset_tonnes, cost_per_tonne, total_cost, transaction_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, project_id, project_name, offset_tonnes, cost_per_tonne, total_cost, transaction_status))
        
        conn.commit()
        EventBus.publish(OffsetSaved())
        return True
    except Exception as e:
        print(f'save_offset_transaction error: {e}')
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_offset_transactions(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM offset_transactions WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def delete_offset_transaction(transaction_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM offset_transactions WHERE id = ?', (transaction_id,))
        conn.commit()
        EventBus.publish(OffsetSaved())
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def clear_offset_transactions(user_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM offset_transactions WHERE user_id = ?', (user_id,))
        conn.commit()
        EventBus.publish(OffsetSaved())
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_offsets(user_id: int) -> float:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(offset_tonnes) FROM offset_transactions WHERE user_id = ? AND transaction_status != "reversed"', (user_id,))
        total = cursor.fetchone()[0]
        return total if total else 0.0
    except Exception:
        return 0.0
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_spend(user_id: int) -> float:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(total_cost) FROM offset_transactions WHERE user_id = ? AND transaction_status != "reversed"', (user_id,))
        total = cursor.fetchone()[0]
        return total if total else 0.0
    except Exception:
        return 0.0
    finally:
        if conn:
            conn.close()


def init_water_db() -> bool:
    """
    Initialize water consumption table.
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS water_consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                shower_mins_per_day REAL,
                laundry_loads_per_week REAL,
                dishwasher_runs_per_week REAL,
                garden_mins_per_week REAL,
                diet TEXT,
                total_liters REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        return True
    except Exception as e:
        print(f'Database water init error: {e}')
        return False
    finally:
        if conn:
            conn.close()


def save_water_assessment(user_id: int, shower: float, laundry: float, dishwasher: float, garden: float, diet: str, total_liters: float) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO water_consumption (user_id, shower_mins_per_day, laundry_loads_per_week, dishwasher_runs_per_week, garden_mins_per_week, diet, total_liters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, shower, laundry, dishwasher, garden, diet, total_liters))
        
        conn.commit()
        EventBus.publish(WaterAssessmentSaved())
        return True
    except Exception as e:
        print(f'save_water_assessment error: {e}')
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_water_assessments(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM water_consumption WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()
            conn.close()


def save_dashboard_widget_preferences(user_id: int, widget_ids: list[str]) -> bool:
    """Persist the ordered dashboard widget IDs selected by a user."""
    import json

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_widget_preferences (
                user_id INTEGER PRIMARY KEY,
                widgets_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO dashboard_widget_preferences (user_id, widgets_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                widgets_json = excluded.widgets_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, json.dumps(list(widget_ids))),
        )
        conn.commit()
        return True
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.error("Dashboard preference save error: %s", exc)
        return False
    finally:
        if 'conn' in locals():
            conn.close()


def get_dashboard_widget_preferences(user_id: int) -> list[str] | None:
    """Return the saved widget IDs, or None when the user has no preference."""
    import json

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_widget_preferences (
                user_id INTEGER PRIMARY KEY,
                widgets_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            "SELECT widgets_json FROM dashboard_widget_preferences WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        value = json.loads(row[0])
        return value if isinstance(value, list) else None
    except (sqlite3.Error, json.JSONDecodeError, TypeError) as exc:
        logger.error("Dashboard preference read error: %s", exc)
        return None
    finally:
        if 'conn' in locals():
            conn.close()


def record_environmental_milestone(
    user_id: int,
    milestone_type: str,
    title: str,
    description: str,
    icon: str = "🌱",
    achieved_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Persist a milestone once per user and milestone type.

    Returns True only when a new milestone is inserted.
    """
    import json

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO environmental_milestones (
                user_id,
                milestone_type,
                title,
                description,
                icon,
                achieved_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)
            """,
            (
                user_id,
                milestone_type,
                title,
                description,
                icon,
                achieved_at,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        conn.commit()
        return cursor.rowcount == 1
    except sqlite3.Error as exc:
        logger.error("Unable to record environmental milestone: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def get_environmental_milestones(user_id: int) -> list[dict[str, Any]]:
    """Return a user's milestones from newest to oldest."""
    import json

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                milestone_type,
                title,
                description,
                icon,
                achieved_at,
                metadata_json
            FROM environmental_milestones
            WHERE user_id = ?
            ORDER BY datetime(achieved_at) DESC, id DESC
            """,
            (user_id,),
        )
        milestones = []
        for row in cursor.fetchall():
            try:
                metadata = json.loads(row[6] or "{}")
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            milestones.append(
                {
                    "id": row[0],
                    "milestone_type": row[1],
                    "title": row[2],
                    "description": row[3],
                    "icon": row[4],
                    "achieved_at": row[5],
                    "metadata": metadata,
                }
            )
        return milestones
    except sqlite3.Error as exc:
        logger.error("Unable to load environmental milestones: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


def init_freeze_tokens_db() -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        migrate()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS freeze_token_balances (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER NOT NULL DEFAULT 0,
                total_used INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS freeze_token_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS streak_freezes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                frozen_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, frozen_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_streak_freezes_user_date
            ON streak_freezes(user_id, frozen_date DESC)
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Freeze tokens DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_freeze_token_balance(user_id: int) -> int:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM freeze_token_balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


def ensure_freeze_token_row(user_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO freeze_token_balances (user_id, balance, total_earned, total_used)
            VALUES (?, 0, 0, 0)
        """, (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()


def award_freeze_tokens(user_id: int, amount: int, reason: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        ensure_freeze_token_row(user_id)
        cursor.execute("""
            UPDATE freeze_token_balances
            SET balance = balance + ?, total_earned = total_earned + ?
            WHERE user_id = ?
        """, (amount, amount, user_id))
        cursor.execute("""
            INSERT INTO freeze_token_transactions (user_id, amount, reason)
            VALUES (?, ?, ?)
        """, (user_id, amount, reason))
        conn.commit()
        EventBus.publish(FreezeTokenChanged())
        return True
    except sqlite3.Error as e:
        logger.error("award_freeze_tokens error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def redeem_freeze_token(user_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM freeze_token_balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row[0] < 1:
            return False
        cursor.execute("""
            UPDATE freeze_token_balances
            SET balance = balance - 1, total_used = total_used + 1
            WHERE user_id = ? AND balance >= 1
        """, (user_id,))
        cursor.execute("""
            INSERT INTO freeze_token_transactions (user_id, amount, reason)
            VALUES (?, ?, ?)
        """, (user_id, -1, 'redeem'))
        conn.commit()
        EventBus.publish(FreezeTokenChanged())
        return True
    except sqlite3.Error as e:
        logger.error("redeem_freeze_token error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def use_streak_freeze(user_id: int, frozen_date: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO streak_freezes (user_id, frozen_date)
            VALUES (?, ?)
        """, (user_id, frozen_date))
        conn.commit()
        EventBus.publish(FreezeTokenChanged())
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("use_streak_freeze error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_streak_freeze_dates(user_id: int) -> list[str]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT frozen_date FROM streak_freezes
            WHERE user_id = ?
            ORDER BY frozen_date DESC
        """, (user_id,))
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


def get_freeze_token_transactions(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, amount, reason, created_at
            FROM freeze_token_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
        """, (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_freeze_tokens_earned(user_id: int) -> int:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT total_earned FROM freeze_token_balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Reduction goals
# ---------------------------------------------------------------------------

def init_goals_db() -> bool:
    """
    Create the reduction_goals table.

    Kept as its own initializer to match the existing per-feature pattern
    (init_energy_db, init_gamification_db, init_marketplace_db, init_water_db).
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reduction_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                baseline_kg REAL NOT NULL,
                target_kg REAL NOT NULL,
                start_date TEXT NOT NULL,
                target_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # A user may only have one active goal at a time; history rows are
        # archived or completed and are excluded from the index.
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reduction_goals_active
            ON reduction_goals(user_id)
            WHERE status = 'active'
        """)
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Reduction goals init error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def _goal_row_to_dict(row: Any) -> dict[str, Any] | None:
    """Map a reduction_goals row onto the dict shape src.utils.goals.py expects."""
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "baseline_kg": row[2],
        "target_kg": row[3],
        "start_date": row[4],
        "target_date": row[5],
        "status": row[6],
        "created_at": row[7],
    }


def save_reduction_goal(user_id: int, baseline_kg: float, target_kg: float, start_date: str, target_date: str) -> int | None:
    """
    Persist a new goal, archiving any goal the user already had active.

    Returns the new goal id, or None if the write failed.
    """
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Only one active goal per user, so retire the previous one first.
        cursor.execute(
            "UPDATE reduction_goals SET status = 'archived' "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )
        cursor.execute("""
            INSERT INTO reduction_goals (
                user_id, baseline_kg, target_kg, start_date, target_date, status
            )
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (
            user_id,
            float(baseline_kg),
            float(target_kg),
            str(start_date),
            str(target_date),
        ))
        goal_id = cursor.lastrowid
        conn.commit()
        EventBus.publish(ReductionGoalChanged())
        return goal_id
    except sqlite3.Error as exc:
        logger.error("Unable to save reduction goal: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_active_goal(user_id: int) -> dict[str, Any] | None:
    """Return the user's current active goal, or None."""
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, baseline_kg, target_kg, start_date,
                   target_date, status, created_at
            FROM reduction_goals
            WHERE user_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,))
        return _goal_row_to_dict(cursor.fetchone())
    except sqlite3.Error as exc:
        logger.error("Unable to load active goal: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_goal_history(user_id: int) -> list[dict[str, Any]]:
    """Return every goal the user has ever set, newest first."""
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, baseline_kg, target_kg, start_date,
                   target_date, status, created_at
            FROM reduction_goals
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user_id,))
        return [_goal_row_to_dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("Unable to load goal history: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


def update_goal_status(goal_id: int, status: str) -> bool:
    """Move a goal to a new lifecycle state (archived / completed / active)."""
    if status not in ("active", "archived", "completed"):
        logger.error("Refusing to set unknown goal status: %s", status)
        return False

    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reduction_goals SET status = ? WHERE id = ?",
            (status, goal_id),
        )
        changed = cursor.rowcount > 0
        conn.commit()
        EventBus.publish(ReductionGoalChanged())
        return changed
    except sqlite3.Error as exc:
        logger.error("Unable to update goal status: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def archive_goal(goal_id: int) -> bool:
    """Retire a goal without marking it as met."""
    return update_goal_status(goal_id, "archived")


def complete_goal(goal_id: int) -> bool:
    """Mark a goal as successfully achieved."""
    return update_goal_status(goal_id, "completed")


def delete_reduction_goal(goal_id: int) -> bool:
    """Permanently remove a goal row."""
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reduction_goals WHERE id = ?", (goal_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        EventBus.publish(ReductionGoalChanged())
        return deleted
    except sqlite3.Error as exc:
        logger.error("Unable to delete reduction goal: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def init_waste_db() -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS waste_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                food_scraps REAL DEFAULT 0,
                plastic_packaging REAL DEFAULT 0,
                paper_cardboard REAL DEFAULT 0,
                glass REAL DEFAULT 0,
                metal_cans REAL DEFAULT 0,
                e_waste REAL DEFAULT 0,
                textiles REAL DEFAULT 0,
                mixed_waste REAL DEFAULT 0,
                total_weekly_kg REAL DEFAULT 0,
                annual_co2 REAL DEFAULT 0,
                recyclable_pct REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Waste DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def save_waste_assessment(user_id: int, waste_data: dict[str, float], total_weekly_kg: float, annual_co2: float, recyclable_pct: float) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO waste_assessments (
                user_id, food_scraps, plastic_packaging, paper_cardboard,
                glass, metal_cans, e_waste, textiles, mixed_waste,
                total_weekly_kg, annual_co2, recyclable_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            waste_data.get("Food Scraps", 0),
            waste_data.get("Plastic Packaging", 0),
            waste_data.get("Paper & Cardboard", 0),
            waste_data.get("Glass", 0),
            waste_data.get("Metal (Cans)", 0),
            waste_data.get("Electronics (E-Waste)", 0),
            waste_data.get("Textiles", 0),
            waste_data.get("Other (Mixed Waste)", 0),
            total_weekly_kg, annual_co2, recyclable_pct,
        ))
        conn.commit()
        get_waste_assessments.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Waste assessment save error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_waste_assessments(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM waste_assessments WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        logger.error("Waste assessment read error: %s", e)
        return []
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Unit and currency preferences
# ---------------------------------------------------------------------------

def init_unit_preferences() -> bool:
    """
    Add the unit_system and currency columns to the users table.

    Uses the same defensive ALTER-and-swallow pattern already used for
    anonymous_leaderboard in init_db(), so it is safe to call repeatedly and on
    a database that already has the columns.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        for statement in (
            "ALTER TABLE users ADD COLUMN unit_system TEXT DEFAULT 'metric'",
            "ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'USD'",
        ):
            try:
                cursor.execute(statement)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Unit preference init error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def save_unit_preference(user_id: int, unit_system: str, currency: str) -> bool:
    """
    Persist a user's display preference.

    The value is normalised through src.utils.units.make_preference() first, so an
    unknown system or currency is stored as the default rather than as
    something no page can render.
    """
    from src.utils.units import make_preference

    preference = make_preference(unit_system, currency)
    init_unit_preferences()

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET unit_system = ?, currency = ? WHERE id = ?",
            (preference["system"], preference["currency"], user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as exc:
        logger.error("Unable to save unit preference: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def get_unit_preference(user_id: int) -> dict[str, Any]:
    """
    Return a user's display preference, defaulting to metric + USD.

    Never raises and never returns None: every page reads this on load, so a
    missing user, a missing column or a corrupted value must all degrade to the
    default rather than break the page.
    """
    from src.utils.units import make_preference

    init_unit_preferences()

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT unit_system, currency FROM users WHERE id = ?", (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            return make_preference()
        return make_preference(row[0], row[1])
    except sqlite3.Error as exc:
        logger.error("Unable to read unit preference: %s", exc)
        return make_preference()
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Community Polls
# ---------------------------------------------------------------------------

def init_community_polls_db() -> bool:
    """Initialize database tables for community polls."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS community_polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                status TEXT DEFAULT 'active',
                created_by TEXT DEFAULT 'Community',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                vote_count INTEGER DEFAULT 0,
                FOREIGN KEY (poll_id) REFERENCES community_polls (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                user_identifier TEXT NOT NULL,
                option_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(poll_id, user_identifier),
                FOREIGN KEY (poll_id) REFERENCES community_polls (id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES poll_options (id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Community polls DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def seed_community_polls() -> None:
    """Seed sample sustainability community polls if table is empty."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM community_polls")
        if cursor.fetchone()[0] > 0:
            return

        sample_polls = [
            (
                "What is your primary action for reducing personal carbon footprint in 2026?",
                "Lifestyle",
                "active",
                "EcoBuddy Team",
                [
                    ("Switching to plant-based diet", 45),
                    ("Using public transport & biking", 38),
                    ("Installing solar panels / renewable energy", 29),
                    ("Reducing single-use plastic & waste", 52),
                ],
            ),
            (
                "Which sector needs the most aggressive climate policy enforcement?",
                "Policy",
                "active",
                "EcoBuddy Team",
                [
                    ("Energy & Electricity Generation", 60),
                    ("Industrial Manufacturing & Heavy Industry", 42),
                    ("Transportation & Logistics", 31),
                    ("Agriculture & Deforestation", 25),
                ],
            ),
            (
                "What was the most impactful eco-habit you adopted last year?",
                "Community",
                "archived",
                "Community",
                [
                    ("Composting organic waste", 85),
                    ("Eliminating fast fashion purchases", 64),
                    ("Switching to EV / E-bike", 40),
                    ("Smart home energy management", 53),
                ],
            ),
        ]

        for question, category, status, created_by, options in sample_polls:
            cursor.execute("""
                INSERT INTO community_polls (question, category, status, created_by)
                VALUES (?, ?, ?, ?)
            """, (question, category, status, created_by))
            poll_id = cursor.lastrowid
            for opt_text, count in options:
                cursor.execute("""
                    INSERT INTO poll_options (poll_id, option_text, vote_count)
                    VALUES (?, ?, ?)
                """, (poll_id, opt_text, count))

        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to seed community polls: %s", e)
    finally:
        if conn:
            conn.close()


def create_poll(question: str, options: list[str], category: str = "General", created_by: str = "Community") -> int | None:
    """Create a new poll with given options."""
    if not question.strip() or len(options) < 2:
        return None
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO community_polls (question, category, status, created_by)
            VALUES (?, ?, 'active', ?)
        """, (question.strip(), category, created_by))
        poll_id = cursor.lastrowid
        for opt in options:
            if opt.strip():
                cursor.execute("""
                    INSERT INTO poll_options (poll_id, option_text, vote_count)
                    VALUES (?, ?, 0)
                """, (poll_id, opt.strip()))
        conn.commit()
        get_active_polls.clear()
        get_archived_polls.clear()
        return poll_id
    except sqlite3.Error as e:
        logger.error("Failed to create poll: %s", e)
        return None
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_active_polls() -> list[dict]:
    """Retrieve all active community polls with their options and vote counts."""
    seed_community_polls()
    return _fetch_polls_by_status("active")


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_archived_polls() -> list[dict]:
    """Retrieve all archived community polls with final results."""
    seed_community_polls()
    return _fetch_polls_by_status("archived")


def _fetch_polls_by_status(status: str) -> list[dict]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, question, category, status, created_by, created_at
            FROM community_polls
            WHERE status = ?
            ORDER BY created_at DESC
        """, (status,))
        poll_rows = cursor.fetchall()
        polls = []
        for p in poll_rows:
            poll_id = p[0]
            cursor.execute("""
                SELECT id, option_text, vote_count
                FROM poll_options
                WHERE poll_id = ?
                ORDER BY id ASC
            """, (poll_id,))
            option_rows = cursor.fetchall()
            options = [
                {"id": opt[0], "option_text": opt[1], "vote_count": opt[2]}
                for opt in option_rows
            ]
            total_votes = sum(opt["vote_count"] for opt in options)
            polls.append({
                "id": poll_id,
                "question": p[1],
                "category": p[2],
                "status": p[3],
                "created_by": p[4],
                "created_at": p[5],
                "options": options,
                "total_votes": total_votes,
            })
        return polls
    except sqlite3.Error as e:
        logger.error("Failed to fetch polls: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def has_user_voted(poll_id: int, user_identifier: str) -> bool:
    """Check if a specific user/identifier has already voted on a poll."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM poll_votes WHERE poll_id = ? AND user_identifier = ?
        """, (poll_id, str(user_identifier)))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error("Error checking poll vote: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def vote_poll(poll_id: int, option_id: int, user_identifier: str) -> bool:
    """Record an anonymous vote for an option in a poll."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check if already voted
        cursor.execute("""
            SELECT 1 FROM poll_votes WHERE poll_id = ? AND user_identifier = ?
        """, (poll_id, str(user_identifier)))
        if cursor.fetchone():
            return False

        cursor.execute("""
            INSERT INTO poll_votes (poll_id, user_identifier, option_id)
            VALUES (?, ?, ?)
        """, (poll_id, str(user_identifier), option_id))

        cursor.execute("""
            UPDATE poll_options SET vote_count = vote_count + 1 WHERE id = ? AND poll_id = ?
        """, (option_id, poll_id))

        conn.commit()
        get_active_polls.clear()
        get_archived_polls.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to record vote: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def archive_poll(poll_id: int) -> bool:
    """Archive a poll by ID."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE community_polls SET status = 'archived' WHERE id = ?", (poll_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        get_active_polls.clear()
        get_archived_polls.clear()
        return changed
    except sqlite3.Error as e:
        logger.error("Failed to archive poll: %s", e)
        return False
    finally:
        if conn:
            conn.close()

def create_time_capsule(user_id: int, title: str, promise_text: str, category: str, unlock_date: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO time_capsules (user_id, title, promise_text, category, unlock_date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, title, promise_text, category, unlock_date))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return True
    except sqlite3.Error as e:
        logger.error("create_time_capsule error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_time_capsules(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, title, promise_text, category,
                   unlock_date, is_unlocked, unlocked_at, progress_notes,
                   created_at, updated_at
            FROM time_capsules
            WHERE user_id = ?
            ORDER BY unlock_date ASC, created_at DESC
        """, (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


def update_time_capsule_unlock(capsule_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE time_capsules
            SET is_unlocked = 1, unlocked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_unlocked = 0
        """, (capsule_id,))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("update_time_capsule_unlock error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def update_time_capsule_progress(capsule_id: int, progress_notes: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE time_capsules
            SET progress_notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (progress_notes, capsule_id))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return True
    except sqlite3.Error as e:
        logger.error("update_time_capsule_progress error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def delete_time_capsule(capsule_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM time_capsules WHERE id = ?", (capsule_id,))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return True
    except sqlite3.Error as e:
        logger.error("delete_time_capsule error: %s", e)
        return False
    finally:
        if conn:
            conn.close()
def save_weekly_challenge(user_id: int, title: str, difficulty: str, xp: int, category: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO weekly_challenges
        (user_id,title,difficulty,xp,category)
        VALUES(?,?,?,?,?)
    """,(user_id,title,difficulty,xp,category))

    conn.commit()
    conn.close()

    return True
def get_weekly_challenges(user_id: int) -> list[tuple[Any, ...]]:

    conn=sqlite3.connect(DB_NAME)
    cursor=conn.cursor()

    cursor.execute("""
    SELECT *
    FROM weekly_challenges
    WHERE user_id=?
    ORDER BY created_at DESC
    """,(user_id,))

    data=cursor.fetchall()

    conn.close()

    return data
def complete_weekly_challenge(challenge_id: int) -> bool:

    conn=sqlite3.connect(DB_NAME)
    cursor=conn.cursor()

    cursor.execute("""
    UPDATE weekly_challenges
    SET status='Completed'
    WHERE id=?
    """,(challenge_id,))

    conn.commit()

    conn.close()

    return True


def weekly_challenges_exist(user_id: int) -> bool:
    """True if this user already has challenges generated in the last 7 days."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    last_week = datetime.now() - timedelta(days=7)

    cursor.execute("""
        SELECT COUNT(*)
        FROM weekly_challenges
        WHERE user_id = ?
        AND created_at >= ?
    """, (user_id, last_week))

    count = cursor.fetchone()[0]

    conn.close()

    return count > 0


def get_completed_challenges(user_id: int) -> list[tuple[Any, ...]]:
    """Completed challenges for a user, newest first."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title,difficulty,created_at
        FROM weekly_challenges
        WHERE user_id=?
        AND status='Completed'
        ORDER BY created_at DESC
    """,(user_id,))

    data = cursor.fetchall()

    conn.close()

    return data


# ---------------------------------------------------------------------------
# The four blocks below were added by their feature PRs and lost by a later
# merge, while the modules, pages and tests that call them stayed. Restored
# verbatim from the commits that introduced them:
#   sustainable brands      b39dbb6
#   climate careers         b6f1bd7
#   environmental datasets  3237ce7
#   historical events       14a0a29
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Sustainable Brand Directory
# ---------------------------------------------------------------------------

def init_brand_directory_db() -> bool:
    """Initialize the sustainable brands database table."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sustainable_brands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                sustainability_rating TEXT NOT NULL,
                eco_score INTEGER NOT NULL,
                certifications TEXT,
                description TEXT,
                website TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Sustainable brand DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def seed_sustainable_brands() -> None:
    """Seed initial sustainable brand listings if table is empty."""
    init_brand_directory_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sustainable_brands")
        if cursor.fetchone()[0] > 0:
            return

        initial_brands = [
            (
                "Patagonia",
                "Apparel & Footwear",
                "A+",
                96,
                "B Corp, Fair Trade Certified, 1% for the Planet",
                "High-performance outdoor clothing made from recycled materials with lifetime repair warranty.",
                "https://www.patagonia.com",
            ),
            (
                "Allbirds",
                "Apparel & Footwear",
                "A",
                90,
                "B Corp, Carbon Neutral, FSC Certified",
                "Footwear and apparel crafted from natural, sustainable materials like merino wool and eucalyptus tree fiber.",
                "https://www.allbirds.com",
            ),
            (
                "Beyond Meat",
                "Food & Beverage",
                "A",
                88,
                "Non-GMO Project Verified, Plant-Based Certified",
                "Revolutionary plant-based meats designed to replace animal agriculture and cut carbon src.carbon.emissions.",
                "https://www.beyondmeat.com",
            ),
            (
                "Tentree",
                "Apparel & Footwear",
                "A+",
                94,
                "B Corp, Climate Neutral, Organic Content Standard",
                "Eco-friendly lifestyle apparel brand that plants 10 trees for every item purchased.",
                "https://www.tentree.com",
            ),
            (
                "Seventh Generation",
                "Home & Energy",
                "A",
                89,
                "B Corp, USDA Certified Biobased, Leaping Bunny",
                "Plant-derived household cleaning, paper, and personal care products reducing chemical footprint.",
                "https://www.seventhgeneration.com",
            ),
            (
                "Fairphone",
                "Tech & Electronics",
                "A+",
                95,
                "B Corp, Fairtrade Gold, EcoVadis Platinum",
                "Modular, repairable smartphones designed to reduce electronic waste and respect supply chain labor.",
                "https://www.fairphone.com",
            ),
            (
                "Ethique",
                "Personal Care",
                "A+",
                97,
                "B Corp, Cruelty-Free, Palm Oil Free, Plastic Free",
                "Solid beauty and personal care bars replacing single-use plastic bottles.",
                "https://ethique.com",
            ),
            (
                "Ecover",
                "Home & Energy",
                "B+",
                83,
                "B Corp, Leaping Bunny",
                "Eco-friendly cleaning supplies packaged in plant-based plastic bottles.",
                "https://www.ecover.com",
            ),
            (
                "Oatly",
                "Food & Beverage",
                "A",
                91,
                "Non-GMO, Climate Footprint Labeled",
                "Original oat milk producers reducing livestock agriculture impacts.",
                "https://www.oatly.com",
            ),
            (
                "Tesla",
                "Transportation",
                "B+",
                84,
                "Zero Emission Vehicle Pioneer",
                "Electric vehicles and clean solar energy storage systems.",
                "https://www.tesla.com",
            ),
        ]

        cursor.executemany("""
            INSERT OR IGNORE INTO sustainable_brands
            (name, category, sustainability_rating, eco_score, certifications, description, website)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, initial_brands)
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to seed sustainable brands: %s", e)
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_sustainable_brands(category: str | None = None, search_query: str | None = None) -> list[dict]:
    """Retrieve sustainable brands with optional category and search query filtering."""
    seed_sustainable_brands()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        query = "SELECT id, name, category, sustainability_rating, eco_score, certifications, description, website, created_at FROM sustainable_brands WHERE 1=1"
        params: list[object] = []

        if category and category != "All Categories":
            query += " AND category = ?"
            params.append(category)

        if search_query:
            query += " AND (name LIKE ? OR description LIKE ? OR certifications LIKE ?)"
            term = f"%{search_query}%"
            params.extend([term, term, term])

        query += " ORDER BY eco_score DESC, name ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = ["id", "name", "category", "sustainability_rating", "eco_score", "certifications", "description", "website", "created_at"]
        return [dict(zip(columns, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error("Failed to read sustainable brands: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def add_sustainable_brand(
    name: str,
    category: str,
    sustainability_rating: str,
    eco_score: int,
    certifications: str,
    description: str,
    website: str,
) -> bool:
    """Add a new sustainable brand entry."""
    init_brand_directory_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sustainable_brands (name, category, sustainability_rating, eco_score, certifications, description, website)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, category, sustainability_rating, eco_score, certifications, description, website))
        conn.commit()
        get_sustainable_brands.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to add sustainable brand: %s", e)
        return False
    finally:
        if conn:
            conn.close()




# ---------------------------------------------------------------------------
# Climate Career Hub
# ---------------------------------------------------------------------------

def init_climate_careers_db() -> bool:
    """Initialize database tables for Climate Career Hub."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS climate_careers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                type TEXT NOT NULL,
                domain TEXT NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                apply_url TEXT NOT NULL,
                posted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS career_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                career_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, career_id),
                FOREIGN KEY (career_id) REFERENCES climate_careers (id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Climate careers DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def seed_climate_careers() -> None:
    """Seed initial climate career listings if table is empty."""
    init_climate_careers_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM climate_careers")
        if cursor.fetchone()[0] > 0:
            return

        initial_careers = [
            (
                "Solar Energy Systems Engineer",
                "SunPower Technologies",
                "Full-Time Jobs",
                "Renewable Energy",
                "Remote",
                "Design scalable commercial solar PV systems and grid interconnection architectures.",
                "https://example.com/careers/solar-engineer",
            ),
            (
                "Climate Tech Policy Fellow",
                "Global Clean Energy Institute",
                "Fellowships",
                "Climate Policy",
                "Hybrid - Washington DC",
                "Conduct research on decarbonization policies and present reports to international policymakers.",
                "https://example.com/careers/policy-fellow",
            ),
            (
                "Carbon Accounting & Footprint Analyst",
                "Terraform Carbon Solutions",
                "Full-Time Jobs",
                "Carbon Capture",
                "Remote",
                "Help enterprise clients audit Scope 1, 2, and 3 GHG emissions and achieve net-zero targets.",
                "https://example.com/careers/carbon-analyst",
            ),
            (
                "Sustainable Agriculture Research Intern",
                "EcoSoil Labs",
                "Internships",
                "Sustainable Agriculture",
                "On-site - Davis, CA",
                "Assist field trials evaluating regenerative soil microbiology and organic bio-fertilizers.",
                "https://example.com/careers/agri-intern",
            ),
            (
                "Circular Economy & Waste Reduction Specialist",
                "ZeroWaste Solutions",
                "Full-Time Jobs",
                "Circular Economy",
                "Hybrid - Berlin, Germany",
                "Develop closed-loop product recycling workflows and packaging redesign strategies.",
                "https://example.com/careers/circular-specialist",
            ),
            (
                "EV Fleet Integration Volunteer",
                "Clean Transit Alliance",
                "Volunteer",
                "Clean Mobility",
                "Remote",
                "Support municipal transit agencies in planning electric bus route electrification schedules.",
                "https://example.com/careers/ev-volunteer",
            ),
            (
                "Direct Air Capture R&D Fellow",
                "Climeworks Institute",
                "Fellowships",
                "Carbon Capture",
                "On-site - Zurich, Switzerland",
                "Perform novel chemical sorbent synthesis and test direct air carbon capture efficiency.",
                "https://example.com/careers/dac-fellow",
            ),
        ]

        cursor.executemany("""
            INSERT INTO climate_careers (title, company, type, domain, location, description, apply_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, initial_careers)
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to seed climate careers: %s", e)
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_career_opportunities(
    opportunity_type: str | None = None,
    domain: str | None = None,
    location: str | None = None,
    search_query: str | None = None,
) -> list[dict]:
    """Retrieve filtered climate career opportunities."""
    seed_climate_careers()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        query = "SELECT id, title, company, type, domain, location, description, apply_url, posted_date FROM climate_careers WHERE 1=1"
        params: list[object] = []

        if opportunity_type and opportunity_type != "All Types":
            query += " AND type = ?"
            params.append(opportunity_type)

        if domain and domain != "All Domains":
            query += " AND domain = ?"
            params.append(domain)

        if location and location != "All Locations":
            query += " AND location LIKE ?"
            params.append(f"%{location}%")

        if search_query:
            query += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
            term = f"%{search_query}%"
            params.extend([term, term, term])

        query += " ORDER BY posted_date DESC, id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cols = ["id", "title", "company", "type", "domain", "location", "description", "apply_url", "posted_date"]
        return [dict(zip(cols, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error("Failed to read climate careers: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def add_career_opportunity(
    title: str,
    company: str,
    opportunity_type: str,
    domain: str,
    location: str,
    description: str,
    apply_url: str,
) -> bool:
    """Add a new climate career listing."""
    init_climate_careers_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO climate_careers (title, company, type, domain, location, description, apply_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, company, opportunity_type, domain, location, description, apply_url))
        conn.commit()
        get_career_opportunities.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to add career opportunity: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def toggle_career_bookmark(user_id: int, career_id: int) -> bool:
    """Toggle bookmark status for a career listing."""
    init_climate_careers_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM career_bookmarks WHERE user_id = ? AND career_id = ?", (user_id, career_id))
        row = cursor.fetchone()
        if row:
            cursor.execute("DELETE FROM career_bookmarks WHERE user_id = ? AND career_id = ?", (user_id, career_id))
        else:
            cursor.execute("INSERT INTO career_bookmarks (user_id, career_id) VALUES (?, ?)", (user_id, career_id))
        conn.commit()
        get_bookmarked_careers.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to toggle career bookmark: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_bookmarked_careers(user_id: int) -> list[dict]:
    """Retrieve all career listings bookmarked by a user."""
    init_climate_careers_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.id, c.title, c.company, c.type, c.domain, c.location, c.description, c.apply_url, c.posted_date
            FROM climate_careers c
            INNER JOIN career_bookmarks b ON c.id = b.career_id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        cols = ["id", "title", "company", "type", "domain", "location", "description", "apply_url", "posted_date"]
        return [dict(zip(cols, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error("Failed to read bookmarked careers: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def is_career_bookmarked(user_id: int, career_id: int) -> bool:
    """Check if a career listing is bookmarked by user."""
    init_climate_careers_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM career_bookmarks WHERE user_id = ? AND career_id = ?", (user_id, career_id))
        return cursor.fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()




# ---------------------------------------------------------------------------
# Open Environmental Data Explorer
# ---------------------------------------------------------------------------

def init_environmental_datasets_db() -> bool:
    """Initialize database table for open environmental datasets."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS environmental_datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                provider TEXT NOT NULL,
                license TEXT DEFAULT 'CC-BY-4.0',
                update_frequency TEXT DEFAULT 'Monthly',
                description TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Environmental datasets DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def seed_environmental_datasets() -> None:
    """Seed sample open environmental datasets if table is empty."""
    init_environmental_datasets_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM environmental_datasets")
        if cursor.fetchone()[0] > 0:
            return

        sample_datasets = [
            (
                "Global Atmospheric CO2 Concentration Trends (2015-2025)",
                "Global Carbon Emissions",
                "NOAA / Mauna Loa Observatory",
                "Public Domain",
                "Monthly",
                "Historical atmospheric carbon dioxide levels measured in parts per million (ppm).",
                '{"headers":["Year","Average_PPM","Yearly_Increase_PPM"],"records":[['
                '2015,400.8,2.2],[2017,406.5,2.1],[2019,411.4,2.5],[2021,416.4,2.4],[2023,421.1,2.6],[2025,426.5,2.7]]}',
            ),
            (
                "Major World Cities Air Quality Index (AQI)",
                "Air Quality Index",
                "World Air Quality Project",
                "CC-BY-4.0",
                "Real-time / Daily",
                "Air Pollution index tracking PM2.5, PM10, and Ozone across major global capitals.",
                '{"headers":["City","Country","AQI_Score","Status","PM2_5_ug_m3"],"records":[['
                '"Tokyo","Japan",24,"Good",5.8],["Reykjavik","Iceland",12,"Good",3.1],["London","UK",42,"Moderate",10.2],["Delhi","India",185,"Unhealthy",112.5],["New York","USA",38,"Good",9.1]]}',
            ),
            (
                "Global Renewable Energy Generation Capacity (GW)",
                "Renewable Energy Growth",
                "International Renewable Energy Agency (IRENA)",
                "Open Data License",
                "Annual",
                "Installed capacity breakdown for solar, wind, hydro, and bioenergy worldwide.",
                '{"headers":["Year","Solar_GW","Wind_GW","Hydro_GW","Bioenergy_GW","Total_GW"],"records":[['
                '2018,485,564,1292,120,2461],[2020,714,733,1331,130,2908],[2022,1053,899,1393,142,3487],[2024,1418,1070,1440,154,4082],[2026,1820,1260,1480,165,4725]]}',
            ),
            (
                "Tropical Deforestation Loss by Region (Hectares)",
                "Deforestation Rates",
                "Global Forest Watch",
                "CC-BY-4.0",
                "Annual",
                "Annual primary rainforest canopy loss in South America, Southeast Asia, and Central Africa.",
                '{"headers":["Year","Amazon_Ha","Congo_Basin_Ha","Southeast_Asia_Ha"],"records":[['
                '2020,1850000,820000,640000],[2022,1620000,790000,580000],[2024,1310000,740000,490000],[2025,1150000,690000,430000]]}',
            ),
            (
                "Global Ocean Temperature Anomaly (°C)",
                "Ocean Temperatures",
                "NASA Goddard Institute for Space Studies",
                "Public Domain",
                "Monthly",
                "Global sea surface surface temperature anomalies relative to the 1951-1980 baseline.",
                '{"headers":["Year","Anomaly_C","Heat_Content_ZJ"],"records":[['
                '2016,0.76,215],[2018,0.70,228],[2020,0.82,242],[2022,0.85,257],[2024,0.98,276],[2026,1.04,291]]}',
            ),
        ]

        cursor.executemany("""
            INSERT OR IGNORE INTO environmental_datasets
            (title, category, provider, license, update_frequency, description, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_datasets)
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to seed environmental datasets: %s", e)
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_environmental_datasets(category: str | None = None, search_query: str | None = None) -> list[dict]:
    """Retrieve environmental datasets filtered by category and search term."""
    seed_environmental_datasets()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        query = "SELECT id, title, category, provider, license, update_frequency, description, data_json, created_at FROM environmental_datasets WHERE 1=1"
        params: list[object] = []

        if category and category != "All Categories":
            query += " AND category = ?"
            params.append(category)

        if search_query:
            query += " AND (title LIKE ? OR provider LIKE ? OR description LIKE ?)"
            term = f"%{search_query}%"
            params.extend([term, term, term])

        query += " ORDER BY id ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cols = ["id", "title", "category", "provider", "license", "update_frequency", "description", "data_json", "created_at"]
        return [dict(zip(cols, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error("Failed to read environmental datasets: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def add_environmental_dataset(
    title: str,
    category: str,
    provider: str,
    license: str,
    update_frequency: str,
    description: str,
    data_json: str,
) -> bool:
    """Add a new open environmental dataset."""
    init_environmental_datasets_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO environmental_datasets (title, category, provider, license, update_frequency, description, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, category, provider, license, update_frequency, description, data_json))
        conn.commit()
        get_environmental_datasets.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to add environmental dataset: %s", e)
        return False
    finally:
        if conn:
            conn.close()




# ---------------------------------------------------------------------------
# Environmental Timeline & Historical Events
# ---------------------------------------------------------------------------

def init_historical_events_db() -> bool:
    """Initialize database table for historical environmental events."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historical_environmental_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                title TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                impact_summary TEXT NOT NULL,
                educational_resources TEXT,
                source_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Historical events DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def seed_historical_events() -> None:
    """Seed key global climate history milestones if table is empty."""
    init_historical_events_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM historical_environmental_events")
        if cursor.fetchone()[0] > 0:
            return

        events = [
            (
                1970,
                "First Earth Day Founded",
                "Climate Movements",
                "20 million Americans demonstrated across the US, launching the modern environmental movement and leading to the creation of the EPA.",
                "Catalyzed landmark legislation including the Clean Air Act, Clean Water Act, and Endangered Species Act.",
                "Earth Day Network Educational Guides, EPA History Archive",
                "https://www.earthday.org/history/",
            ),
            (
                1987,
                "Montreal Protocol Signed",
                "Policy & Treaties",
                "Landmark international treaty adopted to phase out ozone-depleting substances like CFCs globally.",
                "Phase-out of over 99% of controlled ozone-depleting substances, putting the stratospheric ozone layer on track to heal by 2060.",
                "UNEP Ozone Secretariat Reports, NASA Ozone Watch",
                "https://ozone.unep.org/",
            ),
            (
                1988,
                "Intergovernmental Panel on Climate Change (IPCC) Established",
                "Scientific Discoveries",
                "UN Environment Programme and WMO established the IPCC to assess climate change science objectively.",
                "Published assessment reports providing the scientific foundation for international negotiations under the UNFCCC.",
                "IPCC Assessment Reports, Climate Change Science Primers",
                "https://www.ipcc.ch/",
            ),
            (
                1997,
                "Kyoto Protocol Adopted",
                "Policy & Treaties",
                "First international agreement committing industrialized nations to legally binding greenhouse gas emission reduction targets.",
                "Established market-based mechanisms such as carbon trading and the Clean Development Mechanism (CDM).",
                "UNFCCC Kyoto Protocol Guide",
                "https://unfccc.int/kyoto_protocol",
            ),
            (
                2015,
                "Paris Climate Agreement Adopted",
                "Policy & Treaties",
                "Historic accord signed by 196 parties at COP21 aiming to limit global warming to well below 2.0°C, preferably 1.5°C, above pre-industrial levels.",
                "Created national Nationally Determined Contributions (NDCs) framework and global net-zero pledge benchmarks.",
                "UN Climate Change Paris Agreement Overview",
                "https://unfccc.int/process-and-meetings/the-paris-agreement",
            ),
            (
                2018,
                "Global Fridays for Future Youth Movement",
                "Climate Movements",
                "Greta Thunberg initiated school strikes for climate outside the Swedish parliament, sparking global youth mobilizations.",
                "Mobilized over 4 million students and activists worldwide to demand urgent political climate action.",
                "Fridays For Future Movement Archives & Toolkits",
                "https://fridaysforfuture.org/",
            ),
            (
                2023,
                "COP28 UAE Consensus on Transitioning Away from Fossil Fuels",
                "Policy & Treaties",
                "For the first time in 28 years of UN climate summits, agreement explicitly called on all nations to transition away from fossil fuels in energy systems.",
                "Pledged to triple global renewable energy capacity and double energy efficiency improvements by 2030.",
                "UNFCCC COP28 Outcome Reports",
                "https://cop28.com/",
            ),
        ]

        cursor.executemany("""
            INSERT OR IGNORE INTO historical_environmental_events
            (year, title, category, description, impact_summary, educational_resources, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, events)
        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to seed historical events: %s", e)
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_historical_events(category: str | None = None, search_query: str | None = None) -> list[dict]:
    """Retrieve historical environmental events with category and search filtering."""
    seed_historical_events()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        query = "SELECT id, year, title, category, description, impact_summary, educational_resources, source_url, created_at FROM historical_environmental_events WHERE 1=1"
        params: list[object] = []

        if category and category != "All Categories":
            query += " AND category = ?"
            params.append(category)

        if search_query:
            query += " AND (title LIKE ? OR description LIKE ? OR impact_summary LIKE ? OR CAST(year AS TEXT) LIKE ?)"
            term = f"%{search_query}%"
            params.extend([term, term, term, term])

        query += " ORDER BY year ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cols = ["id", "year", "title", "category", "description", "impact_summary", "educational_resources", "source_url", "created_at"]
        return [dict(zip(cols, row)) for row in rows]
    except sqlite3.Error as e:
        logger.error("Failed to read historical events: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def add_historical_event(
    year: int,
    title: str,
    category: str,
    description: str,
    impact_summary: str,
    educational_resources: str = "",
    source_url: str = "",
) -> bool:
    """Add a new historical environmental event."""
    init_historical_events_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historical_environmental_events
            (year, title, category, description, impact_summary, educational_resources, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (year, title, category, description, impact_summary, educational_resources, source_url))
        conn.commit()
        get_historical_events.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to add historical event: %s", e)
        return False
    finally:
        if conn:
            conn.close()
import os
import sqlite3
from src.community.challenge_generator import generate_weekly_challenges
from src.core.database_connection import database_connection, execute_with_retry
from src.core.cache import cached
from src.core.cache_config import TTL_DB_READ, CACHE_CATEGORY_DB_READS
from src.core.event_bus import EventBus
from src.core.domain_events import (
    AssessmentSaved,
    AssessmentUndone,
    ApplianceChanged,
    SolarConfigSaved,
    ChallengeEnrolled,
    ChallengeProgressed,
    ChallengeCompleted,
    XPAwarded,
    BadgeUnlocked,
    SkillTreeUpdated,
    JourneySaved,
    JourneyDeleted,
    OffsetSaved,
    OffsetDeleted,
    OffsetCleared,
    WaterAssessmentSaved,
    ReductionGoalChanged,
    FreezeTokenChanged,
    TimeCapsuleChanged,
)
import streamlit as st
import bcrypt
import logging
from typing import Any

logger = logging.getLogger(__name__)
DB_NAME = os.getenv("ECO_BUDDY_DB", "eco_buddy.db")


def get_db_version(conn: sqlite3.Connection) -> int:
    """Get the current database schema version using PRAGMA user_version."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    return cursor.fetchone()[0]


def set_db_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the database schema version using PRAGMA user_version."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA user_version = {version}")
    conn.commit()


def migrate() -> tuple[bool, str]:
    """
    Apply pending database migrations.

    Returns:
        tuple: (success: bool, message: str)
    """
    import migrations

    try:
        with database_connection(DB_NAME) as conn:
            current_version = get_db_version(conn)

            if current_version >= migrations.CURRENT_VERSION:
                return True, (
                    f"Database is already at version {current_version}"
                )

            migrations_to_apply = range(
                current_version + 1,
                migrations.CURRENT_VERSION + 1,
            )
            for version in migrations_to_apply:
                migration_file = f"migrations/migrate_v{version}.py"
                if os.path.exists(migration_file):
                    module = __import__(
                        f"migrations.migrate_v{version}",
                        fromlist=["migrate"],
                    )
                    if hasattr(module, "migrate"):
                        module.migrate(conn)
                        set_db_version(conn, version)
                        print(f"Applied migration v{version}")

        return True, (
            f"Database migrated to version {migrations.CURRENT_VERSION}"
        )
    except Exception as exc:
        return False, f"Migration failed: {exc}"


def init_db() -> bool:
    """
    Initialize the database with core tables and run pending migrations.

    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    try:
        def initialize_schema() -> None:
            with database_connection(DB_NAME) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        anonymous_leaderboard INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute("""
CREATE TABLE IF NOT EXISTS weekly_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    xp INTEGER NOT NULL,
    category TEXT,
    status TEXT DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

                try:
                    cursor.execute(
                        """
                        ALTER TABLE users
                        ADD COLUMN anonymous_leaderboard INTEGER DEFAULT 0
                        """
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER DEFAULT 1,
                        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        transport TEXT,
                        distance REAL,
                        electricity REAL,
                        diet TEXT,
                        flights INTEGER,
                        footprint REAL,
                        eco_score INTEGER,
                        trip_id TEXT
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS carbon_budgets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        budget_type TEXT NOT NULL,
                        budget_limit REAL NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )
                    """
                )

                try:
                    cursor.execute(
                        """
                        ALTER TABLE assessments
                        ADD COLUMN created_at
                        TIMESTAMP DEFAULT '2024-01-01 00:00:00'
                        """
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise

                # Conflict-aware import/export support (#1311): a stable
                # cross-device identifier plus last-modified/source metadata,
                # so an import can tell new, unchanged, updated and
                # conflicting assessments apart instead of matching on the
                # local autoincrement id.
                for column_sql in (
                    "ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                    "ADD COLUMN client_uuid TEXT",
                    "ADD COLUMN source_device TEXT",
                ):
                    try:
                        cursor.execute(f"ALTER TABLE assessments {column_sql}")
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise

                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_assessments_trip_id
                    ON assessments(trip_id)
                    WHERE trip_id IS NOT NULL
                    """
                )

                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_assessments_client_uuid
                    ON assessments(user_id, client_uuid)
                    WHERE client_uuid IS NOT NULL
                    """
                )
                # Immutable calculation-context snapshots. One row per
                # assessment (UNIQUE assessment_id), written once at
                # calculation time and never updated afterwards, so a
                # historical assessment can always be reproduced exactly as
                # it was originally calculated, even after emission factors,
                # category weights, or the eco-score formula change.
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessment_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        assessment_id INTEGER NOT NULL UNIQUE,
                        snapshot_json TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(assessment_id) REFERENCES assessments(id)
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessment_drafts (
                        user_id INTEGER PRIMARY KEY,
                        transport TEXT,                        distance REAL,
                        electricity REAL,
                        diet TEXT,
                        flights INTEGER,
                        region TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS deleted_assessments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_id INTEGER,
                        user_id INTEGER DEFAULT 1,
                        date TIMESTAMP,
                        transport TEXT,
                        distance REAL,
                        electricity REAL,
                        diet TEXT,
                        flights INTEGER,
                        footprint REAL,
                        eco_score INTEGER,
                        deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assessment_activity_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER DEFAULT 1,
                        assessment_id INTEGER,
                        action TEXT NOT NULL,
                        details TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

        execute_with_retry(initialize_schema)
        migrate()
        return True
    except sqlite3.Error as exc:
        logger.error("Database init error: %s", exc)
        return False


def create_user(
    username: str,
    email: str,
    password: str,
    anonymous_leaderboard: bool = False,
) -> bool:
    def insert_user() -> None:
        with database_connection(DB_NAME) as conn:
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")
            conn.execute(
                """
                INSERT INTO users (
                    username,
                    email,
                    password_hash,
                    anonymous_leaderboard
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    password_hash,
                    int(bool(anonymous_leaderboard)),
                ),
            )

    try:
        execute_with_retry(insert_user)
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as exc:
        logger.error("Database user creation error: %s", exc)
        return False


def verify_user(username: str, password: str) -> dict[str, Any] | None:
    def fetch_user() -> dict[str, Any] | None:
        with database_connection(DB_NAME) as conn:
            return conn.execute(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    anonymous_leaderboard
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

    try:
        user = execute_with_retry(fetch_user)

        if user and bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        ):
            return {
                "id": user["id"],
                "username": user["username"],
                "anonymous_leaderboard": bool(
                    user["anonymous_leaderboard"]
                ),
            }
        return None
    except sqlite3.Error as exc:
        logger.error("Database user verification error: %s", exc)
        return None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    def fetch_user() -> dict[str, Any] | None:
        with database_connection(DB_NAME) as conn:
            return conn.execute(
                """
                SELECT
                    id,
                    username,
                    email,
                    anonymous_leaderboard
                FROM users
                WHERE username = ?
                """,
                (username,),
            ).fetchone()

    try:
        user = execute_with_retry(fetch_user)
        if not user:
            return None

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "anonymous_leaderboard": bool(
                user["anonymous_leaderboard"]
            ),
        }
    except sqlite3.Error as exc:
        logger.error("Database user lookup error: %s", exc)
        return None


def update_user_leaderboard_preference(user_id: int, anonymous_leaderboard: bool) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET anonymous_leaderboard = ? WHERE id = ?",
            (int(bool(anonymous_leaderboard)), user_id)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database update user preference error: {e}")
        return False


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_leaderboard(period: str = "all") -> list[tuple[str, int, int, int]]:
    """
    Retrieves community leaderboard rankings.
    Returns list of tuples: (display_name, max_eco_score, total_xp, completed_challenges)
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                u.id,
                u.username,
                u.anonymous_leaderboard,
                COALESCE(MAX(a.eco_score), 0) AS max_eco_score,
                COALESCE(SUM(x.amount), 0) AS total_xp,
                COUNT(DISTINCT c.challenge_id) AS completed_challenges
            FROM users u
            LEFT JOIN assessments a ON u.id = a.user_id
            LEFT JOIN xp_transactions x ON u.id = x.user_id
            LEFT JOIN user_challenges c ON u.id = c.user_id AND c.status = 'completed'
            GROUP BY u.id
            ORDER BY max_eco_score DESC, total_xp DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        leaderboard = []
        for row in rows:
            u_id, username, is_anon, eco_score, xp, challenges = row
            display_name = f"User #{u_id}" if is_anon else username
            leaderboard.append((display_name, eco_score, xp, challenges))

        return leaderboard
    except sqlite3.Error as e:
        print(f"Database get_leaderboard error: {e}")
        return []


def save_assessment(
    user_id: int,
    transport: str,
    distance: float,
    electricity: float,
    diet: str,
    flights: int,
    footprint: float,
    eco_score: int = 0,
    trip_id: str | None = None,
    date: str | None = None,
    factor_version: str | None = None,
    snapshot_json: str | None = None
) -> bool:
    """
    Persist an assessment.

    `factor_version` records which emission factor set produced the footprint
    (see src.carbon.emission_factors.py). It is optional: rows written without it are read
    back as 'static-v1', which is exactly the factor set the app used before
    versioning existed.

    `snapshot_json` is an optional, pre-serialized immutable calculation
    snapshot (see core/assessment_snapshot.py) capturing the full context
    the footprint was computed under: inputs, factor version/provenance,
    calculation-engine version, eco-score config, and category weights.
    When supplied, it is written once to `assessment_snapshots` alongside
    the new assessment row and is never updated afterwards.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Build the column list from whatever the caller actually supplied,
        # so the optional date / trip_id / factor_version columns keep their
        # database defaults when they are omitted.
        columns = [
            "user_id",
            "transport",
            "distance",
            "electricity",
            "diet",
            "flights",
            "footprint",
            "eco_score",
        ]
        values = [
            user_id,
            transport,
            distance,
            electricity,
            diet,
            flights,
            footprint,
            eco_score,
        ]

        if date is not None:
            columns.append("date")
            values.append(date)
        if trip_id is not None:
            columns.append("trip_id")
            values.append(trip_id)
        if factor_version is not None:
            columns.append("factor_version")
            values.append(factor_version)

        placeholders = ", ".join("?" for _ in columns)
        cursor.execute(
            f"INSERT INTO assessments ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values),
        )

        if snapshot_json is not None:
            assessment_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO assessment_snapshots (assessment_id, snapshot_json) VALUES (?, ?)",
                (assessment_id, snapshot_json),
            )

        conn.commit()
        conn.close()
        EventBus.publish(AssessmentSaved())
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"Database save error: {e}")
        return False


def get_assessment_snapshot(assessment_id: int) -> dict[str, Any] | None:
    """
    Read back the immutable calculation snapshot for one assessment.

    Returns None when no snapshot was stored for this assessment (e.g. rows
    created before this feature existed) rather than reconstructing one, so
    callers never mistake a fabricated snapshot for the original.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT snapshot_json FROM assessment_snapshots WHERE assessment_id = ?",
            (assessment_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        import json
        return json.loads(row[0])
    except sqlite3.Error as e:
        print(f"Database get_assessment_snapshot error: {e}")
        return None

# -------------------------------------------------------------------------
# Assessment Timestamp Migration#
# This migration introduces the `created_at` column to the assessments
# table to automatically record when each assessment is created.
#
# The column uses SQLite's `CURRENT_TIMESTAMP` as its default value,
# allowing every newly inserted record to receive an accurate creation
# timestamp without requiring manual handling in application code.
#
# The migration is wrapped in a try/except block to ensure backward
# compatibility with existing databases. If the column already exists,
# SQLite raises an OperationalError, which is safely ignored so the
# application can continue initializing without interruption.
#
# Storing creation timestamps enables future enhancements such as:
#   • Chronological sorting of assessments
#   • Activity history and audit trails
#   • Time-based analytics and reporting
#   • Date range filtering
#   • Exporting records with creation metadata
#
# Existing assessment functionality remains unchanged because SQLite
# automatically populates the timestamp whenever a new record is created.
# -------------------------------------------------------------------------
@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_assessments(user_id: int = 1) -> list[tuple[Any, ...]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, date,created_at, transport, distance, electricity, diet, flights, footprint, eco_score
            FROM assessments
            WHERE user_id = ?
            ORDER BY created_at  DESC, id DESC
        """, (user_id,))

        data = cursor.fetchall()

        conn.close()
        return data
    except sqlite3.Error as e:
        print(f"Database read error: {e}")
        return []

def save_carbon_budget(user_id: int, budget_type: str, budget_limit: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM carbon_budgets WHERE user_id=?",
            (user_id,)
        )

        cursor.execute("""
            INSERT INTO carbon_budgets(user_id,budget_type,budget_limit)
            VALUES(?,?,?)
        """,(user_id,budget_type,budget_limit))

        conn.commit()
        conn.close()

        return True

    except sqlite3.Error as e:
        print(e)
        return False
def get_carbon_budget(user_id: int) -> tuple[str, float] | None:

    try:
        conn=sqlite3.connect(DB_NAME)
        cursor=conn.cursor()

        cursor.execute("""
        SELECT budget_type,budget_limit
        FROM carbon_budgets
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,(user_id,))

        row=cursor.fetchone()

        conn.close()

        return row

    except sqlite3.Error:
        return None
def update_carbon_budget(user_id: int, budget_type: str, budget_limit: float) -> bool:

    try:

        conn=sqlite3.connect(DB_NAME)
        cursor=conn.cursor()

        cursor.execute("""
        UPDATE carbon_budgets
        SET budget_type=?,
            budget_limit=?
        WHERE user_id=?
        """,(budget_type,budget_limit,user_id))

        conn.commit()

        conn.close()

        return True

    except sqlite3.Error:

        return False
@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_assessments_with_factors(user_id: int = 1) -> list[tuple[Any, ...]]:
    """
    Assessments including the factor version each was computed under.

    Kept separate from get_assessments() so the existing nine-column tuple
    shape that every caller already unpacks stays untouched.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, transport,created_at, distance, electricity, diet, flights,
                   footprint, eco_score, factor_version
            FROM assessments
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
        """, (user_id,))
        return cursor.fetchall()
    except sqlite3.Error as exc:
        logger.error("Unable to read assessments with factor versions: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_all_assessments() -> list[tuple[Any, ...]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, date, created_at,transport, distance, electricity, diet, flights, footprint, eco_score
            FROM assessments
            ORDER BY date DESC
            LIMIT 100, id DESC
        """)

        data = cursor.fetchall()

        conn.close()
        return data
    except sqlite3.Error as e:
        print(f"Database read error: {e}")
        return []


def undo_last_assessment(user_id: int = 1) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Undo the user's most recent assessment record.
    Moves record to deleted_assessments table, logs action in activity log,
    and invalidates dependent caches.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Find latest assessment
        cursor.execute(
            """
            SELECT id, date, transport, distance, electricity, diet, flights, footprint, eco_score
            FROM assessments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No assessment found to undo.", None

        rec_id, date, transport, distance, electricity, diet, flights, footprint, eco_score = row

        # Backup into deleted_assessments
        cursor.execute(
            """
            INSERT INTO deleted_assessments (original_id, user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rec_id, user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
        )

        # Delete from assessments table
        cursor.execute("DELETE FROM assessments WHERE id = ?", (rec_id,))

        # Log activity
        details = f"Undone assessment #{rec_id} ({footprint:.1f} kg CO2, score {eco_score})"
        cursor.execute(
            """
            INSERT INTO assessment_activity_log (user_id, assessment_id, action, details)
            VALUES (?, ?, 'UNDO', ?)
            """,
            (user_id, rec_id, details)
        )

        conn.commit()
        conn.close()

        EventBus.publish(AssessmentUndone())
        record_dict = {
            "id": rec_id,
            "date": date,
            "transport": transport,
            "distance": distance,
            "electricity": electricity,
            "diet": diet,
            "flights": flights,
            "footprint": footprint,
            "eco_score": eco_score,
        }
        return True, f"Successfully undone assessment #{rec_id}.", record_dict
    except sqlite3.Error as e:
        logger.error("Undo assessment error: %s", e)
        return False, f"Database error during undo: {e}", None


def restore_last_deleted_assessment(user_id: int = 1) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Restore the user's most recently undone assessment.
    Re-inserts record into assessments table and logs action.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Find latest deleted assessment
        cursor.execute(
            """
            SELECT id, original_id, date, transport, distance, electricity, diet, flights, footprint, eco_score
            FROM deleted_assessments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No deleted assessment available to restore.", None

        del_id, orig_id, date, transport, distance, electricity, diet, flights, footprint, eco_score = row

        # Re-insert into assessments
        cursor.execute(
            """
            INSERT INTO assessments (user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, date, transport, distance, electricity, diet, flights, footprint, eco_score)
        )
        new_id = cursor.lastrowid

        # Delete from deleted_assessments
        cursor.execute("DELETE FROM deleted_assessments WHERE id = ?", (del_id,))

        # Log activity
        details = f"Restored assessment (formerly #{orig_id}, now #{new_id})"
        cursor.execute(
            """
            INSERT INTO assessment_activity_log (user_id, assessment_id, action, details)
            VALUES (?, ?, 'RESTORE', ?)
            """,
            (user_id, new_id, details)
        )

        conn.commit()
        conn.close()

        EventBus.publish(AssessmentSaved())
        return True, f"Successfully restored assessment #{new_id}.", {"id": new_id, "footprint": footprint}
    except sqlite3.Error as e:
        logger.error("Restore assessment error: %s", e)
        return False, f"Database error during restore: {e}", None


def get_last_undone_assessment(user_id: int = 1) -> dict[str, Any] | None:
    """Fetch the latest undone assessment for restore preview."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT original_id, date, transport, distance, electricity, diet, flights, footprint, eco_score, deleted_at
            FROM deleted_assessments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "original_id": row[0],
                "date": row[1],
                "transport": row[2],
                "distance": row[3],
                "electricity": row[4],
                "diet": row[5],
                "flights": row[6],
                "footprint": row[7],
                "eco_score": row[8],
                "deleted_at": row[9],
            }
        return None
    except sqlite3.Error:
        return None


def get_assessment_activity_history(user_id: int = 1) -> list[dict[str, Any]]:
    """Retrieve chronological activity log for assessment creations, undos, and restores."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, assessment_id, action, details, timestamp
            FROM assessment_activity_log
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "assessment_id": r[1],
                "action": r[2],
                "details": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]
    except sqlite3.Error:
        return []


def save_assessment_draft(
    user_id: int,
    transport: str,
    distance: float,
    electricity: float,
    diet: str,
    flights: int,
    region: str,
) -> bool:
    """Insert or update one unfinished assessment per user."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO assessment_drafts (
                user_id,
                transport,
                distance,
                electricity,
                diet,
                flights,
                region,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                transport = excluded.transport,
                distance = excluded.distance,
                electricity = excluded.electricity,
                diet = excluded.diet,
                flights = excluded.flights,
                region = excluded.region,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                transport,
                distance,
                electricity,
                diet,
                flights,
                region,
            ),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Database draft save error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def get_diet_history(user_id: int, limit: int = 7) -> list[tuple[Any, ...]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, diet FROM assessments
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT 100 LIMIT ?
        """, (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except sqlite3.Error as e:
        print(f"get_diet_history error: {e}")
        return []


def get_assessment_draft(user_id: int) -> dict[str, Any] | None:
    """Return the active user's unfinished assessment, if one exists."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                transport,
                distance,
                created_at,
                electricity,
                diet,
                flights,
                region,
                updated_at
            FROM assessment_drafts
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "transport": row[0],
            "distance": row[1],
            "electricity": row[3],
            "diet": row[4],
            "flights": row[5],
            "region": row[6],
            "updated_at": row[7],
        }
    except sqlite3.Error as exc:
        logger.error("Database draft read error: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


def delete_assessment_draft(user_id: int) -> bool:
    """Delete the active user's unfinished assessment."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM assessment_drafts WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Database draft delete error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def init_energy_db() -> bool:
    """
    Initialize energy-related tables (appliances, solar_configs).
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appliances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                name TEXT,
                category TEXT,
                quantity INTEGER,
                power_rating_watts REAL,
                hours_used_per_day REAL,
                standby_draw_watts REAL,
                usage_schedule TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solar_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER DEFAULT 1,
                roof_space_m2 REAL,
                peak_sun_hours REAL,
                utility_rate_per_kwh REAL,
                panel_efficiency REAL,
                installation_cost_per_kw REAL,
                maintenance_cost_per_year REAL,
                annual_rate_increase REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database energy init error: {e}")
        return False


def add_appliance(user_id: int, name: str, category: str, quantity: int, power_rating: float, hours_used: float, standby_draw: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appliances (user_id, name, category, quantity, power_rating_watts, hours_used_per_day, standby_draw_watts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, name, category, quantity, power_rating, hours_used, standby_draw))
        conn.commit()
        conn.close()
        EventBus.publish(ApplianceChanged())
        return True
    except sqlite3.Error as e:
        print(f"Appliance save error: {e}")
        return False


def delete_appliance(app_id: int) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM appliances WHERE id = ?", (app_id,))
        conn.commit()
        conn.close()
        EventBus.publish(ApplianceChanged())
        return True
    except sqlite3.Error as e:
        return False


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_appliances(user_id: int = 1) -> list[dict[str, Any]]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appliances WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []


def save_solar_config(user_id: int, roof_space: float, peak_sun_hours: float, utility_rate: float, panel_efficiency: float, install_cost: float, maint_cost: float, rate_inc: float) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM solar_configs WHERE user_id = ?", (user_id,))
        
        cursor.execute("""
            INSERT INTO solar_configs (
                user_id, roof_space_m2, peak_sun_hours, utility_rate_per_kwh, panel_efficiency, 
                installation_cost_per_kw, maintenance_cost_per_year, annual_rate_increase
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, roof_space, peak_sun_hours, utility_rate, panel_efficiency, install_cost, maint_cost, rate_inc))
        conn.commit()
        conn.close()
        EventBus.publish(SolarConfigSaved())
        return True
    except sqlite3.Error as e:
        return False


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_solar_config(user_id: int = 1) -> dict[str, Any] | None:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM solar_configs WHERE user_id = ? LIMIT 1", (user_id,))
        columns = [column[0] for column in cursor.description]
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(zip(columns, row))
        return None
    except sqlite3.Error as e:
        return None


def init_gamification_db() -> bool:
    """
    Initialize gamification-related tables.
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                challenge_id TEXT NOT NULL,
                progress_value REAL DEFAULT 0.0,
                status TEXT DEFAULT 'enrolled',
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                xp_awarded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unlocked_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                badge_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                xp_awarded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS xp_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                xp_amount INTEGER NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, source_type, source_id)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_xp_user ON xp_transactions(user_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                card_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, card_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skill_tree_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                node_id TEXT NOT NULL,
                status TEXT DEFAULT 'Locked',
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, node_id)
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Database gamification init error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def enroll_challenge(user_id: int, challenge_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM user_challenges WHERE user_id=? AND challenge_id=? AND status != 'expired'", (user_id, challenge_id))
        if cursor.fetchone():
            return False
            
        cursor.execute("""
            INSERT INTO user_challenges (user_id, challenge_id, status)
            VALUES (?, ?, 'enrolled')
        """, (user_id, challenge_id))
        conn.commit()
        EventBus.publish(ChallengeEnrolled())
        return True
    except sqlite3.Error as e:
        print(f"enroll_challenge error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def update_challenge_progress(user_id: int, challenge_id: str, progress_increment: float | None = None, set_progress: float | None = None) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        if progress_increment is not None:
            cursor.execute("""
                UPDATE user_challenges 
                SET progress_value = progress_value + ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND challenge_id = ? AND status = 'enrolled'
            """, (progress_increment, user_id, challenge_id))
        elif set_progress is not None:
             cursor.execute("""
                UPDATE user_challenges 
                SET progress_value = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND challenge_id = ? AND status = 'enrolled'
            """, (set_progress, user_id, challenge_id))
            
        conn.commit()
        EventBus.publish(ChallengeEnrolled())
        return True
    except sqlite3.Error as e:
        print(f"update_challenge_progress error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def complete_challenge(user_id: int, challenge_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE user_challenges 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND challenge_id = ? AND status = 'enrolled'
        """, (user_id, challenge_id))
        
        conn.commit()
        EventBus.publish(ChallengeEnrolled())
        return True
    except sqlite3.Error as e:
        print(f"complete_challenge error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_user_challenges(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_challenges WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


def award_xp(user_id: int, source_type: str, source_id: str, xp_amount: int, description: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO xp_transactions (user_id, source_type, source_id, xp_amount, description)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, source_type, source_id, xp_amount, description))
        
        if source_type == 'challenge':
            cursor.execute("UPDATE user_challenges SET xp_awarded = 1 WHERE user_id = ? AND challenge_id = ?", (user_id, source_id))
            EventBus.publish(ChallengeEnrolled())
        elif source_type == 'badge':
            cursor.execute("UPDATE unlocked_badges SET xp_awarded = 1 WHERE user_id = ? AND badge_id = ?", (user_id, source_id))
            EventBus.publish(BadgeUnlocked())
            
        conn.commit()
        EventBus.publish(XPAwarded())
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"award_xp error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_xp(user_id: int) -> int:
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(xp_amount) FROM xp_transactions WHERE user_id = ?", (user_id,))
        total = cursor.fetchone()[0]
        return total if total else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


def unlock_badge_in_db(user_id: int, badge_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO unlocked_badges (user_id, badge_id)
            VALUES (?, ?)
        """, (user_id, badge_id))
        
        conn.commit()
        EventBus.publish(BadgeUnlocked())
        EventBus.publish(XPAwarded())
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"unlock_badge_in_db error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_unlocked_badges(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM unlocked_badges WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


def unlock_card_in_db(user_id: int, card_id: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO user_cards (user_id, card_id)
            VALUES (?, ?)
        """, (user_id, card_id))

        conn.commit()
        get_unlocked_cards.clear()
        return True
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error as e:
        print(f"unlock_card_in_db error: {e}")
        return False
    finally:
        if conn:
            conn.close()


@st.cache_data
def get_unlocked_cards(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_cards WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_skill_tree_progress(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skill_tree_progress WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        return []
    finally:
        if conn:
            conn.close()


def update_skill_node_status(user_id: int, node_id: str, status: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM skill_tree_progress WHERE user_id=? AND node_id=?", (user_id, node_id))
        if cursor.fetchone():
            if status == 'Completed':
                cursor.execute("""
                    UPDATE skill_tree_progress 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND node_id = ?
                """, (status, user_id, node_id))
            else:
                cursor.execute("""
                    UPDATE skill_tree_progress 
                    SET status = ?
                    WHERE user_id = ? AND node_id = ?
                """, (status, user_id, node_id))
        else:
            if status == 'Completed':
                cursor.execute("""
                    INSERT INTO skill_tree_progress (user_id, node_id, status, completed_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, node_id, status))
            else:
                cursor.execute("""
                    INSERT INTO skill_tree_progress (user_id, node_id, status)
                    VALUES (?, ?, ?)
                """, (user_id, node_id, status))
                
        conn.commit()
        EventBus.publish(SkillTreeUpdated())
        return True
    except sqlite3.Error as e:
        print(f"update_skill_node_status error: {e}")
        return False
    finally:
        if conn:
            conn.close()


def init_marketplace_db() -> bool:
    """
    Initialize marketplace-related tables (journey_profiles, offset_transactions).
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS journey_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                distance_km REAL NOT NULL,
                transport_mode TEXT NOT NULL,
                passenger_count INTEGER DEFAULT 1,
                trips_per_week INTEGER DEFAULT 1,
                is_commute BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS offset_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                project_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                offset_tonnes REAL NOT NULL,
                cost_per_tonne REAL NOT NULL,
                total_cost REAL NOT NULL,
                transaction_status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        return True
    except Exception as e:
        print(f'Database marketplace init error: {e}')
        return False
    finally:
        if conn:
            conn.close()


def save_journey_profile(user_id: int, name: str, distance_km: float, transport_mode: str, passenger_count: int, trips_per_week: int, is_commute: bool) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO journey_profiles (user_id, name, distance_km, transport_mode, passenger_count, trips_per_week, is_commute)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, distance_km, transport_mode, passenger_count, trips_per_week, is_commute))
        
        conn.commit()
        EventBus.publish(JourneySaved())
        return True
    except Exception as e:
        print(f'save_journey_profile error: {e}')
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_journey_profiles(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM journey_profiles WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def delete_journey_profile(profile_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM journey_profiles WHERE id = ?', (profile_id,))
        conn.commit()
        EventBus.publish(JourneySaved())
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def save_offset_transaction(user_id: int, project_id: str, project_name: str, offset_tonnes: float, cost_per_tonne: float, total_cost: float, transaction_status: str = 'completed') -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO offset_transactions (user_id, project_id, project_name, offset_tonnes, cost_per_tonne, total_cost, transaction_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, project_id, project_name, offset_tonnes, cost_per_tonne, total_cost, transaction_status))
        
        conn.commit()
        EventBus.publish(OffsetSaved())
        return True
    except Exception as e:
        print(f'save_offset_transaction error: {e}')
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_offset_transactions(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM offset_transactions WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def delete_offset_transaction(transaction_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM offset_transactions WHERE id = ?', (transaction_id,))
        conn.commit()
        EventBus.publish(OffsetSaved())
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def clear_offset_transactions(user_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM offset_transactions WHERE user_id = ?', (user_id,))
        conn.commit()
        EventBus.publish(OffsetSaved())
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_offsets(user_id: int) -> float:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(offset_tonnes) FROM offset_transactions WHERE user_id = ? AND transaction_status != "reversed"', (user_id,))
        total = cursor.fetchone()[0]
        return total if total else 0.0
    except Exception:
        return 0.0
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_spend(user_id: int) -> float:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(total_cost) FROM offset_transactions WHERE user_id = ? AND transaction_status != "reversed"', (user_id,))
        total = cursor.fetchone()[0]
        return total if total else 0.0
    except Exception:
        return 0.0
    finally:
        if conn:
            conn.close()


def init_water_db() -> bool:
    """
    Initialize water consumption table.
    
    Returns:
        bool: True if initialization succeeded, False otherwise
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        
        # Run migrations to ensure schema is up to date
        migrate()
        
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS water_consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                shower_mins_per_day REAL,
                laundry_loads_per_week REAL,
                dishwasher_runs_per_week REAL,
                garden_mins_per_week REAL,
                diet TEXT,
                total_liters REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        return True
    except Exception as e:
        print(f'Database water init error: {e}')
        return False
    finally:
        if conn:
            conn.close()


def save_water_assessment(user_id: int, shower: float, laundry: float, dishwasher: float, garden: float, diet: str, total_liters: float) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO water_consumption (user_id, shower_mins_per_day, laundry_loads_per_week, dishwasher_runs_per_week, garden_mins_per_week, diet, total_liters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, shower, laundry, dishwasher, garden, diet, total_liters))
        
        conn.commit()
        EventBus.publish(WaterAssessmentSaved())
        return True
    except Exception as e:
        print(f'save_water_assessment error: {e}')
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_water_assessments(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM water_consumption WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()
            conn.close()


def save_dashboard_widget_preferences(user_id: int, widget_ids: list[str]) -> bool:
    """Persist the ordered dashboard widget IDs selected by a user."""
    import json

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_widget_preferences (
                user_id INTEGER PRIMARY KEY,
                widgets_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO dashboard_widget_preferences (user_id, widgets_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                widgets_json = excluded.widgets_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, json.dumps(list(widget_ids))),
        )
        conn.commit()
        return True
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.error("Dashboard preference save error: %s", exc)
        return False
    finally:
        if 'conn' in locals():
            conn.close()


def get_dashboard_widget_preferences(user_id: int) -> list[str] | None:
    """Return the saved widget IDs, or None when the user has no preference."""
    import json

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_widget_preferences (
                user_id INTEGER PRIMARY KEY,
                widgets_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute(
            "SELECT widgets_json FROM dashboard_widget_preferences WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        value = json.loads(row[0])
        return value if isinstance(value, list) else None
    except (sqlite3.Error, json.JSONDecodeError, TypeError) as exc:
        logger.error("Dashboard preference read error: %s", exc)
        return None
    finally:
        if 'conn' in locals():
            conn.close()


def record_environmental_milestone(
    user_id: int,
    milestone_type: str,
    title: str,
    description: str,
    icon: str = "🌱",
    achieved_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Persist a milestone once per user and milestone type.

    Returns True only when a new milestone is inserted.
    """
    import json

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO environmental_milestones (
                user_id,
                milestone_type,
                title,
                description,
                icon,
                achieved_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)
            """,
            (
                user_id,
                milestone_type,
                title,
                description,
                icon,
                achieved_at,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        conn.commit()
        return cursor.rowcount == 1
    except sqlite3.Error as exc:
        logger.error("Unable to record environmental milestone: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def get_environmental_milestones(user_id: int) -> list[dict[str, Any]]:
    """Return a user's milestones from newest to oldest."""
    import json

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                milestone_type,
                title,
                description,
                icon,
                achieved_at,
                metadata_json
            FROM environmental_milestones
            WHERE user_id = ?
            ORDER BY datetime(achieved_at) DESC, id DESC
            """,
            (user_id,),
        )
        milestones = []
        for row in cursor.fetchall():
            try:
                metadata = json.loads(row[6] or "{}")
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            milestones.append(
                {
                    "id": row[0],
                    "milestone_type": row[1],
                    "title": row[2],
                    "description": row[3],
                    "icon": row[4],
                    "achieved_at": row[5],
                    "metadata": metadata,
                }
            )
        return milestones
    except sqlite3.Error as exc:
        logger.error("Unable to load environmental milestones: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


def init_freeze_tokens_db() -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        migrate()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS freeze_token_balances (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER NOT NULL DEFAULT 0,
                total_used INTEGER NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS freeze_token_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS streak_freezes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                frozen_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, frozen_date)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_streak_freezes_user_date
            ON streak_freezes(user_id, frozen_date DESC)
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Freeze tokens DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_freeze_token_balance(user_id: int) -> int:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM freeze_token_balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


def ensure_freeze_token_row(user_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO freeze_token_balances (user_id, balance, total_earned, total_used)
            VALUES (?, 0, 0, 0)
        """, (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        if conn:
            conn.close()


def award_freeze_tokens(user_id: int, amount: int, reason: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        ensure_freeze_token_row(user_id)
        cursor.execute("""
            UPDATE freeze_token_balances
            SET balance = balance + ?, total_earned = total_earned + ?
            WHERE user_id = ?
        """, (amount, amount, user_id))
        cursor.execute("""
            INSERT INTO freeze_token_transactions (user_id, amount, reason)
            VALUES (?, ?, ?)
        """, (user_id, amount, reason))
        conn.commit()
        EventBus.publish(FreezeTokenChanged())
        return True
    except sqlite3.Error as e:
        logger.error("award_freeze_tokens error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def redeem_freeze_token(user_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM freeze_token_balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row[0] < 1:
            return False
        cursor.execute("""
            UPDATE freeze_token_balances
            SET balance = balance - 1, total_used = total_used + 1
            WHERE user_id = ? AND balance >= 1
        """, (user_id,))
        cursor.execute("""
            INSERT INTO freeze_token_transactions (user_id, amount, reason)
            VALUES (?, ?, ?)
        """, (user_id, -1, 'redeem'))
        conn.commit()
        EventBus.publish(FreezeTokenChanged())
        return True
    except sqlite3.Error as e:
        logger.error("redeem_freeze_token error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def use_streak_freeze(user_id: int, frozen_date: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO streak_freezes (user_id, frozen_date)
            VALUES (?, ?)
        """, (user_id, frozen_date))
        conn.commit()
        EventBus.publish(FreezeTokenChanged())
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("use_streak_freeze error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_streak_freeze_dates(user_id: int) -> list[str]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT frozen_date FROM streak_freezes
            WHERE user_id = ?
            ORDER BY frozen_date DESC
        """, (user_id,))
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


def get_freeze_token_transactions(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, amount, reason, created_at
            FROM freeze_token_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
        """, (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_total_freeze_tokens_earned(user_id: int) -> int:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT total_earned FROM freeze_token_balances WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Reduction goals
# ---------------------------------------------------------------------------

def init_goals_db() -> bool:
    """
    Create the reduction_goals table.

    Kept as its own initializer to match the existing per-feature pattern
    (init_energy_db, init_gamification_db, init_marketplace_db, init_water_db).
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reduction_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                baseline_kg REAL NOT NULL,
                target_kg REAL NOT NULL,
                start_date TEXT NOT NULL,
                target_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # A user may only have one active goal at a time; history rows are
        # archived or completed and are excluded from the index.
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reduction_goals_active
            ON reduction_goals(user_id)
            WHERE status = 'active'
        """)
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Reduction goals init error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def _goal_row_to_dict(row: Any) -> dict[str, Any] | None:
    """Map a reduction_goals row onto the dict shape src.utils.goals.py expects."""
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "baseline_kg": row[2],
        "target_kg": row[3],
        "start_date": row[4],
        "target_date": row[5],
        "status": row[6],
        "created_at": row[7],
    }


def save_reduction_goal(user_id: int, baseline_kg: float, target_kg: float, start_date: str, target_date: str) -> int | None:
    """
    Persist a new goal, archiving any goal the user already had active.

    Returns the new goal id, or None if the write failed.
    """
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Only one active goal per user, so retire the previous one first.
        cursor.execute(
            "UPDATE reduction_goals SET status = 'archived' "
            "WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )
        cursor.execute("""
            INSERT INTO reduction_goals (
                user_id, baseline_kg, target_kg, start_date, target_date, status
            )
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (
            user_id,
            float(baseline_kg),
            float(target_kg),
            str(start_date),
            str(target_date),
        ))
        goal_id = cursor.lastrowid
        conn.commit()
        EventBus.publish(ReductionGoalChanged())
        return goal_id
    except sqlite3.Error as exc:
        logger.error("Unable to save reduction goal: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_active_goal(user_id: int) -> dict[str, Any] | None:
    """Return the user's current active goal, or None."""
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, baseline_kg, target_kg, start_date,
                   target_date, status, created_at
            FROM reduction_goals
            WHERE user_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,))
        return _goal_row_to_dict(cursor.fetchone())
    except sqlite3.Error as exc:
        logger.error("Unable to load active goal: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_goal_history(user_id: int) -> list[dict[str, Any]]:
    """Return every goal the user has ever set, newest first."""
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, baseline_kg, target_kg, start_date,
                   target_date, status, created_at
            FROM reduction_goals
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user_id,))
        return [_goal_row_to_dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.error("Unable to load goal history: %s", exc)
        return []
    finally:
        if conn:
            conn.close()


def update_goal_status(goal_id: int, status: str) -> bool:
    """Move a goal to a new lifecycle state (archived / completed / active)."""
    if status not in ("active", "archived", "completed"):
        logger.error("Refusing to set unknown goal status: %s", status)
        return False

    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reduction_goals SET status = ? WHERE id = ?",
            (status, goal_id),
        )
        changed = cursor.rowcount > 0
        conn.commit()
        EventBus.publish(ReductionGoalChanged())
        return changed
    except sqlite3.Error as exc:
        logger.error("Unable to update goal status: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def archive_goal(goal_id: int) -> bool:
    """Retire a goal without marking it as met."""
    return update_goal_status(goal_id, "archived")


def complete_goal(goal_id: int) -> bool:
    """Mark a goal as successfully achieved."""
    return update_goal_status(goal_id, "completed")


def delete_reduction_goal(goal_id: int) -> bool:
    """Permanently remove a goal row."""
    init_goals_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reduction_goals WHERE id = ?", (goal_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        EventBus.publish(ReductionGoalChanged())
        return deleted
    except sqlite3.Error as exc:
        logger.error("Unable to delete reduction goal: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def init_waste_db() -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS waste_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                food_scraps REAL DEFAULT 0,
                plastic_packaging REAL DEFAULT 0,
                paper_cardboard REAL DEFAULT 0,
                glass REAL DEFAULT 0,
                metal_cans REAL DEFAULT 0,
                e_waste REAL DEFAULT 0,
                textiles REAL DEFAULT 0,
                mixed_waste REAL DEFAULT 0,
                total_weekly_kg REAL DEFAULT 0,
                annual_co2 REAL DEFAULT 0,
                recyclable_pct REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Waste DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def save_waste_assessment(user_id: int, waste_data: dict[str, float], total_weekly_kg: float, annual_co2: float, recyclable_pct: float) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO waste_assessments (
                user_id, food_scraps, plastic_packaging, paper_cardboard,
                glass, metal_cans, e_waste, textiles, mixed_waste,
                total_weekly_kg, annual_co2, recyclable_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            waste_data.get("Food Scraps", 0),
            waste_data.get("Plastic Packaging", 0),
            waste_data.get("Paper & Cardboard", 0),
            waste_data.get("Glass", 0),
            waste_data.get("Metal (Cans)", 0),
            waste_data.get("Electronics (E-Waste)", 0),
            waste_data.get("Textiles", 0),
            waste_data.get("Other (Mixed Waste)", 0),
            total_weekly_kg, annual_co2, recyclable_pct,
        ))
        conn.commit()
        get_waste_assessments.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Waste assessment save error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_waste_assessments(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM waste_assessments WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error as e:
        logger.error("Waste assessment read error: %s", e)
        return []
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Unit and currency preferences
# ---------------------------------------------------------------------------

def init_unit_preferences() -> bool:
    """
    Add the unit_system and currency columns to the users table.

    Uses the same defensive ALTER-and-swallow pattern already used for
    anonymous_leaderboard in init_db(), so it is safe to call repeatedly and on
    a database that already has the columns.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        for statement in (
            "ALTER TABLE users ADD COLUMN unit_system TEXT DEFAULT 'metric'",
            "ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'USD'",
        ):
            try:
                cursor.execute(statement)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Unit preference init error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def save_unit_preference(user_id: int, unit_system: str, currency: str) -> bool:
    """
    Persist a user's display preference.

    The value is normalised through src.utils.units.make_preference() first, so an
    unknown system or currency is stored as the default rather than as
    something no page can render.
    """
    from src.utils.units import make_preference

    preference = make_preference(unit_system, currency)
    init_unit_preferences()

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET unit_system = ?, currency = ? WHERE id = ?",
            (preference["system"], preference["currency"], user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as exc:
        logger.error("Unable to save unit preference: %s", exc)
        return False
    finally:
        if conn:
            conn.close()


def get_unit_preference(user_id: int) -> dict[str, Any]:
    """
    Return a user's display preference, defaulting to metric + USD.

    Never raises and never returns None: every page reads this on load, so a
    missing user, a missing column or a corrupted value must all degrade to the
    default rather than break the page.
    """
    from src.utils.units import make_preference

    init_unit_preferences()

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT unit_system, currency FROM users WHERE id = ?", (user_id,)
        )
        row = cursor.fetchone()
        if not row:
            return make_preference()
        return make_preference(row[0], row[1])
    except sqlite3.Error as exc:
        logger.error("Unable to read unit preference: %s", exc)
        return make_preference()
    finally:
        if conn:
            conn.close()


# ---------------------------------------------------------------------------
# Community Polls
# ---------------------------------------------------------------------------

def init_community_polls_db() -> bool:
    """Initialize database tables for community polls."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS community_polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                status TEXT DEFAULT 'active',
                created_by TEXT DEFAULT 'Community',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                vote_count INTEGER DEFAULT 0,
                FOREIGN KEY (poll_id) REFERENCES community_polls (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                user_identifier TEXT NOT NULL,
                option_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(poll_id, user_identifier),
                FOREIGN KEY (poll_id) REFERENCES community_polls (id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES poll_options (id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error("Community polls DB init error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def seed_community_polls() -> None:
    """Seed sample sustainability community polls if table is empty."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM community_polls")
        if cursor.fetchone()[0] > 0:
            return

        sample_polls = [
            (
                "What is your primary action for reducing personal carbon footprint in 2026?",
                "Lifestyle",
                "active",
                "EcoBuddy Team",
                [
                    ("Switching to plant-based diet", 45),
                    ("Using public transport & biking", 38),
                    ("Installing solar panels / renewable energy", 29),
                    ("Reducing single-use plastic & waste", 52),
                ],
            ),
            (
                "Which sector needs the most aggressive climate policy enforcement?",
                "Policy",
                "active",
                "EcoBuddy Team",
                [
                    ("Energy & Electricity Generation", 60),
                    ("Industrial Manufacturing & Heavy Industry", 42),
                    ("Transportation & Logistics", 31),
                    ("Agriculture & Deforestation", 25),
                ],
            ),
            (
                "What was the most impactful eco-habit you adopted last year?",
                "Community",
                "archived",
                "Community",
                [
                    ("Composting organic waste", 85),
                    ("Eliminating fast fashion purchases", 64),
                    ("Switching to EV / E-bike", 40),
                    ("Smart home energy management", 53),
                ],
            ),
        ]

        for question, category, status, created_by, options in sample_polls:
            cursor.execute("""
                INSERT INTO community_polls (question, category, status, created_by)
                VALUES (?, ?, ?, ?)
            """, (question, category, status, created_by))
            poll_id = cursor.lastrowid
            for opt_text, count in options:
                cursor.execute("""
                    INSERT INTO poll_options (poll_id, option_text, vote_count)
                    VALUES (?, ?, ?)
                """, (poll_id, opt_text, count))

        conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to seed community polls: %s", e)
    finally:
        if conn:
            conn.close()


def create_poll(question: str, options: list[str], category: str = "General", created_by: str = "Community") -> int | None:
    """Create a new poll with given options."""
    if not question.strip() or len(options) < 2:
        return None
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO community_polls (question, category, status, created_by)
            VALUES (?, ?, 'active', ?)
        """, (question.strip(), category, created_by))
        poll_id = cursor.lastrowid
        for opt in options:
            if opt.strip():
                cursor.execute("""
                    INSERT INTO poll_options (poll_id, option_text, vote_count)
                    VALUES (?, ?, 0)
                """, (poll_id, opt.strip()))
        conn.commit()
        get_active_polls.clear()
        get_archived_polls.clear()
        return poll_id
    except sqlite3.Error as e:
        logger.error("Failed to create poll: %s", e)
        return None
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_active_polls() -> list[dict]:
    """Retrieve all active community polls with their options and vote counts."""
    seed_community_polls()
    return _fetch_polls_by_status("active")


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_archived_polls() -> list[dict]:
    """Retrieve all archived community polls with final results."""
    seed_community_polls()
    return _fetch_polls_by_status("archived")


def _fetch_polls_by_status(status: str) -> list[dict]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, question, category, status, created_by, created_at
            FROM community_polls
            WHERE status = ?
            ORDER BY created_at DESC
        """, (status,))
        poll_rows = cursor.fetchall()
        polls = []
        for p in poll_rows:
            poll_id = p[0]
            cursor.execute("""
                SELECT id, option_text, vote_count
                FROM poll_options
                WHERE poll_id = ?
                ORDER BY id ASC
            """, (poll_id,))
            option_rows = cursor.fetchall()
            options = [
                {"id": opt[0], "option_text": opt[1], "vote_count": opt[2]}
                for opt in option_rows
            ]
            total_votes = sum(opt["vote_count"] for opt in options)
            polls.append({
                "id": poll_id,
                "question": p[1],
                "category": p[2],
                "status": p[3],
                "created_by": p[4],
                "created_at": p[5],
                "options": options,
                "total_votes": total_votes,
            })
        return polls
    except sqlite3.Error as e:
        logger.error("Failed to fetch polls: %s", e)
        return []
    finally:
        if conn:
            conn.close()


def has_user_voted(poll_id: int, user_identifier: str) -> bool:
    """Check if a specific user/identifier has already voted on a poll."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM poll_votes WHERE poll_id = ? AND user_identifier = ?
        """, (poll_id, str(user_identifier)))
        return cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error("Error checking poll vote: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def vote_poll(poll_id: int, option_id: int, user_identifier: str) -> bool:
    """Record an anonymous vote for an option in a poll."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check if already voted
        cursor.execute("""
            SELECT 1 FROM poll_votes WHERE poll_id = ? AND user_identifier = ?
        """, (poll_id, str(user_identifier)))
        if cursor.fetchone():
            return False

        cursor.execute("""
            INSERT INTO poll_votes (poll_id, user_identifier, option_id)
            VALUES (?, ?, ?)
        """, (poll_id, str(user_identifier), option_id))

        cursor.execute("""
            UPDATE poll_options SET vote_count = vote_count + 1 WHERE id = ? AND poll_id = ?
        """, (option_id, poll_id))

        conn.commit()
        get_active_polls.clear()
        get_archived_polls.clear()
        return True
    except sqlite3.Error as e:
        logger.error("Failed to record vote: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def archive_poll(poll_id: int) -> bool:
    """Archive a poll by ID."""
    init_community_polls_db()
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE community_polls SET status = 'archived' WHERE id = ?", (poll_id,))
        changed = cursor.rowcount > 0
        conn.commit()
        get_active_polls.clear()
        get_archived_polls.clear()
        return changed
    except sqlite3.Error as e:
        logger.error("Failed to archive poll: %s", e)
        return False
    finally:
        if conn:
            conn.close()

def create_time_capsule(user_id: int, title: str, promise_text: str, category: str, unlock_date: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO time_capsules (user_id, title, promise_text, category, unlock_date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, title, promise_text, category, unlock_date))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return True
    except sqlite3.Error as e:
        logger.error("create_time_capsule error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


@cached(category=CACHE_CATEGORY_DB_READS, ttl=TTL_DB_READ)
def get_time_capsules(user_id: int) -> list[dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, title, promise_text, category,
                   unlock_date, is_unlocked, unlocked_at, progress_notes,
                   created_at, updated_at
            FROM time_capsules
            WHERE user_id = ?
            ORDER BY unlock_date ASC, created_at DESC
        """, (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


def update_time_capsule_unlock(capsule_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE time_capsules
            SET is_unlocked = 1, unlocked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_unlocked = 0
        """, (capsule_id,))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("update_time_capsule_unlock error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def update_time_capsule_progress(capsule_id: int, progress_notes: str) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE time_capsules
            SET progress_notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (progress_notes, capsule_id))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return True
    except sqlite3.Error as e:
        logger.error("update_time_capsule_progress error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def delete_time_capsule(capsule_id: int) -> bool:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM time_capsules WHERE id = ?", (capsule_id,))
        conn.commit()
        EventBus.publish(TimeCapsuleChanged())
        return True
    except sqlite3.Error as e:
        logger.error("delete_time_capsule error: %s", e)
        return False
    finally:
        if conn:
            conn.close()
def save_weekly_challenge(user_id: int, title: str, difficulty: str, xp: int, category: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO weekly_challenges
        (user_id,title,difficulty,xp,category)
        VALUES(?,?,?,?,?)
    """,(user_id,title,difficulty,xp,category))

    conn.commit()
    conn.close()

    return True
def get_weekly_challenges(user_id: int) -> list[tuple[Any, ...]]:

    conn=sqlite3.connect(DB_NAME)
    cursor=conn.cursor()

    cursor.execute("""
    SELECT *
    FROM weekly_challenges
    WHERE user_id=?
    ORDER BY created_at DESC
    """,(user_id,))

    data=cursor.fetchall()

    conn.close()

    return data
def complete_weekly_challenge(challenge_id: int) -> bool:

    conn=sqlite3.connect(DB_NAME)
    cursor=conn.cursor()

    cursor.execute("""
    UPDATE weekly_challenges
    SET status='Completed'
    WHERE id=?
    """,(challenge_id,))

    conn.commit()

    conn.close()



from datetime import datetime, timedelta

def weekly_challenges_exist(user_id: int) -> bool:

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    last_week = datetime.now() - timedelta(days=7)

    cursor.execute("""
        SELECT COUNT(*)
        FROM weekly_challenges
        WHERE user_id = ?
        AND created_at >= ?
    """, (user_id, last_week))

    count = cursor.fetchone()[0]

    conn.close()

    return count > 0


def get_completed_challenges(user_id: int) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title,difficulty,created_at
        FROM weekly_challenges
        WHERE user_id=?
        AND status='Completed'
        ORDER BY created_at DESC
    """,(user_id,))

    data = cursor.fetchall()

    conn.close()

    return data


# ============================================================================
# OPTIMIZED DATABASE QUERIES - Issue #778
_db_optimizer = None


def get_db_optimizer() -> Any:
    """Get the database optimizer instance."""
    global _db_optimizer
    if _db_optimizer is None:
        try:
            from src.lib.db_optimizer import get_query_optimizer
            _db_optimizer = get_query_optimizer()
        except Exception:
            _db_optimizer = None
    return _db_optimizer

def save_food_scan(user_id: int, meal_name: str, food_items: dict, total_co2: float) -> bool:
    import json
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO food_scans (user_id, meal_name, items, total_co2_kg) VALUES (?, ?, ?, ?)",
            (user_id, meal_name, json.dumps(food_items), total_co2)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error saving food scan: {e}")
        return False

def get_food_scans(user_id: int) -> list[dict]:
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM food_scans WHERE user_id = ?", (user_id,))
        columns = [column[0] for column in cursor.description]
        data = cursor.fetchall()
        return [dict(zip(columns, row)) for row in data]
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()
            conn.close()

def get_db_optimizer() -> Any:
    """Get the database optimizer instance."""
    global _db_optimizer
    if _db_optimizer is None:
        _db_optimizer = get_query_optimizer()
    return _db_optimizer

def save_food_scan(user_id: int, meal_name: str, food_items: dict, total_co2: float) -> bool:
    import json
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO food_scans (user_id, meal_name, items, total_co2_kg) VALUES (?, ?, ?, ?)",
            (user_id, meal_name, json.dumps(food_items), total_co2)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error saving food scan: {e}")
        return False

def save_urban_health_profile(time_allocation: dict, weekly_park_visits: int, tree_canopy_pct: float, 
                              exposure_data: dict, mitigation_data: dict) -> None:
    """Saves an urban health impact analysis session to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO urban_health_profiles 
        (time_allocation, weekly_park_visits, tree_canopy_pct, exposure_data, mitigation_data)
        VALUES (?, ?, ?, ?, ?)
    """, (
        json.dumps(time_allocation),
        weekly_park_visits,
        tree_canopy_pct,
        json.dumps(exposure_data),
        json.dumps(mitigation_data)
    ))
    conn.commit()
    conn.close()

def get_food_scans(user_id: int) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT created_at, meal_name, total_co2_kg FROM food_scans WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"created_at": row[0], "meal_name": row[1], "total_co2_kg": row[2]} for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Error getting food scans: {e}")
        return []

def save_pcf_label(product_name: str, label_data: dict, transparency_data: dict) -> None:
    """Saves a generated PCF label and transparency score to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pcf_labels (product_name, label_data, transparency_data)
        VALUES (?, ?, ?)
    """, (product_name, json.dumps(label_data), json.dumps(transparency_data)))
    conn.commit()
    conn.close()

def init_energy_tracker_db() -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS energy_consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                electricity_kwh REAL,
                gas_kwh REAL,
                record_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Database energy tracker init error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()

def save_textile_comparison(garments: list, results: list) -> None:
    """Saves a textile comparison session to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO textile_comparisons (garment_data, results_data)
        VALUES (?, ?)
    """, (json.dumps(garments), json.dumps(results)))
    conn.commit()
    conn.close()

def add_energy_record(user_id: int, electricity_kwh: float, gas_kwh: float, record_date: str) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO energy_consumption (user_id, electricity_kwh, gas_kwh, record_date)
            VALUES (?, ?, ?, ?)
        ''', (user_id, electricity_kwh, gas_kwh, record_date))
        conn.commit()
        return True
    except sqlite3.Error as exc:
        logger.error("Database energy tracker insert error: %s", exc)
        return False
    finally:
        if conn:
            conn.close()

def add_pantry_item(item_name: str, purchase_date: str, storage_condition: str) -> None:
    """Adds a new item to the pantry inventory."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pantry_inventory (item_name, purchase_date, storage_condition)
        VALUES (?, ?, ?)
    """, (item_name, purchase_date, storage_condition))
    conn.commit()
    conn.close()

def get_pantry_inventory() -> list:
    """Retrieves all items in the pantry inventory."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, purchase_date, storage_condition FROM pantry_inventory ORDER BY purchase_date ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0], "purchase_date": row[1], "storage": row[2]} for row in rows]

def save_green_finance_profile(portfolio_value: float, deposit_amount: float, 
                               investment_results: dict, banking_results: dict) -> None:
    """Saves a green finance analysis profile to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO green_finance_profiles (portfolio_value, deposit_amount, investment_results, banking_results)
        VALUES (?, ?, ?, ?)
    """, (portfolio_value, deposit_amount, json.dumps(investment_results), json.dumps(banking_results)))
    conn.commit()
    conn.close()

def get_green_finance_history() -> list:
    """Retrieves historical green finance analysis profiles."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT portfolio_value, deposit_amount, investment_results, banking_results, timestamp FROM green_finance_profiles ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def remove_pantry_item(item_name: str) -> None:
    """Removes an item from the pantry inventory."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pantry_inventory WHERE item_name = ?", (item_name,))
    conn.commit()
    conn.close()

def get_energy_records(user_id: int) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, electricity_kwh, gas_kwh, record_date, created_at
            FROM energy_consumption
            WHERE user_id = ?
            ORDER BY record_date ASC
        ''', (user_id,))
        rows = cursor.fetchall()
        return [{"id": row[0], "electricity_kwh": row[1], "gas_kwh": row[2], "record_date": row[3], "created_at": row[4]} for row in rows]
    except sqlite3.Error as exc:
        logger.error("Database energy tracker select error: %s", exc)
        return []
    finally:
        if conn:
            conn.close()

def save_water_energy_profile(household_size: int, grid_intensity: float, comparison_data: dict) -> None:
    """Saves a water-energy nexus comparison profile to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO water_energy_profiles (household_size, grid_intensity, comparison_data)
        VALUES (?, ?, ?)
    """, (household_size, grid_intensity, json.dumps(comparison_data)))
    conn.commit()
    conn.close()

def get_water_energy_history() -> list:
    """Retrieves historical water-energy nexus profiles."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT household_size, grid_intensity, comparison_data, timestamp FROM water_energy_profiles ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def get_pca_balance(user_id: str) -> float:
    """Retrieves the PCA balance for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance_kg FROM pca_balances WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 500.0

def save_travel_itinerary(legs: list, report: dict) -> None:
    """Saves a travel itinerary and its optimization report to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO travel_itineraries (legs_data, optimization_report)
        VALUES (?, ?)
    """, (json.dumps(legs), json.dumps(report)))
    conn.commit()
    conn.close()

def get_travel_itinerary_history() -> list:
    """Retrieves historical travel itineraries."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT legs_data, optimization_report, timestamp FROM travel_itineraries ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]


import json

def save_urban_mining_inventory(device_list: list, result_data: dict) -> None:
    """Saves an urban mining inventory calculation to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO urban_mining_inventories (device_list, total_devices, carbon_avoided_kg, mining_score)
        VALUES (?, ?, ?, ?)
    """, (
        json.dumps(device_list),
        result_data.get("total_devices", 0),
        result_data.get("total_carbon_avoided_kg", 0.0),
        result_data.get("urban_mining_score", 0)
    ))
    conn.commit()
    conn.close()

def get_urban_mining_history() -> list:
    """Retrieves historical urban mining inventory calculations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT device_list, total_devices, carbon_avoided_kg, mining_score, timestamp FROM urban_mining_inventories ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]


def update_pca_balance(user_id: str, amount: float) -> None:
    """Updates the PCA balance for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pca_balances (user_id, balance_kg, last_updated)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET balance_kg = excluded.balance_kg, last_updated = CURRENT_TIMESTAMP
    """, (user_id, amount))
    conn.commit()
    conn.close()

def submit_neighborhood_score(zip_code: str, eco_score: float, carbon_saved_kg: float) -> None:
    """Submits an anonymous score to the neighborhood aggregation table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO neighborhood_scores (zip_code, eco_score, carbon_saved_kg)
        VALUES (?, ?, ?)
    """, (zip_code, eco_score, carbon_saved_kg))
    conn.commit()
    conn.close()

def get_neighborhood_leaderboard() -> list:
    """Retrieves aggregated leaderboard data from the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            zip_code,
            COUNT(*) as total_participants,
            ROUND(AVG(eco_score), 1) as average_eco_score,
            ROUND(SUM(carbon_saved_kg), 2) as total_carbon_saved_kg
        FROM neighborhood_scores
        GROUP BY zip_code
        ORDER BY average_eco_score DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def record_pca_trade(buyer_id: str, seller_id: str, amount_kg: float, price_per_tonne: float, trade_type: str) -> None:
    """Records a PCA trade in the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pca_trades (buyer_id, seller_id, amount_kg, price_per_tonne, trade_type)
        VALUES (?, ?, ?, ?, ?)
    """, (buyer_id, seller_id, amount_kg, price_per_tonne, trade_type))
    conn.commit()
    conn.close()


import json

def save_digital_twin_scenario(current_footprint: float, target_goal: float, report_data: dict) -> None:
    """Saves a digital twin forecasting scenario to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO digital_twin_forecasts (current_footprint, target_goal, scenarios_applied)
        VALUES (?, ?, ?)
    """, (current_footprint, target_goal, json.dumps(report_data.get("scenarios_applied", []))))
    conn.commit()
    conn.close()

def get_digital_twin_history() -> list:
    """Retrieves historical digital twin forecasts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_footprint, target_goal, scenarios_applied, timestamp FROM digital_twin_forecasts ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]


import json

def save_offset_portfolio(user_id: str, summary: dict, risk_profile: dict) -> None:
    """Saves a snapshot of the user's offset portfolio and risk profile."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO offset_portfolios (user_id, total_tonnes, total_cost, diversification_score, risk_rating)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        summary.get("total_tonnes", 0.0),
        summary.get("total_cost", 0.0),
        risk_profile.get("diversification_score", 0.0),
        risk_profile.get("overall_risk_rating", "Unknown")
    ))
    conn.commit()
    conn.close()

def get_offset_portfolio_history(user_id: str) -> list:
    """Retrieves the historical snapshots of a user's offset portfolio."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT total_tonnes, total_cost, diversification_score, risk_rating, timestamp 
        FROM offset_portfolios 
        WHERE user_id = ? 
        ORDER BY timestamp DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_avoided_emissions_log(activity_type: str, quantity: float, avoided_kg: float) -> None:
    """Saves a logged avoided emissions activity to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO avoided_emissions_logs (activity_type, quantity, avoided_kg)
        VALUES (?, ?, ?)
    """, (activity_type, quantity, avoided_kg))
    conn.commit()
    conn.close()

def get_avoided_emissions_history() -> list:
    """Retrieves historical avoided emissions logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activity_type, quantity, avoided_kg, timestamp FROM avoided_emissions_logs ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_challenge_result(scenario_id: str, outcome: str, final_carbon: float, final_cost: float) -> None:
    """Saves a scenario challenge result to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO challenge_results (scenario_id, outcome, final_carbon, final_cost)
        VALUES (?, ?, ?, ?)
    """, (scenario_id, outcome, final_carbon, final_cost))
    conn.commit()
    conn.close()

def get_challenge_history() -> list:
    """Retrieves historical scenario challenge results."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT scenario_id, outcome, final_carbon, final_cost, timestamp FROM challenge_results ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_equivalence_preferences(user_id: int, top_metrics: str, region: str) -> bool:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO equivalence_preferences (user_id, top_metrics, region, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                top_metrics=excluded.top_metrics,
                region=excluded.region,
                updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, top_metrics, region)
        )
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error saving equivalence preferences: {e}")
        return False


import json

def save_green_premium_analysis(product_key: str, utility_inflation: float, subsidy_usd: float, result_data: dict) -> None:
    """Saves a green premium ROI analysis to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO green_premium_analyses (product_key, utility_inflation, subsidy_usd, result_data)
        VALUES (?, ?, ?, ?)
    """, (product_key, utility_inflation, subsidy_usd, json.dumps(result_data)))
    conn.commit()
    conn.close()


def get_equivalence_preferences(user_id: int) -> dict | None:
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT top_metrics, region FROM equivalence_preferences WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {"top_metrics": row[0], "region": row[1]}
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error getting equivalence preferences: {e}")
        return None


import json

def save_relocation_analysis(current_city: str, target_city: str, result_data: dict) -> None:
    """Saves a relocation impact analysis to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO relocation_analyses (current_city, target_city, annual_delta_kg_co2e, result_data)
        VALUES (?, ?, ?, ?)
    """, (current_city, target_city, result_data.get("annual_delta_kg_co2e", 0.0), json.dumps(result_data)))
    conn.commit()
    conn.close()

def save_renovation_estimate(material_key: str, volume_m3: float, total_carbon_kg: float, low_carbon_score: float) -> None:
    """Saves a renovation embodied carbon estimate to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO renovation_estimates (material_key, volume_m3, total_carbon_kg, low_carbon_score)
        VALUES (?, ?, ?, ?)
    """, (material_key, volume_m3, total_carbon_kg, low_carbon_score))
    conn.commit()
    conn.close()

def get_renovation_history() -> list:
    """Retrieves historical renovation carbon estimates."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT material_key, volume_m3, total_carbon_kg, low_carbon_score, timestamp FROM renovation_estimates ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def get_relocation_history() -> list:
    """Retrieves historical relocation analyses."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT current_city, target_city, annual_delta_kg_co2e, timestamp 
        FROM relocation_analyses 
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]


def get_virtual_city_state(user_id: int) -> dict:
    """Retrieve the user's virtual city state."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT carbon_saved_kg, unlocked_assets, layout_state 
        FROM virtual_city_state 
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    import json
    if row:
        return {
            "user_id": user_id,
            "carbon_saved_kg": row[0],
            "unlocked_assets": json.loads(row[1]) if row[1] else [],
            "layout_state": json.loads(row[2]) if row[2] else {}
        }
    else:
        return {
            "user_id": user_id,
            "carbon_saved_kg": 0.0,
            "unlocked_assets": [],
            "layout_state": {}
        }

def save_virtual_city_state(user_id: int, carbon_saved_kg: float, unlocked_assets: list, layout_state: dict) -> None:
    """Saves or updates the user's virtual city state."""
    conn = get_connection()
    cursor = conn.cursor()
    import json
    
    cursor.execute("SELECT user_id FROM virtual_city_state WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    
    if exists:
        cursor.execute("""
            UPDATE virtual_city_state 
            SET carbon_saved_kg = ?, unlocked_assets = ?, layout_state = ?, last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (carbon_saved_kg, json.dumps(unlocked_assets), json.dumps(layout_state), user_id))
    else:
        cursor.execute("""
            INSERT INTO virtual_city_state (user_id, carbon_saved_kg, unlocked_assets, layout_state)
            VALUES (?, ?, ?, ?)
        """, (user_id, carbon_saved_kg, json.dumps(unlocked_assets), json.dumps(layout_state)))
    
    conn.commit()
    conn.close()

def log_civic_action(user_id: int, bill_id: str, action_type: str) -> bool:
    """Logs a civic action taken by a user."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO civic_actions (user_id, bill_id, action_type, created_at)
            VALUES (?, ?, ?, datetime('now'))
        ''', (user_id, bill_id, action_type))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error logging civic action: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def save_efficacy_checkin(user_id: str, anxiety_level: int, agency_level: int, action_taken: bool, efficacy_score: float) -> None:
    """Saves a daily eco-efficacy check-in to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO efficacy_checkins (user_id, anxiety_level, agency_level, action_taken, efficacy_score)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, anxiety_level, agency_level, action_taken, efficacy_score))
    conn.commit()
    conn.close()

def get_efficacy_history(user_id: str) -> list:
    """Retrieves historical eco-efficacy check-ins for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT anxiety_level, agency_level, action_taken, efficacy_score, timestamp 
        FROM efficacy_checkins 
        WHERE user_id = ? 
        ORDER BY timestamp ASC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def get_user_civic_actions(user_id: int) -> list:
    """Retrieves civic actions taken by a user."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, bill_id, action_type, created_at
            FROM civic_actions
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        rows = cursor.fetchall()
        return [{"id": r[0], "bill_id": r[1], "action_type": r[2], "created_at": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error retrieving civic actions: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

import json

def save_ej_impact_log(zip_code: str, activity: str, quantity: float, impact_data: dict) -> None:
    """Saves an EJ impact analysis log to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ej_impact_logs (zip_code, activity, quantity, impact_data)
        VALUES (?, ?, ?, ?)
    """, (zip_code, activity, quantity, json.dumps(impact_data)))
    conn.commit()
    conn.close()

def get_ej_history() -> list:
    """Retrieves historical EJ impact logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT zip_code, activity, quantity, impact_data, timestamp FROM ej_impact_logs ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def init_travel_tracker_db() -> bool:
    try:
        import sqlite3
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS travel_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    record_date TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    distance_km REAL NOT NULL,
                    passengers INTEGER NOT NULL,
                    emissions_kg REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error initializing travel_tracker_db: {e}")
        return False

import json

def save_net_zero_roadmap(scope1: float, scope2: float, scope3: float, target_year: int, roadmap_data: dict) -> None:
    """Saves a generated net-zero roadmap to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO net_zero_roadmaps (scope1, scope2, scope3, target_year, roadmap_data)
        VALUES (?, ?, ?, ?, ?)
    """, (scope1, scope2, scope3, target_year, json.dumps(roadmap_data)))
    conn.commit()
    conn.close()

def get_roadmap_history() -> list:
    """Retrieves historical net-zero roadmap generations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT scope1, scope2, scope3, target_year, roadmap_data, timestamp FROM net_zero_roadmaps ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_appliance_registration(user_id: str, appliance_type: str, age_years: int, annual_usage_kwh: float, result_data: dict) -> None:
    """Saves an appliance lifecycle analysis to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO appliance_registrations (user_id, appliance_type, age_years, annual_usage_kwh, circularity_score)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, appliance_type, age_years, annual_usage_kwh, result_data.get("circularity_score", 0.0)))
    conn.commit()
    conn.close()

def get_appliance_history(user_id: str) -> list:
    """Retrieves historical appliance registrations for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT appliance_type, age_years, annual_usage_kwh, circularity_score, timestamp 
        FROM appliance_registrations 
        WHERE user_id = ? 
        ORDER BY timestamp DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def add_travel_record(user_id: int, record_date: str, mode: str, distance_km: float, passengers: int, emissions_kg: float) -> bool:
    try:
        import sqlite3
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO travel_records (user_id, record_date, mode, distance_km, passengers, emissions_kg)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, record_date, mode, distance_km, passengers, emissions_kg))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding travel_record: {e}")
        return False


def save_grocery_optimization(budget_usd: float, categories: list, result_data: dict) -> None:
    """Saves a grocery optimization session to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO grocery_optimizations (budget_usd, categories, result_data)
        VALUES (?, ?, ?)
    """, (budget_usd, json.dumps(categories), json.dumps(result_data)))
    conn.commit()
    conn.close()

def get_grocery_history() -> list:
    """Retrieves historical grocery optimization sessions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT budget_usd, categories, result_data, timestamp FROM grocery_optimizations ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_skill_listing(user_id: str, skill_name: str, category: str, difficulty: str, karma_cost: int) -> None:
    """Saves a new skill listing to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO skill_listings (user_id, skill_name, category, difficulty, karma_cost)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, skill_name, category, difficulty, karma_cost))
    conn.commit()
    conn.close()

def execute_skill_swap_db(learner_id: str, teacher_id: str, skill_name: str, karma_transferred: int) -> None:
    """Records a completed skill swap in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO skill_swaps (learner_id, teacher_id, skill_name, karma_transferred)
        VALUES (?, ?, ?, ?)
    """, (learner_id, teacher_id, skill_name, karma_transferred))
    conn.commit()
    conn.close()

def get_travel_records(user_id: int) -> list:
    try:
        import sqlite3
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM travel_records WHERE user_id = ? ORDER BY record_date DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting travel_records: {e}")
        return []

def save_carbon_banking_action(user_id: str, action_type: str, amount: float, from_month: str, to_month: str) -> None:
    """Saves a carbon banking action (rollover or borrow) to the src.core.database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO carbon_banking_actions (user_id, action_type, amount, from_month, to_month)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, action_type, amount, from_month, to_month))
    conn.commit()
    conn.close()

def save_commute_log(user_id: str, log_date: str, distance_km: float, chosen_mode: str, baseline_mode: str, carbon_saved_kg: float) -> None:
    """Saves a daily commute log to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO commute_logs (user_id, log_date, distance_km, chosen_mode, baseline_mode, carbon_saved_kg)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, log_date, distance_km, chosen_mode, baseline_mode, carbon_saved_kg))
    conn.commit()
    conn.close()

def save_regeneration_log(garden_area_sqm: float, crop_count: int, regeneration_score: float) -> None:
    """Saves a backyard regeneration impact log to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO regeneration_logs (garden_area_sqm, crop_count, regeneration_score)
        VALUES (?, ?, ?)
    """, (garden_area_sqm, crop_count, regeneration_score))
    conn.commit()
    conn.close()

def get_regeneration_history() -> list:
    """Retrieves historical backyard regeneration logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT garden_area_sqm, crop_count, regeneration_score, timestamp FROM regeneration_logs ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_urban_cooling_plan(baseline_temp: float, hvac_cost: float, cooling_effect_c: float, twenty_year_net_savings: float) -> None:
    """Saves an urban cooling mitigation plan to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO urban_cooling_plans (baseline_temp, hvac_cost, cooling_effect_c, twenty_year_net_savings)
        VALUES (?, ?, ?, ?)
    """, (baseline_temp, hvac_cost, cooling_effect_c, twenty_year_net_savings))
    conn.commit()
    conn.close()

def get_urban_cooling_history() -> list:
    """Retrieves historical urban cooling mitigation plans."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT baseline_temp, hvac_cost, cooling_effect_c, twenty_year_net_savings, timestamp FROM urban_cooling_plans ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def get_commute_history(user_id: str) -> list:
    """Retrieves historical commute logs for a user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT log_date, distance_km, chosen_mode, baseline_mode, carbon_saved_kg, timestamp 
        FROM commute_logs 
        WHERE user_id = ? 
        ORDER BY log_date DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def get_carbon_banking_history(user_id: str) -> list:
    """Retrieves the carbon banking history for a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT action_type, amount, from_month, to_month, timestamp 
        FROM carbon_banking_actions 
        WHERE user_id = ? 
        ORDER BY timestamp DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_policy_simulation(footprint_tonnes: float, tax_rate: float, net_impact_usd: float) -> None:
    """Saves a carbon policy simulation result to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO policy_simulations (footprint_tonnes, tax_rate, net_impact_usd)
        VALUES (?, ?, ?)
    """, (footprint_tonnes, tax_rate, net_impact_usd))
    conn.commit()
    conn.close()

def get_policy_history() -> list:
    """Retrieves historical carbon policy simulations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT footprint_tonnes, tax_rate, net_impact_usd, timestamp FROM policy_simulations ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

import json

def save_load_shifting_plan(appliances: list, preference: str, carbon_saved_kg: float, money_saved_usd: float) -> None:
    """Saves a load shifting optimization plan to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO load_shifting_plans (appliances, preference, carbon_saved_kg, money_saved_usd)
        VALUES (?, ?, ?, ?)
    """, (json.dumps(appliances), preference, carbon_saved_kg, money_saved_usd))
    conn.commit()
    conn.close()

def get_load_shifting_history() -> list:
    """Retrieves historical load shifting plans."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT appliances, preference, carbon_saved_kg, money_saved_usd, timestamp FROM load_shifting_plans ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

import json

def get_assessments_for_anomaly_detection(user_id: str) -> list:
    """Retrieves historical assessment data formatted for anomaly detection."""
    conn = get_connection()
    cursor = conn.cursor()
    # Assuming a standard 'assessments' table exists with date and total_carbon columns
    cursor.execute("""
        SELECT strftime('%Y-%m', timestamp) as date, SUM(total_carbon) as carbon_kg
        FROM assessments
        WHERE user_id = ?
        GROUP BY strftime('%Y-%m', timestamp)
        ORDER BY date ASC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"date": row[0], "carbon_kg": row[1]} for row in rows if row[1] is not None]

def save_aviation_plan(distance_km: float, cabin_class: str, has_layover: bool, total_emissions_kg: float) -> None:
    """Saves an aviation flight plan analysis to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO aviation_plans (distance_km, cabin_class, has_layover, total_emissions_kg)
        VALUES (?, ?, ?, ?)
    """, (distance_km, cabin_class, has_layover, total_emissions_kg))
    conn.commit()
    conn.close()

def get_aviation_history() -> list:
    """Retrieves historical aviation plan analyses."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT distance_km, cabin_class, has_layover, total_emissions_kg, timestamp FROM aviation_plans ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_alert_resolution(user_id: str, alert_date: str, carbon_kg: float) -> None:
    """Logs the resolution of a carbon anomaly alert."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO anomaly_alerts (user_id, alert_date, carbon_kg, severity, resolved)
        VALUES (?, ?, ?, 'medium', 1)
    """, (user_id, alert_date, carbon_kg))
    conn.commit()
    conn.close()

def save_biodiversity_project(baseline_condition: str, total_area_sqm: float, bng_percentage: float, total_bu_gained: float) -> None:
    """Saves a biodiversity net gain project assessment to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO biodiversity_projects (baseline_condition, total_area_sqm, bng_percentage, total_bu_gained)
        VALUES (?, ?, ?, ?)
    """, (baseline_condition, total_area_sqm, bng_percentage, total_bu_gained))
    conn.commit()
    conn.close()

def get_biodiversity_history() -> list:
    """Retrieves historical biodiversity project assessments."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT baseline_condition, total_area_sqm, bng_percentage, total_bu_gained, timestamp FROM biodiversity_projects ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_event_plan(guest_count: int, catering_type: str, total_emissions_kg: float) -> None:
    """Saves an event footprint calculation to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO event_plans (guest_count, catering_type, total_emissions_kg)
        VALUES (?, ?, ?)
    """, (guest_count, catering_type, total_emissions_kg))
    conn.commit()
    conn.close()

def save_p2p_simulation(grid_price: float, p2p_price: float, total_volume_kwh: float, carbon_avoided_kg: float) -> None:
    """Saves a P2P energy simulation result to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO p2p_simulations (grid_price, p2p_price, total_volume_kwh, carbon_avoided_kg)
        VALUES (?, ?, ?, ?)
    """, (grid_price, p2p_price, total_volume_kwh, carbon_avoided_kg))
    conn.commit()
    conn.close()

def get_p2p_history() -> list:
    """Retrieves historical P2P energy simulations."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT grid_price, p2p_price, total_volume_kwh, carbon_avoided_kg, timestamp FROM p2p_simulations ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def get_event_history() -> list:
    """Retrieves historical event plans."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT guest_count, catering_type, total_emissions_kg, timestamp FROM event_plans ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

def save_virtual_water_log(product: str, quantity: float, region: str, scarcity_weighted_l: float) -> None:
    """Saves a virtual water footprint log to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO virtual_water_logs (product, quantity, region, scarcity_weighted_l)
        VALUES (?, ?, ?, ?)
    """, (product, quantity, region, scarcity_weighted_l))
    conn.commit()
    conn.close()

def get_virtual_water_history() -> list:
    """Retrieves historical virtual water logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT product, quantity, region, scarcity_weighted_l, timestamp FROM virtual_water_logs ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip([column[0] for column in cursor.description], row)) for row in rows]

