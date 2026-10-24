# Meia-esquadria — fechamento técnico do aparo controlado

Data: 24/10/2026. Branch `develop/0.7.0`.
Base publicada informada pelo usuário: `6e8f0e1e99e7d15c2a8f6bfa97c502437cd53644`.

**GO técnico para commit local seletivo dos 10 arquivos inventariados, sem executá-lo.**
O usuário aprovou manualmente aparo em A, B e ambos, distâncias, preview e confirmação
bilateral, cancelamento, Undo/Redo, reaplicação e FCStd; também aprovou visualmente
a autorização global única, valores nas opções Início/Fim, grupos A/B, redução
de redundância e diagnósticos semânticos. Essa aprovação foi recebida do usuário;
os gates e a inspeção de capturas desta auditoria não são apresentados como
nova validação manual interativa realizada pelo agente.

Não houve nova funcionalidade, correção funcional ou refinamento visual neste
fechamento. Código de produção, testes e runner permanecem exatamente como
aprovados no início da auditoria. Somente este relatório foi acrescentado fora
das evidências em `test-results/miter-trim-closure/`. Sem `git add`, commit, push,
merge, tag ou release; sem alteração de versão, catálogo ou changelog.

## Referências e escopo consolidado

Foram lidos integralmente [o relatório do aparo](MEMBER_MITER_CONTROLLED_TRIM.md),
[a investigação](MEMBER_MITER_JOINT_INVESTIGATION.md),
[o MVP e seus refinamentos](MEMBER_MITER_JOINT_MVP.md) e
[o fechamento do MVP](MEMBER_MITER_JOINT_MVP_CLOSURE.md).
As pendências de validação manual/visual e de suíte completa desses textos são
históricas e ficam superadas pela aprovação recebida e pelos resultados deste
fechamento. Os relatórios anteriores foram preservados sem reescrever seu histórico.

O incremento amplia somente o comando Meia-esquadria existente. Encontros interiores
exigem escolha explícita de Início/Fim por membro e uma autorização global do
conjunto exato apresentado. Não se infere intenção por proximidade, proporção ou
tamanho da sobra. A checkbox começa desmarcada e só pode ser autorizada após todas
as escolhas necessárias. Mudanças materiais revogam o consentimento; nome,
visibilidade, modo de exibição, cor, paleta, largura e vista não o revogam sem
mudança efetiva da configuração. Clique antes do polling e OK revalidam as entradas.

Valores vêm do cálculo axial real, incluindo extensão livre quando aplicável,
aparecem diretamente nas alternativas e no campo fechado e mantêm `Start`/`End`
em itemData. Pontas ocupadas ficam indisponíveis; a validade geométrica do par
continua obrigatória após autorização, antes de preview/OK. Grupos A/B, nome
destacado, perfil secundário, elisão, tooltips e diagnósticos são os aprovados.

Mantêm-se o plano comum separador, contato real de tampas/contornos, um sólido
válido por membro e veto de interpenetração acima das tolerâncias existentes.
As duas candidatas e a confirmação usam o mesmo pipeline PlaneCut, sem recorte
pelo sólido parceiro, nova propriedade, schema, migração ou relação associativa.
O eixo nominal e o slot oposto são preservados; a confirmação é uma única
transação com revalidação bilateral e rollback. FCStd guarda dois cortes Fixed.

## Árvores isoladas e método

Evidências: `test-results/miter-trim-closure/` (fora do inventário de commit).

- `base/`: extração de `git archive --format=zip` do objeto local `6e8f0e1e99e7d15c2a8f6bfa97c502437cd53644`.
- `candidate/`: cópia integral dessa base sobreposta somente com os 10 caminhos
  da whitelist deste relatório. Sem `.git`, worktree registrada ou commit auxiliar.
- Workspace: árvore local completa, preservando estudos, modelos e experimentos.

A candidata não contém o arquivo experimental de plate nem estudos não publicados.
O delta final contra a base é exatamente **8 modificados + 2 novos**, sem remoções
ou extras fora de caches/evidências. Cada arquivo selecionado corresponde por
SHA-256 ao workspace. `inventory.json`, `selection-final.json`,
`candidate-manifest.json` e `candidate-delta.json` registram a seleção e os hashes.
Não houve consulta ou escrita no remoto; a base publicada foi a indicada pelo usuário.

O relatório definitivo foi copiado para a candidata depois de consolidar os
resultados. Essa atualização é somente documental: fontes Python, testes e runner
finais têm os mesmos hashes executados. Não foi preciso adaptar a candidata para
importar experimentos ou buscar código no workspace.

## Suíte Python completa nas três árvores

Executado uma vez em cada raiz, com Python 3.11.9 e a descoberta completa padrão:

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
```

Um `sitecustomize` de auditoria observa `TextTestResult`, mantendo chamadas a
`super()` e os critérios de unittest; não seleciona, altera, suprime ou pula testes.
O hook é o único caminho adicional em PYTHONPATH, fora do pacote e dos testes.
Não foi feito rerun seletivo para substituir resultado da descoberta completa.
Foram conferidos IDs únicos e correspondência entre os casos registrados e testsRun.

| Árvore | Executados | Aprovados | Skips | Falhas/erros | Retorno |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base publicada `6e8f0e1` | 1994 | 1845 | 149 | 0/0 | 0 |
| Candidata isolada | 2006 | 1857 | 149 | 0/0 | 0 |
| Workspace completo | 2010 | 1861 | 149 | 0/0 | 0 |

**Nenhuma falha/erro nas três execuções.** Candidata adiciona **12 testes**, todos
aprovados: 4 de controlador, 2 de geometria e 6 de painel. Nenhum ID da base foi
removido; os **1.994 IDs comuns** mantêm o mesmo resultado. Os **2.006 casos comuns**
de candidata/workspace também são idênticos. Comandos, tempos, diretórios e logs:
`{base,candidate,workspace}-summary.json`, `*-unittest.log` e `*-cases.json`.
A comparação por ID/motivo está em `comparison.json`.

Coincidência de pontas, colinearidade e veto a expressões são complementados
pelos testes Python `test_coincident_endpoints`,
`test_parallel_and_collinear_rejected` e `test_current_eligibility_restrictions`;
não são apresentados como fixtures nativas específicas desta campanha.

Novos IDs do incremento:

```text
test_member_miter_controller.MiterControllerTests.test_global_trim_consent_and_revocation
test_member_miter_controller.MiterControllerTests.test_one_global_permission_covers_exact_required_set
test_member_miter_controller.MiterControllerTests.test_presentation_and_member_touched_flag_do_not_change_consent_token
test_member_miter_controller.MiterControllerTests.test_trim_permission_requires_explicit_end_and_an_interior_encounter
test_member_miter_geometry.MiterGeometryTests.test_controlled_trim_matrix_and_selection_order
test_member_miter_geometry.MiterGeometryTests.test_interior_requires_choice_and_each_permission_even_for_large_tail
test_member_miter_task_panel.MiterPanelMountTests.test_consent_click_cannot_authorize_an_amount_changed_before_polling
test_member_miter_task_panel.MiterPanelMountTests.test_member_caption_deduplicates_only_presentation
test_member_miter_task_panel.MiterPanelMountTests.test_opening_popup_refreshes_before_showing_options
test_member_miter_task_panel.MiterPanelMountTests.test_popup_only_rebuilds_the_editor_when_inputs_or_presentation_changed
test_member_miter_task_panel.MiterPanelMountTests.test_sync_updates_both_alternatives_without_parsing_text_or_authorizing
test_member_miter_task_panel.MiterPanelMountTests.test_trim_option_text_uses_pt_br_values_and_stable_internal_ids
```

### Skips ambientais

Os **149 skips têm os mesmos IDs e os mesmos motivos** nas três árvores. Não
há skip novo pelo incremento, expected failure ou unexpected success.

| Motivo literal | Casos |
| --- | ---: |
| `Real FreeCAD GUI / Qt event loop required` | 30 |
| `PySide6 não disponível neste Python` | 26 |
| `FreeCAD/Draft native Python required` | 15 |
| `FreeCAD GUI and Qt required` | 47 |
| `FreeCAD Units and PySide6 required` | 8 |
| `FreeCAD units and PySide6 required` | 15 |
| `PySide6 required` | 8 |

Esses casos precisam de FreeCAD/Draft/Qt/Units reais, indisponíveis no Python de
descoberta; não são contabilizados como aprovados. Os gates nativos abaixo cobrem
os fluxos pertinentes ao aparo e ao MVP, sem pretender substituir toda a matriz
GUI das demais ferramentas. A lista completa dos IDs pulados permanece no JSON.

### Experimentos externos

Workspace contém exatamente **4 testes adicionais**, todos aprovados, em
`tests/test_plate_qt_lifecycle_probe.py`. Não são parte do aparo, não foram incluídos
na candidata nem removidos/alterados no workspace:

```text
test_plate_qt_lifecycle_probe.LifecycleProbeSafetyTests.test_caught_native_exception_stops_even_with_exit_zero
test_plate_qt_lifecycle_probe.LifecycleProbeSafetyTests.test_native_signatures_and_timeout_always_stop
test_plate_qt_lifecycle_probe.LifecycleProbeSafetyTests.test_python_failure_is_not_success_even_with_exit_zero
test_plate_qt_lifecycle_probe.LifecycleProbeSafetyTests.test_warning_only_does_not_mask_success
```

Não houve falha experimental ocultada, skip introduzido ou teste enfraquecido para
obter o GO. Não foi necessária alteração em teste ou código neste fechamento.

## Gates completos FreeCAD 1.1.4 na candidata

Executados sequencialmente com cwd `candidate/`, runner/probe da própria candidata
e perfil isolado por processo. Comandos diretos equivalentes aos wrappers de auditoria:

```powershell
python scripts/run_member_miter_joint_gate.py --theme Classic --output-root ../native --timeout 600
python scripts/run_member_miter_joint_gate.py --theme "FreeCAD Dark" --output-root ../native --timeout 600
python scripts/run_member_miter_joint_gate.py --theme OpenDark --output-root ../native --timeout 600
```

Nos comandos executados, output-root usa o caminho absoluto equivalente.
O launcher removeu SS_MITER_UI_ONLY, QT_SCALE_FACTOR e PYTHONPATH herdados.
Os manifestos confirmam **ui_only=False**, sem escala solicitada e root candidato.
Bootstrap aponta explicitamente sys.path/namespace freecad para essa árvore.

| Tema | Checks | Resultado | Pasta em `native/` |
| --- | ---: | --- | --- |
| Classic | 2888 | OK | `1792842808012150800_Classic__9hfmz54` |
| FreeCAD Dark | 2888 | OK | `1792844155073361500_FreeCAD_Dark_0v0mmbws` |
| OpenDark | 2888 | OK | `1792844282522833100_OpenDark_mbhbpatn` |

**3 execuções, 3 sucessos, 8.664 checks**, retorno zero, nenhum timeout, callbacks
Python/Qt vazios e filtros de stderr/FreeCAD.log vazios. Não houve tentativa
nativa falha ou repetição nesta auditoria. Checks são verificações de gate, não
testes unitários independentes. Os **153 hashes de fontes** são idênticos entre
os três manifestos e correspondem à candidata final. `native-comparison.json`
consolida fontes, checks, métricas de apresentação, estilos e logs.

### Cobertura prioritária confirmada

- **A/B/ambos e pontas:** matriz adicional de 49 pares por tema, SHS em
  60°/90°/120°, quatro combinações Start/End e aparo em A/B/ambos; W, U, Ue e RHS
  nos três ângulos; sobras de 10.000/8.000 mm; ordem A/B equivalente.
- **Valores:** distâncias axiais conferidas, inclusive extensão livre; opções
  antes de escolher, campo fechado, abertura/atualização entre polls, separador
  de milhar/decimal, itemData preservado e ponta ocupada indisponível.
- **Consentimento:** uma checkbox real para A/B/ambos, habilitada só após todas
  as escolhas; escolhas sem autorização não permitem confirmar. Revogação por
  ponta, membro, extensão/valor e geometria; reversão não ressuscita token.
  Alterações de nome/cor/display/visibilidade/paleta/resize/vista e escolhas
  idênticas preservam o consentimento da configuração material.
- **Preview:** duas Shapes reais e branches Coin, comparação BRep bidirecional
  das candidatas/previews com o resultado confirmado. Casos inválidos removem
  os dois previews e bloqueiam OK; não há uso de Shape antiga como evidência.
- **Geometria:** semiespaços opostos, tampas/contornos coincidentes com contato
  útil, volume comum dentro da tolerância e um sólido válido por participante.
  Rejeições de ocupação, eliminação/alcance da ponta oposta, contato incompatível,
  paralelos, eixos afastados/reversos, perfis/rolls incompatíveis,
  Linked, dependências e filhos de treliça continuam cobertas.
- **Transação:** uma ação bilateral, recompute/verificação definitiva dos dois
  membros, falha tardia injetada e restauração integral do par sem Undo adicional.
  Ajuste oposto Fixed e associação externa elegível são preservados.
- **Histórico:** Undo/Redo bilateral, reabertura/reaplicação imediata sem recompute
  manual, múltiplos ciclos, ponta ocupada após Redo, nova ligação na ponta livre,
  sentinelas pendentes não executadas e rejeição de fontes pendentes.
- **Cancelamento e recursos:** antes/depois de autorizar, Cancelar, Esc, fechar
  form/tarefa, excluir/trocar alvo, vista/documento e desativar bancada. Sem helper
  persistente; branches/marcador/máscaras restaurados e timer/observer próprios limpos.
- **FCStd:** salvar, fechar, restaurar e recomputar; propriedades, sólidos, massa
  e eixos nominais preservados. Os parceiros continuam fixos e independentes.
- **Convencionais:** a matriz original do MVP, com pontas/raios exteriores e
  prolongamento, W60/90/120, frames inclinados, roll compatível, App::Part comum,
  distinto/aninhado e movimento de parent, é repetida sem controles de aparo.
- **Apresentação:** nomes personalizados/longos, perfil sem duplicação, uma linha
  elidida com tooltip integral, grupos A/B e botão centralizados, larguras **280 e
  360 pixels lógicos**, valores sem coluna duplicada, popup A/B e semântica do OK.

Contraste dos estados finais, medido no painel composto (razão, todos ≥4,5):

| Tema | Neutro | Bloqueio | Sucesso |
| --- | ---: | ---: | ---: |
| Classic | 20.29 | 5.05 | 5.03 |
| FreeCAD Dark | 13.77 | 6.24 | 7.39 |
| OpenDark | 11.85 | 4.71 | 8.27 |

Capturas da candidata nos três temas foram inspecionadas: painel estreito,
agrupamento, fonte secundária, valores e alternativa indisponível. Capturas de
janela têm o artefato OpenGL já documentado; são usadas para o painel. Grabs diretos
do formulário/listas e BRep/renders separados complementam a evidência.

O probe já aprovado fixa o dock e desabilita apenas a animação transitória de
combobox na instância isolada de QA, para não capturar Tasks recolhido ou uma lista
em transição. Nenhuma preferência da sessão do usuário é alterada. A prova Qt a
150% (devicePixelRatio=1,5) do refinamento anterior permanece registrada no relatório
do aparo; não foi repetida neste fechamento, cujos três gates completos usam a
escala ambiente limpa. Não se certificam todas as configurações físicas de DPI.

## Recortar/Ajustar e demais funcionalidades

O diff e a comparação byte a byte de **151 módulos Python de produção** identificam
somente os três módulos miter modificados. Recortar/Ajustar (controlador, painel,
referências, preview e geometria), member.py, member_batch.py, member_plane_cut.py,
geradores de seção, fitting, treliças, Gusset, StructuralPlate, comandos/registro,
ícones, catálogos e metadados de release estão iguais à base publicada.

Além da suíte ampla sem regressão por ID, **135 testes de ajustes, referências,
associatividade, PlaneCut e orientação** passam com os mesmos IDs/resultados da
base. Os gates miter exercitam o pipeline compartilhado real. Não foi feito um
novo teste manual de todas as outras interfaces, nem se alega isso: a conclusão
é ausência de mudança de código externo ao escopo e de regressão automatizada
conhecida. `shared-module-integrity.json` registra módulos iguais e alterados.

## Integridade e preservação

`python scripts/check_project.py` passou nas **três árvores**: sintaxe, arquivos
essenciais, versões sincronizadas e integridade de catálogos. Logs: `*-project.log`;
retornos: `project-checks.json`. `git diff --check` passou no workspace.

Como as árvores extraídas não possuem `.git`, foi feita também a equivalência
`git diff --no-index --check`: modificados contra base e novos contra NUL.
Os 10 caminhos foram verificados em UTF-8, sem trailing whitespace e com newline
final. Retornos 0/1 de no-index dependem da existência de delta; diagnósticos reais
são conferidos separadamente. Avisos LF→CRLF não são erros de whitespace.
`whitespace.json` e `new-file-integrity.json` registram as verificações finais.

O snapshot inicial contém **600 hashes**, incluindo o rascunho deste fechamento
e os caminhos selecionados; **590 arquivos ficam fora da seleção** e foram
preservados. Os **599 arquivos pré-existentes** ao novo fechamento, incluindo
os nove caminhos do incremento já locais, permanecem byte a byte iguais ao início.
Não houve remoção, mudança de estudo/modelo/back-up ou novo arquivo inesperado
fora da seleção/evidências. `preservation-final.json` contém a comparação.

Os 134 caminhos locais não rastreados externos ao incremento estão no anexo,
em `excluded-untracked.json` e `excluded-paths.txt`. Modelos e backups ignorados
também são protegidos pelos hashes quando presentes no snapshot. Evidências,
caches e metadados Git/configurações de ferramentas ficam fora do inventário;
não houve limpeza ou escrita em estudos anteriores de test-results. Só uma
pasta nova de auditoria foi usada para artefatos. HEAD e índice permanecem iguais
ao início; o índice continua vazio. Não houve operação Git de escrita/publicação.

## Inventário fechado para commit seletivo

**10 caminhos: 8 modificados e 2 novos**, relativos a `6e8f0e1`.
Relatórios do MVP já existem na base e não entram no delta.

| Estado | Caminho | Finalidade |
| --- | --- | --- |
| Modificado | `freecad/SteelStructures/member_miter_geometry.py` | Inspeção do encontro, escolha explícita e validação de consentimento no resolvedor puro |
| Modificado | `freecad/SteelStructures/interactive/member_miter_controller.py` | Consentimento global, assinatura material e alcance axial; mesma confirmação bilateral |
| Modificado | `freecad/SteelStructures/interactive/member_miter_task_panel.py` | Controles contextuais, valores Início/Fim, grupos A/B e diagnósticos aprovados |
| Modificado | `scripts/run_member_miter_joint_gate.py` | Gates isolados e opções de QA de apresentação/escala |
| Modificado | `tests/manual_member_miter_joint.py` | Matriz nativa de aparo, consentimento, histórico, persistência e apresentação |
| Modificado | `tests/test_member_miter_geometry.py` | Geometria pura, extremos, consentimento e ordem A/B |
| Modificado | `tests/test_member_miter_controller.py` | Contrato global, revogação e preservação em mudanças visuais |
| Modificado | `tests/test_member_miter_task_panel.py` | Apresentação, atualização, IDs e proteção de consentimento |
| Novo | `Documentation/MEMBER_MITER_CONTROLLED_TRIM.md` | Relatório da implementação e refinamentos aprovados |
| Novo | `Documentation/MEMBER_MITER_CONTROLLED_TRIM_CLOSURE.md` | Este fechamento técnico |

Os hashes completos estão em `selection-final.json`; `candidate-delta.json`
confirma ausência de extras, remoções ou divergência da seleção do workspace.
Não incluir diretórios inteiros nem estudos/reports adicionais por proximidade.

### Staging sugerido — NÃO EXECUTADO

Proposta revisável, também em `selective-staging.ps1.txt`:

```powershell
git add -- `
    "freecad/SteelStructures/member_miter_geometry.py" `
    "freecad/SteelStructures/interactive/member_miter_controller.py" `
    "freecad/SteelStructures/interactive/member_miter_task_panel.py" `
    "scripts/run_member_miter_joint_gate.py" `
    "tests/manual_member_miter_joint.py" `
    "tests/test_member_miter_geometry.py" `
    "tests/test_member_miter_controller.py" `
    "tests/test_member_miter_task_panel.py" `
    "Documentation/MEMBER_MITER_CONTROLLED_TRIM.md" `
    "Documentation/MEMBER_MITER_CONTROLLED_TRIM_CLOSURE.md"
```

Não executar staging global. Mensagem sugerida para um commit local futuro,
dependente de autorização separada, sem executá-lo nesta tarefa:

```text
feat: add controlled endpoint trimming to member miters

Require explicit endpoint choices and global consent for interior encounters.
Keep bilateral PlaneCut preview, atomic confirmation and existing persistence.
Add regression gates, compact presentation and technical closure.
```

## Riscos remanescentes e decisão

- **Redo anterior após abort:** no FreeCAD 1.1.4, a primeira escrita de uma nova
  transação descarta a pilha Redo anterior. Abort restaura ambos os membros e
  UndoCount, mas não reconstrói essa pilha. Cada gate repetiu o controle nativo
  Part::Box e a falha tardia do par; o comportamento coincide. Preview, cancelar
  e rejeições anteriores à escrita preservam histórico. Não há hack de replay.
- **Geometria/domínio:** OCC roda no thread da UI; casos mal condicionados ou
  seções/orientações sem fechamento são recusados conservadoramente. Não há
  garantia para todo perfil/roll, certificação de ligação/solda, T automático,
  corte volumétrico pelo parceiro, múltiplos participantes, associatividade,
  filhos de treliça ou encontros espaciais complexos.
- **Ajustes existentes:** ponta escolhida ocupada não é sobrescrita; associação
  oposta sob parent transformado, fontes pendentes, composições/AutoFit,
  expressões e eixos Linked permanecem fora do domínio documentado.
- **Plataformas:** executado FreeCAD 1.1.4/Qt6 em Windows. FreeCAD 1.1.3 e outras
  plataformas não foram revalidados nesta rodada solicitada para 1.1.4.

**GO para commit local seletivo dos 10 arquivos.** Aprovação manual funcional e
visual recebida, três suítes comparadas sem regressão, três gates completos
da candidata aprovados, inventário fechado e arquivos locais preservados.
A revisão técnica independente do código e da comparação não identificou bloqueador.
Não existe teste manual adicional exigido por mudança funcional deste fechamento,
pois não houve nenhuma. Este GO é uma conclusão técnica, **não uma execução ou
autorização de publicação**. Staging/commit não foram executados; push, merge,
tag e release permanecem não autorizados e não preparados.

## Anexo — 134 exclusões explícitas do status local

Preservar todos os caminhos abaixo e não incluí-los na candidata ou no staging.
Também excluir `test-results/**`, `__pycache__/**`, `.git/**`, `.codex/**`,
`.agents/**`, `.aws/**`, caches, modelos/backups locais novos (`*.FCStd*`,
`*.FCBak`) e qualquer caminho fora da whitelist dos 10 arquivos. Esses padrões
são exclusões de publicação, **não instruções de remoção**.

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

Modelos/backups ignorados adicionais capturados no inventário de preservação:

```text
tests/copiatreliça.20261010-220530.FCBak
tests/copiatreliça2.20261018-204557.FCBak
tests/copiatreliça2.20261021-192020.FCBak
```
