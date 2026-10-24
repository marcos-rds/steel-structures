# Meia-esquadria automática entre dois membros — investigação

Data: 23/10/2026. Branch `develop/0.7.0`.
HEAD inspecionado: `2ef3b49d3e02fd111a8133240519a3ffc9068ca0`.
Publicação informada pelo usuário; não houve consulta ao remoto nesta rodada.

## Recomendação e decisão

**GO para iniciar um MVP de comando próprio, bilateral e fixo**, com dois
membros retos independentes, eixos coplanares concorrentes, encontro nas pontas
ou por prolongamento, gap zero e seções geometricamente compatíveis. Reutilizar
PlaneCut, avaliação destacada e preview da Etapa 1. Dois resultados aparecem
juntos; um OK confirma os dois e um Undo restaura os dois.

**Não iniciar ainda uma ligação associativa genérica ou suporte irrestrito a
filhos de treliça.** O esquema atual conserva cortes locais independentes;
não conserva uma relação entre dois membros. Nas treliças existe ainda uma
questão específica de proveniência entre override manual e AutoFit.

Não foi implementada funcionalidade, interface ou propriedade. Esta rodada
adiciona somente este relatório fora de `test-results/`. Sem alterações de
versão, catálogo, changelog ou publicação. Não houve `git add`, commit, push,
merge, tag ou release. A revisão independente confirmou a recomendação e
suas restrições. A aprovação da Etapa 1 informada pelo usuário foi preservada.

## 1. Mecanismos existentes e reaproveitamento

Foram consultados [a auditoria original](MEMBER_ADJUSTMENT_TECHNICAL_AUDIT.md),
[a Etapa 1](MEMBER_ADJUSTMENT_STAGE1.md) e [seu fechamento e complemento](MEMBER_ADJUSTMENT_STAGE1_CLOSURE.md).
As descrições antigas de ausência de preview/risco de confirmação são
históricas; `2ef3b49` já contém a correção, inclusive assinatura por suporte
geométrico global, sem depender apenas de hash.

Os caminhos da tabela pertencem a `freecad/SteelStructures/`:

| Entrada real | Reuso e limite |
| --- | --- |
| `connections/resolver.py:142`, `chord_joint_plane()` | Já calcula normal por diferença das direções interiores nos encontros de banzos. Quebra de banzo exige equivalência; fechamento terminal tem regras próprias. Depende de participantes topológicos, não recebe dois objetos arbitrários |
| `connections/resolver.py:197`, `_balanced()` | BalancedMiter: duas barras terminais equivalentes da alma, coplanares, sem participante passante da alma; emite duas diretivas PlaneCut com origem/normal comuns |
| `trusses/fitting.py:62`, `_chord_miter_plan()`; `:85`, `_connection_action()` | Convertem origem/normal para frame global e offsets por ponta; alimentam o fitting existente |
| `fitting/models.py`, `resolver.py`, `freecad_adapter.py` | Contratos puros `GeometryReference`, `FitAction`, `PhysicalFitPlan`; conversão para ajustes Fixed, precedência e planos compostos. Não reutilizar a classificação AutoFit para fingir uma ligação genérica |
| `member_adjustment_geometry.py:48`, `:67`, `:92` | Eixo nominal, interseção eixo/plano e ponto de menor distância entre retas. Falta verificar distância entre AMBAS as retas; a projeção atual para Edge aceita retas reversas por contrato |
| `member_plane_cut.py:168`, `:270` | Conversão global/local, precursor e corte planar finito. É o único algoritmo de recorte a utilizar |
| `member.py:572–717` | Slots Start/End, Fixed/Associative, extrusão/corte, Placement, massa e composição de ajustes. Não modificar o eixo nominal para simular corte |
| `member_batch.py:44`, `:74` | Snapshot sem Shape anterior e `prepare_member()` com executor real. Preserva a ponta oposta e, quando solicitado, Placement completo do membro independente |
| `interactive/member_adjustment_controller.py:253`, `:298`, `:321` | Preparação, verificação após recompute e transação segura. Hoje cada `apply()` confirma somente UM membro |
| `interactive/member_adjustment_preview.py` | Uma instância por membro: Shape candidata real, branch Coin transiente, máscara do original e limpeza. Não cria objeto de documento |
| `interactive/member_adjustment_task_panel.py`; `commands.py:382`; `init_gui.py:102` | Captura, reavaliação, timer, lifecycle e exclusão mútua com outras tarefas: padrões a compartilhar, sem duplicar o painel unilateral inteiro |

Não chamar `_balanced()` com participantes fictícios nem criar treliça auxiliar.
A regra de participantes/roles é específica da treliça. Extrair apenas a
pequena operação vetorial comum para um helper puro, se isso permitir reuso
sem mudar as políticas atuais; encontro dos eixos e admissibilidade do par
são responsabilidade do novo resolvedor. Isso não é outro algoritmo de corte.

## 2. Definição geométrica proposta

### Encontro dos eixos e pontas

Usar eixos nominais e Placement atuais, após recompute válido; não inferir
eixo pela bounding box da Shape cortada. Para cada membro, `P + t d`, com
`d` unitário no sentido Start→End e comprimento nominal `L`.

Calcular os dois pontos de menor distância das retas suporte. Com
`w=P_B-P_A`, `c=d_A·d_B` e `D=1-c²`:

```text
t = (w·d_A - c (w·d_B)) / D
s = (c (w·d_A) - w·d_B) / D
Q_A = P_A + t d_A
Q_B = P_B + s d_B
```

Rejeitar paralelismo/condicionamento insuficiente antes da divisão. Exigir
`|Q_A-Q_B| ≤ εL`; só então usar `J=(Q_A+Q_B)/2`. Não aproximar eixos reversos
por um ponto médio e chamá-los concorrentes. O plano dos dois eixos tem normal
`k=unit(d_A×d_B)`; pode estar em XY, vertical ou inclinado no espaço.

Para o primeiro MVP, J deve estar na ponta selecionada ou no seu raio exterior:
**Start: estação ≤ εL; End: estação ≥ L−εL**. Isso admite pontas coincidentes,
eixos que se encontram por prolongamento e seções ainda sem contato. Não
admite cortar automaticamente o meio de uma barra passante. Se J estiver
estritamente dentro de qualquer segmento, rejeitar como fora do escopo inicial
(T, cruzamento ou aparo interior que exige política adicional).

Essa restrição é deliberadamente conservadora: pequenas sobras nominais que
atravessam J também ficam fora inicialmente. Uma extensão posterior poderá
admitir aparo terminal explícito com limite de alcance; não usar uma distância
oculta arbitrária para distinguir T de encontro de pontas.

### Bissetriz e material preservado

Definir `r_A` e `r_B` como vetores unitários de J para o interior retido de
cada membro — por exemplo, em direção à ponta nominal oposta à escolhida.
Não usar diretamente Start→End para ambos: o sinal depende da ponta.

```text
n = unit(r_A - r_B)
plano: n·(X-J) = 0
n·r_A > 0 e n·r_B < 0       (ou ambos os sinais invertidos)
```

O plano contém `k` e a direção `r_A+r_B`: é o plano separador da bissetriz do
encontro. Aos 90°, os cortes são equilibrados em 45°; o mesmo cálculo vale
para outros ângulos não degenerados. A outra bissetriz, com normal
`unit(r_A+r_B)`, deixa os dois interiores no mesmo lado e pode gerar
interpenetração. Não oferecê-la como alternativa equivalente.

Os semiespaços são os que contêm os respectivos pontos interiores retidos.
O clipper existente já escolhe o lado pela extremidade oposta. Validar que
essas escolhas são opostas no plano comum. Trocar `n` por `−n` não muda o
corte; um botão que apenas inverta a normal não resolve escolha errada de ponta.
Para trocar o material retido, escolher outra ponta e resolver novamente,
recusando a combinação se ela não satisfizer as regras.

Exigir estabilidade de interseção e de `|n·d_i|`, e que a extensão axial da
tampa completa não alcance a ponta oposta. Reutilizar `plane_axial_span()`
para estimar isso antes de OCC. Ângulos quase paralelos, seção grande em
membro curto ou plano quase paralelo ao eixo podem exigir precursores enormes:
bloquear com diagnóstico; não corrigir o ângulo ou truncar geometria silenciosamente.

### Plano comum não significa contato completo

Seções de larguras, alturas, paredes, roll, inserção ou offsets diferentes
podem gerar duas Shapes válidas sem suas regiões de material coincidirem no
plano. Isso também ocorre com perfis iguais girados de modo incompatível.
Tubos exigem preservar os vazios; um envelope retangular não comprova contato.

Proposta para um MVP inequívoco de meia-esquadria:

1. Cada candidata deve ser não nula, válida, com volume finito positivo e
   **exatamente um sólido**. A avaliação atual não impõe sozinha esse último critério.
2. Obter a união das regiões reais de fechamento no plano comum, incluindo
   alma/abas e contornos internos; não escolher a maior Face nem guardar FaceN.
3. Exigir área de contato positiva e tampas coincidentes: áreas de
   `cap_A \ cap_B` e `cap_B \ cap_A` abaixo da tolerância, com verificação dos
   contornos. Áreas iguais, isoladamente, não bastam.
4. Exigir semiespaços opostos e volume comum dos dois sólidos abaixo da
   tolerância. Tampas iguais, isoladamente, também não bastam.

As operações OCC de interseção/área servem à **validação**, não recortam A pelo
volume de B. Uma implementação pode medir as tampas pelas faces coplanares
ou por interseção com uma Face plana transiente dimensionada pelos bounds;
as provas usaram a segunda opção. Não criar plano persistente para isso.

Centralizar tolerâncias dimensionais e angulares, com limites absolutos e
escala do par. Comprimento, área e volume precisam de tolerâncias com unidades
corretas. Valores para implementar devem ser calibrados nos testes de escalas
pequenas/grandes; esta prova não certifica um limiar numérico de produção.
Falha OCC na medição significa candidato não aprovável, nunca contato presumido.

Larguras diferentes podem admitir um plano assimétrico em situações particulares,
mas isso exige outra política; alturas, vazios e contornos distintos podem
impedir o fechamento completo. Não deslocar a bissetriz, girar seção, alterar
inserção ou subtrair sólidos como fallback automático. Contato parcial poderá
ser uma operação futura explicitamente identificada, não um passe silencioso
de meia-esquadria completa. O resultado não dimensiona solda ou ligação estrutural.

## 3. MVP e diagnósticos

Escopo recomendado: dois `StructuralMemberProxy` distintos, no mesmo documento,
`GenerationOwner=None`, eixo `AxisDefinitionMode="Independent"`, seções simples
(sem assemblies/transformações de composição), mesmo perfil e mesmo modo de
geometria, plano comum e gap zero. Essa igualdade é filtro de escopo; todas
as verificações geométricas anteriores continuam obrigatórias.

| Situação | Política inicial / diagnóstico |
| --- | --- |
| Encontro a 90° ou ângulo arbitrário bem condicionado | Admitir quando J está nas pontas/raios exteriores e o par passa na geometria real |
| Plano dos eixos inclinado globalmente | Admitir; coplanar não significa horizontal |
| W `i_section/parallel_flange`; U simples e Ue `cold_formed_channel`; RHS e SHS | Famílias propostas para a primeira matriz, com perfis iguais e fechamento coincidente |
| Orientação de seção | Não impor roll zero. Exigir compatibilidade por tampas; rotações espelhadas podem funcionar, rotações numericamente iguais podem falhar |
| Detailed / Simplified | Iniciar a certificação com Detailed, como a prova. Habilitar Simplified somente após casos dedicados no gate; não misturar modos no primeiro contrato |
| U laminado `channel_section/tapered_flange` | Gerador existente, mas diferente de U simples; habilitação após prova nativa própria. Não foi ensaiado nesta rodada |
| Perfis diferentes, inclusive paredes diferentes | Rejeitar no primeiro MVP: “Seções diferentes não estão incluídas nesta operação equilibrada” |
| Mesmo perfil, tampas incompatíveis por giro/inserção/offset | Rejeitar: “As seções não fecham no plano comum; revise orientação e inserção” |
| Retas reversas / afastadas | Rejeitar: “Os eixos não se encontram no mesmo plano”; informar distância residual |
| Paralelos / colineares | Rejeitar: encontro/bissetriz não unívocos; alinhamento de topo reto é outra operação |
| T, cruzamento, J interior ao segmento | Rejeitar: “O encontro não está entre as extremidades; peça passante não é suportada” |
| Ângulo degenerado ou tampa alcançando a ponta oposta | Rejeitar com diagnóstico de condicionamento/comprimento disponível |
| Zero contato, contato parcial, interpenetração ou múltiplos sólidos | Bloquear OK, mostrando a causa; não aceitar apenas porque cada Shape é válida |
| AxisSource Linked externo | Adiar no primeiro incremento; exige teste específico de origem movida e esclarecimento de que o par é fixo |
| Um ou dois filhos de treliças, mesma ou diferentes owners | Bloquear inicialmente e orientar ao editor de ligações da treliça quando aplicável |
| Documentos diferentes, mesmo objeto duas vezes, objeto inválido/excluído | Bloquear sem transação |

Orientação comprovada nas provas: `x_local=k`, `y_local=r_i×k`, `z_local=r_i`,
com ambos os inícios voltados a J. Nesse frame, W/RHS/SHS/U simples/Ue iguais
fecharam com roll 0/0. W a 60° fechou com 23°/−23°, mas não com 23°/23°.
Isso especifica um exemplo reprodutível, **não os valores de Rotation exibidos
na interface para qualquer Placement**, nem autorização para girar os membros.
O teste das tampas decide a orientação efetiva, inclusive para Start/End mistos.

### Ajustes anteriores

Preservar a ponta oposta e seus parâmetros, extensões, perfil, inserção, offsets,
eixo nominal e catálogo. Se ela inviabilizar uma das candidatas, bloquear o par.
Na ponta escolhida, Fixed ou Associative existente exige substituição explícita
no painel, com resumo de A/B; não apagar um vínculo sem informar. Confirmar
apenas os slots escolhidos. Se ambos já representam o resultado pedido, tratar
como “sem alteração necessária”, sem criar Undo vazio.

Rejeitar dependência preexistente entre os dois membros, inclusive transitiva
ou pela ponta oposta: preparar A contra a Shape antiga de B e depois alterar B
pode invalidar a avaliação desacoplada de A. Não basta testar ciclos novos.
Recomputar fontes antes da avaliação; não aceitar estados Touched/Invalid ou
expressões que substituam os campos de ajuste selecionados.

## 4. Provas pequenas no FreeCAD 1.1.4

Evidências em [`test-results/member_miter_joint_investigation/`](../test-results/member_miter_joint_investigation/).
Foram feitos **três processos isolados**: tentativa inicial interrompida ao
buscar um identificador incorreto de família no script de prova, uma rodada
de 11 fixtures e a rodada final de 15 fixtures. A primeira não avaliou
geometria; seu erro está preservado. Nenhum código do pacote foi alterado.

```powershell
python test-results/member_miter_joint_investigation/run_probe.py
```

O runner usa `FreeCAD_1.1.4.../bin/freecad.exe`, perfil próprio, documentos novos,
manifesto SHA-256 das fontes e captura de logs. A rodada final está em
`attempt3/result.json`, manifesto, logs e `fixed-pair.FCStd`; `probe.py` contém
somente fixtures dirigidas, não um comando ou resolvedor genérico de meia-esquadria.
As duas rodadas geométricas concluíram sem erros nos filtros nativos.

As quinze fixtures finais geraram duas candidatas válidas, cada uma com um
sólido, pelo **prepare_member → execute → PlaneCut existente**. Os originais,
objetos do documento e Undo permaneceram intactos durante a avaliação destacada.
Dez pares fecharam completamente sem volume comum; cinco demonstram rejeições:

| Prova | Medida relevante / conclusão |
| --- | --- |
| SHS 15,87×15,87×0,75 a 90°, 60° e 135° | Tampas coincidentes; volumes comuns zero |
| Mesmo SHS a 60°, plano inteiro rotacionado 37° em torno de (1,2,3) | Resultado equivalente em plano global inclinado |
| Mesmo SHS a 90°, normal invertida | Mesmo resultado; confirmação da invariância de sinal |
| RHS 30×20×0,75, W 150×13, U 50×25×1,20 e Ue 50×25×10×1,20 a 90° | Contato completo nas orientações descritas acima; vazios/contornos preservados |
| W a 60°, rolls 23°/−23° | Área de contato 3148,52 mm², tampas coincidentes |
| W a 60°, rolls 23°/23° | Cada tampa tem 3148,52 mm², mas só 184,91956 mm² são comuns: rejeitar |
| U simples, abertura oposta (roll 0°/180°) | Tampas ≈163,01051 mm², contato ≈39,87706 mm²: rejeitar |
| RHS 30×20×0,75 versus 30×20×0,9 | Áreas residuais ≈1,20183 e 20,11359 mm²: espessura diferente não fecha |
| RHS 30×20×0,75 versus 35×15×0,75 | Áreas de tampa e volumes iguais; contato só ≈3,18198 mm²: comparar áreas/volumes não basta |
| SHS com normal da outra bissetriz `r_A+r_B` | Tampas coincidentes, porém interpenetração ≈179,27179 mm³: rejeitar |

As pontas nominais estavam a 50 mm de J: o precursor existente prolongou as
seções para o encontro. No SHS a 90°, os dois conjuntos Fixed foram gravados
em uma transação: **um Undo restaurou ambos, Redo preservou ambos os eixos
nominais e FCStd reabriu com os dois slots Fixed**. Após mover somente A em
100 mm no eixo global X, os planos ficaram separados em ≈70,71068 mm na normal.
Isso comprova a persistência dos cortes locais e a ausência de vínculo de par.
Não comprova uma interface futura, rollback de todas as falhas bilaterais ou
comportamento de famílias/rolls não ensaiados.

Também executado:
`python -B -m unittest tests.test_connections_c5b tests.test_member_plane_cut tests.test_fitting_c5a`:
**48 testes OK**, sem skips. `python scripts/check_project.py` e
`git diff --check`: aprovados. **Suíte completa não executada**, conforme solicitado.

## 5. Arquitetura e persistência

### Comparação de alternativas

| Alternativa | Custo / consequência | Decisão |
| --- | --- | --- |
| Acrescentar modalidade bilateral ao painel unilateral | Mistura dois alvos, pontas, rascunhos, substituição de slots e confirmação de par com o fluxo Face/Edge de uma ponta; risco de regressão desnecessário |
| Comando próprio, backend compartilhado | Isola seleção/estado do par e reutiliza cálculos, candidatos, verificação e preview | **Recomendado** |
| Novo objeto Joint já no MVP | Dá identidade editável ao encontro, mas exige dependências, propriedade/schema, restauração e política de ownership | Adiar |
| Duas chamadas consecutivas a `controller.apply()` | Duas transações; A pode confirmar antes de B falhar | **Rejeitado** |
| Faces persistentes auxiliares / referências cruzadas | Adiciona objetos/ciclos e dependência de FaceN sem necessidade | **Rejeitado** |

### Representação fixa sem propriedades novas

Para cada ponta escolhida, usar os seis campos atuais:
`AdjustmentMode=Fixed`, `AdjustmentGeometryMode=PlaneCut`,
`AdjustmentReference=None`, `AdjustmentGap=0`, offset relativo à ponta nominal
e normal local do mesmo plano global. Se a estação de J é `t` desde Start,
offset Start=`t`, offset End=`L−t`. Converter a normal pelo Placement efetivo
do membro, não somente por seu roll; a translação do início efetivo não altera
a normal. A interseção eixo/plano fornece a estação que reconstrói esse plano.

Não há propriedade de par, ID de encontro, plano global persistente ou novo
SchemaVersion. Após salvar/reabrir, continuam dois ajustes Fixed editáveis
individualmente em Recortar/Ajustar. Reexecutar Meia-esquadria com o par resolve
um novo encontro; não é reedição de um Joint persistente.

| Edição posterior | Contrato do MVP fixo |
| --- | --- |
| Mover/girar um membro | Seu corte acompanha o próprio referencial; o parceiro não muda; contato pode desaparecer |
| Alongar/alterar eixo | Offset continua relativo à ponta nominal correspondente; normal permanece local; pode deixar de haver plano comum |
| Alterar perfil/inserção/offset | Recompute usa o novo contorno com o ajuste local; compatibilidade do par não é revalidada automaticamente |
| Mover ambos por mesmo movimento rígido | Dois cortes podem continuar coerentes, mas não existe grupo/constraint que imponha isso |
| Apagar um participante | O outro mantém seu corte fixo; não há reparo automático |

### Confirmação bilateral atômica

Preparar as duas propostas e candidatas antes de qualquer mutação. Extrair
somente os helpers pequenos necessários para criar candidata por valores e
verificar resultado, hoje internos ao controlador unilateral; não construir
Faces falsas para satisfazer `validate()` nem reescrever esse controlador.
O MVP deve deixar esses helpers com contrato compartilhado e testado.

No OK: resolver novamente o par, validar tampas/semiespaços e fontes atuais,
abrir **uma** transação, gravar os dois slots, recomputar, verificar os dois
resultados e a compatibilidade bilateral definitiva; só então confirmar.
Qualquer divergência/Shape antiga/estado Invalid/status inadequado ou falha
OCC aborta toda a transação. Testar também B falhando depois de A recomputado.
Não aplicar Shapes de preview como atalhos que evitem o execute definitivo.

### Associatividade: decisão separada

Referenciar A pela Face cortada de B e B pela Face de A cria ciclo, já rejeitado
por `member_adjustment_reference.would_create_adjustment_cycle()`. Um Joint que
lê A/B completos e é, ao mesmo tempo, referência dos dois recria esse ciclo.

Uma evolução realmente associativa precisa de entradas nominais independentes:

```text
eixos/fontes nominais upstream → regra/plano do encontro → membros cortados
```

Outra alternativa é um owner de conjunto, que separe entradas de A/B e saídas,
como faz a treliça. Ambas exigem decidir onde se edita eixo/perfil, como tratar
exclusão/reversão dos eixos, slots ocupados, ownership e migração FCStd.
Não resolver isso com observer que escreva propriedades fora de transação,
JSON de nomes soltos, `PropertyLinkHidden` para esconder ciclo ou cache Python
sem persistência. Para duas peças fixas, esse subsistema não é necessário.

### Um ou dois membros de treliças

A infraestrutura já aceita ajustes manuais nos filhos e conserva Shape anterior
quando uma geração falha; isso não prova que uma nova operação de par pode
ser aplicada irrestritamente. Pontos concretos:

- `fitting/freecad_adapter.py:29–71` recupera estado automático de
  PhysicalFitPlan e classifica override manual por diferença dos campos/referências.
  Se o novo Fixed coincide com AutoFit/ConnectionIntent, pode continuar automático.
- `:74–104`, `composed_plane_cuts()`, e `member.py:701` podem usar planos
  automáticos adicionais para aquele slot. Coincidência numérica não significa
  que só o plano do novo par governa o sólido.
- Limpar apenas `PhysicalFitAutoState` não resolve: o estado é recuperável do
  plano persistido. Não alterar planos do pai nem propriedades controladas por fora.
- `truss.py:225–245` protege alterações controladas e remoção de filhos com
  overrides; `member_batch.py:265` também verifica dependências associativas
  da própria treliça e fontes pendentes.

Portanto, o primeiro comando deve recusar **ambos** os casos: um filho + um
independente e dois filhos, inclusive de owners diferentes. A extensão posterior
precisa testar proveniência por ponta, overrides idênticos ao auto, planos
compostos, edição/regeneração do pai, mudança de topologia, Undo e FCStd.
Se a política exigir que “feito pelo comando” seja um override mesmo quando
idêntico, avaliar proveniência persistente explícita nessa etapa. O enum
`FitSource.UserOverride` existe, mas a UI genérica não grava, por si, um contrato
de ownership do par. Dentro de um nó de treliça conhecido, priorizar o editor
BalancedMiter existente em vez de criar ligação paralela que dispute o pai.

## 6. Proposta de interface

Novo comando público proposto: `SteelStructures_MiterMembers`, texto
**Meia-esquadria entre membros**, próximo a Recortar/Ajustar no menu/toolbar.
Sem dois modos de confirmação dentro do painel atual.

1. Pré-seleção de exatamente dois membros abre o painel preenchido. Com zero
   ou um, capturar A e B por clique no objeto; recusar duplicatas/documento
   distinto/excesso de seleção com mensagem clara.
2. Identificar encontro J e pontas admissíveis. Mostrar A/B, perfil, ponta,
   ângulo e prolongamento calculado; destaque transiente da ponta retida.
   Não exigir seleção de Face nem plano preparado pelo usuário.
3. Mostrar simultaneamente os dois resultados e um indicador transiente do
   plano comum. Duas instâncias do preview existente, pertencentes à mesma
   sessão; se a segunda falhar, limpar ambas e restaurar os dois originais.
4. Alterar ponta A/B ou substituir um alvo recalcula o par. A ordem A/B não
   define peça principal: a operação é simétrica. Inverter só a normal não
   deve aparecer como ação que promete mudar o resultado.
5. Exibir **“Cortes fixos: alterações posteriores dos membros não atualizam o
   encontro”**. Não oferecer checkbox de associatividade sem implementação.
   Gap zero é contrato inicial; sem campo de folga que tenha semântica ambígua.
6. OK habilitado apenas com par completo válido e eventual substituição de
   ajustes explicitamente aceita. Um OK, uma transação, um Undo. Cancelar/Esc,
   fechamento/exclusão/troca de documento limpam os dois previews e callbacks.

Reutilizar cores/legibilidade da Etapa 1; identificar A/B no painel e, se
necessário, por marcadores/cores transientes sem alterar aparência persistente.
Polling observa ambos os membros, slots e suportes geométricos globais, não
apenas hashes. Invalidar o preview inteiro se qualquer entrada ficar obsoleta.
Atualizações não devem confirmar um membro enquanto o outro está inválido.

### Referências de fluxo, sem copiar interface

O Advance Steel documenta cortes nas duas pontas, eixos de inserção coplanares
e regra editável por objeto de conexão. Isso confirma a distinção entre
processamento geométrico e persistência da regra; não obriga criar Joint no
MVP. [Documentação oficial Autodesk 2026](https://help.autodesk.com/cloudhelp/2026/ENU/AdvSteel-3Dmodeling/files/GUID-E25BA7C6-4F9D-4990-AABA-4B363F3AB379.htm).

O Tekla distingue Mitre, ajuste por prioridade, peça passante e sobreposição,
com escolha separada de conexão/solda. A lição adotada aqui é manter políticas
distintas e participantes explícitos. A ordem principal/secundário desse
produto não precisa ser importada para nossa operação simétrica.
[Documentação oficial Trimble](https://support.tekla.com/help/tekla-structures/not-version-specific/fitbeamsandcolumns).

As fontes não garantem contato perfeito de quaisquer seções nem um único Undo
bilateral. Esses critérios são decisões próprias sustentadas pelo código e
pelas provas locais.

## 7. Arquivos prováveis e plano incremental

| Área | Arquivos prováveis na implementação futura |
| --- | --- |
| Geometria pura do par | Novo `member_miter_geometry.py`; reuso de `member_adjustment_geometry.py`; pequeno helper compartilhado com `connections/resolver.py` se apropriado |
| Candidata/validação/transação | Novo `interactive/member_miter_controller.py`; helpers pequenos em `member_batch.py` / `interactive/member_adjustment_controller.py` |
| UI e ownership da sessão | Novo `interactive/member_miter_task_panel.py`; reuso de `member_adjustment_preview.py` e padrões de cleanup |
| Registro | `commands.py`, `init_gui.py`, `paths.py`, ícone SVG próprio no sistema existente |
| Testes | Geometria pura, controlador bilateral, preview/lifecycle e gate nativo direcionado |
| Persistência associativa / filhos | Fora do MVP; `member.py`, fitting/treliças só quando houver contrato próprio aprovado |

Não modificar o clipper para obter outro resultado, nem criar gerador por
família dentro do comando. `profiles/geometry.py` continua fornecendo as
seções reais. Evitar refatoração ampla de comandos/painéis funcionais.

Sequência recomendada para a próxima tarefa:

1. **Contrato e matemática:** implementar resolvedor puro de J/pontas/normal,
   condicionamento e diagnósticos. Testar Start/Start, Start/End, End/End,
   troca A/B, normal invertida, ângulos 90/60/135, paralelos, reversos, T e
   cruzamentos. Sem alterar persistência.
2. **Par destacado:** converter plano comum em dois slots Fixed; preparar ambos
   com o pipeline existente. Medir tampas, vazios, sólidos e interpenetração.
   Cobrir seções/orientações da matriz, offsets/inserções, ponta oposta ajustada,
   extinção de comprimento e erro OCC. Testes negativos nativos desta investigação
   devem continuar sendo rejeitados.
3. **Atomicidade:** uma transação para ambos; falha antes de mutação e após
   recompute de A; comparar todos os inputs/saídas/Undo dos dois após rollback.
   Undo/Redo sem deriva nominal, FCStd reaberto e cortes locais persistentes.
4. **UI bilateral:** seleção/captura, plano e duas candidatas, substituição
   explícita, OK/Cancelar/Esc/fechar, troca de alvo/vista/documento e exclusão de
   um membro. Critérios por estado/eventos reais, sem sleeps/retries que escondam falhas.
5. **Gate de liberação do MVP:** cenários nativos FreeCAD 1.1.4, Classic,
   FreeCAD Dark e OpenDark; depois suíte Python apropriada/completa e
   `check_project.py`, conforme a implementação. Validação manual do usuário
   antes de commit; publicação continua separada.
6. **Extensões posteriores:** AxisSource Linked externo; Simplified/Detailed
   adicionais e outras famílias; aparo terminal interior explícito; filhos de
   treliça com proveniência; associação persistente somente em etapa arquitetural
   própria. Encontros reversos/espaciais complexos, T, múltiplos participantes,
   planos assimétricos para seções distintas e recorte volumétrico ficam fora.

## 8. GO/NO-GO e preservação

**GO para iniciar a implementação do MVP delimitado**, não para considerar
feature pronta ou publicada. A preferência de dois selecionados, preview
simultâneo e um OK/Undo é tecnicamente viável e recomendada. A prova da
transação existente confirma a base; ainda faltam controlador, UI, diagnósticos
e testes de falha do comando futuro.

**NO-GO para prometer nesta mesma entrega** associação que mantenha o encontro
após editar um participante, qualquer combinação de perfis/rolls, filhos sem
preflight de proveniência ou contato físico por subtração de sólido. Esses
objetivos não são consequências automáticas de ter PlaneCut disponível.

Conferência final por SHA-256 dos **584 arquivos locais inventariados** fora
de `.git`, evidências e caches: nenhum existente alterado; somente este
relatório novo. Estudos Gusset, StructuralPlate, documentação intermediária,
FCStd locais e os três documentos consultados permanecem preservados.
`test-results/member_miter_joint_investigation/preservation-final.json` registra
a comparação. HEAD e índice permanecem inalterados.
