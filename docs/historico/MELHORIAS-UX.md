> **Documento histórico — não descreve o estado atual do sistema.**
>
> Preservado como registro do que foi planejado ou anunciado na época. Uma
> auditoria posterior verificou várias afirmações destes documentos contra o
> código e encontrou divergências relevantes: funcionalidades listadas como
> concluídas que nunca foram ligadas ao produto, e endpoints descritos como
> funcionais que respondiam sucesso sem gravar nada.
>
> Para saber o que o sistema faz hoje, veja **[docs/ESTADO-ATUAL.md](../ESTADO-ATUAL.md)**.

---

# Melhorias de usabilidade — benchmark e implementação

Estudo dos CRMs líderes no Brasil e nos EUA aplicado ao TRUST CRM, com a
primeira leva de melhorias implementada.

**Produtos analisados**
Brasil: RD Station CRM, Agendor, Ploomes, Moskit, Pipedrive BR.
EUA: Salesforce Sales Cloud, HubSpot Sales Hub, Pipedrive, Attio, Close.com, Folk.

---

## 0. Achado de segurança (trate antes de qualquer melhoria de UX)

Ao acessar `crm.trustcorp.com.br` foi possível **entrar como administrador sem
nenhuma credencial**: a tela de login servia botões de "Entrar com 1 clique",
e as contas usam as senhas padrão publicadas no próprio repositório
(`admin123`, `vendas123`, …). Qualquer pessoa com o endereço tinha acesso total
à base.

O que mudou:

- Os botões de demonstração agora dependem de `CRM_DEMO_LOGIN=true`.
  **Desligado por padrão** — se a demonstração pública for intencional, defina
  a variável no Railway; se não for, não faça nada.
- Instalação nova pode nascer sem senha padrão, via
  `CRM_SEED_PASSWORD_ADMIN` e equivalentes.
- O administrador passa a ver um alerta dentro do sistema enquanto houver conta
  com senha padrão.

⚠️ **A base de produção já existe com `admin123`.** As variáveis de semente não
alteram banco existente: é necessário trocar a senha das contas em
«Minha conta / Trocar senha».

---

## 1. O que foi implementado

### Funil comercial (referência: Pipedrive, Agendor)

| Antes | Agora |
|---|---|
| Cabeçalho da coluna dizia só "1 oportunidade(s)" | Contagem **+ valor total + valor ponderado** por etapa |
| Nenhum sinal de negociação abandonada | **Indicador de estagnação** por etapa, com marca colorida no card |
| Sem visão de previsão | Faixa de resumo: em aberto, **previsão ponderada**, ticket médio |
| Tabela com `deal_id`, `value`, `close_date` cru | Rótulos em pt-BR, **R$ 190.000** e **19/05/2026** |

O indicador de estagnação segue o "rotting" do Pipedrive: cada etapa tem sua
tolerância de silêncio, e etapas avançadas apodrecem mais rápido — 7 dias sem
contato numa negociação pesa mais do que 21 dias numa descoberta.

A **previsão ponderada** (valor × probabilidade) é o número que o gestor
precisa. A soma bruta da coluna sempre superestima o funil.

### "Meu Dia" (referência: HubSpot Sales Workspace, Close Inbox)

Nova primeira tela do menu, para todos os papéis. Responde "o que eu faço
agora?" em vez de obrigar o usuário a varrer módulo por módulo:

- Tarefas **atrasadas** (mais atrasada primeiro) e tarefas de hoje
- Negociações **sem contato** além do limite da etapa
- Chamados que **consumiram 80%+ do SLA**, com os já estourados no topo

Respeita o filtro global de responsável: sem filtro mostra a equipe, com filtro
mostra só as pendências da pessoa.

### Busca global (referência: Attio cmd+K, HubSpot)

Um campo na barra lateral que procura ao mesmo tempo em **clientes,
oportunidades e chamados**, ignora acento e leva direto ao módulo do
resultado. Antes era preciso adivinhar em qual módulo o registro morava.

### Qualidade de cadastro (referência: Ploomes, RD Station)

- **CPF/CNPJ com validação de dígito verificador**, com retorno enquanto o
  usuário digita — não depois do submit, quando o erro já custou o formulário
  inteiro. Campo novo `document`, adicionado por migração automática.
- **Detecção de duplicado** na criação do cliente, por documento e por nome
  normalizado (ignora acento, caixa e sufixo societário: "Ecoplus Engenharia
  LTDA" casa com "Ecoplus Engenharia"). Criar duplicado exige confirmação
  explícita.

### Onboarding e estados vazios (referência: HubSpot, Attio)

- Checklist de primeiros passos que se marca sozinho conforme os dados
  aparecem, e some quando tudo está concluído.
- Estado vazio do funil explica **para que serve o módulo** e qual o próximo
  passo, em vez de só dizer "nenhum registro".

---

### Auto-preenchimento por CNPJ (referência: Ploomes, RD Station)

Digite o CNPJ, clique em **Buscar na Receita** e o cadastro chega preenchido
com razão social / nome fantasia, CNAE, cidade e situação cadastral. Se a
empresa não estiver **ATIVA**, o aviso aparece junto — informação que muda a
decisão comercial antes da primeira conversa.

Usa a [BrasilAPI](https://brasilapi.com.br), gratuita e sem chave. Todo o
acesso à rede está isolado em `crm_receita.py` e é tolerante a falha por
princípio: API fora do ar, CNPJ inexistente ou limite de requisições viram
aviso e **nunca** impedem o cadastro manual. O dígito verificador é conferido
antes da chamada, para não gastar rede com documento inválido.

### Visões salvas (referência: Attio, HubSpot 2026)

O recorte de filtros vira uma visão nomeada — "Minha carteira Brasil" — que se
reaplica em um clique, por usuário, persistida em `user_preferences`. Salvar
com um nome existente sobrescreve, em vez de criar duas visões homônimas.

Ao aplicar, só chaves de uma lista de permissão entram no estado da aplicação:
uma preferência antiga com campos que não existem mais não injeta lixo na tela.

### Campos obrigatórios por etapa (referência: RD Station, Ploomes, HubSpot)

Exigir tudo no cadastro afasta o vendedor; não exigir nada produz funil sem
informação. Cada etapa agora cobra só o que ela pressupõe — Proposta pede valor
e data de fechamento, Negociação pede também probabilidade. Valor zero conta
como ausente: proposta de R$ 0 é dado faltando, não valor legítimo.

### Ficha do cliente orientada à linha do tempo (referência: Pipedrive, Close, Attio)

A ficha deixou de abrir por cadastro e passa a abrir pelo que exige decisão.

**Próxima ação** no topo, com hierarquia deliberada: SLA estourado vence receita
em risco, que vence prospecção, que vence o plano cadastrado. Sem essa ordem, a
recomendação viraria ruído. Entre negociações paradas, a de maior valor vem
primeiro — é onde o silêncio custa mais caro.

**Linha do tempo como conteúdo principal**, agrupada por dia com rótulos humanos
("Hoje", "Ontem", "Há 3 dias") e ícone por canal. O cadastro foi para o painel
lateral, junto com oportunidades e chamados relacionados — cada um com seu
sinal de saúde.

**Registro de interação na própria tela**: canal, título e detalhe, sem sair da
ficha. Era o elo que faltava — antes o histórico só crescia por evento de
sistema, nunca pelo que o vendedor tinha acabado de fazer.

---

## 2. Como isso foi verificado

- **224 testes**, contra 25 no início da auditoria.
- A lógica de produto — formatação pt-BR, dígito verificador, estagnação,
  agenda do dia, duplicados, busca, visões salvas, portões de etapa — está
  separada da renderização (`crm_ux.py`, `crm_views.py`, `crm_receita.py`) e
  testada isoladamente.
- **Testes de renderização** (`tests/test_app_smoke.py`) executam o app de
  verdade com o `AppTest` do Streamlit. Validados por controle negativo: com um
  defeito injetado, eles falham.
- **A rede fica fora da suíte.** Os testes de CNPJ injetam o cliente HTTP e
  cobrem sucesso, 404, 429, erro 500, resposta vazia e timeout. Um teste de
  contrato separado (`pytest -m contract`) confere o formato real da BrasilAPI
  sem poder quebrar a CI por indisponibilidade de terceiro.

Esses testes de renderização pagaram por si: pegaram **três defeitos reais**
antes do deploy — em três pontos distintos eu escrevia em estado de widget já
instanciado, o que teria quebrado a tela ao salvar visão, aplicar visão e
consultar CNPJ. A correção foi mover as três ações para callbacks.

---

## 3. Próximas melhorias recomendadas

Em ordem de valor sobre esforço.

1. **WhatsApp com contexto do CRM** — 79% das vendas brasileiras acontecem no
   WhatsApp (RD Station). O módulo Canais é a superfície natural: conversa,
   resposta e vínculo com a negociação na mesma tela.
2. **Edição em linha nas tabelas** via `st.data_editor` — evita abrir formulário
   para trocar um campo, e **ações em lote** para reatribuir vários registros.
3. **Visões salvas por módulo** — hoje as visões cobrem os filtros globais;
   estendê-las a filtros por módulo (etapa, situação, faixa de valor) multiplica
   o ganho.
4. **Consentimento LGPD por titular**, com exclusão que apaga CPF, e-mail e
   telefone preservando o histórico anonimizado.
5. **Arrastar e soltar no funil** — exige componente externo; o ganho é menor
   que os itens acima, apesar de ser o mais pedido visualmente.

### O que ainda separa este CRM dos líderes

Vale ser direto: as melhorias acima fecham lacunas de **usabilidade**, e nisso o
produto está competitivo. Estar entre os melhores do mundo depende de três
coisas que nenhuma tela resolve:

1. **Persistência.** O sistema roda em SQLite num volume só. Os líderes operam
   Postgres com réplica e backup testado. Sem isso, um incidente de disco é
   perda de base — e nenhuma quantidade de recurso compensa isso.
2. **Os endpoints placeholder.** Boa parte de `crm_api.py` ainda devolve lista
   vazia. Enquanto existirem, a API não é integrável de verdade.
3. **Multi-tenant e auditoria.** Hoje há papéis, mas não isolamento por
   organização. É pré-requisito para vender o produto a mais de um cliente.
