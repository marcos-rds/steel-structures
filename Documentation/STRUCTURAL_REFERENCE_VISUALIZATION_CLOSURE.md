# Visualização estrutural — fechamento técnico

24/10/2026. Steel Structures, branch `develop/0.7.0`.
Base publicada: `f303f81b76749d621e7dc58ae128fe7787a783eb`.
Incremento exclusivamente local. **GO técnico para commit local seletivo dos
24 arquivos enumerados abaixo. Nenhum staging, commit ou publicação foi executado.**

O usuário informou aprovação manual dos eixos/extremidades, dos três modos,
dos botões exclusivos, dos toggles, da restauração e do primeiro plano em pórticos
e treliças. Essa aprovação é anterior a este fechamento; os gates desta rodada
são automatizados, com inspeção de capturas, sem repetir ou presumir uma nova
validação manual completa. A cor turquesa e a perda de profundidade permanecem
conforme decisão explícita do usuário. Não houve refinamento visual novo.

## 1. Escopo consolidado e referências

Relatórios consultados, preservados como histórico das respectivas etapas:

- [Auditoria arquitetural](STRUCTURAL_REFERENCE_ARCHITECTURE_STUDY.md).
- [MVP de consulta e desenho](STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md).
- [Refinamento visual](STRUCTURAL_REFERENCE_VISUAL_REFINEMENT.md).
- [Modos e refinamento dos botões](STRUCTURAL_REFERENCE_DISPLAY_MODES.md).
- [Prioridade gráfica](STRUCTURAL_REFERENCE_ON_TOP_MVP.md).

Restrições iniciais a modos e primeiro plano foram ampliadas pelas solicitações
posteriores do usuário e pelas provas registradas nesses relatórios. Descrições
antigas de cores, símbolos, menu e oclusão não descrevem o estado final abaixo.
As pendências de aprovação manual desses históricos foram encerradas pelo usuário.

| Recurso final | Contrato |
| --- | --- |
| Eixos | Segmentos nominais Start→End, turquesa `#55C8D0`, tracejado `0x03FF`, fator 2, largura 2,5 e contorno escuro 4,5, dimensionados por DPR |
| Extremidades | Discos laranja, anel branco e proteção escura; diâmetros base 15/13/9 e 23/21/15 em DPR 1,5 |
| Físico | Aparência original; toggles independentes, profundidade normal |
| Estrutural | Máscara gráfica temporária do físico; referências elegíveis em primeiro plano |
| Raio X | Cópia gráfica translúcida dos objetos físicos visíveis; referências em primeiro plano |
| Comandos | Três botões checkable exclusivos e dois toggles independentes; sem seletor antigo ou painel adicional |
| Persistência | Nenhum objeto auxiliar, propriedade, preferência de modo ou schema novo |

**Extremidade nominal não é nó de conectividade analítica.** Não há conexão,
interseção topológica, snap novo, divisão, estação intermediária, centroide,
modelo analítico ou cálculo estrutural neste incremento.

## 2. Auditoria de integração

A auditoria cobriu os módulos novos e os dois diffs rastreados contra `f303f81`.
Uma revisão técnica independente, somente de leitura, examinou coordenadas,
fontes, cache, observers, apresentação, comandos e integração GUI. Após a correção
pontual descrita adiante, não encontrou bloqueador arquitetural restante.

### Fontes de verdade e categorias

`structural_reference.py` é um adaptador de leitura, sem GUI, Part, Shape ou OCC.
Produz descritores imutáveis em coordenadas mundiais. Para Independent:

```text
H = getGlobalPlacement() * inverse(Placement)
A = H(StartPoint); B = H(EndPoint)
frame = rotação real de getGlobalPlacement()
```

Start/End são coordenadas no espaço do pai. Placement.Base pode corresponder ao
início efetivo de um corte, e não é reaplicado ao ponto nominal. São validados
comprimento, finitude, frame rígido destro e direção longitudinal; tolerâncias
de leitura de 1e−7 mm e 1e−7 adimensional, sem significado de tolerância de ligação.
Inserção, offsets, roll e cortes não deslocam artificialmente o eixo nominal.

| Categoria | Situação final |
| --- | --- |
| Membros e pilares Independent | Suportados, em direções gerais e com estado válido |
| App::Part rígido comum/aninhado | Transformação global acumulada uma vez |
| Extensões/offsets/PlaneCut anteriores | Eixo nominal preservado; não segue a face física |
| Filhos físicos de treliça | Somente com owner/bindings/AppliedState/ControlledState aceitos e coerentes |
| Treliça pendente/conflitante ou filho fora do domínio hierárquico comprovado | Omitido com diagnóstico |
| Linked a Draft Line, App::Link, arrays/escala | Sem fonte de referência neste MVP; nenhum contrato ampliado |
| Grid e grafo lógico de treliça | Contexto nativo; não constituem segunda fonte desenhada |
| Part/Mesh externos | Participam dos modos físicos, mas não geram eixos Steel Structures |

Não se recria o grafo da treliça nem se desenha simultaneamente seu grafo lógico
como uma segunda camada. Um contexto descartável compartilha a leitura do owner
por lote; a prova de 103 filhos faz uma leitura do owner.

### Estado, apresentação e ciclo de vida

- Um serviço, uma sessão por documento vivo e uma camada por viewport.
  Name é usado para readquirir objetos, com validação da identidade do documento.
  Descritores e fingerprints são runtime, sem identidade analítica persistente.
- Um par de observers App/Gui, fila Qt single-shot, reconciliação a cada 500 ms
  e conexão MDI próprios. Não há callback de mouse/câmera nem recompute solicitado
  para desenhar. Labels/cores não resolvem novamente o eixo nominal.
- O enum da sessão é a fonte do modo. Sincronização das QActions bloqueia sinais;
  reclicar no modo ativo reafirma checked. Não há grupo/menu paralelo concorrente.
  Toggles físicos e do preset têm memória separada; voltar ao Físico recupera
  a configuração física anterior.
- O modo tem escopo de documento, coerente nas suas vistas, com recursos gráficos
  locais a cada viewport. Só o documento ativo recebe máscara/Raio X. Tarefas,
  edição e comandos Draft suspendem o preset. Prioridade segue o modo efetivo,
  inclusive pausa, documento inativo e fallback.
- Estrutural envolve ObjectGroup/GroupOnTop com switches privados. Raio X mantém
  o ObjectGroup original invisível apenas no wrapper para preservar picking,
  e desenha cópia Coin UNPICKABLE com transparência mínima 78%, conservando
  transparência original maior, cores, transforms, switches e alpha empacotado.
- O mesmo lote de referências é anexado diretamente no Físico ou dentro de
  `SoAnnotation` nos presets. Não há duplicação de coordenadas ou overlay
  alternativo residual. Depth write continua desligado; picking é UNPICKABLE.
- Retorno ao Físico recoloca os mesmos ramos nativos. Não se escreve Visibility,
  Transparency, DisplayMode ou materiais e não se reaplica snapshot antigo sobre
  uma edição do usuário. A revisão gráfica acompanha mudanças reais; hover e
  seleção não provocam cópias Raio X estáveis.
- Pins Coin explícitos protegem cenas, wrappers, clone e annotation. Cleanup é
  idempotente, remove referências antes de soltar a apresentação e trata falhas.
  Exclusão GUI libera recursos antes de destruir ViewProviders. Fechamento de
  vista inativa é reconciliado pelo timer; desligar/desativar remove os recursos
  próprios. O pequeno registro compartilhado de bitmaps por diâmetro é cache
  intencional do processo, sem crescimento por alternância.
- Undo/Redo só aceita Touched mediante fingerprint exato previamente validado,
  sem recompute manual ou limpeza de estado do membro. Valores novos/ inválidos
  continuam bloqueados. Históricos têm até 32 assinaturas por Name e são apagados
  com a sessão; evidências de membros ausentes são mantidas para Undo da exclusão.

Não foram encontrados mecanismos gráficos duplicados, observers redundantes ou
registro do antigo seletor. Protótipos permanecem apenas nas evidências excluídas.
Os engines de membro/pilar, Grid, treliça, ajustes, Meia-esquadria, PlaneCut,
catálogos e schema permanecem iguais à base publicada. Só `init_gui.py` integra
o serviço novo na barra/submenu e no ciclo de ativação da bancada.

### Correção real encontrada no fechamento

Excluir um membro e criar `Part::Box` com o mesmo Name antes do flush deixava
seu eixo antigo no cache: o objeto existia, mas já não era fonte. Reprodução
unitária falhou antes da correção. Agora o lote e o scan completo descartam eixo,
diagnóstico e replay quando o Name pertence a um objeto não fonte.

Dois testes novos distinguem esse caso de membro simplesmente ausente. Uma
primeira tentativa de limpeza apagava também o replay de ausentes; o gate nativo
detectou regressão no Undo da exclusão. Essa tentativa foi corrigida: ausência
preserva o contrato de replay anterior; substituição estrangeira o revoga.
O gate final confirma tanto Undo sem recompute quanto a substituição real no
mesmo lote. Não houve mudança de geometria ou comportamento visual aprovado.

## 3. Isolamento e três suítes completas

Árvores novas em `test-results/sr-close/`, sem checkout, worktree ou alteração
de índice: `git archive f303f81` originou `base/` e `candidate/`. Sobre a segunda
foi copiada somente a lista fechada da seção 6. O relatório foi acrescentado após
os testes de código. Base: 463 arquivos; candidata final: 485, com **2 modificados,
22 novos e nenhuma exclusão**. Caches Python não integram esse inventário.

O harness `suite.py` usa `unittest.defaultTestLoader.discover('tests',
pattern='test_*.py')`, sem filtros, failfast ou alteração dos testes; é a mesma
descoberta de `python -m unittest discover -s tests -p "test_*.py"`. Cada árvore
roda em processo Python 3.11.9 separado, com cwd e import path próprios. Ele
registra resultado por `TestCase.id()`, incluindo subtests com falha e motivos de
skip, em vez de comparar apenas totais. Nenhum teste foi removido ou enfraquecido.

| Árvore | Executados | Aprovados | Skips | Failures/errors | Tempo |
| --- | ---: | ---: | ---: | ---: | ---: |
| Base publicada | 2.006 | 1.857 | 149 | 0 | 65,662 s |
| Candidata isolada final | 2.068 | 1.919 | 149 | 0 | 66,759 s |
| Workspace final | 2.072 | 1.923 | 149 | 0 | 63,377 s |

**Comparação por identidade:** os 2.006 testes compartilhados base→candidata
têm os mesmos estados e motivos de skip; nenhum removido ou resultado alterado.
Os 62 novos estão todos aprovados: 28 em `test_structural_reference`, sete em
`test_structural_reference_modes`, 26 em `test_structural_reference_view` e um
em `test_general_tools`. Incluem a regressão do cache desta auditoria.

Os 2.068 compartilhados candidata→workspace também têm resultados idênticos.
Há somente quatro testes exclusivos do workspace, todos aprovados, em
`test_plate_qt_lifecycle_probe.LifecycleProbeSafetyTests`: diagnósticos experimentais
de StructuralPlate, deliberadamente excluídos. IDs e resultados completos em
`suite-comparison.json` e nos três JSONs de resultados.

Os 149 skips são **as mesmas identidades e os mesmos motivos nas três árvores**:

| Motivo ambiental | Quantidade |
| --- | ---: |
| Real FreeCAD GUI / Qt event loop required | 30 |
| PySide6 não disponível neste Python | 26 |
| FreeCAD/Draft native Python required | 15 |
| FreeCAD GUI and Qt required | 47 |
| FreeCAD Units and PySide6 required | 8 |
| FreeCAD units and PySide6 required | 15 |
| PySide6 required | 8 |

São módulos de widgets/coordenadas, Gusset/Plate GUI e referências/interface de
treliça; não surgiram skips novos do incremento. Os gates abaixo exercitam os
contratos nativos desta entrega, sem afirmar que substituem todos esses 149 testes.
Os 61 testes dos três módulos estruturais também passaram diretamente com unittest
após a correção. As primeiras suítes e os runs diagnósticos foram preservados;
a tabela usa as execuções finais da candidata e do workspace.

Comandos executados na raiz, com harness de evidência fora da candidata:

```powershell
python -B test-results/sr-close/suite.py test-results/sr-close/base test-results/sr-close/base-suite.json
python -B test-results/sr-close/suite.py test-results/sr-close/candidate test-results/sr-close/candidate-final-suite.json
python -B test-results/sr-close/suite.py . test-results/sr-close/workspace-final-suite.json
python -B -m unittest tests.test_structural_reference_view tests.test_structural_reference_modes tests.test_structural_reference
```

## 4. Gates FreeCAD 1.1.4 a partir da candidata

Quatro processos GUI separados, preferências/home/output próprios, sem modificar
a sessão ou modelos do usuário. Runner e três helpers nativos pertencem à candidata.

| Tema | DPR real | Run | Checks | Resultado |
| --- | ---: | --- | ---: | --- |
| Classic | 1,0 | `1792886335991252000_Classic_hwn77i8n` | 270 | PASS |
| FreeCAD Dark | 1,0 | `1792886371398375800_FreeCAD_Dark_sicfgegu` | 270 | PASS |
| OpenDark | 1,0 | `1792886423750768300_OpenDark_ledt505_` | 270 | PASS |
| OpenDark 150% | 1,5 | `1792886479095703900_OpenDark_j6to44dm` | 270 | PASS |

**1.080 verificações, quatro saídas 0, sem timeout, erros nativos ou callbacks
Python/Qt capturados.** Os 162 hashes de fontes/recursos são iguais nos quatro
manifestos e correspondem à candidata final. Os 99 módulos carregados verificados
por run, incluindo helpers, vieram da candidata, conforme `module-origins.json`.
Nenhuma dependência de diagnósticos ou experimentos locais foi necessária.

34 fontes publicadas têm somente diferenças CRLF/LF entre checkout e archive;
foram comparadas com normalização de fim de linha, sem reescrever o workspace.
Os arquivos seletivos são byte a byte iguais entre workspace e candidata.

Com cwd em `test-results/sr-close/candidate`, executado o runner abaixo para
Classic, `"FreeCAD Dark"`, OpenDark e OpenDark com `--scale-factor 1.5`:

```powershell
python scripts/run_structural_reference_visualization_gate.py --theme Classic --output-root "C:/Users/marco/Desktop/FREECAD/MINHA BANCADA/SteelStructures/test-results/sr-close/native"
python scripts/run_structural_reference_visualization_gate.py --theme "FreeCAD Dark" --output-root "C:/Users/marco/Desktop/FREECAD/MINHA BANCADA/SteelStructures/test-results/sr-close/native"
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --output-root "C:/Users/marco/Desktop/FREECAD/MINHA BANCADA/SteelStructures/test-results/sr-close/native"
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --scale-factor 1.5 --output-root "C:/Users/marco/Desktop/FREECAD/MINHA BANCADA/SteelStructures/test-results/sr-close/native"
```

### Cobertura e integridade visual/documental

- Direções e hierarquia rígida, cortes prévios, extremos nominais, filhos de
  treliça válidos e recusas conservadoras. Undo/Redo de membro e treliça sem
  recompute manual; atualizações por movimento, pais e recompute real.
- Comandos/QActions reais, cinco botões e três ícones distintos, exclusividade,
  reclick, memória dos toggles e sua sincronização entre documentos.
- Ciclos repetidos Físico→Estrutural→Raio X→Físico; cores/transparência originais
  diferentes, arrays de cores, objeto previamente oculto, Part/Mesh externos,
  App::Part, Grid, criação/exclusão e edições durante o preset.
- Duas vistas, fechamento de vista inativa, documentos distintos, reuso de Name,
  pausa por TaskDialog/edição, troca/desativação da bancada, observadores/timers
  removidos e ausência de ramas próprias após cleanup.
- Snapshots de entradas/saídas, propriedades, placements, BRep/volume/validade
  e apresentação, além de Undo e Modified. Save/reopen FCStd com overlay e com
  Raio X ativo preserva os dados e abre em Físico, sem helpers ou estado persistido.
- Identidade dos ramos nativos restituídos e edições visuais do usuário mantidas;
  transparência original maior que o preset não é reduzida. Nenhum recompute
  ocorre exclusivamente para alternar modo/prioridade.
- Doze capturas quantitativas de prioridade por run: opaco/transparente 65%,
  Físico/Estrutural/Raio X, seleção/preselection, apenas eixos, apenas extremos,
  ambos desligados e retorno. Foram inspecionados renders W/U/treliças e capturas
  da barra nos temas, incluindo escala 150%; não houve novo ajuste visual.

Na faixa controlada, Estrutural/Raio X conservaram cores completas mesmo sob
seleção/preselection: 826/98 pixels eixo/ponto em Classic e FreeCAD Dark,
785/98 em OpenDark e 791/298 em OpenDark 150%. No Físico a obstrução preservou
zero pixels dessas cores exatas, como esperado. Essas contagens provam prioridade
na fixture, não conectividade ou legibilidade universal em qualquer modelo.

**Sobreposição distinta:** dois membros W em profundidades separadas por 400 mm
e sólidos sem interpenetração projetam os mesmos extremos na vista frontal.
Continuam duas identidades, dois segmentos e quatro extremos no lote, em todos
os modos. Nenhuma propriedade/relação/objeto adicional, entrada Undo ou troca de
Snapper aparece. A camada continua UNPICKABLE e não registra provedor de snaps;
snaps físicos nativos existentes não foram removidos. Coincidência visual não
cria conectividade. A mesma prova testa substituição por Part::Box no mesmo lote.

Os engines de Criar Membro/Pilar, Ajuste, Meia-esquadria, treliças e Grid não
mudaram. As suítes completas preservam seus resultados, e o gate cobre suspensão
com TaskDialog válido. Não foi refeito manualmente cada fluxo dessas ferramentas
nesta rodada; não se anuncia certificação universal de addons ou todos os skips.

### Diagnósticos preservados e excluídos do PASS

Três runs Classic anteriores ficaram em `native/`: `1792886175633292600` detectou
a regressão de Undo da tentativa de limpeza; `1792886237037920100` e
`1792886277582999200` detectaram baseline prematura na fixture nova de sobreposição.
Nesta última, o boolean OCC de verificação era executado após o snapshot e mudava
o hash BRep dos próprios argumentos. A medição foi movida para antes do baseline,
sem relaxar a igualdade exigida. Somente os quatro runs finais entram no PASS.
Não houve Access violation nesses diagnósticos.

Os helpers mantêm o despacho explícito de `DeferredDelete` entre fechamentos
para representar turnos de UI que uma fixture monolítica não entrega. Falhas
nativas antigas e sua investigação permanecem nos relatórios/evidências anteriores;
não foram apagadas, ignoradas pelo runner nem atribuídas especulativamente à engine.

### Desempenho observado

Tempos locais de ativação por viewport, fixtures Simplified; sem p95/FPS:

| Tema | Overlay 100/1.000 membros | Raio X 100/1.000 membros |
| --- | ---: | ---: |
| Classic | 22,7 / 404,4 ms | 284,7 / 2.886,8 ms |
| FreeCAD Dark | 32,7 / 415,9 ms | 304,5 / 2.934,6 ms |
| OpenDark | 38,8 / 428,7 ms | 371,9 / 2.900,2 ms |
| OpenDark 150% | 33,1 / 613,5 ms | 343,0 / 4.507,4 ms |

O overlay tem 24 nós no Físico e 25 com annotation, independente de 100/1.000
membros. A cópia Raio X contém 6.701/67.001 nós. Hover/preselection não reconstrói
a cópia estável. Mudança real ainda invalida a cópia agregada inteira; várias
vistas multiplicam custo/memória. Não se certifica fluidez em modelos grandes.

## 5. Integridade, riscos e limites remanescentes

`python scripts/check_project.py` passou nas três árvores. `git diff --check`
passou no workspace. Os arquivos novos também passaram UTF-8, newline final,
XML dos cinco SVGs e `git diff --no-index --check` contra arquivo vazio; para os
modificados foi usada a base publicada. A verificação equivalente aceita CRLF
como EOL (`cr-at-eol`), sem ocultar whitespace real. Nenhum arquivo foi normalizado
ou alterado só por causa de EOL.

Snapshot inicial: **621 arquivos**, incluindo todos os tracked, untracked não
ignorados e backups FCBak em `tests/`. Apenas quatro existentes mudaram neste
fechamento: serviço de view, seu teste unitário e os dois helpers nativos citados
na correção/provas. **617 permanecem byte a byte idênticos**, incluindo modelos,
backups e todos os estudos externos. O relatório é a única nova entrega desta
rodada; evidências próprias estão em diretório ignorado separado. A extração da
base continua byte a byte igual ao archive. HEAD e hash do índice Git não mudaram.

Riscos conhecidos aceitos ou delimitados:

1. Turquesa pode se aproximar do realce nativo; mantido por decisão do usuário.
   Referências em primeiro plano perdem a indicação de profundidade, especialmente
   quando se sobrepõem. Nenhuma solução nova foi implementada para esses pontos.
2. Estrutural usa seleção pela árvore. Em Raio X o picking é do físico original;
   pode escolher objeto diferente do dono de um marcador visualmente sobreposto.
   O realce nativo pode ficar opaco. Referências não são selecionáveis/snappable.
3. Prioridade cobre geometria 3D, não Qt/HUD/navigation cube ou annotations de
   terceiros inseridas depois. Câmera, frustum e clipping permanecem válidos.
4. Raio X tem custo linear da cópia agregada, com pausa perceptível em milhares
   de membros; não há cache incremental por objeto ou benchmark universal.
5. Modo é por documento, não independente por viewport, e não é salvo. Fontes
   Linked/Links/escala/hierarquias não demonstradas permanecem sem eixo desenhado.
6. Cache de replay é por sessão, limitado a 32 assinaturas por Name. Names de
   fontes ausentes ficam retidos até o fim da sessão para Undo; sessões longas
   com muita criação/exclusão podem acumular esse histórico descartável.
7. Certificação local FreeCAD 1.1.4/Windows e Qt scale 1,5. Outros drivers,
   plataformas, DPI físico entre monitores, materiais/shaders especiais, clipping
   customizado e scenegraphs de addons fora dos seams nativos exigem prova própria.
8. Os 149 testes ambientais continuam skips; aprovação das ferramentas anteriores
   e a aprovação manual fornecida pelo usuário não eliminam esses limites.

**Confirmação explícita: não houve migração de schema, nova persistência,
alteração de propriedades permanentes dos membros nem mudança da engine.**

## 6. Inventário seletivo fechado

Status contra `f303f81`: **M = modificado, N = novo**. Nenhum arquivo excluído.
Todos os demais caminhos estão fora do commit proposto.

| Status | Caminho | Responsabilidade |
| --- | --- | --- |
| M | `freecad/SteelStructures/init_gui.py` | Integração barra/menu e ciclo da bancada |
| N | `freecad/SteelStructures/structural_reference.py` | Leitura nominal, hierarquia e replay |
| N | `freecad/SteelStructures/interactive/structural_reference_view.py` | Serviço/cache/layers/annotation/ciclo de vida |
| N | `freecad/SteelStructures/interactive/structural_reference_modes.py` | Apresentação reversível por viewport |
| N | `freecad/SteelStructures/interactive/structural_reference_commands.py` | Três modos e dois toggles |
| N | `Resources/Icons/MemberAxes.svg` | Ícone de eixos |
| N | `Resources/Icons/MemberEndpoints.svg` | Ícone de extremidades |
| N | `Resources/Icons/StructuralDisplayMode.svg` | Ícone Físico; nome histórico reutilizado |
| N | `Resources/Icons/StructuralDisplayAxes.svg` | Ícone Estrutural |
| N | `Resources/Icons/StructuralDisplayXray.svg` | Ícone Raio X |
| M | `tests/test_general_tools.py` | Composição aditiva e ciclo GUI |
| N | `tests/test_structural_reference.py` | Resolvedor, coordenadas, treliça/replay |
| N | `tests/test_structural_reference_modes.py` | Wrappers/clone/materiais/rollback |
| N | `tests/test_structural_reference_view.py` | Serviço, renderer, ações, cache e cleanup |
| N | `tests/manual_structural_reference_visualization.py` | Gate nativo integrado, origem e desempenho |
| N | `tests/manual_structural_display_modes.py` | Gate de modos, controles e restauração |
| N | `tests/manual_structural_reference_on_top.py` | Gate de prioridade e sobreposição distinta |
| N | `scripts/run_structural_reference_visualization_gate.py` | Runner isolado e controle de erros |
| N | `Documentation/STRUCTURAL_REFERENCE_ARCHITECTURE_STUDY.md` | Contratos e investigação |
| N | `Documentation/STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md` | Histórico MVP |
| N | `Documentation/STRUCTURAL_REFERENCE_VISUAL_REFINEMENT.md` | Histórico de estilo |
| N | `Documentation/STRUCTURAL_REFERENCE_DISPLAY_MODES.md` | Modos e botões |
| N | `Documentation/STRUCTURAL_REFERENCE_ON_TOP_MVP.md` | Investigação/contrato da prioridade |
| N | `Documentation/STRUCTURAL_REFERENCE_VISUALIZATION_CLOSURE.md` | Este fechamento |

### Exclusões explícitas

- Todos os estudos/documentos `STRUCTURAL_PLATE_*`, os diagnósticos de heap,
  QLineEdit/lifecycle/tracker, seus scripts/manuals e `test_plate_qt_lifecycle_probe.py`.
- Todos os estudos Gusset e pastas `Documentation/gusset_*`, SVGs, HTML e matrizes.
- Documentação intermediária `Documentation/TRUSS_*` e experimentos de treliça.
- `tests/copiatreliça.FCStd`, `tests/copiatreliça2.FCStd`, quaisquer FCStd/FCBak
  experimentais e backups; inclusive a edição que o usuário pediu para preservar.
- `test-results/**`, árvores base/candidata, ZIP, screenshots, FCStd de gate,
  logs, scripts de prova, diagnósticos e manifestos. São evidências, não dependências.
- Caches, preferências, `.git`, configurações pessoais e quaisquer outros arquivos
  fora dos 24 caminhos. Sem versões, changelog/release ou catálogos alterados.

### Staging sugerido — não executado

Somente após decisão do usuário. Lista literal, sem staging global ou diretórios:

```powershell
$visualizationFiles = @(
    'freecad/SteelStructures/init_gui.py'
    'freecad/SteelStructures/structural_reference.py'
    'freecad/SteelStructures/interactive/structural_reference_view.py'
    'freecad/SteelStructures/interactive/structural_reference_modes.py'
    'freecad/SteelStructures/interactive/structural_reference_commands.py'
    'Resources/Icons/MemberAxes.svg'
    'Resources/Icons/MemberEndpoints.svg'
    'Resources/Icons/StructuralDisplayMode.svg'
    'Resources/Icons/StructuralDisplayAxes.svg'
    'Resources/Icons/StructuralDisplayXray.svg'
    'tests/test_general_tools.py'
    'tests/test_structural_reference.py'
    'tests/test_structural_reference_modes.py'
    'tests/test_structural_reference_view.py'
    'tests/manual_structural_reference_visualization.py'
    'tests/manual_structural_display_modes.py'
    'tests/manual_structural_reference_on_top.py'
    'scripts/run_structural_reference_visualization_gate.py'
    'Documentation/STRUCTURAL_REFERENCE_ARCHITECTURE_STUDY.md'
    'Documentation/STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md'
    'Documentation/STRUCTURAL_REFERENCE_VISUAL_REFINEMENT.md'
    'Documentation/STRUCTURAL_REFERENCE_DISPLAY_MODES.md'
    'Documentation/STRUCTURAL_REFERENCE_ON_TOP_MVP.md'
    'Documentation/STRUCTURAL_REFERENCE_VISUALIZATION_CLOSURE.md'
)
git add -- $visualizationFiles
git diff --cached --name-status
git diff --cached --check
```

Conferir exatamente 24 caminhos, 2 M/22 A e nenhuma exclusão antes de qualquer
commit. O comando sugerido não autoriza push, que continua exigindo autorização
explícita separada. Não foram executados add, commit, push, merge, tag, release,
git clean ou outra operação destrutiva neste fechamento.

## 7. Evidências, roteiro e decisão

Evidências locais em `test-results/sr-close/`:

- `initial.json`, `inventory.json`, `published.zip`, `base/` e `candidate/`.
- `base-suite.*`, `candidate-final-suite.*`, `workspace-final-suite.*` e
  `suite-comparison.json`: identidades, resultados completos e skips.
- `native-summary.json`, `native-eol-only.json` e `native/<run>/`: manifestos,
  origens, checks, métricas, logs, renders e documentos FCStd de teste.
- `integrity.json`, `*-project-check.log` e `diff-check.log`: inventário exato,
  preservação, hashes, sintaxe/catálogos/versões, UTF-8/XML/whitespace.

Não há validação manual nova obrigatória decorrente de alteração visual nesta
rodada. Para uma conferência final opcional: abrir W/U e treliça, alternar os
três modos e os dois toggles; selecionar em Raio X e pela árvore no Estrutural;
observar profundidades sobrepostas sem interpretar conexão; editar comprimento,
usar Undo/Redo, fechar/trocar documento/vista e bancada; salvar/reabrir e confirmar
Físico original. O cache corrigido também pode ser conferido excluindo um membro
e criando objeto externo com o mesmo Name antes da próxima atualização.

**GO para commit local exclusivamente seletivo do inventário de 24 arquivos.**
As três suítes completas são compatíveis por identidade, a candidata isolada
reproduz os quatro gates, os estudos externos foram preservados e a aprovação
manual funcional/visual foi fornecida pelo usuário. Os riscos remanescentes estão
explicitados acima, sem novo escopo ou soluções especulativas.
