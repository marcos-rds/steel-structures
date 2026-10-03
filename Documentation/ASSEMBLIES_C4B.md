# C4-B — attachment físico e interconectores na Treliça

Base: `develop/0.6.0`, `6cf6db59a3b9f90f5ae6a37279a29a60def3df89`.
Uma revisão arquitetural curta antes da implementação; depois somente o
Implementer. Sem mudança de versão de release ou auditoria QA ampla.

## Convenção e geometria

`d = normalize(B.start − A.start)` e `n = w × d`, sendo `w` a direção
longitudinal nominal. Para um par separado em +u, n é +v do frame da assembly.
**Face A = +n; Face B = −n.** A câmera e os eixos globais não participam.
O frame dos interconectores C4-A permanece intacto; a direção n é projetada
nesse frame para resolver o posicionamento da seção.

`assemblies/attachment.py` é puro, sem FreeCAD, Part, Qt ou Coin.
`support(section, direction)` calcula extremos analíticos: extremidades de
segmentos e ângulos críticos dos arcos que pertencem ao sweep, inclusive
arcos de círculo completo e sentido horário. Percorre contornos externos e
internos. Não aproxima a posição física por amostragem nem por dimensões
nominais hardcoded. Os testes incluem U, L, RHS, SHS e seções sólidas.

A seção é construída pelo gerador real de `SectionGeometry2D`, transformada
por `SectionTransform`, e sua referência de inserção transformada é subtraída.
O suporte resultante é projetado no frame do membro e somado à posição do eixo
físico. A geometria transformada é cacheada em memória para evitar reconstruir
a mesma seção para cada estação; nenhuma Shape de documento é usada no core.

- Gap interno da chapa: `min_B(d) − max_A(d)`, restringindo os contornos
  à faixa em n ocupada pela seção física da chapa. As interseções com a faixa
  são analíticas, inclusive nos arcos. Assim, faces recuadas são alcançadas
  quando as abas não ocupam essa faixa; não há regra especial para U.
- Span externo: `max_B(d) − min_A(d)`.
- SpacerPlate: a faixa física da chapa é centralizada na interseção dos
  suportes transversais dos componentes, compensando a inserção da chapa.
  A posição acompanha deslocamentos reais, sem ficar ancorada à referência
  de inserção do perfil. Sem sobreposição transversal válida, há conflito
  humano; o cálculo face-a-face dentro da faixa permanece preservado.
- Plano Face A: suporte máximo em n de ambos os componentes.
- Plano Face B: suporte mínimo em n de ambos os componentes.

Os suportes correspondentes A/B precisam coincidir dentro de
`ATTACHMENT_TOLERANCE = 1e-6 mm`. Caso contrário:
“As superfícies selecionadas dos componentes não são coplanares.”
Não há torção, média de planos incompatíveis ou offset silencioso.

Tangência usa também o suporte da seção **do interconector**, incluindo sua
transformação e inserção. Face A posiciona o eixo em `plano − min_support(n)`;
Face B usa `plano − max_support(n)`. Não coloca metade da seção para dentro
do componente. Não há lógica geométrica por família nem boolean cut.

## Tipos e posicionamento explícito

`InterconnectorSpec.attachment_plane` é aditivo, com default **AxisToAxis**.
O schema de assembly continua 1; payloads C3/C4-A sem esse campo mantêm o
posicionamento anterior. Abrir ou editar um documento legado não o converte
automaticamente para Face A/B. O editor mostra “Eixo-a-eixo (legado)” quando
esse valor está presente.

- `SpacerPlate`: chapa espaçadora no gap interno, endpoints nos suportes
  internos A/B, plano central dos eixos e `InnerFaces` obrigatório. Gap nulo
  ou negativo é incompatível. Não oferece Face A/B/Both.
- `Battens`: span entre extremos externos, em Face A, Face B ou Both.
- `SingleLacing`: conserva a alternância C4-A e StartSide. Endpoints usam
  coordenada longitudinal da estação e coordenada de separação do eixo do
  componente, deslocados para tangência ao plano selecionado.
- `DoubleLacing`: duas barras independentes por intervalo, em cada face
  selecionada. O cruzamento não cria nó, divisão ou conexão.

As superfícies são suportes do envelope. Isso não escolhe flange, alma,
linha de solda ou parafuso e não resolve fitting de contato final.

## Distribuição, identidade e persistência

A distribuição C4-A permanece baseada no eixo nominal, independente de
extensions, adjustments e Shapes recortadas. `ByCount` conta **estações**;
`ByTargetSpacing` usa ceil para obter espaçamento efetivo não superior ao alvo.
Offsets não são alterados automaticamente.

Nos modos físicos C4-B, os afastamentos se referem ao envelope longitudinal
da peça. O resolver projeta a seção transformada (incluindo inserção) em w e
recua as estações para conter os extremos. Treliçamentos recalculam as margens
conforme a inclinação até acomodar o envelope. Por espaçamento máximo, mantém
a contagem calculada no intervalo nominal com afastamentos; o intervalo entre
eixos diminui, preservando o teto de espaçamento e evitando oscilar a contagem.
`AxisToAxis` conserva integralmente as estações C4-A. Nenhum schema foi alterado.
O preview longitudinal mostra contornos projetados das peças, com o título
“Vista longitudinal”, sem repetir afastamentos medidos nos eixos. Um único
comprimento nominal aparece como label; múltiplos comprimentos continuam selecionáveis.

Validação manual do polimento: comparar a medida da chapa às faces internas
na faixa ocupada (inclusive U inward e perfil rotacionado); conferir bordas
inicial/final com 0/0 nos quatro tipos; alternar Face A/B/Ambas, regenerar,
salvar/reabrir e verificar preservação dos membros. Conferir também uma
configuração C4-A em Eixo-a-eixo. Testes automatizados não substituem essa
validação no FreeCAD. Contatos curvos/inclinados usam suportes tangentes;
cortes de adaptação para contato de área inteira permanecem fora da C4-B.

O ramo primário conserva a identidade C4-A. Somente Both acrescenta
`SECONDARY` à identidade das cópias. FaceA↔FaceB e AxisToAxis→FaceA com a mesma
cardinalidade atualizam os membros existentes. Both→single preserva o ramo
primário deterministicamente; mudanças de cardinalidade passam pelo
RegenerationPlan. Labels não contêm a identidade nem determinam bindings.

No adaptador standalone, cada peça continua StructuralMember. Na Treliça,
GenerationOwner continua sendo StructuralTruss; RunKey + AssemblyKey +
InterconnectorKey/SlotKey/GeneratedElementKey registram a associação lógica.
AssemblyElementKind diferencia Component/Interconnector. Os registries hidden
evitam dependências reversas; não há links entre os componentes A/B.

## Integração com a Treliça

RoleSpec armazena interconectores dentro de assembly_spec. A configuração
vale para cada PhysicalRun do role, incluindo fechamentos esquerdo/direito.
As opções de perfil/inserção/cor/transformação dos interconectores são próprias
e não são sobrescritas pelo perfil dos componentes.

O bridge expande componentes e interconectores físicos. Nenhum TopologyNode,
TopologyEdge, PhysicalRun ou padrão Warren/Pratt/Custom adicional é criado.
As chaves de nós nos itens físicos são proveniência do run, não novas ligações
analíticas. Não foi criado modelo analítico.

O fluxo permanece UI → candidate → preview → RegenerationPlan → transação.
O preview 3D usa o mesmo prepare_batch da aplicação, em uma branch Coin
descartável, sem objetos FeaturePython temporários. A preparação completa
ocorre antes da mutação. Erros preservam o último estado, e rollback limpa
caches Python. Extensions/adjustments de sobreviventes são preservados;
remoção que descartaria ajustes/referências externas continua sendo conflito.

Cada role possui um subgrupo nativo “Interconectores” somente quando necessário.
Componentes ficam diretamente no role; labels dos interconectores incluem o
run. O subgrupo vazio é removido. As referências organizacionais desse grupo
são reconhecidas pelo preflight de remoção. Visibilidade de role, subgrupo e
parent usa o comportamento existente, sem interceptação global de Space.

## Editor e previews

O editor existente conserva seus controles e preview transversal; a coluna
“Interconectores” é mostrada para composições duplas. Simples a oculta e não
emite interconectores. Configurações com múltiplas specs preservam todos os
conjuntos; um seletor permite editar cada conjunto já existente.

Controles: tipo, plano, distribuição, quantidade/painéis, espaçamento máximo,
afastamentos inicial/final e StartSide para SingleLacing. N painéis mapeia para
N+1 estações. O espaçamento efetivo é exibido, sem recomendação normativa.

O botão de perfil abre o editor compartilhado com catálogo filtrado, inserção,
rotação e cor; inversão lateral também está disponível. Defaults consultados
no catálogo: `Barra Chata 50,8x6,35` e `L 40 x 4`. Chapas/presilhas filtram
barras chatas; lacing aceita cantoneiras e barras chatas. Os mesmos predicados
validam a entrada do editor, sem limitar a geometria genérica do core.

O preview transversal mostra componentes, guias A/B, plano selecionado e a
projeção de uma peça representativa por conjunto/face. A aproximação visual
dos arcos não é utilizada no cálculo de suporte/tangência.
O preview longitudinal compacto mostra componentes, estações, offsets e
barras. As projeções de Both coincidem nessa vista; o transversal distingue
as faces. Um seletor escolhe entre os comprimentos nominais presentes no role;
todos esses comprimentos são validados antes do OK. Não usa comprimento de
Shape ajustada. Cancelar não modifica o documento.

## Validação realizada

Testes focados, 116 aprovados:

```powershell
python -m unittest tests.test_truss_interconnectors tests.test_assembly_attachment tests.test_assembly_interconnectors tests.test_truss_assemblies tests.test_assembly_refinements tests.test_assemblies tests.test_truss_task_panel
```

As fixtures C4-A foram atualizadas apenas onde esperavam que a Treliça
rejeitasse interconectores ou não conheciam a metadata nova; as asserções de
preservação de objetos continuam presentes.

`python scripts/check_project.py` executado uma vez e aprovado.
`git diff --check` aprovado; arquivos novos também verificados quanto a
whitespace. Índice vazio e HEAD inalterado no fim da implementação.

MCP confirmou FreeCAD 1.1.3 e abriu o editor de prova. A chamada seguinte
expirou no despacho GUI com o diálogo modal. O gate completo foi executado,
com autorização, em uma **instância isolada do FreeCAD 1.1.3**, com configuração
própria. Não se alega que essas verificações tenham passado pelo transporte MCP.

`tests/manual_freecad_assemblies_c4b.py`: **15 verificações agregadas aprovadas**,
com sete casos físicos, projeção de Shapes reais, interseção OCC sem penetração
sistemática, conflito não coplanar, FaceA→FaceB, Both, Undo/Redo, rollback após
criação parcial, árvore/DAG/visibilidade, preview 3D, Qt real, Cancelar,
remoção de subgrupo e save/reopen/recompute. Capturas de presilhas, lacing,
spacer e do modelo axonométrico foram inspecionadas.

Artefatos fora do Git em `test-results/assemblies-c4b/`:
`AssembliesC4B.FCStd`, `assemblies-c4b.png`, `editor-battens.png`,
`editor-lacing.png`, `editor-spacer.png`, `report.json`.

## Roteiro manual e limites

1. Reiniciar FreeCAD para carregar os módulos atuais; abrir o FCStd da prova.
2. Inspecionar SpacerPlate e Batten em vista transversal; comparar Face A/B/Both
   e o caso inclinado. Conferir orientação sem exigir fitting de fabricação.
3. Abrir o role do banzo, editar tipo/plano/perfil/quantidade/offsets/StartSide
   e comparar os três previews. Cancelar deve conservar o estado aplicado.
4. Confirmar alterações, conferir subgrupo/visibilidade e preservação de
   objetos ao trocar somente Face A/B; repetir Undo/Redo e reabertura.

Fora desta etapa: overlap adicional, escolha exata de flange/alma, linhas de
parafuso, furos, bolts, soldas, end/stay plates, conexão no X, gusset, PlaneCut
automático, cope/notch, ElementCut, cálculo normativo, seção equivalente e
modelo analítico. As peças que se cruzam continuam independentes, sem fitting.

## Fechamento C4-B

Validação manual final aprovada pelo usuário no FreeCAD 1.1.3, incluindo
SpacerPlate e sua centralização, deslocamentos reais e conflito sem overlap,
Battens Face A/B/Both, SingleLacing, DoubleLacing, quantidade, espaçamento
máximo, offsets pelo envelope físico, previews transversal/longitudinal/3D,
regeneração, árvore e compatibilidade C3/C4-A.

Suíte completa anteriormente aprovada nesta etapa: **1.077 testes**, antes
do último microajuste da SpacerPlate. Após esse ajuste: **65 testes focados
aprovados**, além de `python scripts/check_project.py`. A suíte completa não
foi repetida no gate final, conforme solicitado pelo usuário.

Gate de fechamento: revisão curta de blockers e escopo C4-B,
`git diff --check`, `python scripts/check_project.py` e verificação do diff
em staging. Commit autorizado: `feat(assembly): add physical interconnector placement`.
Sem push. C5 não iniciada; nenhuma mudança de versão ou release.
