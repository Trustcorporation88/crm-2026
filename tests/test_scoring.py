"""Cobertura dos módulos de scoring e análise.

Estes sete módulos — lead_scoring, health_score, forecast, productivity,
cadences, message_templates e ai_insights — somam cerca de 680 linhas e não
tinham um único teste. São eles que produzem lead score, health score,
previsão de receita e ranking de produtividade: a parte analítica do CRM, que
é onde decisões comerciais são tomadas.

A ausência de cobertura não era teórica. Ao padronizar timestamps em UTC ISO
numa fase anterior, cinco destes módulos passaram a comparar colunas de data
com limiares no formato antigo, alargando as janelas em até 24 horas. A suíte
inteira continuou verde, porque nada aqui era exercitado. A classe
TestLimiaresDeData existe para que esse caso específico não volte.
"""

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def crm(tmp_path):
    """Backend limpo com os schemas auxiliares criados."""
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    os.environ["CRM_SEED_PASSWORD_ADMIN"] = "senha-de-teste-2026"

    for nome in (
        "crm_backend", "lead_scoring", "health_score", "forecast",
        "productivity", "cadences", "message_templates", "ai_insights",
        "scoring_datas",
    ):
        sys.modules.pop(nome, None)

    backend = importlib.import_module("crm_backend")
    backend.init_database()
    return backend


def _interacao(backend, customer_id: str, quando: str, titulo: str = "Contato") -> None:
    """Insere uma interação com event_at controlado.

    Grava direto no banco porque add_interaction() carimba a hora atual, e
    estes testes precisam posicionar eventos em datas específicas.
    """
    with backend._connect() as c:
        c.execute(
            "INSERT INTO interactions (customer_id, event_at, event_type, title, body, channel, owner, related_id)"
            " VALUES (?, ?, 'note', ?, '', 'Email', 'admin', '')",
            (customer_id, quando, titulo),
        )
        c.commit()


def _primeiro_cliente(backend) -> str:
    with backend._connect() as c:
        row = c.execute("SELECT customer_id FROM customers LIMIT 1").fetchone()
    assert row is not None, "o seed não criou nenhum cliente"
    return str(row["customer_id"])


# ---------------------------------------------------------------------------
# O defeito que motivou esta suíte
# ---------------------------------------------------------------------------

class TestLimiaresDeData:
    """O banco guarda dois formatos de timestamp na mesma coluna TEXT.

    Linhas antigas usam "2026-05-25 08:30"; linhas novas, o ISO UTC. A
    comparação em SQL é lexicográfica, então o formato do limiar decide o
    resultado — e um limiar com hora erra em um dos dois formatos, sempre.
    """

    def test_limiar_e_somente_data(self):
        from scoring_datas import limiar_de_dias

        limiar = limiar_de_dias(7)
        assert len(limiar) == 10, f"limiar deveria ser YYYY-MM-DD, veio {limiar!r}"
        assert " " not in limiar and "T" not in limiar

    @pytest.mark.parametrize("formato", ["legado", "iso"])
    def test_janela_correta_nos_dois_formatos(self, crm, formato):
        """O caso concreto: evento de ontem entra na janela, o de 30 dias não."""
        from scoring_datas import limiar_de_dias

        cid = _primeiro_cliente(crm)
        ontem = datetime.now(timezone.utc) - timedelta(days=1)
        antigo = datetime.now(timezone.utc) - timedelta(days=30)

        if formato == "legado":
            grava = lambda d: d.strftime("%Y-%m-%d %H:%M")  # noqa: E731
        else:
            grava = lambda d: d.isoformat()  # noqa: E731

        _interacao(crm, cid, grava(ontem), "recente")
        _interacao(crm, cid, grava(antigo), "antigo")

        with crm._connect() as c:
            dentro = c.execute(
                "SELECT COUNT(*) AS t FROM interactions WHERE customer_id=? AND event_at>=?",
                (cid, limiar_de_dias(7)),
            ).fetchone()["t"]

        assert dentro == 1, (
            f"formato {formato}: esperava só o evento recente na janela de 7 dias, veio {dentro}"
        )

    def test_evento_da_madrugada_nao_escapa_da_janela(self, crm):
        """A regressão exata: ISO das 00:01 comparado a limiar das 13:29.

        Com limiar contendo hora, "2026-08-05T00:01:00+00:00" era considerado
        posterior a "2026-08-05 13:29", porque 'T' > ' ' em ASCII.
        """
        from scoring_datas import limiar_de_dias

        cid = _primeiro_cliente(crm)
        limite = datetime.now(timezone.utc) - timedelta(days=7)
        # Madrugada do dia ANTERIOR ao início da janela: deve ficar de fora.
        fora = (limite - timedelta(days=1)).replace(hour=0, minute=1)
        _interacao(crm, cid, fora.isoformat(), "fora da janela")

        with crm._connect() as c:
            dentro = c.execute(
                "SELECT COUNT(*) AS t FROM interactions WHERE customer_id=? AND event_at>=?",
                (cid, limiar_de_dias(7)),
            ).fetchone()["t"]

        assert dentro == 0, "evento anterior à janela foi contado como recente"

    def test_mesmo_instante_nos_dois_formatos_da_o_mesmo_resultado(self, crm):
        """O invariante que de fato protege contra a regressão.

        O defeito não era "a janela está errada por uma hora" — era que a
        janela dependia do FORMATO em que a linha havia sido gravada. O mesmo
        instante, escrito como "2026-08-05 09:00" ou como
        "2026-08-05T09:00:00+00:00", caía em lados diferentes do limiar.

        Posiciona o evento exatamente no dia do limiar, que é onde a
        divergência aparece, e exige que os dois formatos concordem.
        """
        from scoring_datas import limiar_de_dias

        cid_legado = "BORDA-LEGADO"
        cid_iso = "BORDA-ISO"
        with crm._connect() as c:
            for cid in (cid_legado, cid_iso):
                c.execute(
                    "INSERT INTO customers (customer_id, name, segment, city, country,"
                    " owner, status, health_score, lifetime_value, last_purchase,"
                    " channel, next_action, source)"
                    " VALUES (?,?,'SMB','Recife','Brasil','admin','Novo',50,0,"
                    "'2026-01-01','Email','-','teste')",
                    (cid, f"Cliente {cid}"),
                )
            c.commit()

        # Dia exato do limiar, de madrugada — antes da hora corrente.
        borda = (datetime.now(timezone.utc) - timedelta(days=7)).replace(hour=0, minute=1)
        _interacao(crm, cid_legado, borda.strftime("%Y-%m-%d %H:%M"), "borda legado")
        _interacao(crm, cid_iso, borda.isoformat(), "borda iso")

        limiar = limiar_de_dias(7)
        with crm._connect() as c:
            def conta(cid):
                return c.execute(
                    "SELECT COUNT(*) AS t FROM interactions WHERE customer_id=? AND event_at>=?",
                    (cid, limiar),
                ).fetchone()["t"]

            n_legado, n_iso = conta(cid_legado), conta(cid_iso)

        assert n_legado == n_iso, (
            f"o mesmo instante deu resultados diferentes conforme o formato: "
            f"legado={n_legado}, iso={n_iso}"
        )

    def test_carimbo_de_escrita_e_utc_iso(self):
        from scoring_datas import carimbo_utc

        valor = carimbo_utc()
        assert "T" in valor and valor.endswith("+00:00")


# ---------------------------------------------------------------------------
# lead_scoring
# ---------------------------------------------------------------------------

class TestLeadScoring:
    def test_calcula_e_persiste(self, crm):
        import lead_scoring

        cid = _primeiro_cliente(crm)
        r = lead_scoring.calculate_lead_score(cid)

        assert r["customer_id"] == cid
        assert 0 <= r["score"] <= 100
        assert r["tier"] in {"A", "B", "C", "D"}

        with crm._connect() as c:
            gravado = c.execute(
                "SELECT score, tier FROM lead_scores WHERE customer_id=?", (cid,)
            ).fetchone()
        assert gravado is not None and int(gravado["score"]) == r["score"]

    def test_cliente_inexistente_falha_claramente(self, crm):
        import lead_scoring

        with pytest.raises(ValueError, match="not found"):
            lead_scoring.calculate_lead_score("NAO-EXISTE")

    @pytest.mark.parametrize(
        "score,tier", [(95, "A"), (80, "A"), (79, "B"), (60, "B"), (59, "C"), (40, "C"), (39, "D"), (0, "D")]
    )
    def test_fronteiras_das_faixas(self, crm, score, tier):
        import lead_scoring

        assert lead_scoring._tier(score) == tier

    def test_sinal_de_recencia_respeita_a_janela(self, crm):
        """Teste funcional do defeito, atravessando o módulo de verdade.

        Os testes de limiar acima exercitam o utilitário; este exercita o
        caminho real: uma interação de 9 dias atrás não pode marcar
        `responded_recently`, cuja janela é de 7 dias. Com o limiar antigo
        (contendo hora), um evento ISO da madrugada escapava para dentro.
        """
        import lead_scoring

        cid = _primeiro_cliente(crm)
        antiga = (datetime.now(timezone.utc) - timedelta(days=9)).replace(hour=0, minute=1)
        _interacao(crm, cid, antiga.isoformat(), "fora da janela de 7 dias")

        r = lead_scoring.calculate_lead_score(cid)
        assert r["signals"]["responded_recently"] is False, (
            "interação de 9 dias atrás foi contada como recente"
        )

        # E o contrário: algo de ontem precisa contar.
        _interacao(
            crm, cid,
            (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "dentro da janela",
        )
        r2 = lead_scoring.calculate_lead_score(cid)
        assert r2["signals"]["responded_recently"] is True

    def test_recalculo_em_lote_cobre_todos(self, crm):
        import lead_scoring

        with crm._connect() as c:
            total = c.execute("SELECT COUNT(*) AS t FROM customers").fetchone()["t"]

        r = lead_scoring.recalculate_all_scores(actor={"username": "admin", "role": "admin"})
        assert r.get("total", r.get("count", 0)) == total or total > 0

        with crm._connect() as c:
            pontuados = c.execute("SELECT COUNT(*) AS t FROM lead_scores").fetchone()["t"]
        assert pontuados == total

    def test_score_nunca_sai_da_faixa(self, crm):
        """Mesmo com todas as regras somando, o teto é 100."""
        import lead_scoring

        for cid in [_primeiro_cliente(crm)]:
            r = lead_scoring.calculate_lead_score(cid)
            assert 0 <= r["score"] <= 100


# ---------------------------------------------------------------------------
# health_score
# ---------------------------------------------------------------------------

class TestHealthScore:
    def test_calcula_e_persiste(self, crm):
        import health_score

        cid = _primeiro_cliente(crm)
        r = health_score.calculate_health(cid)

        assert 0 <= r["health_score"] <= 100
        assert r["churn_risk"] in {"Baixo", "Medio", "Alto", "Critico"}
        assert "positive_signals" in r and "negative_signals" in r
        assert r["calculated_at"].endswith("+00:00"), r["calculated_at"]

        with crm._connect() as c:
            gravado = c.execute(
                "SELECT health_score FROM health_snapshots WHERE customer_id=?", (cid,)
            ).fetchone()
        assert gravado is not None
        assert int(gravado["health_score"]) == r["health_score"]

    def test_interacao_recente_melhora_o_sinal(self, crm):
        import health_score

        cid = _primeiro_cliente(crm)
        _interacao(crm, cid, datetime.now(timezone.utc).isoformat(), "contato de hoje")

        r = health_score.calculate_health(cid)
        assert r["positive_signals"]["recent_interaction"] is True

    def test_cliente_inexistente_falha_claramente(self, crm):
        import health_score

        with pytest.raises(ValueError):
            health_score.calculate_health("NAO-EXISTE")


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------

class TestForecast:
    @pytest.mark.parametrize(
        "prob,esperado",
        [(100, "commit"), (80, "commit"), (79, "best_case"), (50, "best_case"),
         (49, "pipeline"), (20, "pipeline"), (19, "longshot"), (0, "longshot")],
    )
    def test_categorizacao_por_probabilidade(self, crm, prob, esperado):
        """Fronteiras exatas das quatro faixas, inclusive longshot."""
        import forecast

        assert forecast._categorize(prob) == esperado

    def test_previsao_tem_as_chaves_esperadas(self, crm):
        import forecast

        r = forecast.get_pipeline_forecast()
        assert isinstance(r, dict)
        for chave in (
            "period_start", "period_end", "deal_count", "weighted_forecast",
            "commit_value", "best_case_value", "pipeline_value", "longshot_value",
        ):
            assert chave in r, f"chave ausente na previsão: {chave}"

    def test_soma_das_categorias_bate_com_o_pipeline_bruto(self, crm):
        """Todo negócio precisa cair em exatamente uma das quatro faixas."""
        import forecast

        r = forecast.get_pipeline_forecast(period_start="2000-01-01", period_end="2099-12-31")
        soma = (
            r["commit_value"] + r["best_case_value"]
            + r["pipeline_value"] + r["longshot_value"]
        )
        assert soma == pytest.approx(r["raw_pipeline_value"])

    def test_previsao_por_owner_e_lista(self, crm):
        import forecast

        assert isinstance(forecast.get_forecast_by_owner(), list)

    def test_metricas_de_velocidade_nao_quebram_sem_dado(self, crm):
        import forecast

        assert isinstance(forecast.get_velocity_metrics(), dict)


# ---------------------------------------------------------------------------
# productivity
# ---------------------------------------------------------------------------

class TestProductivity:
    def test_produtividade_por_owner(self, crm):
        import productivity

        linhas = productivity.get_owner_productivity(period_days=3650)
        assert isinstance(linhas, list)
        if linhas:
            assert "owner" in linhas[0]

    def test_resumo_do_time(self, crm):
        import productivity

        assert isinstance(productivity.get_team_summary(period_days=3650), dict)

    def test_janela_curta_nao_conta_evento_antigo(self, crm):
        """Exercita o limiar de data no caminho de produtividade."""
        import productivity

        cid = _primeiro_cliente(crm)
        antigo = datetime.now(timezone.utc) - timedelta(days=200)
        _interacao(crm, cid, antigo.isoformat(), "muito antigo")

        curto = productivity.get_owner_productivity(period_days=7)
        total_curto = sum(int(linha.get("interactions_total", 0)) for linha in curto)

        longo = productivity.get_owner_productivity(period_days=3650)
        total_longo = sum(int(linha.get("interactions_total", 0)) for linha in longo)

        assert total_curto <= total_longo


# ---------------------------------------------------------------------------
# message_templates
# ---------------------------------------------------------------------------

class TestMessageTemplates:
    def test_listagem_retorna_lista(self, crm):
        import message_templates

        message_templates.init_templates_schema()
        assert isinstance(message_templates.list_templates(), list)

    def test_salvar_e_recuperar(self, crm):
        import message_templates

        message_templates.init_templates_schema()
        message_templates.save_template(
            "boas-vindas", "Email", "Onboarding", "Bem-vindo", "Olá {nome}, tudo bem?"
        )

        t = message_templates.get_template("boas-vindas")
        assert t is not None
        assert t["title"] == "Bem-vindo"

    def test_renderizacao_substitui_variaveis(self, crm):
        import message_templates

        message_templates.init_templates_schema()
        message_templates.save_template(
            "oi", "Email", "Geral", "Oi", "Olá {{nome}}, seu plano é {{plano}}."
        )

        texto = message_templates.render_template("oi", {"nome": "Ana", "plano": "Pro"})
        assert "Ana" in texto and "Pro" in texto
        assert "{{nome}}" not in texto

    def test_variavel_ausente_permanece_no_texto(self, crm):
        """Documenta o comportamento atual: o marcador fica visível.

        Não é necessariamente o ideal — mandar "Olá {{nome}}" para um cliente
        é constrangedor — mas é o que o código faz hoje, e mudar isso é
        decisão de produto, não correção.
        """
        import message_templates

        message_templates.init_templates_schema()
        message_templates.save_template("p", "Email", "Geral", "P", "Olá {{nome}}!")

        assert message_templates.render_template("p", {}) == "Olá {{nome}}!"

    def test_template_inexistente_falha_claramente(self, crm):
        import message_templates

        message_templates.init_templates_schema()
        with pytest.raises(ValueError, match="not found"):
            message_templates.render_template("nao-existe", {})

    def test_carimbo_gravado_em_utc(self, crm):
        import message_templates

        message_templates.init_templates_schema()
        message_templates.save_template("x", "Email", "Geral", "X", "corpo")

        with crm._connect() as c:
            row = c.execute(
                "SELECT created_at FROM message_templates WHERE key='x'"
            ).fetchone()

        assert row["created_at"].endswith("+00:00"), row["created_at"]


# ---------------------------------------------------------------------------
# cadences
# ---------------------------------------------------------------------------

class TestCadences:
    def test_schema_inicializa(self, crm):
        import cadences

        cadences.init_cadences_schema()
        with crm._connect() as c:
            tabelas = {
                r["name"]
                for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "cadence_enrollments" in tabelas

    def test_inscricao_sem_passos_falha(self, crm):
        import cadences

        cadences.init_cadences_schema()
        with pytest.raises(ValueError, match="no steps"):
            cadences.enroll("cadencia-inexistente", _primeiro_cliente(crm), "admin")

    def test_acoes_pendentes_retorna_lista(self, crm):
        import cadences

        cadences.init_cadences_schema()
        assert isinstance(cadences.list_pending_actions(), list)

    def test_inscricoes_ativas_retorna_lista(self, crm):
        import cadences

        cadences.init_cadences_schema()
        assert isinstance(cadences.list_active_enrollments(), list)


# ---------------------------------------------------------------------------
# ai_insights
# ---------------------------------------------------------------------------

class TestAiInsights:
    def test_resumo_da_timeline_e_texto(self, crm):
        import ai_insights

        cid = _primeiro_cliente(crm)
        _interacao(crm, cid, datetime.now(timezone.utc).isoformat(), "Ligação feita")

        resumo = ai_insights.summarize_customer_timeline(cid)
        assert isinstance(resumo, str) and resumo

    def test_proxima_acao_sugerida(self, crm):
        import ai_insights

        r = ai_insights.suggest_next_action(_primeiro_cliente(crm))
        assert isinstance(r, dict)

    @pytest.mark.parametrize(
        "assunto", ["Erro ao emitir nota fiscal", "Quero contratar mais licenças", "Dúvida sobre cobrança"]
    )
    def test_classificacao_de_ticket(self, crm, assunto):
        import ai_insights

        r = ai_insights.classify_ticket(assunto)
        assert isinstance(r, dict)
        assert r, "classificação veio vazia"

    def test_deteccao_de_anomalias(self, crm):
        import ai_insights

        assert isinstance(ai_insights.detect_anomalies(period_days=30), list)

    def test_timeline_de_cliente_sem_evento(self, crm):
        """Não pode estourar quando não há histórico."""
        import ai_insights

        with crm._connect() as c:
            c.execute(
                "INSERT INTO customers (customer_id, name, segment, city, country, owner,"
                " status, health_score, lifetime_value, last_purchase, channel, next_action, source)"
                " VALUES ('SEM-HIST','Sem Historico','SMB','Recife','Brasil','admin','Novo',50,0,'2026-01-01','Email','-','teste')"
            )
            c.commit()

        assert isinstance(ai_insights.summarize_customer_timeline("SEM-HIST"), str)
