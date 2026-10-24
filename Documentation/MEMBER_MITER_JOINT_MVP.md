# Meia-esquadria — MVP bilateral fixo

Data: 23/10/2026. Branch `develop/0.7.0`.
Base: `2ef3b49d3e02fd111a8133240519a3ffc9068ca0`.

**GO para validação manual do usuário**, sem autorização de commit/publicação.
A implementação segue a [investigação aprovada](MEMBER_MITER_JOINT_INVESTIGATION.md):
comando próprio, duas candidatas reais, plano separador comum, cortes Fixed,
um OK e uma transação. Não foi alterado o esquema persistente nem o PlaneCut.
Nenhum `git add`, commit, push, merge, tag ou release foi executado.

## Comportamento implementado

O comando **Meia-esquadria** (`SteelStructures_MiterMembers`) fica próximo a
Recortar/Ajustar no menu e na toolbar de elementos. Aproveita zero, um ou dois
membros pré-selecionados; os botões Selecionar A/B permitem completar ou trocar
os alvos por seleção gráfica ou na árvore. Seleção duplicada, excessiva ou de
objetos não estruturais é recusada. Não há controle de ângulo, gap ou bissetriz
que possa introduzir uma modalidade fora do MVP.

O painel apresenta membro/perfil A/B, pontas automaticamente determinadas,
ângulo e diagnóstico. Após o refinamento, há uma mensagem principal: sucesso
verde com ângulo, erro vermelho com causa objetiva, orientação neutra. As cores
são locais ao label e ajustadas à paleta/contraste do tema; não há QSS global.
Pontas A/B ficam no resumo; legenda de cores e explicação de corte fixo ficam
em tooltips, com nota curta discreta. Os dois sólidos aparecem simultaneamente,
A em azul e B em laranja; um contorno vermelho e uma cruz marcam o plano e o
encontro dos eixos. São branches Coin transientes, sem objetos de documento.
Uma nota informa que os cortes são fixos e não acompanham mudanças do parceiro.

O OK nativo fica desabilitado com seleção incompleta, captura pendente ou par
inválido. O estado do botão é sincronizado depois da montagem da Task View por
evento Qt pertencente ao formulário, sem callback adicional que sobreviva ao
seu fechamento. Capturar outro alvo limpa os previews e restaura os originais.

## Geometria e critérios de aceitação

`member_miter_geometry.resolve_miter()` resolve os pontos mais próximos das
retas nominais e exige encontro dentro da tolerância. Rejeita paralelos,
colineares, quase paralelos, retas reversas, eixos nulos/não finitos e escalas
sem precisão suficiente. O encontro J só é admitido na ponta selecionada ou
no raio exterior dela: Start com estação ≤ tolerância, End com estação ≥ L−tol.
J interior a qualquer segmento é recusado como T/cruzamento/aparo interior.

As direções interiores retidas determinam `n=unit(rA-rB)`. O plano passa por J;
os interiores devem estar em semiespaços opostos. A ordem A/B não altera o
encontro ou os cortes; a normal recebe sinal canônico apenas para estabilidade
da representação. Não é oferecida a outra bissetriz como alternativa equivalente.

O controlador converte o plano para os dois slots Fixed/PlaneCut existentes:
offset relativo à ponta nominal, normal no frame local, gap zero e Reference
nula. Avalia ambos por `MemberAdjustmentController.evaluate_values()` e
`member_batch.prepare_member()`, que executam o pipeline real do membro.
Não há algoritmo novo de extrusão/corte nem subtração do volume do parceiro.

As validações do par são independentes:

- Cada Shape deve ser não nula, válida, ter volume finito positivo e exatamente
  um sólido. Um sólido antigo preservado não é evidência de sucesso.
- O plano transiente de medição abrange os bounds projetados dos dois sólidos.
  A interseção fornece todas as regiões reais de material nas tampas, inclusive
  contornos internos de RHS/SHS. Não se usa bounding box como superfície de contato.
- As tampas precisam ter contato útil positivo e resíduos de área pequenos
  nos dois sentidos. A igualdade de área/volume sozinha não aprova uma junção.
- As curvas dos contornos também são comparadas por diferença nos dois
  sentidos. Não se interpreta distância mínima zero como coincidência completa.
- O volume de interpenetração do par deve ficar abaixo da tolerância própria.
- Antes de gerar OCC, `plane_axial_span()` estima a tampa inteira pelo envelope
  real da seção/inserção/offsets e pelo plano da ponta oposta. O corte novo não
  pode alcançar essa ponta; os casos limítrofes são recusados conservadoramente.

### Tolerâncias

Unidades internas: mm, mm² e mm³. A tolerância linear é
`max(1e-5 mm, 1e-9 × maior comprimento nominal, 32 × ULP da maior coordenada)`.
O piso é 100 vezes 1e-7 mm, escala usual de precisão do kernel e valor já usado
pelo núcleo; a parcela relativa trata escala do modelo e ULP reconhece perda
de precisão das entradas. Se essa tolerância alcançar 1e-4 do menor comprimento,
o resolvedor recusa a escala em vez de aceitar uma geometria imprecisa.
`sin²(ângulo) ≤ 1e-12` e normal quase paralela ao eixo são recusados.

A tolerância de área é `max(1e-6 mm², tol_linear × soma dos perímetros das tampas)`;
a de volume, `max(1e-5 mm³, tol_linear × soma das áreas das tampas)`. A tolerância
de resíduo dos contornos é linear e proporcional à quantidade de arestas.
São orçamentos dimensionais para medir erro, não deslocamentos aplicados à
geometria. A correspondência de curvas é um veto adicional conservador do OCC;
resultados numericamente ambíguos são bloqueados, sem fuzzy-boolean, reparo de
Shape, rotação de seção ou ajuste de valores para forçar aprovação.

## Domínio suportado e rejeições

Dois `StructuralMemberProxy` distintos no mesmo documento, sem GenerationOwner,
AxisDefinitionMode Independent, sem composição, sem plano AutoFit residual,
mesmo perfil e geometria **Detailed**. A matriz inicial contém W de abas
paralelas, U simples, Ue, RHS e SHS. A compatibilidade da orientação é decidida
pela geometria completa; não se exige roll zero nem se assume que rolls iguais
sempre fecham. W com orientações espelhadas de 23°/−23° foi ensaiado a 60°.

| Situação | Comportamento |
| --- | --- |
| 90°, 60°, 135° e outros ângulos bem condicionados | Plano calculado; só aprova quando todas as verificações geométricas passam |
| Start/Start, Start/End, End/End | Pontas inferidas dos raios exteriores; seleção invertida mantém resultado |
| Plano do encontro inclinado no espaço | Suportado; os eixos continuam coplanares |
| Placements rígidos de App::Part | Suportados, inclusive parents distintos/aninhados; cálculo e preview usam coordenadas globais |
| Ponta oposta já ajustada | Preservada, desde que não interfira e suas referências estejam válidas/recomputadas |
| Ponta escolhida já ajustada | **Recusada**, sem substituição automática; remover/revisar previamente no comando unilateral |
| Perfis distintos, mesmo só na espessura | Recusados |
| Rolls, inserções ou offsets que não produzem fechamento | Recusados com diagnóstico de seções/contornos incompatíveis |
| T, cruzamento, aparo nominal interior, paralelos, colineares, reversos | Fora do MVP, recusados |
| Filhos de treliça, um ou dois | Recusados, sem alterar owner/fitting |
| AxisSource Linked, Simplified, outras famílias ou assemblies | Fora do contrato inicial |
| Expressões, fontes pendentes/inválidas ou dependência prévia entre A/B | Recusadas antes da transação |
| Ajuste associativo oposto em parent transformado | Recusado explicitamente: o contrato preexistente de referência desse caso exige revisão fora deste incremento |

“Independente” inclui duas restrições distintas: não ser filho de treliça e
não ter eixo Linked. Documentos e parâmetros existentes não são migrados para
essa condição. Não há fallback para corte por sólido, prioridade ou meia-esquadria
assimétrica entre seções diferentes.

## Placements globais e preview

O frame nominal armazenado no membro é preservado. Para contêineres rígidos,
`parentDelta = getGlobalPlacement() × Placement.inverse()` transforma seus
StartPoint/EndPoint para world; estações/distâncias são invariantes. A normal
é convertida pelo Placement global. As candidatas para aplicação permanecem
no frame do parent; as `global_shapes` são cópias de apresentação/validação.
O renderer existente recebe esse adaptador explícito em coordenadas globais.

O polling observa os dois inputs, suportes geométricos de referências opostas,
estado e Placement global, além da apresentação/vista ativa no painel. Assim,
movimento de App::Part é percebido mesmo sem mudança local/Touched nos filhos.
Uma alteração de entrada durante cálculo/render invalida ambos os previews,
sem consumir a assinatura nova como se tivesse sido avaliada. O próximo poll
normal processa a entrada atual. Não há retry silencioso de confirmação.

Cancelar, Esc, fechar formulário/tarefa, excluir alvo, trocar documento/vista
e desativar a workbench convergem para limpeza idempotente: branches A/B e
marcador removidos, máscaras restauradas, observer removido, timer parado e
desconectado. Se o segundo export falhar, o primeiro também é limpo.
Não foi acrescentado observer de documento ou callback de viewport.

## Confirmação atômica e persistência

No OK, o controlador resolve novamente as entradas e prepara/verifica as duas
candidatas antes de abrir a transação. Grava somente os seis campos da ponta
escolhida de cada membro, recomputa e verifica cada resultado com o guard da
Etapa 1: Shape/estado, comprimento ajustado, massa, volume e Placement. Confere
também propriedades nominais, catálogo/posicionamento de seção, extensões e o
slot oposto preservados; por fim, valida outra vez o par definitivo em world.
Somente então confirma **uma** transação. Qualquer falha aborta as duas gravações.
Não são chamadas duas operações `apply()` unilaterais consecutivas.

Length/MemberLength e eixos nominais permanecem; AdjustedLength e TotalMass
seguem o pipeline existente. TotalMass usa massa linear de catálogo e, para
corte oblíquo, comprimento equivalente derivado do volume/área da seção.
Não foi introduzida outra fórmula de massa nem preenchimento dos vazios.

FCStd guarda dois ajustes Fixed, sem vínculo cruzado, objeto Joint, Face
auxiliar, propriedade nova ou alteração de SchemaVersion. Mover/girar/alongar
ou trocar o perfil de um participante depois pode desfazer o encontro: o
parceiro não acompanha. Essa independência foi verificada após restauração.

## Arquivos deste incremento

| Estado | Arquivo |
| --- | --- |
| Novo | `freecad/SteelStructures/member_miter_geometry.py` |
| Novo | `freecad/SteelStructures/interactive/member_miter_controller.py` |
| Novo | `freecad/SteelStructures/interactive/member_miter_preview.py` |
| Novo | `freecad/SteelStructures/interactive/member_miter_task_panel.py` |
| Novo | `Resources/Icons/MiterMembers.svg` |
| Modificado | `freecad/SteelStructures/commands.py` |
| Modificado | `freecad/SteelStructures/init_gui.py` |
| Modificado | `freecad/SteelStructures/paths.py` |
| Modificado | `freecad/SteelStructures/interactive/member_adjustment_controller.py`: exposição de avaliação por valores e guard compartilhado |
| Modificado | `freecad/SteelStructures/interactive/member_adjustment_preview.py`: parâmetro opcional de cor, padrão anterior preservado |
| Novo | `tests/test_member_miter_geometry.py` |
| Novo | `tests/test_member_miter_controller.py` |
| Novo | `tests/test_member_miter_preview.py` |
| Novo | `tests/test_member_miter_task_panel.py` |
| Novo | `tests/manual_member_miter_joint.py` |
| Novo | `scripts/run_member_miter_joint_gate.py` |
| Modificados | `tests/test_command_registration.py`, `tests/test_column_command.py`, `tests/test_general_tools.py`: listas esperadas incluem o novo comando |
| Novo | `Documentation/MEMBER_MITER_JOINT_MVP.md` |

São **20 caminhos**: 8 modificados e 12 novos. Nenhum ajuste em member.py,
member_batch.py, member_plane_cut.py, catálogos, Gusset, StructuralPlate ou
ferramentas globais do Draft. O registro/deactivation apenas integra a sessão
nova aos padrões de comandos existentes.

## Validações da implementação inicial

Os resultados desta seção antecedem o refinamento relatado ao final. Os gates
iniciais recomputavam explicitamente depois de Undo/Redo; comprovavam restauração,
mas não a reutilização imediata sem recompute manual, lacuna identificada pela
validação do usuário e corrigida na rodada seguinte.

### Python direcionado

**343 testes aprovados, zero falhas e zero skips**, cobrindo 27 módulos:
geometria/controlador/preview/painel novos; ajustes, referências, PlaneCut,
Placement, eixo, criação e orientação de membros; fitting/massa/rollback de
treliças; registro, pilar e ferramentas gerais. Comando e log completos:

`test-results/member_miter_joint_mvp/python-results.json` e `focused.log`.

O comando é `python -B -m unittest` com a lista explícita de módulos registrada
nesse JSON. Inclui regressões de ordem/pontas, retas reversas/T/paralelos,
NaN/Inf e overflow de coordenadas finitas, elegibilidade/seleção, falha tardia,
rollback bilateral, drift nominal, falha do segundo renderer, montagem do OK
e alteração de input durante cálculo. Doubles não substituem os gates abaixo.

`python scripts/check_project.py`: **aprovado**.
`git diff --check`: **aprovado**. A checagem dos novos arquivos também é
registrada nas evidências finais. **Suíte completa reservada para o fechamento**,
conforme solicitado; não foi executada nesta implementação.

### FreeCAD 1.1.4 / Qt6

```powershell
python scripts/run_member_miter_joint_gate.py --theme Classic
python scripts/run_member_miter_joint_gate.py --theme "FreeCAD Dark"
python scripts/run_member_miter_joint_gate.py --theme OpenDark
```

| Gate final | Checks | Resultado | Pasta em `test-results/miter/` |
| --- | ---: | --- | --- |
| Classic | 622 | OK | `1792800141191013400_Classic_ttldhf8a` |
| FreeCAD Dark | 622 | OK | `1792800094824202200_FreeCAD_Dark_zaww810d` |
| OpenDark | 622 | OK | `1792800176608339000_OpenDark_h3j1qgk3` |

**1866 checks nos três gates finais**, não testes unitários independentes.
Todos com saída zero, nenhum timeout, zero erros capturados de callbacks
Python/Qt e filtros de logs nativos vazios. Manifestos registram fontes,
comandos, versão e perfil isolado por processo.

Cobertura nativa: 11 fixtures positivas nas cinco famílias, ângulos 90/60/135,
Start/End mistos, roll espelhado e plano global inclinado; invariância à ordem,
comparação BRep bidirecional das duas candidatas com o resultado, uma ação de
Undo/Redo, restauração FCStd e independência fixa posterior. Rejeições cobrem
roll/perfis incompatíveis, skew/paralelos/T/cruzamentos, ponta ocupada, Linked,
ponta oposta inválida e filhos de treliça. A falha injetada na segunda
verificação definitiva aborta e recupera os dois membros sem Undo adicional.

Também foram ensaiados: ponta oposta Fixed e Associative externa válida,
preservação de LinkSub, Undo/Redo/FCStd e atualização posterior da referência;
App::Part compartilhado, parents distintos e aninhados, movimento de parent
durante a tarefa, atualização/invalidação de ambos os branches e persistência
em cada arranjo. A associação oposta sob parent transformado é recusada.

UI: pré-seleção pelo comando público, captura interativa A/B, captura pendente,
botão OK real após montagem, preview fiel e pixels com/sem os sólidos,
aceitação bilateral, Cancelar/Esc/fechar formulário/tarefa, exclusão, troca de
vista/documento e desativação. Sem objetos persistentes auxiliares nem resíduos
monitorados de branches, timer ou observer.

Foram oito execuções nativas nesta rodada: a primeira parou após 260 checks
porque o registrador de evidências tentava medir Volume de uma Shape
intencionalmente inválida. O registrador foi corrigido para registrar nulidade/
validade/estado e não inventar um volume; medições de Shapes válidas continuam
obrigatórias. A tentativa está preservada em
`1792796386584659700_Classic_nbkxer6d`. Um Classic intermediário passou com
461 checks (`1792796506337534900_Classic_c7ral1sp`), antes da ampliação dos
testes de coordenadas globais. Uma campanha anterior com 622 checks por tema
também passou (`1792796911037234500_Classic_wwopcis8`,
`1792799663473910300_FreeCAD_Dark_g5lpnhnf`,
`1792799733277690800_OpenDark_6yfihvyy`). Os três gates finais acima repetem
essa campanha com captura adicional da janela completa, sem alteração de
produção. São sete execuções concluídas com sucesso e uma interrompida por
erro do registrador; esta não foi contabilizada como passe ou skip.

As capturas finais da Task View e dos renders nativos foram inspecionadas.
Em FreeCAD Dark, `form.grab()` recompõe a área transparente do formulário
isolado sobre cinza claro, produzindo contraste diferente da Task View real.
`miter-window.png` confirma fundo escuro e textos legíveis na janela composta;
não foi necessária correção de produção. A captura da janela contém artefatos
OpenGL no viewport e serve para avaliar o painel; os renders `saveImage`
separados são usados para a geometria e não exibem esse artefato.
Isso é QA visual de evidências, não uma validação manual interativa pelo
usuário. A revisão técnica independente não identificou bloqueador residual.

## Limites e roteiro manual

1. Em Classic, selecionar dois membros iguais Detailed cujos eixos terminem
   em J ou a pouca distância antes dele. Usar Meia-esquadria; conferir A/B,
   pontas, ângulo, cores dos sólidos e marcador vermelho. Repetir invertendo
   a ordem e com Start/End mistos.
2. Conferir W, RHS/SHS, U simples e Ue em 90° e ângulo oblíquo; observar a
   orientação real da seção. Rolls incompatíveis, larguras/espessuras distintas,
   eixo reverso, T ou ponta já ajustada devem bloquear OK sem alterar as peças.
3. Abrir sem seleção, capturar A/B e trocar um alvo. OK deve ficar desabilitado
   durante a captura. Cancelar, Esc e fechar tarefa devem restaurar ambos os
   originais e permitir reabrir sem resíduos.
4. Confirmar; conferir os dois cortes, eixos nominais e massa. Um Undo deve
   restaurar ambos; um Redo, refazer ambos. Salvar/reabrir FCStd e recomputar.
5. Repetir com ponta oposta já ajustada válida e com members em App::Part
   transformado. Mover um parent durante o preview: atualizar ambos ou
   invalidar o par. Não aceitar preview antigo. Associação oposta sob parent
   transformado deve explicar a limitação.
6. Repetir apresentação/legibilidade e Cancelar/Esc nos temas FreeCAD Dark e
   OpenDark. Após confirmar, mover um membro: conferir que o parceiro não segue,
   como informado pela nota de cortes fixos.

O cálculo OCC permanece no thread da interface. Casos grandes, mal condicionados
ou com curvas numericamente incompatíveis podem ser recusados conservadoramente.
FreeCAD 1.1.3 não foi executado nesta etapa solicitada para 1.1.4. Não há
certificação de ligação/solda, associação automática ou promessa de todo perfil
e orientação. A aprovação de funcionamento/design pelo usuário e o fechamento
com suíte completa continuam pendentes antes de qualquer commit.

## Preservação da implementação inicial

HEAD permanece `2ef3b49`, branch `develop/0.7.0`, índice vazio. A conferência
registra **577 arquivos protegidos fora do incremento**, sem modificação ou
remoção. A comparação com o inventário da investigação anterior também não
mostrou diferença fora dos arquivos existentes autorizados. Estudos Gusset,
StructuralPlate, documentos intermediários, FCStd locais e o relatório da
investigação foram preservados.

`test-results/member_miter_joint_mvp/` contém logs direcionados, manifestos e
`preservation-final.json`; `test-results/miter/` contém as evidências nativas.
Essas pastas não integram os 20 caminhos do incremento.

## Refinamento após validação manual — 23/10/2026

O usuário aprovou os encontros nas pontas a 90°/oblíquos, cancelamento e FCStd;
relatou bloqueio após Undo/Redo, excesso de texto, interesse em aparo de pontas
ultrapassadas e possível ressalto nas mesas W. Este refinamento mantém o domínio
geométrico e a persistência do MVP; não modifica member.py, PlaneCut, geradores
de seção, catálogos, treliças, Gusset ou StructuralPlate.

### Causa e correção de Undo/Redo

A prova nativa isolada está em
`test-results/member_miter_refinement/1792802288244232600_undo_g7uvka3b/`.
Undo **e** Redo restauraram slots, Shape, Placement, saídas e eixo nominal,
mas deixaram ambos os membros com `State=['Touched']`. O preflight anterior
rejeitava Touched indistintamente, antes mesmo de preparar as candidatas. Não
foi demonstrada corrupção do sólido nem deriva nominal nesse replay.

No FreeCAD 1.1.4, `doc.recompute([A, B])` limpou o estado sem alterar UndoCount
ou RedoCount. Um objeto alheio propositalmente Touched permaneceu pendente e
seu contador de execução não mudou. `obj.recompute()` executou mas não limpou
Touched, portanto não foi escolhido. A recomputação parcial também pode
executar fontes upstream: a prova registrou esse efeito, que exige preflight.

`MemberMiterController.prepare_inputs()` agora valida **todo** o par e suas
dependências primeiro. Invalid, expressões, referências pendentes e demais
restrições continuam bloqueados antes de qualquer recompute. Somente os
participantes Touched/Recompute elegíveis entram na recomputação parcial;
nenhum objeto auxiliar, transação de preview, purgeTouched ou observer de
Undo foi introduzido. A assinatura dos inputs deve permanecer igual e os
participantes devem sair sem Touched/Invalid/Recompute. Atualizam-se apenas
saídas derivadas necessárias; não se aceita uma Shape antiga como prova.

O painel chama essa preparação antes de capturar sua assinatura avaliada,
evitando interpretar a limpeza esperada de Touched como edição concorrente.
A confirmação revalida tudo e também usa `doc.recompute([A, B])` dentro da
única transação bilateral. Falhas continuam abortando os dois cortes. Uma
ponta já Fixed após Redo continua ocupada e corretamente recusada; uma ponta
livre pode participar imediatamente de outro encontro.

A assinatura do preview passou a incluir os estados das fontes transitivas,
percorridas pelo mesmo helper do preflight. Assim, uma fonte Touched/Invalid
invalida ambos os branches e o OK mesmo quando sua geometria anterior não
mudou. O OK sempre executa uma nova avaliação. Fontes pendentes não são
recomputadas silenciosamente por essa ferramenta.
O gate confirmou o caso relevante: ambos os membros ainda estavam Up-to-date
quando a fonte, com a mesma Shape, ficou Touched; a assinatura adicional
detectou isso e removeu os dois previews.

**Limitação nativa de Redo em falha tardia:** a primeira campanha de refinamento
parou após 413 checks, em
`test-results/miter/1792802665853070700_Classic_36uolpg1/`, porque o gate exigia
preservar também a pilha Redo anterior após uma escrita seguida de abort.
O erro não foi ignorado nem considerado sucesso. Uma prova separada sem
carregar qualquer módulo Steel Structures está em
`test-results/member_miter_refinement/1792802781868524300_abort_yui15uof/`:
App::FeaturePython com Float e Part::Box preservam Redo ao abrir a transação,
mas a primeira escrita descarta Redo; abort restaura valores, Shape e UndoCount,
sem reconstruir essa pilha. Abrir/abortar sem escrever preservou Redo no controle.

O gate passou a separar restauração integral do par, ausência de Undo adicional
e comportamento da pilha Redo comparado ao controle nativo. Não se promete
preservar Redo anterior após uma falha **depois de escrever**; isso é uma
limitação demonstrada da API transacional do FreeCAD 1.1.4. Não foi introduzido
hack de histórico ou replay de operações alheias. Avaliações inválidas anteriores
à transação, abertura de preview e cancelamento preservam Undo/Redo. Uma nova
aplicação confirmada após Undo substitui a pilha Redo como esperado.

### Pontas ultrapassadas: prova e decisão

Evidência geométrica:
`test-results/member_miter_refinement/geometry_review/1792802335900016100/`.
Nove provas usaram W150×13,0 a 60°/90°/120°, com ultrapassagens de
0,1/0,9/1,1 vezes o envelope axial da tampa. O FixedReferenceOffset positivo
existente representou o aparo e o plano comum sem alterar eixo nominal,
extensões ou a ponta oposta. Os nove resultados passaram na validação do par,
com diferença BRep volumétrica zero frente ao encontro exterior correspondente.
Portanto, não há impedimento do PlaneCut nem necessidade demonstrada de
propriedade nova ou ajustes empilhados para representar esse resultado.

Isso **não identifica a intenção**. O mesmo par de eixos/seções pode ser um
canto com sobra ou um T curto cujo trecho passante precisa permanecer. Até
1,1 vezes o envelope passou geometricamente: o envelope pode ser uma política
conservadora de alcance, mas não uma classificação de T. Nem menor distância
à ponta, proporção do comprimento ou uma tolerância maior demonstra a decisão.

**Não foi habilitado aparo interior automático nesta rodada.** O bloqueio é
contratual/de intenção, não uma alegação de grande mudança arquitetural. Para
preservar o requisito de não interromper T verdadeiro, mantém-se o domínio
terminal aprovado. O diagnóstico agora descreve apenas a condição observada:
“Interseção no interior de um membro; aparo de ponta não suportado”, sem
afirmar que toda ultrapassagem é T. Um teste permanente cobre sobras de
0,001/1/50 mm, três ângulos e ambas as ordens de seleção.

Proposta futura: operação contextual explicitamente consentida **Aparar a ponta
escolhida até o encontro**, com ponta A/B retida declarada, alcance axial por
membro e material removido visíveis antes do OK. Poderia usar o envelope da
tampa como limite conservador informado e os mesmos gates de contato, sólidos,
semiespaços e ponta oposta. Não deve prometer reconhecimento automático de T.
Essa política de remoção precisa ser definida e aprovada antes de habilitar
um checkbox que também poderia interromper uma peça intencionalmente passante.

### W150×13,0: ressalto não reproduzido nas provas controladas

A prova ensaiou orientação padrão e frame coplanar controlado a 60°/90°/120°,
mais rolls 23°/−23° e 23°/23° a 60°. Nas três orientações padrão compatíveis:

| Ângulo | Área de contato (mm²) | Envelope axial em torno de J (mm) |
| --- | ---: | ---: |
| 60° | 3148,520000 | ±86,602540 |
| 90° | 2226,339843 | ±50,000000 |
| 120° | 1817,798870 | ±28,867513 |

Nos três, área de ambas as tampas = contato, resíduos de área e comprimento
de contornos zero, volume comum zero e um sólido válido por membro. O erro
das tampas em relação ao plano ficou na ordem de 1e-13 mm; a união também
resultou em um sólido válido. Bounds verticais dos dois: −74…74 mm. Os frames
controlados também passaram. Rolls 23°/−23° fecharam; 23°/23° foram recusados,
com contato de apenas 184,919560 mm² e resíduos de 2963,600440 mm² por tampa.

A seção preserva o gerador existente de cantos vivos: d=148, bf=100, tw=4,3,
tf=4,9 mm; área geométrica de 1574,26 mm². A área catalogada é uma informação
distinta preexistente; não foi usada como substituto da tampa real nem alterada.
Não houve correção especulativa, soldagem/fusão persistente, ajuste de perfil
ou tesselação para esconder a emenda. BREPs e renders separados estão guardados.
As imagens controladas não demonstraram degrau físico; arestas da emenda e
projeção das mesas podem aparecer no viewport. Isso não diagnostica
conclusivamente o encontro original do usuário, cujos inputs não foram
capturados: deve ser repetido no roteiro manual antes de concluir que era
somente representação gráfica.

### Verificações deste refinamento

Python direcionado: **357 testes aprovados, zero falhas e zero skips**, nos
mesmos 27 módulos explícitos da campanha inicial. Comando exato e log:
`test-results/member_miter_refinement/python-results.json` e `focused.log`.
Inclui recompute parcial sem transação, veto de fonte pendente antes da
atualização, preservação do objeto alheio, falha de atualização, estados
transitivos sem mudança de Shape, orientação neutra/sucesso/erro e contraste
em paletas claras/escuras. A suíte completa continua reservada ao fechamento.

Os comandos nativos são os mesmos três `run_member_miter_joint_gate.py --theme`
listados na campanha inicial. Resultados finais deste refinamento:

| Tema | Checks | Resultado | Pasta em `test-results/miter/` |
| --- | ---: | --- | --- |
| Classic | 823 | OK | `1792802900957001100_Classic_agyrb_k1` |
| FreeCAD Dark | 823 | OK | `1792802935315333100_FreeCAD_Dark_edol0tms` |
| OpenDark | 823 | OK | `1792802973874276500_OpenDark_t7f303kw` |

São **2.469 checks**, não testes unitários distintos: três execuções finais
com saída zero, nenhum timeout, callback_errors vazio e filtros de logs nativos
vazios. Manifestos conferem os mesmos hashes finais de produção e do gate.
Houve **quatro execuções do gate** nesta rodada: a tentativa interrompida
após 413 checks descrita acima e as três finais aprovadas. Não houve falha
ocultada, skip ou aprovação por simples retry. A expectativa incorreta sobre
Redo após abort foi substituída por controle nativo explícito, preservando
verificações integrais dos membros e de Undo. Separadamente, **três processos
de prova isolada** concluíram com sucesso: replay/recompute, W/aparo e abort
sem módulos Steel Structures.

Cada gate final cobre três ciclos sucessivos de aplicar → Undo → reabrir sem
recompute manual → aplicar novamente → Undo → reabrir → Redo. A primeira
reabertura usa `Gui.runCommand` público. Confere preservação de Redo ao abrir
preview e cancelar, substituição de Redo só ao reaplicar, ponta ocupada após
Redo e nova ligação na ponta oposta livre. Reabertura após rollback e FCStd
também ocorre sem recompute manual. Sentinelas Touched no mesmo documento e
em outro documento não são executadas pelo preview ou aplicação. Fontes
pendentes com Shape preservada bloqueiam os dois resultados e o OK; após
recompute explícito da fonte, o preview volta. W60/W120 foram adicionados
permanentemente às fixtures, além de W90 e roll espelhado existentes.

Continuam cobertos preview BRep = confirmação, falha injetada na segunda
verificação, persistência, nominal/massa/ajustes opostos, cancelamento, Esc,
fechamento, exclusão, troca de documento/vista e limpeza de branches/timer/
observer. As esperas GUI são por despacho real de eventos/timeout do timer de
produção, sem sleeps, retries silenciosos ou tolerância temporal para aprovar.

As mensagens foram verificadas por severidade, matiz e contraste medido no
fundo da janela composta, com imagens e `message-styles.jsonl` nos três gates.
Contrastes sucesso/erro: Classic 5,03/5,05; FreeCAD Dark 7,39/5,07;
OpenDark 8,27/4,71. Orientação neutra também passou; todos ≥4,5. As capturas
da Task View foram inspecionadas; viewport é avaliado por render nativo separado,
pois `QWidget.grab` da janela tem a limitação OpenGL já registrada acima.
Essa inspeção não substitui a nova aprovação manual de funcionamento/design.

`python scripts/check_project.py`: **aprovado**, inclusive após a versão final
do gate. `git diff --check` e checagem de whitespace dos arquivos novos:
**aprovados**. Nenhuma suíte completa foi executada neste refinamento.

### Arquivos refinados e roteiro adicional

O inventário do incremento permanece nos mesmos 20 caminhos. Nesta rodada
foram refinados: `member_miter_controller.py`, `member_miter_geometry.py`,
`member_miter_task_panel.py`, seus três testes de controlador/geometria/painel,
`tests/manual_member_miter_joint.py` e este relatório. Nenhum arquivo fora
desse conjunto foi alterado pela implementação; evidências ficam em test-results.

1. Aplicar num par válido, Undo e abrir de novo imediatamente: ambos os previews
   devem aparecer sem recompute manual. Reaplicar, Undo, Redo e repetir vários
   ciclos; conferir que cada confirmação bilateral acrescenta um único Undo.
2. Após Redo, a mesma ponta está ocupada e deve explicar esse bloqueio em vermelho;
   uma ponta livre pode participar de novo par. Cancelar não acrescenta Undo
   nem corta peças. Não deve surgir solicitação de recompute dos participantes.
3. Conferir mensagem verde e ângulo em Classic, FreeCAD Dark e OpenDark,
   orientação neutra antes de selecionar e causa vermelha para par inválido.
   Conferir tooltips sem texto redundante no painel.
4. Repetir W150×13,0 a 60°/90°/120° com orientações compatíveis e observar de
   perto mesas superiores/inferiores. Se o ressalto original persistir, conservar
   FCStd e parâmetros/Placement desse caso para comparar tampas e contornos;
   não concluir somente pela linha de emenda.
5. Ponta ultrapassada continua recusada com diagnóstico de interseção interior;
   não deve haver remoção automática de material. Referência oposta pendente
   deve invalidar os dois previews/OK, preservando os membros.

Conferência SHA-256 contra o snapshot do início **desta rodada**: **577 arquivos
fora do incremento preservados**, zero alterações/remoções e nenhum caminho
inesperado acrescentado fora do conjunto selecionado/evidências. A comparação
com o inventário mais antigo já apontava, no início, diferenças preexistentes
em `tests/copiatreliça2.FCStd` e seu `.20261012-094115.FCBak`; ambos foram
incluídos e preservados pelo novo snapshot. Não foram abertos/salvos pelos gates.
Índice vazio e HEAD `2ef3b49`; nenhum staging, commit, push, merge, tag ou release.
Evidências finais: `test-results/member_miter_refinement/preservation-final.json`,
`selected-manifest.json`, `new-whitespace.json` e `final-native-sources.json`.

**GO para nova validação manual** da reutilização após Undo/Redo e do painel
refinado. **Não habilitado** aparo interior automático; W original continua
dependendo da reprodução do caso específico. A limitação nativa de perda do
Redo prévio em falha tardia após escrita está explicitada. A revisão técnica
independente não identificou bloqueador adicional. Suíte completa/fechamento
e aprovação do usuário continuam pendentes antes de considerar commit.
