# Registro de prompts — Zestia

Resumo fiel de solicitações reais da sessão de trabalho com OpenAI Codex; não é uma transcrição integral. Dados privados e credenciais não são reproduzidos.

| Solicitação do proprietário | Trabalho realizado |
|---|---|
| Implementar pedidos como próxima parte do backend | Criação, aprovação/rejeição, histórico, limites transacionais e testes |
| Focar no backend, sem frontend, e seguir os quality gates | Métricas, filtros, validação com PostgreSQL e documentação RF/RN |
| Impedir cadastro público com o e-mail administrativo antes do bootstrap | Reserva de e-mail e testes de autorização |
| Manter apenas o admin com as credenciais configuradas | Substituição/rotação atômica, revogação de sessões e índice único |
| Evitar novos problemas de detecção de segredos no PR | Scanner obrigatório, controles positivos, logs redigidos e preservação das asserções de segurança |
| Escolher envio de e-mail simples/gratuito e documentar decisões | Seleção explícita de Gmail, adaptador SMTP com TLS e testes sem envio real |
| Finalizar todo o necessário e explicar o resultado | Dataset sintético, programa de análise, relatório reproduzível e documentação da disciplina |

O assistente verificou código e executou ferramentas; o proprietário tomou as decisões de escopo, política de admin e provedor. Não se afirma revisão individual de todos os membros nem submissão pelo Teams, ações que dependem da equipe.
