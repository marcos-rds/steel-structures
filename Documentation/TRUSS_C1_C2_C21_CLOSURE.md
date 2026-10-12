# Fechamento técnico de Treliças C1/C2/C2.1

Data: 11/10/2026. Branch `develop/0.7.0`; base commitada
`14449d2e3945516243d2ed0510d39cb1265d7e7e`.

**Recomendação final: NO-GO para o fechamento global solicitado.** Os gates de
treliças passaram, mas o gate integrado de StructuralPlate falhou duas vezes no
fluxo placa avançada → Draft Line. Não há evidência suficiente para atribuir a
causa ao Draft ou às alterações de treliças. Essa pendência deve ser classificada
antes de declarar todos os gates aprovados e recomendar o commit sem ressalvas.
Nenhum commit ou staging foi realizado.

## Inventário e revisão seletiva

Na entrada: 11 arquivos rastreados com diferença de conteúdo e 132 arquivos não
rastreados, incluindo 95 arquivos de estudos Gusset. `init_gui.py` também aparece
como modificado no status, mas não possui diff de conteúdo: aviso de LF/CRLF;
excluído da seleção, sem normalização nesta rodada.

- `truss.py`: reconhecimento restrito da cópia rasa do agregado, reconstrução
  independente de membros/grupos/ligações, visibilidade e exclusão por ownership;
  propriedades aditivas de alturas/alinhamento e realização paramétrica.
- `trusses/{models,envelope,patterns,drivers,editing,realization}.py`: alturas
  nominais, topologia nas extremidades, restauração/rollback e integração do frame
  físico, preservando configurações avançadas e intenções de ligação.
- Novos `support_alignment.py` e `support_alignment_freecad.py`: mecanismo
  compartilhado por Paralela e Duas Águas, consulta das seções e validação OCC.
  Considera inserção, rotação e componentes. O owner mantém a referência bruta;
  o frame de realização aplica o alinhamento. `BottomChord` permanece o padrão.
  Paralela mantém `NominalSpan == Span`; Duas Águas conserva a distinção entre
  distância de referência e vão nominal derivado. Não há mudança de schema.
- `interactive/truss_{controller,preview,task_panel}.py`: encaminhamento dos
  parâmetros, cotas nominais externas compactas, referência discreta e tooltips.
  São alterações acumuladas anteriores; nenhuma modernização de UI nesta rodada.
- Testes novos cobrem alturas, topologia personalizada, cópia, rollback, alinhamento
  físico e apresentação; macros e launcher permitem gates nativos reproduzíveis.
- Quatro documentos históricos de treliças preservam contexto e limitações de
  cada etapa. Este relatório registra os resultados posteriores da consolidação.

A revisão técnica independente não identificou bloqueador funcional concreto no
diff de treliças. Pontos sensíveis examinados: ownership exato, links estrangeiros,
rollback completo, Placement local, remoção posterior à validação e restauração.

Única alteração nesta rodada em arquivo preexistente: no gate
`tests/manual_freecad_truss_c1.py`, a injeção de falha preflight passou de
`prepare_member` para `prepared_item`. A incompatibilidade já existia em
`14449d2`: `prepare_batch` já usava `prepared_item`. A execução inicial não atingiu
a injeção (`counter == 0`). Todas as assertivas de falha, snapshot, estado e
recuperação foram mantidas. Nenhum arquivo funcional foi alterado nesta rodada.

## Resultados

Todos os gates nativos abaixo utilizaram FreeCAD **1.1.4**, em processos isolados.
A aprovação visual/manual anterior é a informada pelo usuário; esta rodada foi
automatizada e não substitui nem inventa nova validação manual.

| Verificação | Resultado |
|---|---|
| Suíte Python completa | 1.695 executados: 1.637 aprovados, 58 skips, 0 erros, 0 falhas; 69,209 s; exit 0 |
| Treliça: alturas/alinhamento/documento/Qt | 218 checks, OK |
| Draft Move: cópia de treliça | 32 checks, OK |
| Exclusão GUI de agregados | 12 checks, OK |
| C1, após manutenção da injeção | 2.184 checks, OK |
| C3B: configurações compostas | 10 cenários, OK; editor Qt: OK, Cancelar preserva documento e família incompatível é rejeitada |
| Placa: regression | 6 checks, OK; inclui Membro/Pilar, sólidos, recompute, Undo/Redo e save/reopen |
| Placa: geometry | 15 testes nativos + 30 de entrada numérica, todos OK, sem skips |
| Placa: tracker | 4 ciclos, OK; mouse, teclado, criação numérica e cancelamento |
| Placa: integrated | **Falha em duas execuções**, após 42 checks aprovados em cada uma |
| `python scripts/check_project.py` | OK |
| `git diff --check` | OK; aviso LF/CRLF de `init_gui.py`, sem erro de whitespace |

Skips da suíte: 30 exigem GUI/event loop Qt real; 13 exigem PySide6 indisponível no
Python externo; 15 exigem Python nativo FreeCAD/Draft. Os gates nativos exercitam
parte dessa cobertura; não se afirma que substituem individualmente os 58 skips.
O log preserva cada teste e seu motivo. O wrapper de auditoria teve erro de
codificação no console depois de gravar o resultado; o subprocesso unittest
terminou com exit 0 e `OK (skipped=58)`.

Comandos principais executados:

```powershell
python -m unittest discover -s tests -p test_*.py -v
python scripts/run_truss_duopitch_gate.py
python scripts/run_truss_duopitch_gate.py --probe copy
python scripts/run_truss_duopitch_gate.py --probe delete
python scripts/run_plate_unified_gate.py --version 1.1.4 --stage regression --processes 1 --cycles 1
python scripts/run_plate_unified_gate.py --version 1.1.4 --stage integrated --processes 1 --cycles 2
python scripts/run_plate_unified_gate.py --version 1.1.4 --stage geometry --processes 1 --cycles 1
python scripts/run_plate_unified_gate.py --version 1.1.4 --stage tracker --processes 1 --cycles 4
python scripts/check_project.py
git diff --check
```

O comando integrated foi executado duas vezes. C1 e C3B foram chamados por
`python test-results/truss_copy/run_probe.py`, com `TRUSS_COPY_PROBE` apontando para
`test-results/truss-closure/existing_gates.py` e `SS_CLOSURE_GATE=c1` ou `c3b`.
Esse adaptador chama as funções existentes `run` e, em C3B, `run_editor`, sem
substituir suas assertivas.

## Cobertura e riscos

Treliças: alturas vinculadas/independentes, extremidades nulas/positivas,
alinhamento inferior/superior nas duas formas, perfis simples/compostos,
inserção/rotação, referências horizontais/inclinadas/invertidas, snapshot e
associativa, propriedades persistentes, recompute e Placement. Cópia, visibilidade,
exclusão, regeneração, save/reopen e Undo/Redo passaram. C1 também testa conflitos
controlados, membros ausentes, falhas automáticas/transacionais e recuperação.
C3B cobre transições Single/Double, espaçamento, ajustes manuais e prévia 3D sem
mutação do documento. O gate Qt exercita prévias em diferentes dimensões.

Gussets/interconectores: materialização em composto, sobrevivência à troca de
alinhamento e exclusão/cópia de agregado com ligações passaram. Não foi executada
uma matriz exaustiva de todas as famílias experimentais de Gusset.

No gate de alinhamento houve duas mensagens nativas
`pending remove of StructuralMember... after recomputing document legacy`.
O gate passou, incluindo a verificação de regeneração sem resíduos. As mensagens
não foram ocultadas. Não apareceu `Recursive calling of recompute` nos logs dos
gates de treliças desta rodada; não foi repetida a investigação geral do Draft.

A falha de StructuralPlate ocorre em
`tests/manual_plate_unified_native.py:1201`: o painel ativo esperado de Draft Line
não existe após substituir a placa avançada. O traceback anterior termina em
`DraftGui.py`, `_inputfield`, `inputfield.setObjectName(name)`, com
`Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted`.
O comando anterior estava finalizado e a sessão fechada. Isso comprova uma falha
de lifecycle no fluxo testado, mas não sua causa. Não é o aviso conhecido de
recompute e não pode ser descartado como mensagem benigna. Ambos os processos
encerraram com exit 0, porém o resultado do probe/launcher foi reprovado; não
houve novos crash dumps e os arquivos monitorados da instalação foram preservados.
Os módulos de placa não têm alterações funcionais neste conjunto.

Limites preservados: cópias associativas continuam usando a mesma fonte externa;
`Document.removeObject` direto não executa a limpeza GUI de `onDelete`; prévia do
agregado durante Draft Move permanece fora do escopo. Não foram criados novos
recursos de Gusset, editor compartilhado, abas ou arquitetura paramétrica.

## Seleção exata proposta para staging futuro

**30 arquivos**, após classificação da pendência. Lista declarativa; nenhum
`git add` foi executado. Não usar staging global.

```text
freecad/SteelStructures/interactive/truss_controller.py
freecad/SteelStructures/interactive/truss_preview.py
freecad/SteelStructures/interactive/truss_task_panel.py
freecad/SteelStructures/truss.py
freecad/SteelStructures/trusses/drivers.py
freecad/SteelStructures/trusses/editing.py
freecad/SteelStructures/trusses/envelope.py
freecad/SteelStructures/trusses/models.py
freecad/SteelStructures/trusses/patterns.py
freecad/SteelStructures/trusses/realization.py
freecad/SteelStructures/trusses/support_alignment.py
freecad/SteelStructures/trusses/support_alignment_freecad.py
tests/test_truss_manual_fixes.py
tests/test_truss_copy.py
tests/test_truss_duopitch_custom.py
tests/test_truss_duopitch_heights.py
tests/test_truss_duopitch_ui.py
tests/test_truss_regeneration_rollback.py
tests/test_truss_support_alignment.py
tests/manual_freecad_truss_c1.py
tests/manual_truss_copy.py
tests/manual_freecad_truss_duopitch.py
tests/manual_freecad_truss_delete.py
tests/manual_truss_move_diagnostics.py
scripts/run_truss_duopitch_gate.py
Documentation/TRUSS_DRAFT_COPY_FIX.md
Documentation/TRUSS_DRAFT_MOVE_DIAGNOSTICS.md
Documentation/TRUSS_DUOPITCH_SUPPORT_GEOMETRY.md
Documentation/TRUSS_REFERENCE_REFINEMENT.md
Documentation/TRUSS_C1_C2_C21_CLOSURE.md
```

Excluir da seleção e preservar integralmente: os 95 arquivos em
`Documentation/gusset_family_review`, `gusset_phase1`, `gusset_round1`,
`gusset_tip_depth` e `gusset_tip_round2`; nove documentos
`Documentation/STRUCTURAL_PLATE_0_7_0_*.md`; scripts `diagnose_plate_heap.py`,
`diagnose_plate_qt_lifecycle.py`, `diagnose_plate_tracker_stability.py`; testes
`manual_plate_heap_comparison.py`, `manual_plate_heap_setvalues_probe.py`,
`manual_plate_numeric_input.py`, `manual_plate_qt_lifecycle.py`,
`manual_plate_rectangle_lifecycle_gate.py`, `manual_plate_tracker_stability.py`,
`manual_point_input_probe.py`, `test_plate_qt_lifecycle_probe.py`;
`tests/copiatreliça.FCStd`; `init_gui.py`; todos os resultados, perfis temporários,
capturas e adaptadores em `test-results/`.

## Evidências e preservação

Logs locais (não recomendados para commit):

- `test-results/truss-closure/`: inventário inicial, diff inicial, suíte/log dos
  skips, logs dos launchers, verificações de integridade e preservação.
- `test-results/truss-duopitch/1791766938684847100`: alinhamento;
  `1791767033389770900`: cópia; `1791767046611334600`: exclusão.
- `test-results/truss_copy/1791767053069672000`: C1 inicial reprovado;
  `1791767228298065500`: C1 corrigido; `1791767252691228200`: C3B/editor.
- `test-results/plate_unified_gate/1791767090772209200_1.1.4_regression`;
  `1791767116070432000_1.1.4_integrated` e
  `1791767274864168500_1.1.4_integrated` (falhas);
  `1791767326515347600_1.1.4_geometry`;
  `1791767347534762200_1.1.4_tracker`.

Comparação SHA-256 dos arquivos preexistentes confirma: os **95 estudos Gusset
inalterados**, experimentos e arquivos funcionais preservados. A única diferença
em arquivo preexistente nesta rodada é o ponto de injeção do gate C1. Acrescentado
este relatório. Branch e HEAD mantidos; índice vazio. Sem alteração de versão,
changelog, tags, release, commit ou push.

Próximo passo restrito recomendado: classificar/reproduzir isoladamente o fluxo
placa avançada → Draft Line; então atualizar o parecer de fechamento. A
modernização UX/UI continua sem ser iniciada.
