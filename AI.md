# Uso de inteligência artificial

OpenAI Codex foi utilizado como assistente na implementação do backend, testes, documentação, análise de requisitos e investigação de falhas de configuração e qualidade. O código inclui contribuições geradas por IA; não é declarado como inteiramente escrito manualmente.

A validação executada inclui Ruff, scanner de segredos, auditoria de dependências, testes com PostgreSQL real e migrações. Isso não comprova ausência de vulnerabilidades nem substitui revisão e compreensão pela equipe. O responsável deve compreender e explicar o código entregue.

As decisões relevantes estão em [DECISIONS.md](DECISIONS.md); o [registro de prompts](PROMPTS.md) resume solicitações reais desta sessão, sem credenciais. A regra atual proíbe o assistente de acessar arquivos privados de ambiente. A sessão teve uma ocorrência anterior de acesso/modificação indevida de configuração, reconhecida ao proprietário; as execuções de validação posteriores usaram configuração sintética e bancos descartáveis. Nenhuma configuração privada ou transcrição contendo segredos está incluída neste registro.
