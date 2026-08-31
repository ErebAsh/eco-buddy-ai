"""
Decision Simulator History Manager.

Persists and retrieves scenarios for the What-If Engine.
"""

import sqlite3
import json
import logging
from typing import List, Optional
from datetime import datetime

from src.core.database import DB_NAME
from src.decision_engine.models import ScenarioInputs, TransportInputs, EnergyInputs, FoodInputs, WasteInputs, WaterInputs

def load_baseline_from_user(user_id: int) -> ScenarioInputs:
    """Attempts to build a baseline from the user's historical data.
    Falls back to defaults if insufficient data exists.
    """
    inputs = ScenarioInputs()
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Check if the user has an existing baseline saved
        cursor.execute('''
            SELECT inputs_json FROM decision_scenarios 
            WHERE user_id = ? AND is_baseline = 1 
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        row = cursor.fetchone()
        
        if row:
            data = json.loads(row[0])
            inputs.transport = TransportInputs(**data.get("transport", {}))
            inputs.energy = EnergyInputs(**data.get("energy", {}))
            inputs.food = FoodInputs(**data.get("food", {}))
            inputs.waste = WasteInputs(**data.get("waste", {}))
            inputs.water = WaterInputs(**data.get("water", {}))
            
    except Exception as e:
        logger.warning(f"Failed to load baseline for user {user_id}: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            
    return inputs

logger = logging.getLogger(__name__)

class ScenarioHistoryManager:
    """Manages the persistence of simulation scenarios."""
    
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        self._init_table()
        
    def _init_table(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decision_scenarios (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    is_baseline BOOLEAN DEFAULT 0,
                    created_at TEXT
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scenarios_user_id ON decision_scenarios(user_id)')
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error initializing scenarios table: {e}")
        finally:
            if conn:
                conn.close()

    def save_scenario(self, user_id: int, scenario_id: str, name: str, inputs: ScenarioInputs, is_baseline: bool = False) -> bool:
        """Saves a scenario to the database."""
        try:
            # We must serialize the dataclass deeply
            from dataclasses import asdict
            inputs_dict = asdict(inputs)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO decision_scenarios (id, user_id, name, inputs_json, is_baseline, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                scenario_id,
                user_id,
                name,
                json.dumps(inputs_dict),
                is_baseline,
                datetime.utcnow().isoformat()
            ))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error saving scenario {scenario_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error serializing scenario {scenario_id}: {e}")
            return False
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    def get_user_scenarios(self, user_id: int) -> List[tuple]:
        """Retrieves history for a user. Returns list of tuples (id, name, is_baseline, created_at, inputs)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, is_baseline, created_at, inputs_json 
                FROM decision_scenarios 
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                sid, name, is_base, created, inputs_str = r
                try:
                    data = json.loads(inputs_str)
                    
                    # Reconstruction
                    transport = TransportInputs(**data.get("transport", {}))
                    energy = EnergyInputs(**data.get("energy", {}))
                    food = FoodInputs(**data.get("food", {}))
                    waste = WasteInputs(**data.get("waste", {}))
                    water = WaterInputs(**data.get("water", {}))
                    
                    inputs = ScenarioInputs(transport=transport, energy=energy, food=food, waste=waste, water=water)
                    results.append((sid, name, bool(is_base), created, inputs))
                except Exception as e:
                    logger.warning(f"Error parsing scenario {sid}: {e}")
                    
            return results
        except sqlite3.Error as e:
            logger.error(f"Error retrieving scenarios for user {user_id}: {e}")
            return []
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    def delete_scenario(self, scenario_id: str) -> bool:
        """Deletes a specific scenario."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM decision_scenarios WHERE id = ?", (scenario_id,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error deleting scenario {scenario_id}: {e}")
            return False
        finally:
            if 'conn' in locals() and conn:
                conn.close()
