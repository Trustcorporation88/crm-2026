# cache_utils.py - Caching strategy utilities
import json
import functools
import redis
import hashlib
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
    """Remove do cache todas as chaves que casam com o padrão.

    Usa SCAN, não KEYS. O KEYS percorre o keyspace inteiro numa única operação
    bloqueante: enquanto ele roda, o Redis não atende mais ninguém. Num banco
    pequeno passa despercebido; num banco grande, cada invalidação de cache
    vira uma pausa no serviço inteiro.

    O SCAN faz o mesmo trabalho em fatias, cedendo o controle entre elas. A
    remoção também é feita em lotes, porque um DELETE com dezenas de milhares
    de argumentos recria o problema que o SCAN evita.
    """
    if not redis_client:
        return

    lote: list = []
    for chave in redis_client.scan_iter(match=pattern, count=500):
        lote.append(chave)
        if len(lote) >= 500:
            redis_client.delete(*lote)
            lote = []
    if lote:
        redis_client.delete(*lote)

class CacheStrategy:
    """Estratégia de cache por tipo de dado.

    NOTA: esta classe não é usada por nenhuma parte do sistema hoje. O que está
    em uso neste módulo são `init_redis` e `clear_cache_pattern`, ambos
    chamados por `crm_api.py`.

    Foi mantida porque descreve uma política de TTL coerente e serve de ponto
    de partida caso o cache por entidade venha a ser adotado. Quem for usá-la
    precisa saber de uma armadilha: não existe invalidação ligada aos caminhos
    de escrita. Aplicar estes métodos sem também chamar os `invalidate_*` em
    todo `add_*` e `update_*` do backend produz leitura de dado velho por até
    o TTL configurado — uma hora, no caso de cliente.
    """
    
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
        # Mesma razão de clear_cache_pattern: KEYS bloqueia o Redis inteiro.
        clear_cache_pattern("customer:*")
    
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
