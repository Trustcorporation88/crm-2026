"""Automações do CRM: regras que criam trabalho sozinhas.

Substitui o antigo ``workflow_engine.py``, que era uma fachada — todos os
handlers apenas escreviam log e devolviam status fabricado, sem tocar no banco.

O desenho aqui é o oposto: a avaliação das regras é **lógica pura** (sem
Streamlit, sem banco), devolve tarefas propostas, e quem grava é o backend.
Isso permite testar cada regra com dados de mesa e mostrar uma prévia ao
usuário antes de qualquer escrita.

Idempotência é requisito, não detalhe: o nome da tarefa é determinístico por
regra + entidade (sem números que mudam a cada dia), então rodar a automação
todo dia não gera fila duplicada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from crm_ux import CLOSED_STAGES, DEFAULT_ROT_DAYS, STAGE_ROT_DAYS, format_compact_brl, parse_date


@dataclass(frozen=True)
class ProposedTask:
    """Tarefa que uma regra quer criar. `task` é a chave natural (idempotência)."""

    rule: str
    task: str
    owner: str
    due_date: str
    priority: str
    entity: str
    reason: str


# Catálogo exibido na tela de Automações. Descrição em linguagem de operação:
# o usuário precisa entender o que vai acontecer antes de ligar.
RULES_CATALOG = [
    {
        "id": "negocio_parado",
        "name": "Negócio parado → tarefa de retomada",
        "description": (
            "Negociação aberta sem interação além do limite da etapa "
            "(Descoberta 21 dias, Proposta 10, Negociação 7) vira tarefa para o responsável."
        ),
        "priority": "Alta",
    },
    {
        "id": "sla_em_risco",
        "name": "Chamado estourando SLA → tarefa de escalonamento",
        "description": "Ticket aberto que passou do prazo de SLA vira tarefa crítica para o responsável.",
        "priority": "Critica",
    },
    {
        "id": "conta_em_risco",
        "name": "Conta em risco → tarefa de retenção",
        "description": "Cliente com saúde abaixo de 50 vira tarefa de retenção para o responsável da conta.",
        "priority": "Alta",
    },
    {
        "id": "cliente_sem_contato",
        "name": "Cliente sem contato há 60 dias → tarefa de reativação",
        "description": "Conta ativa sem nenhuma interação registrada há 60 dias vira tarefa de reativação.",
        "priority": "Media",
    },
]

SILENCE_DAYS = 60
HEALTH_AT_RISK = 50


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return [] if frame.empty else frame.to_dict("records")
    return list(frame)


def _days_since(value: Any, today: date) -> int | None:
    parsed = parse_date(value)
    return (today - parsed).days if parsed else None


def evaluate_rules(
    deals: Any = None,
    tickets: Any = None,
    customers: Any = None,
    last_activity: dict[str, Any] | None = None,
    today: date | None = None,
    enabled: set[str] | None = None,
) -> list[ProposedTask]:
    """Avalia todas as regras e devolve as tarefas propostas.

    `last_activity` mapeia customer_id -> data da última interação (o mesmo
    dicionário que o funil já usa para marcar negociação parada).
    """
    today = today or date.today()
    last_activity = last_activity or {}
    ativos = {r["id"] for r in RULES_CATALOG} if enabled is None else set(enabled)
    propostas: list[ProposedTask] = []

    # 1) Negociação aberta parada além do limite da etapa.
    if "negocio_parado" in ativos:
        for deal in _records(deals):
            stage = str(deal.get("stage", ""))
            if stage in CLOSED_STAGES:
                continue
            dias = _days_since(last_activity.get(deal.get("customer_id")), today)
            limite = STAGE_ROT_DAYS.get(stage, DEFAULT_ROT_DAYS)
            if dias is None or dias <= limite:
                continue
            deal_id = str(deal.get("deal_id", ""))
            propostas.append(
                ProposedTask(
                    rule="negocio_parado",
                    task=f"Retomar negociação parada — {deal_id}",
                    owner=str(deal.get("owner", "")),
                    due_date=today.isoformat(),
                    priority="Alta",
                    entity=deal_id,
                    reason=(
                        f"«{deal.get('name', '')}» em {stage} há {dias} dias sem contato "
                        f"({format_compact_brl(deal.get('value'))} em risco)."
                    ),
                )
            )

    # 2) Ticket aberto que estourou o SLA.
    if "sla_em_risco" in ativos:
        for ticket in _records(tickets):
            if str(ticket.get("status", "")) == "Resolvido":
                continue
            try:
                idade = float(ticket.get("age_hours") or 0)
                alvo = float(ticket.get("sla_hours") or 0)
            except (TypeError, ValueError):
                continue
            if alvo <= 0 or idade <= alvo:
                continue
            ticket_id = str(ticket.get("ticket_id", ""))
            propostas.append(
                ProposedTask(
                    rule="sla_em_risco",
                    task=f"Escalonar chamado fora do prazo — {ticket_id}",
                    owner=str(ticket.get("owner", "")),
                    due_date=today.isoformat(),
                    priority="Critica",
                    entity=ticket_id,
                    reason=(
                        f"«{ticket.get('subject', '')}» com {idade:.0f}h de "
                        f"{alvo:.0f}h de SLA ({idade / alvo * 100:.0f}% consumido)."
                    ),
                )
            )

    # 3) Conta com saúde baixa.
    if "conta_em_risco" in ativos:
        for customer in _records(customers):
            try:
                saude = int(customer.get("health_score") or 0)
            except (TypeError, ValueError):
                continue
            if saude >= HEALTH_AT_RISK:
                continue
            customer_id = str(customer.get("customer_id", ""))
            propostas.append(
                ProposedTask(
                    rule="conta_em_risco",
                    task=f"Plano de retenção — {customer_id}",
                    owner=str(customer.get("owner", "")),
                    due_date=(today + timedelta(days=2)).isoformat(),
                    priority="Alta",
                    entity=customer_id,
                    reason=f"{customer.get('name', '')} com saúde {saude}/100 (abaixo de {HEALTH_AT_RISK}).",
                )
            )

    # 4) Conta ativa em silêncio há muito tempo.
    if "cliente_sem_contato" in ativos:
        for customer in _records(customers):
            if str(customer.get("status", "")) not in ("Ativo", "Novo"):
                continue
            customer_id = str(customer.get("customer_id", ""))
            dias = _days_since(last_activity.get(customer_id), today)
            if dias is None or dias < SILENCE_DAYS:
                continue
            propostas.append(
                ProposedTask(
                    rule="cliente_sem_contato",
                    task=f"Reativar relacionamento — {customer_id}",
                    owner=str(customer.get("owner", "")),
                    due_date=(today + timedelta(days=3)).isoformat(),
                    priority="Media",
                    entity=customer_id,
                    reason=f"{customer.get('name', '')} sem nenhuma interação há {dias} dias.",
                )
            )

    return propostas


def summarize_proposals(proposals: list[ProposedTask]) -> dict[str, int]:
    """Contagem por regra — alimenta a prévia («o que vai ser criado»)."""
    resumo: dict[str, int] = {}
    for item in proposals:
        resumo[item.rule] = resumo.get(item.rule, 0) + 1
    return resumo
