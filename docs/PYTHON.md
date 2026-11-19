# Computational Thinking with Python — demonstração

## Problema e solução

Zestia trata a dificuldade de compatibilizar ofertas de alimentos com pedidos de organizações em Porto Alegre. A API persiste organizações, alimentos e pedidos, aplica regras de autorização/quantidade e calcula indicadores. O programa `scripts/demo.py` demonstra processamento de dados e apoio à decisão sem exigir banco ou credenciais.

## Dados e reprodução

- Entrada: [demo.json](../data/demo.json), cenário inteiramente sintético criado para a disciplina.
- Referência temporal: 19/11/2026, explicitada no dataset para tornar a validade reproduzível.
- Saída: [demo-report.json](../data/demo-report.json), gerada pelo programa, não editada manualmente.
- Quantidades: strings decimais em kg, com precisão de gramas; organizações e identificadores fictícios.
- Os arquivos não contêm credenciais, pessoas atendidas ou dados de instituições reais.

Após o [Quickstart](../README.md#computational-thinking-with-python):

```sh
.venv/bin/python scripts/demo.py
.venv/bin/python scripts/demo.py --output /tmp/zestia-report.json
```

Não há alteração no banco da aplicação, leitura de arquivos de ambiente nem envio de e-mail.

## Resultados e decisão

| Resultado do cenário | Interpretação |
|---|---|
| 33 kg cadastrados | Quantidade dos lotes existentes, inclusive o lote vencido preservado no histórico |
| 27 kg solicitados | Soma das quantidades em todos os pedidos, incluindo rejeitados |
| 12 kg aprovados | Quantidade aprovada; não representa entrega ou alimento salvo |
| 4 PENDING, 1 APPROVED, 1 REJECTED | Distribuição persistível dos estados |
| Feijão vence em 20/11; arroz em 22/11 | Analisar primeiro as ofertas ainda válidas com vencimento mais próximo |
| Pedidos de arroz de 6 kg e 4 kg, saldo de 8 kg | Cada pedido cabe isoladamente; ambos não podem ser aprovados integralmente |
| Pedido de pão com validade em 18/11 | No snapshot de 19/11, não deve avançar para aprovação |

Os checks são independentes, sem reservar pendentes. Eles analisam quantidade e validade; aprovação real continua exigindo autenticação, propriedade e verificação na API, com saldo atualizado sob bloqueio. O programa rejeita referências inválidas, duplicatas, pedido próprio e excesso já aprovado. Não há previsão automática, certificação sanitária ou recomendação logística.

## Evidência

[Testes de análise](../tests/unit/test_analysis.py) verificam resultados, fronteiras e entradas inválidas. [Teste PostgreSQL](../tests/integration/test_demo_dataset.py) carrega o mesmo dataset num banco descartável e compara as quantidades com o repositório real de métricas. O gate completo não permite testes ignorados. Resultados deste dataset não substituem entrevistas ou validação local.
