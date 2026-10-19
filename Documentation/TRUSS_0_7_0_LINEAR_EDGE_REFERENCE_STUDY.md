# Estudo técnico — referência linear por aresta

Steel Structures 0.7.0 · `develop/0.7.0` · base publicada informada e HEAD local
confirmado: `29439b8d6e166b86a979a4633105890f1acb4065`.

**Etapa exclusivamente investigativa.** Nenhuma alteração em produção,
interface, testes permanentes, schema ou objetos de documentos pessoais.
Probes criaram documentos descartáveis em processos FreeCAD separados.

## 1. Decisão executiva

**GO para uma implementação incremental de captura de aresta em Snapshot**,
depois da avaliação deste relatório. **NO-GO para associação genérica a
qualquer Shape.** Vínculos futuros devem ser liberados apenas para fontes e
operações com identidade verificável, qualificadas por testes próprios.

O bloqueador da associação genérica foi reproduzido: reconstruir uma Shape
Python pode conservar o mesmo `Edge1`, a mesma quantidade de arestas e até o
mesmo nome mapeado, mas fazer a referência apontar para outra aresta física.
Portanto, existência de `PropertyLinkSub`, `ElementMap` ou token mapeado não
constitui garantia de identidade.

Primeiro candidato a vínculo qualificado: **lado de Retângulo Draft simples**,
identificado por sua semântica paramétrica local e validado contra a aresta
nativa. Isso deve ser um modo linear separado do Retângulo Draft/envelope
existente. Part::Box e perfis estruturais não ficam automaticamente qualificados
pelo fato de os exemplos simples deste estudo terem mantido seus índices.

## 2. Arquitetura atual: quatro contratos distintos

### 2.1 Rascunho temporário

[`trusses/edit_session.py`](../freecad/SteelStructures/trusses/edit_session.py)
guarda configuração profundamente copiada, baseline, configuração persistida
observada, `AppliedState` capturado, última realização e candidato revisionado.
É estado de edição, sem Qt ou transação própria. Um candidato válido só vale
para sua revisão. Checkpoints do Editor também são cópias profundas.

O controlador resolve a referência antes de construir o candidato. A captura
inválida não deve modificar configuração, widgets, baseline, owner ou candidato.
Esc apenas encerra a aquisição. O desenho Draft suspende/reconstrói a projeção
Qt, preservando sessão e controlador; essa infraestrutura não precisa de outro
gerenciador para receber arestas.

### 2.2 Solicitação persistida no documento

[`truss.py`](../freecad/SteelStructures/truss.py), `config_from_object()`
(linhas 58–77) e `set_config()` (140–164), combinam:

| Dado | Papel atual |
|---|---|
| `C2Configuration` | JSON da solicitação, incluindo `reference_mode`, `reference_linked`, Name da fonte e `reference_edge` |
| `ReferenceMode`, `ReferenceLinked` | Espelhos persistentes; modos existentes TwoPoints, DraftLine, DraftRectangle e ThreePoints |
| `ReferenceSource` | `App::PropertyLinkSub`, dependência nativa oculta, preenchida somente quando vinculado |
| `ReferenceContainers` | `App::PropertyLinkList` para dependências dos placements de contêineres |
| `Placement`, `Span`, alturas e `RoleSpecs` | Dados paramétricos usados para reconstruir a solicitação |

**Lacuna para a extensão:** a leitura atual usa apenas `ReferenceSource[0].Name`;
ignora os subnomes em `[1]`. `reference_edge` continua vindo do JSON. Na escrita,
o LinkSub é reconstruído a partir desse JSON. Assim, um subelemento remapeado
pelo FreeCAD poderia ser ignorado na resolução e posteriormente sobrescrito.
O comportamento é suficiente para os contratos específicos existentes, mas
não deve ser transplantado para arestas genéricas.

### 2.3 Último estado realmente realizado

`AppliedState` contém o candidato realizado, grafo, itens e bindings, em JSON
determinístico. É atualizado após geração/aplicação bem-sucedida. Não é a
autoridade para escolher a fonte corrente, nem deve ser usado como fallback
para uma referência vinculada perdida.

`execute()` (482–541) resolve, valida e prepara antes de alterar as peças.
Falha de referência gera `NeedsRegeneration=True`, `GenerationState=Conflict`
e mensagem; não limpa a última geometria válida. Mudança estrutural normalmente
fica Pending até confirmação no Gerador. Atualizações compatíveis usam o batch
existente, com backups e rollback. Não prometer regeneração estrutural automática
para qualquer alteração da fonte.

### 2.4 Captura e alinhamento

[`member_axis_source.py`](../freecad/SteelStructures/member_axis_source.py)
reconhece Linha Draft por tipo `Part::FeaturePython`, proxy Wire do Draft,
Start/End/Shape e segmento único válido. Start/End já incorporam Placement
próprio do Draft; o resolver acrescenta apenas o placement acumulado dos pais.
Esse contrato específico não deve ser generalizado para sólidos.

[`truss_reference.py`](../freecad/SteelStructures/truss_reference.py) resolve
Linha Draft e Retângulo Draft simples. No retângulo, o lado escolhido determina
também altura, normal para o interior e envelope Parallel. Uma aresta desse
mesmo objeto, usada apenas como eixo, precisa de semântica nova.

O contrato de entrada geométrica é `start`, `end`, `span` e `plane_normal`.
`source_geometry()` projeta a normal persistida perpendicularmente ao eixo;
o Plano de Trabalho fornece fallback na captura, não em recomputes arbitrários.
`input_reference_frame()`, `reference_frame()` e `support_alignment*` mantêm o
alinhamento físico de Banzo inferior/superior. Não é necessário alterar esses
cálculos, topologias ou massa para receber um segmento diferente.

## 3. APIs nativas e evidências

Instalação medida: FreeCAD **1.1.4**, build 20260928, commit
`4fd3bf320d9566a27e60069fc8387448aaa3a094`. Os resultados são desta instalação,
não uma promessa sobre todas as versões do FreeCAD ou produtores de Shape.

### 3.1 Seleção e hierarquia

`getSelectionEx(docName, resolve, single)` admite 0 sem resolução, 1 com
subelemento indexado e 2 com nome mapeado. `addObserver()` também aceita esse
modo. Os padrões são 1; por isso o observador atual recebe a folha da seleção.
Essa API é documentada pelo próprio código tagged 1.1.4 de
[Selection.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Gui/Selection/Selection.cpp#L2329).

O probe confirmou para uma Box em dois App::Part transformados:

| Consulta | Objeto/subnome | Coordenadas retornadas |
|---|---|---|
| `getSelectionEx('', 0)` | Parent / `Inner.Box.Edge1` | Globais, com ancestrais |
| `getSelectionEx('', 1)` | Box / `Edge1` | Placement próprio, sem ancestrais |
| `getSelectionEx('', 2)` | Box / `Edge1` nesse caso sem mapa | Também sem ancestrais |
| Observer resolve=0 | Part / `Box.Edge9` | Preserva a ocorrência/caminho no evento |
| Observer resolve=1 ou 2 | Box / `Edge9` | Resolve para a folha |

Consequência: a futura aquisição deve conservar raiz e caminho da ocorrência
selecionada. Não basta trocar a validação do observador atual por
`subname.startswith('Edge')`: caminhos hierárquicos e nomes mapeados não têm
necessariamente esse formato.

Duas arestas de um objeto aparecem em um SelectionEx com dois
`SubElementNames`. `single=True` não substitui a validação de cardinalidade do
subelemento. Um clique no objeto inteiro, Face ou Vertex não autoriza Edge1.

### 3.2 Coordenadas e Placement

`getSubObject()` transforma ao longo do caminho fornecido; não percorre
automaticamente ancestrais ausentes desse caminho. O probe mediu:

```text
Box.getSubObject('Edge1'):
  (10, -10, 30) → (10, 20, 30)
Parent.getSubObject('Inner.Box.Edge1'):
  (1010, 2073.660254, 3020.980762) → (980, 2073.660254, 3020.980762)
```

O segundo resultado coincide com a transformação global calculada. Não
aplicar novamente Placement próprio ou global sobre uma Shape já transformada.

`getSubObject(..., retType=2)` fornece objeto/matriz/geometria; `Part.getShape()`
aceita `needSubElement=True` e pode resolver links no `retType=2`.
`getGlobalPlacementOf()` é outra API contextual disponível; sua exposição está
no [GeoFeaturePyImp.cpp 1.1.4](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/GeoFeaturePyImp.cpp#L55).
Seu resultado não foi qualificado para todas as variantes de Body/array.

Um App::Link não expôs `getGlobalPlacement()` nesta instalação. O probe com
escala 2 e rotação retornou corretamente comprimento 200 mm para uma aresta
original de 100 mm pelo caminho da instância. `LinkTransform=False` e True
produziram extremos diferentes. Desembrulhar o link para seu objeto alvo
perderia essa ocorrência. Links e arrays devem ficar fora da primeira entrega;
nunca ignorar escala ou transformar matriz geral em Placement rígido.

Conservar a raiz visual não significa automaticamente usá-la como dependência
persistente: um App::Part pode conter também o próprio owner. A escolha entre
folha + dependências dos contêineres e raiz/caminho deve passar pelo DAG nativo
e pelas guardas existentes. Em contextos não qualificados, oferecer Snapshot
ou recusar o vínculo; não remover uma guarda de ciclo para aceitar a seleção.

### 3.3 Vínculos e nomes topológicos

`PropertyLinkSub` único já comporta objeto e caminho para uma única aresta.
`PropertyLinkSubList` guarda múltiplas fontes/subelementos, sem benefício para
esta referência única. Ambos criam dependências; LinkSub normal recusou fonte
externa ao documento no probe. Um Link interno que aponte para outro documento
exige validação adicional do alvo, não apenas do documento da instância.

`resolveSubElement()` retorna objeto, nome mapeado e nome indexado. A assinatura
está em [DocumentObjectPyImp.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/DocumentObjectPyImp.cpp#L925).
`getElementMappedName()`, `getElementIndexedName()`, `ElementMapSize` e histórico
estão expostos por
[ComplexGeoDataPyImp.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/ComplexGeoDataPyImp.cpp#L354).
Servem à resolução e ao diagnóstico; não certificam a qualidade do produtor.

O núcleo mantém nomes auxiliares em ShadowSub e pode atualizar referências;
também possui caminhos de recuperação geométrica. Isso não substitui a
verificação de identidade exigida pela ferramenta. Evidência no
[PropertyLinks.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/PropertyLinks.cpp#L412).

### 3.4 Experimentos de identidade

| Caso | Observação nativa | Implicação |
|---|---|---|
| Draft Rectangle, Length/Height alterados | Edge2 foi de `(100,0,0)→(100,50,0)` para `(200,0,0)→(200,70,0)`; mapa vazio | Funcionou nesse contrato simples; falta qualificação de identidade para vínculo linear |
| Part::Box dimensional + Placement | Edge9 acompanhou comprimento/rotação/translação; mapa vazio | Estabilidade do caso não é garantia de reconstrução geral |
| Perfil U da Steel Structures | Edge1 acompanhou comprimento 1000→1500 e rotação; 36 arestas, mapa vazio | Mudança de perfil/família/recorte ainda não qualificada |
| Part::Compound de duas Boxes | Ao trocar Links `[A,B]→[B,A]`, LinkSub mudou Edge1→Edge13 e conservou extremos | Remapeamento nativo pode funcionar quando há proveniência coerente |
| Remover A do Compound | LinkSub virou `?Edge13`; Shape resolvida nula | Diagnosticar perda; não recuperar Edge1 |
| Holder da referência perdida | `State=['Up-to-date']` | State do objeto não valida LinkSub |
| Restaurar A | Native LinkSub recuperou Edge13 | Recuperação é possível, mas precisa passar novamente por validação |
| Reconstruir Shape Python com arestas reordenadas | Índice, quantidade e token mapeado ficaram iguais; a aresta física mudou | Contraexemplo concreto à associação genérica |

No último caso foram criadas duas linhas, uma em Y=0 e outra em Y=100, e
atribuídos compounds com ordem invertida a um Part::Feature. Antes/depois:

```text
referência: Edge1
token: ;Edge1;:H,E;:H:5,E.Edge1
ElementMapSize: 6
número de arestas: 2
extremos antes:  (0,0,0)   → (10,0,0)
extremos depois: (0,100,0) → (10,100,0)
```

O produtor reconstruiu os mesmos identificadores para significados diferentes.
Isso não é resolvido conferindo apenas o token ou a quantidade de arestas.
A chave desse experimento no JSON chama-se `unmapped_reorder`, mas a medição
mostrou mapa automático com seis entradas: o nome da chave não significa que
o experimento final estava sem mapeamento.

### 3.5 Exclusão, Undo/Redo, cópia e persistência

Excluir a fonte Rectangle zerou o LinkSub; Undo restaurou objeto/subnome e
extremos, Redo zerou de novo. Uma cópia superficial do holder manteve a fonte
externa compartilhada. Save/close/reopen preservou referências do Rectangle,
Compound remapeado, Box e perfil, com tolerância numérica de coordenadas.

O Document.xml salvo registrou, por exemplo:

```xml
<Sub value="Edge13" shadow=";Edge1;:Hdd9,E.Edge13" />
```

Esse formato foi observado, não proposto como serialização manual da bancada.
O FreeCAD deve continuar cuidando de seus dados internos. O teste comprova os
fixtures examinados; não certifica renomeação por importação, documentos
cruzados ou todas as operações PartDesign.

## 4. Fontes e critérios de aceitação

### 4.1 Avaliação por fonte

| Fonte | Captura Snapshot proposta | Vínculo proposto inicialmente |
|---|---|---|
| Linha Draft atual | Preservar implementação | Preservar implementação aprovada |
| Lado explícito de Draft Rectangle simples | GO, sem herdar altura/envelope | Condicionado a identidade semântica do lado e testes adversariais |
| Aresta de Part::Box / Part::Feature direto | GO se validada | Não liberar genericamente |
| Perfil Steel Structures independente | GO se validado | Não liberar até qualificar seção, orientação e reconstruções |
| Perfil de outra origem / Shape importada | GO se segmento válido | Não assumir qualidade de mapa/proxy desconhecido |
| Objeto PartDesign / Body aninhado | Avaliar caminho global em etapa própria | Fora da primeira entrega |
| App::Link, arrays, ocorrências e escalas | Adiar até qualificação contextual | Fora da primeira entrega |
| Objeto de outro documento / alvo externo | Rejeitar inicialmente | Sem propriedade de vínculo externo nova |
| Própria treliça, seus membros ou derivados | Rejeitar por dependência | Rejeitar |

Uma Shape válida não significa necessariamente fonte compatível. Para objetos
diretos e App::Part simples, os resultados medidos permitem iniciar Snapshot;
para contextos ainda não qualificados, recusar claramente em vez de usar
coordenadas locais como globais.

### 4.2 Validação objetiva

1. Documento ativo igual ao da sessão; raiz, folha e cadeia de referência
   pertencentes ao contexto permitido.
2. Uma única seleção de uma aresta explicitamente indicada. Pode haver caminho
   hierárquico ou nome mapeado; resolver primeiro, conferir `ShapeType='Edge'`.
3. Shape/subshape não nula, válida e não degenerada.
4. Curva geométrica linear nativa, não arco, círculo ou spline. Não inferir
   linearidade apenas por dois vértices.
5. Dois extremos físicos distintos, finitos, com comprimento maior que a
   tolerância geométrica existente. Não usar precisão de exibição de duas casas
   para a decisão ou armazenamento.
6. Segmento limitado: conferir extremos topológicos, intervalo e precisão OCC.
   `Part.Precision.isInfinite()` está disponível. O probe encontrou uma reta
   infinita válida com **zero vértices**, parâmetros ±2e100 e comprimento 4e100;
   todos esses números passam por `math.isfinite`. Esse teste sozinho não basta.
7. Extremos em coordenadas globais da ocorrência correta, sem dupla aplicação
   de Placement. Comprimento global coerente com os extremos.
8. Rejeitar dependência de owner, filhos gerados, derivados e contêineres.
   O probe real confirmou ciclo em owner, membro gerado e derivado desse membro;
   uma Box externa independente passou. Conferir também Gussets/interconectores
   quando implementado; não confiar apenas no TypeId ou no nome.
9. Para vínculo, validar também o provedor/identidade qualificados; para
   Snapshot, resolver uma vez e não criar dependência futura.

A lista de vértices e a direção paramétrica nem sempre possuem a mesma ordem.
No Link escalado, os extremos foram iguais como conjunto, mas em ordem oposta.
A implementação deve definir a orientação P0/P1; não ordenar globalmente por
X/Y/Z, pois rotações poderiam inverter os lados da treliça. Snapshot guarda a
ordem capturada; vínculo qualificado precisa de orientação semântica validada.

### 4.3 Mensagens propostas

| Situação | Orientação curta |
|---|---|
| Captura iniciada | Clique em uma linha ou aresta reta. Esc cancela a seleção. |
| Objeto inteiro ou Face | Selecione explicitamente uma aresta. |
| Mais de uma aresta | Selecione uma única aresta. |
| Curva | A referência deve ser um segmento reto. |
| Vertex | Selecione uma aresta, não um vértice. |
| Nula, degenerada ou ilimitada | A aresta não define um segmento finito válido. |
| Contexto não suportado | Esta ocorrência ainda não é suportada como referência. |
| Fonte removida | A fonte vinculada foi removida. Selecione outra referência. |
| Identidade perdida/ambígua | A identidade da aresta não pôde ser confirmada. Selecione novamente. |
| Ciclo | A referência depende da própria treliça. Escolha uma fonte independente. |

Seleção inválida altera apenas a orientação/diagnóstico da captura. Não apagar
fonte anterior, trocar modo, aplicar, mover peças ou reconstruir o rascunho.

## 5. Alternativas e política recomendada

| Alternativa | Benefício | Risco / decisão |
|---|---|---|
| Guardar somente Name + EdgeN | Implementação curta | NO-GO para vínculo: troca silenciosa reproduzida |
| Usar LinkSub e confiar em mapa/token | Reutiliza TNP nativo | Insuficiente isoladamente; contraexemplo reproduzido |
| Buscar aresta parecida por posição/comprimento/direção | Pode recuperar alguns casos | NO-GO: simetrias, duplicatas e mudanças legítimas são ambíguas |
| Rastreador próprio de história topológica | Controle potencial | Não justificado para esta evolução localizada |
| Snapshot genérico | Confiável para geometria capturada, sem dependência | Recomendado como primeira entrega |
| LinkSub + provedor semântico qualificado | Reutiliza núcleo e verifica intenção | Recomendado para vínculos progressivos, com escopo explícito |

Não usar `hashCode`, `Tag`, quantidade de arestas, igualdade de bbox ou token
opaco como prova de identidade. Assinaturas geométricas podem detectar mudança
ou orientar diagnóstico, mas não decidir automaticamente qual é a substituta.
Bloquear toda alteração de Shape e permitir apenas Placement seria uma política
restrita possível, porém não atende a atualização dimensional desejada e exige
um contrato próprio de detecção. Não é a recomendação inicial.

Para qualificar o Rectangle simples, identificar um dos quatro lados locais
orientados pelos cantos `(0,0)`, `(L,0)`, `(L,H)`, `(0,H)`. Guardar a intenção
desse lado e validar que o LinkSub atual ainda resolve esse lado lógico após
Length/Height/Placement. Não substituir silenciosamente o lado se a referência
nativa divergir. Isso é um contrato limitado do produtor Rectangle, não um
rastreador topológico genérico. Fillet, chamfer e subdivisão continuam recusados.

Para um operador nativo composto, a qualificação precisa incluir sua cadeia de
produtores. O êxito do Compound de Boxes não autoriza Compound de Shapes Python
arbitrárias. Perfis exigem identidade e orientação próprias antes de aceitar
mudança de seção/família, composições, recortes ou reconstrução completa.

### Referência vinculada inválida

Resolver LinkSub e política de identidade **antes** de preparar geração física.
Se raiz, subelemento, identidade ou contexto falhar: marcar conflito, manter
último AppliedState/peças e impedir nova aplicação até seleção válida. Não
voltar ao EdgeN do JSON, não zerar treliça e não tratar dado anterior como atual.
Reutilizar os estados de massa pendente/indisponível existentes, sem exibir o
peso do realizado como peso de um candidato inválido.

Undo pode restaurar uma fonte; isso autoriza nova validação, não apagar o
conflito de sessão já disparado por edição externa. A sessão deve continuar
exigindo reabertura quando seu contrato atual assim determina.

Em Snapshot, exclusão ou mudança posterior da fonte não invalida os pontos
capturados. O indicador não pode associar uma nova entidade só porque recebeu
o mesmo Name. Se não houver origem viva verificável, mostrar a condição de
geometria capturada sem apresentar uma fonte inexistente como vinculada.

## 6. Persistência, compatibilidade e versão

### 6.1 Contrato novo separado

Proposta interna: `LinearEdge`, mantendo todos os tokens existentes.
Não reutilizar `DraftRectangle` para uma aresta simples, nem converter modos
antigos ao abrir documentos. Para vínculo novo, **objeto e subnome em
ReferenceSource são autoridade**. JSON contém o descritor serializável da
intenção/política e os dados capturados; AppliedState continua último realizado.

Descritor conceitual, ainda não implementado:

```text
reference_mode: LinearEdge
reference_contract_version: 1
reference_linked: bool
reference_source: Name para apresentação/descrição; não autoridade vinculada
reference_edge: caminho serializável coerente com a referência nativa
reference_policy: Snapshot | QualifiedNative
reference_provider: identificação versionada do provedor qualificado
reference_identity: intenção semântica mínima, incluindo orientação
```

Não persistir referências Python/Qt, ID de sessão ou endereço de objeto.
No rascunho ainda não aplicado não existe LinkSub no owner: o descritor precisa
guardar raiz/caminho e identidade para resolver/validar antes da primeira
aplicação, sem criar um objeto temporário no documento. Ao carregar owner já
aplicado, derivar o descritor da referência nativa atual e validar a intenção.

Não criar PropertyLinkSubList nem segunda propriedade concorrente de ligação.
`ReferenceContainers` permanece necessário; novos caminhos podem exigir
dependências de contêiner/ocorrência adicionais, a qualificar por etapa.
Leitura sem resolução para abrir/diagnosticar referência perdida não deve
transformar perda em referência Snapshot ou recuperar JSON silenciosamente.

`set_config()` e rollback devem conservar o subnome nativo/remapeado aprovado.
Descritor e política participam de comparação persistida, snapshot da sessão,
checkpoint e conflitos. P0/P1 iguais não provam que a identidade não mudou.

### 6.2 Proposta de compatibilidade de schema

Hoje `SCHEMA_VERSION=5`; `encode_state()` emite 2/3/4/5 conforme capacidades
físicas. Apenas acrescentar um enum não garante segurança em leitores antigos:
o núcleo puro não rejeita globalmente todo `reference_mode` desconhecido, e a
UI antiga pode carregar parcialmente um Snapshot novo.

**Recomendação para avaliação antes do código: schema 6 nos estados que usam
LinearEdge, inclusive Snapshot.** Manter leitura explícita de schemas 1–5 e
não elevar estados legados apenas por abrir/salvar. A implementação deverá
decidir/documentar a política de downgrade; código antigo não editará a nova
capacidade com segurança, devendo recusá-la por versão e preservar o realizado.

Armadilhas concretas a cobrir:

- Trocar apenas `SCHEMA_VERSION` para 6 faria os testes `(1,2,3,4,SCHEMA_VERSION)`
  de decode/execute/restore **excluírem o schema 5**. Usar conjunto explícito
  de versões suportadas.
- Não fazer todas as ligações atuais passarem a exigir 6 só porque o encoder
  usa `SCHEMA_VERSION if connected`. Calcular mínimo por capacidades: ligações
  existentes exigem 5; nova referência exige 6; combinações usam o máximo.
- Não alterar `GENERATOR_VERSION` sem necessidade comprovada.
- Legados sem `reference_surface` conservam seu eixo aceito; não converter
  automaticamente para face externa física.

Cópia independente deve continuar duplicando agregado/bindings, mantendo a
fonte externa compartilhada quando esse é o vínculo original. Não compartilhar
membros/Gussets entre owners nem copiar a fonte só para resolver a referência.
Save/reopen, importação/cópia e Name remapeado precisam usar o LinkSub nativo,
não lookup textual como autoridade. Os probes desta etapa mediram holder
simples e não certificaram todas as variantes de cópia de treliça com LinearEdge.

## 7. Interface proposta, sem alterações nesta etapa

É viável um único grupo visual **Linha ou aresta**, com Selecionar existente e
Desenhar nova nas posições e dimensões atuais. Desenhar nova continua criando
exclusivamente Linha Draft nativa e usando `DraftLine` internamente.

O agrupamento visual precisa mapear explicitamente `DraftLine` e `LinearEdge`;
não substituir seus IDs persistentes pelo texto do combo. Hoje
`get_config()` força Edge1 fora de DraftRectangle e copia `currentData()`
diretamente; essas regras terão de ser especializadas para o novo grupo.
Não criar duas opções indistinguíveis com o mesmo rótulo.

Indicador: `Line001`, `Rectangle001 · Edge2`, `Perfil001 · Edge5`, sempre com
Label atual verificado. Para tokens mapeados/hierárquicos, exibir forma legível
e colocar detalhes no tooltip; não expor uma string interna extensa como texto
principal. Erro de vínculo substitui apenas o estado contextual necessário.

Para fonte somente Snapshot, Manter vínculo não pode prometer acompanhamento:
desabilitar com explicação ou exigir escolha explícita por Snapshot. Se estava
marcado, recusar a seleção vinculada e explicar a alternativa; não desmarcar
silenciosamente. A seleção inválida conserva rascunho e referência anteriores.

Dois pontos, Três pontos, Retângulo Draft/envelope, Banzo de referência, layout
com `removeWidget()`, Editor, botões/checkpoints, massa e prévias permanecem.

## 8. Alterações futuras por arquivo

Esta tabela é proposta, não diff desta investigação.

| Arquivo | Mudança futura localizada |
|---|---|
| `truss_reference.py` | Despacho LinearEdge, resolução/validação, preservando contratos Draft atuais |
| Novo `truss_linear_reference.py`, se a separação justificar | Adaptador FreeCAD de raiz/caminho, segmento global e provedores qualificados; sem duplicar sessão |
| `truss.py` | Enum aditivo, autoridade LinkSub no modo novo, escrita/rollback/restauração/cópia compatíveis |
| `trusses/models.py`, `serialization.py` | Capacidade/schema novo explicitamente negociado, preservando 1–5 |
| `truss_reference_selection.py` | Observação contextual resolve=0, um subelemento explícito, identidade validada e limpeza existente |
| `truss_controller.py` | Ampliar aquisição/resolução e guardas de fonte/caminho/ciclo; não outro fluxo Apply |
| `truss_task_panel.py` | Grupo visual agregado, preservar tipo interno e caminho, indicador/vínculo/diagnóstico; remover coerção Edge1 para modo novo |
| `truss_editor_checkpoint.py` | Comparar identidade/política/subelemento além da geometria resolvida |
| `trusses/edit_session.py` | Preferencialmente sem mudança estrutural; descritor JSON participa dos mecanismos existentes |
| `trusses/realization.py` | Validar/aceitar contrato da capacidade nova se necessário; nenhuma fórmula geométrica nova |
| `truss_draft_reference.py`, `truss_task_widgets.py` | Nenhuma mudança de desenho/layout prevista |
| Alinhamento, massa, perfis, Gussets, StructuralPlate, Draft global | Nenhuma alteração prevista |
| `tests/`, runners | Testes permanentes apenas na fase de implementação; probes deste estudo são evidências temporárias |

Não generalizar `member_axis_source.py`: seu contrato é Draft. O helper
`linear_reference_from_link()` de ajustes representa reta infinita, não este
segmento finito, e não deve ser reutilizado sem respeitar essa diferença.

## 9. Etapas incrementais e critérios de avanço

1. **Fechar o contrato de persistência e matriz de versões**, com fixtures 1–5
   e proposta 6. Nenhuma capacidade nova deve vazar em estado antigo silencioso.
2. **Snapshot de aresta explícita**, começando por Rectangle, Part::Box,
   Part::Feature e StructuralMember diretos, mais App::Part simples já medido.
   Validar coordenadas e rejeições; não alterar associação Draft existente.
   Sem linha auxiliar e sem owner antecipado.
3. **Vínculo qualificado de Rectangle simples**, com lado/orientação semânticos,
   dimensões, transformação, identidade divergente, perda e reabertura. Só
   liberar checkbox depois desses testes.
4. **Qualificar produtores adicionais individualmente**, começando por um caso
   nativo controlado. Part::Box, perfis, booleanas e composições exigem seus
   próprios contratos; tokens mapeados não concedem capacidade automaticamente.
5. **Ocorrências complexas**: App::Link, escala/espelho, arrays, Body e cadeias
   externas apenas após probes e testes próprios. Sem suporte cruzado entre
   documentos na primeira implementação.

Revisar após cada etapa. Não desenvolver um rastreador geral para contornar
fontes não qualificadas. Arestas arbitrárias continuam úteis em Snapshot.

## 10. Matriz de testes para a implementação

P = Python puro/stubs; N = FreeCAD 1.1.4 real; M = interação humana/visual.
Stubs não certificam OCC, TNP, transformações nativas nem lifecycle real.

| Grupo | Casos principais | Ambiente | Critério |
|---|---|---|---|
| Captura | botão antes/depois da seleção, uma Edge, multi-Edge, objeto inteiro, Face/Vertex | P + N + M | Uma referência explícita; inválido conserva rascunho |
| Geometria | linha/arc/circle/spline, zero comprimento, nula, infinita, tolerância | P para critérios; N para Shape | Somente segmento físico reto e finito |
| Contexto | raiz/folha, App::Part duplo, rotação, translação, escala de instância | N | Extremos globais, nenhuma transformação dupla |
| Orientação | ordem dos vértices vs parâmetros, eixo invertido, rotação cruzando eixos globais | P + N | P0/P1 preservam intenção; banzos/alturas não invertem silenciosamente |
| Fonte | Rectangle, Box, perfil próprio e externo, Shape importada | N | Capacidade declarada por fonte, sem fallback |
| Snapshot | fonte movida/excluída/recriada com mesmo Name | P + N | P0/P1 capturados independentes; nenhuma reassociação textual |
| Vínculo qualificado | dimensões, Placement, recompute repetido, lado lógico | N | Identidade e orientação confirmadas a cada resolução |
| Identidade nativa | Compound Links reordenado; Edge1→Edge13 | N | LinkSub atualizado é autoridade; peças acompanham somente se identidade válida |
| Contraexemplo obrigatório | Raw reconstruído, token/map/count iguais, aresta física diferente | N | Fonte não qualificada nunca ganha vínculo automático |
| Perda/ambiguidade | `?Edge`, Shape nula, lados simétricos/duplicados, topologia alterada | P + N | Diagnóstico e última geometria preservada |
| Exclusão/Undo/Redo | antes/depois de Aplicar, fonte removida/restaurada, conflito externo | N | Sem ressuscitar objeto errado ou apagar bloqueio externo |
| Persistência | save/close/reopen de casos válidos e perdidos; tokens e intenção | N | Vínculo/diagnóstico corretos sem JSON antigo como fallback |
| Legado | schemas 1–5, TwoPoints/ThreePoints, DraftLine Snapshot/vinculado, DraftRectangle/envelope | P + N | Mesmo resultado e modo; abrir/cancelar sem migração geométrica |
| Schema novo | capacidade 6 sozinha/com Gussets/compostos/recortes; leitor antigo | P + N | Suporte explícito e recusa segura no downgrade |
| Cópia | cópia independente e fonte compartilhada; importação com Name remapeado | N | Agregado independente, LinkSub coerente |
| Dependências | owner, membros, conectores, Gussets, derivados/contêineres, links | P + N | Ciclo recusado antes de mutação |
| Sessão | profundo, candidato, baseline, AppliedState, conflitos/checkpoints | P + N | Mesma sessão/controller/owner; sem segundo manager |
| Operações | Apply repetido/no-op, OK/Cancelar/X do Editor, TaskPanel Cancel | P + N + M | Sem transação extra por captura, aplicação/rollback existentes |
| Quantitativos/alinhamento | Paralela/Duas Águas, inclinação, banzo superior/inferior, massa | P + N | Entrada segmentar não altera fórmulas/legado |
| Lifecycle | Esc/repetição, seleção↔desenho, comando sucessor, Task View, documento | P + N + M | Observer/atalho/Coin limpos; nenhum painel residual |
| Visual | Classic, FreeCAD Dark, OpenDark; largura estreita e DPI | N + M | Mesmo layout aprovado, indicador/status legível |

Começar pelos módulos focados e probes permanentes da capacidade nova, executar
`check_project.py`/diff-check e, no fechamento de implementação, ampliar para
suíte completa e gates integrados proporcionais. Não houve suíte completa nesta
investigação, porque nenhum código funcional foi alterado.

## 11. Evidências executadas, limitações e preservação

Diretório temporário, fora da implementação e ignorado por Git:

```text
test-results/truss-edge-reference-study/20261017_181532/
```

| Probe temporário | Conteúdo | Resultado final |
|---|---|---|
| `probe_api.py` | Docstrings/API, LinkSub/List, SelectionEx, App::Part aninhado e Link | Concluído, exit 0 |
| `probe_topology.py` | Dimensões, perfil U, remapeamento/perda, reconstrução, Undo/Redo, cópia e save/reopen | Concluído, exit 0 |
| `probe_boundaries.py` | Observers 0/1/2, multi-seleção, curvas/infinitas, escala/LinkTransform, documento e ciclos | Concluído, exit 0 |

`api-result.json`, `topology-result.json`, `boundaries-result.json`, logs e
FCStd descartável preservam os dados; `verification.json` verifica 30 observações
desses resultados. São experimentos exploratórios, não aprovação de uma
funcionalidade que ainda não existe. Nenhuma interação manual da UI proposta
ou teste de temas novos foi alegado.

`python scripts/check_project.py` e `git diff --check` foram aprovados. O novo
relatório também passou na checagem de whitespace contra `NUL` (exit 1 por
diff de arquivo novo, sem diagnóstico de whitespace). Nenhuma suíte completa
foi executada nesta etapa.

Foram preservadas também as tentativas iniciais: a API de Link não tinha
`getGlobalPlacement()`; esse resultado passou a ser explicitamente registrado.
A primeira fixture de ciclos usou dois painéis, abaixo do mínimo existente de
quatro, gerou ValueError e o processo isolado terminou pelo timeout de 120 s
porque o documento ficou aberto. Somente o probe foi corrigido para quatro
painéis e fechamento garantido em finally. Isso não foi falha nativa nem
regressão da bancada. Os logs finais não contêm traceback Qt, `already deleted`
ou access violation. Não foi criada correção especulativa para Draft.

As verificações de preservação registram hashes/status antes e depois. Nenhum
arquivo preexistente foi modificado ou removido. A única adição fora dos
resultados ignorados é este relatório. HEAD/branch e índice permanecem
inalterados; sem add, commit, push, merge, tag ou release. Estudos Gusset e
experimentos StructuralPlate permanecem intactos.

## 12. GO/NO-GO para a próxima rodada

- **GO técnico condicionado para iniciar a etapa Snapshot**, depois da
  avaliação deste relatório e definição do contrato/schema. A captura nativa
  e as coordenadas possuem caminho viável, sem linha auxiliar.
- **GO condicionado para estudar/implementar vínculo de Rectangle simples**,
  com identidade semântica e testes adversariais como requisito de entrega.
- **NO-GO para liberar vínculo genérico a sólidos/perfis/Shapes arbitrários**
  ou usar apenas EdgeN/mapa/token como garantia. O contraexemplo é concreto.
- **Sem implementação iniciada nesta etapa.** A revisão técnica adicional foi
  exclusivamente de leitura. A decisão de escopo da próxima implementação é
  separada deste estudo; nenhum arquivo de produção ou teste permanente mudou.
