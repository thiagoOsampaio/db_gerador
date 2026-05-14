# db_gerador — AI Database Architecture Backend

Python backend that orchestrates Google **Gemini** through **LangGraph** to
produce normalized relational models, ER diagrams, SQL migrations, and
performance/security recommendations from a customer database schema —
then publishes the result to an OpenProject task.

## Architecture

```
HTTP (FastAPI)
    │
    ▼
WorkflowEngine ──► LangGraph StateGraph ──► PostgreSQL checkpointer
    │
    ├─ validate_input ─── introspect customer DB (SQLAlchemy)
    ├─ analyze_project ── Gemini → ProjectIR
    ├─ model_schema ───── Gemini → RelationalModel
    ├─ analyze_perf ───┐  Gemini → PerformanceRecommendation[]
    ├─ analyze_sec ────┤  Gemini → SecurityRecommendation[]   (parallel)
    ├─ merge_results ──┘
    ├─ generate_erd ──── deterministic MermaidRenderer
    ├─ await_approval ── HUMAN-IN-THE-LOOP (interrupt)
    ├─ generate_sql ──── deterministic SqlGenerator
    └─ update_openproject (comment + attachments)
```

- **LLM**: Gemini only (`langchain-google-genai`). No multi-provider.
- **State**: PostgreSQL (application data + LangGraph checkpoints). No Redis.
- **Secrets**: Backend env vars; customer DB password encrypted (Fernet, TTL).
- **Outputs**: 100% structured Pydantic v2; SQL/Mermaid are deterministic.

## Como subir o servidor para testar

1. Copie o arquivo `.env.example` para `.env` e preencha as variáveis de ambiente necessárias (como a `GEMINI_API_KEY`):
```bash
cp .env.example .env
```

2. Certifique-se de que possui um banco de dados PostgreSQL rodando (ele é usado para guardar os metadados da aplicação, como logs, sessões e checkpoint do fluxo do LangGraph, não os dados do cliente):
```bash
docker compose up -d postgres
```

3. Instale as dependências da aplicação usando `pip` com o ambiente virtual ativado:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

4. Aplique as migrações no banco de dados para criar a estrutura correta no schema configurado (padrão: `analisador_de_banco`):
```bash
alembic upgrade head
```

5. Rode o servidor usando `uvicorn`:
```bash
uvicorn backend.main:app --reload
```

O servidor estará rodando em `http://localhost:8000`. Você pode acessar o Swagger UI em `http://localhost:8000/docs`.

## Fluxo de Utilização (Overview)

O backend do `db_gerador` utiliza um fluxo com um passo de **Aprovação Humana (Human-in-the-loop)**.

1. **Iniciar Análise**: O usuário chama a API de `start`, fornecendo as credenciais de leitura do banco de dados alvo, dados adicionais de sua arquitetura e seu **token pessoal do OpenProject**. O token é criptografado e salvo, a senha é criptografada e o fluxo assíncrono é iniciado. 
   *(O código nunca realiza alterações - scripts, inserts, drops - no banco de dados do cliente)*.
2. **Processamento Inicial**: O backend acessa o banco (somente-leitura) e extrai o schema. Em seguida, os agentes baseados em IA (Gemini) atuam paralelamente modelando o projeto, validando performance e sugerindo seguranças.
3. **Diagramação e Pausa**: Um diagrama Mermaid é gerado de forma determinística (sem IA). **O fluxo é interrompido** aguardando a decisão humana (status: `awaiting_approval`).
4. **Avaliação**: O usuário solicita o diagrama via API para analisá-lo visualmente.
5. **Decisão Humana**:
   - **Rejeitar (`reject`)**: O usuário envia os apontamentos do que não gostou. O fluxo volta para a etapa de modelagem instruindo a IA a corrigir conforme o feedback enviado. O fluxo será novamente pausado para aprovação posterior.
   - **Aprovar (`approve`)**: O fluxo é retomado, gerando um artefato de script SQL (PostgreSQL).
6. **Integração**: Finalmente, utilizando o Token de OpenProject fornecido pelo próprio usuário, a aplicação anexa o diagrama Mermaid, o arquivo de SQL de migração e um comentário à Task correspondente no OpenProject.

---

## APIs Disponíveis

### 1. Iniciar Análise
**Endpoint:** `POST /analysis/start`
**Para que serve:** Inicia uma nova sessão de análise de banco de dados. Este endpoint salva as credenciais usando criptografia (Fernet) e imediatamente dispara o fluxo do LangGraph em background.

**O que recebe (JSON Body):**
```json
{
  "user_email": "dba@exemplo.com",
  "openproject_task_id": "1234",
  "openproject_token": "token_pessoal_do_usuario_no_openproject",
  "database_type": "postgresql",
  "database_host": "meu-banco-cliente.internal",
  "database_port": 5432,
  "database_name": "minha_base",
  "database_username": "readonly_user",
  "database_password": "minha_senha_secreta",
  "framework_name": "django",
  "orm_name": "django-orm"
}
```

**O que devolve (Status 202 Accepted):**
```json
{
  "session_id": "f0e9b9d3-...",
  "status": "pending",
  "approval_state": "pending",
  "message": "Analysis started"
}
```

---

### 2. Status da Análise
**Endpoint:** `GET /analysis/{session_id}/status`
**Para que serve:** Realizar o *polling* para acompanhar o progresso atual do processamento de uma sessão. 

**O que recebe:** Apenas o parâmetro de rota `session_id`.

**O que devolve:**
```json
{
  "session_id": "f0e9b9d3-...",
  "status": "awaiting_approval",
  "approval_state": "pending",
  "rejection_feedback": null,
  "errors": [],
  "updated_at": "2026-05-14T10:00:00Z"
}
```
*Dica: Você deve aguardar até que o `status` seja `awaiting_approval` para poder ver o diagrama e tomar a decisão.*

---

### 3. Visualizar o Diagrama (ERD)
**Endpoint:** `GET /analysis/{session_id}/diagram`
**Para que serve:** Retorna a string pura no formato Mermaid, representando a modelagem relacional proposta pela IA. O usuário utiliza esta saída para renderizar e visualizar as tabelas e relacionamentos sugeridos.

**O que recebe:** Apenas o parâmetro de rota `session_id`.

**O que devolve:**
```json
{
  "session_id": "f0e9b9d3-...",
  "format": "mermaid",
  "content": "erDiagram\n    users { ... }",
  "summary": "Descrição sumarizada opcional do diagrama."
}
```

---

### 4. Rejeitar a Proposta
**Endpoint:** `POST /analysis/{session_id}/reject`
**Para que serve:** O usuário invoca essa rota caso a modelagem/diagrama sugerida pela IA não atenda às expectativas. O usuário envia em texto livre os motivos.

**O que recebe (JSON Body):**
```json
{
  "user_email": "dba@exemplo.com",
  "feedback": "A tabela 'users' não deveria ter o campo 'cpf', favor retirar. Também mude a relação de orders para 1:N."
}
```

**O que devolve:**
```json
{
  "session_id": "f0e9b9d3-...",
  "status": "awaiting_approval",
  "approval_state": "rejected",
  "rejection_feedback": "A tabela 'users'...",
  "updated_at": "2026-05-14T10:05:00Z"
}
```
*Após isso, o fluxo retoma o processo enviando o feedback para a IA repensar a modelagem e passará novamente por todos os steps até ficar pausado novamente.*

---

### 5. Aprovar a Proposta
**Endpoint:** `POST /analysis/{session_id}/approve`
**Para que serve:** Usada quando o usuário visualizou o diagrama e considerou o trabalho aprovado. Ao dar o aceite, o sistema sairá da pausa, processará deterministicamente o arquivo `.sql` de alteração/criação das tabelas e o submeterá juntamente com o diagrama Mermaid diretamente na task do OpenProject.

**O que recebe (JSON Body):**
```json
{
  "user_email": "dba@exemplo.com"
}
```

**O que devolve:**
```json
{
  "session_id": "f0e9b9d3-...",
  "status": "awaiting_approval",
  "approval_state": "approved",
  "updated_at": "2026-05-14T10:10:00Z"
}
```
*O status de aprovação mudou, o workflow acordará em background e avançará com a atualização no OpenProject.*

---

### 6. Ver Resumo Completo (Opcional)
**Endpoint:** `GET /analysis/{session_id}`
**Para que serve:** Puxa o objeto completo de estado processado até o momento, contendo as recomendações textuais de performance, segurança, SQL e metadados adicionais.

---

### 7. Ver SQL Produzido (Opcional)
**Endpoint:** `GET /analysis/{session_id}/sql`
**Para que serve:** Retorna o `.sql` de Data Definition Language (DDL) e de migrações que a plataforma gerou. **A plataforma nunca roda esse código de forma automática, apenas entrega e anexa no OpenProject.**

---

## Testando com Insomnia

Para testar no Insomnia, basta seguir estes passos:

1. **POST Request (Start)**: 
   - Crie uma rota `POST` para `http://localhost:8000/analysis/start`
   - Adicione o payload JSON contendo os dados do seu banco, ID da task no seu OpenProject e seu token do OpenProject.
   - Envie. Guarde o `session_id` que ele retornou.
2. **GET Request (Status)**:
   - Crie uma rota `GET` para `http://localhost:8000/analysis/<COLE_O_SESSION_ID_AQUI>/status`
   - Dispare até que o status retorne `"awaiting_approval"`.
3. **GET Request (Diagrama)**:
   - Crie uma rota `GET` para `http://localhost:8000/analysis/<COLE_O_SESSION_ID_AQUI>/diagram`
   - Pegue o valor de `content` (o Mermaid) e jogue em um renderizador online (como o mermaid.live) para ver a modelagem.
4. **POST Request (Approve)**:
   - Crie uma rota `POST` para `http://localhost:8000/analysis/<COLE_O_SESSION_ID_AQUI>/approve`
   - Body JSON: `{ "user_email": "seu_email@exemplo.com" }`
   - Envie. Se checar a sua Task lá no OpenProject logo depois, verá que a plataforma já criou um comentário e anexou os arquivos `erd.mmd` e `migration.sql`.

## Security guarantees

| Asset                       | Source                            | Stored as           | In logs | In prompts | In state |
|-----------------------------|-----------------------------------|---------------------|---------|------------|----------|
| Gemini API key              | `GEMINI_API_KEY` env              | `SecretStr`         | never   | never      | never    |
| OpenProject API token       | `OPENPROJECT_API_TOKEN` env       | `SecretStr`         | never   | never      | never    |
| Backend Postgres password   | `POSTGRES_PASSWORD` env           | `SecretStr`         | never   | never      | never    |
| Customer DB password        | API request body                  | Fernet-encrypted    | never   | never      | never    |
| Credential encryption key   | `CREDENTIAL_ENCRYPTION_KEY` env   | `SecretStr`         | never   | never      | never    |

The structlog sanitizer redacts password/key/token patterns in any log
event; the global exception handler runs the same sanitizer on error
messages before returning them.

## Testing

```bash
pytest backend/tests/unit
```

Unit tests cover the deterministic services that never call Gemini:
sanitizer, credential vault, Mermaid renderer, SQL generator, settings.
