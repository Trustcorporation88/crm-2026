# webhook_utils.py - Webhook retry logic and management
import asyncio
import httpx
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional
from structured_logging import get_logger
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base, Session

logger = get_logger("webhook_utils")

Base = declarative_base()

class WebhookLog(Base):
    """Webhook delivery log"""
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True)
    webhook_url = Column(String(500), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)  # pending, success, failed
    attempts = Column(Integer, default=0)
    last_attempt = Column(DateTime, nullable=True)
    next_retry = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WebhookRetryStrategy:
    """Exponential backoff retry strategy"""
    
    MAX_RETRIES = 3
    INITIAL_DELAY = 1  # seconds
    MAX_DELAY = 300    # 5 minutes
    
    @staticmethod
    def get_retry_delay(attempt: int) -> int:
        """Calculate retry delay with exponential backoff"""
        delay = WebhookRetryStrategy.INITIAL_DELAY * (2 ** attempt)
        return min(delay, WebhookRetryStrategy.MAX_DELAY)
    
    @staticmethod
    def should_retry(attempts: int) -> bool:
        """Check if should retry"""
        return attempts < WebhookRetryStrategy.MAX_RETRIES

async def send_webhook_with_retry(
    webhook_url: str,
    payload: Dict[str, Any],
    event_type: str = "webhook_event",
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10
) -> bool:
    """Send webhook with automatic retry logic"""
    
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    
    attempt = 0
    last_error = None
    
    while attempt < WebhookRetryStrategy.MAX_RETRIES:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                response.raise_for_status()
            
            logger.info(
                f"Webhook delivered successfully",
                webhook_url=webhook_url,
                event_type=event_type,
                attempt=attempt + 1
            )
            return True
        
        except Exception as e:
            last_error = str(e)
            attempt += 1
            
            if attempt < WebhookRetryStrategy.MAX_RETRIES:
                delay = WebhookRetryStrategy.get_retry_delay(attempt - 1)
                logger.warning(
                    f"Webhook delivery failed, retrying in {delay}s",
                    webhook_url=webhook_url,
                    event_type=event_type,
                    attempt=attempt,
                    error=last_error
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Webhook delivery failed after {attempt} attempts",
                    webhook_url=webhook_url,
                    event_type=event_type,
                    error=last_error
                )
    
    return False

class WebhookQueue:
    """Queue and retry webhooks asynchronously"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    async def queue_webhook(
        self,
        webhook_url: str,
        payload: Dict[str, Any],
        event_type: str,
        headers: Optional[Dict[str, str]] = None
    ):
        """Queue webhook for delivery"""
        
        # Try immediate delivery
        success = await send_webhook_with_retry(
            webhook_url, payload, event_type, headers
        )
        
        if success:
            status = "success"
            attempts = 1
            next_retry = None
        else:
            status = "pending"
            attempts = 1
            next_retry = datetime.utcnow() + timedelta(
                seconds=WebhookRetryStrategy.get_retry_delay(1)
            )
        
        # Log to database
        log_entry = WebhookLog(
            webhook_url=webhook_url,
            event_type=event_type,
            payload=json.dumps(payload),
            status=status,
            attempts=attempts,
            last_attempt=datetime.utcnow(),
            next_retry=next_retry
        )
        self.db.add(log_entry)
        self.db.commit()
        
        return log_entry.id

async def retry_pending_webhooks(db_session: Session):
    """Retry pending webhooks (call periodically)"""
    
    pending = db_session.query(WebhookLog).filter(
        WebhookLog.status == "pending",
        WebhookLog.next_retry <= datetime.utcnow()
    ).all()
    
    for log in pending:
        if log.attempts >= WebhookRetryStrategy.MAX_RETRIES:
            log.status = "failed"
            continue
        
        payload = json.loads(log.payload)
        success = await send_webhook_with_retry(
            log.webhook_url,
            payload,
            log.event_type
        )
        
        if success:
            log.status = "success"
            log.attempts += 1
        else:
            log.attempts += 1
            log.next_retry = datetime.utcnow() + timedelta(
                seconds=WebhookRetryStrategy.get_retry_delay(log.attempts)
            )
        
        log.last_attempt = datetime.utcnow()
    
    db_session.commit()
