# Visualização de eixos nominais e extremidades — MVP

Data: 24/10/2026. Branch `develop/0.7.0`.
Base publicada preservada: `f303f81b76749d621e7dc58ae128fe7787a783eb`.
Implementação local, sem staging, commit ou publicação.

**GO para inspeção visual e validação manual.** Implementados dois comandos
independentes de apresentação, com leitura dos membros existentes e desenho
transitório. Os testes direcionados e os gates FreeCAD 1.1.4 passaram. A aprovação
manual desta interface ainda é necessária; os resultados automatizados não a
substituem. A suíte completa fica reservada ao fechamento após essa aprovação.

## Contrato seguido

O [estudo arquitetural](STRUCTURAL_REFERENCE_ARCHITECTURE_STUDY.md) foi lido
integralmente antes da implementação. Este incremento realiza sua etapa 1:
eixos **nominais**, extremidades e sobreposição aditiva com os sólidos presentes.
O início/fim de um eixo não é redefinido por cortes, offsets ou pela tampa física.
Não há inferência de centroide, modelo analítico ou conectividade estrutural.

Nenhuma propriedade de membro, schema, catálogo, Shape, Placement ou relação
paramétrica foi criada ou alterada para desenhar as referências. O núcleo de
membros, clipping, ajuste, meia-esquadria, fitting, treliças e Grid permanece igual
à base. Não há divisão, pontos internos, snap, Raio X, seção esquemática ou rótulos.

## Interface e apresentação

A barra **Steel Structures - Visualização** e o submenu
**Steel Structures → Visualização** contêm:

| Comando | ID | Efeito |
| --- | --- | --- |
| Mostrar/Ocultar Eixos | `SteelStructures_ToggleMemberAxes` | Linhas dos eixos nominais dos membros elegíveis visíveis no documento |
| Mostrar/Ocultar Extremidades | `SteelStructures_ToggleMemberEndpoints` | Círculo no início e quadrado no fim dos eixos nominais |

São comandos checkable, `NoTransaction`, sem painel de tarefa. O estado marcado
vem da sessão do documento ativo e usa a QAction nativa compartilhada por menu e
barra. Não são criadas ações paralelas para representar o mesmo comando.
Sem documento/vista 3D ou fora do ciclo ativo da bancada, ficam indisponíveis.

As opções são independentes: somente linhas, somente extremidades, ambas ou
nenhuma. Cada documento mantém suas opções na sessão. Desativar a bancada remove
os recursos e limpa as opções; voltar começa com tudo desligado. Reabrir FCStd
também começa desligado. Não há preferência ou propriedade persistente de modo.

Tooltips identificam o caráter nominal, a diferença em relação a centroide/análise
e a possibilidade de o sólido ocultar as referências. Recusas de elegibilidade
são agregadas em aviso no console, atualizado quando muda o resumo dos motivos;
não há diagnóstico por movimento do mouse nem um painel adicional.

### Decisões gráficas

- Linhas ciano com contorno escuro, em padrão traço-ponto (`0xE4E4`). Espessuras
  dos dois passes: 3,5 e 1,5. São parâmetros gráficos em tela, não dimensões em mm.
- Marcadores preenchidos em dois passes Coin: símbolo externo escuro 9×9 e
  preenchimento ciano 5×5. Início circular e fim quadrado distinguem a orientação
  sem texto. O tamanho é de bitmap em tela, independente do zoom geométrico.
- Paleta e estilo ficam concentrados no renderer para evolução posterior;
  não foi acrescentada uma interface de personalização nesta etapa.
- Um ramo `SoSeparator` por vista, com coordenadas em lote, dois switches e
  `SoPickStyle.UNPICKABLE`. O total é 21 nós Coin por vista, tanto com 100 quanto
  com 1.000 membros; a quantidade de coordenadas cresce com os membros.
- `SoDepthBuffer` mantém teste de profundidade, função LEQUAL e escrita de
  profundidade desligada apenas no ramo próprio. Não há `SoAnnotation`, máscara
  de objetos, alteração global de material ou passe que force desenho acima dos
  sólidos. Em Pivy, o campo `write` é acessado com `getField`, pois esse nome
  também identifica um método do nó.

**Oclusão é esperada.** Um eixo no interior de um perfil opaco pode não aparecer;
um ponto nominal pode estar atrás de uma tampa ou dentro do material. Zoom, câmera
e clipping seguem a cena nativa. A ferramenta não muda DisplayMode/Transparency
para revelar esses pontos. Uma inserção excêntrica ou um aparo pode deixar parte
do eixo nominal visível fora do sólido. O usuário também pode usar os modos de
exibição já existentes do FreeCAD, por decisão própria.

## Arquitetura implementada

### Adaptador de leitura

`structural_reference.py` não importa GUI, Part ou OCC e não acessa Shape ou
ViewObject. `resolve_member_axis()` devolve um resultado com descritor imutável
ou motivo explícito de recusa. O descritor contém Name no documento vivo,
extremos mundiais, frame real, nomes dos pais e categoria física.

Para membros independentes no domínio suportado:

```text
H = getGlobalPlacement() * inverse(Placement)
início mundial = H(StartPoint)
fim mundial = H(EndPoint)
frame mundial = rotação real de getGlobalPlacement()
```

StartPoint/EndPoint estão no espaço do pai. Placement.Base pode estar no início
**efetivo** após extensão/ajuste; aplicar esse Placement inteiro aos pontos
nominais duplicaria transformação. O leitor verifica finitude, comprimento
positivo, frame rígido destro e coerência de Z local com a direção nominal.
Não reconstrói o roll nem consulta arestas da Shape para obter o eixo.

São reconhecidas as classes reais da bancada nos módulos `freecad.SteelStructures`
ou `SteelStructures`; uma classe homônima de outro addon não é aceita.
As tolerâncias de leitura são 1e−7 mm para eixo nulo/comparações de coordenadas
e 1e−7 adimensional para o frame. Isso não é tolerância de conexão ou fabricação.

### Categorias e restrições

| Categoria | Suporte neste MVP |
| --- | --- |
| Membro Independent na raiz | Sim, quando válido e com frame coerente |
| Pilar Independent | Sim; usa o mesmo objeto e o mesmo contrato, sem pressupor que todo membro é vertical |
| Independent em App::Part rígido comum/aninhado | Sim; pais acumulados uma única vez |
| Membro com extensões, offsets ou cortes fixos anteriores | Sim; extremos continuam nominais, separados dos resultados efetivos |
| Filho físico de treliça válida | Sim, com registro/binding/realização aceita e estado controlado coerentes |
| Filho sob contêiner geométrico transformado | Recusado no domínio inicial não comprovado |
| Membro Linked a Draft Line | Recusado, inclusive na raiz, conforme delimitação da etapa 1 do estudo |
| App::Link, arrays, escala ou objeto externo | Não são fontes desta camada |
| Fonte inválida, incoerente ou pendente desconhecida | Omitida com motivo; nunca há recompute automático para torná-la elegível |
| Grid e grafo lógico da treliça | Não são desenhados por este MVP |

Em treliças, o leitor valida `GenerationOwner`, `GenerationKey`, `GeneratedMembers`,
bindings e `AppliedState`, item aceito, frame e `ControlledState`. O grafo não é
reconstruído nem editado. Desenha-se uma referência por **membro físico elegível**;
não se desenha também o grafo do owner, evitando uma representação concorrente.
Runs contínuos, componentes de conjuntos e nós lógicos não são reinterpretados
como conectividade analítica.

### Cache, eventos e ciclo de vida

`interactive/structural_reference_view.py` contém a sessão GUI e o renderer.
O registro é por documento vivo: Name serve para consulta, acompanhado da
verificação de identidade do documento. Há um renderer por vista 3D desse
documento, inclusive quando outro documento está ativo.

Na primeira ativação há uma varredura das fontes candidatas. Depois, callbacks
App invalidam membros alterados; eventos de pai/owner, mudança hierárquica e
histórico podem exigir nova varredura. O callback Gui de Visibility só atualiza
os buffers visíveis. Labels/cores não refazem a resolução geométrica. A inspeção
de candidatos usa TypeId e PropertiesList, evitando pedidos arbitrários de
subobjetos virtuais a contêineres nativos.

Uma fila Qt single-shot agrupa as mudanças antes de tocar Coin. Não há callback
de mouse ou câmera. Um timer de 500 ms reconcilia somente documentos/vistas e
estado dos comandos; em estado estável não enumera membros, não resolve eixos
nem copia o histórico de assinaturas. Ele também detecta fechamento de vista
inativa. A liberação dessa vista pode ocorrer no próximo tick, até cerca de
500 ms, sem manter desenho em uma viewport já destruída.

`AxisReadContext` vive por um flush síncrono e compartilha a leitura/indexação
do owner da treliça. O contexto não atravessa uma mutação nem um retorno ao event
loop. Registro, JSON e fingerprint do owner são processados uma vez por lote;
o estado controlado de cada filho continua validado individualmente.

Desligar ambas as opções remove os ramos próprios, observers App/Gui, conexão
MDI e timers. Fechamento de documento, vistas, troca de bancada e callbacks
pendentes são tratados sem limpar ramos alheios. Desativação é idempotente.
Nenhum SwitchNode de membro é alterado; as máscaras dos previews existentes
continuam sob responsabilidade dessas ferramentas.

### Undo/Redo sem recomputar sólidos

O FreeCAD 1.1.4 pode restaurar inputs e resultados por Undo/Redo conservando
`Touched`. Ignorar esse flag genericamente violaria o contrato de frescor do
estudo; recomputar sólidos para desenhar também violaria o escopo.

A solução usa evidência descartável da sessão: após uma leitura válida e limpa,
guarda-se uma assinatura completa dos valores relevantes, frame, pais e ID
nativo. Apenas depois de um callback Undo/Redo observado a mesma assinatura pode
permitir ler o estado restaurado ainda Touched/Recompute. Mudança material revoga
essa permissão. Invalid e transação em andamento nunca são tolerados.

Para filhos, a assinatura inclui o estado controlado do membro e um SHA256 dos
inputs declarados, Placement, AppliedState, status e registro/IDs do owner.
O digest é calculado uma vez por lote. A permissão de um filho não autoriza
irmãos desconhecidos; leituras strict e de replay usam caches separados.
Treliça com fonte vinculada/expressões ou hierarquia não comprovada não recebe
essa exceção de replay. O fluxo normal de leitura válida continua disponível
conforme a tabela de elegibilidade.

O histórico é limitado a 32 assinaturas limpas por membro, somente enquanto a
sessão visual existir. Não é uma pilha Undo alternativa. Ativar pela primeira
vez após Undo, reabrir um arquivo salvo com fontes pendentes ou voltar a um estado
não conhecido pode deixar essas fontes omitidas até o recompute normal do
FreeCAD. A camada avisa e não inventa um certificado de validade. Não altera
flags State, outputs, documento ou histórico para contornar essa restrição.

## Arquivos do incremento

**12 arquivos: 2 modificados e 10 novos.**

| Estado | Caminho | Responsabilidade |
| --- | --- | --- |
| Modificado | `freecad/SteelStructures/init_gui.py` | Barra/submenu e hooks de ativação/desativação |
| Novo | `freecad/SteelStructures/structural_reference.py` | Leitura, elegibilidade, coordenadas e contexto de lote/replay |
| Novo | `freecad/SteelStructures/interactive/structural_reference_view.py` | Sessões, observers, cache e Coin aditivo |
| Novo | `freecad/SteelStructures/interactive/structural_reference_commands.py` | Dois comandos de apresentação |
| Novo | `Resources/Icons/MemberAxes.svg` | Ícone de eixo nominal |
| Novo | `Resources/Icons/MemberEndpoints.svg` | Ícone de extremidades |
| Modificado | `tests/test_general_tools.py` | Fixture da integração ampliada, mantendo verificações das ferramentas existentes |
| Novo | `tests/test_structural_reference.py` | 28 testes do adaptador e contratos de replay |
| Novo | `tests/test_structural_reference_view.py` | 12 testes de sessão, comandos, buffers e limpeza |
| Novo | `tests/manual_structural_reference_visualization.py` | Gate nativo de leitura/apresentação/ciclo de vida |
| Novo | `scripts/run_structural_reference_visualization_gate.py` | Executor isolado por tema/escala |
| Novo | `Documentation/STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md` | Este relatório e roteiro manual |

O estudo arquitetural anterior continua preservado; seu estado local não é
incorporado implicitamente à seleção acima. Estudos StructuralPlate/Gusset,
treliças experimentais, FCStd, backups e evidências anteriores ficam fora do
incremento. Não houve alteração de catálogos ou metadados de release.

## Validação executada

Evidências desta campanha: `test-results/structural-reference-mvp/`.
Os scripts de auditoria dessa pasta são auxiliares locais, não dependências
de produção nem arquivos para publicação.

### Python e integridade

Comando direcionado final, com 20 módulos:

```powershell
python -B -m unittest -v tests.test_structural_reference tests.test_structural_reference_view tests.test_general_tools tests.test_grid_command tests.test_member_axis_source tests.test_member_axis_creation tests.test_member_placement tests.test_member_orientation tests.test_column_command tests.test_draft_native_member_tool tests.test_grid_object tests.test_grid_view tests.test_truss_copy tests.test_truss_lifecycle tests.test_truss_apply_session tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_miter_controller tests.test_member_miter_preview tests.test_member_plane_cut
python scripts/check_project.py
git diff --check
```

**352 testes OK, zero falhas/erros/skips**, em 2,298 s. Logs e códigos de retorno:
`targeted.log`, `targeted-result.json`, `project.log`, `project-result.json`.
`check_project.py` retornou zero: sintaxe, essenciais, versões e catálogos OK.
O wrapper de evidência teve uma falha ao exibir o log CP1252 como UTF-8; o código
de retorno do check já estava registrado como zero. O log foi convertido e o
wrapper corrigido sem repetir um check já aprovado.

São 40 testes nos dois módulos novos, mais um teste novo de composição da barra
e submenu; os demais são regressões existentes. Cobrem recusa de proxy externo,
matrizes espaciais/hierarquia, corte/offset sem alterar nominal, elegibilidade
dos filhos, custo do lote, assinatura conhecida/desconhecida, revogação, flags
independentes, documentos, vistas, visibilidade e remoção da cauda dos buffers.

Os arquivos novos também recebem verificação equivalente de whitespace com
`git diff --no-index --check`, leitura UTF-8/newline e XML dos SVGs. Retorno 1 de
no-index pode indicar apenas o delta de arquivo novo; não é usado sozinho como
diagnóstico de whitespace. Avisos de conversão LF→CRLF são registrados separadamente.

**A suíte completa não foi executada**, conforme solicitado.

### Gates FreeCAD 1.1.4

```powershell
python scripts/run_structural_reference_visualization_gate.py --theme Classic --output-root test-results/structural-reference-mvp/native
python scripts/run_structural_reference_visualization_gate.py --theme "FreeCAD Dark" --output-root test-results/structural-reference-mvp/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --output-root test-results/structural-reference-mvp/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --scale-factor 1.5 --output-root test-results/structural-reference-mvp/native
```

| Tema/escala efetiva | Checks | Resultado | Pasta |
| --- | ---: | --- | --- |
| Classic, DPR 1 | 157 | OK | `1792861066681843600_Classic_5thgu6xi` |
| FreeCAD Dark, DPR 1 | 157 | OK | `1792861087693479200_FreeCAD_Dark_g101umv0` |
| OpenDark, DPR 1 | 157 | OK | `1792861178270659200_OpenDark_lladptdb` |
| OpenDark, DPR 1,5 | 157 | OK | `1792861279157257100_OpenDark_njbdry0f` |

**471 checks nos três temas, mais 157 na escala adicional: 628 checks aprovados.**
São checks de gate, não testes unitários independentes. Todos retornaram zero,
sem timeout, callbacks Python/Qt ou assinaturas de erro nos logs nativos.
Manifestos registram hashes das fontes executadas, tema e preferências isoladas.
Os 156 hashes de fontes dos quatro manifestos são idênticos e correspondem aos
arquivos finais do workspace; `integrity.json` registra a comparação.

Cobertura nativa final:

- Membros X/Y/Z/inclinados, roll e inserção excêntrica, dois App::Part aninhados
  transformados, corte PlaneCut anterior e eixo nominal distinto da ponta efetiva.
- Acionamento por QAction real da bancada, marcação independente e sincronização
  ao mudar documento. Seleção física continua utilizável sob a sobreposição.
- Dados, propriedades visuais, BRep e quantidade de objetos preservados ao ligar;
  nenhuma entrada Undo ou flag Modified acrescentada pela camada.
- 20 ciclos de liga/desliga, remoção de ramos, observers e timers, callbacks
  pendentes cancelados e nova sessão sem ressuscitar recursos.
- Alteração de comprimento, recompute, movimento de pai, exclusão, Undo/Redo
  independentes e de filhos aceitos, sem recompute extra para desenhar o replay.
- Ocultar/restaurar membro e pai sem resolver novamente eixos; buffers diminuem
  corretamente. Sem varredura geométrica por mouse ou no timer de vistas.
- Duas vistas do mesmo documento, fechamento da vista inativa, dois documentos
  com flags distintas, fechamento e recriação de documento com o mesmo Name.
- Troca efetiva Steel Structures → Part → Steel Structures: cleanup pelo hook real
  e retorno com as opções desligadas.
- Salvar com camada ativa, reabrir FCStd e reconstruir referências de fontes
  válidas sem objetos/propriedades de overlay persistidos.
- Draft Line e membro realmente Linked continuam recusados, sem mudança da fonte
  ou conversão automática para Independent.
- Treliça de 50 painéis/103 filhos, sem segundo grafo e com uma leitura de owner
  por lote; estruturas de 100 e 1.000 membros.

Os probes aquecem caches nativos antes da comparação: consultar Shape de App::Part
pode criar `_Part_ShapeCache` e atualizar flags internas BRep. O snapshot é provado
estável antes de ligar a camada. Para reabrir FCStd, a comparação considera a
quantização nativa de cor de 8 bits, normalização de quaternion e cache nativo
não persistido; geometria física é também comparada por diferença volumétrica
bidirecional. Não se exige igualdade textual de BRep serializada após reabertura.

Houve execuções diagnósticas anteriores durante a implementação. Elas detectaram
preparação incompleta de fixtures, caches nativos/serialização, campo Pivy `write`,
eventos de Visibility e a necessidade de replay conhecido. Permanecem na pasta
de evidências. O Classic preliminar de 149 checks não certificava replay imediato
dos filhos e é substituído pelos quatro resultados finais acima.

### Desempenho observado

Valores em ms; são amostras desta máquina Windows, não benchmark estatístico.
“Edição” inclui o recompute provocado explicitamente pela alteração de modelo do
gate e o despacho da UI; não significa que a camada execute recompute.

| Tema, DPR 1 | Inicial: 100 membros | Inicial: 1.000 membros | Edição de 1 entre 1.000 | Treliça: 103 filhos |
| --- | ---: | ---: | ---: | ---: |
| Classic | 21,6 | 536,7 | 24,7 | 46,4 |
| FreeCAD Dark | 33,5 | 525,6 | 49,8 | 66,4 |
| OpenDark | 25,4 | 387,8 | 19,5 | 47,9 |

Os membros usados no ensaio independente têm representação Simplified. O custo
de criação dos sólidos é medido separadamente em `metrics.json`; não entra no
tempo inicial da camada. A edição conserva os descritores dos membros não
alterados. Não foram medidos p95, milhares de treliças, várias GPUs ou FPS contínuo.

### Inspeção das capturas

Foram inspecionadas capturas `saveImage` nos três temas, cena com eixo excêntrico
visível, marcadores e oclusão. Também foram conferidos os controles reais na barra.
Grabs da janela têm o artefato OpenGL de captura já observado no ambiente: servem
para avaliar controles, não geometria. Os renders da vista são a evidência gráfica.
A execução a 150% confirmou DPR 1,5; não certifica todas as configurações físicas
de monitor ou mudanças de DPI entre telas.

Não foi executado um novo teste manual completo das outras ferramentas. Seus
módulos não mudaram e suas regressões direcionadas passaram; a combinação com
gestos/preview em modelos reais integra o roteiro manual abaixo.

## Limitações e riscos remanescentes

1. Profundidade normal pode esconder integralmente o eixo de uma seção centrada.
   Isso faz parte do MVP aditivo aprovado, não é promessa de Raio X.
2. Linked, ocorrências Link/array/escala e hierarquias de filhos não comprovadas
   continuam fora do domínio. Fontes recusadas geram diagnóstico, não reparo.
3. Replay Touched só é exibido quando a configuração completa já foi validada
   limpa na sessão. Estados desconhecidos continuam pendentes; o recurso não
   recomputa, limpa State ou modifica o histórico do FreeCAD.
4. As cores e tamanhos são iniciais. Fundos customizados, zoom extremo, monitores
   diferentes e estruturas densas requerem inspeção do usuário. Coordenadas muito
   afastadas da origem continuam sujeitas à precisão de renderização Coin; não há
   novo mecanismo de origem flutuante neste incremento.
5. Buffer agregado é reconstruído quando muda a geometria visível; resolução
   nominal é incremental, mas isso não elimina todo custo O(N) de apresentação.
   A primeira ativação de 1.000 membros ficou abaixo de 0,54 s nestas amostras.
6. Validado em FreeCAD 1.1.4/Windows. Não se certifica outra plataforma/driver nem
   FreeCAD 1.1.3 nesta rodada.

## Roteiro curto de validação manual

1. Abrir um modelo real e ativar Steel Structures. Conferir os dois comandos em
   Visualização: eixos, extremidades e ambas as opções; repetir liga/desliga.
2. Observar círculo de início/quadrado de fim. Usar um membro com inserção ou offset
   excêntrico e outro com corte: confirmar que os pontos seguem Start/End nominais.
   No membro centrado opaco, observar a oclusão esperada ao orbitar a câmera.
3. Mover/rotacionar membro e App::Part pai, editar comprimento e usar Undo/Redo.
   Repetir em treliça válida após aplicar alteração. Não deve ser necessário
   recompute manual adicional para os estados já conhecidos da sessão.
4. Selecionar membros e usar Criar Membro/Pilar, Ajuste e Meia-esquadria com a
   camada ligada. Conferir seleção, gestos, preview e Cancelar/Esc; desligar a
   camada deve preservar exatamente a aparência atual dos objetos.
5. Ocultar um membro/pai, abrir outra vista/documento, fechar uma vista inativa,
   mudar de bancada e voltar. Confirmar flags por documento e ausência de fantasmas.
6. Salvar um modelo válido com a camada ligada e reabrir: sólidos e parâmetros
   preservados, opções inicialmente desligadas. Reativar as referências.
7. Repetir observação de contraste e tamanho em Classic, FreeCAD Dark e OpenDark,
   com zoom aproximado/distante e a escala de tela usada no trabalho diário.

## Preservação e decisão

A conferência final cruza hashes do snapshot inicial, inventário do incremento e
manifestos dos gates. Os arquivos fora do incremento, incluindo o estudo
arquitetural, StructuralPlate, Gusset, modelos e backups locais, permanecem
preservados: **599 caminhos fora da seleção**, sem divergência de hash ou remoção.
O snapshot de 603 caminhos já incluía dois rascunhos novos do incremento ao ser
capturado; esses e os dois arquivos rastreados modificados são tratados pela
whitelist, sem confundi-los com os estudos preservados. HEAD e índice continuam
iguais ao início. Nenhuma operação de
staging, commit, push, merge, tag, release ou limpeza destrutiva foi executada.

**GO para validação manual/inspeção visual do MVP.** Não há regressão conhecida
ocultada nem bloqueador técnico identificado no domínio documentado. A aprovação
manual e a suíte completa de fechamento continuam pendentes antes de preparar
publicação; este GO não executa nem autoriza commit ou push.
