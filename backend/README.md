# Backend

## Configuração

A tabela `leituras_gas` já deve existir no PostgreSQL antes de iniciar a API.
O backend não cria nem altera tabelas durante a inicialização.

1. Instale as dependências com `pip install -r requirements.txt`.
2. Configure `DATABASE_URL` (veja [`.env.example`](./.env.example)).
3. Inicie a API na raiz do projeto:

```bash
uvicorn backend.main:app --reload --port 8000
```

O frontend conecta em `http://localhost:8000` por padrão. Para outra URL, use
`VITE_API_URL` antes de executar o Vite.

## Operação

O painel não usa dados simulados. As leituras são exibidas somente depois que
forem recebidas do Arduino pelo WebSocket ou consultadas no histórico do banco.

Endpoints disponíveis:

- `GET /health`
- `GET /api/leituras?inicio=<ISO-8601>&fim=<ISO-8601>`
- `POST /api/leituras`
- `WebSocket /ws`
