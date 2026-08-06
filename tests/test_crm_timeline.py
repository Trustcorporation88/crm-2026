"""Testes da ficha do cliente orientada à linha do tempo."""

from datetime import date

import pandas as pd
import pytest

from crm_ux import (
    build_customer_timeline,
    group_timeline_by_day,
    next_best_action,
    relative_day_label,
)

HOJE = date(2026, 8, 6)


@pytest.fixture
def interactions():
    return pd.DataFrame([
        {"customer_id": "C-1", "event_at": "2026-08-06", "event_type": "call",
         "title": "Ligação de acompanhamento", "body": "Cliente pediu proposta revisada",
         "channel": "Telefone", "owner": "Camila"},
        {"customer_id": "C-1", "event_at": "2026-08-05", "event_type": "note",
         "title": "Nota interna", "body": "Decisor entra de férias em setembro",
         "channel": "", "owner": "Camila"},
        {"customer_id": "C-1", "event_at": "2026-08-06", "event_type": "email",
         "title": "Proposta enviada", "body": "v2 com desconto",
         "channel": "Email", "owner": "Camila"},
        {"customer_id": "C-2", "event_at": "2026-08-01", "event_type": "note",
         "title": "De outro cliente", "body": "", "channel": "", "owner": "Rafael"},
    ])


class TestConstrucaoDaLinhaDoTempo:
    def test_traz_apenas_o_cliente_pedido(self, interactions):
        entradas = build_customer_timeline(interactions, "C-1")
        assert len(entradas) == 3
        assert all("outro cliente" not in e.title for e in entradas)

    def test_ordena_do_mais_recente_para_o_mais_antigo(self, interactions):
        entradas = build_customer_timeline(interactions, "C-1")
        datas = [e.when for e in entradas]
        assert datas == sorted(datas, reverse=True)

    def test_respeita_o_limite(self, interactions):
        assert len(build_customer_timeline(interactions, "C-1", limit=2)) == 2

    def test_cliente_sem_interacao(self, interactions):
        assert build_customer_timeline(interactions, "C-999") == []

    def test_base_vazia(self):
        assert build_customer_timeline(pd.DataFrame(), "C-1") == []
        assert build_customer_timeline(None, "C-1") == []

    def test_registro_sem_data_vai_para_o_fim(self):
        # Registro incompleto não pode se passar pelo mais recente.
        df = pd.DataFrame([
            {"customer_id": "C-1", "event_at": "", "event_type": "note",
             "title": "Sem data", "body": "", "channel": "", "owner": ""},
            {"customer_id": "C-1", "event_at": "2026-01-01", "event_type": "note",
             "title": "Com data", "body": "", "channel": "", "owner": ""},
        ])
        entradas = build_customer_timeline(df, "C-1")
        assert entradas[0].title == "Com data"
        assert entradas[-1].title == "Sem data"

    def test_icone_prioriza_o_canal(self, interactions):
        entradas = build_customer_timeline(interactions, "C-1")
        por_titulo = {e.title: e.icon for e in entradas}
        assert por_titulo["Proposta enviada"] == "✉️"
        assert por_titulo["Ligação de acompanhamento"] == "📞"

    def test_icone_cai_para_o_tipo_quando_nao_ha_canal(self, interactions):
        entradas = build_customer_timeline(interactions, "C-1")
        nota = next(e for e in entradas if e.event_type == "note")
        assert nota.icon == "📝"


class TestRotuloDeDia:
    @pytest.mark.parametrize(
        "quando,esperado",
        [
            (date(2026, 8, 6), "Hoje"),
            (date(2026, 8, 5), "Ontem"),
            (date(2026, 8, 3), "Há 3 dias"),
            (date(2026, 6, 1), "01/06/2026"),
            (None, "Sem data"),
        ],
    )
    def test_rotulo_humano(self, quando, esperado):
        assert relative_day_label(quando, today=HOJE) == esperado


class TestAgrupamentoPorDia:
    def test_agrupa_eventos_do_mesmo_dia(self, interactions):
        grupos = group_timeline_by_day(build_customer_timeline(interactions, "C-1"), today=HOJE)

        rotulos = [rotulo for rotulo, _ in grupos]
        assert rotulos == ["Hoje", "Ontem"]
        assert len(grupos[0][1]) == 2, "os dois eventos de hoje devem ficar no mesmo grupo"

    def test_lista_vazia(self):
        assert group_timeline_by_day([]) == []


class TestProximaAcao:
    """A hierarquia da recomendação é o que evita virar ruído."""

    CLIENTE = {"customer_id": "C-1", "next_action": "Agendar revisão trimestral"}

    def test_sla_estourado_vence_tudo(self):
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "Portal fora do ar", "status": "Aberto",
             "sla_hours": 4, "age_hours": 30},
        ])
        deals = pd.DataFrame([
            {"deal_id": "D-1", "name": "Expansão", "stage": "Negociacao", "value": 500000},
        ])

        acao = next_best_action(self.CLIENTE, deals, tickets, last_activity=None, today=HOJE)

        assert acao.urgency == "critica"
        assert "Portal fora do ar" in acao.headline
        assert acao.is_urgent is True

    def test_ticket_resolvido_nao_gera_acao(self):
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "Antigo", "status": "Resolvido",
             "sla_hours": 4, "age_hours": 300},
        ])
        acao = next_best_action(self.CLIENTE, None, tickets, last_activity="2026-08-05", today=HOJE)
        assert acao.urgency == "normal"

    def test_negociacao_parada_de_maior_valor_vem_primeiro(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "name": "Pequena", "stage": "Negociacao", "value": 10000},
            {"deal_id": "D-2", "name": "Grande", "stage": "Negociacao", "value": 300000},
        ])
        # Silêncio de 60 dias deixa ambas paradas.
        acao = next_best_action(self.CLIENTE, deals, None, last_activity="2026-06-07", today=HOJE)

        assert acao.urgency == "alta"
        assert "Grande" in acao.headline
        assert "R$ 300.000" in acao.reason

    def test_conta_sem_interacao_pede_primeiro_contato(self):
        acao = next_best_action(self.CLIENTE, None, None, last_activity=None, today=HOJE)
        assert acao.urgency == "alta"
        assert "primeiro contato" in acao.headline.lower()

    def test_silencio_longo_sem_negociacao(self):
        acao = next_best_action(self.CLIENTE, None, None, last_activity="2026-06-01", today=HOJE)
        assert acao.urgency == "alta"
        assert "66 dias" in acao.reason

    def test_conta_saudavel_usa_o_plano_cadastrado(self):
        acao = next_best_action(self.CLIENTE, None, None, last_activity="2026-08-04", today=HOJE)
        assert acao.urgency == "normal"
        assert acao.headline == "Agendar revisão trimestral"
        assert acao.is_urgent is False

    def test_sem_plano_cadastrado_nao_inventa_acao(self):
        acao = next_best_action({"customer_id": "C-1"}, None, None,
                                last_activity="2026-08-04", today=HOJE)
        assert acao.headline == "Sem pendência"

    def test_negociacao_fechada_nao_conta_como_risco(self):
        deals = pd.DataFrame([
            {"deal_id": "D-1", "name": "Ganha", "stage": "Fechado ganho", "value": 900000},
        ])
        acao = next_best_action(self.CLIENTE, deals, None, last_activity="2026-08-04", today=HOJE)
        assert acao.urgency == "normal"

    def test_dado_sujo_nao_quebra(self):
        tickets = pd.DataFrame([
            {"ticket_id": "T-1", "subject": "X", "status": "Aberto",
             "sla_hours": "n/d", "age_hours": None},
        ])
        deals = pd.DataFrame([
            {"deal_id": "D-1", "name": "Y", "stage": "Proposta", "value": "muito"},
        ])
        acao = next_best_action(self.CLIENTE, deals, tickets, last_activity=None, today=HOJE)
        assert acao is not None
