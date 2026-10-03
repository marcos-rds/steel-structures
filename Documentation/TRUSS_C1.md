# Gerador de Treliças — C1

## Validação focada C1.1 — headers, visibilidade e rotação

- Headers sem moldura, com setas Qt e separador clicável; navegação em acordeão preservada.
- ViewProvider registra um modo Coin vazio `Group`. Sem modo ativo, o parent tinha
  `Visibility=True`, mas `isVisible()=False`, impedindo o Space nativo de alternar.
  Não há Shape agregada nem mudança de relações entre parent e filhos.
- Dois SVGs de rotação em QToolButtons de 26 px junto ao campo numérico,
  com tooltips `Girar -90°` e `Girar +90°`.
- Verificado no FreeCAD 1.1.3: Space no parent e na diagonal; restauração de filho
  previamente oculto; salvar/reabrir; duplo clique; acordeão e clique no separador;
  aparência e incremento dos botões de rotação.
- A troca para “Começar” ao mostrar pela árvore também foi reproduzida com uma
  `Part::Box` dentro de `App::DocumentObjectGroup`, sem proxy da workbench.
  A alteração direta de Visibility não apresentou a troca. Não foi instalado
  interceptador de Space nem correção de foco global; esse comportamento nativo
  permanece pendente de investigação fora desta correção C1.1.
- O documento temporário foi fechado e o candidato não aplicado do usuário
  foi restaurado com configuração idêntica. Objetos já carregados com o
  ViewProvider antigo devem ser reabertos para carregar o modo visual corrigido.

Implementação funcional inicial, sujeita à validação visual e funcional do usuário.
Não faz análise estrutural, dimensionamento nem detalhamento de ligações.

## Contratos e escopo

```
EnvelopeDefinition
  -> StationPlan
  -> TopologyGraph (segmentos lógicos atômicos)
  -> PhysicalRun (peças retas)
  -> Candidate / RealizationItem
  -> RegenerationPlan
  -> StructuralTruss + StructuralMember existentes
```

O pacote `trusses` é Python puro: não importa FreeCAD, Part, Qt ou Coin.
Coordenadas são triplas em milímetros; no C1, os nós têm Z local igual a zero.
X é o vão, Y é a altura no plano e Z é a normal do plano. A schema permanece 3D.

Envelopes:

- `Parallel`: banzo inferior de (0,0,0) a (Span,0,0); superior na altura Height.
- `DuoPitch`: apoios compartilhados com altura **zero**, banzo inferior reto e
  ápice em (Span × ApexPosition, Height, 0). ApexPosition é fração estritamente
  entre 0 e 1; não existe altura adicional nos apoios.

Panelização: somente `ByPanelCount`, inteiro N >= 4. N é o número final de
intervalos longitudinais. Não há correção silenciosa de paridade.

Na criação de DuoPitch, a alocação inicial é
`left = clamp(floor(N * ApexPosition + 0.5), 1, N-1)` e `right = N-left`.
Os valores aplicados ficam persistidos em LeftPanels/RightPanels e no StationPlan.
Alterar somente o ápice preserva essa divisão, inclusive durante o preview.
Alterar N permite uma nova distribuição. A cumeeira é sempre estação obrigatória.

## Variantes dos presets

Nomes de presets são sementes determinísticas, não classificações de análise.

Warren paralela: diagonais alternadas, começando no banzo inferior à esquerda;
montantes de fechamento somente nas duas extremidades. Há nós de ambos os banzos
em cada estação, mesmo quando o nó só conecta segmentos de banzo.

```
T0----T1----T2----T3----T4
|    /  \       /  \    |
B0----B1----B2----B3----B4
```

Warren de duas águas: os apoios são nós únicos com ambas as afiliações. Os
primeiro/último painéis formam triângulos pelos banzos e pelos montantes nas
primeira/última estações interiores. Não se acrescenta uma diagonal duplicando
um banzo nesses painéis. Nos painéis interiores, a diagonal alterna conforme a
paridade longitudinal. Não há montantes genéricos nas demais estações.

Pratt: há montantes em todas as estações interiores. As diagonais ligam o nó
superior mais externo ao inferior mais interno em direção ao centro (Parallel)
ou ao ápice (DuoPitch). Em Parallel com N ímpar, o painel que contém o centro
segue explicitamente o sentido da metade esquerda. Os extremos de DuoPitch usam
o mesmo fechamento triangular descrito acima, sem diagonais redundantes.

Os testes independentes guardam incidências exatas para ambos os presets,
incluindo painéis ímpares, ápice assimétrico e águas com só um intervalo.

## Identidade e continuidade

As estações de apoio e cumeeira têm chaves semânticas fixas. As intermediárias
usam a fração **reduzida** dentro do trecho semântico (MAIN, LEFT ou RIGHT), não
coordenadas, Label ou índice corrente. Exemplo: S_LEFT_1_2 identifica o meio da
água esquerda. Mudar dimensões preserva todas as chaves; repanelizar preserva
somente as frações que continuam presentes.

Nós compartilham identidade nos apoios de DuoPitch. Edges identificam papel e
par dirigido de nós, com banzos/diagonais no sentido longitudinal e montantes
de baixo para cima. A validação rejeita chaves/referências inválidas, coordenadas
não finitas, arestas nulas/duplicadas e aresta atravessando nó conectado que
exigiria divisão. Componentes desconectados, coincidências e cruzamentos sem
conexão geram avisos geométricos; hiperestaticidade não é rejeitada.

Um PhysicalRun pode cobrir vários edges. `BC_MAIN` permanece a mesma peça
contínua ao inserir estações. `TC_MAIN` é o superior paralelo; `TC_LEFT` e
`TC_RIGHT` são as águas. Nunca há uma peça reta atravessando a cumeeira.

Continuidade C1:

- Continuous e SegmentAtBreaks unem cadeias retas com a mesma RoleSpec. São
  equivalentes para os dois envelopes C1: a única quebra é a cumeeira.
- SegmentAtEveryNode gera uma peça por edge lógico de banzo.

Runs de alma derivam da identidade semântica do edge. Não existe matching por
proximidade, coordenada, comprimento ou Label.

## Especificação e orientação

Cada um dos cinco papéis tem ProfileRef (catalog_id/profile_id), insertion,
rotation, SectionGeometryMode, cor, assembly=Single e physical_fit=None.
Não há vínculo implícito entre papel e família. O Browser existente fornece
qualquer perfil que a infraestrutura atual consegue construir.

A referência TwoPoints exige P0, P1 e normal explícita perpendicular ao eixo.
O painel inicia com normal (0,-1,0), mostrando o plano vertical XZ; não infere
um plano a partir de uma direção quase singular. Coordenadas numéricas e pontos
capturados pelo snapping Draft seguem o mesmo validador.

O parent persiste Placement com origem P0 e base ortonormal. Span é a distância
P0–P1. Mudança numérica de Span move o fim mantendo a direção; não há duas
distâncias independentes. Não se aplica transformação de container aos filhos.

Para cada direção unitária w: u = Z da treliça; v = w × u; u × v = w.
O adaptador compara u com o frame já usado por `_member_frame_rotation()` e
calcula o roll relativo. Soma então a rotação da RoleSpec. Insertion e rotação
continuam sendo os mecanismos normais de StructuralMember; perfil U/cantoneira
não recebe geometria especial. Os membros continuam extrudados no Z local.
O roll aplicado é normalizado em [0,360). Cores são normalizadas para canais
de 8 bits, como a persistência de aparência do FreeCAD; isso evita falsos
conflitos de propriedades após salvar/reabrir. Comparações geométricas ignoram
somente ruído numérico de frame (tolerância absoluta 1e-8 mm/relativa 1e-12),
sem alterar o critério semântico de identidade.

## Parent, árvore e DAG

StructuralTruss é `App::FeaturePython`, com Placement explícito e sem sólido
monolítico. GeneratedMembers e RoleGroups são `App::PropertyLinkListHidden`.
O tipo Hidden exclui as referências organizacionais da dependência nativa;
esconder apenas o editor de um PropertyLink normal não seria equivalente.

Os filhos continuam `Part::FeaturePython` + StructuralMemberProxy. Possuem
GenerationOwner (link normal), GenerationKey, GenerationStatus e ControlledState
interno. O DAG é parent -> member -> grupo comum. Os grupos não são App::Part
e não transformam as peças. A árvore mostra grupos por papel; nós topológicos
não são objetos permanentes.

O parent controla eixo, perfil, inserção, rotação, geometria de seção e cor.
Eixo, Placement e propriedades controladas ficam somente leitura no editor.
Uma edição por Python/expressão ainda é possível no FreeCAD; por isso existe
comparação com ControlledState antes de aplicar. Conflitos preservam a Shape
anterior e são informados, em vez de serem sobrescritos silenciosamente.

Offsets, extensões e ajustes manuais sobrevivem quando a peça sobrevive.
A criação não gera fitting: ConnectionForm é conceitualmente GeometricOnly,
FasteningIntent é Unspecified. Não há furos, chapas ou cortes automáticos.
AxisSource de um filho gerado fica vazio, AxisDefinitionMode Independent; a
definição nominal é controlada pela treliça, sem uma segunda fonte concorrente.

## Aplicação atômica e último conjunto válido

O candidato e o plano de diferenças são puros. Alterações com as mesmas
identidades atualizam os mesmos objetos. Alterações estruturais, incluindo
repanelização, troca de preset e continuidade, ficam pendentes até
**Atualizar Treliça**. `execute()` nunca cria ou remove objetos.

`member_batch.MemberInputSnapshot` é um adaptador de propriedades em memória.
Ele chama o próprio execute de StructuralMemberProxy num objeto destacado,
reutilizando seção, extrusão, massa, extensões e ajustes. Não lê child.Shape
para gerar a definição e não cria um segundo pipeline geométrico.

Todas as Shapes candidatas são preparadas e validadas antes da primeira mutação.
Inputs/resultados são aplicados juntos. O execute subsequente dos filhos consome
um token de preparação para evitar um segundo OCC no mesmo recompute. O token é
de uso único: referências associativas externas podem mudar sem mudar o LinkSub.
Alterações manuais permitidas usam avaliação destacada defensiva e mantêm a
última Shape em caso de falha.

Atualizações geométricas guardam os últimos resultados preparados para rollback
sem ler Shape de filhos. A promoção de AppliedState faz parte do mesmo bloco
protegido. Criação e atualização estrutural usam uma transação, factory com
`recompute=False` para cada filho e um recompute final. Erro posterior aborta a
transação; a recuperação usa recompute separado apenas no caminho de falha.
Não se usa o valor de retorno de recompute como prova de Shapes válidas.

Remover uma peça é bloqueado se houver referências externas, bindings
inconsistentes, conflito de propriedades, expressões, offsets, extensões ou
ajustes que seriam descartados. Não há Detach/Override UI no C1.

Referências associativas a outros filhos/derivados da mesma treliça são
conservadoramente bloqueadas em batch: preflight não pode usar a Shape antiga
de um filho que também mudará. Origens externas com recompute pendente ou estado
inválido exigem recomputar a origem e aplicar novamente. Após restauração, um
membro associativo precisa de avaliação válida antes de servir de baseline de
rollback. Essas restrições evitam criar novos ciclos/dependências nesta fase.

## Persistência e preview

SchemaVersion=1 e generator_version=1 desde o primeiro objeto. AppliedState é
JSON estrito, determinístico, sem NaN/eval, contendo config, StationPlan, grafo,
runs, itens realizados e bindings por Name. RoleSpecs é JSON separado e oculto.
Versões desconhecidas não são migradas silenciosamente. Uma migração futura
deve transformar explicitamente o estado versionado e preservar a definição
aplicada se não conseguir reconstruí-lo.

O painel usa preview 2D sem objetos do documento e debounce de 200 ms para 3D.
O preview 3D usa uma ramificação Coin temporária e não selecionável, preparada
com Shapes do mesmo pipeline. Não cria objetos no documento, não marca o
documento como modificado e não entra no Undo. É removida antes da transação
de criação e ao cancelar; ownership e callbacks pertencem ao controller.

## Testes e próximas fases

Automatizados: `tests/test_truss_core.py`, `tests/test_truss_qa.py`,
`tests/test_truss_task_panel.py` e regressão das ferramentas existentes.
Gate real: `tests/manual_freecad_truss_c1.py`, executado no FreeCAD, grava JSON
numérico e FCStd temporários fora dos arquivos versionados. Screenshots servem
à revisão de orientação/UI, não substituem endpoints, validade e volume.

C2: editor gráfico e novas referências. C3: assemblies reutilizáveis e
transforms de componentes. C4: battens/lacing. C5: fitting genérico e
ConnectionIntent/gusset-aware placement. C6: gusset preliminar. Nenhuma dessas
funcionalidades está implementada no C1. AnalyticalNodes/Bars devem derivar do
grafo lógico, independentemente do número de componentes físicos. Não há solver.

IDs externos de subelementos FaceN não ganham estabilidade topológica por manter
o Name da peça. Alterações de perfil podem exigir rever referências externas.
Treliças espaciais, assemblies duplos e ElementCut permanecem fora do escopo.

## Evidências desta implementação

Gate independente no FreeCAD 1.1.3: 13 fases / 2.184 verificações aprovadas.
Os quatro pares de envelope/preset foram salvos/reabertos, alterados após
restauração e submetidos a recompute repetido. Foram exercitados Pending/Apply,
Undo/Redo, conflitos e falhas injetadas no segundo preflight, segundo apply e
após escrita do estado aceito; o conjunto anterior foi preservado.

GUI: Browser real com U, cantoneira e RHS, popups de orientação, miniaturas,
criação/Undo/Redo e cliques sintéticos Qt na viewport usando o Snapper nativo.
O teste do preview Coin confirmou ausência de objetos e de modificação do
documento após Cancelar. A validação visual final continua com o usuário.

Medição em sessão FreeCAD 1.1.3, Parallel Pratt, perfis U 8" x 17,10,
L 5" x 3/8" e RHS 140x120x9, sem otimização específica:

| Painéis | Peças | Core + realização | Comparação do plano | Preview 3D | Criação | Recompute sem mudanças | Atualização geométrica |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | 15 | 0,66 ms | 0,96 ms | 106 ms | 190 ms | 4,95 ms | 93 ms |
| 12 | 27 | 2,10 ms | 1,70 ms | 189 ms | 320 ms | 0,25 ms | 184 ms |
| 24 | 51 | 7,55 ms | 3,39 ms | 364 ms | 605 ms | 0,35 ms | 336 ms |

Core e comparação são médias de 20/100 execuções; as operações CAD são amostras
individuais, dependentes da máquina, perfil e tesselação. O maior custo observado
é preparar/renderizar geometria, não a topologia. O timer de 200 ms é debounce,
não promessa de tempo total de resposta. O roteiro reproduzível adicional é
`tests/manual_freecad_truss_performance.py`.

## Corre??es da valida??o manual C1

A normal positiva usada anteriormente como X da se??o invertia seu Y no
banzo horizontal. A normal negativa preserva o frame destro e a conven??o
positiva do editor, sem compensa??es por fam?lia. Treli?as j? criadas devem
ser reaplicadas pelo Gerador para corrigir as Shapes existentes.

TopologyPreset, EnvelopeType, PanelCount, continuidades e paneliza??o s?o
somente leitura no Property View. Span, Height, ApexPosition e nomes continuam
edit?veis. O comando de atualiza??o permanece interno, fora da toolbar.
Space no parent guarda a visibilidade de cada filho e a restaura ao mostrar.
O preview de edi??o continua sobreposto: oculta??o tempor?ria por Coin foi
adiada at? valida??o espec?fica de n?o modificar o documento e de restaura??o.

Valida??o manual pendente: U/L em 0/?90/180? em banzos, montantes e diagonais
ascendentes/descendentes, RHS como regress?o; fechamentos voltados para dentro;
roles vis?veis ao trocar o candidato; snap em v?rtices, segundo ponto e Esc;
Space com um filho previamente oculto; duplo clique, Cancel, OK e Undo/Redo.
