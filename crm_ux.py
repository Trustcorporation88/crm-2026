"""Camada de usabilidade do TRUST CRM.

Reúne os padrões de UX adotados pelos CRMs de referência (Pipedrive, HubSpot,
Attio, RD Station, Ploomes, Agendor) numa forma implementável em Streamlit.

O módulo é deliberadamente dividido em duas metades:

* **Lógica pura** (formatação pt-BR, validação de CPF/CNPJ, estagnação de
  negociação, resumo de etapa, detecção de duplicados, agenda do dia). São
  funções sem dependência de Streamlit e cobertas por testes.
* **Renderização** (funções ``render_*``), que apenas desenham o resultado da
  lógica acima.

Essa separação é o que permite testar comportamento de produto sem subir a
interface.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Sequence

import pandas as pd


# ---------------------------------------------------------------------------
# Controle de acesso de demonstração
# ---------------------------------------------------------------------------

def demo_login_enabled() -> bool:
    """Login de demonstração em um clique.

    Desligado por padrão: num domínio público esses botões entregam acesso de
    administrador a qualquer visitante. Para habilitar num ambiente de
    demonstração, defina CRM_DEMO_LOGIN=true.
    """
    return os.getenv("CRM_DEMO_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Formatação pt-BR
# ---------------------------------------------------------------------------

def format_brl(value: Any, decimals: int = 0) -> str:
    """Formata um número como moeda brasileira.

    O padrão pt-BR usa ponto para milhar e vírgula para decimal — o inverso do
    padrão americano que o Python produz por default.

    >>> format_brl(190000)
    'R$ 190.000'
    >>> format_brl(1234.56, decimals=2)
    'R$ 1.234,56'
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"

    formatted = f"{number:,.{decimals}f}"
    # en-US -> pt-BR: troca via placeholder para não sobrescrever o separador.
    formatted = formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"R$ {formatted}"


def format_compact_brl(value: Any) -> str:
    """Versão compacta para cabeçalhos de coluna: R$ 1,2 mi / R$ 340 mil."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"

    absolute = abs(number)
    if absolute >= 1_000_000:
        return f"R$ {number / 1_000_000:.1f} mi".replace(".", ",")
    if absolute >= 1_000:
        return f"R$ {number / 1_000:.0f} mil"
    return format_brl(number)


def format_date_br(value: Any) -> str:
    """Converte data ISO (ou datetime) para dd/mm/aaaa."""
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else "—"


def parse_date(value: Any) -> date | None:
    """Interpreta datas em ISO, datetime ou pandas Timestamp. None se inválida."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Aceita "2026-05-19" e "2026-05-19T13:40:00+00:00".
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Documentos brasileiros (CPF / CNPJ)
#
# Expectativa de mercado no Brasil: o CRM valida o dígito verificador antes de
# aceitar o cadastro. Um CNPJ inválido gravado hoje vira retrabalho de limpeza
# de base depois.
# ---------------------------------------------------------------------------

def only_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def validate_cpf(value: Any) -> bool:
    """Valida CPF pelos dois dígitos verificadores (módulo 11)."""
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    for length in (9, 10):
        weights = range(length + 1, 1, -1)
        total = sum(int(d) * w for d, w in zip(digits[:length], weights))
        check = (total * 10) % 11
        check = 0 if check == 10 else check
        if check != int(digits[length]):
            return False
    return True


def validate_cnpj(value: Any) -> bool:
    """Valida CNPJ pelos dois dígitos verificadores (módulo 11)."""
    digits = only_digits(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    for length in (12, 13):
        # Pesos cíclicos 2..9 aplicados da direita para a esquerda.
        weights = [(i % 8) + 2 for i in range(length - 1, -1, -1)]
        total = sum(int(d) * w for d, w in zip(digits[:length], weights))
        remainder = total % 11
        check = 0 if remainder < 2 else 11 - remainder
        if check != int(digits[length]):
            return False
    return True


def format_cpf_cnpj(value: Any) -> str:
    """Aplica a máscara visual conforme o tamanho do documento."""
    digits = only_digits(value)
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return str(value or "")


def describe_document(value: Any) -> tuple[bool, str]:
    """Valida documento e devolve (válido, mensagem para o usuário)."""
    digits = only_digits(value)
    if not digits:
        return False, "Informe o CPF ou CNPJ."
    if len(digits) == 11:
        return (True, "CPF válido.") if validate_cpf(digits) else (False, "CPF inválido — confira os dígitos.")
    if len(digits) == 14:
        return (True, "CNPJ válido.") if validate_cnpj(digits) else (False, "CNPJ inválido — confira os dígitos.")
    return False, "Documento deve ter 11 dígitos (CPF) ou 14 (CNPJ)."


# ---------------------------------------------------------------------------
# Saúde da negociação (padrão "rotting" do Pipedrive / "Mapa de Vendas" do Agendor)
# ---------------------------------------------------------------------------

# Dias de inatividade tolerados por etapa antes da negociação ser sinalizada.
# Etapas mais avançadas apodrecem mais rápido: silêncio numa proposta enviada
# custa mais caro do que silêncio numa descoberta.
STAGE_ROT_DAYS: dict[str, int] = {
    "Descoberta": 21,
    "Proposta": 10,
    "Negociacao": 7,
    "Negociação": 7,
}
DEFAULT_ROT_DAYS = 14

# Etapas terminais não estagnam.
CLOSED_STAGES = {"Fechado ganho", "Fechado perdido"}


@dataclass(frozen=True)
class DealHealth:
    """Resultado da avaliação de uma negociação."""

    status: str  # "ok" | "atencao" | "parado" | "fechado"
    days_idle: int | None
    threshold: int
    label: str

    @property
    def is_stale(self) -> bool:
        return self.status == "parado"


def deal_health(
    stage: str,
    last_activity: Any,
    today: date | None = None,
    thresholds: dict[str, int] | None = None,
) -> DealHealth:
    """Classifica uma negociação pelo tempo sem interação registrada.

    Retorna "parado" quando ultrapassa o limite da etapa, "atencao" a partir de
    70% do limite, e "fechado" para etapas terminais.
    """
    today = today or date.today()
    thresholds = thresholds or STAGE_ROT_DAYS
    threshold = thresholds.get(stage, DEFAULT_ROT_DAYS)

    if stage in CLOSED_STAGES:
        return DealHealth("fechado", None, threshold, "Fechada")

    last = parse_date(last_activity)
    if last is None:
        return DealHealth("parado", None, threshold, "Sem interação registrada")

    days_idle = (today - last).days
    if days_idle < 0:
        days_idle = 0

    if days_idle >= threshold:
        return DealHealth("parado", days_idle, threshold, f"Parada há {days_idle} dias")
    if days_idle >= max(1, int(threshold * 0.7)):
        return DealHealth("atencao", days_idle, threshold, f"{days_idle} dias sem contato")
    return DealHealth("ok", days_idle, threshold, f"Ativa há {days_idle} dias")


def last_activity_by_customer(interactions: pd.DataFrame) -> dict[str, date]:
    """Mapeia cliente -> data da interação mais recente."""
    if interactions is None or interactions.empty:
        return {}

    latest: dict[str, date] = {}
    for row in interactions.to_dict("records"):
        customer_id = row.get("customer_id")
        event_date = parse_date(row.get("event_at"))
        if not customer_id or event_date is None:
            continue
        current = latest.get(customer_id)
        if current is None or event_date > current:
            latest[customer_id] = event_date
    return latest


# ---------------------------------------------------------------------------
# Resumo de etapa do funil (cabeçalho de coluna estilo Pipedrive)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageSummary:
    stage: str
    count: int
    total_value: float
    weighted_value: float
    stale_count: int = 0

    @property
    def headline(self) -> str:
        if self.count == 0:
            return "Nenhuma oportunidade"
        plural = "oportunidade" if self.count == 1 else "oportunidades"
        return f"{self.count} {plural} · {format_compact_brl(self.total_value)}"


def summarize_stage(
    deals: pd.DataFrame,
    stage: str,
    stale_ids: Iterable[Any] = (),
) -> StageSummary:
    """Agrega contagem, valor total e valor ponderado de uma etapa.

    O valor ponderado (valor × probabilidade) é o que o gestor precisa para
    prever receita — sem ele, a soma bruta da coluna superestima o funil.
    """
    if deals is None or deals.empty:
        return StageSummary(stage, 0, 0.0, 0.0, 0)

    subset = deals[deals["stage"] == stage]
    if subset.empty:
        return StageSummary(stage, 0, 0.0, 0.0, 0)

    values = pd.to_numeric(subset["value"], errors="coerce").fillna(0.0)
    probabilities = pd.to_numeric(subset.get("probability", 0), errors="coerce").fillna(0.0)

    total = float(values.sum())
    weighted = float((values * probabilities / 100.0).sum())

    stale_set = set(stale_ids)
    stale_count = 0
    if stale_set and "deal_id" in subset.columns:
        stale_count = int(subset["deal_id"].isin(stale_set).sum())

    return StageSummary(stage, len(subset), total, weighted, stale_count)


def pipeline_totals(deals: pd.DataFrame, open_stages: Sequence[str] | None = None) -> dict[str, float]:
    """Totais do funil aberto: valor bruto, ponderado e ticket médio."""
    empty = {"total": 0.0, "weighted": 0.0, "count": 0, "average": 0.0}
    if deals is None or deals.empty:
        return empty

    subset = deals if open_stages is None else deals[deals["stage"].isin(open_stages)]
    if subset.empty:
        return empty

    values = pd.to_numeric(subset["value"], errors="coerce").fillna(0.0)
    probabilities = pd.to_numeric(subset.get("probability", 0), errors="coerce").fillna(0.0)

    total = float(values.sum())
    count = int(len(subset))
    return {
        "total": total,
        "weighted": float((values * probabilities / 100.0).sum()),
        "count": count,
        "average": total / count if count else 0.0,
    }


# ---------------------------------------------------------------------------
# Detecção de duplicados no cadastro
# ---------------------------------------------------------------------------

def _normalize_name(value: Any) -> str:
    """Normaliza para comparação: sem acento, sem caixa, sem sufixo societário."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"\b(ltda|me|epp|eireli|s\.?a\.?|sa)\b", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def find_duplicates(
    customers: pd.DataFrame,
    name: str | None = None,
    document: str | None = None,
    email: str | None = None,
) -> list[dict[str, Any]]:
    """Procura clientes já cadastrados que colidem com os dados informados.

    Detectar no momento da criação é ordens de magnitude mais barato do que
    deduplicar a base depois.
    """
    if customers is None or customers.empty:
        return []

    target_doc = only_digits(document) if document else ""
    target_name = _normalize_name(name) if name else ""
    target_email = str(email or "").strip().lower()

    matches: list[dict[str, Any]] = []
    for row in customers.to_dict("records"):
        reasons = []

        if target_doc:
            for column in ("document", "cnpj", "cpf", "tax_id"):
                if column in row and only_digits(row.get(column)) == target_doc:
                    reasons.append("mesmo CPF/CNPJ")
                    break

        if target_name and _normalize_name(row.get("name")) == target_name:
            reasons.append("mesmo nome")

        if target_email:
            for column in ("email", "contact_email"):
                if column in row and str(row.get(column) or "").strip().lower() == target_email:
                    reasons.append("mesmo e-mail")
                    break

        if reasons:
            matches.append({
                "customer_id": row.get("customer_id"),
                "name": row.get("name"),
                "reasons": sorted(set(reasons)),
            })

    return matches


# ---------------------------------------------------------------------------
# "Meu Dia" — superfície de trabalho diário
# (HubSpot Sales Workspace / Close Inbox View)
# ---------------------------------------------------------------------------

@dataclass
class DayAgenda:
    overdue_tasks: list[dict[str, Any]] = field(default_factory=list)
    today_tasks: list[dict[str, Any]] = field(default_factory=list)
    stale_deals: list[dict[str, Any]] = field(default_factory=list)
    sla_risk_tickets: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_actions(self) -> int:
        return (
            len(self.overdue_tasks)
            + len(self.today_tasks)
            + len(self.stale_deals)
            + len(self.sla_risk_tickets)
        )

    @property
    def is_empty(self) -> bool:
        return self.total_actions == 0


def build_day_agenda(
    tasks: pd.DataFrame | None,
    deals: pd.DataFrame | None,
    tickets: pd.DataFrame | None,
    interactions: pd.DataFrame | None,
    owner: str | None = None,
    today: date | None = None,
    sla_warning_ratio: float = 0.8,
) -> DayAgenda:
    """Monta a lista de ações do dia para um responsável.

    Responde a "o que eu faço agora?" em vez de obrigar o usuário a varrer
    cada módulo para reconstruir o próprio contexto.
    """
    today = today or date.today()
    agenda = DayAgenda()

    def belongs_to_owner(value: Any) -> bool:
        return not owner or str(value or "").strip() == owner

    # Tarefas vencidas e do dia
    if tasks is not None and not tasks.empty:
        for row in tasks.to_dict("records"):
            if not belongs_to_owner(row.get("owner")):
                continue
            due = parse_date(row.get("due_date"))
            if due is None:
                continue
            if due < today:
                row["days_late"] = (today - due).days
                agenda.overdue_tasks.append(row)
            elif due == today:
                agenda.today_tasks.append(row)

    # Negociações estagnadas
    if deals is not None and not deals.empty:
        latest = last_activity_by_customer(interactions) if interactions is not None else {}
        for row in deals.to_dict("records"):
            if not belongs_to_owner(row.get("owner")):
                continue
            health = deal_health(
                row.get("stage", ""),
                latest.get(row.get("customer_id")),
                today=today,
            )
            if health.is_stale:
                enriched = dict(row)
                enriched["health_label"] = health.label
                enriched["days_idle"] = health.days_idle
                agenda.stale_deals.append(enriched)

    # Tickets perto de estourar o SLA
    if tickets is not None and not tickets.empty:
        for row in tickets.to_dict("records"):
            if not belongs_to_owner(row.get("owner")):
                continue
            if str(row.get("status", "")).strip().lower() in {"resolvido", "fechado", "encerrado"}:
                continue
            try:
                sla_hours = float(row.get("sla_hours") or 0)
                age_hours = float(row.get("age_hours") or 0)
            except (TypeError, ValueError):
                continue
            if sla_hours <= 0:
                continue
            consumed = age_hours / sla_hours
            if consumed >= sla_warning_ratio:
                enriched = dict(row)
                enriched["sla_consumed"] = consumed
                enriched["sla_breached"] = consumed >= 1
                agenda.sla_risk_tickets.append(enriched)

    # Mais atrasado / mais crítico primeiro.
    agenda.overdue_tasks.sort(key=lambda r: r.get("days_late", 0), reverse=True)
    agenda.stale_deals.sort(key=lambda r: r.get("days_idle") or 999, reverse=True)
    agenda.sla_risk_tickets.sort(key=lambda r: r.get("sla_consumed", 0), reverse=True)
    return agenda


# ---------------------------------------------------------------------------
# Busca global
# ---------------------------------------------------------------------------

def global_search(
    term: str,
    customers: pd.DataFrame | None = None,
    deals: pd.DataFrame | None = None,
    tickets: pd.DataFrame | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Busca única sobre clientes, oportunidades e chamados.

    Casa por prefixo/substring normalizada, então "eco" encontra
    "Ecoplus Engenharia" e a acentuação não atrapalha.
    """
    needle = _normalize_name(term)
    if not needle or len(needle) < 2:
        return []

    results: list[dict[str, Any]] = []

    def scan(df: pd.DataFrame | None, kind: str, id_col: str, label_cols: Sequence[str], section: str) -> None:
        if df is None or df.empty:
            return
        for row in df.to_dict("records"):
            haystacks = [str(row.get(col, "")) for col in label_cols]
            haystacks.append(str(row.get(id_col, "")))
            for text in haystacks:
                normalized = _normalize_name(text)
                if needle in normalized and normalized:
                    results.append({
                        "kind": kind,
                        "id": row.get(id_col),
                        "label": str(row.get(label_cols[0], row.get(id_col, ""))),
                        "detail": str(row.get(label_cols[-1], "")) if len(label_cols) > 1 else "",
                        "section": section,
                        # Casar no começo do texto é mais relevante que no meio.
                        "score": 0 if normalized.startswith(needle) else 1,
                    })
                    break

    scan(customers, "Cliente", "customer_id", ["name", "segment"], "Clientes 360")
    scan(deals, "Oportunidade", "deal_id", ["name", "stage"], "Funil Comercial")
    scan(tickets, "Chamado", "ticket_id", ["subject", "status"], "Atendimento")

    results.sort(key=lambda item: (item["score"], item["label"]))
    return results[:limit]


# ---------------------------------------------------------------------------
# Checklist de primeiros passos
# ---------------------------------------------------------------------------

def onboarding_steps(
    customers: pd.DataFrame | None,
    deals: pd.DataFrame | None,
    tickets: pd.DataFrame | None,
    templates_count: int = 0,
) -> list[dict[str, Any]]:
    """Passos de configuração inicial, com estado calculado a partir dos dados."""

    def has_rows(df: pd.DataFrame | None) -> bool:
        return df is not None and not df.empty

    return [
        {"key": "cliente", "label": "Cadastrar o primeiro cliente", "done": has_rows(customers), "section": "Clientes 360"},
        {"key": "oportunidade", "label": "Criar a primeira oportunidade", "done": has_rows(deals), "section": "Funil Comercial"},
        {"key": "atendimento", "label": "Registrar o primeiro atendimento", "done": has_rows(tickets), "section": "Atendimento"},
        {"key": "modelo", "label": "Salvar um modelo de mensagem", "done": templates_count > 0, "section": "Modelos de Mensagem"},
    ]


def onboarding_progress(steps: Sequence[dict[str, Any]]) -> tuple[int, int]:
    done = sum(1 for step in steps if step.get("done"))
    return done, len(steps)


# ===========================================================================
# Renderização (Streamlit)
# ===========================================================================

_HEALTH_STYLE = {
    # cor da borda, rótulo curto
    "parado": ("#ef4444", "🔴"),
    "atencao": ("#f59e0b", "🟡"),
    "ok": ("#22c55e", "🟢"),
    "fechado": ("#64748b", "⚪"),
}


def render_deal_card(deal: dict[str, Any], customer_name: str, health: DealHealth) -> None:
    """Card de oportunidade no funil.

    Segue a contenção do Pipedrive: cliente, título, valor e UM sinal de
    status. Cartão sobrecarregado deixa de ser escaneável.
    """
    import streamlit as st

    color, icon = _HEALTH_STYLE.get(health.status, _HEALTH_STYLE["ok"])
    probability = deal.get("probability", 0)

    st.markdown(
        f"""
        <div class='mini-card' style='border-left:3px solid {color};'>
            <div class='mini-label'>{customer_name}</div>
            <div class='mini-value' style='font-size:1.05rem;'>{deal.get('name','')}</div>
            <div class='mini-caption'>{format_brl(deal.get('value'))} · {probability}% · {deal.get('owner','')}</div>
            <div class='mini-caption' style='color:{color};'>{icon} {health.label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stage_header(summary: StageSummary) -> None:
    """Cabeçalho de coluna com contagem, valor total e valor ponderado."""
    import streamlit as st

    st.markdown(f"**{summary.stage}**")
    st.caption(summary.headline)
    if summary.count:
        caption = f"Ponderado: {format_compact_brl(summary.weighted_value)}"
        if summary.stale_count:
            caption += f" · 🔴 {summary.stale_count} parada(s)"
        st.caption(caption)


def render_pipeline_summary(totals: dict[str, float]) -> None:
    """Faixa de totais do funil aberto."""
    import streamlit as st

    columns = st.columns(4)
    columns[0].metric("Oportunidades abertas", int(totals["count"]))
    columns[1].metric("Valor em aberto", format_compact_brl(totals["total"]))
    columns[2].metric(
        "Previsão ponderada",
        format_compact_brl(totals["weighted"]),
        help="Soma de valor × probabilidade. É a projeção realista de receita, não o total bruto.",
    )
    columns[3].metric("Ticket médio", format_compact_brl(totals["average"]))


def render_day_agenda(agenda: DayAgenda, on_navigate=None) -> None:
    """Painel 'Meu Dia': o que precisa de ação agora."""
    import streamlit as st

    if agenda.is_empty:
        st.success("Nada pendente para hoje. Seu funil está em dia.")
        return

    columns = st.columns(4)
    columns[0].metric("Tarefas atrasadas", len(agenda.overdue_tasks))
    columns[1].metric("Tarefas de hoje", len(agenda.today_tasks))
    columns[2].metric("Negociações paradas", len(agenda.stale_deals))
    columns[3].metric("Chamados no limite do SLA", len(agenda.sla_risk_tickets))

    if agenda.overdue_tasks:
        st.markdown("#### 🔴 Atrasadas")
        for task in agenda.overdue_tasks:
            dias = task.get("days_late", 0)
            st.markdown(
                f"- **{task.get('task','')}** · venceu há {dias} dia(s) · {task.get('priority','')}"
            )

    if agenda.today_tasks:
        st.markdown("#### 📅 Para hoje")
        for task in agenda.today_tasks:
            st.markdown(f"- **{task.get('task','')}** · {task.get('priority','')}")

    if agenda.sla_risk_tickets:
        st.markdown("#### ⏱️ Atendimento no limite do SLA")
        for ticket in agenda.sla_risk_tickets:
            consumido = int(ticket.get("sla_consumed", 0) * 100)
            estado = "estourado" if ticket.get("sla_breached") else "próximo do limite"
            st.markdown(
                f"- **{ticket.get('subject','')}** · SLA {estado} ({consumido}% consumido)"
            )

    if agenda.stale_deals:
        st.markdown("#### 💤 Negociações sem contato")
        for deal in agenda.stale_deals:
            st.markdown(
                f"- **{deal.get('name','')}** · {format_brl(deal.get('value'))} · "
                f"{deal.get('stage','')} · {deal.get('health_label','')}"
            )

    if on_navigate:
        on_navigate()


def render_onboarding_checklist(steps: Sequence[dict[str, Any]]) -> None:
    """Checklist de primeiros passos — some quando tudo está concluído."""
    import streamlit as st

    done, total = onboarding_progress(steps)
    if done >= total:
        return

    with st.expander(f"🚀 Primeiros passos ({done}/{total})", expanded=done == 0):
        st.progress(done / total if total else 0.0)
        for step in steps:
            marca = "✅" if step["done"] else "⬜"
            st.markdown(f"{marca} {step['label']}")
        st.caption("O checklist desaparece sozinho quando todos os passos estiverem concluídos.")


def render_document_field(label: str, key: str, help_text: str | None = None) -> tuple[str, bool]:
    """Campo de CPF/CNPJ com validação de dígito verificador em tempo real.

    Devolve (valor digitado, é_válido) para o formulário decidir se permite salvar.
    """
    import streamlit as st

    raw = st.text_input(label, key=key, help=help_text, placeholder="00.000.000/0000-00")
    if not raw:
        return "", False

    valid, message = describe_document(raw)
    if valid:
        st.caption(f"✅ {message} — {format_cpf_cnpj(raw)}")
    else:
        st.caption(f"⚠️ {message}")
    return raw, valid


def render_duplicate_warning(matches: Sequence[dict[str, Any]]) -> None:
    """Alerta de possível duplicado antes de gravar o cadastro."""
    import streamlit as st

    if not matches:
        return

    st.warning(
        "Possível duplicado: "
        + "; ".join(
            f"**{m['name']}** ({', '.join(m['reasons'])})" for m in matches[:3]
        )
        + ". Confirme antes de criar um novo cadastro."
    )


def render_empty_module(title: str, explanation: str, action_label: str | None = None) -> None:
    """Estado vazio que ensina em vez de só informar que não há dados."""
    import streamlit as st

    st.markdown(
        f"""
        <div class='panel' style='text-align:center; padding:2.5rem 1.5rem;'>
            <div style='font-size:1.15rem; font-weight:600; margin-bottom:0.5rem;'>{title}</div>
            <div style='opacity:0.75; max-width:52ch; margin:0 auto;'>{explanation}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if action_label:
        st.caption(f"Próximo passo: {action_label}")


def render_global_search(results: Sequence[dict[str, Any]], on_select=None) -> None:
    """Resultados da busca global agrupados por tipo."""
    import streamlit as st

    if not results:
        st.caption("Nenhum resultado. Tente parte do nome do cliente, da oportunidade ou do chamado.")
        return

    for item in results:
        label = f"{item['kind']}: {item['label']}"
        if st.button(label, key=f"gs_{item['kind']}_{item['id']}", width="stretch"):
            if on_select:
                on_select(item)


# ---------------------------------------------------------------------------
# Campos obrigatórios por etapa (padrão RD Station / Ploomes / HubSpot)
#
# Exigir tudo no cadastro afasta o vendedor; não exigir nada produz funil sem
# informação. A saída dos líderes é o "portão de etapa": cada avanço cobra
# apenas o que aquela etapa pressupõe.
# ---------------------------------------------------------------------------

STAGE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "Proposta": ["value", "close_date"],
    "Negociacao": ["value", "close_date", "probability"],
    "Negociação": ["value", "close_date", "probability"],
    "Fechado ganho": ["value", "close_date", "owner"],
}

FIELD_LABELS = {
    "value": "Valor",
    "close_date": "Fechamento previsto",
    "probability": "Probabilidade",
    "owner": "Responsável",
    "name": "Nome da oportunidade",
    "customer_id": "Cliente",
}


def _is_blank(value: Any) -> bool:
    """Campo vazio para efeito de obrigatoriedade.

    Zero é ausência de informação num valor de negociação ou probabilidade —
    tratar como preenchido deixaria passar proposta de R$ 0.
    """
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (int, float)):
        return float(value) == 0.0
    return False


def missing_fields_for_stage(
    deal: dict[str, Any],
    stage: str,
    requirements: dict[str, list[str]] | None = None,
) -> list[str]:
    """Campos que faltam para a negociação entrar na etapa."""
    requirements = requirements or STAGE_REQUIRED_FIELDS
    required = requirements.get(stage, [])
    return [field_name for field_name in required if _is_blank(deal.get(field_name))]


def can_advance_to_stage(
    deal: dict[str, Any],
    stage: str,
    requirements: dict[str, list[str]] | None = None,
) -> tuple[bool, str]:
    """Autoriza (ou não) o avanço de etapa, com mensagem pronta para o usuário."""
    missing = missing_fields_for_stage(deal, stage, requirements)
    if not missing:
        return True, ""

    labels = [FIELD_LABELS.get(name, name) for name in missing]
    if len(labels) == 1:
        return False, f"Para mover para «{stage}», preencha: {labels[0]}."
    return False, f"Para mover para «{stage}», preencha: {', '.join(labels[:-1])} e {labels[-1]}."
