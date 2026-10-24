# Meia-esquadria — fechamento técnico do MVP

Data: 23/10/2026. Branch `develop/0.7.0`.
Base: `2ef3b49d3e02fd111a8133240519a3ffc9068ca0`.

**GO técnico para commit local seletivo de 24 arquivos**, sem executá-lo.
Validação manual aprovada pelo usuário: encontros terminais a 90°/oblíquos,
preview simultâneo, seleção/cancelamento, Undo/Redo e reutilização sem recompute
manual, diagnósticos, rejeições e FCStd. A aprovação foi informada pelo usuário;
esta auditoria não a apresenta como teste manual realizado pelo agente.

Nenhuma funcionalidade foi acrescentada ou alterada neste fechamento. Foram
ajustadas somente duas listas esperadas de comandos em testes existentes e
criado este relatório. Não houve staging, commit, push, merge, tag ou release.
Metadados de versão e changelog permanecem intactos. Este GO não autoriza
publicação nem constitui preparação de release.

## Escopo consolidado

Foram lidos integralmente [a investigação](MEMBER_MITER_JOINT_INVESTIGATION.md)
e [o relatório do MVP e refinamento](MEMBER_MITER_JOINT_MVP.md), e auditados
seus módulos, testes e integração. As pendências de validação manual dos
relatórios anteriores são históricas e ficam superadas pela aprovação acima.

Permanecem: comando próprio bilateral, plano comum separador, duas candidatas
do pipeline real PlaneCut, preview Coin sem objetos de documento, cortes Fixed,
revalidação no OK, uma transação e um Undo. Não há propriedade nova, migração de
schema, Joint persistente ou referência cruzada entre os membros. O recompute
restrito aos participantes permite reutilização após Undo/Redo; fontes pendentes
continuam bloqueadas antes de qualquer recomputação automática. Estados das
fontes transitivas e Placements globais integram a assinatura do preview.

Domínio: dois membros independentes e retos, eixos coplanares concorrentes nas
pontas/raios exteriores, mesmo perfil Detailed e seções que efetivamente fecham.
W de abas paralelas, U simples/Ue, RHS e SHS estão na matriz. Orientações são
aceitas pela geometria real das tampas, não por igualdade numérica de roll.
Filhos de treliças, perfis distintos, ponta escolhida já ajustada, T/cruzamento,
eixos reversos/paralelos, aparo interior automático e associação entre os membros
continuam recusados. Não houve alteração em Gusset, StructuralPlate, Draft,
member.py, member_batch.py, clipper, geradores de seção ou catálogos.

O possível ressalto visual W não foi confirmado como defeito e não é tratado
como regressão aberta. Provas anteriores a 60°/90°/120° mostraram contato completo,
contornos coincidentes, Shapes válidas e interpenetração zero; o gate deste
fechamento repete W60/W90/W120. Nenhuma correção especulativa foi realizada.

## Árvores e método

Evidências desta rodada: `test-results/member_miter_closure/` no workspace da
auditoria. Os caminhos de evidência citados abaixo não fazem parte do commit.

- `baseline/`: extração exclusiva de `git archive --format=zip 2ef3b49...`.
- `candidate/`: a mesma base, sobreposta somente com os 24 caminhos inventariados.
- Workspace: árvore local completa, incluindo estudos e experimentos preservados.

Não foram criadas branches, worktrees registradas ou commits auxiliares. A
candidata não possui `.git` e não importa arquivos experimentais para funcionar.
O delta de conteúdo contra a base contém **exatamente 24 caminhos**, nenhum
extra/removido e nenhuma divergência contra os arquivos selecionados do workspace.
Os 20 caminhos do MVP foram acrescidos da investigação (referenciada pelo MVP),
deste fechamento e dos dois testes de integração corrigidos nesta auditoria.

O relatório final foi copiado para a candidata após consolidar os resultados;
essa atualização é documental. Código de produção, testes e runner da candidata
final são os mesmos executados. Hashes finais estão em `candidate-manifest.json`.

## Suíte Python completa e comparação

Executado em cada raiz, com o mesmo Python 3.11:

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
```

Um `sitecustomize` de auditoria registra os resultados do TextTestResult em JSON;
não seleciona, altera ou suprime testes. A descoberta e os critérios padrão do
unittest foram mantidos. Comandos, diretórios, tempos, retornos, logs e IDs estão
em `{baseline,candidate,workspace}-summary.json`, `*-unittest.log` e `*-cases.json`.

| Árvore final | Executados | Aprovados | Skips | Falhas/erros | Retorno |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base publicada `2ef3b49` | 1950 | 1801 | 149 | 0/0 | 0 |
| Candidata seletiva | 1994 | 1845 | 149 | 0/0 | 0 |
| Workspace completo | 1998 | 1849 | 149 | 0/0 | 0 |

A candidata adiciona **44 testes**: 18 de controlador, 11 de geometria, 5 de
preview e 10 de painel. Nenhum ID da base foi removido, nenhum resultado comum
piorou e todos os novos testes passaram. Os casos comuns de workspace e
candidata têm resultados idênticos. A comparação por ID está em `comparison.json`.

O workspace tem exatamente quatro casos adicionais de
`test_plate_qt_lifecycle_probe.LifecycleProbeSafetyTests`, todos aprovados e
externos ao incremento: exceção nativa capturada, assinaturas/timeout nativos,
falha Python com retorno zero e warning sem falha. Esse arquivo experimental
permanece excluído da candidata. Não há falha experimental ocultada ou removida
para obter o GO.

### Primeira tentativa e correção de integração

Houve cinco execuções completas: uma na base e duas em cada uma das outras
árvores. Na primeira, a base já passou; workspace e candidata tiveram as mesmas
duas falhas de expectativa de registro, respectivamente 1847/1843 aprovados,
149 skips e 2 falhas. Os artefatos integrais estão preservados em `attempt1/`.

Os testes eram:

- `test_grid_command.GridCommandTests.test_registration_and_resources`;
- `test_project_integrity.IdentityMigrationTests.test_only_new_command_ids_are_registered`.

Ambos exigiam uma lista exata ainda sem `SteelStructures_MiterMembers`. Foi
acrescentado somente esse ID, na posição correta, às duas listas. Não foi
removida ou relaxada nenhuma assertiva nem alterado código funcional. Os 22
testes direcionados desses módulos passaram; as duas suítes completas foram
repetidas e passaram conforme a tabela. A base não foi repetida porque seu
conteúdo e resultado não mudaram. São lacunas corrigidas da integração dos
testes com o novo comando aprovado, não um defeito geométrico ou de runtime.

### Skips ambientais

Os **149 skips têm exatamente os mesmos IDs e motivos nas três árvores**.
Não foram introduzidos skips pelo incremento. Motivos reportados pelo ambiente:

| Motivo literal | Casos |
| --- | ---: |
| `Real FreeCAD GUI / Qt event loop required` | 30 |
| `PySide6 não disponível neste Python` | 26 |
| `FreeCAD/Draft native Python required` | 15 |
| `FreeCAD GUI and Qt required` | 47 |
| `FreeCAD Units and PySide6 required` | 8 |
| `FreeCAD units and PySide6 required` | 15 |
| `PySide6 required` | 8 |

Esses testes requerem FreeCAD/Units/Qt/PySide6 reais, ausentes no Python de
descoberta. Não são contabilizados como aprovados; os gates nativos abaixo
cobrem os fluxos relevantes deste MVP, sem pretender substituir toda a matriz
nativa de outras funcionalidades do projeto.

## Gates FreeCAD 1.1.4 na candidata

Executados sequencialmente a partir de `candidate/`, com o runner e probe
originais da candidata e perfil FreeCAD isolado por processo:

```powershell
python scripts/run_member_miter_joint_gate.py --theme Classic --output-root "../native"
python scripts/run_member_miter_joint_gate.py --theme "FreeCAD Dark" --output-root "../native"
python scripts/run_member_miter_joint_gate.py --theme OpenDark --output-root "../native"
```

Na execução foi usado o caminho absoluto equivalente de `../native`. O manifesto
registra esse comando, a raiz candidata e o probe nessa árvore. O bootstrap
aponta `sys.path` e o namespace freecad para a candidata; não usa os estudos.

| Tema | Checks | Resultado | Pasta em `native/` |
| --- | ---: | --- | --- |
| Classic | 823 | OK | `1792806199823120800_Classic_u_obv9zl` |
| FreeCAD Dark | 823 | OK | `1792806264996378200_FreeCAD_Dark_8qhay_6y` |
| OpenDark | 823 | OK | `1792806337843270200_OpenDark_2tnalpgr` |

**Três execuções, três sucessos, zero falhas: 2.469 checks**, distintos da
contagem de testes unitários. Todos com FreeCAD 1.1.4, retorno zero, nenhum
timeout, nenhum erro capturado de callback e filtros de logs nativos vazios.
Os três manifestos têm as mesmas **153 fontes Python** e os hashes coincidem
com a candidata final. `native-comparison.json` consolida essas verificações.

Cobertura confirmada:

- W/U/Ue/RHS/SHS, 90° e oblíquos (incluindo W60/90/120), Start/End mistos,
  frame inclinado e roll compatível; inversão A/B com diferença BRep bidirecional.
- Tampas reais coincidentes e contato útil, semiespaços opostos, volume de
  interpenetração, um sólido válido por resultado e preservação da ponta oposta.
- Duas candidatas exibidas em Coin e correspondência BRep com o resultado
  confirmado; resultado inválido remove ambos os previews e bloqueia OK.
- Rejeições de perfis/rolls incompatíveis, skew/paralelos, T/cruzamento, slot
  ocupado, Linked, ponta oposta inválida e filhos de treliça.
- Uma transação bilateral, um Undo/Redo, falha tardia injetada na segunda
  verificação e restauração dos dois membros. Não há aplicação unilateral parcial.
- Três ciclos de aplicar/Undo/reabrir sem recompute manual/reaplicar/Undo/Redo
  por tema; primeira reabertura pelo comando público. Ponta ocupada após Redo
  continua bloqueada por ocupação, enquanto a ponta oposta livre pode ser usada.
- Recompute limitado aos participantes, sentinelas pendentes no mesmo/outro
  documento preservadas; fonte Touched com Shape antiga bloqueia o par e o OK
  sem executar essa fonte. Recuperação após recompute explícito da fonte.
- Cancelar/Esc/fechar tarefa, captura/troca/exclusão de alvo, mudança de
  vista/documento e desativação; branches removidos, máscaras restauradas,
  timer parado/desconectado e observer removido, sem objetos persistentes auxiliares
  ou transações de preview. Não se promete remover observers de outras ferramentas.
- Salvar/fechar/reabrir FCStd, cortes Fixed e propriedades/eixos/massa preservados,
  abertura da tarefa sem recompute manual e independência posterior dos parceiros.
- App::Part compartilhado, distinto e aninhado; preview/validação globais e
  persistência. Associação oposta sob parent transformado permanece rejeitada.
- Diagnósticos info/success/error e contraste ≥4,5 na janela composta nos três
  temas. Artefatos de `QWidget.grab` no viewport não são usados como prova geométrica;
  o gate usa BRep e renders nativos separados.

## Redo após abort: limitação demonstrada, sem mudança de mecanismo

Cada processo executou primeiro um controle nativo Part::Box. Depois de um
commit e Undo, havia Undo=0/Redo=1. Abrir outra transação manteve Redo=1; a
primeira escrita o descartou. Abortar restaurou valores, Placement/Shape e
Undo=0, mas Redo permaneceu zero. O controle que abriu/abortou sem escrever
preservou Redo=1. Evidência por tema: `native-abort-baseline.json`.

A falha tardia injetada do MVP, após escrever os dois slots, teve histórico
0/2 → 0/0, em conformidade com esse controle. Imediatamente após abort os dois
membros tinham os mesmos inputs, outputs, volume, bounds, validade e Placement
anteriores; apenas o estado esperado Touched permanecia. Ao reabrir a tarefa,
a normalização local recuperou também o estado, sem nova entrada de Undo.
Os snapshots completos normalizados dos **dois membros** são iguais ao estado
anterior nos três temas, ver `replay-cases.json` e `native-comparison.json`.

Não foi tentado reconstruir Redo por replay ou manipulação do histórico.
A limitação é do FreeCAD 1.1.4 e não invalida a restauração bilateral. Preview,
Cancelar e rejeições antes de escrever continuam preservando Undo/Redo e foram
verificados. Uma nova aplicação confirmada após Undo descarta Redo como esperado.

## Integridade e candidata final

`python scripts/check_project.py` passou nas **três árvores**; logs em
`*-project.log`, retornos em `*-project.json`. Foram validados sintaxe, arquivos
essenciais, versões e integridade dos catálogos, sem alterar dados ou metadados.

`git diff --check` passou no workspace. Como a candidata extraída não tem `.git`,
a verificação equivalente usou `git diff --no-index --check` para cada um dos
10 arquivos modificados contra a base e cada um dos 14 novos contra `NUL`.
Todos sem erros de whitespace; retornos 0/1 de no-index são esperados conforme
haja diferença. Avisos LF→CRLF não foram tratados como falha de whitespace.
Resultados completos: `whitespace.json`.

Foram inventariados por SHA-256 **574 arquivos existentes fora da seleção**, todos
preservados, sem remoção ou mudança. Os 134 caminhos de status Git excluídos
estão no anexo e em `excluded-status.json`/`excluded-paths.txt`. Modelos FCStd,
backups FCBak e arquivos ignorados locais também permanecem fora da candidata;
os que estão no inventário são protegidos pelos mesmos hashes. Evidências/caches
não são publicados. Não houve limpeza de não rastreados nem modificação de
estudos anteriores em test-results; a auditoria usa uma pasta nova própria.

Somente as duas expectativas de teste e este relatório mudaram durante o
fechamento. Os arquivos funcionais e demais arquivos do MVP mantêm os hashes
do início da rodada. O delta final da candidata é exatamente a lista abaixo,
sem extras, remoções ou divergência da seleção do workspace. Referências:
`preservation-final.json`, `candidate-manifest.json`, `selection.json` e
`tracked-miter.patch`. HEAD permanece `2ef3b49`, branch `develop/0.7.0`, índice vazio.

## Inventário exato para staging seletivo

**24 arquivos: 10 modificados e 14 novos**, relativos à base publicada.
Inclui a investigação porque o MVP a referencia; não inclui outras etapas.

| Estado | Arquivo |
| --- | --- |
| Modificado | `freecad/SteelStructures/commands.py` |
| Modificado | `freecad/SteelStructures/init_gui.py` |
| Modificado | `freecad/SteelStructures/paths.py` |
| Modificado | `freecad/SteelStructures/interactive/member_adjustment_controller.py` |
| Modificado | `freecad/SteelStructures/interactive/member_adjustment_preview.py` |
| Modificado | `tests/test_command_registration.py` |
| Modificado | `tests/test_column_command.py` |
| Modificado | `tests/test_general_tools.py` |
| Modificado | `tests/test_grid_command.py` |
| Modificado | `tests/test_project_integrity.py` |
| Novo | `freecad/SteelStructures/member_miter_geometry.py` |
| Novo | `freecad/SteelStructures/interactive/member_miter_controller.py` |
| Novo | `freecad/SteelStructures/interactive/member_miter_task_panel.py` |
| Novo | `freecad/SteelStructures/interactive/member_miter_preview.py` |
| Novo | `Resources/Icons/MiterMembers.svg` |
| Novo | `tests/test_member_miter_geometry.py` |
| Novo | `tests/test_member_miter_controller.py` |
| Novo | `tests/test_member_miter_preview.py` |
| Novo | `tests/test_member_miter_task_panel.py` |
| Novo | `tests/manual_member_miter_joint.py` |
| Novo | `scripts/run_member_miter_joint_gate.py` |
| Novo | `Documentation/MEMBER_MITER_JOINT_INVESTIGATION.md` |
| Novo | `Documentation/MEMBER_MITER_JOINT_MVP.md` |
| Novo | `Documentation/MEMBER_MITER_JOINT_MVP_CLOSURE.md` |

Proposta somente, **não executada** (também em `selective-staging.ps1.txt`):

```powershell
git add -- `
    "freecad/SteelStructures/commands.py" `
    "freecad/SteelStructures/init_gui.py" `
    "freecad/SteelStructures/paths.py" `
    "freecad/SteelStructures/interactive/member_adjustment_controller.py" `
    "freecad/SteelStructures/interactive/member_adjustment_preview.py" `
    "tests/test_command_registration.py" `
    "tests/test_column_command.py" `
    "tests/test_general_tools.py" `
    "tests/test_grid_command.py" `
    "tests/test_project_integrity.py" `
    "freecad/SteelStructures/member_miter_geometry.py" `
    "freecad/SteelStructures/interactive/member_miter_controller.py" `
    "freecad/SteelStructures/interactive/member_miter_task_panel.py" `
    "freecad/SteelStructures/interactive/member_miter_preview.py" `
    "Resources/Icons/MiterMembers.svg" `
    "tests/test_member_miter_geometry.py" `
    "tests/test_member_miter_controller.py" `
    "tests/test_member_miter_preview.py" `
    "tests/test_member_miter_task_panel.py" `
    "tests/manual_member_miter_joint.py" `
    "scripts/run_member_miter_joint_gate.py" `
    "Documentation/MEMBER_MITER_JOINT_INVESTIGATION.md" `
    "Documentation/MEMBER_MITER_JOINT_MVP.md" `
    "Documentation/MEMBER_MITER_JOINT_MVP_CLOSURE.md"
```

Não usar staging global nem incluir arquivos adicionais por diretório. Mensagem
sugerida para uma autorização futura de commit local:

```text
feat: add fixed bilateral member miter command

Reuse PlaneCut candidates for simultaneous preview and atomic confirmation.
Support immediate reuse after Undo/Redo with scoped recompute and safe cleanup.
Add native gates, regression coverage and technical closure.
```

## Limitações e decisão

Não há aparo automático de excedentes, T verdadeiro, associação entre membros,
filhos de treliças, corte por sólido, múltiplos participantes ou novas modalidades
de referência. Fontes pendentes, expressões e composições continuam exigindo
revisão; associação oposta sob parent transformado permanece fora do domínio.
O cálculo OCC ocorre no thread da UI e pode rejeitar conservadoramente casos
mal condicionados. Não há certificação de ligação/solda nem suporte prometido
a qualquer seção/orientação. FreeCAD 1.1.3 não foi executado neste fechamento
solicitado para 1.1.4; release/matriz ampliada são avaliação separada.

**GO para commit local seletivo dos 24 arquivos.** Aprovação manual recebida,
suítes comparadas sem regressão remanescente, candidata limpa de experimentos,
gates nativos aprovados nos três temas e arquivos locais preservados. A revisão
técnica e a revisão QA independentes não identificaram bloqueador. A limitação
nativa de Redo após escrita seguida de abort está explicitada, sem alteração
especulativa do mecanismo de transações. Nenhuma correção especulativa em W.

Não há validação manual adicional exigida por alterações funcionais deste
fechamento, pois não houve nenhuma. Commit não foi executado; push/release não
foram preparados nem autorizados. A lista seletiva é uma proposta revisável.

## Anexo — 134 exclusões explícitas do status local

Todos os caminhos abaixo foram preservados e não entram na candidata/staging.
Além deles, excluir `test-results/**`, `__pycache__/**`, `.git/**`, `.codex/**`,
`.agents/**`, modelos/backups ignorados (`*.FCStd`, `*.FCBak`) e quaisquer
artefatos não presentes no inventário seletivo acima. Nenhum desses padrões
é instrução para remover arquivos.

```text
Documentation/STRUCTURAL_PLATE_0_7_0_AUTO_PLANE_REFINEMENT.md
Documentation/STRUCTURAL_PLATE_0_7_0_B1.md
Documentation/STRUCTURAL_PLATE_0_7_0_B_RECTANGLE_PILOT.md
Documentation/STRUCTURAL_PLATE_0_7_0_FINAL_UI_REFINEMENT.md
Documentation/STRUCTURAL_PLATE_0_7_0_INPUT_CONSISTENCY.md
Documentation/STRUCTURAL_PLATE_0_7_0_UI_POLISH.md
Documentation/STRUCTURAL_PLATE_0_7_0_UNIFICATION_GATE.md
Documentation/STRUCTURAL_PLATE_0_7_0_UNIFIED_PROTOTYPE.md
Documentation/STRUCTURAL_PLATE_0_7_0_USABILITY_EXTRUSION.md
Documentation/STRUCTURAL_PLATE_QLINEEDIT_BASELINE_DIAGNOSIS.md
Documentation/TRUSS_0_7_0_COMPACT_TASK_PANEL.md
Documentation/TRUSS_0_7_0_DIRECT_DRAFT_REFERENCE.md
Documentation/TRUSS_0_7_0_EDITOR_ACTIONS.md
Documentation/TRUSS_0_7_0_INTERACTIVE_REFERENCE_SELECTION.md
Documentation/TRUSS_0_7_0_REFERENCE_LAYOUT_FIX.md
Documentation/TRUSS_0_7_0_STAGE1_EDIT_SESSION.md
Documentation/TRUSS_0_7_0_STAGE2_LIFECYCLE_UNDO.md
Documentation/TRUSS_0_7_0_STAGE2_REPEAT_APPLY.md
Documentation/TRUSS_0_7_0_STAGE3A_EXPANDED_EDITOR.md
Documentation/TRUSS_0_7_0_STAGE3B1_FUNCTIONAL_TABS.md
Documentation/TRUSS_0_7_0_STAGE3B2_FIVE_TABS.md
Documentation/TRUSS_0_7_0_STAGE3B2_THEME_COMPATIBILITY.md
Documentation/TRUSS_0_7_0_STAGE3B2_TOOLBAR_VISUAL_POLISH.md
Documentation/TRUSS_0_7_0_STAGE3B2_UI_REFINEMENT.md
Documentation/TRUSS_0_7_0_TASK_PANEL_INPUT_REFINEMENT.md
Documentation/TRUSS_0_7_0_UX_UI_RESUME_VALIDATION.md
Documentation/TRUSS_0_7_0_VISUAL_POLISH.md
Documentation/gusset_family_review/CONFIGURACOES.md
Documentation/gusset_family_review/ESTRATEGIA.md
Documentation/gusset_family_review/F01_01.svg
Documentation/gusset_family_review/F01_02.svg
Documentation/gusset_family_review/F02_01.svg
Documentation/gusset_family_review/F02_02.svg
Documentation/gusset_family_review/F02_03.svg
Documentation/gusset_family_review/F02_04.svg
Documentation/gusset_family_review/F02_05.svg
Documentation/gusset_family_review/F02_06.svg
Documentation/gusset_family_review/F02_07.svg
Documentation/gusset_family_review/F02_08.svg
Documentation/gusset_family_review/F02_09.svg
Documentation/gusset_family_review/F02_10.svg
Documentation/gusset_family_review/F03_01.svg
Documentation/gusset_family_review/F03_02.svg
Documentation/gusset_family_review/F03_03.svg
Documentation/gusset_family_review/F03_04.svg
Documentation/gusset_family_review/F04_01.svg
Documentation/gusset_family_review/F04_02.svg
Documentation/gusset_family_review/F04_03.svg
Documentation/gusset_family_review/F04_04.svg
Documentation/gusset_family_review/F04_05.svg
Documentation/gusset_family_review/F05_01.svg
Documentation/gusset_family_review/F06_01.svg
Documentation/gusset_family_review/F07_01.svg
Documentation/gusset_family_review/F07_02.svg
Documentation/gusset_family_review/F07_03.svg
Documentation/gusset_family_review/F07_04.svg
Documentation/gusset_family_review/F07_05.svg
Documentation/gusset_family_review/F08_01.svg
Documentation/gusset_family_review/F09_01.svg
Documentation/gusset_family_review/MATRIZ.md
Documentation/gusset_family_review/index.html
Documentation/gusset_phase1/A_propostas.svg
Documentation/gusset_phase1/B_propostas.svg
Documentation/gusset_phase1/C_propostas.svg
Documentation/gusset_phase1/PROPOSTAS.md
Documentation/gusset_phase1/coordenadas.json
Documentation/gusset_phase1/coordenadas.md
Documentation/gusset_round1/F01_01.svg
Documentation/gusset_round1/F01_02.svg
Documentation/gusset_round1/F02_01.svg
Documentation/gusset_round1/F02_02.svg
Documentation/gusset_round1/F02_03.svg
Documentation/gusset_round1/F02_04.svg
Documentation/gusset_round1/F02_05.svg
Documentation/gusset_round1/F02_06.svg
Documentation/gusset_round1/F02_07.svg
Documentation/gusset_round1/F02_08.svg
Documentation/gusset_round1/F02_09.svg
Documentation/gusset_round1/F02_10.svg
Documentation/gusset_round1/F03_01.svg
Documentation/gusset_round1/F03_02.svg
Documentation/gusset_round1/F03_03.svg
Documentation/gusset_round1/F03_04.svg
Documentation/gusset_round1/F04_01.svg
Documentation/gusset_round1/F04_02.svg
Documentation/gusset_round1/F04_03.svg
Documentation/gusset_round1/F04_04.svg
Documentation/gusset_round1/F04_05.svg
Documentation/gusset_round1/F05_01.svg
Documentation/gusset_round1/F06_01.svg
Documentation/gusset_round1/F07_01.svg
Documentation/gusset_round1/F07_02.svg
Documentation/gusset_round1/F07_03.svg
Documentation/gusset_round1/F07_04.svg
Documentation/gusset_round1/F07_05.svg
Documentation/gusset_round1/F08_01.svg
Documentation/gusset_round1/F09_01.svg
Documentation/gusset_round1/RELATORIO.md
Documentation/gusset_round1/estudos/F04_03.json
Documentation/gusset_round1/estudos/F04_03.svg
Documentation/gusset_round1/estudos/F04_04.json
Documentation/gusset_round1/estudos/F04_04.svg
Documentation/gusset_round1/estudos/F08_01.json
Documentation/gusset_round1/estudos/F08_01.svg
Documentation/gusset_round1/estudos/index.html
Documentation/gusset_round1/index.html
Documentation/gusset_round1/resultados.json
Documentation/gusset_tip_depth/CRITERIO.md
Documentation/gusset_tip_depth/F04_03.svg
Documentation/gusset_tip_depth/F04_04.svg
Documentation/gusset_tip_depth/HP_limite.svg
Documentation/gusset_tip_depth/coordenadas.json
Documentation/gusset_tip_depth/index.html
Documentation/gusset_tip_round2/CRITERIO.md
Documentation/gusset_tip_round2/F04_01.svg
Documentation/gusset_tip_round2/F04_02.svg
Documentation/gusset_tip_round2/F04_03.svg
Documentation/gusset_tip_round2/F04_04.svg
Documentation/gusset_tip_round2/F04_05.svg
Documentation/gusset_tip_round2/coordenadas.json
Documentation/gusset_tip_round2/index.html
scripts/diagnose_plate_heap.py
scripts/diagnose_plate_qt_lifecycle.py
scripts/diagnose_plate_tracker_stability.py
tests/copiatreliça.FCStd
tests/copiatreliça2.FCStd
tests/manual_plate_heap_comparison.py
tests/manual_plate_heap_setvalues_probe.py
tests/manual_plate_numeric_input.py
tests/manual_plate_qt_lifecycle.py
tests/manual_plate_rectangle_lifecycle_gate.py
tests/manual_plate_tracker_stability.py
tests/manual_point_input_probe.py
tests/test_plate_qt_lifecycle_probe.py
```
