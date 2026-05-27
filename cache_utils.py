# cache_utils.py - Caching strategy utilities
import json
import asyncio
import functools
import redis
import hashlib
from datetime import timedelta
from typing import Any, Callable, Optional

# Initialize Redis connection
redis_client = None

def init_redis(redis_url: str):
    """Initialize Redis connection"""
    global redis_client
    redis_client = redis.from_url(redis_url)
    return redis_client

def cache_key(*args, **kwargs) -> str:
    """Generate cache key from function args"""
    key_data = f"{str(args)}{str(sorted(kwargs.items()))}"
    return hashlib.md5(key_data.encode()).hexdigest()

def cache(ttl_seconds: int = 3600):
    """Decorator for caching function results"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not redis_client:
                return await func(*args, **kwargs)
            
            key = f"{func.__name__}:{cache_key(*args, **kwargs)}"
            
            # Try get from cache
            try:
                cached = redis_client.get(key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
            
            # Get fresh data
            result = await func(*args, **kwargs)
            
            # Store in cache
            try:
                redis_client.setex(key, ttl_seconds, json.dumps(result))
            except Exception:
                pass
            
            return result
        
        return wrapper
    return decorator

def clear_cache_pattern(pattern: str):
    """Clear all cache entries matching pattern"""
    if not redis_client:
        return
    
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)

class CacheStrategy:
    """Centralized caching strategy"""
    
    # TTL for different data types
    CUSTOMER_TTL = 3600      # 1 hour
    TICKET_TTL = 600        # 10 min (changes frequently)
    DEAL_TTL = 1800         # 30 min
    USER_TTL = 7200         # 2 hours
    CONFIG_TTL = 86400      # 1 day
    
    @staticmethod
    def get_customer(customer_id: int) -> Optional[dict]:
        """Get cached customer"""
        if not redis_client:
            return None
        key = f"customer:{customer_id}"
        cached = redis_client.get(key)
        return json.loads(cached) if cached else None
    
    @staticmethod
    def set_customer(customer_id: int, data: dict):
        """Set customer cache"""
        if not redis_client:
            return
        key = f"customer:{customer_id}"
        redis_client.setex(key, CacheStrategy.CUSTOMER_TTL, json.dumps(data))
    
    @staticmethod
    def invalidate_customer(customer_id: int):
        """Invalidate customer cache"""
        if not redis_client:
            return
        redis_client.delete(f"customer:{customer_id}")
    
    @staticmethod
    def invalidate_all_customers():
        """Invalidate all customer caches"""
        if not redis_client:
            return
        keys = redis_client.keys("customer:*")
        if keys:
            redis_client.delete(*keys)
    
    @staticmethod
    def get_ticket(ticket_id: int) -> Optional[dict]:
        """Get cached ticket"""
        if not redis_client:
            return None
        key = f"ticket:{ticket_id}"
        cached = redis_client.get(key)
        return json.loads(cached) if cached else None
    
    @staticmethod
    def set_ticket(ticket_id: int, data: dict):
        """Set ticket cache"""
        if not redis_client:
            return
        key = f"ticket:{ticket_id}"
        redis_client.setex(key, CacheStrategy.TICKET_TTL, json.dumps(data))
    
    @staticmethod
    def invalidate_ticket(ticket_id: int):
        """Invalidate ticket cache"""
        if not redis_client:
            return
        redis_client.delete(f"ticket:{ticket_id}")
    
    @staticmethod
    def get_config(key: str) -> Optional[Any]:
        """Get cached config"""
        if not redis_client:
            return None
        cached = redis_client.get(f"config:{key}")
        return json.loads(cached) if cached else None
    
    @staticmethod
    def set_config(key: str, value: Any):
        """Set config cache"""
        if not redis_client:
            return
        redis_client.setex(f"config:{key}", CacheStrategy.CONFIG_TTL, json.dumps(value))
