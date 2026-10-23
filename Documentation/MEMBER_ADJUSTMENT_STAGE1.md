# Recortar / Ajustar Membro — Etapa 1

Data: 21/10/2026. Steel Structures 0.7.0, branch `develop/0.7.0`.
Base preservada: `fd96c2fe34586d9dbc099994e2e0bd4d7e02a768`.
Leitura integral prévia de `MEMBER_ADJUSTMENT_TECHNICAL_AUDIT.md`.

**Resultado: GO para validação manual do usuário.** A prévia usa a geometria
candidata real, e a confirmação recusa candidatos inválidos antes de alterar
o documento. Não há autorização de publicação implícita nesse resultado.
Não foram executados stage, commit, push, merge, tag ou release. O índice
permanece vazio. Os arquivos locais de StructuralPlate, Gussets e estudos
foram preservados; o relatório de auditoria anterior não foi alterado.

## 1. Diagnóstico nativo anterior à correção

O risco da auditoria foi **confirmado**, antes das alterações de produção.
O cenário cria um membro independente ou uma diagonal de treliça, seleciona
uma face a 25% do eixo nominal e tenta ajustar o início com gap positivo de
duas vezes o comprimento. Isso cruza as extremidades. Foram combinados
`LengthLimit`/`PlaneCut` e `Fixed`/`Associative`: oito casos.

| Alvo | Resultado original | Propriedades e histórico | Geometria e persistência |
| --- | --- | --- | --- |
| Independente, quatro casos | Operação recusada | Rollback, sem novo Undo | Estado anterior recuperado |
| Diagonal gerada, quatro casos | Operação aceita indevidamente | Ajuste inválido gravado; Undo aumentava de 1 para 2 | Shape anterior preservada; estado inválido permanecia no FCStd reaberto |

O executor de filhos protege legitimamente a última Shape quando uma nova
geração falha. Ele registrava `GenerationStatus = "Erro: ..."`; o controlador
antigo verificava somente se havia uma Shape não nula e confirmava a transação.
Portanto, a proteção da Shape era correta; a interpretação dessa proteção
como sucesso da operação atual era o defeito.

No pai, `AppliedState` não mudou e `GenerationState` continuou `Valid`.
A leitura de massa física detectou o filho inválido e ficou indisponível,
com diagnóstico. Isso evita afirmar uma massa física válida, mas não evitava
a gravação indevida do ajuste. Não foi observado dano adicional ao registro
de filhos do pai nesse cenário.

Evidência original imutável nesta rodada:
[`1792627205698266500_reproduction_Classic_zz0254dg`](../test-results/member_adjustment_stage1/1792627205698266500_reproduction_Classic_zz0254dg/).
Contém `risk-cases.json` com antes/depois/restaurado, oito FCStd, logs,
`result.json` e manifesto SHA-256 das fontes. Resultado: quatro aceitações
inválidas em oito tentativas. O modo `--phase reproduction` pressupõe as
fontes de produção anteriores à correção; na árvore atual usar `stage1`.

## 2. Avaliação candidata e confirmação

O controlador acrescenta `AdjustmentCandidate` e `evaluate()`:

1. Resolve novamente a referência atual e monta somente os valores do slot
   escolhido, mantendo a outra extremidade.
2. Executa `member_batch.prepare_member()` sobre um snapshot em memória,
   sem copiar a Shape anterior e sem criar objeto de documento.
3. Reutiliza `StructuralMemberProxy.execute()`, incluindo seção, inserção,
   offsets, extensões, referências, cortes OCC e composição de fitting já
   existente. Não existe outro algoritmo de corte para a prévia.
4. Exige Shape nova não nula, válida e com volume positivo e finito. Falhas
   são diagnosticadas no painel. Nenhum comprimento, gap ou plano é ajustado
   automaticamente para tentar obter sucesso.

Para membros independentes, o avaliador preserva a orientação completa do
`Placement`, inclusive rotações manuais que não estão descritas apenas pelo
roll da seção. O parâmetro opcional de `prepare_member()` mantém seu padrão
anterior nos consumidores existentes e nos filhos gerados.

No OK há nova avaliação, mesmo que uma prévia anterior estivesse válida.
Só depois disso é aberta a transação existente. O recompute definitivo usa
o mesmo pipeline. O controlador verifica Shape, estado `Invalid`, status do
filho gerado, comprimento ajustado, massa, volume e Placement contra o
candidato. Uma falha nessa fase aborta a transação. Remover ajuste também
passa por avaliação candidata, preservando a outra ponta.

Não se usa a simples existência de uma Shape anterior como evidência de
sucesso. A proteção já existente da última Shape de filhos não foi removida.

### Correção necessária de Undo/Redo

O gate encontrou um segundo defeito durante corte inicial de um pilar
independente com rotação manual: desfazer restaurava a base do Placement,
mas o callback interpretava essa restauração como movimento do usuário.
No cenário observado, o eixo nominal sofria deslocamento indevido de
215 mm. O volume restaurado, sozinho, não revelava o problema.

`member.py:onChanged()` agora distingue replay/rollback por
`Document.Transacting`. Durante esse replay, não deriva novos pontos,
comprimento ou giro de propriedades que o próprio histórico está
restaurando; atualiza os caches internos de Placement, rotação e comprimento.
A mudança não cria propriedades, schema ou observadores. Foram verificados
Undo/Redo do corte inicial/final, remoção, movimento rígido, roll e Length,
além do rollback de falha após recompute.

## 3. Prévia e lifecycle

`MemberAdjustmentPreview` exporta uma cópia da Shape candidata com seu
Placement global por `writeInventor()` e a apresenta em um branch Coin
temporário. O sólido aparece em ciano, com transparência discreta e
`UNPICKABLE`. A tesselação é a representação normal do BRep para o viewport;
a operação geométrica não é aproximada por um envelope ou eixo.

O original é mascarado somente no `SwitchNode` do ViewProvider. A ferramenta
nunca escreve `ViewObject.Visibility`. Ao limpar, restaura o estado anterior
do switch e respeita alterações de visibilidade e modo de exibição feitas
explicitamente pelo usuário. Não existem auxiliares persistentes, Shapes de preview na árvore,
nem transações de preview.

Mudanças nos controles e na referência selecionada recalculam a prévia.
Um QTimer de 180 ms, filho do formulário, detecta alterações externas do
membro/referências e troca de vista ativa. Ele compara assinaturas; não faz
um corte a cada tick. Durante digitação do gap, a atualização ocorre ao
concluir a edição, evitando cálculo OCC em cada tecla.

Se o cálculo falhar, a prévia é removida, o original reaparece, o diagnóstico
fica visível e o OK é desabilitado. Mensagens herdam a cor do tema; erros
recebem destaque de peso de fonte, evitando texto escuro sobre tema escuro.

OK, Cancelar, Esc com foco em um controle, fechar formulário, fechamento
nativo da tarefa, exclusão do alvo e fechamento do documento convergem para
limpeza idempotente. Ela remove o branch, para/desconecta o timer e remove
o observador de seleção já existente. Não foi acrescentado observador de
documento nem callback de viewport. Na destruição nativa do formulário,
o callback do comando não tenta fechar recursivamente o TaskDialog.

## 4. Arquivos deste incremento

| Arquivo | Alteração |
| --- | --- |
| `freecad/SteelStructures/interactive/member_adjustment_controller.py` | Avaliação candidata, diagnóstico e confirmação segura |
| `freecad/SteelStructures/interactive/member_adjustment_preview.py` (novo) | Branch Coin transiente e máscara/restauração do original |
| `freecad/SteelStructures/interactive/member_adjustment_task_panel.py` | Preview reativo, bloqueio de OK e lifecycle |
| `freecad/SteelStructures/member_batch.py` | Opção de preservar Placement e rejeição de volume não finito |
| `freecad/SteelStructures/member.py` | Proteção de derivações durante Undo/Redo e rollback |
| `freecad/SteelStructures/commands.py` | Fechamento sem reentrada na destruição nativa |
| `tests/test_member_adjustment_controller.py` | Avaliação destacada, falhas e referência alterada antes do OK |
| `tests/test_member_adjustment_preview.py` (novo) | Ownership Coin, máscaras, falhas e limpeza |
| `tests/test_member_placement.py` | Regressões do replay de transação e stub de Shape vazia |
| `tests/manual_member_adjustment_stage1.py` (novo) | Reprodução e gate instrumentado no FreeCAD real |
| `scripts/run_member_adjustment_stage1_gate.py` (novo) | Execução isolada por tema, evidências e filtros nativos |
| `Documentation/MEMBER_ADJUSTMENT_STAGE1.md` (novo) | Este relatório |

Não foram alterados catálogos, propriedades persistentes, serialização,
SchemaVersion, nomenclatura de perfis ou resolvedores de meia-esquadria.
Não foi introduzido botão Aplicar, associação nova ou referência por sólido.

## 5. Validações

### Python focado

**308 testes aprovados, zero falhas e zero skips.** Comando final:

```powershell
python -B -m unittest tests.test_member_adjustment_geometry tests.test_member_adjustment_reference tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_adjustment_task_panel tests.test_member_associative_adjustment tests.test_member_plane_cut tests.test_member_placement tests.test_member_length tests.test_member_orientation tests.test_member_axis_source tests.test_member_source_axis_preview tests.test_member_axis_creation tests.test_member_creation_types tests.test_member_controller tests.test_truss_physical_mass tests.test_fitting_c5a tests.test_fitting_c6g_assembly tests.test_ridge_fitting tests.test_truss_regeneration_rollback tests.test_command_registration tests.test_column_command tests.test_general_tools
```

Inclui falha simulada de OCC, volume não finito e estado nativo inválido com
Shape anterior válida. Os doubles verificam contratos de ownership e
transações; a fidelidade OCC/Pivy/Qt foi verificada separadamente no nativo.
A suíte completa não foi executada, conforme o escopo da etapa.

### FreeCAD 1.1.4, Python 3.11 / Qt6

```powershell
python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme Classic
python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme "FreeCAD Dark"
python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme OpenDark
```

| Tema | Resultado final | Evidências em `test-results/member_adjustment_stage1/` |
| --- | --- | --- |
| Classic | 288 verificações aprovadas | `1792628808730537000_stage1_Classic__af_mdjw` |
| FreeCAD Dark | 288 verificações aprovadas | `1792628824525156100_stage1_FreeCAD_Dark_nin9kx4j` |
| OpenDark | 288 verificações aprovadas | `1792628866033300800_stage1_OpenDark_udy91xuk` |

Em cada tema: **zero aceitações inválidas em oito casos de risco**, zero
erros capturados de callbacks Python/Qt e zero ocorrências nos filtros dos
logs nativos. Filtros incluem Traceback, objeto C++ já destruído, Access
violation, exceção Base não tratada, heap corruption, assert e QThread
destruída. São 864 verificações nos três gates finais; não são 864 testes
unitários independentes.

Cobertura nativa adicional:

- Oito fluxos válidos: W em X/Y, pilar RHS em Z, U simples inclinado e
  diagonal de treliça com ambas as extremidades ajustadas; Detailed e
  Simplified, offsets/extensões e orientação manual preservados.
- Cortes perpendiculares e inclinados, prolongamento axial além do eixo
  nominal, limitação axial por Face e Edge, modos
  Fixed/Associative, gaps zero/positivo/negativo e referência movida durante
  a tarefa. Os testes geométricos focados também exercitam o pipeline existente.
- Prévia e resultado definitivo comparados por volume, centro ponderado dos
  sólidos, bounds e diferença booleana nos dois sentidos. Bounds curvos têm
  tolerância de 0,01 mm por cache de tesselação OCC; a diferença booleana
  exige volume residual inferior a `1e-5 mm³` nos dois sentidos.
- Nenhuma alteração do original, objetos de documento ou Undo ao variar
  somente a prévia; confirmação cria uma ação reversível.
- Recusa de candidato inválido depois de prévia válida; rollback de falha
  injetada depois do recompute em pilar e filho gerado.
- Remoção de um slot sem perder o oposto, Undo/Redo, FCStd aceito reaberto,
  massa e comportamento fixo/associativo após restauração.
- Massa física de treliça disponível e igual à soma dos volumes reais vezes
  a densidade; comprimentos, massa do membro e eixo nominal preservados no
  histórico e na restauração.
- Cancelar, Esc em campo filho, fechar formulário, `Gui.Control.closeDialog`,
  trocar alvo, excluir referência/alvo, alternar visibilidade/modo de exibição, mudar vista
  3D ativa, comando público e fechar documento; sem timer/seleção/branch
  residual nos caminhos verificados.

Cada pasta contém manifesto de fontes, checks, logs, FCStd e capturas.
As capturas da Task View foram inspecionadas, assim como os renders nativos
`candidate-viewport.png` e `candidate-viewport-theme.png`. A captura Qt da
janela inteira na execução isolada pode apresentar viewport vazio ou
artefatos de composição OpenGL; por isso ela serve para ler a Task View,
não como prova isolada do sólido. Os renders via `saveImage()` e a comparação
OCC foram usados para avaliar a prévia geométrica.

### Integridade

`python scripts/check_project.py`: aprovado, incluindo sintaxe, arquivos,
versão e integridade dos catálogos. `git diff --check`: aprovado.
Branch/HEAD conferidos e índice vazio ao final.

## 6. Limites conhecidos

- GO refere-se à validação manual; não substitui aprovação do usuário sobre
  produtividade e apresentação em sua sessão normal do FreeCAD.
- O cálculo OCC roda no thread da interface. Cortes muito complexos podem
  causar uma pausa; não foram introduzidos workers ou observers adicionais.
- Alterações externas são detectadas pelo timer e pelas assinaturas atuais
  dos inputs/subelementos. Não há promessa de atualização durante cada etapa
  intermediária de um recompute externo ainda não concluído. O OK sempre
  reavalia a referência atual.
- A prévia pertence à vista 3D ativa e é transferida ao trocar de vista;
  não é duplicada simultaneamente em todas as vistas do documento.
- Referências associativas podem tornar-se inválidas depois da confirmação.
  O tratamento paramétrico preexistente, inclusive proteção da última Shape
  de filhos e diagnóstico de massa indisponível, continua em vigor. Esta
  etapa impede aceitar um candidato já inválido; não migra nem repara
  automaticamente documentos antigos com propriedades inválidas.
- Sem meia-esquadria automática genérica, sólido inteiro, tipos novos de
  associação, Aplicar ou alterações no fitting automático de treliças.

## 7. Roteiro de validação manual

1. Em Classic, FreeCAD Dark e OpenDark, abrir Recortar / Ajustar Membro com
   um membro W, um pilar tubular e um U simples, em orientações diferentes.
   Selecionar explicitamente uma Face plana; variar operação, extremidade e
   gap. Conferir a prévia ciano e a legibilidade da Task View.
2. Usar uma face inclinada e testar início/fim. Em Limitar comprimento,
   testar uma Edge reta transversal. Conferir que planos paralelos/arestas
   não aceitas apresentam diagnóstico sem modificar o membro.
3. Manter vínculo, mover a referência e recomputar: conferir prévia e depois
   geometria associativa. Repetir sem vínculo, confirmar, mover a referência
   e conferir que o corte fixo permanece.
4. Depois de uma prévia válida, informar gap que cruze as pontas. Conferir
   remoção da prévia, reapresentação do original e OK desabilitado. Cancelar
   e conferir propriedades, massa, eixo e ausência de Undo adicional.
5. Testar Cancelar, Esc com foco no gap, fechar tarefa, trocar alvo/vista e
   fechar documento. Reabrir a ferramenta e confirmar ausência de resíduos.
6. Confirmar um corte inicial no pilar, com rotação manual, e cortes em
   ambas as pontas de uma diagonal de treliça. Conferir Undo/Redo e Remover
   ajuste sem deslocamento do eixo ou perda do slot oposto.
7. Salvar/reabrir FCStd e recomputar. Conferir estado das referências,
   comprimento nominal/ajustado, orientação, geometria e massa física da
   treliça.

Não foi identificado bloqueador arquitetural para esta etapa. Publicação e
suíte completa ficam para o fechamento posterior solicitado pelo usuário.
