"""Limiares de data para as consultas de scoring.

Existe porque as colunas de timestamp do banco guardam TEXT em mais de um
formato: linhas antigas em ``2026-05-25 08:30`` e linhas novas no ISO UTC
adotado depois (``2026-05-25T08:30:00+00:00``). Como a comparação em SQL sobre
essas colunas é lexicográfica, o formato do limiar decide o resultado — e um
limiar com hora erra em um dos dois formatos, sempre.

A demonstração, com limiar ``2026-08-05 13:29``:

    "2026-08-05T00:01:00+00:00" >= "2026-08-05 13:29"  ->  True

O registro é das 00:01, anterior ao limiar das 13:29, e ainda assim entra: o
``T`` do ISO (0x54) é maior que o espaço (0x20) do formato antigo. Usar um
limiar em ISO inverte o problema e passa a excluir indevidamente as linhas
antigas do dia.

Um limiar contendo **apenas a data** é o único que se comporta corretamente
nos dois formatos ao mesmo tempo, porque ``"2026-08-05"`` é prefixo de ambos e
qualquer registro daquele dia o sucede na ordenação. Também preserva o uso de
índice, por continuar sendo comparação de prefixo sem função sobre a coluna.

O efeito prático é que as janelas passam a começar à meia-noite do dia
correspondente, em vez do horário exato da execução. Para janelas de 7, 14, 30
ou 90 dias, essa é a semântica que se espera de "últimos N dias" — a precisão
de hora anterior era ilusória, já que nunca funcionou nos dois formatos.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Agora, em UTC e com fuso explícito."""
    return datetime.now(timezone.utc)


def limiar_de_dias(dias: int) -> str:
    """Data de corte para uma janela de ``dias``, no formato ``YYYY-MM-DD``.

    Use este valor ao comparar com colunas de timestamp em SQL::

        WHERE event_at >= ?    -- limiar_de_dias(7)
    """
    return (utcnow() - timedelta(days=dias)).strftime("%Y-%m-%d")


def carimbo_utc() -> str:
    """Timestamp de escrita, em ISO 8601 UTC.

    Mesmo formato que ``crm_backend`` passou a gravar, para que colunas
    escritas por estes módulos não reintroduzam a divergência.
    """
    return utcnow().isoformat()
