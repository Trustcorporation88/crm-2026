"""Testes do funil kanban: montagem do board, diff do drag e mudança de etapa.

O drag-and-drop em si roda no navegador (streamlit-sortables); o que dá para
provar em teste é a parte que decide: como o board é montado, como uma soltura
vira (deal, de, para) e como o backend grava a mudança com trilha completa.
"""

import pandas as pd
import pytest

import crm_backend
from crm_ux import (
    build_kanban_containers,
    diff_kanban,
    kanban_deal_label,
)

ETAPAS = ["Descoberta", "Proposta", "Negociacao", "Fechado ganho"]

ADMIN = {"username": "admin", "role": "admin", "full_name": "Admin Teste"}
MARKETING = {"username": "marketing", "role": "marketing", "full_name": "Mkt Teste"}


def _deals():
    return [
        {"deal_id": "D-1", "customer_id": "C1", "name": "Alpha", "stage": "Descoberta", "value": 10_000},
        {"deal_id": "D-2", "customer_id": "C2", "name": "Beta", "stage": "Proposta", "value": 68_000},
        {"deal_id": "D-3", "customer_id": "C1", "name": "Gama", "stage": "Proposta", "value": 2_000},
    ]


NOMES = {"C1": "Ecoplus", "C2": "Northwind"}


class TestMontagemDoBoard:
    def test_containers_seguem_a_ordem_das_etapas(self):
        containers, header_etapa, _ = build_kanban_containers(_deals(), NOMES, ETAPAS)
        assert [header_etapa[c["header"]] for c in containers] == ETAPAS

    def test_cabecalho_carrega_contagem_e_valor(self):
        containers, _, _ = build_kanban_containers(_deals(), NOMES, ETAPAS)
        proposta = containers[1]
        assert "Proposta" in proposta["header"]
        assert "2" in proposta["header"]           # duas oportunidades
        assert "R$ 70 mil" in proposta["header"]   # 68k + 2k

    def test_rotulo_mapeia_de_volta_para_o_deal(self):
        containers, _, rotulo_deal = build_kanban_containers(_deals(), NOMES, ETAPAS)
        rotulos = [r for c in containers for r in c["items"]]
        assert len(rotulos) == 3
        assert sorted(rotulo_deal[r] for r in rotulos) == ["D-1", "D-2", "D-3"]

    def test_negociacao_parada_ganha_marca_vermelha(self):
        containers, _, _ = build_kanban_containers(
            _deals(), NOMES, ETAPAS, stale_ids={"D-2"}
        )
        rotulos = [r for c in containers for r in c["items"]]
        marcados = [r for r in rotulos if r.startswith("🔴")]
        assert len(marcados) == 1 and "D-2" in marcados[0]

    def test_etapa_desconhecida_nao_quebra_o_board(self):
        deals = _deals() + [
            {"deal_id": "D-9", "customer_id": "C1", "name": "Zeta", "stage": "Inexistente", "value": 1}
        ]
        containers, _, rotulo_deal = build_kanban_containers(deals, NOMES, ETAPAS)
        assert len(rotulo_deal) == 3  # D-9 fica de fora, sem exceção

    def test_rotulo_usa_valor_compacto(self):
        deal = {"deal_id": "D-2", "value": 68_000}
        assert kanban_deal_label(deal, "Northwind") == "D-2 · Northwind — R$ 68 mil"


class TestDiffDoDrag:
    def _board(self, stale=None):
        return build_kanban_containers(_deals(), NOMES, ETAPAS, stale_ids=stale)

    def test_sem_mudanca_nao_ha_movimento(self):
        containers, header_etapa, rotulo_deal = self._board()
        assert diff_kanban(containers, containers, header_etapa, rotulo_deal) == []

    def test_mover_entre_colunas_e_detectado(self):
        containers, header_etapa, rotulo_deal = self._board()
        depois = [dict(c, items=list(c["items"])) for c in containers]
        movido = depois[0]["items"].pop(0)      # D-1 sai de Descoberta
        depois[2]["items"].append(movido)       # e cai em Negociacao
        moves = diff_kanban(containers, depois, header_etapa, rotulo_deal)
        assert moves == [("D-1", "Descoberta", "Negociacao")]

    def test_reordenar_dentro_da_coluna_nao_e_movimento(self):
        containers, header_etapa, rotulo_deal = self._board()
        depois = [dict(c, items=list(c["items"])) for c in containers]
        depois[1]["items"].reverse()  # troca a ordem em Proposta
        assert diff_kanban(containers, depois, header_etapa, rotulo_deal) == []

    def test_retorno_invalido_do_componente_e_ignorado(self):
        containers, header_etapa, rotulo_deal = self._board()
        for invalido in (None, [], "x", 42, [{"sem_header": True}]):
            assert diff_kanban(containers, invalido, header_etapa, rotulo_deal) == []


class TestMudancaDeEtapaNoBanco:
    @pytest.fixture()
    def deal_novo(self):
        crm_backend.init_database()
        customers = crm_backend.get_data()["customers"]
        customer_id = str(customers.iloc[0]["customer_id"])
        deal_id = crm_backend.add_deal(
            {
                "customer_id": customer_id,
                "name": "Kanban de teste",
                "stage": "Descoberta",
                "value": 5_000,
                "probability": 30,
                "owner": "Admin Teste",
                "close_date": "2026-12-01",
                "source": "Outbound",
            },
            actor=ADMIN,
            source="teste-kanban",
        )
        return deal_id, customer_id

    def _stage_de(self, deal_id):
        deals = crm_backend.get_data()["deals"]
        return str(deals.loc[deals["deal_id"] == deal_id, "stage"].iloc[0])

    def test_mover_grava_etapa_auditoria_e_linha_do_tempo(self, deal_novo):
        deal_id, customer_id = deal_novo
        crm_backend.update_deal_stage(deal_id, "Proposta", actor=ADMIN, source="teste-kanban")

        assert self._stage_de(deal_id) == "Proposta"

        data = crm_backend.get_data()
        eventos = data["interactions"]
        do_deal = eventos[eventos["customer_id"] == customer_id]
        assert any("movida de Descoberta para Proposta" in str(s) for s in do_deal["body"]), (
            "a mudança de etapa precisa aparecer na linha do tempo do cliente"
        )

    def test_mover_para_a_mesma_etapa_e_no_op(self, deal_novo):
        deal_id, _ = deal_novo
        crm_backend.update_deal_stage(deal_id, "Descoberta", actor=ADMIN)
        assert self._stage_de(deal_id) == "Descoberta"

    def test_oportunidade_inexistente_da_erro_claro(self):
        crm_backend.init_database()
        with pytest.raises(ValueError, match="não encontrada"):
            crm_backend.update_deal_stage("D-999999", "Proposta", actor=ADMIN)

    def test_perfil_sem_permissao_nao_move(self, deal_novo):
        deal_id, _ = deal_novo
        with pytest.raises(PermissionError):
            crm_backend.update_deal_stage(deal_id, "Proposta", actor=MARKETING)
        assert self._stage_de(deal_id) == "Descoberta"
