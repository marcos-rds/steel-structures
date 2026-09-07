# Treliça C2 — validação local

**Fechamento C2:** validação manual no FreeCAD 1.1.3 concluída e aprovação funcional informada pelo usuário. As pendências descritas nas etapas abaixo são registros históricos, encerrados por essa aprovação. Nenhum recurso C3 incluído.

O pipeline C1 continua sendo `Envelope → StationPlan → TopologyGraph → PhysicalRuns → RealizationPlan → StructuralMember`.
O editor da alma trabalha no candidato do Gerador. Não cria objetos de nó na árvore nem objetos temporários de preview.

## Edição da alma

Em **Alma → Editar alma**, os botões exclusivos são Selecionar, Criar barra, Remover barra, Adicionar nó, Remover nó e Mover nó.
O hover destaca snap, com prioridade nó → midpoint → ponto sobre barra. Adicionar nó sobre barra divide a TopologyEdge e preserva seu papel; um banzo contínuo permanece um PhysicalRun. **Permitir nó livre** inicia desligado; ligado, permite nó interno dentro do envelope. Mover não funde nós coincidentes.
O magnetismo permanece igual: midpoint usa triângulo discreto, nó usa círculo e ponto sobre barra usa quadrado. Remover nó recompõe uma divisão colinear de grau 2 com a mesma origem lógica e papel; vínculos adicionais bloqueiam a remoção. Nós internos livres podem ser removidos. A proveniência de splits é um campo opcional do JSON Custom, compatível com C2 anterior, sem alteração de SchemaVersion.
Criar barra exige dois cliques em nós. Mover exige um clique no nó interno e outro na posição desejada. Esc cancela primeiro o gesto em andamento; outro Esc fecha o editor.
As alterações aparecem no candidato e só são aplicadas ao documento com OK no Gerador. Cancelar o Gerador descarta todas elas.

Os banzos pertencem ao envelope e não são removidos ou movidos por esse editor. Nós internos manuais usam UUID; nós dos presets usam identidades semânticas. Cruzamentos não criam nós. Quando um nó explicitamente conectado está sobre uma barra, os segmentos incidentes são materializados no grafo.

Qualquer edição da alma, incluindo espelhamento, ativa `TopologyMode = Custom` e o combo mostra **Padrão: Custom**. `base_preset` persiste separadamente no JSON C2 e aparece como **Base para restaurar**. Configurações Custom antigas conservam seu antigo TopologyPreset como base. Trocar perfil, rotação, inserção ou cor mantém o modo. Escolher outro preset em Custom apenas muda a base; o combo continua Custom. **Restaurar padrão** usa essa base e volta ao modo preset, preservando referência, specs e continuidades.

Dentro do editor, **Inverter alma** reflete a alma inteira por `x' = Span - x`, substituindo sua orientação no candidato. Reutiliza entidades equivalentes e cria endpoints topológicos nos banzos sem exigir estações correspondentes. Refletir para fora do envelope ou sem encontrar o banzo correspondente continua sendo conflito explícito.
**Copiar espelhado** escolhe Esquerda → Direita ou Direita → Esquerda, preserva a origem e o centro, reutiliza nós semanticamente coincidentes e evita barras duplicadas. Ambas as operações materializam Custom.
O editor usa um único QToolButton **Copiar espelhado** com menu **Esquerda → Direita / Direita → Esquerda**. A escolha executa a cópia e o clique principal repete a última direção selecionada nessa janela; a direção ativa aparece marcada no menu e no tooltip. Novos endpoints sobre barras/banzos subdividem TopologyEdges. Identidades geradas são determinísticas. Apenas Restaurar padrão permanece no painel principal.

## Presets e panelização

Os contratos estão em `trusses/preset_contracts.py`. O limite desta implementação é de 4 a 200 painéis; nenhum preset arredonda a entrada de quantidade silenciosamente.

| Preset | Contrato adicional |
|---|---|
| Warren, Pratt, Warren com montantes, Howe | Sem paridade obrigatória |
| X | Variante sem conexão ou com nó central e quatro segmentos em cada X |
| K | Somente Parallel; nós internos a meia altura nas estações interiores |
| Fink básico | Somente DuoPitch; quantidade par; quatro pernas em W entre rafters, tie e ápice |
| Fan | Somente DuoPitch; quantidade par; webs convergem para o nó inferior sob o ápice |
| King Post | Somente DuoPitch; quantidade par; post central e duas struts simétricas |
| Queen Post | Somente DuoPitch; mínimo 6, múltiplo de 3; dois posts e straining beam horizontal |
| Custom | Semente com banzos e alma vazia |

Em DuoPitch, a cumeeira é sempre uma estação obrigatória. As restrições dos presets também são aplicadas à lista de espaçamentos; incompatibilidades mantêm o preview válido anterior e bloqueiam OK.
O combo lista apenas presets compatíveis. Ao mudar envelope, um preset incompatível passa explicitamente a Warren. Custom bloqueia a troca de envelope até Restaurar padrão, preservando o grafo. Crossings declarados de X desconectado não geram aviso; diagnostics Custom mostram contagens humanas, sem IDs no rodapé. Custom reconcilia endpoints coincidentes antigos e propaga a incidência de nós explícitos sobre edges; crossings sem nó continuam sem ligação. No editor, componentes fora do maior componente recebem destaque magenta.

- **Número de painéis:** conserva o driver C1.
- **Espaçamento desejado:** escolhe a quantidade compatível cuja média de espaçamento está mais próxima do alvo; empate favorece a menor quantidade. Mostra o valor efetivo.
- **Ângulo desejado:** disponível para Warren, Pratt, Warren com montantes, Howe e X. Avalia a média dos ângulos agudos dos segmentos DIAGONAL e mostra média e faixa efetivas. É uma aproximação geométrica discreta. Editar manualmente congela a quantidade resolvida em ByPanelCount e informa a desativação do ângulo-alvo.
- **Lista de espaçamentos:** reutiliza o `SpacingEditor` do Grid. Valores absolutos positivos, soma igual ao vão e, em DuoPitch, estação exatamente na cumeeira. Não altera valores para fechar o vão.
  Mostra Soma, Vão e Restante. **Completar vão** acrescenta explicitamente o restante positivo; excesso de soma permanece como conflito. A adaptação local conserva a precisão da referência sem alterar o widget do Grid.

Custom conserva vínculos normalizados ao envelope e identidades de estações. Span/Height e mudanças compatíveis da posição da cumeeira reposicionam o grafo. Trocar quantidade de estações ou driver com identidades incompatíveis exige resolução explícita ou Restaurar padrão; não inventa uma nova alma.

## Referências

TwoPoints permanece disponível. ThreePoints captura início da base, fim da base e ápice usando o mesmo Snapper; deriva plano, altura e posição do ápice, selecionando DuoPitch. Pontos coincidentes/colineares e ápice projetado fora do interior do vão são inválidos.

Linha Draft e Retângulo Draft aceitam pré-seleção ou **Usar seleção Draft** no painel. O retângulo inteiro mede as quatro arestas reais e escolhe a primeira das mais compridas como base inicial; quadrados, dentro da tolerância de 0,000001 mm, exigem escolha explícita e abrem Referência. Uma aresta pré-selecionada prevalece mesmo sendo mais curta. As quatro bases continuam selecionáveis e o preview destaca a escolhida. Apenas retângulos simples, sem subdivisão, arredondamento ou chanfro são aceitos. O encaixe usa eixos nominais, sem compensação pelo contorno dos perfis.

Defaults de modelagem: catálogo Gerdau 01/23, `u-4x8.04` (U 4" x 8,04, altura 101,6 mm) nos dois banzos azuis, superior a −90° e inferior a +90°; `equal-angle-metric-40x4` (L 40 x 4) na alma, montantes/fechamentos laranja e diagonais amarelas. Para abas voltadas ao interior, o fechamento esquerdo usa 180° e o direito 0°; montantes e diagonais permanecem em 0°. Não representam dimensionamento estrutural.

Sem **Manter vínculo**, a referência é Snapshot. Com vínculo, as dimensões válidas são derivadas da fonte e seu frame fica persistido. A linha reutiliza AxisSource e orienta o plano a partir do frame/working plane; uma mudança vinculada que torne essa orientação degenerada exige selecionar novamente a referência.

Também são registradas dependências dos containers de Placement da fonte. Containers que criariam ciclo com a treliça exigem Snapshot. Após criação/aplicação bem-sucedida, a fonte é ocultada; cancelar não modifica sua visibilidade.

Mudanças vinculadas com as mesmas identidades atualizam os membros existentes. Mudanças estruturais marcam `NeedsRegeneration` e mantêm o conjunto aplicado; duplo clique → Gerador → OK aplica a regeneração. Fontes removidas/degeneradas preservam o último estado válido e exibem conflito. Não há criação/deleção de filhos em `execute`.

## Persistência e validação

Schema 2 adiciona a configuração C2 e os vínculos. Schema 1 continua legível; a definição aplicada C1 é preservada até aplicação bem-sucedida. Não há mudança de versão de release.

Testes focados: `test_truss_c2`, `test_truss_c2_editor`, `test_truss_c2_references`, com regressões de C1 em `test_truss_core`, `test_truss_qa`, `test_truss_task_panel` e `test_truss_manual_fixes`.
A sessão MCP/FreeCAD 1.1.3 verificou semântica real de Rectangle, Placement próprio e de App::Part, Linked com/sem mudança de quantidade, fonte inválida/removida e save/reopen de Custom. Testes com stubs não substituem a validação dos gestos e apresentação pelo usuário.

Roteiro manual pendente:

1. Warren: remover/adicionar diagonal; conferir Custom e trocar perfil sem reaplicar preset.
2. Adicionar e mover nó interno; cancelar gesto com Esc; Cancelar o Gerador.
3. Comparar X conectado e não conectado, K, Fink, Fan, King e Queen.
4. Dentro do editor, Inverter alma e Copiar espelhado; conferir preview e Restaurar padrão no Gerador.
5. Experimentar os quatro drivers, incluindo lista incompatível com a cumeeira.
6. Linha Snapshot/Linked e retângulo com base explícita; alterar suas dimensões.
7. Capturar ThreePoints com snap nos três cliques.
8. Salvar/reabrir Custom; alterar fonte Linked com mudança de PanelCount e aplicar pelo Gerador.

### Revisão Custom e espelhamento — validação focada

Comando executado nesta revisão (33 testes aprovados):

```powershell
python -m unittest tests.test_truss_c2_custom_review tests.test_truss_c2_refinements.PanelContracts tests.test_truss_c2_refinements.EditorContracts tests.test_truss_c2_editor.EditorGestureTests tests.test_truss_c2.C2GraphTests.test_explicit_connected_node_splits_crossing_edges tests.test_truss_c2.C2GraphTests.test_mirror_twice_and_restore_preserve_specs
git diff --check
```

Sem suíte completa, check_project, MCP ou QA amplo nesta revisão. Casos reproduzidos em testes: endpoint duplicado por ID, endpoint sobre banzo sem split e nó isolado movido sobre barra. O documento do caso manual relatado não foi inspecionado; a confirmação nele permanece pendente.

Validação manual desta revisão: conferir abas dos fechamentos; editar e fechar a janela para verificar Padrão Custom/base de restauração; remover um midpoint com e sem terceira barra incidente; inverter/copiar uma metade Custom com estações assimétricas; conferir triângulo de midpoint e destaque magenta; selecionar Rectangle inteiro alongado, quadrado e uma aresta curta pré-selecionada.

### Gate local após microcorreção do menu

68 testes focados aprovados; `git diff --check` sem erros:

```powershell
python -m unittest tests.test_truss_c2 tests.test_truss_c2_editor tests.test_truss_c2_references tests.test_truss_c2_refinements tests.test_truss_c2_custom_review
```

A microcorreção alterou somente a apresentação/disparo da direção de cópia e seu teste, preservando o algoritmo e os demais controles. Sem suíte completa, QA amplo, staging, commit ou push. Branch `develop/0.6.0`, HEAD `941a8302b59f0b128a981fabf9f6a1833b70e738` preservados. Gate automatizado aprovado; o gate manual continua pendente, incluindo conferir menu, indicação da direção e repetição pelo botão principal no FreeCAD.

Nenhum recurso de C3, análise estrutural ou ampliação de perfis faz parte desta etapa.

### Gate final para commit

Revisão curta de C1/schema, Custom, callbacks, referências Linked, espelhamento/cópia e Rectangle, sem blocker funcional evidente e sem arquivos fora da C2. Sem nova sessão MCP; validação manual já aprovada pelo usuário.

- Suíte completa executada uma vez: `python -m unittest discover -s tests -p "test_*.py"` — 979 testes, com 12 erros no namespace temporário da fixture antiga do painel.
- Corrigida somente a resolução dos imports tardios da fixture Qt, preservando todos os asserts e a implementação aprovada. Revalidação focada: `python -m unittest tests.test_truss_task_panel tests.test_truss_manual_fixes` — 29 testes aprovados, incluindo todos os casos que falharam. A suíte completa não foi repetida.
- `python scripts/check_project.py`: aprovado, executado uma vez.
- `git diff --check`: sem erros.
- Commit autorizado: `feat(truss): add advanced topology editing`. Sem push, tag ou release.
