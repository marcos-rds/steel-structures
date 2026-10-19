# Fechamento técnico — Etapa 1: arestas retas em Snapshot

Auditoria de 18/10/2026, sobre `develop/0.7.0`, base/HEAD publicado
`29439b8d6e166b86a979a4633105890f1acb4065`. Escopo: revisão e preparação de
commit seletivo; nenhuma funcionalidade nova ou alteração em produção nesta
auditoria. Staging, commit, push, merge, tag e release não foram executados.

## Aprovação manual e autoridade documental

O usuário informou neste fechamento que concluiu e aprovou todos os testes
manuais no FreeCAD 1.1.4, inclusive pré-seleção, equivalência dos fluxos,
Placements hierárquicos, Snapshot independente, preservação Draft, interface,
cancelamentos, checkpoints, Aplicar/OK e Undo/Redo. Essa aprovação substitui
as pendências manuais históricas registradas nos documentos anteriores.
Os gates desta auditoria são automação adicional, não outra alegação de teste
manual pelo agente.

Relatórios originais preservados integralmente:

- [Estudo técnico de referências lineares](TRUSS_0_7_0_LINEAR_EDGE_REFERENCE_STUDY.md).
- [Implementação Snapshot](TRUSS_0_7_0_EDGE_SNAPSHOT.md).
- [Correção da pré-seleção](TRUSS_0_7_0_EDGE_PRESELECTION_FIX.md).

O estudo contém propostas futuras (`LinearEdge`, schema 6 e vínculo
qualificado de lados). A Etapa 1 aprovada adotou deliberadamente o contrato
existente `TwoPoints`: não implementa essas propostas nem exige migração.
O estudo também adiava Body; os testes posteriores qualificaram captura
Snapshot de `PartDesign::Body` em `App::Part`. Isso não qualifica Link,
arrays ou associatividade genérica.

## Contrato auditado

Os dois fluxos usam seleção bruta `getSelectionEx("", 0)` e convergem em
`selected_linear_reference()` → `selected_path()` / `capture_edge()` →
`_adopt_selected_reference()`. A pré-seleção mantém a raiz e o caminho; o
observador interativo usa `resolve=0`, entrega diferida e o mesmo adaptador.
A única diferença intencional é `allow_rectangle=True` na abertura, para
preservar o Retângulo Draft inteiro como envelope legado. Sua aresta
explicitamente indicada é segmento Snapshot.

A captura lê `root.getSubObject(path)` uma vez e usa os parâmetros físicos
da aresta, sem reaplicar Placement. Exige Shape/aresta válidas, reta nativa,
dois vértices, parâmetros/comprimento finitos e limitados, extremos distintos
e coerentes. Cardinalidade, documento, caminho, ciclos e ocorrências não
suportadas são verificados antes de alterar o rascunho.

Para fontes genéricas, a configuração é `reference_mode="TwoPoints"`,
`reference_linked=False`, `reference_source=""`, `reference_edge=""`, com
extremos globais, normal e referência definida. Nome, ID e `EdgeN` são
metadados informativos temporários da sessão/checkpoint; não entram no JSON
persistido, `AppliedState` ou dependências do owner. As propriedades legadas
`ReferenceSource` e `ReferenceContainers` continuam existindo, mas ficam
respectivamente `None` e `[]` para Snapshot. Nenhum `PropertyLinkSub` novo
é criado para essas fontes, nem Linha Draft auxiliar ou aplicação automática.

Linha Draft continua no reconhecedor/resolvedor legado e conserva associação
quando solicitada. Retângulo inteiro conserva envelope e escolha de base
legados. Dois/Três pontos, documentos antigos e contratos de recompute
continuam sob os mesmos módulos persistentes.

Seleção inválida conserva o rascunho. Esc/fechamento reaproveitam a limpeza
de observer, atalho e callbacks existente; entrega enfileirada verifica se a
operação já foi encerrada. O checkpoint acrescenta apenas cópias profundas
da origem informativa e preferência de vínculo, sem mudar o fluxo do Editor.

Não há diff em `truss.py`, `truss_reference.py`, schema/modelos,
serialização, núcleo geométrico, Editor funcional, massa, perfis compostos,
Gussets, StructuralPlate, ferramentas globais Draft, versão ou release.
Revisão técnica independente somente leitura não identificou bloqueador.

## Inventário exato recomendado para staging

São **15 arquivos: seis modificados e nove novos**. Esta é a lista completa;
não usar staging por diretório nem incluir outros arquivos locais.

### Produção modificada — 4

```text
freecad/SteelStructures/interactive/truss_controller.py
freecad/SteelStructures/interactive/truss_editor_checkpoint.py
freecad/SteelStructures/interactive/truss_reference_selection.py
freecad/SteelStructures/interactive/truss_task_panel.py
```

O controlador unifica captura/abertura; a seleção conserva caminho bruto e
observação contextual; o painel projeta Snapshot e política de vínculo; o
checkpoint restaura metadados temporários. São mudanças complementares.

### Gate e teste existentes modificados — 2

```text
scripts/run_truss_duopitch_gate.py
tests/test_truss_reference_selection_gui.py
```

O runner registra `edge_snapshot` no mesmo isolamento/temas/logs dos demais
gates. O teste anterior deixa de rejeitar arestas retas que agora são
suportadas; conserva rejeições de objeto genérico inteiro, face e vértice,
com os casos válidos cobertos pelos novos testes.

### Novo módulo de produção — 1

```text
freecad/SteelStructures/truss_edge_snapshot.py
```

### Novos testes permanentes e entrada nativa — 4

```text
tests/test_truss_edge_snapshot.py
tests/test_truss_edge_snapshot_gui.py
tests/test_truss_preselection.py
tests/manual_freecad_truss_edge_snapshot.py
```

Apesar do prefixo `manual_`, o último arquivo é a entrada permanente do gate
nativo isolado; não é probe exploratório. Os imports reutilizados pelos novos
arquivos já existem em `29439b8`. Não dependem de estudos, experimentos,
probes, FCStd locais ou resultados gerados.

### Documentação nova — 4

```text
Documentation/TRUSS_0_7_0_LINEAR_EDGE_REFERENCE_STUDY.md
Documentation/TRUSS_0_7_0_EDGE_SNAPSHOT.md
Documentation/TRUSS_0_7_0_EDGE_PRESELECTION_FIX.md
Documentation/TRUSS_0_7_0_EDGE_SNAPSHOT_CLOSURE.md
```

Os três primeiros documentos são históricos originais; este fechamento
consolida decisões, aprovação manual, inventário e evidências finais.

## Exclusões obrigatórias

Todos os demais arquivos locais permanecem fora do staging. Em particular:

- `Documentation/gusset_family_review/`, `gusset_phase1/`, `gusset_round1/`,
  `gusset_tip_depth/`, `gusset_tip_round2/` e seus SVGs/relatórios/configurações.
- `Documentation/STRUCTURAL_PLATE_*.md` e demais relatórios Truss de etapas
  anteriores que ainda estão locais, mas não são dependência deste incremento.
- `scripts/diagnose_plate_heap.py`, `diagnose_plate_qt_lifecycle.py`,
  `diagnose_plate_tracker_stability.py` e seus probes/testes experimentais.
- `tests/manual_plate_*.py`, `tests/manual_point_input_probe.py`,
  `tests/test_plate_qt_lifecycle_probe.py`.
- `tests/copiatreliça.FCStd`, `tests/copiatreliça2.FCStd`.
- `test-results/`, logs, caches, perfis FreeCAD descartáveis e artefatos
  gerados, inclusive o orquestrador desta auditoria e as árvores isoladas.

## Testes finais

Comandos completos de descoberta e integridade:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python scripts/check_project.py
git diff --check
```

Suíte workspace: **1.905 testes, 1.756 aprovados e 149 skips**, zero falhas ou
erros. Suíte candidata: **1.901 testes, 1.752 aprovados e os mesmos 149 skips**,
zero falhas ou erros. Os quatro testes extras do workspace são de
`test_plate_qt_lifecycle_probe.py`, experimento excluído do commit; não há
dependência esquecida na árvore candidata.

A base publicada também foi testada em árvore separada: **1.857 testes,
1.739 aprovados e 118 skips**, zero falhas/erros. O delta da candidata é de
13 testes Python executáveis e 31 casos da classe nativa Snapshot. Essa classe
inclui regressões herdadas de seleção e não representa 31 novos cenários
independentes. A repetição em temas também não multiplica casos distintos.

Os skips são indisponibilidade de FreeCAD/FreeCADGui/Draft, FreeCAD Units ou
PySide6 no Python 3.11 do sistema. Não foram contados como aprovação. Os gates
usam FreeCAD 1.1.4 real, revisão `4fd3bf320d9566a27e60069fc8387448aaa3a094`.
Os motivos registrados agrupam 77 casos GUI/event loop FreeCAD, 34 PySide6,
23 Units/PySide6 e 15 FreeCAD/Draft nativo; o detalhamento por teste está nos
JSONs e logs de descoberta. Não se afirma que todos os 149 skips tenham sido
executados por uma suíte Qt equivalente.

Todos os 15 gates nativos do workspace passaram. Cada linha abaixo foi
executada com `python scripts/run_truss_duopitch_gate.py` seguido pelos
argumentos indicados. Nas linhas OpenDark, `$snapshotQss` representa a
variável PowerShell definida assim:

```powershell
$snapshotQss = "C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss"
```

| Argumentos | Resultado | Diretório em `test-results/truss-duopitch/` |
| --- | --- | --- |
| `--probe edge_snapshot --editor-theme Classic` | 31 testes aprovados | `1792370418910758500_t9dsool6` |
| `--probe edge_snapshot --editor-theme "FreeCAD Dark"` | 31 testes aprovados | `1792370460951994600_ldqp62zi` |
| `--probe edge_snapshot --editor-qss $snapshotQss` | 31 testes aprovados | `1792370510694584700_hv1a4k26` |
| `--probe reference_selection --editor-theme Classic` | 12 testes aprovados | `1792370560537491100__8yxfs4k` |
| `--probe draft_reference --editor-qss $snapshotQss` | 103 verificações aprovadas | `1792370573524987300_itrl2jar` |
| `--probe copy` | 32 verificações aprovadas | `1792370589724080500_9ibt5_ao` |
| `--probe session` | 23 verificações aprovadas | `1792370599918329300_jmt855px` |
| `--probe apply` | 54 verificações aprovadas | `1792370607433226500_9d6y765w` |
| `--probe lifecycle` | 95 verificações aprovadas | `1792370624785846900_wk4z_n7p` |
| `--probe undo` | 93 verificações aprovadas | `1792370634236441500_r5r8kl0m` |
| `--probe editor_actions --editor-qss $snapshotQss` | 124 verificações aprovadas | `1792370647363693700_cx8rwh9y` |
| `--probe alignment` | 251 verificações aprovadas | `1792370670544756400_dl322mfi` |
| `--probe mass` | 79 verificações aprovadas | `1792370712781550800_6rztrbjm` |
| `--probe reference_layout --editor-theme Classic` | 4 testes aprovados | `1792370723856786300_28yhbkro` |
| `--probe reference_layout --editor-qss $snapshotQss --qt-scale-factor 1.5` | 4 testes aprovados | `1792370731040923800_awo_jk4i` |

Na árvore candidata isolada, os seis gates centrais também passaram. Os
comandos usam o mesmo runner, com diretório corrente na candidata. Evidências
em `candidate/test-results/truss-duopitch/` dentro da pasta desta auditoria:

| Argumentos | Resultado | Diretório |
| --- | --- | --- |
| `--probe edge_snapshot --editor-qss $snapshotQss` | 31 testes aprovados | `1792370755279281200_car4or1b` |
| `--probe draft_reference --editor-theme Classic` | 103 verificações aprovadas | `1792370799385238800_q9glesay` |
| `--probe copy` | 32 verificações aprovadas | `1792370813559736800_ri6k8us4` |
| `--probe lifecycle` | 95 verificações aprovadas | `1792370823643682700__xsph8s5` |
| `--probe undo` | 93 verificações aprovadas | `1792370833184619100_gkzqlxix` |
| `--probe editor_actions --editor-theme Classic` | 124 verificações aprovadas | `1792370846172789000_tsvx3q6d` |

Resultado: **21 processos/gates nativos aprovados**, todos com saída zero.
Não foram observados traceback, objetos C++ já destruídos, access violation,
falha nativa ou exceção Qt nos filtros de todos os logs desses gates. Os
testes de limpeza passaram, sem observers/callbacks residuais identificados.
Avisos nativos Draft `QString::arg` continuam presentes e são classificados
como limitação conhecida de mensagens do Draft, sem mudar o resultado dos
gates. Nenhuma falha introduzida pelo incremento foi identificada, nem houve
necessidade de alteração de produção/testes durante este fechamento.

`check_project.py` passou no workspace e na candidata; `git diff --check`
passou, com apenas os avisos já existentes de conversão LF/CRLF em três
arquivos locais. Não foram feitas correções cosméticas nesses arquivos.

Como `git diff --check` não inclui arquivos ainda não rastreados, foi feita
checagem adicional dos nove arquivos novos por
`git diff --no-index --check -- NUL <arquivo>`. Oito não têm diagnóstico de
whitespace. Em `tests/test_truss_edge_snapshot_gui.py:617`, Git informou
`new blank line at EOF` (código 3: arquivo novo mais diagnóstico de whitespace).
É uma linha em branco final preexistente, sem efeito funcional ou falha de
teste; foi preservada nesta auditoria. Não é bloqueador técnico do commit,
mas permanece como apontamento editorial explícito. O relatório está em
`new_file_whitespace.json`; não se declara whitespace impecável dos arquivos
novos. O código 1 das demais comparações significa arquivo novo diferente de
NUL, sem diagnóstico de whitespace.

## Isolamento e preservação

Evidências locais desta auditoria:
`test-results/truss-edge-closure/20261018_213917/`.

As árvores `baseline/` e `candidate/` foram extraídas por `git archive` da
base publicada, sem checkout, worktree Git, alteração de índice ou operações
destrutivas. A candidata recebeu somente os 15 arquivos recomendados. O
relatório consolidado é copiado novamente ao finalizar; nenhum arquivo de
produção/teste foi alterado após a extração.

A comparação binária com o archive confirmou exatamente os seis arquivos
modificados esperados e nove adições da lista. Todos os demais 410 arquivos
rastreados são idênticos à base. Os 15 candidatos são conferidos por SHA-256
contra os arquivos do workspace. A suíte completa e os gates selecionados
da árvore candidata executam a partir dela, sem precisar de arquivos locais
excluídos.

O inventário completo, incluindo todos os caminhos fora de escopo, está em
`inventory.json`; `staging-candidates.txt` contém somente os 15 caminhos
recomendados. `before.json`, `preservation.json` e `isolation.json` registram
estado Git, hashes e comparação entre árvores. Os JSONs das suítes e gates
registram comandos, códigos de saída, skips, resultados e diretórios. A
auditoria de logs também cobre probes cujo runner não faz filtro próprio.

No início havia seis arquivos modificados e 142 não rastreados. Ao final,
o novo fechamento eleva os não rastreados a 143: nove são candidatos ao
commit e **134 continuam excluídos** (121 em Documentation, três scripts,
dez arquivos de testes/documentos). Os 558 arquivos preexistentes foram
preservados por SHA-256, incluindo os três relatórios originais e todos os
estudos/experimentos/FCStd não ignorados. Resultados antigos não foram
removidos; os novos resultados usam diretórios próprios.

Estado Git esperado e verificado: branch `develop/0.7.0`, HEAD
`29439b8d6e166b86a979a4633105890f1acb4065`, índice vazio; sem add, commit,
push, merge, tag ou release. A única adição não ignorada desta auditoria é
este relatório.

## Limitações e classificação de riscos

- Arestas genéricas são exclusivamente Snapshot; nenhuma identidade
  topológica ou associatividade futura é prometida. Link/arrays/ocorrências
  externas continuam recusados. Associatividade semântica de lados de
  Retângulo pertence a outra etapa.
- O rótulo de origem é temporário. Após salvar/reabrir/copiar para outra
  sessão, a referência aparece como **Dois pontos**, conservando a geometria.
  Isso é o contrato persistente aprovado, não perda de associação prometida.
- Reconstrução de coordenadas a partir de Placement persistido pode conter
  resíduo numérico de rotação. O teste de round-trip usa `1e-7`; a comparação
  direta pré-seleção/interativa permanece exata.
- O perfil isolado FreeCAD Dark mantém a ressalva histórica de contraste de
  widgets genéricos. Não houve contorno QSS/paleta em produção. A aprovação
  manual atual do usuário na instalação habitual é registrada separadamente
  desse comportamento do perfil descartável.
- Avisos `QString::arg` de Draft devem ser separados de traceback Qt,
  objetos C++ destruídos, falhas nativas, regressões ou callbacks residuais.
- A execução nativa desta auditoria qualifica FreeCAD 1.1.4; não certifica
  automaticamente outras versões ou todos os produtores de Shape.

## Veredito e mensagem de commit

**GO técnico para commit seletivo local dos 15 arquivos listados.** A
aprovação manual informada está concluída, as três suítes completas passaram,
os 21 gates nativos passaram e a árvore isolada confirmou suficiência dos
arquivos selecionados. Não há bloqueador efetivo identificado. A execução do
commit depende de instrução própria; esta auditoria não altera o índice.
O GO conserva o apontamento editorial não bloqueante de linha em branco no
EOF de um teste novo, descrito acima; não houve correção ou enfraquecimento
de testes para obter aprovação.

**NO-GO para publicar a release 0.7.0 nesta etapa.** O incremento está
qualificado para compor uma release futura, mas este fechamento não avalia
todo o escopo da 0.7.0 nem realiza a preparação de release, documentação de
release, empacotamento, tag ou publicação. Essa separação não representa
falha do incremento; versão e metadados permanecem intactos.

Mensagem sugerida, sem executá-la:

```text
Add Snapshot capture of straight-edge truss references

Share raw hierarchical selection and Snapshot adoption between opening
preselection and interactive capture. Preserve associative Draft lines,
rectangle envelopes and existing TwoPoints persistence.

Cover global coordinates, invalid selections, checkpoints, lifecycle,
copy/persistence and Undo/Redo with Python and native FreeCAD gates.
```
