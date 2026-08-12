"""Regressões da Fase 1 que continuam válidas.

Este arquivo era maior. A maior parte dos testes exercitava endpoints do
`crm_api.py` — os que respondiam HTTP 200 sem gravar nada, e os que passaram a
responder 501 por não terem implementação. Esse serviço foi aposentado, então
os testes correspondentes foram removidos junto: teste de código que não existe
mais é ruído, não cobertura.

A capacidade equivalente (escrita com RBAC e auditoria) vive hoje no serviço
oficial, em `PUT`/`DELETE /api/{entity_type}/{entity_id}`, e é coberta por
`tests/test_crm_security.py::test_update_delete_require_jwt_and_audit_before_after`.

O que sobrou aqui é a verificação que não depende de nenhum serviço: o token de
exportação da base não pode voltar para o repositório. Era o achado mais grave
da auditoria — com ele versionado e o modo export ligado, qualquer pessoa
baixava o banco inteiro.

A verificação era feita só no `render.yaml`. A Render foi abandonada e o arquivo
removido, então ela passou a varrer **todos** os arquivos de configuração — o
que é mais robusto: o segredo não pode reaparecer em nenhum deles, seja qual for
o provedor da vez.
"""

from pathlib import Path

REPO_RAIZ = Path(__file__).resolve().parent.parent

# O token que esteve versionado num repositório público.
TOKEN_VAZADO = "crm-migrate-20260705-temp"

# Extensões onde configuração de deploy costuma morar.
PADROES_DE_CONFIG = ("*.yaml", "*.yml", "*.toml", "*.example", "*.json", "Dockerfile*")

DIRETORIOS_IGNORADOS = {".git", ".venv", "__pycache__", ".ruff_cache", "docs"}


def _arquivos_de_configuracao() -> list[Path]:
    encontrados: list[Path] = []
    for padrao in PADROES_DE_CONFIG:
        for caminho in REPO_RAIZ.rglob(padrao):
            if DIRETORIOS_IGNORADOS & set(caminho.relative_to(REPO_RAIZ).parts):
                continue
            if caminho.is_file():
                encontrados.append(caminho)
    return encontrados


class TestSegredosNaoVersionados:
    def test_token_de_exportacao_nao_esta_em_nenhuma_configuracao(self):
        culpados = [
            str(caminho.relative_to(REPO_RAIZ))
            for caminho in _arquivos_de_configuracao()
            if TOKEN_VAZADO in caminho.read_text(encoding="utf-8", errors="ignore")
        ]

        assert not culpados, f"o token de exportação reapareceu em: {culpados}"

    def test_nenhuma_configuracao_liga_o_modo_de_exportacao(self):
        """Em modo export o contêiner serve a base inteira no lugar do CRM.

        Era o que estava em produção quando a auditoria começou. Nunca deve
        estar fixo em arquivo de deploy — se for preciso reexportar, define-se
        a variável manualmente no painel e remove-se ao terminar.
        """
        culpados = []
        for caminho in _arquivos_de_configuracao():
            for linha in caminho.read_text(encoding="utf-8", errors="ignore").splitlines():
                ativa = linha.split("#", 1)[0]
                if "CRM_MIGRATION_MODE" in ativa and "export" in ativa:
                    culpados.append(f"{caminho.relative_to(REPO_RAIZ)}: {linha.strip()}")

        assert not culpados, f"modo de exportação ligado em: {culpados}"


class TestConfiguracaoDoDeployAtual:
    """A configuração precisa descrever o provedor em uso, não o anterior."""

    def test_arquivos_da_render_foram_removidos(self):
        for obsoleto in ("render.yaml", "RENDER-ENV.example", "docs/DEPLOY-RENDER.md"):
            assert not (REPO_RAIZ / obsoleto).exists(), (
                f"{obsoleto} voltou, mas a Render não é mais o destino do deploy"
            )

    def test_existe_guia_do_deploy_em_uso(self):
        assert (REPO_RAIZ / "docs" / "DEPLOY-RAILWAY.md").exists()

    def test_exemplo_de_variaveis_documenta_o_banco(self):
        """DATABASE_URL é o que decide entre Postgres e SQLite.

        Sem ela o app cai no SQLite do contêiner, que some a cada deploy — e o
        silêncio dessa troca é justamente o que a torna perigosa.
        """
        conteudo = (REPO_RAIZ / "RAILWAY-ENV.example").read_text(encoding="utf-8")

        assert "DATABASE_URL" in conteudo
        assert "Supabase" in conteudo
