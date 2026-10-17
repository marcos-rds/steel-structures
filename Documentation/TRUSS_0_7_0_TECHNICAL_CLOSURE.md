# Fechamento técnico — Gerador de Treliças 0.7.0

Auditoria local contra `68dc4b4`, branch `develop/0.7.0`. O usuário informou aprovação manual completa no FreeCAD 1.1.4, incluindo massa, checkpoint e os três botões. Nenhuma publicação autorizada nesta rodada.

## Bloqueadores encontrados antes de qualquer ajuste

A primeira descoberta completa executou 1.804 testes, com três erros e 102 skips. Evidência integral: `test-results/truss_closure/unittest_full.log`.

1. `test_assembly_refinements`: o teste AST não fornecia contexto de pacote/locale para o import relativo do formatador `truss_units`; `KeyError: "'__name__' not in globals"` em `_setup_run_length`.
2. `test_gusset_plate_c6c`: a fixture do controlador não fornecia `App.ActiveDocument`, exigido pela proteção de documento ativo em `preview3d`.
3. `test_gusset_plate_document_c6b`: a fixture não fornecia `App.listDocuments` e o nome do documento, exigidos pela proteção contra restauração de visibilidade em documento fechado.

Diagnóstico: fixtures antigas incompatíveis com os contratos atuais, sem defeito funcional demonstrado nesses três casos. Foram completados os contextos/fakes, conservadas as assertivas de geometria/visibilidade e ampliadas as verificações de formatação e passagem de locale. Os 24 testes desses três módulos passaram, seguidos da suíte completa. **Nenhum arquivo de produção foi alterado nesta auditoria.**

## Parecer final

**GO técnico para futuro commit local seletivo dos 65 arquivos da lista anexa.** Não há bloqueador funcional conhecido do incremento aprovado; a aprovação manual informada pelo usuário está registrada. Este parecer não executa nem autoriza automaticamente commit ou publicação.

**Release: NO-GO nesta rodada.** O fechamento é local e seletivo, não uma campanha de release. A ocorrência histórica intermitente de Qt/Draft na StructuralPlate continua sem causa/correção estabelecida, embora não tenha reaparecido na única passagem integrada atual. Não foram preparados metadados, changelog de release, tag ou distribuição; nenhuma dessas operações foi solicitada.

Todos os gates obrigatórios executados nesta rodada terminaram aprovados. Isso não transforma uma passagem isolada em prova de ausência do defeito Qt histórico, nem remove os skips ambientais da suíte Python.

## Arquitetura consolidada desde 68dc4b4

- `TrussEditSession` é o modelo compartilhado de rascunho, candidato validado, histórico de reconciliação, baseline e estado aplicado. TaskPanel, editor gráfico e abas operam sobre a mesma sessão. Revisão/contexto/persistência bloqueiam candidato desatualizado e conflitos externos.
- `TrussController` permanece responsável por preview Coin e pelo fluxo transacional existente. Aplicar repetido conserva o owner e não cria transação/recompute quando não há mudanças. O fechamento libera captura, callbacks, preview, visibilidade temporária e recursos Qt sem encerrar a ferramenta sucessora.
- TaskPanel compacto conserva controles rápidos; o Editor modal mantém canvas, toolbar, Geometria em duas colunas, Perfis e Ligações. O acesso principal usa `TrussEditor.svg`; os oito SVGs da toolbar continuam integrados às ações reais de nós/barras e transformações da alma.
- No Editor, **Cancelar/X** restauram o checkpoint profundo e retornam ao TaskPanel; **Aplicar** materializa e renova o checkpoint sem fechar; **OK** aplica e fecha somente o Editor. O checkpoint inclui configuração completa, `last_candidate`, controles e texto numérico parcial. Não restaura baseline nem escreve objetos físicos; conflitos externos impedem rollback silencioso. Os botões do TaskPanel conservam sua semântica global.
- `TrussReferenceField`, `TrussLengthSpinBox` e `truss_units` usam unidades preferidas do FreeCAD e locale do widget, duas casas na apresentação e armazenamento preciso. Ponto inicial/final têm XYZ e comprimento; Normal do plano é adimensional. Layout responsivo e espelhos do Editor preservam edição parcial. A aquisição Draft não foi substituída.
- Novas configurações usam Pratt e referências físicas externas. `support_alignment*` e `realization` tratam o marcador de superfície; a ausência do marcador conserva o contrato legado no núcleo. Abrir/cancelar não migra sólidos existentes. Compatibilidade e reabertura foram verificadas pelos gates.
- `physical_mass` lê os sólidos finais registrados e pertencentes à treliça, após recortes e ajustes: banzos, montantes, diagonais, fechamentos, componentes de perfis compostos, interconectores materializados e Gussets físicos. Deduplica referências ao mesmo objeto, inclui peças ocultas e exclui grupos, fontes Draft e previews. Não usa união global nem massa nominal do catálogo; não provoca recompute.
- A massa é `soma(Shape.Volume em mm³) × 0,00000785 kg/mm³`. O peso linear divide por `distância física P0–P1 em metros`, inclusive em referências inclinadas, e não pela soma das barras. Densidade: 7.850 kg/m³. Inconsistências/peças relevantes sem sólidos contabilizáveis tornam o total indisponível, com diagnóstico.
- `physical_changes` separa mudanças físicas de seleção, aba, foco e apresentação. Massa atual mostra valores e unidades; pendência mostra dois traços e um aviso com relógio; erro mostra indisponibilidade. O aviso passa para baixo em largura reduzida. Massa só acompanha o estado efetivamente aplicado, sem segunda geração 3D na prévia.

Custom, restauração de padrão, perfis compostos, interconectores, ligações e Gussets continuam no pipeline existente. Não há novo schema de materiais ou massa persistente.

## Inventário e dependências

A proposta contém **65 caminhos únicos** em `TRUSS_0_7_0_STAGING.txt`, separados abaixo e com SHA-256 em `test-results/truss_closure/recommended_staging.json`.

| Grupo exclusivo | Arquivos |
|---|---:|
| Modificados já versionados: 11 de produção, runner e 14 testes | 26 |
| Novos módulos funcionais | 9 |
| Novos SVGs: oito da toolbar e um de acesso ao Editor | 9 |
| Novos testes permanentes: 10 unitários/Qt e sete gates manuais | 17 |
| Documentação selecionada, incluindo esta lista/relatório | 4 |
| **Total** | **65** |

São 20 arquivos de produção e 31 arquivos de teste no conjunto. As alterações em `assembly_editor`, `assembly_preview` e `interconnector_editor` são dependências funcionais da apresentação de comprimentos do Editor: precisam acompanhar os novos controles e formatadores.

Não foram encontrados imports de `test-results`, estudos ou diagnósticos na produção, dependências externas novas ou comandos públicos duplicados. `commands.py` está intacto; CreateTruss e UpdateTruss têm um registro cada. Os nove SVGs foram analisados como XML; a toolbar referencia exatamente os oito ícones esperados, carregados também no gate GUI. Os imports relativos foram conferidos contra a árvore seletiva.

`init_gui.py` foi examinado: `i/lf`, `w/mixed`, sem diferença textual em `git diff 68dc4b4` ou alteração funcional efetiva. **Excluído** da seleção e preservado sem normalização de fins de linha.

Ficam fora da proposta, intactos: 132 caminhos pendentes, incluindo estudos `Documentation/gusset_*`, experimentos/relatórios da StructuralPlate, diagnósticos descartáveis, dois FCStd de teste e os relatórios de etapas antigas que não representam o contrato final. Os relatórios de precisão/massa e checkpoint são mantidos por descreverem os mecanismos; este fechamento registra a aprovação manual posterior e prevalece sobre seus estados históricos de validação. Resultados, dumps, caches e probes de auditoria permanecem em diretório ignorado e não fazem parte da lista.

## Validação executada

Ambiente nativo: FreeCAD **1.1.4**, Python 3.11, binário `4fd3bf320d9566a27e60069fc8387448aaa3a094`, Windows. Gates com processo/perfil isolados; aplicação pessoal, instalação e preferências globais não foram alteradas.

| Verificação | Resultado final |
|---|---|
| Suíte Python completa no working tree | **1.804 executados: 1.702 aprovados, 102 skips, zero falhas/erros** |
| Cópia isolada de 68dc4b4 + somente 65 caminhos propostos | **1.800 executados: 1.698 aprovados, 102 skips, zero falhas/erros** |
| Qt real + unidades + geometria de seções, Python do FreeCAD | **73 aprovados**, sem skips |
| Alinhamentos Paralela/Duas Águas e geometria física | 251 verificações |
| Sessão compartilhada e referências | 23 |
| Apply transacional e repetido | 54 |
| Lifecycle Qt/Coin e encerramento externo | 95 |
| Undo/Redo e conflitos | 93 |
| Volume/massa física, recortes, compostos, Gussets e persistência | 79 |
| Cópia independente | 32 |
| Exclusão/Undo/Redo/reabertura | 12 |
| Editor ampliado/gráfico, campos, SVGs e documentos legados — Classic | 405 |
| Checkpoint, três botões e estados de massa — OpenDark | 124 |
| Captura Coin real de dois/três pontos, Draft Line/Rectangle, snapshot/vínculo e reabertura | 20 |
| Regressão Membro/Pilar/Grid/StructuralPlate | 6 grupos de verificações |
| StructuralPlate integrada, uma passagem e um ciclo | 48 verificações |
| `python scripts/check_project.py` | Aprovado |
| `git diff --check` | Aprovado |

Total dos gates de treliças: **1.188 verificações**; os gates adjacentes têm resultado separado. Contagens não somam testes repetidos ou substituem inspeção visual/manual. O usuário já aprovou manualmente o incremento completo; nesta rodada a confirmação GUI adicional foi automatizada.

Os 102 skips da descoberta no Python do sistema são ambientais: 30 exigem GUI/event loop real, 26 exigem PySide6, 15 FreeCAD/Draft nativo, oito FreeCAD Units/PySide6, 15 unidades FreeCAD/PySide6 e oito PySide6. Os 73 testes nativos complementares exercitam os módulos relevantes; não se afirma que todos os 102 skips foram eliminados.

A diferença de quatro testes entre working tree e árvore seletiva é o módulo local `test_plate_qt_lifecycle_probe.py`, que testa um diagnóstico descartável excluído. Nenhuma cobertura permanente de treliças foi removida. A árvore isolada demonstra que os experimentos não são necessários para a suíte seletiva.

Uma primeira tentativa do wrapper de coleta JSON usou `sys.path` inadequado por estar em `test-results`; ela é inválida como resultado do projeto e foi preservada separadamente em `unittest_harness_path_error.*`. Após acrescentar a raiz ao wrapper, a descoberta completa passou. A execução direta original e a execução direta na árvore seletiva também permanecem registradas.

### Comandos

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m unittest tests.test_assembly_refinements tests.test_gusset_plate_c6c tests.test_gusset_plate_document_c6b
```

A coleta final detalhada usa `python test-results/truss_closure/run_full.py`, com a mesma descoberta completa e JSON de erros/skips. A execução da árvore seletiva usa `verify_selective.py`, que extrai `git archive 68dc4b4` e sobrepõe apenas a lista, sem checkout ou staging.

```powershell
& 'C:/Users/marco/Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311/bin/python.exe' -m unittest tests.test_truss_length_precision tests.test_truss_reference_fields tests.test_gusset_preview_qt_c6q tests.test_truss_visual_polish tests.test_freecad_section_geometry
python scripts/run_truss_duopitch_gate.py --probe alignment
python scripts/run_truss_duopitch_gate.py --probe session
python scripts/run_truss_duopitch_gate.py --probe apply
python scripts/run_truss_duopitch_gate.py --probe lifecycle
python scripts/run_truss_duopitch_gate.py --probe undo
python scripts/run_truss_duopitch_gate.py --probe mass
python scripts/run_truss_duopitch_gate.py --probe copy
python scripts/run_truss_duopitch_gate.py --probe delete
python scripts/run_truss_duopitch_gate.py --probe editor --editor-theme Classic
python scripts/run_truss_duopitch_gate.py --probe editor_actions --editor-qss 'C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss'
python test-results/truss_closure/launch_references.py
python scripts/run_plate_unified_gate.py --version 1.1.4 --stage regression --processes 1 --cycles 1
python scripts/run_plate_unified_gate.py --version 1.1.4 --stage integrated --processes 1 --cycles 1
python scripts/check_project.py
git diff --check
```

O probe suplementar de referências usa cliques Qt reais na vista Coin, sem simular o controlador, para adquirir dois e três pontos. Fontes Line/Rectangle são objetos Draft reais selecionados, aplicados e reabertos com vínculo. Esse probe de fechamento é evidência descartável, não dependência funcional nem item de staging.

### StructuralPlate e risco Qt conhecido

O smoke de regressão passou em `test-results/plate_unified_gate/1792249898250201700_1.1.4_regression/1`. Cobre comandos públicos Membro/Pilar/Grid após chapa, sólidos/recompute, Undo/Redo, save/reopen e o probe existente de Placement do Grid.

A passagem integrada única passou em `test-results/plate_unified_gate/1792250246573854500_1.1.4_integrated/1`: exit 0, 48 verificações, nenhum dump novo e instalação preservada. Incluiu `replacement_draft_line_native_and_advanced`. Os logs atuais não contêm traceback ou assinatura nativa relevante.

Assinatura histórica que continua registrada, mas **não ocorreu nesta passagem**:

```text
gui_lines.py:86 Activated → DraftGui.py:849 lineUi
→ pointUi:907 → taskUi:756 → setupToolBar:353/357
→ _inputfield:284 inputfield.setObjectName(name)
RuntimeError: Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.
```

Sequência histórica: chapa Polígono → plano Auto → painel avançado vazio → chamada direta de Draft Line, sem Cancelar antes da substituição. A investigação anterior reproduziu a falha no baseline `14449d2` sem importar treliças. Isso sustenta a classificação preexistente, com causa inconclusiva; não prova que todo erro Qt futuro terá a mesma causa. Nenhuma correção especulativa ou campanha repetida foi realizada aqui.

## Riscos e pendências

- Não há bloqueador conhecido para o commit seletivo. O estado inicial da suíte reprovado foi corrigido somente nas três fixtures, antes da passagem final.
- O risco Qt/Draft histórico permanece aberto para acompanhamento separado. Sucesso isolado atual não prova correção de intermitência.
- Quantitativo pressupõe aço homogêneo a 7.850 kg/m³. Shape inválida, registro inconsistente ou Gusset solicitado sem peça contabilizável tornam o resultado indisponível; não há aproximação silenciosa.
- Não foram criadas propriedades de material, listas de corte ou novos quantitativos. Não houve mudança de versão/schema nesta auditoria.
- Os 65 hashes descrevem o estado auditado. Qualquer edição posterior exige reconferir inventário e validação pertinente antes do futuro staging.

## Estado Git e preservação

| Estado | Antes | Depois |
|---|---|---|
| Branch | develop/0.7.0 | develop/0.7.0 |
| HEAD | 68dc4b4dffb573f5db677ec92177c3fa34aab98b | mesmo |
| Caminhos tracked marcados modificados | 24 | 27 |
| Não rastreados, fora dos ignorados | 168 | 170 |
| Staging | vazio | vazio |

Os três modificados adicionais são as fixtures corrigidas; os dois novos arquivos desta auditoria são este relatório e a lista seletiva. Todos os arquivos locais anteriores fora desses três testes foram conferidos por hash e preservados. `init_gui.py`, estudos Gusset, experimentos, FCStd e documentação excluída continuam intactos.

Não houve `git add`, commit, push, merge, tag, release, reset, clean, normalização de EOL ou reorganização dos excluídos. O único `git archive` foi leitura do commit base para criar a árvore descartável em `test-results`.

Evidências completas: `test-results/truss_closure/` — estado Git antes/depois, inventário com categorias/hashes, arquivos excluídos, logs das suítes, fontes/gates e auditoria final. Nenhum resultado gerado integra a proposta de staging.

## Lista exata para staging seletivo futuro

Fonte textual de caminhos, um por linha: **`Documentation/TRUSS_0_7_0_STAGING.txt`**. O arquivo contém 65 entradas únicas, incluindo a própria lista. Não é script e não executa staging. A separação por categoria e os hashes ficam no JSON de auditoria; os grupos são reproduzidos a seguir.

### 1. Modificados já versionados — 26

```text
freecad/SteelStructures/interactive/assembly_editor.py
freecad/SteelStructures/interactive/assembly_preview.py
freecad/SteelStructures/interactive/interconnector_editor.py
freecad/SteelStructures/interactive/truss_controller.py
freecad/SteelStructures/interactive/truss_preview.py
freecad/SteelStructures/interactive/truss_task_panel.py
freecad/SteelStructures/interactive/truss_topology_editor.py
freecad/SteelStructures/truss.py
freecad/SteelStructures/trusses/realization.py
freecad/SteelStructures/trusses/support_alignment.py
freecad/SteelStructures/trusses/support_alignment_freecad.py
scripts/run_truss_duopitch_gate.py
tests/manual_freecad_truss_duopitch.py
tests/test_assembly_refinements.py
tests/test_connection_topology_preservation.py
tests/test_connections_c5b_polish.py
tests/test_gusset_plate_c6c.py
tests/test_gusset_plate_document_c6b.py
tests/test_gusset_preview_qt_c6q.py
tests/test_truss_c2_custom_review.py
tests/test_truss_c2_editor.py
tests/test_truss_c2_refinements.py
tests/test_truss_duopitch_ui.py
tests/test_truss_manual_fixes.py
tests/test_truss_support_alignment.py
tests/test_truss_task_panel.py
```

### 2. Novos módulos funcionais — 9

```text
freecad/SteelStructures/interactive/truss_editor_checkpoint.py
freecad/SteelStructures/interactive/truss_editor_fields.py
freecad/SteelStructures/interactive/truss_length_spinbox.py
freecad/SteelStructures/interactive/truss_reference_field.py
freecad/SteelStructures/interactive/truss_task_widgets.py
freecad/SteelStructures/interactive/truss_units.py
freecad/SteelStructures/trusses/edit_session.py
freecad/SteelStructures/trusses/physical_changes.py
freecad/SteelStructures/trusses/physical_mass.py
```

### 3. Novos SVGs — 9

```text
Resources/Icons/TrussBarAdd.svg
Resources/Icons/TrussBarRemove.svg
Resources/Icons/TrussEditor.svg
Resources/Icons/TrussNodeAdd.svg
Resources/Icons/TrussNodeMove.svg
Resources/Icons/TrussNodeRemove.svg
Resources/Icons/TrussSelect.svg
Resources/Icons/TrussWebInvert.svg
Resources/Icons/TrussWebMirrorCopy.svg
```

### 4. Novos testes permanentes — 17

```text
tests/manual_freecad_truss_apply.py
tests/manual_freecad_truss_editor.py
tests/manual_freecad_truss_editor_actions.py
tests/manual_freecad_truss_lifecycle.py
tests/manual_freecad_truss_mass.py
tests/manual_freecad_truss_session.py
tests/manual_freecad_truss_undo.py
tests/test_truss_apply_session.py
tests/test_truss_edit_session.py
tests/test_truss_editor_actions.py
tests/test_truss_editor_opening.py
tests/test_truss_length_precision.py
tests/test_truss_lifecycle.py
tests/test_truss_physical_changes.py
tests/test_truss_physical_mass.py
tests/test_truss_reference_fields.py
tests/test_truss_visual_polish.py
```

### 5. Documentação selecionada — 4

```text
Documentation/TRUSS_0_7_0_EDITOR_CHECKPOINT.md
Documentation/TRUSS_0_7_0_PHYSICAL_MASS_PRECISION.md
Documentation/TRUSS_0_7_0_TECHNICAL_CLOSURE.md
Documentation/TRUSS_0_7_0_STAGING.txt
```
