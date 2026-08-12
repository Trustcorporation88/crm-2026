"""Regressões da Fase 3: CI, imagem Docker e observabilidade.

Configuração quebrada não aparece em teste unitário — aparece em produção, no
pior momento. Estes testes leem os arquivos de configuração e falham se os
defeitos corrigidos voltarem.

Defeitos cobertos:

1. Todos os gates de qualidade do CI eram não bloqueantes (--exit-zero,
   "|| true"), então nada impedia um deploy com erro de lint ou achado de
   segurança.
2. O backup "pré-deploy" era tirado depois de subir a versão nova.
3. O passo de testes de integração apontava para um diretório inexistente.
4. O CMD do Dockerfile embrulhava o processo em "sh -c", impedindo o SIGTERM
   de chegar ao Streamlit.
5. Uma variável de ambiente trocava o CRM pelo servidor de exportação da base.
6. Não havia .dockerignore: .git e todo o resto iam para o contexto de build.
7. Os alvos do Prometheus apontavam para localhost dentro do Compose.
"""

from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent


def _ler(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="utf-8")


def _linhas_ativas(nome: str) -> list[str]:
    """Linhas sem comentários — inclusive os de fim de linha.

    Necessário porque os próprios comentários explicativos citam o padrão
    antigo ("antes isto era chmod a+rwX"), e uma busca ingênua no texto bruto
    acusaria o defeito que acabou de ser corrigido.
    """
    ativas = []
    for linha in _ler(nome).splitlines():
        sem_comentario = linha.split("#", 1)[0].rstrip()
        if sem_comentario.strip():
            ativas.append(sem_comentario)
    return ativas


class TestPipelineDeCI:
    def test_lint_bloqueia_o_build(self):
        conteudo = _ler(".github/workflows/deploy.yml")
        assert "ruff check . --exit-zero" not in conteudo, (
            "o lint voltou a ser não bloqueante"
        )

    def test_bandit_bloqueia_o_build(self):
        conteudo = _ler(".github/workflows/deploy.yml")
        assert "bandit -r . -ll -i || true" not in conteudo, (
            "a verificação de segurança voltou a ser decorativa"
        )

    def test_backup_acontece_antes_do_deploy(self):
        ativas = _linhas_ativas(".github/workflows/deploy.yml")
        indice_backup = next(
            (i for i, linha in enumerate(ativas) if "pg_dump" in linha), None
        )
        indice_subida = next(
            (i for i, linha in enumerate(ativas) if "docker-compose up -d" in linha),
            None,
        )

        assert indice_backup is not None, "o backup pré-deploy sumiu"
        assert indice_subida is not None
        assert indice_backup < indice_subida, (
            "o backup voltou a ser tirado depois de subir a versão nova"
        )

    def test_passo_de_integracao_tolera_ausencia_do_diretorio(self):
        conteudo = _ler(".github/workflows/deploy.yml")
        if not (RAIZ / "tests" / "integration").exists():
            assert "if [ -d tests/integration ]" in conteudo, (
                "o passo falha sempre, pois o diretório não existe"
            )

    def test_workflow_e_yaml_valido(self):
        yaml.safe_load(_ler(".github/workflows/deploy.yml"))


class TestImagemDocker:
    def test_cmd_nao_usa_shell_wrapper(self):
        """Com 'sh -c', o PID 1 é o shell e o SIGTERM não chega ao processo."""
        conteudo = _ler("Dockerfile")
        linha_cmd = [
            linha for linha in conteudo.splitlines()
            if linha.startswith("CMD ")
        ]
        assert linha_cmd, "CMD não encontrado"
        assert 'sh", "-c"' not in linha_cmd[0], (
            "o CMD voltou a embrulhar o processo num shell"
        )

    def test_dockerfile_nao_liga_modo_export(self):
        assert not any(
            "CRM_MIGRATION_MODE" in linha for linha in _linhas_ativas("Dockerfile")
        ), (
            "uma variável de ambiente volta a trocar o CRM pelo exportador da base"
        )

    def test_dockerignore_existe_e_exclui_o_essencial(self):
        caminho = RAIZ / ".dockerignore"
        assert caminho.exists(), ".dockerignore ausente: .git vai para a imagem"

        conteudo = caminho.read_text(encoding="utf-8")
        for padrao in (".git", "tests/", ".env"):
            assert padrao in conteudo, f"{padrao} não está excluído do contexto"

    def test_entrypoint_nao_deixa_dados_com_permissao_ampla(self):
        for linha in _linhas_ativas("docker-entrypoint.sh"):
            assert "a+rw" not in linha, (
                f"dados voltaram a ficar graváveis por qualquer processo: {linha.strip()}"
            )


class TestObservabilidade:
    def test_alvos_nao_usam_localhost(self):
        """No Compose, o Prometheus tem seu próprio contêiner."""
        for linha in _linhas_ativas("prometheus.yml"):
            if "targets:" not in linha:
                continue
            assert "localhost" not in linha, f"alvo inalcançável: {linha.strip()}"

    def test_prometheus_e_yaml_valido(self):
        yaml.safe_load(_ler("prometheus.yml"))


class TestLintDeterministico:
    """Um gate bloqueante precisa ser reprodutível para ser confiável."""

    def test_existe_configuracao_de_ruff(self):
        assert (RAIZ / "ruff.toml").exists(), (
            "sem config no repositório, o ruff aplica o padrão da versão "
            "instalada — que muda entre versões e torna o gate imprevisível"
        )

    def test_ruff_esta_com_versao_fixa_no_ci(self):
        conteudo = _ler(".github/workflows/deploy.yml")
        assert "ruff==" in conteudo, (
            "o CI voltou a instalar o ruff sem fixar versão"
        )

    def test_repositorio_passa_no_proprio_lint(self):
        """Se este teste falha, o deploy está barrado — corrija antes do merge."""
        import shutil
        import subprocess

        executavel = shutil.which("ruff")
        if executavel is None:
            pytest.skip("ruff não instalado neste ambiente")

        resultado = subprocess.run(
            [executavel, "check", "."],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        assert resultado.returncode == 0, (
            f"ruff acusou problemas:\n{resultado.stdout}\n{resultado.stderr}"
        )


class TestDependencias:
    def test_requirements_web_nao_duplica_versoes(self):
        """Duplicar sem fixar permitia sobrescrever as versões de produção."""
        conteudo = _ler("web_requirements.txt")
        linhas = [
            linha.strip() for linha in conteudo.splitlines()
            if linha.strip() and not linha.strip().startswith("#")
        ]
        assert all(linha.startswith("-r ") for linha in linhas), (
            f"web_requirements.txt voltou a listar pacotes soltos: {linhas}"
        )

    @pytest.mark.parametrize(
        "pacote,piso",
        [("streamlit", "1.54.0"), ("pillow", "12.3.0"), ("urllib3", "2.7.0")],
    )
    def test_pisos_de_seguranca_declarados(self, pacote, piso):
        conteudo = _ler("requirements.txt").lower()
        assert f"{pacote}>={piso}" in conteudo, (
            f"{pacote} voltou para uma faixa com vulnerabilidade conhecida"
        )
