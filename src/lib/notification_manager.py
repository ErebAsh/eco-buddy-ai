"""
Notification Manager for EcoBuddy AI
Handles all notifications, alerts, and reminders for users.
"""

import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import queue
from collections import deque
import hashlib

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    """Notification priority levels."""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    INFO = 4


class NotificationType(Enum):
    """Types of notifications."""
    ALERT = "alert"
    REMINDER = "reminder"
    ACHIEVEMENT = "achievement"
    PROGRESS = "progress"
    TIP = "tip"
    CHALLENGE = "challenge"
    SOCIAL = "social"
    SYSTEM = "system"
    BUDGET = "budget"
    STREAK = "streak"


@dataclass
class Notification:
    """Data class for a single notification."""
    id: str
    user_id: int
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    created_at: datetime
    read: bool = False
    dismissed: bool = False
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'type': self.type.value,
            'priority': self.priority.value,
            'title': self.title,
            'message': self.message,
            'created_at': self.created_at.isoformat(),
            'read': self.read,
            'dismissed': self.dismissed,
            'action_url': self.action_url,
            'action_label': self.action_label,
            'metadata': self.metadata,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Notification':
        """Create notification from dictionary."""
        return cls(
            id=data['id'],
            user_id=data['user_id'],
            type=NotificationType(data['type']),
            priority=NotificationPriority(data['priority']),
            title=data['title'],
            message=data['message'],
            created_at=datetime.fromisoformat(data['created_at']),
            read=data.get('read', False),
            dismissed=data.get('dismissed', False),
            action_url=data.get('action_url'),
            action_label=data.get('action_label'),
            metadata=data.get('metadata', {}),
            expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None,
            read_at=datetime.fromisoformat(data['read_at']) if data.get('read_at') else None,
            delivered_at=datetime.fromisoformat(data['delivered_at']) if data.get('delivered_at') else None
        )


@dataclass
class NotificationPreferences:
    """User notification preferences."""
    user_id: int
    email_enabled: bool = True
    push_enabled: bool = True
    in_app_enabled: bool = True
    digest_enabled: bool = True
    alert_threshold: float = 0.8  # 80% of budget
    reminder_interval_days: int = 7
    quiet_hours_start: int = 22  # 10 PM
    quiet_hours_end: int = 7  # 7 AM
    enabled_types: List[str] = field(default_factory=lambda: [t.value for t in NotificationType])
    email_frequency: str = "daily"  # daily, weekly, monthly


class NotificationManager:
    """
    Manages all notifications, alerts, and reminders for the application.
    Handles creation, storage, delivery, and cleanup of notifications.
    """
    
    def __init__(self):
        self._notifications: Dict[str, Dict[int, List[Notification]]] = {}  # user_id -> list of notifications
        self._preferences: Dict[int, NotificationPreferences] = {}
        self._delivery_queue = queue.Queue()
        self._notification_counter = 0
        self._lock = threading.Lock()
        
        # Start delivery worker
        self._stop_worker = False
        self._worker_thread = threading.Thread(target=self._delivery_worker, daemon=True)
        self._worker_thread.start()
        
        # Notification templates
        self._templates = self._load_templates()
        
        logger.info("NotificationManager initialized")
    
    def _load_templates(self) -> Dict[str, Any]:
        """Load notification templates."""
        return {
            'alert': {
                'carbon_budget_exceeded': {
                    'title': '⚠️ Carbon Budget Alert',
                    'message': 'You have exceeded {percentage}% of your monthly carbon budget. Current usage: {usage:.1f} kg CO₂.',
                    'priority': NotificationPriority.CRITICAL,
                    'action_label': 'View Budget'
                },
                'carbon_budget_warning': {
                    'title': '⚠️ Carbon Budget Warning',
                    'message': 'You have used {percentage}% of your monthly carbon budget. Remaining: {remaining:.1f} kg CO₂.',
                    'priority': NotificationPriority.HIGH,
                    'action_label': 'View Budget'
                },
                'footprint_spike': {
                    'title': '📈 Footprint Spike Detected',
                    'message': 'Your carbon footprint increased by {increase:.1f}% compared to your average.',
                    'priority': NotificationPriority.HIGH,
                    'action_label': 'View Details'
                },
                'streak_at_risk': {
                    'title': '🔥 Streak at Risk!',
                    'message': 'You haven\'t logged an assessment in {days} days. Your {streak} day streak is at risk!',
                    'priority': NotificationPriority.HIGH,
                    'action_label': 'Log Now'
                }
            },
            'achievement': {
                'new_badge': {
                    'title': '🏆 New Badge Unlocked!',
                    'message': 'You earned the "{badge_name}" badge for {reason}!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Badges'
                },
                'level_up': {
                    'title': '🎉 Level Up!',
                    'message': 'Congratulations! You reached Level {level} with {xp} XP!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Profile'
                },
                'milestone_reached': {
                    'title': '🎯 Milestone Reached!',
                    'message': 'You completed {count} assessments! Keep up the great work!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View History'
                }
            },
            'progress': {
                'weekly_summary': {
                    'title': '📊 Weekly Progress Summary',
                    'message': 'This week: {footprint_change}% change in footprint. You completed {assessments} assessments.',
                    'priority': NotificationPriority.LOW,
                    'action_label': 'View Report'
                },
                'monthly_summary': {
                    'title': '📈 Monthly Progress Report',
                    'message': 'This month: You reduced your footprint by {reduction:.1f}%. Average score: {score:.0f}/100.',
                    'priority': NotificationPriority.LOW,
                    'action_label': 'View Report'
                },
                'improvement_detected': {
                    'title': '🌟 Improvement Detected!',
                    'message': 'Your carbon footprint has improved by {improvement:.1f}% compared to last {period}.',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Details'
                }
            },
            'reminder': {
                'assessment_reminder': {
                    'title': '🌱 Assessment Reminder',
                    'message': 'It\'s been {days} days since your last assessment. Log your impact today!',
                    'priority': NotificationPriority.LOW,
                    'action_label': 'Start Assessment'
                },
                'budget_checkin': {
                    'title': '💰 Budget Check-in',
                    'message': 'You\'ve used {percentage}% of your monthly carbon budget. Keep tracking!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Budget'
                },
                'goal_reminder': {
                    'title': '🎯 Goal Reminder',
                    'message': 'You\'re {progress}% towards your goal of {goal} kg CO₂. Keep going!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Goals'
                }
            },
            'challenge': {
                'challenge_start': {
                    'title': '🏁 New Challenge Started!',
                    'message': 'The "{challenge_name}" challenge has started. Complete it to earn {xp} XP!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Challenge'
                },
                'challenge_progress': {
                    'title': '📊 Challenge Progress',
                    'message': 'You\'re {progress}% through the "{challenge_name}" challenge. Keep going!',
                    'priority': NotificationPriority.LOW,
                    'action_label': 'View Challenge'
                },
                'challenge_completed': {
                    'title': '🎉 Challenge Completed!',
                    'message': 'You completed the "{challenge_name}" challenge! Earned {xp} XP!',
                    'priority': NotificationPriority.HIGH,
                    'action_label': 'View Rewards'
                }
            },
            'social': {
                'new_follower': {
                    'title': '👤 New Follower',
                    'message': '{username} started following you!',
                    'priority': NotificationPriority.LOW,
                    'action_label': 'View Profile'
                },
                'community_achievement': {
                    'title': '🏆 Community Achievement',
                    'message': 'Your team "{team_name}" reached a new milestone!',
                    'priority': NotificationPriority.MEDIUM,
                    'action_label': 'View Team'
                },
                'shared_insight': {
                    'title': '💡 Shared Insight',
                    'message': '{username} shared an insight about sustainability with you!',
                    'priority': NotificationPriority.LOW,
                    'action_label': 'View Insight'
                }
            },
            'system': {
                'maintenance': {
                    'title': '🔧 System Maintenance',
                    'message': 'EcoBuddy AI will be undergoing maintenance on {date}. Downtime: ~{duration} minutes.',
                    'priority': NotificationPriority.INFO,
                    'action_label': 'Learn More'
                },
                'feature_update': {
                    'title': '🚀 New Feature Available!',
                    'message': '{feature_name} is now available. Check it out!',
                    'priority': NotificationPriority.INFO,
                    'action_label': 'Explore'
                }
            }
        }
    
    def create_notification(
        self,
        user_id: int,
        type: NotificationType,
        template_key: str,
        **kwargs
    ) -> Optional[Notification]:
        """
        Create a new notification from a template.
        
        Args:
            user_id: User ID
            type: Notification type
            template_key: Template key
            **kwargs: Template variables
        
        Returns:
            Notification object or None
        """
        try:
            # Get template
            template = self._get_template(type, template_key)
            if not template:
                logger.warning(f"Template not found: {type.value}/{template_key}")
                return None
            
            # Check if user has this notification type enabled
            prefs = self.get_preferences(user_id)
            if type.value not in prefs.enabled_types:
                logger.debug(f"User {user_id} has {type.value} notifications disabled")
                return None
            
            # Format message
            title = template['title']
            message = template['message'].format(**kwargs) if kwargs else template['message']
            priority = template.get('priority', NotificationPriority.MEDIUM)
            action_label = template.get('action_label')
            action_url = template.get('action_url')
            
            # Create notification
            notification = Notification(
                id=self._generate_id(user_id),
                user_id=user_id,
                type=type,
                priority=priority,
                title=title,
                message=message,
                created_at=datetime.now(),
                action_url=action_url,
                action_label=action_label,
                metadata=kwargs
            )
            
            # Store notification
            self._store_notification(notification)
            
            # Queue for delivery
            self._delivery_queue.put(notification)
            
            logger.debug(f"Created notification {notification.id} for user {user_id}")
            return notification
            
        except Exception as e:
            logger.error(f"Failed to create notification: {e}")
            return None
    
    def _get_template(self, type: NotificationType, key: str) -> Optional[Dict[str, Any]]:
        """Get notification template."""
        templates = self._templates.get(type.value, {})
        return templates.get(key)
    
    def _generate_id(self, user_id: int) -> str:
        """Generate unique notification ID."""
        self._notification_counter += 1
        timestamp = int(time.time() * 1000)
        return f"notif_{user_id}_{timestamp}_{self._notification_counter}"
    
    def _store_notification(self, notification: Notification) -> None:
        """Store notification in memory."""
        with self._lock:
            if notification.user_id not in self._notifications:
                self._notifications[notification.user_id] = []
            
            # Add to user's notifications
            self._notifications[notification.user_id].append(notification)
            
            # Keep only last 1000 notifications per user
            if len(self._notifications[notification.user_id]) > 1000:
                self._notifications[notification.user_id] = self._notifications[notification.user_id][-1000:]
    
    def _delivery_worker(self) -> None:
        """Background worker for delivering notifications."""
        while not self._stop_worker:
            try:
                notification = self._delivery_queue.get(timeout=1)
                if notification:
                    self._deliver_notification(notification)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Delivery worker error: {e}")
    
    def _deliver_notification(self, notification: Notification) -> None:
        """Deliver notification to user."""
        try:
            prefs = self.get_preferences(notification.user_id)
            
            # Check quiet hours
            if self._is_quiet_hours(prefs):
                # Schedule for later delivery
                logger.debug(f"Notification {notification.id} delayed due to quiet hours")
                # Reschedule for delivery after quiet hours
                self._delivery_queue.put(notification)
                return
            
            # In-app delivery
            if prefs.in_app_enabled:
                self._deliver_in_app(notification)
            
            # Push delivery
            if prefs.push_enabled:
                self._deliver_push(notification)
            
            # Email delivery (only for important notifications)
            if prefs.email_enabled and notification.priority in [NotificationPriority.CRITICAL, NotificationPriority.HIGH]:
                self._deliver_email(notification)
            
            notification.delivered_at = datetime.now()
            
        except Exception as e:
            logger.error(f"Failed to deliver notification {notification.id}: {e}")
    
    def _deliver_in_app(self, notification: Notification) -> None:
        """Deliver notification in-app."""
        # In-app delivery is handled by the UI polling for notifications
        # Mark as delivered
        notification.delivered_at = datetime.now()
    
    def _deliver_push(self, notification: Notification) -> None:
        """Deliver push notification."""
        # This would integrate with a push notification service
        # For now, we just log it
        logger.debug(f"Push notification: {notification.title}")
    
    def _deliver_email(self, notification: Notification) -> None:
        """Deliver email notification."""
        # This would integrate with an email service
        # For now, we just log it
        logger.debug(f"Email notification: {notification.title}")
    
    def _is_quiet_hours(self, prefs: NotificationPreferences) -> bool:
        """Check if current time is within quiet hours."""
        now = datetime.now()
        current_hour = now.hour
        
        if prefs.quiet_hours_start > prefs.quiet_hours_end:
            # Quiet hours wrap around midnight
            return current_hour >= prefs.quiet_hours_start or current_hour < prefs.quiet_hours_end
        else:
            return prefs.quiet_hours_start <= current_hour < prefs.quiet_hours_end
    
    def get_user_notifications(
        self,
        user_id: int,
        include_read: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Notification]:
        """
        Get notifications for a user.
        
        Args:
            user_id: User ID
            include_read: Include read notifications
            limit: Maximum number of notifications
            offset: Offset for pagination
        
        Returns:
            List of notifications
        """
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            
            if not include_read:
                notifications = [n for n in notifications if not n.read]
            
            # Sort by created_at descending
            notifications = sorted(notifications, key=lambda n: n.created_at, reverse=True)
            
            return notifications[offset:offset + limit]
    
    def get_unread_count(self, user_id: int) -> int:
        """Get number of unread notifications for a user."""
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            return sum(1 for n in notifications if not n.read and not n.dismissed)
    
    def mark_as_read(self, user_id: int, notification_id: str) -> bool:
        """Mark a notification as read."""
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            for n in notifications:
                if n.id == notification_id:
                    n.read = True
                    n.read_at = datetime.now()
                    return True
            return False
    
    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user."""
        count = 0
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            for n in notifications:
                if not n.read:
                    n.read = True
                    n.read_at = datetime.now()
                    count += 1
            return count
    
    def dismiss_notification(self, user_id: int, notification_id: str) -> bool:
        """Dismiss a notification."""
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            for n in notifications:
                if n.id == notification_id:
                    n.dismissed = True
                    return True
            return False
    
    def dismiss_all(self, user_id: int) -> int:
        """Dismiss all notifications for a user."""
        count = 0
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            for n in notifications:
                if not n.dismissed:
                    n.dismissed = True
                    count += 1
            return count
    
    def get_preferences(self, user_id: int) -> NotificationPreferences:
        """Get user notification preferences."""
        if user_id not in self._preferences:
            self._preferences[user_id] = NotificationPreferences(user_id=user_id)
        return self._preferences[user_id]
    
    def update_preferences(self, user_id: int, **kwargs) -> NotificationPreferences:
        """Update user notification preferences."""
        prefs = self.get_preferences(user_id)
        for key, value in kwargs.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        return prefs
    
    def cleanup_expired(self) -> int:
        """Remove expired notifications."""
        count = 0
        now = datetime.now()
        
        with self._lock:
            for user_id in list(self._notifications.keys()):
                notifications = self._notifications[user_id]
                self._notifications[user_id] = [
                    n for n in notifications
                    if not (n.expires_at and n.expires_at < now)
                ]
                count += len(notifications) - len(self._notifications[user_id])
                
                # Remove empty user lists
                if not self._notifications[user_id]:
                    del self._notifications[user_id]
        
        return count
    
    def cleanup_old(self, days: int = 30) -> int:
        """Remove notifications older than specified days."""
        count = 0
        cutoff = datetime.now() - timedelta(days=days)
        
        with self._lock:
            for user_id in list(self._notifications.keys()):
                notifications = self._notifications[user_id]
                self._notifications[user_id] = [
                    n for n in notifications
                    if n.created_at > cutoff
                ]
                count += len(notifications) - len(self._notifications[user_id])
                
                if not self._notifications[user_id]:
                    del self._notifications[user_id]
        
        return count
    
    def get_notification_stats(self, user_id: int) -> Dict[str, Any]:
        """Get notification statistics for a user."""
        with self._lock:
            notifications = self._notifications.get(user_id, [])
            
            stats = {
                'total': len(notifications),
                'unread': sum(1 for n in notifications if not n.read and not n.dismissed),
                'read': sum(1 for n in notifications if n.read),
                'dismissed': sum(1 for n in notifications if n.dismissed),
                'by_type': {},
                'by_priority': {}
            }
            
            for n in notifications:
                stats['by_type'][n.type.value] = stats['by_type'].get(n.type.value, 0) + 1
                stats['by_priority'][n.priority.name] = stats['by_priority'].get(n.priority.name, 0) + 1
            
            return stats
    
    def get_notification_templates(self) -> Dict[str, Any]:
        """Get all notification templates."""
        return self._templates
    
    def stop(self) -> None:
        """Stop the notification manager."""
        self._stop_worker = True
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)


# Global notification manager instance
_notification_manager: Optional[NotificationManager] = None
_notification_manager_lock = threading.Lock()


def get_notification_manager() -> NotificationManager:
    """Get or create global notification manager instance."""
    global _notification_manager
    with _notification_manager_lock:
        if _notification_manager is None:
            _notification_manager = NotificationManager()
        return _notification_manager


def create_notification(
    user_id: int,
    type: NotificationType,
    template_key: str,
    **kwargs
) -> Optional[Notification]:
    """
    Convenience function to create a notification.
    
    Args:
        user_id: User ID
        type: Notification type
        template_key: Template key
        **kwargs: Template variables
    
    Returns:
        Notification object or None
    """
    manager = get_notification_manager()
    return manager.create_notification(user_id, type, template_key, **kwargs)


def get_user_notifications(
    user_id: int,
    include_read: bool = False,
    limit: int = 50,
    offset: int = 0
) -> List[Notification]:
    """
    Convenience function to get user notifications.
    
    Args:
        user_id: User ID
        include_read: Include read notifications
        limit: Maximum number of notifications
        offset: Offset for pagination
    
    Returns:
        List of notifications
    """
    manager = get_notification_manager()
    return manager.get_user_notifications(user_id, include_read, limit, offset)


def get_unread_count(user_id: int) -> int:
    """Convenience function to get unread notification count."""
    manager = get_notification_manager()
    return manager.get_unread_count(user_id)


def mark_as_read(user_id: int, notification_id: str) -> bool:
    """Convenience function to mark notification as read."""
    manager = get_notification_manager()
    return manager.mark_as_read(user_id, notification_id)


def mark_all_as_read(user_id: int) -> int:
    """Convenience function to mark all notifications as read."""
    manager = get_notification_manager()
    return manager.mark_all_as_read(user_id)

def dismiss_notification(user_id: int, notification_id: str) -> bool:
    """Convenience function to dismiss a notification."""
    manager = get_notification_manager()
    return manager.dismiss_notification(user_id, notification_id)

def dismiss_all(user_id: int) -> int:
    """Convenience function to dismiss all notifications."""
    manager = get_notification_manager()
    return manager.dismiss_all(user_id)