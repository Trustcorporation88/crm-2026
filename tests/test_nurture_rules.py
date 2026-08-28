"""Testes das jornadas automáticas de nutrição (Fase 2 do roadmap).

Regra que propõe matrícula duplicada vira ruído (mesmo cliente inscrito duas
vezes na mesma cadência) e regra que ignora quem realmente precisa de
acompanhamento deixa lead esfriar sem ninguém perceber. Os dois riscos estão
cobertos aqui, do jeito mais barato: lógica pura, sem banco.
"""

from datetime import date

import pandas as pd

from nurture_rules import RULES_CATALOG, evaluate_rules, summarize_proposals

HOJE = date(2026, 8, 28)

TITLES = {
    "new_lead_outbound": "Novo lead - 5 toques em 14d",
    "post_proposal": "Pos-proposta - 3 toques",
    "win_back": "Reativacao inativo",
}


class TestLeadNovoSemJornada:
    def test_lead_novo_sem_matricula_gera_proposta(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Alpha", "status": "Novo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, cadence_titles=TITLES, today=HOJE,
            enabled={"lead_novo_sem_jornada"},
        )
        assert len(propostas) == 1
        assert propostas[0].cadence_key == "new_lead_outbound"
        assert propostas[0].customer_id == "C1"
        assert propostas[0].owner == "Rafael"

    def test_lead_novo_ja_matriculado_nao_duplica(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Alpha", "status": "Novo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, cadence_titles=TITLES, today=HOJE,
            active_enrollments={("C1", "new_lead_outbound")},
            enabled={"lead_novo_sem_jornada"},
        )
        assert propostas == []

    def test_cliente_nao_novo_e_ignorado(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Alpha", "status": "Ativo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, cadence_titles=TITLES, today=HOJE,
            enabled={"lead_novo_sem_jornada"},
        )
        assert propostas == []


class TestPropostaSemAcompanhamento:
    def test_deal_em_proposta_sem_cadencia_gera_proposta(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "customer_id": "C1", "name": "Negocio X",
             "stage": "Proposta", "owner": "Amanda"},
        ])
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Beta", "status": "Ativo", "owner": "Amanda"},
        ])
        propostas = evaluate_rules(
            customers=customers, deals=deals, cadence_titles=TITLES, today=HOJE,
            enabled={"proposta_sem_acompanhamento"},
        )
        assert len(propostas) == 1
        assert propostas[0].cadence_key == "post_proposal"
        assert propostas[0].deal_id == "D-1"

    def test_deal_ja_com_cadencia_ativa_nao_duplica(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "customer_id": "C1", "name": "Negocio X",
             "stage": "Proposta", "owner": "Amanda"},
        ])
        propostas = evaluate_rules(
            deals=deals, cadence_titles=TITLES, today=HOJE,
            active_enrollments={("C1", "post_proposal")},
            enabled={"proposta_sem_acompanhamento"},
        )
        assert propostas == []

    def test_deal_fora_de_proposta_e_ignorado(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "customer_id": "C1", "name": "Negocio X",
             "stage": "Descoberta", "owner": "Amanda"},
        ])
        propostas = evaluate_rules(
            deals=deals, cadence_titles=TITLES, today=HOJE,
            enabled={"proposta_sem_acompanhamento"},
        )
        assert propostas == []


class TestClienteParado60Dias:
    def test_cliente_ativo_parado_60d_gera_proposta(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Gama", "status": "Ativo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, last_activity={"C1": "2026-06-01"}, cadence_titles=TITLES,
            today=HOJE, enabled={"cliente_parado_60d"},
        )
        assert len(propostas) == 1
        assert propostas[0].cadence_key == "win_back"

    def test_cliente_ativo_recente_nao_gera_proposta(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Gama", "status": "Ativo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, last_activity={"C1": "2026-08-20"}, cadence_titles=TITLES,
            today=HOJE, enabled={"cliente_parado_60d"},
        )
        assert propostas == []

    def test_cliente_ja_em_reativacao_nao_duplica(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Gama", "status": "Ativo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, last_activity={"C1": "2026-01-01"}, cadence_titles=TITLES,
            today=HOJE, active_enrollments={("C1", "win_back")},
            enabled={"cliente_parado_60d"},
        )
        assert propostas == []


class TestRegraDesligada:
    def test_regra_fora_do_enabled_nao_roda(self):
        customers = pd.DataFrame([
            {"customer_id": "C1", "name": "Alpha", "status": "Novo", "owner": "Rafael"},
        ])
        propostas = evaluate_rules(
            customers=customers, cadence_titles=TITLES, today=HOJE, enabled=set(),
        )
        assert propostas == []

    def test_catalogo_tem_as_tres_regras_documentadas(self):
        ids = {r["id"] for r in RULES_CATALOG}
        assert ids == {"lead_novo_sem_jornada", "proposta_sem_acompanhamento", "cliente_parado_60d"}


def test_summarize_proposals_conta_por_regra():
    customers = pd.DataFrame([
        {"customer_id": "C1", "name": "Alpha", "status": "Novo", "owner": "Rafael"},
        {"customer_id": "C2", "name": "Beta", "status": "Novo", "owner": "Amanda"},
    ])
    propostas = evaluate_rules(
        customers=customers, cadence_titles=TITLES, today=HOJE,
        enabled={"lead_novo_sem_jornada"},
    )
    resumo = summarize_proposals(propostas)
    assert resumo == {"lead_novo_sem_jornada": 2}
