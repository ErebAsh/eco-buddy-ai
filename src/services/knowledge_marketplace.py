"""
Knowledge Marketplace.
Curates and displays available skill offerings, complete with categories, difficulty levels, and user ratings.
"""

from typing import Dict, Any, List
from src.services.skill_swap_engine import SkillSwapEngine


class KnowledgeMarketplace:
    """Provides search, filter, and display capabilities for the skill swap ecosystem."""

    VALID_CATEGORIES = [
        "gardening",
        "repair",
        "cooking",
        "technology",
        "crafts",
        "finance",
    ]
    VALID_DIFFICULTIES = ["beginner", "intermediate", "advanced"]

    def __init__(self, engine: SkillSwapEngine):
        self.engine = engine

    def get_all_active_listings(self) -> List[Dict[str, Any]]:
        """Returns all active skill listings with teacher details."""
        active_listings = []
        for listing in self.engine.listings:
            if listing["status"] == "active":
                teacher = self.engine.get_user(listing["teacher_id"])
                active_listings.append(
                    {
                        **listing,
                        "teacher_rating": teacher["rating"] if teacher else 5.0,
                        "teacher_swaps": teacher["completed_swaps"] if teacher else 0,
                    }
                )
        return active_listings

    def search_listings(
        self, query: str = "", category: str = "", difficulty: str = ""
    ) -> List[Dict[str, Any]]:
        """Filters active listings based on search criteria."""
        listings = self.get_all_active_listings()
        filtered = listings

        if query:
            query_lower = query.lower()
            filtered = [l for l in filtered if query_lower in l["skill_name"].lower()]

        if category:
            filtered = [
                l for l in filtered if l["category"].lower() == category.lower()
            ]

        if difficulty:
            filtered = [
                l for l in filtered if l["difficulty"].lower() == difficulty.lower()
            ]

        # Sort by teacher rating (descending)
        return sorted(filtered, key=lambda x: x["teacher_rating"], reverse=True)

    def get_marketplace_stats(self) -> Dict[str, Any]:
        """Returns aggregate statistics about the marketplace."""
        active_listings = self.get_all_active_listings()
        categories = {}

        for listing in active_listings:
            cat = listing["category"]
            categories[cat] = categories.get(cat, 0) + 1

        total_swaps = len(self.engine.swaps)

        return {
            "active_listings_count": len(active_listings),
            "total_completed_swaps": total_swaps,
            "category_distribution": categories,
        }
