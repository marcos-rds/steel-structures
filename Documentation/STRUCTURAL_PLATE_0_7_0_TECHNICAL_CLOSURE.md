# Fechamento técnico — Criar Chapa Estrutural 0.7.0

**Seguimento de diagnóstico (10/10/2026):** o
[relatório Qt dedicado](STRUCTURAL_PLATE_0_7_0_QT_LIFECYCLE_DIAGNOSIS.md)
reproduziu o wrapper destruído com Draft Line puro no 1.1.3 e registrou Access
Violation capturado em um controle posterior. A campanha GUI foi interrompida;
nenhum patch de produção foi aplicado. Continua **NO-GO**. As observações abaixo
sobre ausência de falha nativa e resultados dos gates descrevem somente o
fechamento anterior, não esse seguimento. O inventário de staging abaixo também
antecede os novos arquivos de diagnóstico, que permanecem sem staging.

Data: 10/10/2026. Branch `develop/0.7.0`. HEAD
`9ad0446f9cb896a8f9255a3ea698156adc063834` — baseline `feat(plate): add parametric structural plate workflow`.

**NO-GO para commit local. NO-GO para release.** O gate integrado 1.1.3 reproduziu
o erro Qt de InputField destruído. Não houve crash nativo, mas a integração não
ficou integralmente verde. Não foi aplicada correção especulativa. Nenhum staging,
commit, push, tag ou release foi feito. A aprovação manual final de funcionamento
e OpenDark foi informada pelo usuário antes deste fechamento; os gates abaixo
são automatizados, sem alegação de nova validação manual visual.

## Arquitetura final e integração pública

`StructuralPlate` permanece um `Part::FeaturePython`, com proxy em `plate.py`,
contorno puro em `plate_geometry.py`, adaptador OCC em `plate_freecad_geometry.py`,
captura de frame em `plate_planes.py` e fontes em `plate_sources.py`.
`ContourData` guarda o contorno XY local; `Placement` o orienta no documento.
Schema 1 e persistência permanecem inalterados neste fechamento.

Há somente `SteelStructures_CreatePlate` — **Criar Chapa Estrutural** — registrado
em `commands.py` e publicado no menu/toolbar por `init_gui.py`. Usa o ícone existente
`Resources/Icons/CreatePlate.svg`. O gate verifica a ausência de registro do piloto.

`PlateCreationSession` coordena aquisições sequenciais: Polígono/Retângulo 2P
Draft-native, Automático/3P pelo controlador aprovado, e seleção temporária de face.
Não há dois motores ativos. `draft_plate_polygon_tool.py` herda a base interna de
`draft_plate_rectangle_tool.py`; este módulo não pode ser removido como piloto.
O rectangleTracker local continua com **5 vetores**, sem monkeypatch global.

Preservados: `plate_controller.py`, `plate_preview.py`, `plate_task_panel.py`,
`coordinate_input_widget.py`, `point_input.py`, `plate_creation_session.py`,
`plate_face_selection.py`, `plate_panel_shortcuts.py`, ambos adaptadores Draft e
`plate_rectangle_tracker.py`. O desenvolvimento B1 de conversão numérica e aquisição
3D continua necessário. Não houve alteração de UX/UI, geometria permanente,
Material/PlateType, Gussets ou outras ferramentas nesta etapa.

## Remoções comprovadas e alterações deste fechamento

- `commands.py`: removidos `_active_plate_rectangle_tool`,
  `CreatePlateRectangleCommand`, `_plate_rectangle_closed` e
  `close_plate_rectangle_tool`, além da chamada defensiva em `close_plate_panel`.
  A classe não era registrada nem instanciada pela ferramenta unificada.
- Removidos localmente `tests/test_plate_rectangle_command.py` e
  `tests/manual_plate_rectangle_native.py`: exclusivos do piloto abandonado;
  o probe exigia o antigo comando público ausente. Eram arquivos untracked,
  portanto não haverá exclusão de arquivo versionado. Cópias preservadas em
  `test-results/plate_technical_closure/` e snapshot inicial ignorado.
- `tests/test_draft_native_member_tool.py`: delimitada por AST a função examinada,
  preservando **todas** as assertions. O delimitador textual anterior não existia
  e incluía os comandos posteriores, gerando falso positivo com `clearTaskWatcher`
  de Criar Chapa. A função de produção é idêntica no baseline e nos snapshots.
  Evidência: `test-results/plate_technical_closure/static_member_test_origin.json`.
- Gate unificado ampliado somente no harness: regressões de Membro/Pilar/Grid,
  persistência conjunta e controles Qt isolados; hashes do harness nos próximos runs.
- Guia consolidado, referência no README e notas de contexto nos relatórios históricos.

Testes de geometria, entrada, lifecycle, fontes, persistência e regressões foram
preservados. Os demais diagnósticos não foram apagados por mera idade: alguns
reproduzem deliberadamente caminhos históricos perigosos e ficam apenas locais.
O delta exato desta etapa está em `test-results/plate_technical_closure/closure_delta.json`.

## Ocorrência Qt: evidência e conclusão

O registro original, citado em `STRUCTURAL_PLATE_0_7_0_FINAL_UI_REFINEMENT.md`, está
em `test-results/plate_unified_gate/1791662756163138800_1.1.4_integrated/1/FreeCAD.log:384–403`.
Caminho: comando → sessão → Rectangle native → `_input_ui` → Draft `pointUi` →
`taskUi` → `setupToolBar` → `_inputfield`. O wrapper `PySide6.QtWidgets.QLineEdit`
retornado por `UiLoader.createWidget("Gui::InputField")` já estava inválido ao
executar `setObjectName`, antes de instalar os novos atalhos/preview/callbacks.
O Automático ainda não havia sido aberto naquele processo.

**Recorrência neste fechamento:** PID 6692, FreeCAD 1.1.3, gate
`1791666148716274100_1.1.3_integrated`, após 42 verificações e 62 ativações.
Ao substituir o Automático por Draft Line, o novo `yValue` falhou no mesmo
`DraftGui._inputfield:284`, imediatamente após `createWidget`. O novo Line ainda
não havia criado seu objeto/callback Coin. `replacement_debug` registra sessão
antiga encerrada, sem painel; a assertion seguinte detectou ausência do diálogo
novo. Há também aviso posterior de disconnect de `destroyed`, sem prova de causa.
O processo saiu com zero e sem dump: **exceção Python Qt; sem crash, dump ou evidência de corrupção de heap neste run**.

Foram examinados teardown, callbacks tardios guardados, timers pertencentes ao
painel, ownership dos forms e encerramento antes da limpeza Qt adiada. Não se
identificou destruidor concreto ou ownership concorrente que justifique patch.
A amostra InputField de métricas do Automático é hipótese, não causa comprovada:
o incidente original ocorreu antes dela. Dois controles isolados 1.1.3, sem
importar SteelStructures, passaram: 12 ciclos Draft Line puro e 12 intercalados
com criação/parent/hide/deleteLater de InputField. Ponteiros e sinais destroyed
foram registrados. A ausência de falha nesses controles **não resolve** a recorrência.

Não é possível atribuir conclusivamente a falha à bancada, Draft ou binding/harness.
O próximo diagnóstico deve isolar essa sequência e seu destruidor; não se recomenda
retry automático, refatoração do lifecycle ou declarar o episódio resolvido.

## Risco nativo 0xc0000374

Nenhum Access Violation, corrupção de heap ou novo dump foi registrado nesta etapa.
Os gates verificaram exit code e preservação de `gui_trackers.py` e `pivy/coin.py`
instalados. Não foram modificadas instalações FreeCAD nem usado tracker original
com contagem incorreta. O dump histórico `freecad.exe.7956.dmp` permanece no local
original; relatórios heap/tracker preservam stack, identificação e limitações.
A correção local de cinco vetores é mantida. Não se afirma eliminação do risco.
Não foram repetidas campanhas históricas de centenas de ciclos.

## Geometria, propriedades e persistência

Conferidos `ContourData`, `Placement`, `Thickness`, `Offset`, `ReverseExtrusion`,
`SourceMode`, `KeepSourceLink`, `SourceObject`, dependências de contêiner,
`GrossArea`, `EnvelopeVolume` e `GenerationStatus`.
Thickness positiva; normal `[Offset, Offset+Thickness]`, invertida
`[Offset-Thickness, Offset]`. Contorno e frame não mudam; área/volume não mudam
ao inverter. Testes OCC cobrem Offset negativo/zero/positivo, XY/XZ/YZ/inclinado,
fontes Rectangle/Wire associativas e snapshots, contêineres, fonte inválida,
recompute, save/reopen e Undo/Redo. A fixture FCStd antiga é serializada sem
ReverseExtrusion, inspecionada no XML e reaberta com False, mantendo SchemaVersion 1.
Automático/3P/2P são exercitados também no gate integrado; no 1.1.3 esses caminhos
passaram antes da falha final ao abrir Draft Line.

## Suíte Python e integridade

Primeira execução: 1639 testes; 1580 aprovados, 1 falha, 0 erros, 58 skips.
A falha estática descrita acima foi demonstrada e corrigida no escopo do teste,
sem modificar produção ou enfraquecer assertions. O módulo de 42 testes passou.

Execução final: `python -m unittest discover -s tests -p "test_*.py" -v`:
**1639 testes, 1581 aprovados, 0 falhas, 0 erros, 58 skips**, 62,046 s.
Logs e lista individual dos skips em `test-results/plate_technical_closure/python_suite_final.*`.
Os skips são 30 controles de coordenadas GUI e 15 testes FreeCAD/Draft nativos,
executados com zero skips em cada instalação; mais 13 testes Qt Gusset C6Q por
ausência de PySide6 no Python de sistema. Estes últimos não foram reexecutados
nativamente: pertencem a ferramenta não alterada, fora das campanhas desta etapa.
As demais ferramentas passaram pela suíte regular, incluindo comandos, Grid,
Membro/Pilar, perfis, treliças e ligações; não se alega campanha manual completa delas.

`python scripts/check_project.py`: aprovado (sintaxe, versões, catálogos, essenciais).
`git diff --check`: aprovado; somente avisos da política LF/CRLF, sem erro de whitespace.

## Gates Qt/FreeCAD/OCC

Cada linha usa perfil isolado, sem operar a sessão do usuário. Resultados, logs,
eventos e imagens ficam em `test-results/plate_unified_gate/<ID>/`.

| ID | Resultado |
|---|---|
| `1791665994967496800_1.1.4_geometry` | PASS — 15 testes OCC/persistência + 30 Qt, zero skips |
| `1791666020610960200_1.1.3_geometry` | PASS — 15 testes OCC/persistência + 30 Qt, zero skips |
| `1791666041978831500_1.1.4_integrated` | PASS — 48 verificações, 66 ativações |
| `1791666148716274100_1.1.3_integrated` | FAIL — 42 verificações concluídas, 62 ativações; erro Qt ao substituir Auto por Draft Line |
| `1791670458893112700_1.1.4_regression` | PASS — 6 verificações de Draft/Membro/Pilar/Grid/OCC/FCStd; smoke inicial, ampliado nas duas últimas linhas |
| `1791670524960770700_1.1.3_regression` | PASS — 6 verificações de Draft/Membro/Pilar/Grid/OCC/FCStd; smoke inicial, ampliado nas duas últimas linhas |
| `1791671142468724600_1.1.3_qt_native` | PASS — 12 ciclos, sem importar SteelStructures |
| `1791671184611571100_1.1.3_qt_sample` | PASS — 12 ciclos, sem importar SteelStructures |
| `1791671224373879300_1.1.4_regression` | PASS — 6 verificações de Draft/Membro/Pilar/Grid/OCC/FCStd |
| `1791671240846346600_1.1.3_regression` | PASS — 6 verificações de Draft/Membro/Pilar/Grid/OCC/FCStd |

Comandos executados: `python scripts/run_plate_unified_gate.py --version <versão>
--stage <stage> --processes 1 --cycles <n>`. Geometry/regression: n=1; integrated:
n=6; qt_native/qt_sample: n=12. A versão/estágio exatos constam nos IDs acima.

O integrated cobre modos/planos, selecionar/alterar face, snaps, numérico, foco,
atalhos, limpeza completa, fechamento, cancelamento, callbacks tardios, painéis
substitutos, troca de vista, fechamento de documento e restauração do WP.
A última regressão abre/cancela Chapa comum antes de Membro, Auto antes de Pilar,
e Chapa com P1 antes de Grid, no mesmo processo; valida transações, sólidos OCC,
Undo/Redo e save/reopen de Membro/Pilar/Chapa e o probe existente de Grid.
O erro no gate 1.1.3 não foi ocultado nem convertido em PASS por repetição.

## Documentação e arquivos fora do incremento

Recomendados: guia consolidado, este fechamento, baseline-A identificado como
histórico e relatórios heap/tracker como evidência de segurança. README aponta
para o guia sem alterar a versão publicada. Não recomendar automaticamente os
relatórios B1/piloto/refinamentos, pois descrevem estados intermediários.

Os seguintes arquivos permanecem locais, fora da proposta de staging:
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
scripts/diagnose_plate_heap.py
scripts/diagnose_plate_tracker_stability.py
tests/manual_plate_heap_comparison.py
tests/manual_plate_heap_setvalues_probe.py
tests/manual_plate_numeric_input.py
tests/manual_plate_rectangle_lifecycle_gate.py
tests/manual_plate_tracker_stability.py
tests/manual_point_input_probe.py
```

Também excluídos, **sem apagar nem modificar**:
```text
Documentation/gusset_family_review/
Documentation/gusset_phase1/
Documentation/gusset_round1/
Documentation/gusset_tip_depth/
Documentation/gusset_tip_round2/
```

Hashes confirmam os 95 arquivos desses estudos idênticos ao início do fechamento,
incluindo o `inventario.json` já versionado. Excluídos ainda `test-results/`,
dumps, caches, perfis isolados, FCStd de teste, logs e temporários.
`init_gui.py` aparece M no status, mas não tem diff textual; não está na proposta.

## Lista EXATA proposta para staging posterior

**35 arquivos** (13 modificados versionados + 22 novos). Lista de escopo apenas:
**não executar staging enquanto este NO-GO persistir**. Não há staging atual.
O manifesto local correspondente é `test-results/plate_technical_closure/proposed_staging.txt`.
```text
Documentation/STRUCTURAL_PLATE.md
Documentation/STRUCTURAL_PLATE_0_7_0_A.md
Documentation/STRUCTURAL_PLATE_0_7_0_HEAP_DIAGNOSTIC.md
Documentation/STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md
Documentation/STRUCTURAL_PLATE_0_7_0_TRACKER_STABILITY.md
README.md
freecad/SteelStructures/commands.py
freecad/SteelStructures/interactive/coordinate_input_widget.py
freecad/SteelStructures/interactive/draft_plate_polygon_tool.py
freecad/SteelStructures/interactive/draft_plate_rectangle_tool.py
freecad/SteelStructures/interactive/plate_controller.py
freecad/SteelStructures/interactive/plate_creation_session.py
freecad/SteelStructures/interactive/plate_face_selection.py
freecad/SteelStructures/interactive/plate_panel_shortcuts.py
freecad/SteelStructures/interactive/plate_preview.py
freecad/SteelStructures/interactive/plate_rectangle_tracker.py
freecad/SteelStructures/interactive/plate_task_panel.py
freecad/SteelStructures/interactive/point_input.py
freecad/SteelStructures/plate.py
freecad/SteelStructures/plate_freecad_geometry.py
scripts/run_plate_unified_gate.py
tests/manual_plate_unified_native.py
tests/test_coordinate_input_widget.py
tests/test_draft_native_member_tool.py
tests/test_draft_plate_polygon_tool.py
tests/test_draft_plate_rectangle_tool.py
tests/test_plate_command.py
tests/test_plate_creation_session.py
tests/test_plate_face_selection.py
tests/test_plate_interactive.py
tests/test_plate_native.py
tests/test_plate_panel_shortcuts.py
tests/test_plate_rectangle_tracker.py
tests/test_plate_task_panel_lifecycle.py
tests/test_point_input.py
```

## git diff --stat e inventário dos novos arquivos

O Git não inclui arquivos untracked no diff --stat. Saída exata dos versionados:
```text
 Documentation/STRUCTURAL_PLATE_0_7_0_A.md          |   3 +
 README.md                                          |   4 +
 freecad/SteelStructures/commands.py                |  63 ++++-
 .../interactive/plate_controller.py                | 139 +++++++++-
 .../SteelStructures/interactive/plate_preview.py   |  20 +-
 .../interactive/plate_task_panel.py                | 271 +++++++++++++++---
 freecad/SteelStructures/plate.py                   |  18 +-
 freecad/SteelStructures/plate_freecad_geometry.py  |  11 +-
 tests/test_draft_native_member_tool.py             |   7 +-
 tests/test_plate_command.py                        | 304 +++++++++++++++------
 tests/test_plate_interactive.py                    | 291 +++++++++++++++++++-
 tests/test_plate_native.py                         | 141 ++++++++++
 tests/test_plate_task_panel_lifecycle.py           |  58 ++++
 13 files changed, 1171 insertions(+), 159 deletions(-)
```

Novos arquivos propostos, sem staging (linhas atuais):

| Arquivo | Linhas |
|---|---:|
| `Documentation/STRUCTURAL_PLATE.md` | 119 |
| `Documentation/STRUCTURAL_PLATE_0_7_0_HEAP_DIAGNOSTIC.md` | 252 |
| `Documentation/STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md` | 417 |
| `Documentation/STRUCTURAL_PLATE_0_7_0_TRACKER_STABILITY.md` | 264 |
| `freecad/SteelStructures/interactive/coordinate_input_widget.py` | 352 |
| `freecad/SteelStructures/interactive/draft_plate_polygon_tool.py` | 138 |
| `freecad/SteelStructures/interactive/draft_plate_rectangle_tool.py` | 598 |
| `freecad/SteelStructures/interactive/plate_creation_session.py` | 451 |
| `freecad/SteelStructures/interactive/plate_face_selection.py` | 196 |
| `freecad/SteelStructures/interactive/plate_panel_shortcuts.py` | 163 |
| `freecad/SteelStructures/interactive/plate_rectangle_tracker.py` | 32 |
| `freecad/SteelStructures/interactive/point_input.py` | 106 |
| `scripts/run_plate_unified_gate.py` | 97 |
| `tests/manual_plate_unified_native.py` | 1469 |
| `tests/test_coordinate_input_widget.py` | 571 |
| `tests/test_draft_plate_polygon_tool.py` | 255 |
| `tests/test_draft_plate_rectangle_tool.py` | 1004 |
| `tests/test_plate_creation_session.py` | 453 |
| `tests/test_plate_face_selection.py` | 264 |
| `tests/test_plate_panel_shortcuts.py` | 247 |
| `tests/test_plate_rectangle_tracker.py` | 149 |
| `tests/test_point_input.py` | 109 |

Os outros novos arquivos são os registros locais listados acima e os estudos
Gusset explicitamente excluídos. A lista completa de untracked está no status.

## git status --short

Branch/HEAD esperados; index vazio (`git diff --cached --name-only` sem saída).
Não há alteração textual fora do incremento, exceto a correção justificada do
teste compartilhado de Membro. Metadados, changelog, outras ferramentas e
estudos anteriores foram preservados.
```text
 M Documentation/STRUCTURAL_PLATE_0_7_0_A.md
 M README.md
 M freecad/SteelStructures/commands.py
 M freecad/SteelStructures/init_gui.py
 M freecad/SteelStructures/interactive/plate_controller.py
 M freecad/SteelStructures/interactive/plate_preview.py
 M freecad/SteelStructures/interactive/plate_task_panel.py
 M freecad/SteelStructures/plate.py
 M freecad/SteelStructures/plate_freecad_geometry.py
 M tests/test_draft_native_member_tool.py
 M tests/test_plate_command.py
 M tests/test_plate_interactive.py
 M tests/test_plate_native.py
 M tests/test_plate_task_panel_lifecycle.py
?? Documentation/STRUCTURAL_PLATE.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_AUTO_PLANE_REFINEMENT.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_B1.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_B_RECTANGLE_PILOT.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_FINAL_UI_REFINEMENT.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_HEAP_DIAGNOSTIC.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_INPUT_CONSISTENCY.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_TRACKER_STABILITY.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_UI_POLISH.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_UNIFICATION_GATE.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_UNIFIED_PROTOTYPE.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_USABILITY_EXTRUSION.md
?? Documentation/gusset_family_review/CONFIGURACOES.md
?? Documentation/gusset_family_review/ESTRATEGIA.md
?? Documentation/gusset_family_review/F01_01.svg
?? Documentation/gusset_family_review/F01_02.svg
?? Documentation/gusset_family_review/F02_01.svg
?? Documentation/gusset_family_review/F02_02.svg
?? Documentation/gusset_family_review/F02_03.svg
?? Documentation/gusset_family_review/F02_04.svg
?? Documentation/gusset_family_review/F02_05.svg
?? Documentation/gusset_family_review/F02_06.svg
?? Documentation/gusset_family_review/F02_07.svg
?? Documentation/gusset_family_review/F02_08.svg
?? Documentation/gusset_family_review/F02_09.svg
?? Documentation/gusset_family_review/F02_10.svg
?? Documentation/gusset_family_review/F03_01.svg
?? Documentation/gusset_family_review/F03_02.svg
?? Documentation/gusset_family_review/F03_03.svg
?? Documentation/gusset_family_review/F03_04.svg
?? Documentation/gusset_family_review/F04_01.svg
?? Documentation/gusset_family_review/F04_02.svg
?? Documentation/gusset_family_review/F04_03.svg
?? Documentation/gusset_family_review/F04_04.svg
?? Documentation/gusset_family_review/F04_05.svg
?? Documentation/gusset_family_review/F05_01.svg
?? Documentation/gusset_family_review/F06_01.svg
?? Documentation/gusset_family_review/F07_01.svg
?? Documentation/gusset_family_review/F07_02.svg
?? Documentation/gusset_family_review/F07_03.svg
?? Documentation/gusset_family_review/F07_04.svg
?? Documentation/gusset_family_review/F07_05.svg
?? Documentation/gusset_family_review/F08_01.svg
?? Documentation/gusset_family_review/F09_01.svg
?? Documentation/gusset_family_review/MATRIZ.md
?? Documentation/gusset_family_review/index.html
?? Documentation/gusset_phase1/
?? Documentation/gusset_round1/
?? Documentation/gusset_tip_depth/
?? Documentation/gusset_tip_round2/
?? freecad/SteelStructures/interactive/coordinate_input_widget.py
?? freecad/SteelStructures/interactive/draft_plate_polygon_tool.py
?? freecad/SteelStructures/interactive/draft_plate_rectangle_tool.py
?? freecad/SteelStructures/interactive/plate_creation_session.py
?? freecad/SteelStructures/interactive/plate_face_selection.py
?? freecad/SteelStructures/interactive/plate_panel_shortcuts.py
?? freecad/SteelStructures/interactive/plate_rectangle_tracker.py
?? freecad/SteelStructures/interactive/point_input.py
?? scripts/diagnose_plate_heap.py
?? scripts/diagnose_plate_tracker_stability.py
?? scripts/run_plate_unified_gate.py
?? tests/manual_plate_heap_comparison.py
?? tests/manual_plate_heap_setvalues_probe.py
?? tests/manual_plate_numeric_input.py
?? tests/manual_plate_rectangle_lifecycle_gate.py
?? tests/manual_plate_tracker_stability.py
?? tests/manual_plate_unified_native.py
?? tests/manual_point_input_probe.py
?? tests/test_coordinate_input_widget.py
?? tests/test_draft_plate_polygon_tool.py
?? tests/test_draft_plate_rectangle_tool.py
?? tests/test_plate_creation_session.py
?? tests/test_plate_face_selection.py
?? tests/test_plate_panel_shortcuts.py
?? tests/test_plate_rectangle_tracker.py
?? tests/test_point_input.py
```

## Roteiro manual curto e decisão

1. Em cada versão, abrir Criar Chapa, alternar Polígono/Retângulo e WP/Face/Auto;
   selecionar e alterar face; conferir uma única aquisição e restauração do WP.
2. Criar contornos, desfazer/limpar, testar numérico e V///O/W/R/G, cancelar/reabrir;
   testar 3P e Automático inclinado sem profundidade inventada antes de P3.
3. Inverter extrusão, variar espessura/Offset e salvar/reabrir; conferir área/volume.
4. Após Auto, abrir Draft Line e Membro/Pilar/Grid; observar InputField destruído,
   preview/callback residual e fechamento de documento. A recorrência Qt é o bloqueio.

**Decisão final: NO-GO para commit local e para release.** Funcionalidades aprovadas
foram preservadas; o erro Qt reproduzido permanece sem causa demonstrada.
Para reconsiderar o commit, é necessário esclarecer essa falha e aprovar o gate
integrado 1.1.3. Mesmo um futuro GO para commit não autoriza release ou push.
Nenhuma nova melhoria foi iniciada após esta conclusão.
