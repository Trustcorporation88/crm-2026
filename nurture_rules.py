"""Jornadas automáticas de nutrição: gatilhos que propõem matrícula em cadências.

Antes desta automação, toda matrícula em cadência (``cadences.py``) era
manual: alguém tinha que abrir o cliente e escolher a sequência um a um.
Isso é disparo pontual, não jornada de nutrição — a Fase 2 do roadmap pede
o oposto: o sistema detecta sozinho quem deveria entrar em qual sequência.

Mesmo desenho de ``automation_rules.py``: a avaliação é lógica pura (recebe
dados já carregados, devolve propostas), quem aplica é o backend
(``cadences.enroll_proposals``), e a matrícula é idempotente porque só
propõe quando não existe matrícula ATIVA (não concluída) do cliente naquela
cadência — se a jornada já terminou e o cliente voltou a bater no mesmo
gatilho, ele entra de novo, o que é o comportamento certo para nutrição
contínua.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

NEW_LEAD_STATUS = "Novo"
ACTIVE_STATUS = "Ativo"
PROPOSAL_STAGE = "Proposta"
SILENCE_DAYS = 60

# Catálogo exibido na tela de Cadências. Descrição em linguagem de operação,
# igual ao padrão de automation_rules.RULES_CATALOG.
RULES_CATALOG = [
    {
        "id": "lead_novo_sem_jornada",
        "name": "Lead novo sem jornada → matrícula em «Novo lead»",
        "cadence_key": "new_lead_outbound",
        "description": (
            "Cliente com status «Novo» e sem nenhuma cadência ativa entra na "
            "sequência de 5 toques em 14 dias."
        ),
    },
    {
        "id": "proposta_sem_acompanhamento",
        "name": "Proposta em aberto sem cadência → matrícula em «Pós-proposta»",
        "cadence_key": "post_proposal",
        "description": (
            "Negociação na etapa Proposta cujo cliente ainda não está na "
            "cadência de acompanhamento pós-proposta."
        ),
    },
    {
        "id": "cliente_parado_60d",
        "name": "Cliente ativo parado 60d+ → matrícula em «Reativação»",
        "cadence_key": "win_back",
        "description": (
            "Cliente ativo sem nenhuma interação há 60 dias ou mais entra na "
            "cadência de reativação."
        ),
    },
]


@dataclass(frozen=True)
class ProposedEnrollment:
    """Matrícula que uma regra quer criar."""

    rule: str
    cadence_key: str
    cadence_title: str
    customer_id: str
    customer_name: str
    deal_id: str | None
    owner: str
    reason: str


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return [] if frame.empty else frame.to_dict("records")
    return list(frame)


def _days_since(value: Any, today: date) -> int | None:
    from crm_ux import parse_date

    parsed = parse_date(value)
    return (today - parsed).days if parsed else None


def evaluate_rules(
    customers: Any = None,
    deals: Any = None,
    last_activity: dict[str, Any] | None = None,
    active_enrollments: set[tuple[str, str]] | None = None,
    cadence_titles: dict[str, str] | None = None,
    today: date | None = None,
    enabled: set[str] | None = None,
) -> list[ProposedEnrollment]:
    """Avalia todas as regras e devolve as matrículas propostas.

    ``active_enrollments`` é o conjunto de (customer_id, cadence_key) com
    matrícula em andamento agora (``cadences.get_active_enrollment_keys()``)
    — é o que garante que ninguém é proposto duas vezes para a mesma jornada.
    """
    today = today or date.today()
    last_activity = last_activity or {}
    active_enrollments = active_enrollments or set()
    cadence_titles = cadence_titles or {}
    ativos = {r["id"] for r in RULES_CATALOG} if enabled is None else set(enabled)
    propostas: list[ProposedEnrollment] = []

    def _title(key: str) -> str:
        return cadence_titles.get(key, key)

    customer_records = _records(customers)

    # 1) Lead novo sem nenhuma jornada.
    if "lead_novo_sem_jornada" in ativos:
        key = "new_lead_outbound"
        for cust in customer_records:
            if str(cust.get("status", "")) != NEW_LEAD_STATUS:
                continue
            cid = str(cust.get("customer_id", ""))
            if (cid, key) in active_enrollments:
                continue
            propostas.append(
                ProposedEnrollment(
                    rule="lead_novo_sem_jornada",
                    cadence_key=key,
                    cadence_title=_title(key),
                    customer_id=cid,
                    customer_name=str(cust.get("name", "")),
                    deal_id=None,
                    owner=str(cust.get("owner", "") or ""),
                    reason=f"{cust.get('name', '')} entrou como lead novo e ainda não tem sequência de toques.",
                )
            )

    # 2) Negociação em Proposta sem cadência de acompanhamento.
    if "proposta_sem_acompanhamento" in ativos:
        key = "post_proposal"
        customers_by_id = {str(c.get("customer_id", "")): c for c in customer_records}
        for deal in _records(deals):
            if str(deal.get("stage", "")) != PROPOSAL_STAGE:
                continue
            cid = str(deal.get("customer_id", ""))
            if (cid, key) in active_enrollments:
                continue
            cust = customers_by_id.get(cid, {})
            propostas.append(
                ProposedEnrollment(
                    rule="proposta_sem_acompanhamento",
                    cadence_key=key,
                    cadence_title=_title(key),
                    customer_id=cid,
                    customer_name=str(cust.get("name", cid)),
                    deal_id=str(deal.get("deal_id", "")) or None,
                    owner=str(deal.get("owner", "") or cust.get("owner", "") or ""),
                    reason=f"«{deal.get('name', '')}» está em Proposta sem cadência de acompanhamento.",
                )
            )

    # 3) Cliente ativo em silêncio há 60 dias ou mais.
    if "cliente_parado_60d" in ativos:
        key = "win_back"
        for cust in customer_records:
            if str(cust.get("status", "")) != ACTIVE_STATUS:
                continue
            cid = str(cust.get("customer_id", ""))
            if (cid, key) in active_enrollments:
                continue
            dias = _days_since(last_activity.get(cid), today)
            if dias is None or dias < SILENCE_DAYS:
                continue
            propostas.append(
                ProposedEnrollment(
                    rule="cliente_parado_60d",
                    cadence_key=key,
                    cadence_title=_title(key),
                    customer_id=cid,
                    customer_name=str(cust.get("name", "")),
                    deal_id=None,
                    owner=str(cust.get("owner", "") or ""),
                    reason=f"{cust.get('name', '')} sem nenhuma interação há {dias} dias.",
                )
            )

    return propostas


def summarize_proposals(proposals: list[ProposedEnrollment]) -> dict[str, int]:
    """Contagem por regra — alimenta a prévia («o que vai ser criado»)."""
    resumo: dict[str, int] = {}
    for item in proposals:
        resumo[item.rule] = resumo.get(item.rule, 0) + 1
    return resumo
