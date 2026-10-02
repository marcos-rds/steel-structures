# Chapas Gusset — contrato técnico da C6

A ligação Gusset da Steel Structures 0.6.0 produz chapas preliminares a partir
das seções e dos participantes físicos do nó. Furos, soldas, parafusos e
verificação resistente não fazem parte da C6. A geometria usa os dados nominais
dos membros, incluindo suas transformações e componentes, e não os sólidos já
recortados pelo fitting.

## Criação, atualização e lifecycle

Uma intenção Gusset válida fornece um `GussetPlateSpec`, identificado pelo nó
e por sua chave estável. O pipeline calcula um `GussetOutline` puro; o adaptador
`trusses/gusset_freecad.py` extruda esse contorno na espessura e no plano
resolvidos. O mesmo resultado geométrico alimenta a prévia e a chapa persistente.

A aplicação/regeneração explícita da treliça cria ou atualiza uma
`StructuralGussetPlate` (`Part::FeaturePython`) por nó materializável, vinculada
à `StructuralTruss` por `ParentTruss` e `GeneratedGussetPlates`. A identidade
estável permite atualizar a chapa existente sem substituir seu nome ou rótulo.
A mudança para ligação direta e a remoção efetiva do nó eliminam as chapas
correspondentes durante essa aplicação explícita. Um placement inviável não
materializa uma chapa em uma posição inventada: a intenção e seu diagnóstico
podem permanecer sem sólido.

O recompute ordinário atualiza objetos existentes a partir do estado aceito;
não cria nem remove filhos implicitamente. A restauração do documento recupera
propriedades e vínculos, e a regeneração reconcilia os registros. Configurações
dos nós sobreviventes são preservadas por identidade semântica, não transferidas
para outro nó apenas porque suas coordenadas coincidem. Cancelamento, Undo/Redo
e salvar/fechar/reabrir seguem o lifecycle e as transações da treliça.

`Thickness`, `EdgeMargin`, `MemberOverlap`, `PlateArea` e `Volume` refletem o
resultado controlado da chapa. `StructuralGussetPlate` não é um membro, não cria
barra analítica ou interconnector e não calcula massa. Ajustes manuais dos
membros mantêm a precedência existente sobre fitting automático.

## Parâmetros e interface

No Editor de Topologia, selecionar um nó e o tipo de ligação Gusset disponibiliza
espessura, margem, sobreposição e folgas. A coluna direita de **Ligação do nó**
contém a **Vista transversal**, junto dos controles **Região da chapa** e
**Posição**. Não há um controle separado de “Contato no banzo” nesse fluxo.

- `MemberOverlap` define a extensão nominal de cobertura ao longo dos corredores
  físicos dos participantes. Perfis compostos contribuem com seus componentes
  transformados; não são substituídos por uma seção maciça fictícia.
- `EdgeMargin` participa das exigências de margem nos extremos da sobreposição
  e nas laterais aplicáveis. Não é uma inflação global uniforme em torno de
  toda a união dos perfis: contato com o banzo e limites terminais são restrições
  físicas, e a região proximal não recebe uma margem global adicional.
- Os valores padrão de margem e sobreposição são 25 mm e 150 mm. A espessura
  inicial padrão da treliça é 10 mm (`DefaultGussetThickness`); uma espessura
  confirmada passa a ser o padrão para novas Gussets daquela treliça, sem
  modificar as já configuradas.

A margem não impõe que toda aresta ou cap tenha comprimento igual ou superior
a `EdgeMargin`. Sua validade é verificada contra a cobertura e os suportes
físicos correspondentes. Uma solução não pode reduzir silenciosamente os
parâmetros configurados para obter um contorno menor.

## Regiões, posições e plano de attachment

`GussetAttachmentSlot` descreve os espaços transversais acessíveis;
`GussetAttachmentPlane` registra o placement resolvido, inclusive os limites
`plate_low` e `plate_high` ocupados pela espessura. A chave
`transverse_placement` seleciona um candidato físico estável; a chave vazia
solicita resolução automática.

O editor oferece somente as regiões e posições derivadas dos candidatos
geométricos disponíveis. Conforme o perfil, aparecem regiões externas,
internas, entre componentes ou associadas a faces/enrijecedores específicos.
“Lado A”, “Central”, “Lado B” e os demais rótulos são contextuais: não garantem
que a mesma lista exista para toda seção, orientação ou espessura.

Os slots distinguem `OUTER_HALFSPACE`, `OPEN_RECESS`, `BETWEEN_COMPONENTS`,
`ENCLOSED_VOID` e `UNSUPPORTED`. A disponibilidade considera a geometria real,
a direção de acesso dos participantes, a espessura inteira e possíveis colisões.
Tangência planejada é admitida; interseção positiva com material não é um
placement válido. SHS/RHS não oferecem o vazio fechado como alojamento para uma
chapa simples. DoubleAngle, DoubleChannel e SpacedPair preservam espaçamentos,
orientações e componentes individuais.

Em W/I, o recesso aberto entre as mesas pode fornecer posições junto à mesa A,
central e junto à mesa B, quando fisicamente admissíveis. A rotação da seção
altera o acesso: nas configurações de referência a 90° o recesso é acessível;
a 0° as mesas bloqueiam o acesso lateral dos participantes e permanecem os
apoios válidos na face da mesa. Isso não é uma regra universal baseada apenas
no ângulo. O resolvedor considera as transformações e os participantes reais.
A família I usa as faces inclinadas e os raios de sua seção, sem assumir mesas
paralelas iguais às de W. Nenhuma posição pode atravessar a alma.

**Automático e manual são geometricamente equivalentes quando resolvem o mesmo
candidato físico.** Ambos usam o mesmo attachment, as mesmas bandas efetivas,
o mesmo contorno e a mesma extrusão. A origem automática da seleção não ativa
um contorno compacto especial. Candidatos físicos distintos podem produzir
chapas distintas, mesmo que pertençam à mesma região genérica.

## Bandas C6-L: contato e extensão do contorno

A seleção transversal é distinta do lado de contato no plano da treliça.
`GussetChordContact` permanece no modelo persistente (`Auto`, `TrussInterior`,
`TrussExterior`), assim como os campos legados de modo e lado. Interior da treliça
significa o lado voltado aos participantes, não necessariamente uma cavidade
da seção. Esse sentido é calculado no referencial da treliça e pode variar entre
os dois ramos de uma cumeeira.

- `contact_band` representa a fronteira física de contato na faixa ocupada pela
  espessura inteira da chapa. Considera material real transformado, paredes,
  mesas inclinadas, lábios, raios e componentes. Não usa apenas eixo, linha média
  ou centro da chapa.
- `outline_band` governa a extensão do contorno junto ao banzo para o candidato
  escolhido. Pode diferir da banda de contato em placements externos/laterais;
  essa diferença não redefine a superfície usada no diagnóstico de contato.

O contorno usa `outline_band` do candidato resolvido, quando fornecida, também
no modo Automático. As janelas de contato e os resíduos continuam baseados nas
superfícies físicas compatíveis. Não se deve substituir uma banda pela outra
apenas para encurtar a chapa. A discretização de arcos usa erro de corda limitado
a 0,01 mm; o limite geométrico de contato usa a tolerância conservadora existente.

## Famílias de contorno aprovadas

A classificação usa participantes, direções, corredores, limites físicos e
condições do encontro. Os IDs Fxx abaixo identificam as famílias de referência;
nomes de objetos, NodeKeys e IDs de galeria não escolhem regras em produção.

| Família | Contrato |
|---|---|
| F01 — participante simples | Preserva o contorno estabelecido pelos suportes físicos. |
| F02 — dois participantes, como diagonal e montante | Laterais pelo ramo fisicamente dominante e fechamento pelos caps; transição direta quando aplicável, sem bridge histórica obrigatória. |
| F03 — duas diagonais em banzo contínuo | Laterais e fechamento no referencial do banzo, preservando cobertura e caps. |
| F04 — duas diagonais e montante | Mantém o leque aprovado; somente pontas geometricamente elegíveis recebem o truncamento local descrito abaixo. |
| F05 — cumeeira com duas diagonais | Dois contatos superiores, laterais pela bissetriz e fechamento inferior conforme a família aprovada. |
| F06 — cumeeira com duas diagonais e montante | Preserva o leque protegido e os contatos dos banzos. |
| F07 — encontro terminal | Respeita o limite terminal físico, as margens aplicáveis e o chanfro da família; o caso simples protegido mantém seu contorno. |
| F08 — alma passante, encontro K | Mantém o contorno atual aprovado; não aplica a alternativa histórica de outra forma. |
| F09 — leque com mais ramos | Mantém o contorno protegido do pipeline. |

O contorno é validado contra cobertura, margens, contato e limites rígidos.
`WEB_END_CAP` identifica terminações; participantes passantes não recebem cap.
`WEB_SECTOR_BRIDGE` só aparece quando a construção a exige, não em todo encontro
de duas barras. `TERMINAL_BOUNDARY` limita a chapa mesmo quando não constitui
uma aresta ativa. A quantidade de vértices depende da configuração física,
não de uma busca global por área mínima.

Se uma proposta de família não satisfaz suas exigências, o retorno ao contorno
original só é permitido quando ele também passa na validação. A recusa gera
diagnóstico; falhas não são ocultadas por um contorno arbitrário.

## F04: truncamento local condicional de 40%

A seleção aplica-se ao leque de duas diagonais e um montante terminais em banzo
contínuo, sem quebra de banzo nem limite terminal. Uma ponta é elegível quando
o ângulo da lateral junto ao banzo é menor que 60° e sua altura normal local H
é maior que `MemberOverlap`. A condição é geométrica, sem regras por NodeKey.

Para a ponta original P e o vértice superior S da lateral, o alvo é:

`h = 0,40 H` e `Q = P + 0,40 (S − P)`.

R é a projeção normal de Q sobre a linha de contato do banzo. Retira-se somente
o triângulo P–Q–R. O segmento Q–S conserva 60% da lateral original, com a mesma
inclinação e seu suporte; Q–R forma a nova face perpendicular local. As demais
laterais não são substituídas e o contorno não vira um retângulo.

Os 40% são uma preferência de forma aprovada, condicionada à cobertura, às
margens e aos limites físicos. Cada corte deve preservar a lateral superior,
remover exatamente o triângulo previsto e permanecer contido na chapa original.
A redução local do comprimento de contato na ponta é deliberada; não autoriza
perder as exigências de cobertura, margem ou ultrapassar o suporte do banzo.

Se o alvo violar essas exigências, a ponta original é mantida e o diagnóstico
registra a recusa e o limite físico. Não se reduz silenciosamente o percentual
para fazer o corte caber. Os cortes são avaliados localmente: uma ponta recusada
não exige desfazer outra ponta que foi aceita. Se nenhuma for aceita, toda a
geometria original permanece. Não se presume recusa obrigatória para uma família
de perfil como HP: a decisão depende da configuração física resolvida.

## Prévia transversal C6-Q e diagnósticos

A vista mostra a seção nominal física do banzo, seus componentes e vazios, e a
projeção transversal da chapa com espessura e posição efetivas. A escala é
uniforme e automática. Atualiza ao trocar nó, região, posição, espessura ou
configuração física, usando os resultados geométricos do controlador; não há
resolvedor independente no Qt nem criação de objetos persistentes para redesenhar.

Seções equivalentes podem compartilhar uma vista. Quando realmente distintas,
o seletor permite examiná-las separadamente, sem fingir que uma única seção
representa toda a ligação. Dados insuficientes, attachment nominal de fallback
ou contorno inválido produzem indicação de indisponibilidade.

A vista não tem tooltip. Os diagnósticos funcionais continuam abaixo do esquema
da treliça, limitados ao nó selecionado e sem duplicação. `CONTACT`, `GAP`,
`INTERFERENCE` e `NO_COMPATIBLE_SURFACE` descrevem os resíduos calculados pelo
resolvedor. Uma sobreposição apenas na projeção da preview não cria um novo
diagnóstico de colisão. O contato do participante governante não garante o
contato de todos os demais.

A seção apresentada precede os recortes de fitting; a chapa é uma projeção
transversal, não um corte longitudinalmente localizado do sólido. Detalhes de
apresentação e comando de teste Qt estão em
[GUSSET_TRANSVERSE_PREVIEW_C6Q.md](GUSSET_TRANSVERSE_PREVIEW_C6Q.md).

## Persistência e referências de validação

`ConnectionIntent` usa schema 4, `GussetPlateSpec` schema 3 e
`StructuralGussetPlate` schema 2. Os leitores mantêm a compatibilidade existente
com intenções anteriores; defaults e campos legados são normalizados pelo modelo.
O contrato é preservado por testes de serialização, reconciliação, lifecycle,
regeneração, Undo/Redo e reabertura.

As referências autocontidas estão em `tests/fixtures/gusset_round1.json` e
`tests/fixtures/gusset_tip_round2.json`: abrangem as 41 chapas de referência e
as correções aprovadas de ponta. Os testes de famílias, C6-L, W/I e C6-Q protegem
as restrições físicas e a equivalência automática/manual. Testes de sólidos e
persistência no FreeCAD complementam a suíte Python; não substituem a validação
visual da interface.
