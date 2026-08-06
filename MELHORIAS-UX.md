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

## 2. Como isso foi verificado

- **73 testes novos** (139 no total, de 25 na primeira auditoria).
- A lógica de produto — formatação pt-BR, dígito verificador, estagnação,
  agenda do dia, duplicados, busca — está em `crm_ux.py`, separada da
  renderização e testada isoladamente.
- **Testes de renderização** (`tests/test_app_smoke.py`) executam o app de
  verdade com o `AppTest` do Streamlit e falham se qualquer seção quebrar.
  Foram validados por controle negativo: com um defeito injetado, eles falham.

---

## 3. Próximas melhorias recomendadas

Em ordem de valor sobre esforço.

1. **Visões salvas por módulo** — filtro + ordenação nomeados e reaplicáveis
   num clique. Hoje o usuário refaz o mesmo filtro toda sessão. É o padrão
   central do Attio e do HubSpot pós-2026. Exige persistência por usuário.
2. **Auto-preenchimento por CNPJ** — consultar a Receita Federal e preencher
   razão social, CNAE, endereço e situação cadastral. A validação de dígito já
   está pronta; falta a chamada de API (~R$ 0,13/consulta). É expectativa
   básica de CRM B2B brasileiro.
3. **Campos obrigatórios por etapa** — bloquear o avanço da negociação até que
   os campos daquela etapa estejam preenchidos. Amarra a qualidade do dado a
   uma ação que o vendedor já está fazendo.
4. **Linha do tempo como visão principal do cliente** — hoje a ficha lidera por
   campos; os líderes lideram pela narrativa de interações.
5. **Edição em linha nas tabelas** via `st.data_editor` — evita abrir formulário
   para trocar um campo.
6. **WhatsApp com contexto do CRM** — 79% das vendas brasileiras acontecem no
   WhatsApp (RD Station). O módulo Canais é a superfície natural: conversa,
   resposta e vínculo com a negociação na mesma tela.
7. **Consentimento LGPD por titular**, com exclusão que apaga CPF, e-mail e
   telefone preservando o histórico anonimizado.
8. **Arrastar e soltar no funil** — exige componente externo; o ganho é menor
   que os itens acima, apesar de ser o mais pedido visualmente.
