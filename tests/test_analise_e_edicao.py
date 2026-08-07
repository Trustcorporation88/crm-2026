"""Testes da análise de perdas e da edição inline/ações em massa.

A análise de perdas transforma o motivo coletado no fechamento em decisão
gerencial («35% perdemos por preço»); a edição inline muda dados reais do
funil — cada regra aqui protege um número que o gestor vai usar.
"""

import pandas as pd
import pytest

import crm_backend
from crm_ux import loss_analysis

ADMIN = {"username": "admin", "role": "admin", "full_name": "Admin Teste"}
MARKETING = {"username": "marketing", "role": "marketing", "full_name": "Mkt Teste"}


class TestAnaliseDePerdas:
    def _deals(self):
        return pd.DataFrame(
            [
                {"deal_id": "D-1", "stage": "Fechado perdido", "value": 10_000,
                 "loss_reason": "Preço acima do orçamento"},
                {"deal_id": "D-2", "stage": "Fechado perdido", "value": 30_000,
                 "loss_reason": "Preço acima do orçamento — achou 20% mais barato"},
                {"deal_id": "D-3", "stage": "Fechado perdido", "value": 5_000,
                 "loss_reason": "concorrente Y ofereceu bundle"},  # texto livre => Outro
                {"deal_id": "D-4", "stage": "Fechado ganho", "value": 50_000, "loss_reason": ""},
                {"deal_id": "D-5", "stage": "Proposta", "value": 99_000, "loss_reason": ""},
            ]
        )

    def test_agrega_contagem_valor_e_taxa(self):
        resultado = loss_analysis(self._deals())
        assert resultado["lost_count"] == 3
        assert resultado["lost_value"] == 45_000
        assert resultado["won_count"] == 1
        # 3 perdidos / 4 fechados = 75%
        assert resultado["loss_rate"] == 75.0

    def test_motivo_com_detalhe_cai_no_balde_do_catalogo(self):
        # «Preço acima do orçamento — detalhe» conta junto com o motivo puro
        por_motivo = {i["reason"]: i for i in loss_analysis(self._deals())["by_reason"]}
        assert por_motivo["Preço acima do orçamento"]["count"] == 2
        assert por_motivo["Preço acima do orçamento"]["value"] == 40_000

    def test_texto_livre_vira_outro(self):
        por_motivo = {i["reason"]: i for i in loss_analysis(self._deals())["by_reason"]}
        assert por_motivo["Outro"]["count"] == 1

    def test_percentual_soma_as_perdas(self):
        resultado = loss_analysis(self._deals())
        assert sum(i["pct"] for i in resultado["by_reason"]) == pytest.approx(100.0, abs=0.5)

    def test_negocio_aberto_fica_de_fora(self):
        resultado = loss_analysis(self._deals())
        # D-5 (Proposta, R$ 99 mil) não entra em nada
        assert resultado["lost_value"] + resultado["won_value"] == 95_000

    def test_sem_dados_nao_quebra(self):
        assert loss_analysis(None)["lost_count"] == 0
        assert loss_analysis(pd.DataFrame())["by_reason"] == []


class TestEdicaoInline:
    @pytest.fixture()
    def deal(self):
        crm_backend.init_database()
        customer_id = str(crm_backend.get_data()["customers"].iloc[0]["customer_id"])
        deal_id = crm_backend.add_deal(
            {
                "customer_id": customer_id,
                "name": "Edição inline",
                "stage": "Proposta",
                "value": 20_000,
                "probability": 40,
                "owner": "Admin Teste",
                "close_date": "2026-11-01",
                "source": "Inbound",
            },
            actor=ADMIN,
            source="teste",
        )
        return deal_id

    def _row(self, deal_id):
        deals = crm_backend.get_data()["deals"]
        return deals.loc[deals["deal_id"] == deal_id].iloc[0]

    def test_edita_varios_campos_de_uma_vez(self, deal):
        aplicados = crm_backend.update_deal_fields(
            deal,
            {"value": 25_000, "probability": 60, "owner": "Camila Costa", "close_date": "2026-12-15"},
            actor=ADMIN,
            source="teste",
        )
        assert set(aplicados) == {"value", "probability", "owner", "close_date"}
        row = self._row(deal)
        assert float(row["value"]) == 25_000
        assert int(row["probability"]) == 60
        assert row["owner"] == "Camila Costa"
        assert row["close_date"] == "2026-12-15"

    def test_valores_iguais_sao_no_op(self, deal):
        assert crm_backend.update_deal_fields(deal, {"value": 20_000}, actor=ADMIN) == {}

    def test_campo_fora_da_whitelist_e_ignorado(self, deal):
        # etapa não muda por edição inline: passa pelo kanban/fechamento
        aplicados = crm_backend.update_deal_fields(
            deal, {"stage": "Fechado ganho", "loss_reason": "x"}, actor=ADMIN
        )
        assert aplicados == {}
        assert self._row(deal)["stage"] == "Proposta"

    def test_probabilidade_fora_da_faixa_e_recusada(self, deal):
        with pytest.raises(ValueError, match="0 e 100"):
            crm_backend.update_deal_fields(deal, {"probability": 150}, actor=ADMIN)

    def test_valor_negativo_e_recusado(self, deal):
        with pytest.raises(ValueError, match="negativo"):
            crm_backend.update_deal_fields(deal, {"value": -1}, actor=ADMIN)

    def test_auditoria_guarda_antes_e_depois(self, deal):
        crm_backend.update_deal_fields(deal, {"value": 32_000}, actor=ADMIN, source="teste")
        auditoria = crm_backend.get_data()["audit_log"]
        eventos = auditoria[(auditoria["action"] == "deal.update") & (auditoria["entity_id"] == deal)]
        assert len(eventos) >= 1
        assert "32000" in str(eventos.iloc[-1]["payload_json"])

    def test_perfil_sem_permissao_nao_edita(self, deal):
        with pytest.raises(PermissionError):
            crm_backend.update_deal_fields(deal, {"value": 1}, actor=MARKETING)

    def test_negocio_inexistente_da_erro_claro(self):
        crm_backend.init_database()
        with pytest.raises(ValueError, match="não encontrada"):
            crm_backend.update_deal_fields("D-999999", {"value": 1}, actor=ADMIN)
