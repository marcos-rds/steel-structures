# Referências Draft no Gerador de Treliças — contrato e fechamento técnico

Base: `develop/0.7.0`, commit publicado `be75a7a`.
Este documento consolida desenho direto, seleção interativa e layout de
Referência. O usuário aprovou manualmente esses fluxos no FreeCAD 1.1.4,
inclusive OpenDark. A auditoria de fechamento não alterou código funcional.

## Arquitetura e comportamento consolidado

### Desenhar uma linha

No modo **Linha Draft**, **Desenhar nova** inicia uma instância local de
`draftguitools.gui_lines.Line`. Não registra um comando paralelo nem modifica
globalmente Draft, Snapper ou Plano de Trabalho.

`ReferenceLineOperation` conserva uma cópia profunda da configuração candidata
e o estado da prévia 3D, mantendo o mesmo controlador, owner e
`TrussEditSession`. Ela interrompe a prévia e os callbacks de aquisição,
suspende a projeção Qt e fecha a Task View. Os widgets destruídos não são
reutilizados. Ao terminar o comando nativo, `_show_truss_panel()` constrói
widgets novos sobre a mesma sessão, sem reinicializar seu baseline ou aplicar
a treliça.

A fila nativa Draft cria a linha na transação própria do Draft e entrega o
objeto exato pela variável `line`, usando um token exclusivo da operação.
Não há busca por diferença de objetos, seleção global ou Label para adivinhar
o resultado. As instruções enfileiradas são protegidas pelo token e pelo
documento; não criam objetos em um documento sucessor ou já fechado.
A reconstrução acontece depois da remoção da UI, criação e recompute nativos,
pois o envio numérico do Draft ainda acessa widgets após `finish()`.

Concluir associa a nova Linha Draft, sincroniza P0/P1, vão e prévias e retorna
em **Linha Draft**, com **Manter vínculo com a fonte** marcado. Os demais
parâmetros do rascunho permanecem. Não há aplicação automática nem novo owner.

Esc antes ou depois do primeiro ponto retorna com o modo, referência e
rascunho anteriores, sem objeto parcial. Uma linha já concluída é independente:
Cancelar a treliça posteriormente não a exclui. Seu Undo/Redo continua sendo
o nativo do Draft, separado das aplicações da treliça.

Troca/fechamento de documento, comando sucessor ou encerramento externo da
Task View abortam a operação sem ressuscitar um painel encerrado. O registro
temporário e o observer de documento são removidos no encerramento.

### Selecionar uma fonte existente

**Selecionar existente** aceita uma pré-seleção válida ou inicia aquisição no
viewport. `TrussReferenceSelection` observa temporariamente `Gui.Selection`;
cada evento usa a entrada de `SelectionEx` correspondente ao objeto e ao
subelemento clicados, sem incorporar seleções anteriores acumuladas.

A orientação aparece no indicador da fonte. Um `QShortcut` de Esc com escopo
da janela cancela somente a aquisição, inclusive com foco na vista Coin.
Nenhum filtro global ou timer recorrente é instalado. A entrega é diferida
com `QTimer.singleShot(0, ...)`, para não atualizar widgets/previews dentro do
despacho nativo da seleção.

Documento ativo, contexto da sessão, conflitos persistentes, ciclos,
geometria da fonte e compatibilidade Custom são verificados antes de mutar o
rascunho. A validação preliminar lê somente a normal necessária do widget;
não chama `get_config()`, que sincronizaria a sessão antes da validação.
Clique inválido conserva a referência anterior e mantém a captura ativa.

Concluir ou cancelar remove os observers de seleção e documento, desabilita e
desconecta o atalho e agenda sua exclusão. A limpeza é idempotente e tolera
destruição prévia do Qt. Entregas diferidas após o encerramento ficam inertes.
Mudança de modo, Editor, desenho, Aplicar/OK/Cancelar, fechamento da Task View,
troca/fechamento de documento e handoff também encerram a captura.

### Vínculo, modos existentes e documentos anteriores

Ao selecionar uma fonte existente, **Manter vínculo com a fonte** conserva a
escolha atual do usuário. Marcada, utiliza o resolver associativo existente;
desmarcada, conserva Snapshot. Desenhar uma nova linha começa vinculado.
O indicador usa Label, com fallback para Name, e não mantém nomes de fontes
excluídas ou de outro documento. Renomeação, recompute e Undo/Redo atualizam
esse indicador sem escrever geometria.

**Dois pontos** e **Três pontos** mantêm suas aquisições existentes.
**Retângulo Draft** preserva sua semântica própria: uma base determina também
altura, normal e envelope. A aquisição gráfica desse modo exige uma aresta
explícita, mostra `Label · EdgeN` e não escolhe um lado pelo usuário. A
inicialização legada e o alinhamento físico externo não foram alterados.

As propriedades persistentes, enum, JSON, `AppliedState`, schema e resolvers
paramétricos permanecem os do commit base. Não há migração de documentos,
alteração em perfis, Custom, interconectores, Gussets, geometria ou massa.

Aplicar/OK/Cancelar do TaskPanel e os checkpoints do Editor continuam usando
as operações transacionais existentes. Aplicações anteriores são preservadas;
não há Undo global para cancelar captura. Se uma edição externa ou Undo/Redo
alterar a definição persistida de um owner, o bloqueio existente exige
cancelar e reabrir a sessão. A integração não sobrescreve esse conflito.

### Layout e ícones

A ordem em Linha Draft é: modo, duas ações proporcionais, indicador e opção
de vínculo. Dois pontos mostra apenas a ação de selecionar pontos. O seletor
inferior é **Banzo de referência**, com propriedades e valores inalterados.

O reposicionamento da seção usa `removeWidget()` e reinserção do mesmo widget,
liberando o item anterior do layout. O antigo `takeAt(...).widget()` deixava
um item/cache de altura por largura que provocava compressão. Não foram
introduzidas alturas absolutas ou redução de fontes. O scroll nativo continua
disponível; Editor e prévia se deslocam normalmente.

`TrussReferenceActions` divide a largura entre os botões e quebra seus nomes
em duas linhas quando necessário, usando métricas do estilo Qt. A altura é
nativa. Um QSS local restringe somente padding horizontal a 4 pixels lógicos;
cores, estados e fontes vêm do tema. Não há QSS global.

Ícones existentes são obtidos por `Gui.getIcon("Draft_Line")` e
`Gui.getIcon("view-select")`. Nenhum SVG novo, comando global, alteração em
`init_gui.py` ou dependência externa é necessário.

## Limites e riscos conhecidos

- **Arestas genéricas de sólidos/perfis não são suportadas.** Curvas, faces,
  vértices e fontes nulas/degeneradas são rejeitadas. O modo não foi renomeado
  para prometer suporte a arestas.
- Existe `ReferenceSource` como `App::PropertyLinkSub`, mas a leitura atual
  recupera somente o objeto; `reference_edge` vem do JSON. Uma evolução para
  arestas genéricas precisa definir a autoridade do subelemento vinculado,
  compatibilidade com estado persistido e política para mudança de identidade
  topológica. `EdgeN` textual não garante a mesma aresta após alterar um sólido.
  Não se deve escolher outra aresta silenciosamente ou criar linha auxiliar
  desconectada. Esse incremento permanece futuro.
- `UsePartPrimitives=True` é recusado antes da suspensão: produziria
  `Part::Line`, fora do contrato atual de Linha Draft. A preferência global não
  é alterada pela ferramenta.
- A adaptação local depende do itinerário nativo do FreeCAD 1.1.4, incluindo
  variável macro `line` e fila `draftutils.todo`. É necessário repetir os gates
  dedicados ao atualizar FreeCAD; esta auditoria não certifica outras versões.
- O erro histórico nativo `QLineEdit already deleted`, reproduzido antes no
  baseline, é risco independente. Não foi introduzido contorno global ou
  correção especulativa neste incremento.
- Gates de referência copiam preferências GUI pessoais para um perfil
  descartável, desativam overlay apenas nesse perfil e inicializam a Steel
  Structures explicitamente. O perfil pessoal é somente lido. O caminho do
  FreeCAD e o caminho OpenDark são específicos do ambiente local do runner.

## Seleção exata para commit independente

### Cinco arquivos versionados modificados

```text
freecad/SteelStructures/interactive/truss_controller.py
freecad/SteelStructures/interactive/truss_task_panel.py
freecad/SteelStructures/interactive/truss_task_widgets.py
scripts/run_truss_duopitch_gate.py
tests/test_truss_task_panel.py
```

O teste versionado recebe apenas `_suspended=False` na fixture; nenhum teste
anterior é removido ou enfraquecido. O runner acrescenta os três probes de
referência, temas/DPI e inspeção dos logs para exceções Qt/nativas.

### Dois módulos funcionais novos

```text
freecad/SteelStructures/interactive/truss_draft_reference.py
freecad/SteelStructures/interactive/truss_reference_selection.py
```

### Oito arquivos novos de testes permanentes e wrappers

```text
tests/test_truss_draft_reference.py
tests/test_truss_reference_controls.py
tests/test_truss_reference_layout.py
tests/test_truss_reference_selection.py
tests/test_truss_reference_selection_gui.py
tests/manual_freecad_truss_draft_reference.py
tests/manual_freecad_truss_reference_layout.py
tests/manual_freecad_truss_reference_selection.py
```

### Um documento técnico novo

```text
Documentation/TRUSS_0_7_0_DRAFT_REFERENCES.md
```

Total: **16 arquivos**. Todos os demais imports funcionais e testes de apoio
já pertencem a `be75a7a`. A árvore seletiva é construída com `git archive` do
commit base e apenas esses overlays, sem staging ou modificação de `.git`.

### Exclusões preservadas

Não incluir estudos em `Documentation/gusset_*`, experimentos e relatórios
StructuralPlate, `tests/copiatreliça*.FCStd`, scripts `diagnose_plate_*`,
probes manuais de Plate, `manual_point_input_probe.py`,
`test_plate_qt_lifecycle_probe.py`, logs, caches ou resultados gerados.

Este documento substitui, para o commit proposto, os relatos intermediários
`TRUSS_0_7_0_DIRECT_DRAFT_REFERENCE.md`,
`TRUSS_0_7_0_REFERENCE_LAYOUT_FIX.md` e
`TRUSS_0_7_0_INTERACTIVE_REFERENCE_SELECTION.md`. Esses arquivos, assim como
os demais relatórios de etapas anteriores, permanecem locais e intactos.
`init_gui.py` está sem diferença e não integra a seleção.

## Validação desta auditoria

Resultados e inventário com hashes são registrados em
`test-results/draft-reference-closure/20261017_175625/`. Esse diretório é
evidência gerada, deliberadamente excluída do commit proposto.

### Python completo

Comando executado nos dois locais, com saída verbosa preservada:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

| Árvore | Total | Aprovados | Skips | Falhas/erros |
|---|---:|---:|---:|---:|
| Working tree completo | 1861 | 1743 | 118 | 0 |
| Base + seleção proposta | 1857 | 1739 | 118 | 0 |

A diferença é exatamente os quatro testes de segurança do probe experimental
`test_plate_qt_lifecycle_probe.py`, excluído do commit de referências.
Nenhum teste permanente da integração ficou faltando na árvore seletiva.
Os skips refletem ausência de FreeCAD/Qt no Python externo; não são declarados
aprovações. Os 16 testes Qt novos de seleção/layout foram executados também
nativamente, nos três temas, conforme abaixo. Os demais skips não são
considerados integralmente cobertos por esta campanha específica.

### Gates FreeCAD 1.1.4 na árvore seletiva

| Probe | Tema/escala | Aprovações | Pasta do resultado em `selective-tree/test-results/truss-duopitch/` |
|---|---|---:|---|
| `draft_reference` | Classic | 103 verificações | `1792270647084539600_vh4g0nmb` |
| `reference_selection` | Classic | 12 testes | `1792270712976800400_318q94st` |
| `reference_selection` | FreeCAD Dark | 12 testes | `1792270725545890700_y7o3i1mk` |
| `reference_selection` | OpenDark | 12 testes | `1792270743293330100_2nt9gn69` |
| `reference_layout` | Classic, 100% | 4 testes | `1792270757952430000_sqeyqdrj` |
| `reference_layout` | FreeCAD Dark, 100% | 4 testes | `1792270765084528300_8z8e3u2g` |
| `reference_layout` | OpenDark, 150% | 4 testes | `1792270773613949900_3gie5m7m` |
| `apply` | Perfil isolado | 54 verificações | `1792270782418231800_fjh4qu95` |
| `lifecycle` | Perfil isolado | 95 verificações | `1792270800497814400_22wrzslo` |
| `undo` | Perfil isolado | 93 verificações | `1792270810175302800_e_quvlbz` |
| `editor_actions` | Perfil isolado | 124 verificações | `1792270823631332700_zdfvqfu6` |

Total: 11 processos com exit 0, 48 execuções de testes Qt e 469 verificações
dos demais probes. Nenhum erro/assinatura fatal nos logs inspecionados, nem
`QLineEdit already deleted`. Não houve falha de gate nesta auditoria.
Mensagens esperadas ao construir fixture degenerada e avisos nativos de
tradução `QString::arg` não foram classificados como regressões da integração.

Os gates validam desenho/conclusão/Esc, sessão e controlador preservados,
fonte exata, seleção real no viewport e pré-seleção, substituição, associação
e Snapshot, ciclos e fontes inválidas, alterações externas, Retângulo Draft,
compostos/Gussets/Custom, mesmo owner, massas, Apply/OK/Cancelar/checkpoints,
Undo/Redo, save/reopen, fechamento/troca de documento, Plano de Trabalho,
encerramento externo e limpeza de preview/callbacks. Layout verifica larguras
380/300/260, altura reduzida, alternância, Label longo, clipping, sobreposição,
scroll e retorno após desenho/Esc.

Comandos de reprodução, dentro da árvore que se deseja validar:

```powershell
python scripts/run_truss_duopitch_gate.py --probe draft_reference --editor-theme Classic
python scripts/run_truss_duopitch_gate.py --probe reference_selection --editor-theme Classic
python scripts/run_truss_duopitch_gate.py --probe reference_selection --editor-theme "FreeCAD Dark"
python scripts/run_truss_duopitch_gate.py --probe reference_selection --editor-qss "C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss"
python scripts/run_truss_duopitch_gate.py --probe reference_layout --editor-theme Classic
python scripts/run_truss_duopitch_gate.py --probe reference_layout --editor-theme "FreeCAD Dark"
python scripts/run_truss_duopitch_gate.py --probe reference_layout --editor-qss "C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss" --qt-scale-factor 1.5
python scripts/run_truss_duopitch_gate.py --probe apply
python scripts/run_truss_duopitch_gate.py --probe lifecycle
python scripts/run_truss_duopitch_gate.py --probe undo
python scripts/run_truss_duopitch_gate.py --probe editor_actions
python scripts/check_project.py
git diff --check
```

`check_project.py` aprovado no working tree e na árvore seletiva.
`git diff --check` aprovado no repositório; os arquivos novos também foram
checados por `git diff --no-index --check` contra `NUL`, sem erros de whitespace
(exit 1 nessa comparação significa arquivo novo/diff presente). Um controle
positivo com espaço final produziu exit 3 e o diagnóstico esperado. O aviso de conversão
LF/CRLF não representa erro de whitespace nem diferença exclusivamente de
EOL na seleção; os cinco diffs versionados contêm mudanças efetivas.

A árvore seletiva contém exatamente os 416 arquivos esperados do archive base
mais os overlays propostos, sem arquivo funcional adicional ou ausente.
Os 55 hashes dos cinco arquivos de produção, registrados pelos 11 processos
nativos, conferem com a seleção final. A documentação final também foi copiada
para essa árvore; nenhuma dependência dos arquivos excluídos foi encontrada.
Um probe nativo adicional confirmou os caminhos de importação de 97 módulos
`freecad.SteelStructures`: todos vieram da árvore seletiva, sem módulo da cópia
de trabalho original ou de outra instalação. Resultado em `origin-result.json`.

### Decisão e preservação

**GO para commit local seletivo dos 16 arquivos.** A aprovação manual foi
informada pelo usuário e os testes finais passaram. Não foi encontrado
bloqueador técnico nem dependência funcional esquecida. A revisão adicional
foi somente de leitura; o fechamento criou apenas esta documentação no
conjunto de fontes versionáveis. Nenhum código funcional ou arquivo excluído
foi alterado durante a auditoria.

**NO-GO para declarar uma release global a partir deste fechamento.** A
campanha certifica a integração no FreeCAD 1.1.4 e não substitui qualificação
global de GUI das outras ferramentas, todos os testes que exigem Qt/FreeCAD,
outros alvos de versão/plataforma ou tratamento separado dos riscos nativos
históricos. Esse limite não impede o commit local deste incremento.
Não foram executados merge, tag ou release, nem alterados versão/metadados.

Mensagem sugerida:

```text
feat(truss): integrate native Draft reference drawing and interactive selection
```

Antes e depois: branch `develop/0.7.0`, HEAD completo
`be75a7a35093aa370df9da18b5d914893c6267bf`, índice vazio. Os cinco arquivos
versionados já modificados na entrada permanecem byte a byte iguais ao início
da auditoria. Todos os arquivos preexistentes, inclusive experimentos e estudos
Gusset, são conferidos por hash. Somente este documento novo foi acrescentado
fora dos resultados ignorados. Nenhum add, commit, push, merge, tag ou release.

Evidências geradas: `before.json`, `git-before.txt`,
`python-full.*`, `isolated-python-full.*`, `native-campaign.json`,
`recommended-files.txt/json`, `selection-manifest.json`, `excluded-files.txt`,
`preservation.json`, `git-after.txt` e a árvore seletiva. Os manifests nativos
registram hashes do código executado para comparar com os arquivos propostos.

## Roteiro de regressão manual

O usuário já aprovou os fluxos no FreeCAD 1.1.4. Para repetir após um futuro
commit seletivo:

1. Em OpenDark, abrir Criar Treliça, definir parâmetros e selecionar Linha
   Draft. Usar Desenhar nova com snapping, entrada numérica e Plano de Trabalho.
   Conferir retorno à mesma sessão, sem aplicação automática.
2. Repetir Esc antes/depois do primeiro ponto; conferir referência e rascunho.
   Clicar Selecionar existente antes da geometria e testar também pré-seleção.
   Substituir a fonte e alternar seleção/desenho.
3. Conferir Snapshot/vínculo, Label/renomeação, P0/P1, vão e prévias. Em
   Retângulo Draft, escolher explicitamente a base e conferir seu envelope.
4. Aplicar repetidamente, abrir Editor, usar seu checkpoint e Cancelar/OK.
   Conferir mesmo owner, massa, Custom, composições e Gussets preservados.
   Cancelar a treliça não deve excluir a linha independente.
5. Testar Undo/Redo, reabrir documento e owner, alternar documentos, fechar
   Task View e iniciar Plano de Trabalho/linha nativa. Não deve haver callback,
   preview ou painel antigo residual. Respeitar diagnóstico de conflito externo.
6. Alternar os modos em painel estreito, com rolagem e escala maior. Conferir
   ordem, legibilidade e ausência de corte/overposição nos três temas.
