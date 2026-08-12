"""Regressões do Bloco D: código não integrado e documentação.

O problema que estes testes travam não é de execução — é de confiança. Cerca de
vinte documentos na raiz descreviam como concluídas funcionalidades que nunca
foram ligadas ao produto, e três módulos ficavam ao lado do código em uso sem
serem importados por ninguém. Quem lia a documentação concluía que o CRM tinha
SSO, tradução e reenvio de webhook; nenhuma das três acontece em execução.

Documentação errada não quebra teste, então precisa de teste próprio.
"""

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
NAO_INTEGRADOS = ("sso_auth", "i18n", "webhook_utils")


def _modulos_python_ativos() -> list[Path]:
    """Arquivos .py que fazem parte do produto (fora de testes e não integrados)."""
    ativos = []
    for caminho in RAIZ.rglob("*.py"):
        partes = set(caminho.relative_to(RAIZ).parts)
        if partes & {"tests", "nao_integrado", ".venv", "__pycache__", "docs"}:
            continue
        ativos.append(caminho)
    return ativos


def _imports_de(caminho: Path) -> set[str]:
    try:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module.split(".")[0])
    return nomes


class TestCodigoNaoIntegrado:
    def test_modulos_orfaos_saíram_da_raiz(self):
        for nome in NAO_INTEGRADOS:
            assert not (RAIZ / f"{nome}.py").exists(), (
                f"{nome}.py voltou para a raiz, ao lado do código em uso"
            )
            assert (RAIZ / "nao_integrado" / f"{nome}.py").exists()

    def test_continuam_sem_ser_importados(self):
        """Se algum for integrado, precisa sair do diretório — e ser revisado.

        No caso do sso_auth isso é especialmente importante: ele não valida o
        parâmetro `state` do OAuth nem a assinatura do id_token. Hoje é
        inofensivo porque ninguém o importa.
        """
        for caminho in _modulos_python_ativos():
            importados = _imports_de(caminho)
            for nome in NAO_INTEGRADOS:
                assert nome not in importados, (
                    f"{caminho.name} importa {nome}, que está em nao_integrado/. "
                    f"Se foi integrado de verdade, mova o arquivo e revise os "
                    f"avisos de nao_integrado/README.md antes."
                )

    def test_diretorio_tem_readme_com_os_avisos(self):
        readme = RAIZ / "nao_integrado" / "README.md"
        assert readme.exists()

        conteudo = readme.read_text(encoding="utf-8")
        # O aviso de segurança do SSO é o motivo principal deste README existir.
        assert "state" in conteudo and "id_token" in conteudo

    def test_cache_utils_permanece_na_raiz(self):
        """Guarda contra uma remoção equivocada.

        Uma análise anterior classificou cache_utils como código morto. Não é:
        crm_api.py importa init_redis e clear_cache_pattern dele. Só a classe
        CacheStrategy está sem uso.
        """
        assert (RAIZ / "cache_utils.py").exists()

        usado = any(
            "cache_utils" in _imports_de(caminho) for caminho in _modulos_python_ativos()
        )
        assert usado, "cache_utils deixou de ser importado — reavalie antes de removê-lo"


class TestDocumentacao:
    def test_raiz_tem_apenas_o_readme(self):
        markdowns = {p.name for p in RAIZ.glob("*.md")}
        assert markdowns == {"README.md"}, (
            f"markdowns voltaram a se acumular na raiz: {sorted(markdowns - {'README.md'})}"
        )

    def test_existe_documento_de_estado_atual(self):
        assert (RAIZ / "docs" / "ESTADO-ATUAL.md").exists()

    def test_readme_aponta_para_o_estado_atual(self):
        conteudo = (RAIZ / "README.md").read_text(encoding="utf-8")
        assert "docs/ESTADO-ATUAL.md" in conteudo

    def test_readme_nao_afirma_visibilidade_incorreta(self):
        """O README dizia 'Visibilidade: Privado' num repositório clonável."""
        conteudo = (RAIZ / "README.md").read_text(encoding="utf-8")
        assert "Privado" not in conteudo

    @pytest.mark.parametrize(
        "documento",
        sorted(p.name for p in (RAIZ / "docs" / "historico").glob("*")
               if p.name != "README.md"),
    )
    def test_documento_historico_tem_aviso(self, documento):
        conteudo = (RAIZ / "docs" / "historico" / documento).read_text(encoding="utf-8")
        assert conteudo.lstrip().startswith("> **Documento histórico"), (
            f"{documento} está sem o aviso e pode ser lido como descrição do presente"
        )

    def test_estado_atual_registra_o_que_nao_existe(self):
        """A seção mais importante: o que a documentação antiga prometia."""
        conteudo = (RAIZ / "docs" / "ESTADO-ATUAL.md").read_text(encoding="utf-8")
        for tema in ("SSO", "Backup automático", "nao_integrado"):
            assert tema in conteudo, f"ESTADO-ATUAL.md não menciona {tema}"


class TestCacheSemOperacaoBloqueante:
    def test_invalidacao_usa_scan_e_nao_keys(self):
        """KEYS bloqueia o Redis inteiro enquanto percorre o keyspace."""
        conteudo = (RAIZ / "cache_utils.py").read_text(encoding="utf-8")
        ativas = [
            linha.split("#", 1)[0]
            for linha in conteudo.splitlines()
            if linha.split("#", 1)[0].strip()
        ]
        assert not any("redis_client.keys(" in linha for linha in ativas), (
            "clear_cache_pattern voltou a usar KEYS"
        )
        assert any("scan_iter" in linha for linha in ativas)
