# Referência linear por aresta — Etapa 1 Snapshot

Base: `develop/0.7.0`, `29439b8d6e166b86a979a4633105890f1acb4065`.
Implementação local, sem staging ou publicação. Fundamentação:
[estudo de referências lineares](TRUSS_0_7_0_LINEAR_EDGE_REFERENCE_STUDY.md).

## Contrato e persistência

A captura de aresta reutiliza `TwoPoints`: P0/P1 globais, normal validada,
`reference_defined=True`, `reference_linked=False`, `reference_source=""`
e `reference_edge=""`. Não acrescenta modo persistente, propriedade,
schema, migração ou `PropertyLinkSub`. O `set_config()` existente deixa
`ReferenceSource=None` e `ReferenceContainers=[]`.

A aresta é consultada uma única vez. O candidato não contém o objeto,
`EdgeN`, nome mapeado ou identificador da origem. Mover, rotacionar,
redimensionar, reconstruir ou excluir a fonte não atualiza o Snapshot.
Não há Linha Draft auxiliar, alteração da fonte, transação de seleção ou
aplicação automática. A realização física continua exclusivamente no fluxo
existente de Aplicar/OK.

Nome/ID do objeto e `EdgeN` são somente informações temporárias na
`TrussEditSession`. Não são serializados no candidato, `C2Configuration`
ou `AppliedState`. Servem para o rótulo; nenhuma resolução geométrica usa
esses metadados depois da captura. Uma origem excluída ou substituída por
outro objeto com o mesmo Name deixa de ser identificada no rótulo, sem
invalidar as coordenadas. Após reabrir/copiar/editar em outra sessão, a
referência aparece como **Dois pontos**, coerentemente com seu contrato
persistido. A identificação informativa não acompanha a persistência.

## Autoridade do subelemento e coordenadas

`Selecionar existente` reutiliza a aquisição anterior, com observer nativo,
entrega diferida fora do dispatch de seleção, Esc e limpeza existentes.
Para a captura linear ampliada, utiliza:

1. `Gui.Selection.getSelectionEx("", 0)` e `addObserver(observer, 0)`.
   Assim, o objeto raiz e o caminho apontado no viewport não são reduzidos
   prematuramente à folha, perdendo seus ancestrais.
2. `root.getSubObject(path, 1)`, `getSubObjectList(path)` e
   `resolveSubElement(path)` identificam a fonte, os containers e o tipo
   explicitamente apontado. Não se escolhe `Edge1` de um objeto genérico.
3. `root.getSubObject(path)` obtém a aresta transformada pelo caminho
   completo. Não se multiplica novamente por `Placement` ou
   `getGlobalPlacement()`.
4. Os pontos são `edge.valueAt(FirstParameter)` e
   `edge.valueAt(LastParameter)`. A ordem não depende da enumeração de
   `Vertexes`. A normal é projetada perpendicularmente ao segmento,
   seguindo a convenção da Linha Draft e validada pelo `reference_frame`
   existente. A captura mantém a altura/envelope do rascunho.

As verificações nativas cobrem Translation/Rotation próprios, dois
`App::Part` aninhados e `PartDesign::Body` com feature. Comparam o caminho
global com uma transformação global calculada independentemente, para
detectar tanto coordenadas locais quanto transformação duplicada.

## Aceitação e limites

Aceita somente Shape válida e aresta explícita válida, `Part::GeomLine`,
dois vértices, parâmetros/comprimento finitos e limitados, extremos finitos
distintos e comprimento coerente acima de `AXIS_TOLERANCE`. A precisão
original dos pontos é preservada pelos campos existentes.

Rejeita faces, vértices, objeto completo genérico, curva/círculo/spline,
aresta ausente, fonte inválida, degeneração, outro documento e dependência
da própria treliça ou de seus componentes. A infraestrutura existente de
detecção de ciclos também verifica o caminho de containers. Um clique
inválido conserva o rascunho e mantém a aquisição disponível para nova
tentativa ou Esc.

**App::Link e arrays não são liberados nesta etapa.** Transformações e
ocorrências desses objetos exigem qualificação própria; a mensagem pede
selecionar a geometria original. Uma Shape derivada comum é aceita se for
válida, linear e independente da treliça. Splines visualmente retas também
são rejeitadas: não há aproximação silenciosa de curva.

Não há associatividade genérica nem tentativa de rastreamento topológico.
`EdgeN` é usado somente para resolver a seleção atual e informar sua origem
na sessão. Uma coincidência futura desse índice não pode criar vínculo.

## Coexistência com Draft e interface

O texto **Linha ou aresta** usa o identificador visual legado `DraftLine`.
Para uma aresta Snapshot, a projeção visual permanece nessa categoria,
enquanto `get_config()` entrega `TwoPoints` ao controlador. O indicador
exibe `Origem · EdgeN — Snapshot`; **Manter vínculo com a fonte** fica
desmarcado e desabilitado, com tooltip de coordenadas fixas. A preferência
anterior é restaurada ao selecionar uma fonte Draft vinculável.

Linha Draft continua no reconhecedor/resolver legado: seleção inteira ou
Edge1, vínculo quando solicitado e Snapshot quando o vínculo não é marcado.
Uma Linha Draft aninhada é entregue ao adaptador legado como objeto folha;
suas transformações de containers continuam no contrato existente.
**Desenhar nova** continua exclusivamente no comando nativo Draft Line,
com a suspensão/reconstrução aprovada e a mesma sessão/controlador.

**Retângulo Draft** continua um modo distinto: sua base explícita determina
o envelope e a altura. Selecionar um lado do mesmo retângulo na categoria
**Linha ou aresta** captura somente aquele segmento, mantendo o envelope
e a altura anteriores.

O layout aprovado, incluindo `removeWidget()`, não foi alterado. Não há
filtros globais, novo timer, captura de pontos ou gerenciador de transações.

## Sessão, Editor e aplicação

Selecionar uma aresta muda somente o rascunho. Baseline, owner e sólidos
continuam intactos até Aplicar/OK. Esc encerra somente a captura, sem
restauração destrutiva porque nenhum clique inválido altera a configuração.

O checkpoint profundo do Editor inclui os metadados informativos e a
preferência de vínculo. Cancelar/X restaura ambos juntamente com a
configuração/candidato/widgets, respeitando os bloqueios de conflito
existentes. Aplicar atualiza o checkpoint pelo fluxo transacional aprovado;
Cancelar posterior preserva o resultado já materializado. Os botões do
TaskPanel mantêm sua semântica anterior.

Desenhar nova com Esc preserva os metadados da sessão reconstruída. Uma
Linha Draft criada com sucesso substitui a referência e limpa a identificação
Snapshot ao reconstruir o painel com o modo DraftLine real.

## Arquivos deste incremento

Produção modificada:

- `freecad/SteelStructures/interactive/truss_controller.py`
- `freecad/SteelStructures/interactive/truss_reference_selection.py`
- `freecad/SteelStructures/interactive/truss_task_panel.py`
- `freecad/SteelStructures/interactive/truss_editor_checkpoint.py`

Novo adaptador funcional:

- `freecad/SteelStructures/truss_edge_snapshot.py`

Testes/runner:

- `tests/test_truss_edge_snapshot.py` — novo, contratos com stubs.
- `tests/test_truss_edge_snapshot_gui.py` — novo, Qt/Part/Draft reais.
- `tests/manual_freecad_truss_edge_snapshot.py` — novo, entrada isolada.
- `tests/test_truss_reference_selection_gui.py` — ajusta as rejeições:
  arestas retas explícitas passam a ser suportadas; face/vértice/objeto
  inteiro continuam rejeitados.
- `scripts/run_truss_duopitch_gate.py` — acrescenta `edge_snapshot`, usando
  o mesmo isolamento, temas, logs e critérios de erro dos gates anteriores.

Não foram modificados núcleo geométrico, schema/serialização, `truss.py`,
massa, perfis, Gussets, StructuralPlate, Draft global, ícones ou versões.

## Validação

Execução em FreeCAD **1.1.4**, revisão local da instalação
`4fd3bf320d9566a27e60069fc8387448aaa3a094`. Os gates usam processos e
perfis descartáveis em `test-results/truss-duopitch/`, sem alterar as
preferências do usuário. Resultados finais:

| Comando/probe | Resultado | Pasta de evidências |
| --- | --- | --- |
| Python focado, comando abaixo | **83 aprovados**, zero falhas/skips | saída unittest |
| `edge_snapshot --editor-theme Classic` | **26 aprovados**, zero erros Qt/logs | `1792273908310974600_mq8vj81t` |
| `edge_snapshot --editor-theme "FreeCAD Dark"` | **26 aprovados**, ressalva visual abaixo | `1792273947206884300_yu5r1x19` |
| `edge_snapshot --editor-qss OpenDark.qss` | **26 aprovados**, zero erros Qt/logs | `1792273989486012800_8hdb2ymh` |
| `draft_reference --editor-qss OpenDark.qss` | **103 verificações aprovadas** | `1792273866367184700_bpf32j74` |
| `reference_layout --editor-theme Classic` | **4 aprovados** | `1792273536770643300_dorhihaq` |
| `reference_layout --editor-qss OpenDark.qss --qt-scale-factor 1.5` | **4 aprovados**, DPR 1,5 | `1792274147239253100_jxkirixe` |
| `python scripts/check_project.py` | aprovado | saída do comando |
| `git diff --check` | aprovado, apenas avisos de conversão LF/CRLF | saída do comando |

```powershell
python -m unittest tests.test_truss_edge_snapshot tests.test_truss_reference_controls tests.test_truss_reference_selection tests.test_truss_task_panel tests.test_truss_draft_reference tests.test_truss_editor_actions tests.test_truss_c2_references
python scripts/run_truss_duopitch_gate.py --probe edge_snapshot --editor-theme Classic
python scripts/run_truss_duopitch_gate.py --probe edge_snapshot --editor-theme "FreeCAD Dark"
python scripts/run_truss_duopitch_gate.py --probe edge_snapshot --editor-qss "C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss"
```

Uma execução adicional do conjunto Python incluindo
`tests.test_truss_reference_fields` totalizou 98 testes: 83 aprovados e
15 skips por ausência de FreeCAD/Qt no Python do sistema. Não foram
contabilizados como aprovação desses 15 casos. Os campos reais e a
preservação dos pontos globais foram exercitados pelos gates nativos.

Os 26 testes nativos por tema incluem 12 regressões da seleção anterior e
14 casos Snapshot: retângulo/Box/membro/chapa, cliques reais e pré-seleção,
Placement próprio/hierárquico, Body em Part, metadados/checkpoint,
Custom/compostos/Gusset, retorno do desenho/Esc, Aplicar repetido, Cancelar/X,
OK, troca/exclusão de fonte, cópia/save/reopen, Undo/Redo/conflito, fontes
inválidas e fechamento/troca de documento/comando. O mesmo conjunto é
repetido nos temas; não são 78 casos distintos.

Construção dos testes: as primeiras rodadas registraram um import incorreto
no teste de persistência e falhas nas fixtures de clique/medição Qt. Foram
corrigidas as chamadas ao contrato real `config_from_object`, a exibição da
cena e a acomodação da largura antes da captura/medição. Nenhuma correção
geométrica ou mudança do layout aprovado foi necessária. Os tracebacks
dessas rodadas permanecem nas pastas geradas, incluindo
`1792273258149020900_myrd2pf7` e `1792273594436058800_zkr5_u4c`.

**Limitação visual Dark:** o perfil isolado com o tema nativo FreeCAD Dark
reproduziu fundo claro de widgets genéricos e texto claro herdado do tema,
inclusive nos rótulos antigos do painel. Os testes funcionais, tamanhos e
ausência de sobreposição passaram; isso não significa aprovação de contraste
nesse perfil. Uma verificação adicional sem o antigo `General/QtStyle`
copiado também reproduziu o problema (`1792274087666434200_vse2usa4`,
26 aprovados; palette Window `#f0f0f0`). A hipótese desse parâmetro foi
descartada e o runner não mantém esse ajuste experimental. Não houve
contorno de paleta/QSS em produção. A aparência Dark precisa ser conferida
manualmente na instalação habitual. Capturas Classic e OpenDark foram
inspecionadas, incluindo 260 px, com controles legíveis e sem sobreposição.

O erro histórico `QLineEdit already deleted` não foi observado nesta rodada.
Há avisos nativos `QString::arg` do Draft nos logs; não houve exceção de
callback Qt, falha nativa ou resíduo identificado pelos gates. Nenhuma
alteração global foi aplicada ao Draft para silenciar esses avisos.

Testes com stubs/Qt automatizado não substituem a aprovação manual
interativa. **A suíte completa não foi executada**, conforme o escopo.

## Preservação e Git

HEAD e branch mantidos: `29439b8`, `develop/0.7.0`; índice vazio antes e
depois. Nenhum add, commit, push, merge, tag ou release.

Comparação SHA-256 de 551 arquivos preexistentes: somente os seis arquivos
modificados listados acima diferem. Os outros 545 permanecem intactos,
incluindo estudo técnico, estudos Gusset, experimentos StructuralPlate e
documentos locais. Registro em
`test-results/truss-edge-snapshot/20261017_183719/preservation.json`.
Este incremento acrescenta cinco arquivos: adaptador, dois módulos de
testes, entrada nativa e este documento; total de **11 arquivos** no escopo.

## Roteiro manual curto — OpenDark / FreeCAD 1.1.4

1. Criar Box, retângulo Draft, membro e chapa; mover/rotacionar uma fonte e
   colocar outra em `App::Part`. Abrir o Gerador, ajustar altura e perfis.
2. Em **Linha ou aresta → Selecionar existente**, clicar em uma aresta
   reta. Conferir P0/P1/vão globais, preview, identificação Snapshot e
   vínculo desmarcado/indisponível. Confirmar que nenhum objeto foi criado.
3. Tentar face, vértice e curva; conferir mensagem, preservação dos campos
   e nova tentativa. Pressionar Esc e repetir a captura.
4. Aplicar; mover/redimensionar/excluir a fonte. A treliça deve permanecer
   fixa. Salvar/reabrir: conferir geometria e modo Dois pontos, sem vínculo.
5. Selecionar uma Linha Draft; conferir recuperação da preferência de
   vínculo e atualização associativa quando marcada. Testar **Desenhar
   nova**, Esc e conclusão; depois, Retângulo Draft com base explícita.
6. Em Snapshot, abrir Editor, alterar e Cancelar/X; conferir checkpoint.
   Aplicar no Editor, alterar novamente e Cancelar: preservar a aplicação.
   Repetir em largura estreita e conferir leitura/rolagem sem sobreposição.

O incremento fica pronto para validação manual após os gates focados;
publicação continua condicionada ao fluxo normal de aprovação do projeto.
