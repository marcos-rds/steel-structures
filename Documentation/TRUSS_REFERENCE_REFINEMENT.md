# Refinamento localizado de treliças — 0.7.0

Branch `develop/0.7.0`, HEAD `14449d2`. Alterações locais, prontas para
validação do usuário; sem staging, commit, push, alteração de versão ou changelog.
Os desenvolvimentos anteriores, StructuralPlate e estudos Gusset foram preservados.

## Referência física compartilhada

Paralela e Duas Águas usam `upper_section_offset`, `aligned_frame` e a mesma
validação OCC das seções finais nos apoios. A consulta considera geometria do
perfil, inserção, rotação, transformações dos componentes e disposição do composto.
Interconectores não definem o topo da seção do banzo.

Na Paralela, a referência local fica em `Y = Height + support_section_offset`,
nos dois extremos. O deslocamento rígido coloca esse topo físico sobre a linha.
Com Y local para cima e linha horizontal, a treliça fica abaixo da referência.
`Span` e `NominalSpan` permanecem iguais ao comprimento da linha; alturas laterais
latentes de Duas Águas não participam do cálculo.

Duas Águas conserva o cálculo aprovado: a distância entre apoios é a referência
fornecida; o vão nominal inferior é derivado quando necessário. As alturas são
sempre perpendiculares ao eixo nominal inferior, antes da orientação rígida.

O `Placement` do owner continua representando a referência bruta; o ajuste físico
é aplicado ao frame de realização. Não há transformação extra incorporada ao
owner nem mudança de schema. `BottomChord` continua o padrão de modelos antigos.
Linhas invertidas conservam a convenção existente de direção e normal do plano:
o lado positivo da altura é Y local, sem forçar uma orientação global nova.

Só existem envelopes implementados para `Parallel` e `DuoPitch`; nenhuma forma
adicional foi habilitada.

## Prévia e painel

- Duas Águas: cotas verticais externas de altura esquerda/direita, com extensões
  curtas, linha de cota e traços de extremidade.
- Paralela: uma cota da altura nominal constante entre eixos dos banzos.
- Valores desenhados verticalmente fora do contorno; margens fixas em pixels
  (40 por lado cotado), recalculadas no resize, sem texto ampliando o sceneRect.
- Alturas pequenas mantêm os endpoints verdadeiros; somente a linha indicadora
  se prolonga para leitura. Altura zero omite a cota, sem inventar dimensão.
- Referência tracejada mais discreta, sem legendas extensas no desenho.
- Nota permanente de alturas removida; explicação nos tooltips dos campos.
- Mesmas seções Geometria, Alma, Perfis e Referência, sem reorganização.

Capturas verificadas em 320×170, 480×220 e 640×250, com alturas normais,
assimétricas, muito pequenas e nulas. O gate drena eventos de layout antes de
capturar trocas de forma, evitando registrar estados transitórios do Qt.

## Limpeza na exclusão nativa

Uma regressão adicional confirmou resíduos ao excluir somente o owner pelo
`Std_Delete`: membros e grupos permaneciam. Foi acrescentado `onDelete` ao
ViewProvider para remover o agregado na transação nativa, sem recompute interno.

São removidos somente membros com `GenerationOwner == owner`, chapas com
`ParentTruss == owner` e grupos próprios sem conteúdo estrangeiro. Grupos
compartilhados com outro owner são preservados. Fontes Draft e referências
externas não são percorridas. Não há ocultação de mensagens.

`Document.removeObject` direto continua sendo a API de remoção de um objeto,
sem executar callbacks GUI. A limpeza do agregado é validada pelo comando GUI;
a regeneração tem sua própria remoção dos membros obsoletos.

## Validação executada

```powershell
python -m unittest tests.test_truss_support_alignment tests.test_truss_duopitch_ui tests.test_truss_task_panel tests.test_truss_duopitch_heights tests.test_truss_duopitch_custom tests.test_truss_copy tests.test_truss_regeneration_rollback tests.test_truss_c2_references tests.test_truss_manual_fixes
python scripts/run_truss_duopitch_gate.py
python scripts/run_truss_duopitch_gate.py --probe copy
python scripts/run_truss_duopitch_gate.py --probe delete
python scripts/check_project.py
git diff --check
```

| Verificação | Resultado |
|---|---|
| Nove módulos unittest focados | 97 testes, OK |
| Gate alinhamento/documento/Qt, FreeCAD 1.1.4 | 218 verificações, OK |
| Gate existente Draft Move/cópia, FreeCAD 1.1.4 | 32 verificações, OK |
| Gate exclusão nativa, FreeCAD 1.1.4 | 12 verificações, OK |
| check_project.py | OK |
| git diff --check | OK |

Não foi executada a suíte completa. Os gates são automatizados em processos
isolados do FreeCAD 1.1.4, com perfis temporários, sem alterar sessões do usuário.
Não representam aprovação manual do funcionamento/design pelo usuário.

Cobertura: alturas vinculadas/independentes e zero↔positivo; padrões de Duas
Águas; alinhamentos inferior/superior; perfis simples/compostos, inserção/rotação;
referências horizontais/inclinadas/invertidas; associativa/snapshot; Property View;
regeneração e rollback; Placement da cópia; cópia de cópia; ocultação independente;
save/reopen; Undo/Redo; exclusão de original/cópia com seleção múltipla; compostos
com interconectores e Gusset preservados. A exclusão dedicada compara o conjunto
exato de objetos e reabre documento salvo depois de Undo.

O gate de alinhamento ainda registra duas mensagens `pending remove of
StructuralMember` durante uma regeneração dentro de recompute. Os cenários
terminam válidos e os membros obsoletos são removidos. Não houve
`Recursive calling of recompute` nos logs destes gates. A investigação geral
desse aviso do Draft não foi repetida.

Evidências em `test-results/truss-duopitch/`:

- `1791764994505245700/`: alinhamento/documento/Qt, `result.json`, FCStd e capturas.
- `1791764921859443300/`: regressão de cópia, `result.json` e logs.
- `1791764931005765800/`: exclusão nativa, `result.json`, FCStd após Undo e logs.

## Roteiro manual curto — FreeCAD 1.1.4

1. Criar dois pilares e uma Draft Line entre seus topos. Selecionar a linha,
   criar Paralela e escolher Topo do banzo superior. Conferir contato físico
   com a linha e treliça abaixo dela; alternar para Banzo inferior.
2. Repetir com linha inclinada e invertida, conferindo direção/normal do plano.
   Alterar perfil, inserção, rotação e composto; conferir topo físico e vão.
3. Comparar referência snapshot e associativa movendo um extremo da linha.
   Alterar Height/ReferenceAlignment pela Property View e regenerar membros.
4. Em Duas Águas, testar alturas distintas, vínculo, valores pequenos e zero;
   alternar alinhamento e redimensionar o painel. Conferir cotas e tooltips.
5. Duplicar com Draft Move, editar/ocultar/excluir original e cópia separadamente,
   conferir árvore sem resíduos; testar Undo/Redo, salvar e reabrir.

## Arquivos desta rodada

- `freecad/SteelStructures/trusses/support_alignment.py`
- `freecad/SteelStructures/trusses/support_alignment_freecad.py`
- `freecad/SteelStructures/trusses/realization.py`
- `freecad/SteelStructures/truss.py`
- `freecad/SteelStructures/interactive/truss_preview.py`
- `freecad/SteelStructures/interactive/truss_task_panel.py`
- `tests/test_truss_support_alignment.py`
- `tests/test_truss_duopitch_ui.py`
- `tests/test_truss_copy.py`
- `tests/manual_freecad_truss_duopitch.py`
- `tests/manual_freecad_truss_delete.py` (novo)
- `scripts/run_truss_duopitch_gate.py`
- Este relatório.

O working tree já continha alterações e arquivos não rastreados no início.
Eles permanecem locais; a lista acima discrimina o escopo desta rodada, não todo
o diff acumulado em relação ao HEAD.
