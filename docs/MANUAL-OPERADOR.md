# Manual de uso — Auditor de Sites (1 página)

**Entrar:** e-mail, senha e código de 6 dígitos do aplicativo autenticador. No primeiro acesso, escaneie o QR code. Após 5 erros, a conta fica bloqueada por 15 minutos. A sessão dura 8 horas.

## O fluxo, do lead ao fechamento

1. **Buscar** — *Buscas → Nova busca*: escolha a categoria (ou digite um termo), a UF e a cidade da lista. Em até 2 minutos a lista aparece. Empresas sem site já chegam como **“Sem site”**: são leads para um site do zero.
2. **Selecionar e auditar** — marque as empresas na tabela (filtros: situação do site, nota, bairro) e clique em **Auditar selecionados** (até 50). Cada auditoria leva até 3 minutos. Para um site avulso: *Leads → URL avulsa*.
3. **Revisar** — abra a auditoria e clique em **Revisar achados**. Achados de regra já vêm confirmados; os de IA (“avaliação assistida”) vêm **pendentes**. Atalhos: **C** confirma, **E** edita, **D** descarta, **J/K** navega. Reescreva em linguagem de dono de negócio, com tom construtivo.
4. **Gerar o relatório** — *Preparar relatório*: ajuste o texto de abertura, a ordem (os 5 primeiros viram o “Top 5”) e os concorrentes. Clique em **Gerar link + PDF**. Confira a pré-visualização à direita.
5. **Enviar** — *Abrir no WhatsApp* (envio individual, nunca em massa) ou baixe o PDF. Depois clique em **Marcar como enviado**: o lead passa para “Relatório enviado”. Na lista de relatórios você vê quantas vezes o link foi aberto.
6. **Negociar** — na ficha do lead, mova o funil (*Em negociação → Fechado* ou *Perdido*) e registre anotações.
7. **Fechou?** — *Briefing do site novo*: cada problema confirmado vira um requisito, junto com o checklist da categoria e as metas (nota ≥ 85 e +30 pontos). Exporte em Markdown para a equipe de desenvolvimento.
8. **Entregou?** — use **Reauditar** no site novo para provar a melhoria e marque o lead como *Entregue*.

## Bom saber

- **“Não medido”** numa etapa quer dizer que a ferramenta não estava disponível (ex.: sem chave da IA) ou que o site bloqueou o robô. A nota considera só o que foi medido, e o relatório informa isso.
- **Site bloqueia o robô (Cloudflare/captcha)?** Ele é marcado como “não auditável”. Faça a análise manual e adicione achados com *Achado manual*.
- **Link enviado errado?** No editor do relatório, clique em **Revogar link**: ele para de funcionar na hora.
- **Pedido de exclusão (LGPD)?** Na ficha do lead: *Excluir dados (pedido LGPD)*. Isso apaga a empresa, as capturas e os relatórios, e registra o atendimento.
- **Somente o Administrador** altera pesos, checklists, regras, prompts, a marca e os usuários (*Configurações*).
- O custo das APIs no mês aparece no Painel; ao passar de 80% do teto, surge um alerta.
