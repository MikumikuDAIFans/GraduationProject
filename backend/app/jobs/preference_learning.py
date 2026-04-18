"""偏好学习 Celery 定时任务"""

import logging
from datetime import datetime

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def learn_user_preferences(self, user_id: str = None, days: int = 30):
    """
    定期学习用户偏好
    
    如果 user_id 为 None，则学习所有用户的偏好
    """
    from ..core.vector_store import get_vector_store
    from ..db.session import async_session
    from ..services.preference_learner import PreferenceLearner

    try:
        vector_store = get_vector_store()
        
        if user_id:
            user_ids = [user_id]
        else:
            # 获取所有有事件的用户
            from ..models import Event
            from sqlalchemy import select, distinct
            
            import asyncio
            
            async def get_all_users():
                async with async_session() as db:
                    stmt = select(distinct(Event.user_id))
                    result = await db.execute(stmt)
                    return [row[0] for row in result.all() if row[0]]
            
            user_ids = asyncio.run(get_all_users())

        learned_count = 0
        for uid in user_ids:
            async def learn_one(uid):
                async with async_session() as db:
                    learner = PreferenceLearner(db=db, vector_store=vector_store)
                    prefs = await learner.learn_from_history(uid, days=days)
                    return prefs

            prefs = asyncio.run(learn_one(uid))
            if prefs:
                learned_count += 1
                logger.info(f"Learned preferences for user {uid}: {list(prefs.keys())}")

        return f"Learned preferences for {learned_count} users"

    except Exception as e:
        logger.error(f"Failed to learn preferences: {e}")
        raise self.retry(exc=e, countdown=300)  # 5分钟后重试
