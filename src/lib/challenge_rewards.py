"""
Challenge Rewards for EcoBuddy AI
Manages rewards, achievements, and reward tiers for challenges.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger(__name__)


class RewardType(Enum):
    """Types of rewards."""
    XP = "xp"
    BADGE = "badge"
    TITLE = "title"
    ICON = "icon"
    CUSTOM = "custom"


class RewardTier(Enum):
    """Reward tiers."""
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


@dataclass
class Reward:
    """Data class for a reward."""
    id: str
    type: RewardType
    tier: RewardTier
    name: str
    description: str
    value: Any
    icon: Optional[str] = None
    requirements: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RewardClaim:
    """Data class for a reward claim."""
    reward_id: str
    user_id: int
    claimed_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChallengeRewards:
    """
    Manages rewards for challenges and achievements.
    """
    
    def __init__(self):
        self._rewards: Dict[str, Reward] = {}
        self._user_rewards: Dict[int, List[str]] = {}  # user_id -> reward_ids
        self._reward_tiers = self._load_reward_tiers()
        
        # Load default rewards
        self._load_default_rewards()
        
        logger.info("ChallengeRewards initialized")
    
    def _load_reward_tiers(self) -> Dict[str, Dict[str, Any]]:
        """Load reward tier configurations."""
        return {
            'bronze': {
                'color': '#cd7f32',
                'icon': '🥉',
                'xp_multiplier': 1.0,
                'badge_style': 'bronze'
            },
            'silver': {
                'color': '#c0c0c0',
                'icon': '🥈',
                'xp_multiplier': 1.5,
                'badge_style': 'silver'
            },
            'gold': {
                'color': '#ffd700',
                'icon': '🥇',
                'xp_multiplier': 2.0,
                'badge_style': 'gold'
            },
            'platinum': {
                'color': '#e5e4e2',
                'icon': '💎',
                'xp_multiplier': 2.5,
                'badge_style': 'platinum'
            },
            'diamond': {
                'color': '#b9f2ff',
                'icon': '💠',
                'xp_multiplier': 3.0,
                'badge_style': 'diamond'
            }
        }
    
    def _load_default_rewards(self) -> None:
        """Load default rewards."""
        defaults = [
            Reward(
                id="first_challenge",
                type=RewardType.BADGE,
                tier=RewardTier.BRONZE,
                name="First Challenge",
                description="Completed your first challenge!",
                value="first_challenger",
                icon="🎯",
                requirements={'challenges_completed': 1}
            ),
            Reward(
                id="challenge_master",
                type=RewardType.BADGE,
                tier=RewardTier.SILVER,
                name="Challenge Master",
                description="Completed 10 challenges!",
                value="challenge_master",
                icon="🏆",
                requirements={'challenges_completed': 10}
            ),
            Reward(
                id="challenge_legend",
                type=RewardType.BADGE,
                tier=RewardTier.GOLD,
                name="Challenge Legend",
                description="Completed 50 challenges!",
                value="challenge_legend",
                icon="👑",
                requirements={'challenges_completed': 50}
            ),
            Reward(
                id="team_player",
                type=RewardType.BADGE,
                tier=RewardTier.BRONZE,
                name="Team Player",
                description="Joined a team!",
                value="team_player",
                icon="🤝",
                requirements={'team_joined': True}
            ),
            Reward(
                id="team_captain",
                type=RewardType.BADGE,
                tier=RewardTier.SILVER,
                name="Team Captain",
                description="Created your own team!",
                value="team_captain",
                icon="👑",
                requirements={'team_created': True}
            ),
            Reward(
                id="top_10_rank",
                type=RewardType.BADGE,
                tier=RewardTier.SILVER,
                name="Top 10",
                description="Ranked in the top 10!",
                value="top_10",
                icon="🔟",
                requirements={'rank': 10}
            ),
            Reward(
                id="top_3_rank",
                type=RewardType.BADGE,
                tier=RewardTier.GOLD,
                name="Top 3",
                description="Ranked in the top 3!",
                value="top_3",
                icon="🥉",
                requirements={'rank': 3}
            ),
            Reward(
                id="number_1",
                type=RewardType.BADGE,
                tier=RewardTier.PLATINUM,
                name="Number 1!",
                description="Ranked #1 on the leaderboard!",
                value="number_1",
                icon="👑",
                requirements={'rank': 1}
            )
        ]
        
        for reward in defaults:
            self._rewards[reward.id] = reward
    
    def get_reward(self, reward_id: str) -> Optional[Reward]:
        """Get a reward by ID."""
        return self._rewards.get(reward_id)
    
    def get_all_rewards(self, tier: Optional[RewardTier] = None) -> List[Reward]:
        """Get all rewards, optionally filtered by tier."""
        rewards = list(self._rewards.values())
        if tier:
            rewards = [r for r in rewards if r.tier == tier]
        return rewards
    
    def get_user_rewards(self, user_id: int) -> List[Reward]:
        """Get all rewards a user has earned."""
        reward_ids = self._user_rewards.get(user_id, [])
        return [self._rewards[rid] for rid in reward_ids if rid in self._rewards]
    
    def check_and_award_rewards(self, user_id: int, context: Dict[str, Any]) -> List[Reward]:
        """
        Check if user has earned any rewards based on context.
        
        Args:
            user_id: User ID
            context: Context data (challenges completed, rank, etc.)
        
        Returns:
            List of newly earned rewards
        """
        earned = []
        
        for reward in self._rewards.values():
            if reward.id in self._user_rewards.get(user_id, []):
                continue  # Already earned
            
            if self._check_requirements(reward.requirements, context):
                self._award_reward(user_id, reward.id)
                earned.append(reward)
                logger.info(f"User {user_id} earned reward: {reward.name}")
        
        return earned
    
    def _check_requirements(self, requirements: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if user meets reward requirements."""
        for key, value in requirements.items():
            if key not in context:
                return False
            
            if isinstance(value, dict):
                # Complex requirements
                if not self._check_complex_requirement(value, context[key]):
                    return False
            else:
                # Simple equality or comparison
                if context[key] != value:
                    return False
        
        return True
    
    def _check_complex_requirement(self, requirement: Dict[str, Any], actual_value: Any) -> bool:
        """Check complex requirements with operators."""
        operator = requirement.get('operator', 'eq')
        value = requirement.get('value')
        
        if operator == 'eq':
            return actual_value == value
        elif operator == 'gt':
            return actual_value > value
        elif operator == 'gte':
            return actual_value >= value
        elif operator == 'lt':
            return actual_value < value
        elif operator == 'lte':
            return actual_value <= value
        elif operator == 'between':
            return value[0] <= actual_value <= value[1]
        
        return False
    
    def _award_reward(self, user_id: int, reward_id: str) -> None:
        """Award a reward to a user."""
        if user_id not in self._user_rewards:
            self._user_rewards[user_id] = []
        self._user_rewards[user_id].append(reward_id)
        
        # Create notification
        from .notification_manager import create_notification, NotificationType
        reward = self._rewards.get(reward_id)
        if reward:
            create_notification(
                user_id=user_id,
                type=NotificationType.ACHIEVEMENT,
                template_key='new_badge',
                badge_name=reward.name,
                reason="completing challenges and earning rewards"
            )
    
    def get_reward_stats(self, user_id: int) -> Dict[str, Any]:
        """Get reward statistics for a user."""
        rewards = self.get_user_rewards(user_id)
        
        stats = {
            'total_rewards': len(rewards),
            'by_tier': {},
            'by_type': {}
        }
        
        for reward in rewards:
            stats['by_tier'][reward.tier.value] = stats['by_tier'].get(reward.tier.value, 0) + 1
            stats['by_type'][reward.type.value] = stats['by_type'].get(reward.type.value, 0) + 1
        
        return stats
    
    def get_reward_tier_info(self, tier: RewardTier) -> Dict[str, Any]:
        """Get information about a reward tier."""
        return self._reward_tiers.get(tier.value, {})
    
    def get_next_rewards(self, user_id: int, context: Dict[str, Any]) -> List[Reward]:
        """Get rewards the user is close to earning."""
        next_rewards = []
        
        for reward in self._rewards.values():
            if reward.id in self._user_rewards.get(user_id, []):
                continue
            
            # Check how many requirements are met
            met_count = 0
            total = len(reward.requirements)
            
            for key, value in reward.requirements.items():
                if key in context:
                    if isinstance(value, dict):
                        if self._check_complex_requirement(value, context[key]):
                            met_count += 1
                    else:
                        if context[key] == value:
                            met_count += 1
            
            if total > 0 and met_count / total >= 0.5:  # 50%+ requirements met
                next_rewards.append(reward)
        
        return next_rewards[:5]  # Top 5 closest rewards


# Global challenge rewards instance
_challenge_rewards: Optional[ChallengeRewards] = None


def get_challenge_rewards() -> ChallengeRewards:
    """Get or create global challenge rewards instance."""
    global _challenge_rewards
    if _challenge_rewards is None:
        _challenge_rewards = ChallengeRewards()
    return _challenge_rewards


def check_and_award_rewards(user_id: int, context: Dict[str, Any]) -> List[Reward]:
    """Convenience function to check and award rewards."""
    rewards = get_challenge_rewards()
    return rewards.check_and_award_rewards(user_id, context)


def get_user_rewards(user_id: int) -> List[Reward]:
    """Convenience function to get user rewards."""
    rewards = get_challenge_rewards()
    return rewards.get_user_rewards(user_id)