# C4-A — núcleo de interconectores

Implementação standalone reutilizável em `assemblies/` e `assembly.py`, sem
FreeCAD/Part/Qt/Coin no contrato e nos resolvers puros. Revisão arquitetural
curta realizada antes da implementação, sem auditoria QA ampla.

## Contrato e persistência

`MemberAssemblySpec.interconnectors` agora aceita uma tupla de
`InterconnectorSpec` imutáveis. O campo já era reservado na C3-A: o schema de
assembly permanece **1**. JSON C3-A/C3-B sem o campo carrega `()`; o preflight
não regrava documentos antigos nem adiciona metadata. Campos novos são
instalados somente na aplicação explícita. Serialização da Treliça não mudou.

Cada spec define chave estável, `kind`, `component_pair` por chaves (não
índices), `ProfileRef`, modo geométrico, `SectionTransform` C3-A, referência de
inserção, cor, afastamentos inicial/final, `DistributionSpec` e `start_side`.
Kinds: `None`, `Battens`, `SingleLacing`, `DoubleLacing`. A tupla vazia é a
representação preferida de ausência de interconectores; `None` não emite membros.

Há validação de chaves únicas, par existente/distinto e cardinalidade dois.
Na resolução, os eixos devem ser paralelos, orientados no mesmo sentido,
corresponder ao comprimento nominal, começar na mesma estação nominal e ter
separação transversal não nula. Perfil inexistente é rejeitado no preflight
do adaptador, antes de alterar o documento, com mensagem humana.

`plane/side` não está no contrato atual: o plano é definido pelos dois eixos.
Uma extensão futura deve introduzir um campo com default equivalente a esse
plano e leitura compatível; semânticas que não sejam aditivas exigirão nova
versão. Não há payload arbitrário para opções ainda não implementadas.

## Distribuição longitudinal

Comprimento útil = comprimento **nominal** − start_offset − end_offset.
Shapes, ajustes, cortes e extensões físicas não entram nesse cálculo.

- `ByCount`: `station_count` é quantidade de estações, não de barras/painéis.
  Com duas ou mais, inclui ambos os extremos úteis e divide uniformemente.
  Uma presilha isolada é permitida no meio do comprimento útil, com espaçamento
  efetivo zero e mensagem explícita. Lacing exige pelo menos duas estações.
- `ByTargetSpacing`: informar `station_count=None` e `target_spacing > 0`.
  Número de intervalos = `ceil(comprimento_útil / target_spacing)`, no mínimo 1;
  número de estações = intervalos + 1. Espaçamento efetivo = comprimento útil
  dividido pelos intervalos. Offsets não são ajustados silenciosamente.
- O resultado inclui estações/chaves, posições, comprimento útil, quantidade,
  espaçamento efetivo e mensagens. Não constitui recomendação estrutural.
- Tolerância longitudinal: `LENGTH_TOLERANCE = 1e-8 mm`. Limite de recursos:
  `MAX_STATIONS = 10000`, com erro explícito se excedido.

As chaves padrão `S0000`, `S0001`, ... representam slots ordinais. A mesma
cardinalidade conserva esses slots mesmo que as coordenadas mudem. Um
controlador pode persistir `station_keys` explícitas; sua quantidade deve
coincidir com o resultado. Intervalos usam o par ordenado de chaves de estação.

## Padrões e orientação

### Decisão arquitetural confirmada no fechamento

Battens, SingleLacing e DoubleLacing são resolvidos entre os **eixos físicos
dos componentes A/B**. Essa realização eixo-a-eixo (axis-to-axis) é uma
**referência geométrica da C4-A**, não geometria final de fabricação. Ela prova
distribuição, identidade, regeneração, ownership e frames; não representa
ainda contato real com alma, aba ou face dos perfis.

`AttachmentPlane`, `FaceA`, `FaceB` e `Both` serão tratados na C4-B.
Fitting, overlap, recorte, solda, parafusos e contato final permanecem **fora
da C4**. A implementação não foi alterada para terminar a barra chata nas faces.

Presilhas: uma barra `A(s) → B(s)` por estação.

SingleLacing: uma diagonal por intervalo, alternando
`A(S0) → B(S1)`, `B(S1) → A(S2)` etc. `start_side="B"` inverte essa sequência.
A/B aqui significam a primeira/segunda chave de `component_pair`, inclusive
quando as chaves reais possuem outros nomes.

DoubleLacing: duas barras independentes por intervalo:
`A(Si) → B(Si+1)` e `B(Si) → A(Si+1)`. O cruzamento não divide barras e não
produz nó, conexão ou aresta topológica.

Cada barra possui eixo e frame próprios. A normal é obtida por
`(B.start − A.start) × longitudinal`; Y da seção segue essa normal, X está no
plano e Z segue o eixo da barra. Isso coloca a largura de uma barra chata no
plano de ligação. A orientação passa por `MemberFrame`, `member_batch.item_values`
e pelo resolver existente do StructuralMember. `SectionTransform` permanece
uma transformação local de seção; não há infraestrutura paralela nem hacks
por família ou pelo plano XY global.

## Identidade, ownership e regeneração

Componentes mantêm `(assembly_key, component_key)` da C3. Interconectores usam
`(assembly_key, "Interconnector", spec_key, kind, station/bay slots..., branch)`.
Ramos são `Batten`, `Lace`, `LaceA`, `LaceB`; StartSide não participa da identidade.
GenerationKey é o JSON inequívoco dessa tupla. Labels e floats não são IDs.

`AssemblyRealization.components` continua compatível; `interconnectors` e
`distributions` são separados, e `elements` reúne somente os membros físicos.
RegenerationPlan compara todos os elements. Mudanças de perfil, transformação,
cor, afastamentos, distância transversal e StartSide conservam membros quando
as identidades permanecem. Troca de kind/count passa por plano estrutural e
`allow_structural=True`. Remover membros ajustados/referenciados continua sendo
conflito explícito, preservando o estado anterior.

Todos são StructuralMembers reais pelo mesmo prepare/apply de C3. Preflight
prepara o lote inteiro; uma transação aplica tudo e aborta em erro, invalidando
caches Python. Extensions e adjustments existentes são carregados no snapshot.

Metadata: `AssemblyElementKind` (`Component`/`Interconnector`), `AssemblyKey`,
`ComponentKey`, `InterconnectorKey`, `InterconnectorSlotKey`, `GeneratedElementKey`.
Interconnector tem ComponentKey vazio. As propriedades são somente leitura.
O registry `AssemblyMembers` permanece `PropertyLinkListHidden`; cada membro
aponta para `GenerationOwner`. Não há links A→B nem B→A, nem ciclo owner/filhos.
Labels de prova são `Presilha 01`, `Treliçamento 01` etc.; agrupamento final não
faz parte desta etapa.

## Limite com a Treliça

Nesta C4-A, aplicação é pela API standalone `apply_assembly`. O bridge puro
`resolve_logical_member` aceita specs C4-A sem modificar o candidate da Treliça.
O editor/RoleSpec C3-B rejeita explicitamente assemblies com interconectores,
evitando descarte silencioso em sua expansão atual. Wiring/UX da Treliça fica
para C4-B. Nenhum TopologyNode, TopologyEdge, PhysicalRun, Warren/Pratt/Custom
ou modelo analítico foi alterado.

## Prova e validação

Fixtures puras em `tests/assemblies_c4a_fixtures.py`: SpacedPair sem conexão,
com quatro presilhas, com SingleLacing e com DoubleLacing; DoubleChannel com
presilhas/lacing e dupla cantoneira com lacing. Perfis consultados no catálogo:
`U 4" x 8,04`, `Barra Chata 50,8x6,35` e `L 40 x 4`.

`tests/manual_freecad_assemblies_c4a.py` executado por MCP no FreeCAD **1.1.3**:
**13 verificações agregadas aprovadas**. Inclui seis casos visuais, sólidos
válidos/volumes positivos, eixos e frames, offsets/estações, alternância, X,
transformação inclinada, DAG, compatibilidade C3, atualização com preservação
de nomes/extensão/ajuste, Undo/Redo, perfil inexistente, rollback após criação
parcial e save/reopen/recompute. Captura axonométrica inspecionada.

Durante o gate, foi corrigida a tradução de ProfileNotFoundError para ValueError
com mensagem humana no adaptador. A fixture é carregada por caminho porque a
workbench Fasteners já ocupa o pacote Python genérico `tests` nessa sessão.

Artefatos locais fora do Git: `test-results/assemblies-c4a/AssembliesC4A.FCStd`,
`assemblies-c4a.png` e `report.json`. Para executar novamente, carregar a fixture
com `importlib.util.spec_from_file_location` e chamar `run(output_directory)`.
Ela cria somente um novo documento; não altera documentos do usuário.

Testes focados (71 aprovados, incluindo 29 C4-A e compatibilidade C3):

```powershell
python -m unittest tests.test_assembly_interconnectors tests.test_assemblies tests.test_truss_assemblies tests.test_assembly_refinements
```

`python scripts/check_project.py` executado uma vez e aprovado;
`git diff --check` aprovado. Esse gate de implementação não incluiu staging,
commit ou push. Suíte completa não executada.

### Validação manual confirmada pelo usuário

Inspeção no FreeCAD 1.1.3 aprovada para fechamento da C4-A:

- Par espaçado sem conexão: OK.
- Battens: distribuição longitudinal regular e frame coerente.
- SingleLacing: OK.
- DoubleLacing: OK.
- Caso espacial/inclinado: OK.
- DoubleChannel/cantoneiras: orientação coerente.

Em um caso da fixture com dois U, as faces internas foram medidas em
aproximadamente **253,86 mm**. Três presilhas possuem `Length` nominal de
**240 mm**, coerente com a realização eixo-a-eixo. Uma presilha apresenta
`AdjustedLength` de **258 mm** porque a fixture testa extensão/ajuste de
StructuralMember. Essa diferença **não é bug da distribuição C4-A** e não
altera sua referência longitudinal nominal.

Fechamento autorizado com revisão curta e repetição somente do gate focado;
sem suíte completa e sem nova rodada MCP. Commit solicitado:
`feat(assembly): add member interconnectors`. Push não autorizado.
C4-B não iniciada neste fechamento.
