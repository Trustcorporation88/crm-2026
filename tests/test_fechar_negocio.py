"""Testes das ações rápidas Ganho/Perdido no funil (padrão Pipedrive).

Fechar um negócio é irreversível na prática (grava desfecho, motivo e data),
então cada regra aqui protege um dado que a equipe vai analisar depois: por que
ganhamos, por que perdemos, e quando.
"""

import pytest

import crm_backend
from crm_ux import (
    LOSS_REASONS,
    deal_closing_label,
    open_deals_for_closing,
)

ADMIN = {"username": "admin", "role": "admin", "full_name": "Admin Teste"}
MARKETING = {"username": "marketing", "role": "marketing", "full_name": "Mkt Teste"}


class TestHelpersPuros:
    def test_so_negocios_abertos_podem_fechar(self):
        deals = [
            {"deal_id": "D-1", "stage": "Proposta"},
            {"deal_id": "D-2", "stage": "Fechado ganho"},
            {"deal_id": "D-3", "stage": "Fechado perdido"},
            {"deal_id": "D-4", "stage": "Descoberta"},
        ]
        abertos = {d["deal_id"] for d in open_deals_for_closing(deals)}
        assert abertos == {"D-1", "D-4"}  # os já fechados ficam de fora

    def test_rotulo_de_fechamento_traz_cliente_e_valor(self):
        deal = {"deal_id": "D-9", "name": "Expansão", "value": 104_000}
        rotulo = deal_closing_label(deal, "Clina Prime")
        assert "D-9" in rotulo and "Clina Prime" in rotulo
        assert "Expansão" in rotulo and "R$ 104 mil" in rotulo

    def test_catalogo_de_motivos_tem_outro_para_texto_livre(self):
        assert "Outro" in LOSS_REASONS
        assert len(LOSS_REASONS) >= 5


class TestFecharNoBanco:
    @pytest.fixture()
    def deal_aberto(self):
        crm_backend.init_database()
        customer_id = str(crm_backend.get_data()["customers"].iloc[0]["customer_id"])
        deal_id = crm_backend.add_deal(
            {
                "customer_id": customer_id,
                "name": "Negócio de teste",
                "stage": "Proposta",
                "value": 40_000,
                "probability": 50,
                "owner": "Admin Teste",
                "close_date": "2026-12-01",
                "source": "Inbound",
            },
            actor=ADMIN,
            source="teste",
        )
        return deal_id, customer_id

    def _deal(self, deal_id):
        deals = crm_backend.get_data()["deals"]
        return deals.loc[deals["deal_id"] == deal_id].iloc[0]

    def test_ganho_move_para_fechado_e_crava_100(self, deal_aberto):
        deal_id, _ = deal_aberto
        crm_backend.close_deal(deal_id, "ganho", actor=ADMIN, source="teste")
        row = self._deal(deal_id)
        assert row["stage"] == "Fechado ganho"
        assert int(row["probability"]) == 100
        assert str(row["loss_reason"]) == ""      # ganho não tem motivo de perda
        assert str(row["closed_at"]) != ""        # data de fechamento gravada

    def test_perdido_grava_motivo_e_zera_probabilidade(self, deal_aberto):
        deal_id, _ = deal_aberto
        crm_backend.close_deal(
            deal_id, "perdido", reason="Escolheu concorrente", actor=ADMIN, source="teste"
        )
        row = self._deal(deal_id)
        assert row["stage"] == "Fechado perdido"
        assert int(row["probability"]) == 0
        assert str(row["loss_reason"]) == "Escolheu concorrente"
        assert str(row["closed_at"]) != ""

    def test_perdido_sem_motivo_e_recusado(self, deal_aberto):
        deal_id, _ = deal_aberto
        with pytest.raises(ValueError, match="motivo"):
            crm_backend.close_deal(deal_id, "perdido", reason="   ", actor=ADMIN)
        # e o negócio continua aberto — nada foi gravado pela metade
        assert self._deal(deal_id)["stage"] == "Proposta"

    def test_desfecho_invalido_e_recusado(self, deal_aberto):
        deal_id, _ = deal_aberto
        with pytest.raises(ValueError, match="ganho.*perdido|perdido.*ganho"):
            crm_backend.close_deal(deal_id, "cancelado", actor=ADMIN)

    def test_fechar_registra_auditoria_e_linha_do_tempo(self, deal_aberto):
        deal_id, customer_id = deal_aberto
        crm_backend.close_deal(
            deal_id, "perdido", reason="Preço acima do orçamento", actor=ADMIN, source="teste"
        )
        data = crm_backend.get_data()

        eventos = data["interactions"]
        do_cliente = eventos[eventos["customer_id"] == customer_id]
        assert any("PERDIDA" in str(b) and "Preço acima" in str(b) for b in do_cliente["body"]), (
            "o desfecho e o motivo precisam aparecer na linha do tempo do cliente"
        )

        auditoria = data["audit_log"]
        fechamentos = auditoria[auditoria["action"] == "deal.closed"]
        assert len(fechamentos) >= 1

    def test_perfil_sem_permissao_nao_fecha(self, deal_aberto):
        deal_id, _ = deal_aberto
        with pytest.raises(PermissionError):
            crm_backend.close_deal(deal_id, "ganho", actor=MARKETING)
        assert self._deal(deal_id)["stage"] == "Proposta"

    def test_negocio_inexistente_da_erro_claro(self):
        crm_backend.init_database()
        with pytest.raises(ValueError, match="não encontrada"):
            crm_backend.close_deal("D-999999", "ganho", actor=ADMIN)
