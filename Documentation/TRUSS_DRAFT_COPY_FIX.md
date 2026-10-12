# Treliça paramétrica — cópia por Draft Move

Investigação em `develop/0.7.0`, baseline `14449d2`, FreeCAD 1.1.4.

## Defeito reproduzido antes da correção

O comando nativo Move chama `Draft.move(..., copy=True)`, que usa
`draftmake.make_copy.make_copy`. Para `App::FeaturePython` sem
`OriginGroupExtension`, essa função chama `document.copyObject(obj)` sem
recursão. `StructuralTruss` não é um container geométrico: seus filhos são
registrados em `GeneratedMembers`, `RoleGroups` e `GeneratedGussetPlates`.
`claimChildren` organiza a árvore, sem alterar esse contrato de cópia.

O probe GUI isolado `test-results/truss_copy/1791678543699371900/` demonstrou:

- proxies da origem/cópia distintos, mas referências aos mesmos membros/grupos;
- Placement da cópia deslocado para `(0, 2400, 300)`, membros ainda na origem;
- recompute em `Conflict`, mensagem `Binding inconsistente: BC_MAIN`;
- ocultar qualquer uma altera a visibilidade dos membros compartilhados.

`AppliedState.bindings` também contém nomes de objetos em JSON. A simples cópia
recursiva dos links não atualiza esses nomes. Membros têm coordenadas globais,
regeneradas pelo Placement do owner; mover owner e filhos duplicaria a transformação.

## Correção aplicada

`StructuralTrussProxy.onDocumentRestored`, chamado também por `copyObject`,
reconhece somente a cópia integral dos registros de outra treliça viva no mesmo
documento. A restauração normal, com filhos já pertencentes ao próprio owner,
não gera objetos adicionais. Registros parciais ou de owners misturados não são
reparados automaticamente.

`restore_copied_children` valida os bindings originais e copia explicitamente
membros, chapas Gusset, grupos de função e subgrupos de interconectores, em uma
única chamada `document.copyObject(lista, False)`. Essa API remapeia os links
internos entre os objetos da lista, sem duplicar referências externas. A lógica
atualiza `GenerationOwner`, `ParentTruss`, os registros do owner e os nomes em
`AppliedState.bindings`. Todos os novos objetos pertencem à transação nativa da
cópia. Em caso de falha, são removidos somente os objetos criados nessa etapa.

As propriedades visuais são preservadas: o padrão de cor de um objeto novo
não pode invalidar o `ControlledState` aceito do membro. A visibilidade dos
grupos é restaurada antes da visibilidade individual dos filhos, pois grupos
propagam alterações aos seus conteúdos. O cache de visibilidade de uma treliça
copiada já oculta também é remapeado para os novos nomes. O ViewProvider limita
as alterações de visibilidade aos filhos pertencentes ao próprio owner.

O deslocamento continua aplicado somente ao Placement do owner; a regeneração
existente posiciona os membros. Não há mudança de schema, topologia, UX, comando
público, geometria de membros, infraestrutura Draft ou instalação FreeCAD.

## Limitação associativa preservada

Uma referência externa associativa continua governando a posição da treliça.
Copiar o owner não duplica a Linha/Retângulo de referência nem desliga o vínculo.
Portanto, uma cópia associativa continua ancorada à mesma fonte: o deslocamento
livre do owner não substitui a posição determinada pela fonte. Os filhos são
independentes, mas a referência externa permanece deliberadamente compartilhada.
Para uma cópia livremente deslocável, utilizar o modo snapshot existente.
Não foi acrescentado um offset associativo nem um comando alternativo.

## Validação

FreeCAD 1.1.4, build `4fd3bf320`, sessões GUI reais com perfil isolado:

- Gate `tests/manual_truss_copy.py`: **27 verificações aprovadas**, incluindo
  cópia deslocada em plano inclinado, owners/bindings/grupos independentes,
  visibilidade em ambas as direções e filhos individualmente ocultos, cópia de
  owner oculto, dimensões e regeneração independentes, exclusão em ambas as
  direções, save/reopen, Undo/Redo da cópia e do deslocamento, perfis compostos,
  interconectores, Gussets e referência externa preservada.
- Probe do comando nativo `Draft_Move`, com `isCopy` marcado e dois pontos
  numéricos: **4 verificações aprovadas**, incluindo commit diferido, posição
  dos filhos e encerramento do comando/painel.
- Nenhum traceback Python, wrapper Qt destruído ou falha nativa nos logs dessas
  execuções. Evidências locais em `test-results/truss_copy/1791679829042366200/`
  e `test-results/truss_copy/1791679914399727100/` (não versionar resultados).

Testes Python focados: **84 aprovados**, zero falhas/erros/skips:

```powershell
python -m unittest tests.test_truss_copy tests.test_truss_manual_fixes tests.test_truss_core tests.test_truss_assemblies tests.test_truss_interconnectors tests.test_truss_c2_references tests.test_gusset_plate_document_c6b
python scripts/check_project.py
git diff --check
```

As duas verificações de integridade passaram. A suíte completa não foi executada
nesta etapa. O teste existente de restauração usa extração AST: seu fixture
recebeu a nova função e a lista vazia de membros, mantendo as mesmas asserções.
Os 95 arquivos dos estudos Gusset permanecem idênticos ao inventário SHA-256.

## Roteiro manual curto — FreeCAD 1.1.4

1. Criar uma treliça snapshot, selecionar o owner na árvore e usar Draft Move
   com **Criar cópia**. Deslocar em X/Y/Z e conferir ambas as geometrias.
2. Ocultar/exibir cada owner, alterar a altura da cópia e regenerar cada uma.
   Repetir com um membro oculto e com o owner oculto antes da cópia.
3. Fazer Undo/Redo da cópia e do deslocamento; salvar, fechar e reabrir. Excluir
   uma treliça e confirmar que a outra continua válida. Repetir com perfil
   composto/interconectores e, quando presentes, Gussets.

## Arquivos desta correção

- `freecad/SteelStructures/truss.py`
- `tests/test_truss_copy.py`
- `tests/test_truss_manual_fixes.py`
- `tests/manual_truss_copy.py`
- `Documentation/TRUSS_DRAFT_COPY_FIX.md`

Branch e HEAD mantidos. Nenhum staging, commit ou push. A alteração preexistente
de `init_gui.py` (sem diff textual), os estudos e os experimentos locais foram
preservados. A correção está pronta para validação manual do usuário.

Validação manual posterior do usuário: três treliças copiadas em posições
distintas, com visibilidade e regeneração independentes. A investigação seguinte
detectou um aviso nativo de recompute que não fazia parte do filtro de erros do
primeiro runner. Os resultados funcionais acima não constituem aprovação desse
critério. Ver [diagnóstico do Draft Move](TRUSS_DRAFT_MOVE_DIAGNOSTICS.md).
