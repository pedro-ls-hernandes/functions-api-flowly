# Flowly Voice API Mock

API HTTP em Python para processar comandos de voz e executar operações no Flowly. 
**Roda completamente mockada, sem backend ou banco de dados**, usando dados locais em `mock_data.json`.

## Overview

- **Pronta para Google Cloud Functions** via HTTP Trigger
- **MockAPI com dados locais** para testes rápidos
- **Compatível com Cloud Run** via Functions Framework
- **Suporte completo a comandos de voz** traduzidos em ações

## Quick Start (Local)

### Terminal / CLI
```bash
cd flowly_assistente_mock
python -m venv venv
venv\Scripts\activate  # ou `source venv/bin/activate` no Linux/Mac
pip install -r requirements.txt
python cli.py
```

### HTTP Server (Functions Framework)
Ideal para testar como estará em Google Cloud Functions.

```bash
cd flowly_assistente_mock
pip install -r requirements.txt
functions-framework --target trigger_http --port 8080
```

Teste em outro terminal:
```bash
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -d '{"utterance":"meu perfil"}'
```

### Docker

```bash
cd flowly_assistente_mock
docker build -t flowly-voice-api:latest .
docker run --rm -p 8080:8080 flowly-voice-api:latest
```

## Como Funciona

1. **Entrada**: POST com `utterance` (texto do comando de voz)
2. **Parsing**: Identifica o comando usando fuzzy matching (~78% default)
3. **Resolução**: Converte "nomes" em IDs (equipes, tarefas)
4. **Execução**: Aplica a ação no mock data
5. **Resposta**: JSON com resultado + texto para TTS

## API Reference

### Endpoint
```
POST / 
Content-Type: application/json
```

### Request Body

```json
{
  "utterance": "minhas tarefas",
  "user_type": "admin",
  "me_user_id": "507f1f77bcf86cd799439011",
  "params": {}
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `utterance` | string | ✓ | Comando de voz (texto) |
| `user_type` | string | ✗ | `"admin"` ou `"user"` (default: env var ou "admin") |
| `me_user_id` | string | ✗ | ID do usuário autenticado (default: env var) |
| `params` | object | ✗ | Parâmetros adicionais (task_id, equipe, etc) |

### Response (Success)

```json
{
  "ok": true,
  "command": {
    "key": "my_tasks",
    "title": "listar minhas tarefas",
    "score": 98
  },
  "user_type": "admin",
  "result": [
    {
      "_id": "507f1f77bcf86cd799439011",
      "descricao": "Implementar autenticação",
      "status": "aberto"
    }
  ],
  "reply_text": "Ok. Encontrei 3 itens."
}
```

### Response (Error)

```json
{
  "ok": false,
  "error": "unrecognized_command",
  "reply_text": "Não consegui identificar o comando. Pode repetir?"
}
```

## Exemplos de Comandos

### Tarefas
```json
{"utterance": "minhas tarefas"}
{"utterance": "listar backlog"}
{"utterance": "detalhes da tarefa Implementar autenticação"}
{"utterance": "marcar como concluído", "params": {"task_id": "Implementar autenticação"}}
{"utterance": "atribuir para mim", "params": {"task_id": "Revisar PR"}}
```

### Equipes
```json
{"utterance": "minhas equipes"}
{"utterance": "criar equipe Backend"}
{"utterance": "membros da equipe Backend"}
```

### Usuários
```json
{"utterance": "meu perfil"}
{"utterance": "listar usuários"}
{"utterance": "buscar usuário João"}
```

### Comentários
```json
{"utterance": "adicionar comentário Pronto para revisar", "params": {"task_id": "Implementar autenticação"}}
```

## Variáveis de Ambiente

```bash
# Tipo de usuário padrão (se não enviado no request)
FLOWLY_USER_TYPE=admin

# ID do usuário autenticado
FLOWLY_ME_USER_ID=507f1f77bcf86cd799439011

# Caminho do arquivo de mock data
FLOWLY_MOCK_DATA_PATH=/tmp/mock_data.json

# Threshold de matching (0-100, default 78)
FLOWLY_MATCH_THRESHOLD=78

# CORS Origin (default: "*")
FLOWLY_CORS_ORIGIN=*
```

## Mock Data

Edite `mock_data.json` para criar seus próprios usuários/equipes/tarefas:

```json
{
  "users": [
    {"_id": "...", "nome": "João Silva", "tipo": "admin"}
  ],
  "equipes": [
    {"_id": "...", "nome": "Backend"}
  ],
  "tarefas": [
    {"_id": "...", "descricao": "Implementar autenticação"}
  ]
}
```

## Deployment

### Google Cloud Functions (Gen2)

1. Deploy via gcloud CLI:
```bash
gcloud functions deploy flowly-voice-api \
  --runtime python312 \
  --trigger-http \
  --allow-unauthenticated \
  --entry-point trigger_http \
  --region us-central1 \
  --source flowly_assistente_mock
```

2. Ou via Cloud Run:
```bash
gcloud run deploy flowly-voice-api \
  --source flowly_assistente_mock \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## Estrutura do Projeto

```
flowly_assistente_mock/
├── main.py              # Entrypoint para Cloud Functions
├── function.py          # Handler HTTP principal (flowly_mock, trigger_http)
├── api_client.py        # Mock API client (sem backend)
├── command_parser.py    # Parser de comandos (fuzzy matching)
├── commands.py          # Definição dos comandos suportados
├── mock_data.json       # Dados mockados (usuários, tarefas, etc)
├── requirements.txt     # Dependências Python
├── Dockerfile           # Container para Cloud Run
├── .env.example         # Template de variáveis de ambiente
└── README.md            # Este arquivo
```

## Comandos Suportados

- ✓ Gerenciar tarefas (listar, detalhar, atribuir, atualizar status)
- ✓ Gerenciar equipes (criar, listar, membros)
- ✓ Gerenciar usuários (perfil, buscar, listar)
- ✓ Comentários e subtarefas
- ✓ Timers
- ✓ Mensagens de equipe

Veja `commands.py` para lista completa.
