"""A vitrine pública (democrm.trustcorp.com.br) e as travas que a cercam.

A demonstração roda o MESMO código da produção, com a mesma marca e num
endereço de terceiro nível quase igual. Dois acidentes ficam possíveis, e os
dois são caros:

1. **A carga apagar a base real.** O primeiro passo da carga é `DELETE` nas
   tabelas de cliente, negócio e chamado. Se ela rodar apontada para o
   Supabase, apaga a operação — numa base sem rotina de backup própria.
2. **Alguém confundir os dois ambientes.** Um vendedor trabalhando horas dentro
   da vitrine achando que é o CRM; um cliente em prospecção achando que está
   vendo dados de clientes reais da Trust.

Estes testes travam as duas coisas. O primeiro grupo é o que importa: a
verificação de que a produção está protegida vale mais que todo o resto do
arquivo somado.
"""

import importlib
import sys

import pytest

import demo_meishop


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CRM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CRM_DB_PATH", str(tmp_path / "demo.sqlite3"))
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "senha-de-teste-2026")
    sys.modules.pop("crm_backend", None)
    modulo = importlib.import_module("crm_backend")
    modulo.init_database()
    return modulo


class TestProducaoNaoPodeSerTocada:
    """A trava mais importante do arquivo."""

    def test_recusa_quando_ha_banco_de_producao_configurado(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@aws.pooler.supabase.com:5432/postgres")

        with pytest.raises(demo_meishop.ProducaoProtegida):
            demo_meishop._proteger_producao()

    def test_o_arranque_desiste_em_silencio_em_vez_de_apagar(self, monkeypatch):
        """Com as duas variáveis ligadas ao mesmo tempo, ninguém escreve nada.

        É o acidente concreto: alguém liga CRM_DEMO_DATASET no serviço de
        produção. A carga não pode rodar, e a tela também não pode quebrar.
        """
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
        monkeypatch.setenv("CRM_DEMO_DATASET", "meishop")

        chamou = []
        monkeypatch.setattr(demo_meishop, "_popular", lambda: chamou.append(1))

        assert demo_meishop.preparar_demonstracao_no_arranque() is False
        assert not chamou, "a carga rodou apesar de haver banco de produção"

    def test_a_carga_realmente_apaga_o_que_encontra(self, backend, monkeypatch):
        """Prova que a trava protege de algo real, e não de um susto.

        Sem este teste, os anteriores só demonstram que uma função levanta
        exceção. É este que mostra o tamanho do estrago evitado.
        """
        monkeypatch.setenv("CRM_DEMO_DATASET", "meishop")
        antes = len(backend.get_data()["customers"])
        assert antes > 0, "o seed deveria ter criado clientes de exemplo"

        demo_meishop._popular()

        nomes = set(backend.get_data()["customers"]["name"])
        assert not any("Northwind" in nome for nome in nomes), (
            "os clientes do seed original sobreviveram à carga"
        )


class TestSoLigaComAVariavelCerta:
    def test_desligado_por_padrao(self, monkeypatch):
        monkeypatch.delenv("CRM_DEMO_DATASET", raising=False)
        assert demo_meishop.modo_demonstracao() is False

    @pytest.mark.parametrize("valor", ["meishop", "MEISHOP", " meishop "])
    def test_liga_com_o_nome_do_conjunto(self, monkeypatch, valor):
        monkeypatch.setenv("CRM_DEMO_DATASET", valor)
        assert demo_meishop.modo_demonstracao() is True

    @pytest.mark.parametrize("valor", ["", "true", "1", "sim", "demo", "outro"])
    def test_nao_liga_com_qualquer_valor(self, monkeypatch, valor):
        """`true` não serve de propósito: a variável nomeia um conjunto de dados.

        Se um dia houver um segundo conjunto, o nome já distingue — e um `true`
        herdado de outra configuração não liga a vitrine por acidente.
        """
        monkeypatch.setenv("CRM_DEMO_DATASET", valor)
        assert demo_meishop.modo_demonstracao() is False


class TestCargaAcontecaUmaVezPorDeploy:
    def test_carrega_no_primeiro_arranque(self, backend, monkeypatch):
        """O gatilho é uma marca própria, não a tabela de clientes vazia.

        A primeira versão testava "vazio" e passava, porque o teste apagava a
        tabela antes. Em produção nunca ficava vazia — `init_database` semeia
        clientes de exemplo — e a vitrine subia mostrando "Ecoplus Engenharia"
        e "Grupo Aurora", justamente os dados que ela existe para substituir.

        Este teste não apaga nada: começa do estado real de um contêiner novo,
        com o seed já aplicado.
        """
        monkeypatch.setenv("CRM_DEMO_DATASET", "meishop")

        assert demo_meishop.ja_carregada() is False
        assert demo_meishop.preparar_demonstracao_no_arranque() is True
        assert demo_meishop.ja_carregada() is True

        nomes = set(backend.get_data()["customers"]["name"])
        assert any("Bella Hair" in nome for nome in nomes), (
            "a vitrine subiu sem os dados da MEiSHOP"
        )
        assert not any("Ecoplus" in nome or "Aurora" in nome for nome in nomes), (
            "os dados genéricos do seed sobreviveram — é o defeito que este "
            "teste existe para travar"
        )

    def test_nao_recarrega_a_cada_sessao(self, backend, monkeypatch):
        """O Streamlit executa o script a cada visitante que conecta.

        Sem a verificação de banco vazio, cada nova aba de cada visitante
        apagaria e recriaria a base — inclusive no meio de uma apresentação.
        """
        monkeypatch.setenv("CRM_DEMO_DATASET", "meishop")
        demo_meishop.preparar_demonstracao_no_arranque()

        chamou = []
        monkeypatch.setattr(demo_meishop, "_popular", lambda: chamou.append(1))

        assert demo_meishop.preparar_demonstracao_no_arranque() is False
        assert not chamou, "recarregou a demonstração com o banco já populado"


class TestDadosDaVitrine:
    """A vitrine tem de mostrar a operação da MEiSHOP, não a de exemplo."""

    def test_a_operacao_carregada_e_coerente(self, backend, monkeypatch):
        monkeypatch.setenv("CRM_DEMO_DATASET", "meishop")
        total = demo_meishop._popular()
        dados = backend.get_data()

        assert len(dados["customers"]) == total["contas"]
        assert len(dados["deals"]) == total["negocios"]
        assert len(dados["tickets"]) == total["chamados"]

    def test_todo_registro_tem_dono_com_conta(self, backend, monkeypatch):
        """Dono sem conta fica invisível para quem não é admin.

        A vitrine é apresentada; um registro que não aparece na tela de um
        vendedor estraga a demonstração na frente do cliente.
        """
        monkeypatch.setenv("CRM_DEMO_DATASET", "meishop")
        demo_meishop._popular()

        with backend._connect() as conexao:
            contas = {
                linha["username"]
                for linha in conexao.execute("SELECT username FROM users").fetchall()
            }
            orfaos = []
            for tabela in ("customers", "tickets", "deals", "tasks"):
                for linha in conexao.execute(f"SELECT owner_username FROM {tabela}").fetchall():
                    dono = (linha["owner_username"] or "").strip()
                    if dono not in contas:
                        orfaos.append((tabela, dono))

        assert not orfaos, f"registros da vitrine sem conta de dono: {sorted(set(orfaos))}"

    def test_as_etapas_do_funil_sao_as_que_a_tela_reconhece(self):
        """O funil filtra por lista fechada; etapa fora dela some da tela.

        Foi o que aconteceu ao montar esta carga: um negócio de R$ 196 mil
        gravou sem erro com a etapa "Prospeccao" e desapareceu do kanban e do
        resumo, enquanto outra métrica do produto continuava contando.

        O defeito do produto segue em aberto — nada valida `stage` na escrita.
        Este teste apenas garante que a vitrine não o exibe.
        """
        from pathlib import Path

        fonte = (Path(__file__).resolve().parent.parent / "crm_app.py").read_text(encoding="utf-8")
        trecho = fonte.split("ordered_stages = [", 1)[1].split("]", 1)[0]
        reconhecidas = {p.strip().strip('"').strip("'") for p in trecho.split(",") if p.strip()}

        usadas = {negocio["stage"] for negocio in demo_meishop.NEGOCIOS}
        assert usadas <= reconhecidas, (
            f"a vitrine usa etapas que a tela não desenha: {sorted(usadas - reconhecidas)}"
        )


class TestAvisoNaTela:
    """Vitrine sem aviso é indistinguível do sistema real."""

    def _fonte_do_app(self) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent / "crm_app.py").read_text(encoding="utf-8")

    def test_a_faixa_aparece_na_tela_de_login(self):
        fonte = self._fonte_do_app()
        login = fonte.split("def show_login()", 1)[1].split("\ndef ", 1)[0]
        assert "faixa_de_demonstracao()" in login, (
            "a tela de login não avisa que é demonstração — é a primeira tela "
            "que um cliente em prospecção vê"
        )

    def test_a_faixa_aparece_tambem_depois_de_entrar(self):
        fonte = self._fonte_do_app()
        depois = fonte.split("render_top_bar(section)", 1)[1]
        assert "faixa_de_demonstracao()" in depois

    def test_a_faixa_cala_a_boca_fora_do_modo_demonstracao(self, monkeypatch):
        monkeypatch.delenv("CRM_DEMO_DATASET", raising=False)
        assert demo_meishop.modo_demonstracao() is False


class TestDocumentacao:
    def test_o_guia_do_deploy_explica_a_vitrine(self):
        from pathlib import Path

        guia = (
            Path(__file__).resolve().parent.parent / "docs" / "DEPLOY-RAILWAY.md"
        ).read_text(encoding="utf-8")

        assert "CRM_DEMO_DATASET" in guia
        assert "democrm" in guia, "o guia não diz qual é o endereço da vitrine"
        assert "DATABASE_URL" in guia
