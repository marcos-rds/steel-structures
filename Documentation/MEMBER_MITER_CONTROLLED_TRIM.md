# Meia-esquadria — aparo controlado de extremidades

Data: 24/10/2026. Branch `develop/0.7.0`. Base publicada: `6e8f0e1`.

Incremento do MVP bilateral fixo. Referências preservadas:
[investigação](MEMBER_MITER_JOINT_INVESTIGATION.md),
[MVP](MEMBER_MITER_JOINT_MVP.md) e
[fechamento anterior](MEMBER_MITER_JOINT_MVP_CLOSURE.md).
Os bloqueios históricos de aparo interior desses documentos descrevem o MVP;
este incremento os amplia somente com escolha e consentimento explícitos.

O usuário aprovou manualmente o funcionamento, a interface com autorização
global e os comportamentos geométricos. Esta rodada trata somente dos valores
nas alternativas Início/Fim e da apresentação dos conjuntos A/B; requer inspeção
**visual final**, sem autorização de commit/publicação. HEAD e índice preservados.

## Decisão arquitetural anterior à implementação

**GO sem migração ou mudança do núcleo.** A inspeção de `member.py`,
`member_plane_cut.py` e do controlador bilateral, também revisada de forma
independente, confirmou que os slots existentes representam a operação:

- Estação do encontro J medida desde Start: `t` no eixo nominal de comprimento `L`.
- Ponta Start: `StartFixedReferenceOffset=t`; ponta End: `EndFixedReferenceOffset=L−t`.
- `AdjustmentMode=Fixed`, `AdjustmentGeometryMode=PlaneCut`, referência nula,
  gap zero e normal convertida para o frame local de cada membro.
- O executor existente calcula os pontos efetivos, comprimento ajustado,
  massa e sólidos cortados. StartPoint/EndPoint, extensões, catálogo e slot
  oposto permanecem preservados.

Não foi alterado `SchemaVersion`, serialização, tipos de propriedade, `member.py`,
clipper ou fitting. Não há novo comando, objeto Joint ou vínculo entre os membros.
Consentimento e escolha existem somente na sessão da tarefa; FCStd guarda os
dois cortes fixos comuns já suportados. Reabrir a ferramenta não concede nova
autorização nem substitui uma ponta ocupada.

## Critérios geométricos e intenção

`inspect_miter()` calcula o encontro das retas suporte e as estações dos dois
eixos antes de atribuir uma extremidade. Conserva os filtros de precisão,
coplanaridade e condicionamento do MVP. Encontros convencionais continuam
inferindo Start ou End pelos respectivos raios exteriores, sem controles novos.

Quando J está estritamente no interior de um segmento nominal, **nenhuma ponta
é inferida**, mesmo que uma sobra seja muito curta. O usuário deve escolher
Início ou Fim para aquele membro e autorizar o aparo. Escolher a ponta a aparar
declara que o material no sentido da ponta oposta será preservado. Se ambos
os segmentos contêm J, são duas escolhas e uma autorização global do conjunto.
Um T sem essas ações continua bloqueado; a ferramenta não classifica intenção
por distância, envelope, proporção ou tamanho da sobra.

Para uma ponta livre, o valor mostrado é a distância axial até J, incluindo
eventual extensão positiva daquela ponta: Start=`t+StartExtension`,
End=`L−t+EndExtension`. O contrato puro `MiterPlan.trim_lengths` guarda somente
os excedentes **nominais**, sem extensão. A interface usa `trim_length()` para
mostrar o alcance axial completo. Esse valor é a redução do alcance sobre o
eixo, não uma medida da maior aresta da face oblíqua nem um volume removido.
As extensões permanecem armazenadas; o slot Fixed determina a ponta efetiva.
Nos encontros convencionais, o tratamento anterior de extensões permanece.

Não existe limite arbitrário para o aparo. Uma sobra de 10.000 mm requer a
mesma escolha e autorização inequívocas de uma sobra de 80 mm. Isso não dispensa
os testes de precisão ou de comprimento útil restante.

Depois da escolha/consentimento, o algoritmo anterior calcula a bissetriz
separadora `n=unit(rA−rB)` a partir das direções dos interiores retidos. O plano
passa por J. A outra bissetriz não é oferecida; inverter somente a normal não
escolhe outro material. O pipeline PlaneCut gera as duas candidatas físicas
completas, inclusive precursores necessários às faces oblíquas.

Mantêm-se todos os critérios do MVP:

- Envelope axial da tampa inteira sem alcançar o plano da ponta oposta.
- Interiores em semiespaços opostos, sem inversão da parte preservada.
- Exatamente um sólido válido por membro, com volume finito positivo.
- Superfícies de contato reais coincidentes, incluindo vazios e contornos;
  contato útil positivo, diferenças de área/contorno dentro das tolerâncias.
- Interpenetração volumétrica abaixo da tolerância dimensional do par.
- Mesmo perfil Detailed, família habilitada e orientação efetivamente compatível.

Os limites numéricos e tolerâncias lineares/de área/de volume permanecem os
documentados no MVP. Falhas OCC ou geometrias ambíguas bloqueiam o par;
não há reparo, rotação da seção ou corte pelo sólido do parceiro como fallback.

## Interface e autorização

O painel mantém o título Meia-esquadria e os botões Selecionar A/B. A seção
**Membros** tem dois conjuntos horizontais compactos. A/B fica centralizado
verticalmente à esquerda, junto de uma linha curta `QFrame.VLine` que usa o
estilo/paleta Qt. Ao lado, nome em negrito discreto e perfil secundário menor;
o botão Selecionar fica à direita, centralizado no mesmo conjunto. Não há cartões,
bordas grandes nem QSS novo. Textos longos permanecem em uma linha, elididos,
com conteúdo integral no tooltip. Os conjuntos têm espaçamento consistente.

A seção contextual **Extremidades a aparar** aparece somente quando há encontro
interior em um ou ambos os membros. Cada linha mostra A/B e uma combobox como
**Início (5.000 mm)** / **Fim (100 mm)**. Os valores vêm de `trim_length()` para
cada alternativa, incluindo a extensão livre aplicável. A opção selecionada
mantém o valor no campo fechado; abrir a lista confere as entradas e atualiza
os itens se necessário, inclusive entre polls. O editor estável não é reconstruído
desnecessariamente durante a troca entre listas A/B. `itemData` guarda `Start`/`End`;
o texto não é interpretado para decidir a operação. Não existe coluna separada
de valores nem repetição no título, diagnóstico ou rodapé de pontas.

Pontas já ocupadas ficam desabilitadas, com “indisponível” e motivo no tooltip;
não se mostra um valor de corte executável para elas. As alternativas livres
exibem distâncias axiais calculadas, **não uma certificação isolada de corte**:
a compatibilidade e a validade do par dependem das duas escolhas e continuam
verificadas pelo pipeline original após autorização, antes de preview/OK.
Casos de contato incompatível, corte alcançando a ponta oposta e demais rejeições
geométricas continuam bloqueados, sem novo solver, estimativa ou autorização
automática para avaliar alternativas. O tooltip esclarece esse contrato.

A notação usa ponto de milhar, vírgula decimal e nove algarismos significativos,
como a precisão de apresentação anterior; valores muito pequenos/grandes podem
usar notação científica. Isso não arredonda os parâmetros usados na geometria.
A advertência de cortes fixos sem associação e a legenda do preview ficam no
tooltip da mensagem de estado, sem nota permanente adicional.

Há uma única checkbox **Autorizar os aparos indicados**, inicialmente desmarcada.
Ela só fica habilitada após escolher todas as extremidades necessárias. Uma
marcação autoriza o conjunto exato apresentado, seja A, B ou ambos. Configurar
B antes de autorizar não exige nenhuma autorização individual prévia em A.
O preview bilateral real aparece imediatamente quando esse consentimento e
as verificações geométricas passam; o OK permanece bloqueado antes disso.
Uma ponta ocupada permanece recusada mesmo com consentimento.

O token global contém identidades dos participantes, assinatura material dos
dois membros, fontes, referências, placements e escolhas. State do próprio
membro não integra o token de consentimento: renomeação pode marcar Touched
sem mudar a operação. State continua na assinatura observada pelo painel e no
preflight/recompute original. Estados das fontes continuam observados, e os
filtros de elegibilidade não foram relaxados.

Trocar efetivamente membro/extremidade, geometria, extensão ou valores revoga
o consentimento global. Selecionar o mesmo membro ou a mesma ponta é inócuo.
Renomear, mudar cor, visibilidade, modo de exibição, paleta, tamanho ou vista
pode atualizar o preview, mas não revoga a autorização da mesma configuração.
Uma autorização já invalidada não reaparece ao reverter a mudança.
O controlador repete
essa verificação antes de abrir a transação, sem depender do timer da UI.
Se o valor mudar entre sua exibição e o clique no checkbox, o painel atualiza
os dados e exige outro clique. Assim, um consentimento dado vendo 80 mm não
autoriza silenciosamente 105 mm. Se as entradas mudarem antes do OK, o painel
atualiza a prévia e exige nova confirmação.

Os controles usam widgets e paleta nativos. Não há QSS global nem mudança
no algoritmo de cores semânticas do painel.

### Duplicação do perfil

O helper compartilhado `member_display_name()` já evita repetição textual exata.
Entretanto, `create_member()` grava o Label com a designação recebida enquanto
Profile usa `property_designation()` (normaliza aspas para ″), e o FreeCAD pode
alterar os últimos dígitos de Labels automáticos repetidos para torná-los únicos.
Esses caminhos quebravam a comparação literal e explicam o perfil duplicado.

O novo `_member_caption()` é exclusivo deste painel. Separa um sufixo de seção
equivalente do nome; trata a variação do uniquificador somente em nomes automáticos
identificados pelo ElementType. Se um Label personalizado já contém integralmente
o perfil em outra posição, conserva o Label e omite a linha redundante da seção.
Normaliza aspas, espaços e ×/x somente para a comparação de apresentação.
Não grava Label, DisplayName, Profile ou qualquer outra propriedade, nem altera
o helper ou a formatação das outras ferramentas.

## Transação, preview e persistência

Mantém-se uma única transação bilateral: preparar/revalidar os dois candidatos,
gravar somente os slots escolhidos, recomputar ambos, verificar cada saída e
o contato definitivo, confirmar. Uma falha tardia aborta as duas gravações;
um único Undo desfaz ambos e um Redo restaura ambos.

O preview usa as Shapes reais dos candidatos, branches Coin temporários e
máscaras existentes; não cria objetos de documento. Cancelar antes ou depois
da autorização preserva os membros e o histórico. A limpeza de timer, seleção,
branches e máscaras continua centralizada no ciclo de vida anterior.

Após Undo, uma nova tarefa pode ser usada sem recompute manual. A nova sessão
exige novamente escolha e autorização. Após Redo, as pontas já ajustadas ficam
ocupadas, conforme o contrato anterior. A limitação nativa de perda da pilha
Redo anterior após escrita seguida de abort, demonstrada no fechamento do MVP,
continua aplicável; não foi introduzido mecanismo alternativo de histórico.

## Casos aceitos e recusados

| Caso | Política |
| --- | --- |
| Encontro terminal convencional | Fluxo anterior, sem controles de aparo |
| J interior em A ou B | Escolha explícita e uma autorização global da configuração |
| J interior em ambos | Duas escolhas e uma autorização global; aceitar somente com geometria válida |
| Início/Fim e ordem A/B invertida | Material retido segue a ponta escolhida; ordem não altera o resultado equivalente |
| Sobras grandes | Sem limite artificial; valor completo informado, consentimento obrigatório |
| T/cruzamento sem autorização | Bloqueado, sem modificação automática da peça passante |
| Ponta escolhida ocupada | Recusado; não sobrescreve ajuste anterior |
| Ponta oposta ocupada | Preservada se válida e suficientemente distante |
| Corte extingue/inverte a peça ou tampa alcança ponta oposta | Recusado |
| Sem contato completo, seção/orientação incompatível, sólidos inválidos | Recusado |
| Paralelos, colineares, reversos, precisão insuficiente | Recusado |
| Filhos de treliça, Linked, composição, perfis diferentes | Restrições do MVP preservadas |

T automático verdadeiro, associatividade, múltiplos participantes, encontros
espaciais complexos e novos tipos de ligação permanecem fora do escopo.

## Arquivos do incremento

- `freecad/SteelStructures/member_miter_geometry.py`: inspeção separada da
  decisão, escolha explícita e consentimento no resolvedor puro.
- `freecad/SteelStructures/interactive/member_miter_controller.py`: escolhas,
  tokens de autorização e alcance axial; mesmo pipeline e transação.
- `freecad/SteelStructures/interactive/member_miter_task_panel.py`: controles
  contextuais, atualização imediata e proteção entre exibição/clique/OK.
- `tests/test_member_miter_geometry.py`, `tests/test_member_miter_controller.py`,
  `tests/test_member_miter_task_panel.py`: casos direcionados e regressões.
- `tests/manual_member_miter_joint.py`: extensão do gate existente com a matriz
  de aparo, autorização, rollback, preview, histórico e FCStd.
- Este relatório.

Nenhuma alteração nos estudos Gusset, StructuralPlate, documentação intermediária,
catálogos, experimentos existentes ou metadados de release. Sem `git add`, commit,
push, merge, tag ou release.

## Validação automatizada original do aparo

Python direcionado, sem descoberta completa:

```powershell
python -B -m unittest tests.test_member_miter_geometry tests.test_member_miter_controller tests.test_member_miter_task_panel tests.test_member_miter_preview tests.test_member_plane_cut tests.test_member_orientation tests.test_member_associative_adjustment tests.test_member_adjustment_geometry tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_adjustment_reference tests.test_member_adjustment_task_panel
python scripts/check_project.py
git diff --check
```

Resultado da implementação original: **184 testes aprovados, zero falhas e zero skips**.
`check_project.py` e `git diff --check` aprovados. A suíte completa fica
reservada para o fechamento técnico solicitado; não foi executada nesta etapa.

Gate nativo FreeCAD 1.1.4, executado com perfil isolado:

```powershell
python scripts/run_member_miter_joint_gate.py --theme Classic --output-root test-results/miter-trim --timeout 600
python scripts/run_member_miter_joint_gate.py --theme "FreeCAD Dark" --output-root test-results/miter-trim --timeout 600
python scripts/run_member_miter_joint_gate.py --theme OpenDark --output-root test-results/miter-trim --timeout 600
```

| Tema | Checks | Resultado | Pasta em `test-results/miter-trim/` |
| --- | ---: | --- | --- |
| Classic | 2.726 | OK | `1792835976641915800_Classic_akc_lq0j` |
| FreeCAD Dark | 2.726 | OK | `1792836084879474100_FreeCAD_Dark_524wo812` |
| OpenDark | 2.726 | OK | `1792836183294029900_OpenDark_zvn4b9p1` |

**8.178 checks finais, três sucessos**, FreeCAD 1.1.4, retorno zero, nenhum
timeout, zero erros capturados de callbacks e filtros de logs nativos vazios.
Uma campanha Classic inicial passou com 2.692 checks em
`1792835829761443800_Classic_q8es8kqx`; ela antecede a proteção adicional de
consentimento antes do polling e os testes adicionais de rollback com aparo.
Não integra a soma da campanha final. Não houve falha de gate nativo nesta rodada.

`focused.log`, `check-project.log`, `diff-check.log` e `verification.json`,
na mesma raiz de evidências, registram comandos, resultados, HEAD, índice
e hashes dos oito arquivos do incremento. Os três manifestos nativos foram
comparados às fontes finais; nenhuma divergência no código executado.

A matriz nativa adicional contém 49 pares: SHS em 60°/90°/120°, quatro
combinações Start/End e aparo em A/B/ambos; W, U, Ue e RHS nos três ângulos
com ambos os aparos; sobras de 10.000/8.000 mm. Cada par verifica invariância
A/B, valores, avaliação sem mutação, comparação BRep preview/confirmado,
um Undo/Redo e restauração FCStd com sólidos equivalentes. Inclui extensão
livre e ajuste oposto fixo preservado.

Os cenários Qt reais cobrem autorização separada, escolha de outro lado,
cancelamento antes/depois, revogação por ponta/inputs, clique antes do polling,
OK nativo, branches Coin, preview/resultado e reaplicação imediata após Undo.
Rejeições nativas cobrem ponta ocupada, extinção geométrica, contato
incompatível, paralelos e eixos afastados. A campanha anterior do MVP também
é repetida integralmente pelo mesmo gate. Checks de gate não equivalem a
testes unitários independentes e não substituem a validação manual do usuário.

As capturas `controlled-trim-window.png` e `controlled-trim-preview.png` dos
três temas foram inspecionadas: blocos A/B e valores legíveis, seleção/consentimento
separados, sucesso verde e ambos os sólidos no render. A captura composta da
janela pode omitir ou distorcer o viewport OpenGL, como já documentado no MVP;
ela foi usada para avaliar o painel. Os renders separados `saveImage` exibem
as duas geometrias sem esse artefato. Isso é inspeção visual das evidências
automatizadas; não é validação manual interativa pelo usuário.

A revisão técnica independente confirmou a representação sem migração e
identificou uma brecha antes do polling: um clique poderia autorizar um valor
novo que ainda não havia sido exibido. Ela foi corrigida e ganhou regressão
unitária e nativa (80→105 mm, exigindo novo clique). Também foi removida uma
quantidade nominal contraditória no diagnóstico puro quando havia extensão.
A revisão posterior confirmou ambos os ajustes e não identificou bloqueador.
O primeiro teste novo de grande sobra falhou por comparação exata de floats;
foi corrigido para comparação aproximada, mantendo as verificações de valor
e a matriz integral. As execuções direcionadas finais passaram sem skips.

## Refinamento de interface — 24/10/2026

Escopo desta rodada: controlador (somente contrato de consentimento), painel,
testes do controlador/painel, gate nativo existente e este relatório. Sem mudança
no resolvedor puro, PlaneCut, critérios geométricos, persistência ou transação.
A comparação com os manifestos da campanha anterior comprova a preservação
dos módulos geométricos. Estudos e experimentos locais permanecem intactos.

A revisão independente confirmou o token global e a proteção no clique/OK,
sem bloqueador. A observação sobre perfil no meio/início de Label personalizado
foi incorporada à deduplicação e recebeu regressão.

Python direcionado: mesmo comando explícito dos 12 módulos acima, agora com
**187 testes aprovados, zero falhas e zero skips**. Suíte completa não executada.
`python scripts/check_project.py` e `git diff --check` aprovados.

Gates nativos do refinamento:

```powershell
python scripts/run_member_miter_joint_gate.py --theme Classic --output-root test-results/miter-trim-ui --timeout 600
python scripts/run_member_miter_joint_gate.py --theme "FreeCAD Dark" --output-root test-results/miter-trim-ui --timeout 600
python scripts/run_member_miter_joint_gate.py --theme OpenDark --output-root test-results/miter-trim-ui --timeout 600
```

| Tema | Checks | Resultado | Pasta em `test-results/miter-trim-ui/` |
| --- | ---: | --- | --- |
| Classic | 2.824 | OK | `1792838486223199300_Classic_3u3nbxvg` |
| FreeCAD Dark | 2.824 | OK | `1792838590628909300_FreeCAD_Dark_qcdhl6jl` |
| OpenDark | 2.824 | OK | `1792838737415396200_OpenDark_divchrbp` |

**8.472 checks finais, três sucessos**, FreeCAD 1.1.4, retorno zero, sem timeout,
sem erros de callbacks e sem erros nos filtros de logs nativos. Os manifestos
da campanha final correspondem às fontes entregues. `verification.json` nesta
raiz consolida resultados, comparação das fontes, HEAD e índice.

A primeira execução Classic (`1792838221332639100_Classic_w9dlg18q`) parou após
2.783 checks por uma suposição do teste de que a descrição mais longa habilitada
teria pelo menos 25 caracteres. O gate agora usa a maior descrição real do
catálogo e verifica conteúdo integral e altura de uma linha, sem esse limite
arbitrário de texto. Não se tratou de falha de aparo ou autorização; a execução
não é contabilizada como passe. As evidências da tentativa foram preservadas.

A segunda Classic (`1792838357877917500_Classic_rqxj63bw`) parou após 2.814
checks ao trocar o par para perfis incompatíveis. O controlador já revogava o
consentimento e bloqueava a operação, mas a checkbox escondida mantinha uma
marca visual antiga porque a validação falhava antes de reconstruir os controles.
A sincronização da checkbox agora ocorre no início de `_refresh`, protegida
contra callbacks e antes do preflight. A regressão também verifica esse estado
em falha de elegibilidade. Nenhuma falha foi ignorada ou tratada como passe.

Além da matriz anterior de 49 pares, rollback, Undo/Redo e FCStd, os cenários
nativos novos cobrem A/B/ambos com uma checkbox, habilitação só após todas as
escolhas, preview bilateral e OK, revogação por extremidade/membro/excedente,
ausência de ressurreição de consentimento, mesmo membro/ponta e preservação após
renomear, cor, modo de exibição, visibilidade, paleta, resize e troca de vista.
Cobrem Label personalizado longo, perfil mais longo habilitado, ausência de
duplicação e layout de uma linha com tooltips completos. As capturas
`global-trim-{A,B,AB}-window.png` registram o painel composto por tema.

As capturas dos três temas foram inspecionadas: títulos discretos, alinhamento
das linhas, uma checkbox global, valores únicos, nomes longos em uma linha e
perfil secundário sem duplicação. Os diagnósticos semânticos mantiveram os
checks de contraste do gate. O artefato OpenGL das capturas de janela continua
limitando sua utilização ao painel, conforme explicado anteriormente; os renders
separados e as comparações BRep verificam as candidatas. Esta inspeção de
evidências automatizadas não substitui a nova aprovação visual do usuário.

## Refinamento final de apresentação — 24/10/2026

Aprovação manual recebida para a interface/global anterior e para a geometria.
Esta rodada altera somente o painel, seus testes de apresentação e o runner/probe
nativo. O controlador, resolvedor, cálculo de excedentes/planos, PlaneCut,
preview, persistência e transação foram preservados. Um diagnóstico independente,
somente leitura, auxiliou a identificar o recolhimento do dock durante capturas;
não houve implementação paralela.

Foram recuperados os dois valores na própria lista, removida a coluna à direita,
adicionada atualização ao abrir o popup e mantidos os dados internos das opções.
O agrupamento horizontal de A/B usa uma divisória Qt simples; nomes principais
agora têm negrito, sem alterar a elisão, tooltips, Label ou propriedades dos membros.
Trocas materiais continuam revogando o consentimento global; abrir lista,
redimensionar ou outras alterações de apresentação não concedem/revogam autorização.

Testes Python: os mesmos 12 módulos direcionados listados acima, incluindo quatro
regressões novas para formatação/IDs, atualização de ambas as alternativas,
ordem atualização→popup e ausência de reconstrução do editor estável. Logs em
`test-results/miter-final-ui/{python-checks.json,focused.log,check-project.log,diff-check.log}`.
**191 testes aprovados, zero falhas e zero skips.** `check_project.py` e
`git diff --check` aprovados. Suíte completa não executada.

O runner recebeu opções exclusivamente de QA: `--ui-only` para a verificação
focada de apresentação e `--scale-factor` para solicitar a escala no processo
isolado. A escala real e o DPI são registrados por Qt em `presentation-metrics.json`.
Nenhuma preferência de DPI/tema da sessão do usuário é gravada.

```powershell
python scripts/run_member_miter_joint_gate.py --theme Classic --output-root test-results/miter-final-ui --timeout 600
python scripts/run_member_miter_joint_gate.py --theme "FreeCAD Dark" --output-root test-results/miter-final-ui --timeout 600 --ui-only
python scripts/run_member_miter_joint_gate.py --theme OpenDark --output-root test-results/miter-final-ui --timeout 600 --ui-only
python scripts/run_member_miter_joint_gate.py --theme Classic --output-root test-results/miter-final-ui --timeout 600 --ui-only --scale-factor 1.5
```

| Gate final | Checks | Resultado | Pasta em `test-results/miter-final-ui/` |
| --- | ---: | --- | --- |
| Classic, regressão ampliada | 2.888 | OK | `1792841762573179400_Classic_a3qav2hu` |
| FreeCAD Dark, apresentação | 65 | OK | `1792841772757580500_FreeCAD_Dark_rk9hd2ig` |
| OpenDark, apresentação | 65 | OK | `1792841733280430300_OpenDark_wb5rmkz9` |
| Classic, apresentação a 150% | 65 | OK | `1792841737096909800_Classic_ur6v3mfd` |

**3.083 checks finais**, FreeCAD 1.1.4, quatro sucessos, sem timeout, sem erros
de callbacks e sem erros nos filtros de logs nativos. As fontes de cada campanha
final correspondem às entregues. A comparação com o manifesto da interface
aprovada identifica somente `member_miter_task_panel.py` no pacote de produção.
`verification.json` consolida hashes, resultados, tentativas, HEAD e índice.

Todos os cenários verificaram larguras de **280 e 360 pixels lógicos**, nomes
longos, alinhamento vertical A/B e botão, linha Qt curta, IDs e opções indisponíveis.
Os valores selecionados couberam nos campos, sem truncamento. Na escala solicitada
de 150%, Qt confirmou `devicePixelRatio=1.5` e DPI lógico 96; não se alterou a
configuração de monitores do Windows. Essa é uma prova de escala Qt, não uma
certificação de todas as configurações físicas de monitores/DPI.

O primeiro Classic focado (`1792840129062917900_Classic_egmfruk7`) aprovou 44
checks antes do acréscimo de medições de contraste dos três estados. A campanha
final acrescenta essas medições e conserva o cenário de painel estreito, nomes
longos, valores fechados/abertos, ponta ocupada, revogação entre polls e cancelamento.
Capturas `final-members-{280,360}-{panel,window}.png`, `final-options-popup-*.png`
e `final-options-list-{280,360}-{0,1}.png` (listas diretamente capturadas)
acompanham cada gate. A regressão ampliada Classic também repete a matriz de
49 pares, preview/resultado, rollback, Undo/Redo e FCStd já aprovada.

As capturas finais do painel e das listas A/B foram inspecionadas nos três
temas e a 150%: valores presentes ao abrir/fechar, nome principal em negrito,
perfil secundário, identificação integrada e pontas ocupadas desabilitadas.
Capturas de janela continuam sujeitas ao artefato OpenGL já documentado; os
grabs diretos do painel/listas foram usados para complementar a inspeção.

As tentativas intermediárias estão preservadas e não são contabilizadas na
campanha final. Houve interrupções nas medições de visibilidade/contraste porque
o overlay do FreeCAD recolhia Tasks para fora da janela durante `processEvents`
(diagnóstico em x=1815 para janela de largura 1800), e depois ao capturar a
transição animada entre popups A/B. O diagnóstico por hierarquia Qt e animações,
conferido independentemente, identificou as causas. No **processo isolado de QA**,
o comando nativo `Std_DockOverlayAll` fixa o dock quando ele está em overlay,
e `UI_AnimateCombo=False` permite capturar a lista assentada. As verificações
de visibilidade, conteúdo e contraste foram mantidas. Não se modificaram cores,
preferências do usuário ou o ciclo de vida aprovado da ferramenta para contornar
a captura. Ensaios experimentais de medição foram revertidos; nenhum resultado
falho foi convertido em passe. `all_native_attempts` registra os detalhes.

## Roteiro de inspeção visual final

1. Reabrir em uma sessão atualizada do FreeCAD para carregar o código local.
   Em Classic, criar dois membros iguais Detailed a 90°, com 80 mm de sobra
   axial em A. Abrir Meia-esquadria: sem preview/OK até escolher Início/Fim
   e autorizar. Conferir os valores das duas alternativas na lista e o valor
   selecionado no campo fechado, sem coluna duplicada. Conferir a parte preservada;
   cancelar e repetir.
2. Marcar **Autorizar os aparos indicados** e conferir os dois sólidos completos. Confirmar: apenas um
   Undo deve restaurar ambos. Reabrir após Undo sem recompute manual, escolher
   e autorizar novamente. Conferir Redo e reaplicação.
3. Repetir com sobra somente em B e depois em ambos. Escolher apenas uma das
   pontas necessárias deve manter a checkbox desabilitada. Após ambas as escolhas,
   um único clique autoriza o conjunto. Inverter A/B e experimentar Start/End mistos.
4. Conferir encontros a 60° e 120°, W/RHS/SHS/U/Ue compatíveis, sobra grande,
   extensão livre e ponta oposta ajustada. O valor inclui a extensão escolhida;
   o slot oposto deve permanecer intacto.
5. Trocar ponta ou alterar parâmetros: a autorização global deve ser revogada.
   Renomear, redimensionar ou trocar a vista não deve desmarcá-la. Conferir nome
   personalizado e seção sem repetição, nome principal em negrito, agrupamento
   horizontal A/B e botão centralizado, texto longo elidido e tooltip integral.
   Alterar extensão e abrir a lista antes do próximo poll: os dois valores devem
   ser atualizados e o consentimento anterior revogado. Ponta ocupada deve aparecer
   indisponível; as demais escolhas ainda dependem da validação geométrica do par.
   Um T sem escolha/consentimento, ponta ocupada, corte sem
   comprimento útil e seções sem contato devem permanecer bloqueados.
6. Salvar/reabrir FCStd e recomputar; conferir sólidos, massa, eixos nominais
   preservados e cortes fixos independentes. Mover um membro não move o parceiro.
7. Repetir legibilidade, controles contextuais, preview, Cancelar/Esc e OK nos
   temas FreeCAD Dark e OpenDark. Encontros convencionais não mostram controles
   de aparo. Conferir manualmente que não restam marcadores/objetos temporários.

**GO para inspeção visual final do usuário**, sem bloqueador conhecido nas
verificações realizadas. A confirmação visual desses dois ajustes permanece pendente.
A aprovação funcional e da autorização global anterior permanece registrada.
FreeCAD 1.1.3 e suíte completa não executados nesta etapa. O cálculo OCC continua
no thread da UI e casos numericamente inseguros são recusados conservadoramente.
Inspeção visual final e fechamento técnico com suíte completa
continuam necessários antes de commit. Nenhuma operação de publicação foi executada.
