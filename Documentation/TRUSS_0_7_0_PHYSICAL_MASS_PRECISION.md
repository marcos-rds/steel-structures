# Gerador de Treliças — precisão visual e massa física

Implementação local em `develop/0.7.0`, sobre HEAD `68dc4b4`. A organização aprovada do TaskPanel, Editor, canvas e abas foi preservada. Não houve alteração de geometria, topologia, alinhamento dos banzos, `TrussEditSession`, schema ou propriedades persistentes. Nenhum `git add`, commit ou push foi realizado.

## Precisão e unidades

Comprimentos são apresentados com duas casas decimais e agrupamento regional no TaskPanel, nas coordenadas P0/P1, Editor, cotas do preview, informações de panelização e diálogos de composição/interconectores. Os fatores e símbolos vêm de `FreeCAD.Units.Quantity.getUserPreferred()`; os separadores vêm do `QLocale` do widget. As preferências globais não são modificadas pela implementação.

O novo `TrussLengthSpinBox` mantém o controle Qt nativo para os campos que já eram spinboxes. A precisão de armazenamento do Qt permanece no máximo, enquanto `textFromValue()` controla exclusivamente a apresentação. Ao receber foco, o campo mostra os dígitos completos, sem agrupamento, para edição. As coordenadas reutilizam `TrussReferenceField`. Normal, ângulos e percentuais mantêm sua apresentação existente.

A conversão de unidades e validação dimensional reutilizam o parser aprovado de `TrussReferenceField`. Foi acrescentado um fallback de `QLocale.toDouble()` para números com agrupamento regional antes de devolver a expressão de unidade ao FreeCAD. A entrada original continua aceitando vírgula/ponto decimal, unidades explícitas e notação científica.

Foco/Enter/Tab sem edição não reparsam a apresentação arredondada. Uma alteração deliberada para um valor arredondado é uma edição real. Sincronizações preservam texto, cursor e seleção tanto de entradas incompletas quanto de entradas válidas ainda não confirmadas. Entradas incompletas bloqueiam Aplicar quando lidas pelo painel; Enter inválido preserva o texto e informa o erro. Escape ou correção para o mesmo valor recuperam a validação, inclusive nos espelhos do Editor.

O formatador é puro: consultas Qt de `sizeHint()` ou formatação dos extremos do intervalo não podem trocar o fator de unidade de uma edição em andamento. Não foram introduzidos timers, filtros globais ou QSS adicionais.

Em esquemas imperiais fracionários, a apresentação decimal usa o fator/símbolo retornado pelo FreeCAD, por exemplo polegadas decimais; a edição continua aceitando expressões de unidades suportadas pelo FreeCAD.

## Fonte física e componentes contabilizados

A `StructuralTruss` é organizacional. Não se usa um volume agregado dela nem uma união global.

O leitor `trusses/physical_mass.py` consulta exclusivamente os objetos materiais registrados no documento:

- `GeneratedMembers`: banzos, montantes, diagonais, fechamentos, componentes A/B de perfis compostos e interconectores efetivamente materializados. Chapas espaçadoras, presilhas e treliçamentos simples/duplos já entram nesse registro como peças próprias.
- `GeneratedGussetPlates`: chapas Gusset físicas pertencentes à treliça.

Cada peça contribui com seu `Shape.Volume` final em mm³, depois dos recortes, extensões e ajustes físicos já realizados pelo pipeline existente. A visibilidade não participa do cálculo. Peças distintas permanecem somadas mesmo quando se sobrepõem: o quantitativo é de peças fabricadas.

Grupos de roles, subgrupos de interconectores, referências compartilhadas, linhas Draft, candidatos e previews não contribuem. Várias referências ao mesmo objeto documental são deduplicadas. Componentes A/B distintos nunca são deduplicados por RunKey, posição ou geometria coincidente.

Não se usa `TotalMass` dos membros: esse valor legado segue a massa linear do catálogo e foi integralmente preservado. A nova informação aplica explicitamente a hipótese homogênea de aço a 7850 kg/m³.

## Integridade e indisponibilidade

Antes de disponibilizar um total, o leitor confere `AppliedState`, chaves dos itens físicos serializados, bindings, registros, identidade documental, ownership e estados de geração. Objetos com geração pendente, conflito, `Touched`, `Invalid` ou recompute pendente não recebem um total.

Cada Shape precisa ser válida, não nula e composta exclusivamente de sólidos. Cada sólido precisa ter volume positivo e finito; a soma dos volumes dos sólidos deve concordar com `Shape.Volume`. Uma casca/face ou um Compound misturando sólido e entidades abertas não é convertido silenciosamente em volume de aço.

Peças owned fora dos registros, bindings ausentes, ownership estrangeiro e chapas distintas no mesmo nó produzem diagnósticos. O resultado pode conter contribuições parciais para diagnóstico, mas o total e kg/m ficam indisponíveis quando a cobertura não é completa.

Limitação concreta dos Gussets: o estado aplicado não possui bindings persistentes próprios de placas; o gerador também pode manter uma intenção Gusset em `NominalFallback` sem produzir chapa. Conservadoramente, uma intenção Gusset sem peça física correspondente torna o total indisponível e explica a causa no tooltip. Não se estima a chapa nominal e não se executam resolvedores/geradores para adivinhar sua massa.

## Fórmulas e distância entre apoios

```text
volume_total_mm³ = soma dos Shape.Volume das peças físicas distintas
peso_total_kg = volume_total_mm³ × 7850 × 10⁻⁹
              = volume_total_mm³ × 0,00000785
distância_apoios_m = distância euclidiana entre P0 e P1 aplicados / 1000
peso_linear_kg/m = peso_total_kg / distância_apoios_m
```

O denominador é a distância física reta entre os apoios, inclusive em uma referência inclinada. Não é a soma dos comprimentos das barras nem uma projeção horizontal. Em Duas Águas com referência superior e alturas diferentes, o vão nominal derivado pode diferir desse comprimento. O tooltip informa ambos, além da densidade assumida.

Exemplo medido no gate: Duas Águas inclinada, distância entre apoios 2400,00 mm, vão nominal derivado 2381,35 mm, massa 62,09 kg e peso linear 25,87 kg/m.

## Aplicar, rascunho e lifecycle

O quadro continua na coluna direita de Geometria, com painéis, espaçamento médio, nós e barras nominais. Uma separação discreta precede `Peso total (kg)` e `Peso linear (kg/m)`.

- Treliça nova sem sólidos: `Aguardando aplicação`, valores `—`.
- Treliça existente válida: seção explicitamente identificada como `Última aplicação`. Durante um rascunho válido, esses valores continuam se referindo aos sólidos materializados, como esclarece o tooltip; não são a massa da prévia.
- Candidato inválido ou desatualizado: valores apagados e informação de indisponibilidade.
- Peças físicas incompletas ou inválidas: total indisponível e diagnóstico no tooltip.
- Após Aplicar/OK: o fluxo existente materializa e valida as peças; a atualização do quadro lê os sólidos resultantes.

O leitor não abre transações, escreve propriedades, recompõe geometria, chama `build_candidate()` ou força recompute. Não há cache de massa, observer global ou segunda geração 3D. O estado documental é relido, permitindo Undo/Redo, cópias e reabertura sem depender de referências Python antigas. Os conflitos de sessão já existentes continuam sendo respeitados.

## Testes executados

Python focado: **242 testes passaram**:

```powershell
python -m unittest tests.test_truss_physical_mass tests.test_truss_editor_opening tests.test_truss_lifecycle tests.test_truss_apply_session tests.test_truss_edit_session tests.test_truss_task_panel tests.test_truss_c2 tests.test_truss_c2_references tests.test_truss_c2_editor tests.test_connection_topology_preservation tests.test_truss_manual_fixes tests.test_truss_c2_custom_review tests.test_truss_c2_refinements tests.test_truss_duopitch_ui tests.test_truss_assemblies tests.test_truss_interconnectors tests.test_truss_duopitch_custom tests.test_truss_duopitch_heights tests.test_truss_support_alignment tests.test_truss_regeneration_rollback tests.test_connections_c5b_polish
```

Qt/Units reais do Python do FreeCAD 1.1.4: **54 testes passaram**:

```powershell
& 'C:/Users/marco/Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311/bin/python.exe' -m unittest tests.test_truss_length_precision tests.test_truss_reference_fields tests.test_gusset_preview_qt_c6q tests.test_truss_visual_polish
```

Cobertura inclui pt_BR/en_US/de_DE, agrupamento regional, preferências globais de precisão diferentes, esquemas mm/cm/m/in/ft e imperial adaptativo, valor pequeno, doubles completos, digitação científica, texto parcial, seleção, Enter/Tab/Escape, erros dimensionais e contexto de unidades após consultas de tamanho. Os testes Qt de apresentação usam adaptadores controlados; os testes numéricos e gates abaixo usam Units/Qt reais.

Gates em instâncias isoladas e ocultas do FreeCAD **1.1.4**:

| Comando | Verificações aprovadas |
|---|---:|
| `python scripts/run_truss_duopitch_gate.py --probe mass` | 79 |
| `python scripts/run_truss_duopitch_gate.py --probe editor --editor-theme Classic` | 402 |
| `python scripts/run_truss_duopitch_gate.py --probe editor --editor-theme 'FreeCAD Dark'` | 402 |
| `python scripts/run_truss_duopitch_gate.py --probe editor --editor-qss 'C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss'` | 402 |
| `python scripts/run_truss_duopitch_gate.py --probe apply` | 54 |
| `python scripts/run_truss_duopitch_gate.py --probe lifecycle` | 95 |
| **Total** | **1434** |

O gate de massa confere Paralela, Duas Águas inclinada, massa alterada por recorte oblíquo e extensão via pipeline suportado, perfis compostos, quatro tipos de interconectores, Gusset presente/ausente, peças ocultas, referência por identidade, leitura sem recompute/transação/objetos adicionais, atualização após Aplicar, Aplicar repetido, texto válido pendente durante refresh, texto inválido e recuperação, Cancelar após Aplicar, Undo/Redo, cópia independente, exclusão da cópia e save/reopen. Os testes Python complementam com grupos/referências repetidas, colisão de nomes entre documentos, placa duplicada por nó, Shape inválida/não sólida/mista e volumes inválidos. Os gates do editor cobrem referências por pontos/Draft, temas, larguras 560/220, aberturas repetidas, Qt e documento legado sem marcador de face externa.

Exemplos do gate de massa: a Paralela simples passou de 71,1323534605 kg para 70,3132383229 kg após recorte/ajuste real. A composição com presilhas e Gusset passou de 90,3482571219 kg para 96,3226407576 kg após Aplicar nova altura; a UI apresentou 96,32 kg e 40,13 kg/m. Dígitos completos são registrados apenas nos artefatos de diagnóstico, não como falsa precisão da UI.

`python scripts/check_project.py` e `git diff --check` passaram. Avisos de CRLF preexistentes e depreciações Qt no harness foram observados; nenhum erro de execução foi ocultado. A suíte completa não foi executada, conforme solicitado; FreeCAD 1.1.3 não foi revalidado nesta rodada.

Os resultados, manifests SHA-256, logs, screenshots e FCStd de teste estão em `test-results/truss-duopitch/`. `test-results/truss_physical_mass/gate_audit.json` relaciona as execuções finais e confere os hashes dos fontes testados. `baseline.json` e `final_scope.json` documentam a preservação dos demais arquivos locais, incluindo StructuralPlate, estudos Gusset, experimentos e documentos do usuário.

## Arquivos deste incremento

| Arquivo em `freecad/SteelStructures/` | Alteração |
|---|---|
| `trusses/physical_mass.py` (novo) | Leitor físico, integridade, volumes e fórmulas |
| `interactive/truss_units.py` (novo) | Apresentação de comprimentos com unidades/locale |
| `interactive/truss_length_spinbox.py` (novo) | Controle nativo com precisão interna e edição preservadas |
| `interactive/truss_reference_field.py` | Duas casas nas coordenadas e entrada com agrupamento regional |
| `interactive/truss_task_panel.py` | Campos lineares, spacings, mensagens e validação de edição parcial |
| `interactive/truss_editor_fields.py` | Espelhos, informações e última massa aplicada |
| `interactive/truss_topology_editor.py` | Campos lineares do diálogo existente |
| `interactive/truss_preview.py` | Cotas lineares formatadas |
| `interactive/assembly_editor.py` | Comprimentos, gaps e resumos da composição |
| `interactive/interconnector_editor.py` | Distâncias dos interconectores |
| `interactive/assembly_preview.py` | Cota entre eixos |

Validação: `scripts/run_truss_duopitch_gate.py`, `tests/manual_freecad_truss_mass.py` (novo), `tests/manual_freecad_truss_editor.py`, `tests/test_truss_physical_mass.py` (novo), `tests/test_truss_length_precision.py` (novo), `tests/test_truss_reference_fields.py`, `tests/test_gusset_preview_qt_c6q.py`, `tests/test_truss_duopitch_ui.py` e este relatório.

## Limitações e validação manual pendente

A densidade é convencional e homogênea: não representa seleção de material, soldas, parafusos não materializados ou peças fora dos registros da treliça. Uma intenção nominal de Gusset não recebe massa estimada. Nenhuma dessas limitações altera os sólidos ou o `TotalMass` legado.

Foram executados gates nativos automatizados e inspecionadas imagens do quadro e do Editor, incluindo OpenDark. Isso não equivale a uma nova aprovação manual do usuário. Capturas de widgets destacados de uma janela oculta podem perder o fundo herdado no FreeCAD Dark; os controles reais e estados foram exercitados pelo gate, mas contraste no TaskView visível e DPI próprio da estação continuam no roteiro manual.

## Roteiro manual — FreeCAD 1.1.4 / OpenDark

1. Criar uma Paralela; conferir duas casas no vão, alturas, P0/P1 e espaçamentos. Abrir o Editor e confirmar que o novo quadro não reduz o canvas. Antes da primeira aplicação, conferir `Aguardando aplicação`.
2. Digitar um comprimento com unidade, por exemplo `1,25 m`; selecionar parte do texto, mudar o tamanho do painel e conferir preservação. Digitar `1e`, tentar confirmar e conferir erro sem substituição. Usar Escape e reparar o mesmo valor. Repetir no Editor.
3. Aplicar e conferir peso total, kg/m e tooltip de densidade/apoios. Alterar altura sem aplicar: a seção deve continuar identificada como `Última aplicação`. Aplicar novamente e conferir atualização. Repetir Aplicar sem mudanças; cancelar um rascunho posterior e reabrir.
4. Repetir em Duas Águas com apoios inclinados e alturas diferentes. Conferir no tooltip distância P0–P1 e vão nominal derivado. Testar composição, interconectores e Gusset física; ocultar peças e conferir que continuam contabilizadas. Para intenção sem chapa materializada, conferir indisponibilidade/diagnóstico.
5. Fazer Undo/Redo, cópia independente, exclusão da cópia, salvar/reabrir e abrir uma treliça antiga. Comparar pesos e ausência de modificações geométricas. Conferir também Classic/FreeCAD Dark, TaskPanel estreito e DPI usado normalmente.
