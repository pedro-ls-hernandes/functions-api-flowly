# Flowly Voice API Mock

API HTTP em Python para processar comandos de voz e executar operações no Flowly. A API funciona através do **Google Cloud Functions**, 
rodando completamente mockada, sem backend ou banco de dados, usando dados locais em `mock_data.json` a fim de testes da atividade.
O funcinamento coeso da API será entregue junto ao projeto final. Você pode encontrar nosso [aqui](https://github.com/FATEC-Mobile-Group/flowly-2.0)

## Arquitetura

```
Requisição HTTP
    ↓
function.py (flowly_mock)
    ↓
CommandParser (command_parser.py) → identifica o comando
    ↓
Match (comando + parâmetros extraídos)
    ↓
_execute() → chama api_client
    ↓
FlowlyAPIClient (api_client.py) → acessa mock_data
    ↓
Resposta JSON
```

## Justificativa

Adotar uma arquitetura serverless orientada a eventos através do Google Cloud Functions para esta funcionalidade, em detrimento de um endpoint comum na API principal, traz vantagens estratégicas cruciais:

**Isolamento de Carga e Escalabilidade Independente:** O processo de parsing de texto, cálculos de similaridade de strings (fuzzy matching) e resolução de entidades é computacionalmente mais volátil e pesado do que as operações tradicionais de CRUD da API. Isolando-o em uma Cloud Function, garantimos que picos de uso do assistente de voz escalem de forma totalmente independente, sem consumir a CPU/Memória do backend principal e sem comprometer a estabilidade do restante do sistema.

**Eficiência de Custos (Pay-per-use):** Comandos de voz tendem a ser utilizados de forma esporádica ao longo do dia. Em uma infraestrutura tradicional, haveria um servidor rodando e consumindo recursos continuamente para manter o endpoint ativo. Com o modelo serverless, o custo é cobrado estritamente pelo tempo de execução da requisição (ao milissegundo), reduzindo o desperdício a zero quando a funcionalidade não estiver sendo demandada.

**Desacoplamento e Manutenibilidade:** O assistente de voz funciona essencialmente como uma camada de tradução autônoma. Ao transformá-lo em um microsserviço independente, a equipe pode atualizar as regras gramaticais, os dicionários de sinônimos, os limiares de threshold e os pacotes de processamento de texto em commands.py sem a necessidade de buildar, testar ou realizar o deploy de toda a API principal do Flowly.

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

```bash
cd flowly_assistente_mock
pip install -r requirements.txt
functions-framework --target trigger_http --port 8080
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

## Como testar

O teste da API torna-se mais fácil utilizando uma IDE como Postman ou Insomnia, mas pode funcionar através do navegador ou então testes pelo terminal.

### Postman
1. Defina o método da requisição para `POST`
2. Defina o URL com o link do funcionamento da sua API *(Nuvem ou localhost)*
3. Confira se `Content-Type` está definido como `application/json`
4. No `Body`, selecione `RAW/json` e defina o Request Body *(Encontrado em exemplo logo abaixo)*

### Terminal/Navegador
1. Modifique o `curl` do modo que preferir, seguindo as referências abaixo.
```
curl -X POST "https://SUA-FUNCAO-URL/" `
  -H "Content-Type: application/json" `
  -d '{"utterance":"meu perfil"}'
```
2. Faça a requisição.

## API Reference

### Endpoint
```
POST / https://functions-api-flowly-646126851973.southamerica-east1.run.app/
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

Edite `mock_data.json` para criar seus próprios usuários/equipes/tarefas se usado localmente:

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
