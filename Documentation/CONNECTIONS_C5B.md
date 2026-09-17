# C5-B — ConnectionIntent e fitting de ligações

## Contrato

`ConnectionIntent` é um contrato puro, imutável e versionado, associado por
`TopologyNode.key` na configuração da treliça. Ele não cria objetos de documento.
O resolver obtém participantes lógicos por `PhysicalRun.key`, role e ponta
`Start`/`End`; banzos contínuos que atravessam o nó são participantes `Through` e
permanecem inteiros. Labels e ordem da árvore não participam da resolução.

`ConnectionForm` oferece:

- `GeometricOnly`: não acrescenta fitting de ligação; o ToChord explícito da
  C5-A continua válido.
- `Direct`: contato direto com políticas `Independent`, `BalancedMiter` e
  `Priority`.
- `Gusset`: fitting preliminar `GussetAware`, sem Shape de chapa.

`FasteningIntent` (`Unspecified`, `Welded`, `Bolted`, `Mixed`) registra somente a
intenção semântica. A C5-B não cria soldas, parafusos ou furos.

Configurações e documentos sem `connection_intents` continuam equivalentes a
`GeometricOnly`/`Unspecified` e não têm a geometria migrada. Novas treliças
também começam com esse fallback seguro; os defaults ToChord por role da C5-A
continuam independentes.

## Direct

`Independent` preserva os ajustes existentes. `BalancedMiter` aceita exatamente
duas webs de geometria equivalente no nó. O resolver cria um único plano pelo nó
nominal, derivado das direções locais que entram no encontro, e aplica o mesmo
`PlaneCut` aos dois participantes. Eixos nominais e TopologyNodes nunca mudam.
Geometria diferente, eixos degenerados/não coplanares ou mais de duas webs geram
diagnóstico e mantêm o encontro independente.

`Priority` mantém o participante prioritário e ajusta as demais webs contra sua
face física. Havendo duas ou mais webs, o banzo não concorre com elas: seu contato
continua controlado por ToChord. Para N webs, todas as N−1 secundárias recebem
fitting independente contra o primário, sem relações secundária–secundária.
`Automatic` escolhe o montante se houver exatamente um; caso contrário, prefere
a direção node→other_end mais à esquerda entre diagonais no frame local.
A stable key desempata. A árvore e os Labels não influenciam.
Priority usa o plano de suporte da seção física completa do primário, do lado
da secundária: uma face reentrante encontrada apenas pelo eixo pode deixar uma
aba da cantoneira atravessando a outra barra. Em assemblies, considera todos os
componentes do primário. ToChord mantém sua resolução C5-A independente.
`ParticipantA` e `ParticipantB` seguem a ordem estável dos participantes
configurados para compatibilidade. Novas seleções usam `priority_run_key`, campo
opcional com default vazio no contrato v1, e listam todas as webs por nomes
semânticos, como Diagonal esquerda e Montante.

O plano de contato é resolvido primeiro. Depois, o `physical_fit_gap` de cada
membro recua sua própria extremidade ao longo do eixo da barra. O plano
compartilhado não é deslocado para simular gap.

## GussetAware preliminar

`GussetFitSpec` mantém separadas quatro grandezas:

- `plate_thickness`: espessura transversal reservada para a futura chapa;
- `normal_clearance`: folga normal ao plano central da chapa;
- `axial_clearance`: recuo longitudinal preliminar de cada participante;
- `side`: `Center` nesta etapa.

Espessura e folga normal definem um slab centrado no plano local da ligação.
Cada seção física A/B é projetada na normal desse plano, considerando inserção,
rotação, espelhamento e posição efetiva. Não são convertidas em gap axial.
`axial_clearance` é aplicado depois do contato ToChord, quando presente, e o gap
C5-A é aplicado adicionalmente ao longo do eixo do membro.
Duplas cantoneiras e canais podem reservar uma chapa central quando o vão entre
componentes comporta espessura mais os dois clearances normais. `FaceA` e
`FaceB` permanecem no schema e retornam diagnóstico nesta etapa. Quando a seção
intercepta o slab reservado, há diagnóstico explícito: encurtar um eixo paralelo
ao plano não resolve a folga normal. Não há deslocamento transversal automático.
Os parâmetros pedidos e o recuo axial permanecem; deve-se ajustar posição ou
espaçamento para viabilizar a futura chapa. Isso também se aplica a um L simples.

## Composição e persistência

As diretivas de ConnectionIntent são compostas no `PhysicalFitPlan` versão 2,
com leitura compatível da versão 1. `additional_actions` retém as restrições
adicionais da mesma ponta: ToChord não é substituído pelo miter ou Priority.
O adapter usa a restrição axial mais interna para EffectiveStart/End e fornece
todas as restrições ao clipper planar existente. Cada plano conserva sua própria
estação axial; a Shape final é a interseção dos semiespaços. Isso não introduz
ElementCut, cope, notch ou um segundo sistema de recortes. Um
ajuste manual real bloqueia somente a ponta correspondente e produz mensagem
humana. Estado inválido preserva o último fitting de ligação válido quando ele
existe.

Assemblies recebem a mesma intenção no `PhysicalRun` lógico, propagada aos
componentes A/B. Interconnectors não são participantes e nunca recebem fitting
de nó; sua distribuição é recalculada no envelope físico fitted dos componentes.
Preview 3D e documento consomem os mesmos planos. A configuração por stable node
key participa do estado transacional da treliça, portanto save/reopen e Undo/Redo
seguem a disciplina já usada pelo `ControlledState`.

## Interface e limites

O editor da alma mostra, para o nó selecionado, tipo da ligação, intenção de
fixação, política direta, prioridade e parâmetros mínimos de gusset. As barras
participantes são destacadas e o preview 2D usa símbolos discretos para Direct e
Gusset.

Os textos de ConnectionForm são **Sem ajuste entre barras**, **Ligação direta**
e **Chapa de ligação**. BalancedMiter é omitido para cardinalidade ou
geometria incompatível: exatamente duas barras da alma equivalentes são
necessárias. DIAGONAL, VERTICAL e END_POST contam; chord Through não conta.
Esquerda/direita usam o frame local, nunca a câmera, e nomes repetidos recebem
numeração. Campos de folga normal e axial usam mm, sem clamp ou conversão oculta.
Os spin boxes concluem a digitação antes de atualizar o candidato.
O formulário oculta campos e seus rótulos sem significado: `Tipo de encontro`
somente em Ligação direta, Prioridade somente nessa política, e parâmetros de
chapa somente em Gusset. A ajuda fica na linha de status abaixo do desenho;
o canvas do editor não apresenta tooltip de ajuda sobreposto.

Na troca de preset/topologia, NodeKeys removidos são expurgados somente do
candidato. Remoção de membros e componente B aceita ajustes cuja proveniência
automática ainda corresponde aos campos atuais. Somente a normal permite
arredondamento absoluto de até 1e-12; modos, referências, gaps e offsets mantêm
comparação exata. A causa do falso bloqueio era o arredondamento de vetores
persistidos no FreeCAD, seguido do descarte do snapshot automático.
Snapshots antigos perdidos só são reconhecidos novamente quando os campos
atuais coincidem com a ação automática do plano persistido no próprio membro.
Essa classificação é somente leitura durante RegenerationPlan, sem escrever
no documento candidato. Slots antigos são mantidos quando há conflito manual,
para permitir Undo ou restauração explícita dos valores; uma ação automática
removida limpa sua ponta mesmo quando a outra ponta ainda tem ToChord.
Qualquer alteração
manual real, extensão ou referência manual continua protegida. Double→Single
retém A, limpa sua transformação de seção composta e resolve novamente o fitting.

### Correções da validação manual

A folga 200 que voltava a 20/0 não era conversão de unidade: a validação de espaço
da assembly cancelava todas as diretivas e restaurava a intenção anterior.
Com atualizações a cada tecla, esse estado anterior podia ser o valor parcial
digitado. Agora a geometria normal é diagnosticada separadamente, os parâmetros
não são restaurados silenciosamente e A/B recebem o mesmo setback lógico.

O gate específico está em `tests/manual_freecad_connections_c5b_blockers.py` e
produz `test-results/connections-c5b-blockers/C5BBlockers.FCStd` e `result.json`.

A C5-B não cria Shape de gusset, PreliminaryGusset, dimensionamento de chapa,
soldas, parafusos, furos, recortes, cope, notch, saddle cuts, verificações
normativas ou modelo analítico final. Esses elementos físicos e de fabricação
ficam para C6.


### Participantes passantes genéricos — fechamento C5-B

`ConnectionParticipant` distingue `EndParticipant` e `ThroughParticipant`.
Duas runs com o mesmo NodeKey, sentidos incidentes opostos (tolerância angular
1e-7), role e seção/composição compatíveis e frame de seção coerente formam
um participante passante. Pareamentos ambíguos e barras paralelas no mesmo
sentido permanecem separados. Runs e NodeKeys não são renomeados; a resolução
é transitória e não transfere ConnectionIntent por coordenadas.

K e Custom usam a mesma resolução. Automatic prefere o único passante elegível;
Priority aceita qualquer uma das duas chaves antigas como referência ao grupo.
Ambas as runs primárias permanecem sem corte entre si. Cada diagonal secundária
recebe seu plano contra o envelope completo das runs/componentes primários.
A UI mostra Montante (passante), banzos passantes ou Barra passante. Diagonais
no mesmo lado local recebem superior/inferior quando essas posições diferem.

Ligação direta oferece Meia-esquadria equilibrada (quando aplicável) e Prioridade.
Direct/Independent permanece serializável e executável; o editor só mostra
Sem ajuste adicional (legado) quando necessário para representar esse documento,
sem escrita ao selecionar o nó. O halo ciano de seleção é independente dos
símbolos Direct/Gusset e as mensagens permanecem abaixo do canvas.

Restaurar padrão restaura a topologia da alma; **não significa Limpar ligações**.
Intents de NodeKeys sobreviventes permanecem e os órfãos são descartados no
candidato. Seleção múltipla e aplicação de ligações em lote ficam como melhoria
futura de UX, fora desta rodada.

Snapshots antigos podem omitir PhysicalFitStatus e demais saídas opcionais de
fitting. A reaplicação usa valores compatíveis; a guarda de propriedades do
gerador mantém diagnóstico limpo. Manual > AutoFit permanece no core; não foi
adicionada UI de override manual de filhos.

Gate curto real: `tests/manual_freecad_connections_c5b_through.py` verifica
K/Custom com Automatic/Priority, validade OCC, interseção diagonal/montante,
snapshot legado, guarda de filho e halo/nomes/opções no editor. A evidência fica
em `test-results/connections-c5b-through/`. A aprovação visual e funcional final
continua pendente do usuário.

### Priority, Gusset e override manual

Com exatamente um passante elegível, Priority oferece somente Automática e esse
participante, também em Custom. Sem passante, opções e regras espaciais anteriores
permanecem. Chaves explícitas antigas continuam interpretadas pelo core; abrir
o editor não reescreve a configuração persistida.

Qualquer web passante impede BalancedMiter na UI e produz diagnóstico defensivo
no core. Preservar o passante e aplicar miter só às barras terminais fica como
política híbrida futura. Gusset recua somente participantes terminais e preserva
as runs do passante; a chapa física fica fora da C5-B.

LengthLimit e PlaneCut válidos da ferramenta Recortar/Ajustar Membro são
reconhecidos como override manual e não impedem reabrir o gerador. A validação
não exige `_last_generated_result`, cache Python ausente após restauração:
as referências persistentes e a geometria preparada são validadas. Referências
inválidas, ciclos e fontes pendentes de recompute continuam protegidos, assim
como a remoção estrutural de um membro com ajuste manual.

`tests/manual_freecad_connections_c5b_overrides.py` cobre os dois tipos de
ajuste, fixos e associativos a referência externa, pelo controlador oficial,
reabertura sem cache, Manual > AutoFit, conflito de remoção e save/reopen FCStd.
Resultados em `test-results/connections-c5b-overrides/`.

### Reabertura com override Associative

A abertura do Gerador é independente da resolução momentânea de um override
manual. A tentativa de reparar snapshots após Undo/Redo pode diagnosticar uma
referência Associative ausente, removida, inválida ou pendente, mas não impede a
construção do editor. O warning é mostrado na linha de mensagens do painel.

O ViewProvider da Treliça sempre consome o duplo clique. Se houver uma falha
fatal antes de o painel ser mostrado, ela é registrada no console sem devolver
o gesto ao editor padrão de Label. Não há interceptação global de mouse ou
teclado.

Fixed e Associative permanecem overrides manuais, fora do `ControlledState`
estrutural. O modo e o LinkSub válido persistem no FCStd. Quando o LinkSub fica
nulo ou seu objeto é apagado, o modo Associative e o último Shape válido são
preservados; a abertura não converte o ajuste para Fixed ou None. Manual >
AutoFit e a proteção contra remoção estrutural continuam válidos.

O gate real está em `tests/manual_freecad_truss_associative_reopen.py` e cobre
duplo clique, Fixed, Associative válido/nulo/apagado, save/reopen, diagnóstico,
Shape preservado, `ControlledState` e precedência manual. Evidências em
`test-results/truss-associative-reopen/`.

### Quebra angular do banzo e cumeeira

`ChordBreakParticipant` representa duas runs não colineares do mesmo papel de
banzo incidentes no mesmo NodeKey. É distinto de `ThroughParticipant`, conserva
os IDs das runs e não cria objeto na árvore. Seções/transformações incompatíveis
impedem a aplicação do candidato com diagnóstico, preservando o documento.

As branches recebem o mesmo plano bissetor pelo nó nominal, calculado no frame
local da treliça, independentemente de ConnectionIntent. O montante do ápice
recebe as restrições dos dois envelopes. Cada diagonal seleciona seu ramo pelo
lado topológico local; se a seção cortada ainda cruzar o envelope oposto, recebe
uma restrição adicional de proteção no PhysicalFitPlan v2. As restrições de
ligação entre webs continuam compostas com essas faces. Não há cope ou novo
ElementCut. Preview e documento consomem o mesmo candidato/plano.

### Centro do envelope nas cantoneiras

`envelope_center`, apresentado como **Centro do envelope**, é o centro da caixa
envolvente do contorno 2D da cantoneira. Transformações de componentes recalculam
essa caixa; a inserção é aplicada uma única vez antes da rotação longitudinal.
O default permanece Centroide e a opção não foi ampliada a outras famílias.

É útil para alinhar a geometria física de perfis assimétricos em uma work line
regular, especialmente em treliças. Não representa necessariamente o centroide
físico. Start/End, nós, runs e painéis permanecem nominais; somente a seção física
muda de posição. Uma futura camada analítica poderá representar a excentricidade
entre work line e eixo centroidal, fora do escopo da C5-B.

`tests/test_ridge_fitting.py` cobre resolução pura, composição, assemblies e
round-trip. `tests/manual_freecad_ridge_insertion.py` executa o gate OCC/Qt no
FreeCAD 1.1.3: cumeeira simétrica/assimétrica, Height/ApexPosition, plano inclinado,
interseções dos sólidos, preview compartilhado, troca de inserção, rotação,
transformação e save/reopen. Evidências em `test-results/ridge-insertion/`.
A aprovação visual e funcional final permanece com o usuário.
