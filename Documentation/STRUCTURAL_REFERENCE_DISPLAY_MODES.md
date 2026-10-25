# Modos de visualização estrutural

Data: 24/10/2026. Branch `develop/0.7.0`, HEAD publicado `f303f81`.
Incremento local sobre o MVP e seu refinamento visual, sem staging ou publicação.

Evolução posterior: [MVP de referências em primeiro plano](STRUCTURAL_REFERENCE_ON_TOP_MVP.md).
Esse relatório define a prioridade atual no Estrutural/Raio X; os resultados e
limites de profundidade abaixo permanecem como histórico das etapas anteriores.

**Atualização UX/UI:** o seletor descrito no histórico abaixo foi substituído por
três botões diretos. O estado atual, os novos parâmetros de linha e os resultados
estão na seção final [Refinamento UX/UI](#refinamento-uxui--botões-diretos-e-linhas).

**GO para validação manual**, com os limites de seleção, transparência nativa e
desempenho descritos neste relatório. Os quatro gates finais FreeCAD 1.1.4 passaram
sem erros nativos. A aprovação visual do usuário e a suíte completa de fechamento
continuam pendentes para este incremento.

## Escopo e contratos

Foram consultados integralmente o
[estudo arquitetural](STRUCTURAL_REFERENCE_ARCHITECTURE_STUDY.md), o
[MVP](STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md) e o
[refinamento visual](STRUCTURAL_REFERENCE_VISUAL_REFINEMENT.md), além dos módulos
reais de apresentação, comandos e previews de Ajuste/Meia-esquadria.

A solicitação atual autoriza ampliar a apresentação para os sólidos externos à
bancada. Isso não amplia as fontes de eixos: continuam sendo referências nominais
dos membros elegíveis do MVP. Não há conectividade confirmada, snapping, estações,
modelo analítico, eixo centroidal ou representação esquemática nova.

Start/End, Placement, Shape, propriedades paramétricas, schema, catálogos, engine,
ajustes, cortes, treliças e Grid não foram alterados. Não há novos objetos de
documento, propriedades persistentes ou migração. A cor dos eixos passou a
**`#55C8D0`**, preservando larguras 3/5, padrão `0x00FF`, espaçamento e escala DPR.
As extremidades continuam circulares, laranja, preenchidas, com contorno branco
e proteção escura. São extremidades geométricas nominais, não nós analíticos.

## Interface e comportamento

Um único comando novo, `SteelStructures_StructuralDisplayMode`, abre um menu
compacto na barra/submenu de Visualização já existentes. Há três opções:

| Modo | Apresentação | Seleção |
| --- | --- | --- |
| Físico | Apresentação original dos objetos; eixos/extremidades opcionais | Nativa |
| Estrutural | Ramo físico temporariamente mascarado; referências nominais elegíveis | Pela árvore; as referências continuam não selecionáveis |
| Raio X | Cópia gráfica translúcida dos objetos físicos visíveis; referências destacadas | Picking físico e realce nativos |

O estado é um enum exclusivo. O menu marca o modo solicitado, e a ação recebe
texto/tooltip atualizados e ícones distintos para cada modo. Durante suspensão,
o texto inclui “pausado”. Os dois comandos anteriores mantêm seus IDs, ícones,
tooltips nominais e independência. Não foi criado painel de personalização.

Cada documento vivo conserva seu modo e duas configurações transitórias:
as escolhas do Físico e as escolhas do preset. Entrar do Físico em um preset
ativa inicialmente ambas as camadas, sem perder as escolhas anteriores.
Alternar Estrutural/Raio X conserva os toggles do preset; voltar ao Físico restaura
os toggles do Físico. É permitido desligar ambos mesmo em Estrutural, produzindo
uma vista sem referências, sem excluir ou ocultar objetos por propriedades.

O escopo do modo é **documento**, coerente em todas as suas vistas 3D, com recursos
gráficos separados por viewport. Só o documento ativo recebe máscara/Raio X.
Ao alternar documento, a apresentação física do anterior é restaurada; seu preset
solicitado fica guardado para quando voltar. Tarefas, edição e comandos Draft
ativos suspendem a máscara/translucidez. A sobreposição aditiva das referências
pode continuar visível durante essas pausas. Desativar a bancada limpa tudo.

## Investigação e estratégia escolhida

As provas foram feitas em processos FreeCAD 1.1.4 isolados, antes de introduzir
os modos em produção. Confirmaram roots de cena distintos por viewport e
ViewProviders compartilhados entre vistas.

| Alternativa | Avaliação |
| --- | --- |
| Gravar Visibility/Transparency/DisplayMode temporariamente | Rejeitada: propriedades compartilhadas, save/Modified e conflito com edições do usuário |
| Reusar SwitchNode de cada membro, como nos previews | Rejeitada para estes presets: máscara compartilhada entre vistas e restauração concorrente |
| Override global de material | Rejeitado: risco de afetar cores e outras camadas, sem resolver corretamente todos os materiais |
| `viewer.setOverrideMode()` | Não oferece o isolamento/material exigidos; percorre os ViewProviders do documento |
| Substituir todo o scenegraph do viewer | Rejeitado: pode divergir de picking, edição e captura nativos |
| Wrapper local do ObjectGroup + cópia Coin | **Adotado:** mantém fontes nativas intactas, reversível por vista, sem propriedades escritas |

O FreeCAD 1.1.4 mantém um `ObjectGroup` por vista para objetos físicos. Os seus
ViewProviders continuam filhos diretos desse grupo: a implementação envolve
**o grupo**, sem mover os roots individuais ou substituir seu conteúdo. Assim,
as inserções/remoções nativas continuam usando o mesmo grupo. O grupo de realce
`GroupOnTop` é tratado separadamente no Estrutural.
[Fonte FreeCAD 1.1.4](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Gui/View3DInventorViewer.cpp).

Um override simples de transparência não foi usado: Coin documenta a associação
dos bits de override de cor difusa/transparência e um escape por variável global
de processo. A bancada não introduz essa configuração global.
[SoMaterial](https://www.coin3d.org/coin/classSoMaterial.html).

### Estrutural

Dois switches próprios, locais à viewport, mascaram ObjectGroup e GroupOnTop.
Não se escreve em Visibility nem no SwitchNode dos membros. A seleção existente
é conservada, mas não desenha de volta o sólido selecionado. Não há picking das
referências nem do físico mascarado; a árvore é o caminho de seleção desta etapa.
Grid e demais elementos pertencentes ao ramo físico também são mascarados.
Elementos nativos de navegação/HUD fora desse ramo permanecem como estão.

### Raio X

O ramo original permanece com `SoDrawStyle.INVISIBLE` somente no wrapper local,
preservando o picking nativo. Uma cópia Coin não selecionável representa o físico.
São mantidos transforms, switches de visibilidade, coordenadas, cores e arrays
de materiais. Somente os materiais da **cópia** recebem transparência mínima 78%;
uma transparência original maior é mantida. Alpha de cores empacotadas também é
tratado na cópia. Objetos previamente ocultos não são revelados.

Não há tesselação OCC, execução de membro ou cópia de BRep para o modo. A cópia é
da representação gráfica. A profundidade, câmera, clipping e ordenação de
transparência continuam nativos; não há SoAnnotation, depth test desligado ou
passagem que ponha indiscriminadamente eixos sobre toda a cena.

O realce de seleção/preselection nativo pode aparecer opaco. Ele é feedback de
seleção, sem alteração do material original. Superfícies translúcidas também
podem atenuar a cor aparente das referências pela composição normal do Coin.

## Reversibilidade, cache e ciclo de vida

- `ViewportPresentation` possui seus wrappers, cópia e referências nativas
  explícitas. A cópia retornada por `copy()` recebe `ref()` e é liberada com
  `unref()` após sair da cena. Cleanup e close são idempotentes.
- Voltar ao Físico recoloca os mesmos ramos originais. Nenhum snapshot antigo de
  propriedades é restaurado sobre uma edição posterior do usuário.
- Uma revisão de apresentação, alimentada pelos observers App/Gui, invalida a
  cópia em mudanças reais, inclusive de objetos externos. A fila Qt agrupa eventos.
  A cópia é reconstruída por viewport quando a revisão muda.
- Não se usa o node ID Coin como revisão do serviço: seleção/preselection também
  pode modificá-lo. Hover, câmera e o timer de vistas não refazem a cópia estável.
- A infraestrutura existente reconcilia vistas, documento ativo e suspensão em
  tarefas. Fechar uma vista inativa libera seus recursos na reconciliação, sem
  manter desenho numa viewport destruída.
- O observer **GUI** de exclusão do documento libera os ramos sincronamente antes
  de os ViewProviders e vistas serem destruídos. O sinal nativo ocorre antes do
  destrutor de Gui::Document; o callback App tardio não é usado sozinho para isso.
  [Application.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Gui/Application.cpp),
  [DocumentObserverPython.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Gui/DocumentObserverPython.cpp).
- Falha de cópia ou ausência do ramo nativo esperado retorna ao Físico e avisa no
  console. Não há fallback que grave propriedades. Se outro recurso reparentear
  um wrapper, só o conteúdo próprio é neutralizado, sem reconstruir a árvore alheia.
- Undo/Redo invalida apresentação e mantém o replay nominal aprovado do MVP.
  Reabrir FCStd começa em Físico, sem flags ou helpers persistidos.

## Arquivos desta rodada

Inventário relativo ao snapshot local do início desta etapa, que já continha
MVP e refinamento sem commit. **5 arquivos modificados e 7 novos**:

| Arquivo | Estado / responsabilidade |
| --- | --- |
| `freecad/SteelStructures/interactive/structural_reference_view.py` | Modificado: turquesa, estado dos modos, revisão, suspensão e cleanup GUI |
| `freecad/SteelStructures/interactive/structural_reference_commands.py` | Modificado: menu único e tooltips |
| `freecad/SteelStructures/interactive/structural_reference_modes.py` | Novo: apresentação reversível por viewport |
| `Resources/Icons/StructuralDisplayMode.svg` | Novo: Físico |
| `Resources/Icons/StructuralDisplayAxes.svg` | Novo: Estrutural |
| `Resources/Icons/StructuralDisplayXray.svg` | Novo: Raio X |
| `tests/test_structural_reference_view.py` | Modificado: presets, suspensão, revisão, callbacks e falha |
| `tests/test_structural_reference_modes.py` | Novo: ownership, materiais, cache e rollback gráfico |
| `tests/manual_structural_reference_visualization.py` | Modificado: integração dos gates, galerias e desempenho Raio X |
| `tests/manual_structural_display_modes.py` | Novo: gates dos modos |
| `scripts/run_structural_reference_visualization_gate.py` | Modificado: manifesto inclui novo gate e ícones |
| `Documentation/STRUCTURAL_REFERENCE_DISPLAY_MODES.md` | Novo: este relatório |

`init_gui.py` não precisou mudar nesta rodada: já consome a lista retornada pelo
registrador. Resolver nominal, engine física e todos os módulos das demais
ferramentas permanecem idênticos ao início desta etapa.

## Testes e evidências

### Python e integridade

**366 testes direcionados aprovados**, 2,420 s, sem failures, errors ou skips.
São 21 módulos: os 20 da campanha anterior mais `test_structural_reference_modes`.
Há 12 testes adicionais nesta rodada: sete no módulo novo e cinco no serviço.
Cobrem preservação dos toggles, documentos, suspensão, provider expirado, cleanup
GUI pré-destruição, cores/alpha, identidade dos ramos, pins balanceados, cache,
falha de cópia e reparenting externo. Regressões de criação, pilares, Grid,
treliças, Ajuste, preview, Meia-esquadria e PlaneCut continuam passando.

```powershell
python -B -m unittest -v tests.test_structural_reference_modes tests.test_structural_reference tests.test_structural_reference_view tests.test_general_tools tests.test_grid_command tests.test_member_axis_source tests.test_member_axis_creation tests.test_member_placement tests.test_member_orientation tests.test_column_command tests.test_draft_native_member_tool tests.test_grid_object tests.test_grid_view tests.test_truss_copy tests.test_truss_lifecycle tests.test_truss_apply_session tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_miter_controller tests.test_member_miter_preview tests.test_member_plane_cut
python scripts/check_project.py
git diff --check
```

`check_project.py` aprovado. Whitespace foi conferido também por `--no-index
--check` para os arquivos locais não rastreados; UTF-8/newline e XML dos SVGs
verificados. A suíte completa foi reservada para o fechamento após validação manual.

### Gates nativos finais — FreeCAD 1.1.4 / Windows

| Tema | DPR | Execução | Checks | Resultado |
| --- | --- | --- | --- | --- |
| Classic | 1,0 | `1792871727424013600_Classic_ghbadpgj` | 209 | PASS |
| FreeCAD Dark | 1,0 | `1792871752599353800_FreeCAD_Dark_6z6mt4z3` | 209 | PASS |
| OpenDark | 1,0 | `1792871927006203900_OpenDark_y9i0ocdb` | 209 | PASS |
| OpenDark 150% | 1,5 | `1792871827988571900_OpenDark_f84mxfez` | 209 | PASS |

**836 verificações**, saída 0 nos quatro processos, sem timeout, callbacks Python/Qt
ou erros nativos capturados. Os 161 hashes de fontes/recursos são iguais nos quatro
manifestos e correspondem ao workspace final.

Comandos, usando o runner existente ampliado:

```powershell
python scripts/run_structural_reference_visualization_gate.py --theme Classic --output-root test-results/structural-display-modes/native
python scripts/run_structural_reference_visualization_gate.py --theme "FreeCAD Dark" --output-root test-results/structural-display-modes/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --output-root test-results/structural-display-modes/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --scale-factor 1.5 --output-root test-results/structural-display-modes/native
```

A campanha mantém os gates anteriores e acrescenta menu real, dez ciclos
Físico→Estrutural→Raio X→Físico, ausência de Modified/Undo, transparência prévia,
arrays de cores por face, objetos ocultos, Part e Mesh externos, App::Part, Grid,
duas vistas, fechamento de viewport inativa, edições visuais/geométricas,
inserção/exclusão, Undo/Redo, suspensão em TaskDialog, documentos distintos,
desativação e FCStd salvo com Raio X ativo. Galerias W/U e treliças foram geradas
nos três modos. Renders e menus foram inspecionados nos três temas e em DPR 1,5.

Há também uma prova com **seis verificações** em callbacks sucessivos, retornando
ao main loop real entre fechamentos, sem `processEvents` manual:
`probe-1792871655221143700`, saída 0 e logs limpos. Exercita Mesh, duas vistas,
fechamento de viewport/documento em Raio X, reuso de Name e troca de bancada.

### Diagnósticos intermediários preservados

Não se consideraram aprovados runs com asserções passando mas erros nos logs.
Foram corrigidos ownership da prova inicial, reimportação do script lançador,
acesso a providers em destruição e preparação da fixture Qt. Runs intermediários
registraram Access violation no retorno ao event loop da fixture monolítica.

O gate agora despacha `DeferredDelete` após fechamentos retornarem, representando
os turnos de UI que o callback longo não entregava. Isso é procedimento de teste,
sem código equivalente inserido em produção nem supressão dos erros. A documentação
Qt explica o limite de `processEvents` em laços locais e o uso de `sendPostedEvents`.
[QCoreApplication](https://doc.qt.io/qt-6/qcoreapplication.html#processEvents),
[QObject::deleteLater](https://doc.qt.io/qt-6/qobject.html#deleteLater).
A causa nativa exata desses runs não foi atribuída conclusivamente à engine;
a prova adicional com turnos reais e os quatro gates finais ficaram limpos.

### Desempenho observado

Tempo inicial do Raio X, em ms por viewport; amostras locais, sem medição de p95/FPS:

| Tema | 100 membros | 1.000 membros |
| --- | --- | --- |
| Classic | 304,3 | 2.868,5 |
| FreeCAD Dark | 354,9 | 2.913,7 |
| OpenDark | 307,0 | 2.820,8 |
| OpenDark 150% | 279,3 | 4.471,9 |

O overlay conserva 24 nós. A cópia física contém 6.701/67.001 nós nesses ensaios
Simplified. A leitura compartilhada da treliça de 103 filhos continua uma vez por
lote. Preselection repetida não incrementou `copy_updates` em 100/1.000 membros.

**Limite relevante:** uma mudança real invalida a cópia agregada, que ainda é
reconstruída inteira. Em modelos grandes pode haver pausa perceptível, multiplicada
pelas vistas. Não se certifica interação fluida em milhares de membros ou várias
vistas; cache incremental por objeto é evolução futura, sem reescrever a engine.

## Limitações e validação pendente

1. Estrutural não oferece seleção/snaps dos eixos; usar a árvore. Membros Linked
   e outras categorias recusadas pelo MVP continuam sem referência desenhada.
2. Raio X preserva o realce nativo, eventualmente opaco. A composição translúcida
   pode alterar a cor aparente das linhas/pontos atrás do material. Não há passagem
   que ignore indiscriminadamente profundidade.
3. Escopo físico usa o ObjectGroup nativo, comprovado para membros, treliças,
   Grid, Part e Mesh. HUDs, previews e providers externos que deliberadamente não
   participem desse ramo não são reescritos; addons com scenegraph próprio exigem
   prova específica. Não se promete suporte universal a renderers externos.
4. Multiview é por documento, com uma cópia por viewport, não presets diferentes
   entre duas vistas do mesmo documento. A configuração não é persistida.
5. Certificado neste ambiente FreeCAD 1.1.4/Windows. Outros drivers, plataformas,
   DPI físico entre monitores, transparências complexas/texturas e clipping
   customizado exigem inspeção. Câmera e clipping seguem o viewer nativo.
6. Gates de suspensão usam TaskDialog válido; não foi refeito manualmente todo
   o fluxo de criação/Ajuste/Meia-esquadria nesta rodada. Seus módulos não mudaram
   e as regressões Python passaram. A interação real integra o roteiro abaixo.

## Roteiro manual

1. Em um pórtico W/U, deixar somente Eixos ligado no Físico. Escolher Estrutural,
   Raio X e Físico pelo menu; conferir ícone, estado e restauração dos toggles.
2. Observar treliças, orientação espacial, zoom e órbita. Conferir turquesa,
   tracejado e círculos laranja/branco; não interpretar coincidência como conexão.
3. Misturar perfis de cores diferentes, transparência prévia, caixa Part, Mesh,
   Grid e objeto oculto. Verificar Raio X sem revelar o oculto. Editar cor e
   transparência durante o modo e retornar ao Físico: conservar a edição atual.
4. Selecionar pelo sólido em Raio X e pela árvore em Estrutural. Observar o realce
   nativo; abrir/cancelar Criar Membro/Pilar, Ajuste e Meia-esquadria. Durante a
   tarefa o preset pausa; ao sair, retorna sem interferir no preview/consentimento.
5. Mover/rotacionar/alongar membros e pais, usar Undo/Redo, criar/excluir e
   ocultar/exibir objetos. Conferir atualização sem recompute extra para o desenho.
6. Abrir duas vistas e dois documentos, alternar, fechar a vista inativa e o
   documento com Raio X ativo. Trocar de bancada e voltar; não deve restar máscara,
   transparência alterada, sessão antiga ou camada duplicada.
7. Salvar FCStd com modo ativo e reabrir: começar em Físico, com dados/aparência
   originais e sem helpers. Repetir nos três temas e em OpenDark 150%.
8. Avaliar a pausa inicial do Raio X no tamanho real dos modelos de trabalho.

## Preservação e decisão

Snapshot inicial: 612 arquivos. Os cinco arquivos existentes do inventário são as
únicas modificações; **607 arquivos externos à etapa permanecem idênticos**.
As sete adições são as enumeradas acima. HEAD e índice Git estão inalterados.
Estudos StructuralPlate/Gusset, treliças experimentais, FCStd, backups, documentação
anterior e evidências foram preservados. Nada foi staged, commitado ou publicado.

Evidências: `test-results/structural-display-modes/` (logs, imagens, manifestos,
provas, snapshot inicial e conferência de integridade). Revisão técnica independente
de leitura não identificou bloqueador final; não substitui a inspeção do usuário.

**GO para validação manual dos modos e da cor turquesa**, com atenção à seleção no
Estrutural, realce do Raio X e custo da cópia em modelos grandes. Suíte completa
e decisão de commit ficam para o fechamento técnico após aprovação manual.

## Refinamento UX/UI — botões diretos e linhas

Rodada de 24/10/2026, sobre os modos locais já apreciados pelo usuário.
**GO técnico para validação manual do refinamento.** Nenhuma alteração de engine,
geometria, schema, persistência, fontes nominais ou apresentação física dos modos.
O histórico anterior permanece neste documento; esta seção prevalece para a UI
atual e o estilo das linhas.

### Interface atual

O seletor/menu foi removido da composição da bancada. A barra e o submenu
Steel Structures → Visualização passam a conter, nesta ordem:

| Botão | ID do comando | Ícone existente reutilizado |
| --- | --- | --- |
| Físico | `SteelStructures_DisplayPhysical` | `StructuralDisplayMode.svg`: cubo sólido |
| Estrutural | `SteelStructures_DisplayStructural` | `StructuralDisplayAxes.svg`: eixos e extremidades |
| Raio X | `SteelStructures_DisplayXRay` | `StructuralDisplayXray.svg`: contorno translúcido com eixo |
| Mostrar/Ocultar Eixos | `SteelStructures_ToggleMemberAxes` | Preservado |
| Mostrar/Ocultar Extremidades | `SteelStructures_ToggleMemberEndpoints` | Preservado |

Os três modos usam ações nativas checkable/NoTransaction. Somente o modo
solicitado fica marcado; os outros ficam desmarcados e continuam disponíveis para
troca rápida. Clicar novamente no botão já marcado reafirma seu estado, sem
desligá-lo. Marcação e tooltips seguem o documento ativo e o ciclo da bancada.
Durante uma tarefa, o modo solicitado continua marcado e seu tooltip informa
que está pausado, mantendo o contrato de suspensão anterior.

A exclusividade vem do enum do serviço existente. A sincronização bloqueia sinais
enquanto aplica o estado às QActions nativas, evitando uma segunda fonte de
verdade em Qt. Não há novos grupos Qt permanentes, menus temporários ou estilos
QSS próprios. O destaque checked/pressed é fornecido pelo tema.

Os toggles de eixos/extremidades continuam independentes. As escolhas do Físico
permanecem guardadas durante os presets e são restauradas ao voltar. Não foram
alterados `set_mode`, o resolvedor nominal, os wrappers de cena, as cópias Raio X,
o cache, os observers, a suspensão, a limpeza ou a persistência FCStd.

`init_gui.py` já monta a barra/submenu com a lista retornada pelo registrador;
por isso não precisou de nova alteração. Também não foi necessário redesenhar
os ícones: os três SVGs existentes já têm identidades diferentes e ficam intactos.
O comando antigo `SteelStructures_StructuralDisplayMode` deixa de ser registrado.
Reiniciar o FreeCAD é o roteiro recomendado para carregar essa nova composição;
não há migração de barras personalizadas ou preferências do usuário nesta etapa.

### Estilo da linha

| Parâmetro | Antes | Agora |
| --- | --- | --- |
| Cor | `#55C8D0` | Preservada |
| Largura principal | 3 | 2,5 |
| Largura do contorno escuro | 5 | 4,5 |
| Padrão Coin | `0x00FF`, fator 2 | `0x03FF`, fator 2 |
| Traço/intervalo em DPR 1 | Aproximadamente 16/16 pixels | Aproximadamente 20/12 pixels |
| Principal/contorno em DPR 1,5 | 4,5/7,5 | 3,75/6,75 |
| Traço/intervalo em DPR 1,5 | Aproximadamente 24/24 pixels | Aproximadamente 30/18 pixels |

O novo padrão tem dez bits ligados/seis desligados. O período total é preservado,
com traços 25% maiores e intervalos 25% menores. A linha fica discretamente mais
fina, mantendo contraste sobre fundos claros/escuros e o dimensionamento por DPR.
Os marcadores, mapas circulares, laranja, branco e diâmetros 15/13/9 (23/21/15 em
DPR 1,5) não mudaram. A política de profundidade e a composição Raio X permanecem
as aprovadas; nenhuma nova passagem gráfica foi introduzida.

### Inventário desta rodada

**Oito arquivos existentes modificados; nenhum arquivo novo de produção ou teste.**
Comparação contra o snapshot local do início deste refinamento, não contra o HEAD
que ainda não contém o sistema de visualização local completo.

| Arquivo | Alteração restrita |
| --- | --- |
| `freecad/SteelStructures/interactive/structural_reference_commands.py` | Três comandos diretos; remoção do QMenu |
| `freecad/SteelStructures/interactive/structural_reference_modes.py` | Somente metadados dos IDs/tooltips dos comandos |
| `freecad/SteelStructures/interactive/structural_reference_view.py` | Sincronização das três ações e constantes do estilo |
| `tests/test_structural_reference_view.py` | Registro, exclusividade, reclick e parâmetros visuais |
| `tests/test_general_tools.py` | Fixture da composição com os cinco comandos |
| `tests/manual_structural_display_modes.py` | Acionamento das QActions reais, estados exclusivos e capturas da barra |
| `tests/manual_structural_reference_visualization.py` | Expectativas nativas das larguras |
| `Documentation/STRUCTURAL_REFERENCE_DISPLAY_MODES.md` | Aviso de atualização e esta seção |

### Verificação Python e integridade

**368 testes direcionados aprovados**, 2,410 s, sem failures, errors ou skips.
São os mesmos 21 módulos da campanha de modos, com dois testes adicionais para
registro dos cinco comandos/ausência do seletor, ícones distintos, exclusividade
e reclick do botão selecionado. Os testes existentes continuam cobrindo toggles,
restauração do Físico, documentos, falhas, cache, Undo/Redo e cleanup.
O teste de estilo verifica `0x03FF`, dez bits ligados e larguras nas duas escalas.

```powershell
python -B -m unittest -v tests.test_structural_reference_modes tests.test_structural_reference tests.test_structural_reference_view tests.test_general_tools tests.test_grid_command tests.test_member_axis_source tests.test_member_axis_creation tests.test_member_placement tests.test_member_orientation tests.test_column_command tests.test_draft_native_member_tool tests.test_grid_object tests.test_grid_view tests.test_truss_copy tests.test_truss_lifecycle tests.test_truss_apply_session tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_miter_controller tests.test_member_miter_preview tests.test_member_plane_cut
python scripts/check_project.py
git diff --check
```

`check_project.py` aprovado. Whitespace dos oito arquivos, inclusive os ainda não
rastreados, conferido também com `git diff --no-index --check`, leitura UTF-8 e
newline final. A suíte completa não foi executada nesta etapa de UI.

### Gates nativos finais — FreeCAD 1.1.4

| Tema | DPR | Execução | Verificações | Resultado |
| --- | --- | --- | --- | --- |
| Classic | 1,0 | `1792880423466675900_Classic_lm2xw34p` | 217 | PASS |
| FreeCAD Dark | 1,0 | `1792880488950573100_FreeCAD_Dark_of9khptk` | 217 | PASS |
| OpenDark | 1,0 | `1792880357221178400_OpenDark_yczol59d` | 217 | PASS |
| OpenDark 150% | 1,5 | `1792880563736897800_OpenDark_mi32fxs_` | 217 | PASS |

**868 verificações**, quatro saídas 0, sem timeout, erros nativos ou callbacks
Python/Qt. Os 161 hashes dos quatro manifestos coincidem com as fontes finais.

```powershell
python scripts/run_structural_reference_visualization_gate.py --theme Classic --output-root test-results/structural-display-toolbar-refinement/native
python scripts/run_structural_reference_visualization_gate.py --theme "FreeCAD Dark" --output-root test-results/structural-display-toolbar-refinement/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --output-root test-results/structural-display-toolbar-refinement/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --scale-factor 1.5 --output-root test-results/structural-display-toolbar-refinement/native
```

Os gates mantêm a regressão completa da linha anterior e verificam agora a barra
real com cinco ações, ausência do seletor, ícones distintos presentes, um único
modo marcado, reclick, disponibilidade dos outros modos e sincronização ao trocar
documentos. As capturas da barra mostram os três estados nos temas nativos.
Também foram inspecionados os renders W/U e treliças, em Físico, Estrutural e
Raio X. Isso não substitui a aprovação visual do usuário em seus modelos.

Um primeiro run diagnóstico não aguardava a habilitação das QActions após abrir
a fixture. O gate passou a aguardar a atualização nativa, como já fazia com os
toggles anteriores. Não foi necessário contorno em produção; esse run não integra
os resultados finais e está preservado na pasta de evidências.

### Limites preservados e roteiro manual

Não há ampliação de suporte ou promessa nova de desempenho. O Estrutural continua
com seleção pela árvore; o Raio X mantém o realce nativo eventualmente opaco e a
composição translúcida pode atenuar linhas atrás do material. O custo da cópia
gráfica em modelos grandes permanece como descrito no relatório anterior.
Arredondamento de largura/antialiasing depende do driver OpenGL.

1. Reiniciar o FreeCAD e ativar a bancada. Conferir os três botões Físico,
   Estrutural e Raio X, seguidos dos toggles de eixos/extremidades, sem o seletor.
2. Alternar os modos e reclicar no ativo: só um modo deve continuar marcado.
   Conferir os ícones e o destaque do tema, com os outros modos ainda clicáveis.
3. Em Físico, deixar só Eixos ligado. Entrar nos presets, alterar os toggles e
   voltar ao Físico: recuperar a escolha anterior sem alterar os sólidos.
4. Comparar linhas em perfis W/U e treliças, com zoom próximo/distante, sólidos
   presentes e Raio X. Avaliar traços maiores, intervalos menores e espessura.
   Confirmar marcadores laranja/branco e tamanho visual preservados.
5. Repetir em Classic, FreeCAD Dark, OpenDark e OpenDark 150%. Trocar documento,
   abrir/cancelar tarefa, usar Undo/Redo e desativar/reativar a bancada.

Snapshot desta rodada: 619 arquivos. Os oito arquivos do inventário são as únicas
alterações realizadas pelo incremento. **608 arquivos fora do incremento e do
conjunto de modelos/backups editado pelo usuário permaneceram idênticos**.
O usuário confirmou o salvamento concorrente de `tests/copiatreliça2.FCStd` e
solicitou preservar sua edição. O salvamento também rotacionou backups FCBak;
novas rotações desse mesmo modelo foram observadas durante a conferência.
A edição e os backups atuais foram mantidos, sem reversão. O snapshot em
`baseline/tests/` da pasta de evidências conserva cópias dos três caminhos
iniciais desse conjunto, inclusive dos backups rotacionados. Hashes observados
ficam nos registros de integridade; esses modelos/backups estão fora da entrega.

O renderer de modos e o controlador funcional permanecem iguais, à exceção dos
metadados/UI indicados. HEAD e índice Git não mudaram. Estudos Gusset/StructuralPlate,
experimentos e documentos anteriores não relacionados não foram alterados.

Evidências em `test-results/structural-display-toolbar-refinement/`.
**GO técnico para validação manual.** Sem staging, commit, push ou publicação.
