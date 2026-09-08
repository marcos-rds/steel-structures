# C3-A — núcleo reutilizável de MemberAssembly

Status: implementação local para validação arquitetural e visual. Sem UI C3-B,
sem seção equivalente, conectores C4 ou alteração de catálogos/releases.

## Contratos e unidades

`assemblies/` é puro: não importa FreeCAD, Part, Qt ou Coin. Distâncias em mm;
ângulos em graus. `MemberAssemblySpec` contém `assembly_key`, `behavior_mode`
(`Single` / `MultiComponent`), `assembly_insertion`, tupla de componentes,
`component_spacing` opcional e `interconnectors=()` reservado. Conectores não
vazios são rejeitados. Serialização JSON possui schema próprio, versão 1; não
migra nem altera o schema C1/C2 da treliça.

`AssemblyComponentSpec` contém chave estável, `ProfileRef` existente,
`SectionGeometryMode`, `SectionTransform`, translação transversal `(du,dv)`,
referência de inserção canônica e cor RGB. Valores não finitos, chaves repetidas,
modos incompatíveis e referências de inserção indisponíveis são rejeitados
(referências dependentes do perfil são verificadas no preflight do adaptador).

`Single` tem um componente e reproduz o caso atual quando transform=identidade
e translação=zero. Membros avulsos existentes não recebem assemblies nem novas
propriedades obrigatórias.

## Coordenadas, inserção e espaçamento

O frame é destro e ortonormal: **X da seção = u**, **Y da seção = v = w × u**,
**Z longitudinal = w**. A seção continua no XY local do StructuralMember e a
orientação global continua em seu Placement. O chamador fornece u; nunca se usa
câmera nem um eixo global implícito.

**Compatibilidade C1/C2:** a implementação existente de Truss fornece
`section_u_global = -normal_da_treliça`. Esse sinal permanece intacto. A ponte
pura `resolve_logical_member(item, spec)` recebe exatamente esse frame; não
reinterpreta a normal como +Z. Em chamadas avulsas, u pode ser a normal positiva
do plano escolhido pelo chamador. O contrato é explícito em ambos os casos.

Para ponto canônico p, inserção canônica q e transformação T:

```text
eixo físico inicial/final = eixo nominal inicial/final + du*u + dv*v
seção local inserida      = T(p) - T(q)
seção global             = eixo físico + u*x_local + v*y_local
```

Os dois extremos recebem o mesmo vetor. Comprimento, TopologyNode/Edge, run,
Span e Height não mudam. A assembly nunca grava esse vetor em OffsetX/Y.
Offsets e ajustes já existentes do membro são preservados pelo snapshot normal;
offsets manuais continuam no XY local do membro, após a transformação da seção.

`Center` ancora a origem do sistema da assembly no eixo nominal; não calcula
centroide resistente nem recentraliza pelo bounding box. `SymmetricPair` exige
dois eixos com translações opostas e ponto médio no eixo nominal. Não exige
perfis iguais: a simetria desta opção é dos eixos de inserção. `NearSide` e
`FarSide` estão reservados e são rejeitados nesta etapa; futuramente serão lados
de u local, nunca da câmera.

`ComponentSpacing` significa **distância entre os dois eixos de inserção**.
Somente com inserções centroidais isso é a distância entre os centroides
nominais dos perfis. Não é folga livre entre faces. A distância é conferida
contra as translações explícitas; não é uma segunda fonte de deslocamento.

## Transformação e reflexão

`SectionTransform(rotation_degrees, reflect_x)` representa `R(ângulo) @ mirrorX`:
a reflexão, se presente, ocorre primeiro. Determinante +1 significa rotação;
−1 significa reflexão verdadeira. São suportadas rotações gerais, incluindo
0/90/180/270°. A reflexão nunca é codificada como Rotation/Placement impróprio.

`transform_section` transforma pontos, centros de arcos, origem centroidal e
referências de inserção. Reflexão inverte sweep; em seguida reverte ordem e
sentido dos segmentos para conservar o winding de cada contorno. Furos são
preservados e os bounds são recalculados incluindo extremos dos arcos.

As referências são resolvidas **antes** da transformação. A função retorna
`(geometry, insertion_references)`: use as referências retornadas. Não chame o
resolver de inserção canônica na geometria transformada: o catálogo usa índices
de contorno para cantoneiras e stations escalares para U. As stations canônicas
não são propagadas como se fossem dimensões do perfil transformado.

O adaptador existente cria Face/extrusão; não existe um segundo pipeline de
sólidos. `AssemblySectionTransform` é JSON persistente opcional no componente:
ausência/string vazia = identidade para documentos anteriores. Quando presente,
participa de snapshot, assinatura e estado controlado, inclusive após restore.
Insertion continua sendo a referência original identificável do perfil.

## Identidade, ownership e regeneração

Identidade pura: `(assembly_key, component_key)`, contextualizada pelo owner.
Bindings persistem essa tupla sem ambiguidade, sem depender de Label, índice,
coordenadas, perfil ou ordem de Shape. `GenerationKey` codifica a tupla em JSON;
`AssemblyKey` e `ComponentKey` ficam disponíveis como metadados explícitos.

O adaptador `assembly.py` recebe um owner fornecido pelo chamador. Para uso
avulso técnico, basta um `App::FeaturePython`, como na fixture. Não se cria um
novo tipo paramétrico permanente MemberAssembly. O owner registra `AssemblyState`
e `AssemblyMembers` (LinkListHidden); cada StructuralMember aponta ao owner por
GenerationOwner. O registro hidden é organizacional, sem dependência reversa.

Na integração futura, um controlador de peça lógica/run pode servir de owner
e guardar a relação com StructuralTruss. **Esta etapa não expande automaticamente
RoleSpecs de Truss nem converte bindings legados**: a ponte pura resolve um run,
e o adaptador realiza os componentes. A adoção na edição de Treliça permanece
explícita para a etapa seguinte, preservando integralmente o fluxo atual.

`RegenerationPlan`/`RegenerationAction` são os mesmos contratos compartilhados
por C1/C2 e assemblies. Spacing, perfil, cor, insertion e transform com as mesmas
chaves atualizam os mesmos objetos. Alteração do conjunto de chaves ou do modo
é estrutural. O adapter exige `allow_structural=True` para criar/remover, após
preflight completo. `prepare_assembly` permite inspecionar o plano sem mutação.

Todo o lote é avaliado com `prepare_member` antes da transação. Aplicação usa
`apply_result`. Conflitos controlados, referências externas e remoção de ajustes
impedem a operação. Uma falha aborta a transação e invalida caches Python;
extensões/ajustes de componentes preservados não são apagados. O estado aceito
é atualizado apenas no lote aplicado. Atualização do owner é explícita nesta
etapa, não uma regeneração automática em callbacks.

Cada componente conserva geometria, material e propriedades individuais do
StructuralMember. Nenhuma inércia/seção resistente equivalente é calculada;
não se adicionou propriedade agregada de massa.

## Presets de prova e validação

- `single`: um componente A.
- `double_angle`: L esquerdo refletido, L direito canônico; quinas próximas ao
  centro e abas voltadas para fora, usando `L 40 x 4` real do catálogo existente.
- `double_channel`: U canônico abre +X; `outward` resulta em `][`, `inward` em
  `[]`, usando `U 4" x 8,04` real. Não há condicionais de família na transformação.
- `spaced_pair`: dois componentes com espaçamento e transforms explícitos;
  a prova visual usa bocas voltadas para dentro com afastamento maior.

Fixture: `tests/manual_freecad_assemblies_c3a.py`, chamar `run(output_directory)`
no Python do FreeCAD com a raiz do repositório no sys.path. Cria um documento
novo com os cinco casos, mais um par inclinado. Verifica sólidos, volumes,
inserção, bocas pela ocupação física do sólido, eixo/Placement, espaçamento,
identidades, alterações de perfil, extensão/ajuste, gate estrutural, rollback
injetado, Undo/Redo, reflexão de seção vazada com arcos e save/reopen/recompute.

Validação MCP realizada no FreeCAD 1.1.3: 85 verificações aprovadas. Artefato
local em `test-results/assemblies-c3a/AssembliesC3A.FCStd` e `report.json`.
Inspeção visual realizada em vista superior; aprovação de design cabe ao usuário.

Roteiro curto: abrir o FCStd, observar os cinco casos da esquerda para direita,
comparar `][` e `[]`, inspecionar as cantoneiras e o par inclinado; conferir
StartPoint/EndPoint e OffsetX/Y nos componentes. Alternar vista superior e
axonométrica. A cantoneira A mantém uma extensão/ajuste proposital da prova.

Testes focados: `python -m unittest tests.test_assemblies
tests.test_member_orientation tests.test_section_geometry_mode
tests.test_truss_core tests.test_truss_c2`. Suíte completa deliberadamente adiada
para o gate final C3. C3-B, Near/Far avançados, UI e todos os elementos C4+ não
foram implementados.
