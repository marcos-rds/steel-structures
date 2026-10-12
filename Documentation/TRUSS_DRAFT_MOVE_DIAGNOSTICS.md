# Treliças — recompute e prévia do Draft Move

Branch `develop/0.7.0`, HEAD `14449d2`. Investigação posterior à validação manual
da duplicação independente pelo usuário. FreeCAD 1.1.4, build `4fd3bf320`.
Nenhuma alteração de produção nesta rodada.

## Recompute: causa demonstrada

Mensagem reproduzida:

```text
<App> Document.cpp(2648): Recursive calling of recompute for document NativeMoveDiagnostics
```

A mensagem também ocorre com uma Wire Draft nativa de 2.500 pontos, em sessão
isolada, **sem importar Steel Structures**. A repetição de controle sem profiler
também apresentou o aviso. Não é um efeito exclusivo do proxy da treliça ou da
instrumentação.

Sequência comprovada pelo trace e pelo código Draft instalado:

1. `Move.move()` agenda `Draft.move(...)` e o recompute final.
2. `DraftTool.finish()` (`draftguitools/gui_base_original.py:189–192`) separa o
   recompute: `ToDo.delayCommit(...)` e `ToDo.delayAfter(Gui.doCommand, ...)`.
3. Ambas as funções agendam um timer de intervalo zero para `ToDo.doTasks`.
4. A fila `commitlist` é esvaziada antes da execução. A `afteritinerary` só é
   esvaziada **depois** de executar suas entradas (`draftutils/todo.py:186–204`).
5. Durante o recompute, o processamento de eventos permite reentrar em
   `doTasks`; a mesma entrada `FreeCAD.ActiveDocument.recompute()` ainda está
   em `afteritinerary`, sendo executada novamente antes da primeira terminar.

Stack da segunda chamada, também obtida no controle puro:

```text
draftutils/todo.py:188 doTasks -> Gui.doCommand(recompute)
  <string>:1 recompute
    draftutils/todo.py:188 doTasks -> Gui.doCommand(recompute)
      <string>:1 recompute
```

Não foi identificado um `recompute()` chamado por `StructuralTruss.execute`,
`onChanged`, visibilidade, `onDocumentRestored` ou reconstrução do agregado.
`apply_truss` mantém seu recompute final para aplicar/validar a transação; suas
operações isoladas não apresentaram o aviso. Não foi determinado qual ponto
interno C++ bombeia os eventos; não é necessário supor um callback da bancada
para explicar a reentrância observada na fila do Draft.

Não foi aplicada correção especulativa no proxy. Seu guard `_updating` não pode
evitar uma chamada reentrante a Document.recompute feita pela fila externa.
Alterar a fila compartilhada, instalar monkeypatch ou remover recomputes
necessários violaria o escopo e não corrigiria a causa no Draft puro.

## Prévia: diagnóstico e alternativa

`Move.set_ghosts` usa `_modifiers_process_selection` e `ghostTracker` nativos.
`ghostTracker.getNodeFull` copia `obj.ViewObject.RootNode`. O owner da treliça
é um `App::FeaturePython` com display mode vazio; os sólidos ficam nos membros
gerados. `claimChildren` organiza a árvore, mas não integra o RootNode do owner.

O gate confirmou bounding box vazio no ghost da treliça em Move, Copy e
cancelamento. O mesmo teste sobre a Wire nativa retornou bounding box não vazio.
Logo, o problema não é a posição candidata: o ghost recebe uma representação
sem geometria.

`getMovableChildren` é consultado somente com `copy=False`; não atende à opção
Criar cópia. Não há hook do proxy para fornecer a lista de preview em Copy nesse
caminho instalado. Alterar Group/getSubObject afetaria também seleção e cópia;
adicionar representação ao RootNode mudaria a apresentação permanente.

**Prévia não implementada nesta rodada.** A menor alternativa local para discutir
é um adaptador restrito à instância do comando Draft Move que forneça ao ghost
os filhos gerados, sem alterar a seleção/cópia real. Usaria a transformação e o
teardown nativos do ghost, sem objetos paramétricos ou recomputes por movimento.
Ainda exigiria integração explícita com a instância do comando e testes de
callbacks/ownership; não é um hook simples disponível atualmente. Uma alternativa
mais sustentável seria um hook de preview disponibilizado pelo próprio Draft.
Nenhuma dessas alternativas foi instalada ou simulada como solução definitiva.

## Resultados

| Caminho | Verificações funcionais | Avisos de recompute |
| --- | --- | --- |
| API Draft.move + regressão da treliça | 32 aprovadas | 0 |
| Comando GUI: treliça, Move e três Copies | 34 aprovadas no conjunto | 4: um em Move e um por Copy |
| Controle GUI Draft Wire, sem bancada e sem profiler | 23 aprovadas | 3: um por Copy |

Criação, propriedades da original/cópia e regeneração separada: sem avisos.
Cancelamento, Undo/Redo e save/reopen: sem avisos nas etapas correspondentes.
O gate GUI validou posições, identidade, término do comando e remoção do ghost.
O gate API cobre também visibilidade, exclusão, plano inclinado, perfis compostos,
interconectores, Gussets, referências externas e três cópias sucessivas de cópias.

**O gate de ausência de avisos GUI permanece reprovado.** O runner agora detecta
explicitamente `Recursive calling of recompute` e retorna falha, embora o
processo FreeCAD termine com código zero e as verificações funcionais passem.
Não houve traceback Python, objeto Qt destruído, Access Violation ou corrupção
nativa nessas execuções. Não declarar o aviso resolvido.

Evidências locais (resultados e FCStd gerados não devem integrar o commit):

- `test-results/truss_copy/1791681278183529000/`: etapas e stacks iniciais.
- `test-results/truss_copy/1791682137217429400/`: controle puro com trace.
- `test-results/truss_copy/1791682257602656200/`: 32 verificações API.
- `test-results/truss_copy/1791682372352386200/`: 34 verificações GUI da treliça.
- `test-results/truss_copy/1791682410263957100/`: controle puro, profiler desligado.

Testes Python focados: **84 aprovados**, zero falhas/erros/skips:

```powershell
python -m unittest tests.test_truss_copy tests.test_truss_manual_fixes tests.test_truss_core tests.test_truss_assemblies tests.test_truss_interconnectors tests.test_truss_c2_references tests.test_gusset_plate_document_c6b
python scripts/check_project.py
git diff --check
```

A suíte completa não foi executada. O probe reproduzível é
`tests/manual_truss_move_diagnostics.py`: lançar em GUI isolada com
`TRUSS_COPY_ROOT` apontando ao repositório e `TRUSS_COPY_RUN` ao diretório de
resultados. `TRUSS_MOVE_CONTROL=1` ativa o controle sem a bancada;
`TRUSS_MOVE_TRACE=0` desliga a instrumentação. Sempre verificar o FreeCAD.log.

`check_project.py` e `git diff --check` aprovados. Os 95 arquivos dos estudos
Gusset permanecem idênticos ao inventário SHA-256. O SHA-256 de `truss.py`
permanece igual ao início desta rodada; a implementação validada foi preservada.

## Roteiro manual e estado

1. Abrir o Report View e criar uma treliça snapshot. Executar Move sem cópia,
   depois três cópias. Conferir posições, ocultação e regeneração independentes.
2. Iniciar outro Move e cancelar após P1. Conferir término e ausência de ghost.
3. Fazer Undo/Redo e salvar/reabrir. Registrar o aviso por operação; sua ausência
   em uma execução curta não elimina a reentrância demonstrada.
4. Para comparar sem a bancada, abrir uma sessão Draft pura, criar uma Wire de
   muitos vértices e usar Move Copy. Não importar Steel Structures nessa sessão.

O trabalho anterior permanece preservado. Não houve mudança da implementação
de duplicação, geometria, propriedades, referências, gerador ou instalações.
Não houve staging, commit ou push. A prévia continua pendente e a ausência de
avisos no comando GUI não foi aprovada.
