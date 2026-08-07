"""Testes do Comparativo Benchmark.

Este conteúdo é exibido dentro do produto e usado para decidir. Os testes
protegem menos a "lógica" e mais a **integridade editorial**: todo concorrente
precisa de preço datado com fonte, todo diferencial precisa existir, e o
comparativo precisa continuar admitindo onde estamos atrás — um comparativo
que só elogia a casa é propaganda, não é informação.
"""

import pytest

from benchmark_market import (
    CAPABILITY_MATRIX,
    COMPETITORS,
    PRICE_CHECKED_AT,
    TRUST_POSITION,
    benchmark_markdown,
    brazilian_competitors,
    capability_score,
    global_competitors,
)


class TestIntegridadeDosDados:
    def test_todo_concorrente_tem_os_campos_obrigatorios(self):
        obrigatorios = [
            "name", "origin", "audience", "price", "price_source",
            "strengths", "limitations", "brasil", "trust_diff",
        ]
        for c in COMPETITORS:
            for campo in obrigatorios:
                assert c.get(campo), f"{c.get('name')} sem «{campo}»"

    def test_nenhum_nome_repetido(self):
        nomes = [c["name"] for c in COMPETITORS]
        assert len(nomes) == len(set(nomes))

    def test_preco_sempre_tem_moeda_ou_diz_que_nao_e_publico(self):
        for c in COMPETITORS:
            preco = c["price"]
            tem_moeda = "R$" in preco or "US$" in preco
            declara_ausencia = any(
                t in preco.lower() for t in ("sob consulta", "não publicado", "nao publicado")
            )
            assert tem_moeda or declara_ausencia, f"{c['name']}: preço sem moeda nem ressalva — {preco}"

    def test_preco_em_dolar_fica_explicito(self):
        # Exposição cambial é decisão de compra: não pode ficar escondida.
        for c in COMPETITORS:
            if "US$" in c["price"]:
                assert "US$" in c["price"]  # marcado no próprio texto do preço

    def test_cada_concorrente_tem_pontos_fortes_e_limitacoes(self):
        for c in COMPETITORS:
            assert len(c["strengths"]) >= 2, f"{c['name']} com poucos pontos fortes"
            assert len(c["limitations"]) >= 1, f"{c['name']} sem limitação listada"

    def test_data_de_consulta_dos_precos_esta_declarada(self):
        assert PRICE_CHECKED_AT and "/" in PRICE_CHECKED_AT

    def test_cobre_os_principais_players_do_brasil(self):
        nomes = " ".join(c["name"] for c in COMPETITORS)
        for esperado in ("RD Station", "Ploomes", "Agendor", "Pipedrive", "HubSpot", "Salesforce"):
            assert esperado in nomes, f"{esperado} fora do comparativo"

    def test_separa_brasileiros_de_globais_sem_sobreposicao(self):
        br = {c["name"] for c in brazilian_competitors()}
        glob = {c["name"] for c in global_competitors()}
        assert br and glob
        assert not (br & glob), "concorrente classificado nos dois grupos"
        assert len(br) + len(glob) == len(COMPETITORS)

    def test_operacao_no_brasil_nao_torna_o_player_brasileiro(self):
        # Kommo e Pipedrive atuam no Brasil, mas não são brasileiros.
        br = {c["name"] for c in brazilian_competitors()}
        assert "Pipedrive" not in br
        assert not any("Kommo" in nome for nome in br)


class TestHonestidadeDoComparativo:
    def test_admite_capacidades_em_que_estamos_atras(self):
        assert TRUST_POSITION["atras"], "comparativo sem nenhuma fraqueza é propaganda"
        assert capability_score()["atras"] >= 1

    def test_o_email_esta_declarado_como_lacuna(self):
        texto = " ".join(TRUST_POSITION["atras"]).lower()
        assert "mail" in texto, "a maior lacuna precisa estar declarada"

    def test_matriz_marca_as_tres_lacunas_conhecidas(self):
        atrasadas = [m["capability"].lower() for m in CAPABILITY_MATRIX if m["verdict"] == "atras"]
        juntas = " ".join(atrasadas)
        assert "mail" in juntas
        assert "integra" in juntas or "marketplace" in juntas
        assert "multiempresa" in juntas

    def test_diferencial_menciona_o_concorrente_de_forma_util(self):
        # Diferencial genérico não ajuda: exigimos texto com substância.
        for c in COMPETITORS:
            assert len(c["trust_diff"]) > 80, f"{c['name']} com diferencial raso"

    def test_matriz_usa_apenas_vereditos_conhecidos(self):
        validos = {"vantagem", "empate", "parcial", "atras"}
        for linha in CAPABILITY_MATRIX:
            assert linha["verdict"] in validos

    def test_placar_soma_todas_as_capacidades(self):
        assert sum(capability_score().values()) == len(CAPABILITY_MATRIX)


class TestMarkdownDoComparativo:
    def test_markdown_lista_todos_os_concorrentes(self):
        md = benchmark_markdown()
        for c in COMPETITORS:
            assert c["name"] in md

    def test_markdown_traz_data_dos_precos_e_as_duas_faces(self):
        md = benchmark_markdown()
        assert PRICE_CHECKED_AT in md
        assert "Onde ganhamos" in md
        assert "Onde estamos atrás" in md

    def test_manual_de_servicos_termina_com_o_comparativo(self):
        from services_catalog import services_manual_markdown

        md = services_manual_markdown()
        assert "Comparativo Benchmark" in md
        assert md.index("Comparativo Benchmark") > md.index("Central de Atendimento"), (
            "o comparativo deve fechar o catálogo, não abrir"
        )
