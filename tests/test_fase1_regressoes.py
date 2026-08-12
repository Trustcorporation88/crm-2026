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
exportação da base não pode voltar para o `render.yaml`. Era o achado mais grave
da auditoria — com ele versionado e o modo export ligado, qualquer pessoa
baixava o banco inteiro.
"""

from pathlib import Path

REPO_RAIZ = Path(__file__).resolve().parent.parent


class TestSegredosNaoVersionados:
    """O token de exportação não pode voltar para o repositório."""

    def test_render_yaml_nao_contem_token_de_migracao(self):
        conteudo = (REPO_RAIZ / "render.yaml").read_text(encoding="utf-8")

        assert "crm-migrate-20260705-temp" not in conteudo

    def test_render_yaml_nao_liga_o_modo_export(self):
        """Em modo export o contêiner sobe o servidor de exportação da base
        inteira no lugar do CRM. Isso nunca deve estar fixo no blueprint."""
        conteudo = (REPO_RAIZ / "render.yaml").read_text(encoding="utf-8")

        ativas = [
            linha.split("#", 1)[0]
            for linha in conteudo.splitlines()
            if linha.split("#", 1)[0].strip()
        ]
        assert not any("value: export" in linha for linha in ativas)
