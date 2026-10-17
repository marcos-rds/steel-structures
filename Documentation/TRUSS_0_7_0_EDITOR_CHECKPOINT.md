# Editor de Treliças — checkpoint local e quantitativos

Refinamento local sobre `develop/0.7.0`, HEAD `68dc4b4`. Sem alteração de versão, schema, geometria, topologia ou cálculo físico. Todas as alterações anteriores foram preservadas.

## Comportamento

- Ordem fixa em `QHBoxLayout`: **Cancelar · Aplicar · OK**, com espaçamento adicional após Cancelar. Removido Voltar ao painel.
- **Aplicar** reutiliza `panel.apply()` e o controlador transacional existente. Atualiza o mesmo owner, massa e checkpoint, mantendo a janela aberta. Aplicação sem mudanças não cria transação/recompute.
- **OK** usa a mesma aplicação e fecha apenas o diálogo. TaskPanel e sessão continuam disponíveis.
- **Cancelar/X** fecham apenas o diálogo e restauram o checkpoint após o retorno de `exec()`, quando diálogos filhos e observer modal já foram liberados. Nenhum Undo, aplicação física ou exclusão do owner participa desse rollback.
- Os botões do TaskPanel mantêm sua semântica anterior.

## Checkpoint

`TrussEditorCheckpoint` guarda cópias profundas da configuração completa e de `last_candidate`, eixo de referência, opções/seleções dos controles, doubles internos, texto parcial e metadados de unidades. A lista de espaçamentos também é preservada. O checkpoint é capturado na abertura e substituído somente após aplicação bem-sucedida.

A restauração bloqueia sinais e atualizações intermediárias, sincroniza controles e cartões de perfis e revalida pelo fluxo existente. Não restaura nem substitui baseline, `AppliedState`, estado realizado ou snapshot de persistência. Composições, Custom, intenções de ligações e Gussets permanecem no mesmo modelo compartilhado.

Antes do rollback, o controlador verifica contexto e persistência. Mudança externa do owner, Undo/Redo, remoção ou mudança da fonte Draft vinculada impede a restauração e mantém o conflito visível. Fontes Draft nunca são escritas pelo checkpoint.

Corrigida também a abertura com comprimento/espaçamento incompleto: a construção usa o double interno como semente, sem tentar interpretar texto parcial. Cancelar/X preservam a entrada incompleta original do TaskPanel.

## Quantitativos

Títulos **Peso total:** e **Peso linear:** em negrito discreto; valores em fonte normal, com duas casas decimais e unidades somente nos valores. Fórmulas, densidade e enumeração física dos componentes permanecem intactas.

- Atualizado: valores em `kg` e `kg/m`, sem aviso.
- Pendente: dois traços e um único relógio + `Aguardando aplicação`.
- Indisponível: diagnóstico no tooltip, sem aviso de espera.

O aviso ocupa uma coluna à direita, centralizada nas duas linhas. Em largura insuficiente passa para uma linha abaixo. Layout nativo e cores de paleta, sem QSS global. Seleção, foco e troca de aba continuam sem invalidar massa confirmada.

## Arquivos desta rodada

Produção:

- `interactive/truss_editor_checkpoint.py` (novo);
- `interactive/truss_task_panel.py`;
- `interactive/truss_topology_editor.py`;
- `interactive/truss_editor_fields.py`;
- `interactive/truss_task_widgets.py`.

Todos os caminhos de produção estão sob `freecad/SteelStructures/`. Testes ajustados: `test_truss_editor_actions.py`, `test_truss_editor_opening.py`, `test_gusset_preview_qt_c6q.py`, `test_truss_visual_polish.py`, `manual_freecad_truss_editor.py` e `manual_freecad_truss_editor_actions.py`.

## Validação

- **256 testes Python focados aprovados**, módulos de ações, abertura, sessão, Apply, lifecycle, massa, definição física, referências, Custom, composição, interconectores, alinhamento e rollback. Comando completo registrado em `test-results/truss_editor_checkpoint/validation_commands.txt`.
- **57 testes Qt aprovados** no Python do FreeCAD 1.1.4: `tests.test_truss_length_precision`, `tests.test_truss_reference_fields`, `tests.test_gusset_preview_qt_c6q`, `tests.test_truss_visual_polish`.
- Gates isolados do FreeCAD 1.1.4: `editor_actions` **124 por tema** (Classic, FreeCAD Dark, OpenDark); `editor` **405**; `apply` **54**; `lifecycle` **95**; `undo` **93**; `mass` **79**. Total lógico: **1.098 verificações**; repetições de diagnóstico não entram nessa contagem.
- `python scripts/check_project.py` e `git diff --check` aprovados.
- Sem suíte completa nesta rodada. Nenhum git add, commit ou push.

Os gates de integração precederam o último ajuste exclusivamente de contraste/pintura do relógio. Depois desse ajuste, foram repetidos os três gates modais por tema (124 cada) e os oito testes Qt de apresentação. Os manifests e essa diferença restrita estão registrados na auditoria.

Os gates exercitam modal real, repetição sem transação/recompute, mesmo owner, OK limpo/pendente, Cancelar após Aplicar, X, rascunho anterior à abertura, cópia profunda de Custom/compostos/Gussets, entradas parciais, conflito externo e fonte Draft, troca/fechamento de documentos, Plano de Trabalho e liberação de wrappers/previews/callbacks. O gate de massa inclui persistência/cópia e ausência de recomputes de leitura.

Foram inspecionadas capturas dos três temas e da disposição reduzida. Isso é validação GUI automatizada com inspeção das imagens; o teste interativo pelo usuário permanece pendente. DeprecationWarnings Qt e avisos nativos de tamanho mínimo de janela não indicaram falha funcional.

## Roteiro interativo curto — OpenDark / FreeCAD 1.1.4

1. No TaskPanel, altere a altura sem aplicar; abra o Editor, altere novamente e use Cancelar. Confira o rascunho anterior e o TaskPanel ainda aberto. Repita pelo X.
2. Abra o Editor, altere altura/perfil/Gusset e use Aplicar. Confira pesos atualizados; aplique novamente sem mudança e confirme ausência de nova transação no histórico.
3. Faça outra alteração e cancele: devem voltar os valores da última aplicação, mantendo os sólidos. Abra, altere e use OK: somente o Editor deve fechar.
4. Confira títulos em negrito, valores normais e unidades apenas junto aos números. Alterar fisicamente deve mostrar dois traços e um único relógio/aviso; reduzir a janela deve mover o aviso para baixo sem sobreposição.
5. Selecione nós e troque abas: a massa deve continuar atualizada. Em sessão separada, execute Undo externo e confira o bloqueio de aplicação/rollback. Termine usando os botões habituais do TaskPanel.

Evidências e auditoria de preservação: `test-results/truss_editor_checkpoint/`. Estudos Gusset, experimentos, arquivos FCStd e implementação física permanecem preservados. Alterações locais continuam sem staging ou publicação.
