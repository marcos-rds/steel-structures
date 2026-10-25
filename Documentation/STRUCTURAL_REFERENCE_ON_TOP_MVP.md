# Referências estruturais em primeiro plano — investigação e MVP

24/10/2026. Branch `develop/0.7.0`, HEAD `f303f81`. Incremento local.

**Avaliação: viável, com baixo risco no domínio comprovado do FreeCAD 1.1.4.**
Implementado o MVP para linhas e extremidades. **GO para validação manual.**
Não houve migração de schema, alteração da engine, criação de objetos persistentes
nem escrita em propriedades físicas, paramétricas ou visuais dos membros.

## Contrato entregue

| Modo efetivo | Referências |
| --- | --- |
| Físico | Profundidade normal; sólidos podem ocultar linhas e pontos, como antes |
| Estrutural | Linhas e extremidades em primeiro plano sobre a geometria 3D |
| Raio X | Linhas e extremidades em primeiro plano, sem atenuação pelas superfícies translúcidas |

São preservados os três botões, sua exclusividade, os toggles independentes,
cores `#55C8D0`/laranja/branco, espessuras 2,5/4,5, tracejado `0x03FF` e DPR.
Não há nova preferência ou comando. Tooltips dos dois presets informam a
apresentação em primeiro plano. Continuam sendo **extremidades nominais**, sem
inferência de nós conectados ou contato físico.

Usa-se o modo **efetivo**, não apenas o solicitado: pausa durante tarefa/edição,
documento inativo e fallback ao Físico também restauram a profundidade normal.
Elegibilidade e visibilidade das fontes continuam filtradas pelo serviço existente;
o recurso não revela referências de membros previamente ocultos.

## Alternativas e decisão

| Abordagem | Avaliação |
| --- | --- |
| Depth bias / PolygonOffset | Adequado a proximidade de superfícies; não resolve occlusão arbitrária por um perfil sem deslocamentos dependentes da câmera. Descartado |
| Somente `SoDepthBuffer.test=False` | Expõe referências sobre opacos, mas o passe transparente posterior ainda mistura suas cores. Insuficiente |
| Superimposition/overlay do render manager | Exigiria integração adicional de câmera, captura e lifecycle; desnecessário para esta camada 3D existente |
| `SoAnnotation` + depth local desligado | **Adotado:** desenho tardio nativo, usando o mesmo lote e câmera da cena |

O Coin implementa SoAnnotation com caminhos adiados e teste de profundidade
desligado no passe tardio. Apenas as referências entram nesse ramo; não se muda
o depth buffer global, o algoritmo de transparência ou o render manager.
[SoAnnotation e implementação](https://github.com/coin3d/coin/blob/master/src/nodes/SoAnnotation.cpp),
[SoRenderManager](https://www.coin3d.org/coin/classSoRenderManager.html).

O realce on-top do próprio FreeCAD também utiliza caminhos adiados, de modo que
a ordem exige prova, não somente inspeção da API. O attachment das referências
fica depois do contexto nativo. Seleção e preselection foram exercitadas nos gates.
[FreeCAD 1.1.4 — seleção](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Gui/Selection/SoFCUnifiedSelection.cpp).

### Prova anterior às alterações de produção

Processo isolado: `probe-1792883249356758100`, saída 0, seis verificações e logs
limpos. Comparou oclusão normal, depth desligado e annotation sobre perfil e
obstrução opaca/transparente/selecionada, também com Raio X.

Pixels com as cores originais na faixa controlada, DPR 1:

| Caso | Só depth desligado: eixo/ponto | Annotation: eixo/ponto |
| --- | --- | --- |
| Obstrução opaca | 826 / 98 | 826 / 98 |
| Obstrução transparente 65% | 0 / 0 | 826 / 98 |
| Raio X | 0 / 0 | 826 / 98 |

Zero significa ausência da **cor original** nessa medição: a referência pode
estar ocultada ou visualmente atenuada pela composição. Os renders também foram
inspecionados. Forçar as alternativas no Físico fez parte somente dessa prova;
o Físico entregue continua com profundidade normal.

## Integração e reversibilidade

`ReferenceLayer.root` continua sendo o lote único de coordenadas, linhas e
marcadores. `node` identifica o attachment efetivo: root direto no Físico ou root
dentro de um SoAnnotation privado nos presets. Não se duplica a geometria.

Root e annotation possuem pins nativos explícitos durante reparenting. O teste
de profundidade muda apenas no lote; depth write permanece desligado e
`UNPICKABLE` permanece ativo. Não há callback de mouse, material global, mudança
de comprimento/Placement ou recompute para alternar prioridade.

A sincronização ocorre depois da apresentação dos modos e antes de qualquer
retorno por ausência de geometria suja. Assim, pausa/retorno não dependem de
resolver eixos novamente. A desmontagem destaca as referências enquanto o pin da
cena ainda está vivo, esvazia os ramos próprios e só depois fecha a apresentação.
Rollback do construtor e cleanup têm guards/finally; chamadas repetidas são seguras.

Os wrappers de ObjectGroup/GroupOnTop, a cópia Raio X, a leitura nominal e as
transações anteriores não foram reimplementados. A revisão técnica independente
de leitura aprovou a integração após as proteções de lifetime; não substitui os
gates nem a aprovação visual do usuário.

## Arquivos do incremento

| Arquivo | Alteração |
| --- | --- |
| `freecad/SteelStructures/interactive/structural_reference_view.py` | Attachment tardio, depth local, pins, cleanup e sincronização pelo modo efetivo |
| `freecad/SteelStructures/interactive/structural_reference_modes.py` | Somente tooltips e docstring da apresentação |
| `tests/test_structural_reference_view.py` | Três testes novos, guards de cleanup e assertions de modo efetivo |
| `tests/manual_structural_display_modes.py` | Verificação de prioridade em multiview, pausa e documento inativo |
| `tests/manual_structural_reference_visualization.py` | Cleanup pelo attachment efetivo, métricas e chamada do gate novo |
| `tests/manual_structural_reference_on_top.py` | Novo: captura e medição de visibilidade/picking |
| `scripts/run_structural_reference_visualization_gate.py` | Manifesto inclui o gate novo |
| `Documentation/STRUCTURAL_REFERENCE_DISPLAY_MODES.md` | Link de evolução, mantendo o histórico |
| `Documentation/STRUCTURAL_REFERENCE_ON_TOP_MVP.md` | Este relatório novo |

Nenhuma alteração nos comandos/botões, ícones, catálogos, objetos de membros,
treliças, Grid, ajuste, Meia-esquadria ou estudos locais não relacionados.

## Validação

**371 testes Python direcionados aprovados**, 2,265 s, sem failures/errors/skips.
Os três casos novos verificam lote único e toggles em 20 ciclos de prioridade,
pins balanceados, attachment ausente e remoção antes de liberar o contexto,
inclusive com falha simulada de fechamento. Os testes do serviço comprovam
restauração de prioridade em pausa e documento inativo sem novas leituras.

Comando: os mesmos 21 módulos direcionados da rodada anterior, registrados em
`targeted-result.json`/`targeted.log` da pasta de evidências. Não houve suíte completa.

Os gates FreeCAD 1.1.4/Windows exercitam 12 capturas quantitativas por execução:
Físico/Estrutural/Raio X com obstruções 0/65%, seleção, preselection, pontos
isolados, linhas isoladas, ambas desligadas e retorno ao Físico. Verificam cores
completas, picking físico, ausência de novas entradas Undo/escritas e limpeza.
Continuam as regressões de persistência, hierarquias, treliças, multiview e modos.

### Gates finais FreeCAD 1.1.4 / Windows

| Tema | DPR | Execução | Checks | Resultado |
| --- | --- | --- | --- | --- |
| Classic | 1,0 | `1792884059194872200_Classic_095krmqf` | 252 | PASS |
| FreeCAD Dark | 1,0 | `1792884108422463700_FreeCAD_Dark_iv_kopwx` | 252 | PASS |
| OpenDark | 1,0 | `1792884225520577400_OpenDark_34g2imwc` | 252 | PASS |
| OpenDark 150% | 1,5 | `1792884361529401100_OpenDark_4siu2oe3` | 252 | PASS |

**1.008 verificações**, quatro saídas 0, sem timeout, erros nativos ou callbacks
Python/Qt capturados. Os 162 hashes dos manifestos finais coincidem entre si e
com o workspace. Capturas W/U, treliças e cenas de obstrução foram inspecionadas
nos três temas e em DPR 1,5. São testes nativos automatizados com inspeção dos
renders; a aprovação manual do usuário continua pendente.

```powershell
python -B -m unittest -v tests.test_structural_reference_modes tests.test_structural_reference tests.test_structural_reference_view tests.test_general_tools tests.test_grid_command tests.test_member_axis_source tests.test_member_axis_creation tests.test_member_placement tests.test_member_orientation tests.test_column_command tests.test_draft_native_member_tool tests.test_grid_object tests.test_grid_view tests.test_truss_copy tests.test_truss_lifecycle tests.test_truss_apply_session tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_miter_controller tests.test_member_miter_preview tests.test_member_plane_cut
python scripts/run_structural_reference_visualization_gate.py --theme Classic --output-root test-results/structural-reference-on-top/native
python scripts/run_structural_reference_visualization_gate.py --theme "FreeCAD Dark" --output-root test-results/structural-reference-on-top/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --output-root test-results/structural-reference-on-top/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --scale-factor 1.5 --output-root test-results/structural-reference-on-top/native
python scripts/check_project.py
git diff --check
```

`check_project.py` e whitespace aprovados, incluindo verificação equivalente
`--no-index --check` dos arquivos locais não rastreados. Não foi executada a suíte
completa. A primeira prova teve apenas uma incompatibilidade no leitor de pixels
Qt (memoryview versus ponteiro); o harness foi ajustado sem alterar produção.
Runs anteriores ao fechamento dos guards são diagnósticos, preservados na pasta
de evidências; os quatro resultados acima correspondem ao mesmo código final.

## Limites conhecidos e roteiro manual

- A prioridade é sobre a geometria 3D. Qt, HUD/navigation cube e annotations de
  terceiros adicionadas posteriormente podem ter precedência própria.
- Câmera, frustum e clipping continuam válidos; não é HUD fixo na tela.
- Referências cruzadas/sobrepostas em projeção deixam de indicar profundidade.
  Coincidência visual não confirma conectividade. Não há novo picking ou snap.
  No Raio X, um clique ainda escolhe o físico nativo, que pode não ser o dono do
  marcador sobreposto sob o cursor.
- A árvore anexada da camada tem 24 nós no Físico e 25 nos presets, também em
  100/1.000 membros. O annotation privado fica desanexado no Físico. Não há
  reconstrução de buffers para mudar prioridade.
  O custo preexistente de cópias do Raio X permanece; não foi medido FPS/p95.
- Certificado no FreeCAD 1.1.4 disponível. Outros drivers, algoritmos customizados
  de transparência, renderers externos e DPI físico entre monitores não foram
  certificados. A aprovação visual dos modelos reais permanece pendente.

1. Reiniciar a bancada/FreeCAD para carregar o código. Em W/U opaco no Físico,
   ligar eixos e extremidades: observar a oclusão normal.
2. Alternar Estrutural/Raio X em pórticos e treliças. Conferir linhas turquesa e
   discos laranja/branco completos sobre os perfis, incluindo transparência manual.
3. Selecionar/preselecionar sólidos em Raio X: o realce nativo deve continuar,
   com referências por cima. No Estrutural, usar a árvore como antes.
4. Mostrar somente linhas, somente pontos, ambas e nenhuma. Voltar ao Físico e
   confirmar restauração dos toggles anteriores e da profundidade normal.
5. Orbitar e variar zoom, inclusive em muitos membros sobrepostos. Conferir a
   perda intencional de profundidade, sem interpretar cruzamentos como ligações.
6. Abrir/cancelar tarefa, trocar documento/vista, fechar viewport e desativar a
   bancada. Não devem restar referências ou ramos órfãos. Repetir nos três temas
   e em OpenDark 150%.

## Preservação e decisão

O inventário desta rodada é de sete arquivos modificados e dois novos. O snapshot
inicial, hashes, manifestos e resultados ficam em
`test-results/structural-reference-on-top/`. A integridade é comparada ao workspace
local inicial, preservando o incremento anterior ainda sem commit. As fontes da
engine, o resolvedor nominal, o controlador dos modos e os demais estudos não
relacionados não mudaram; os objetos/transações são também verificados nos gates.
Dos 619 arquivos iniciais, 612 permaneceram byte a byte idênticos. Não houve novas
divergências nos modelos/backups do usuário nesta rodada.

Eventuais edições concorrentes do modelo `copiatreliça2.FCStd` e seus backups,
cuja preservação já foi solicitada pelo usuário, são tratadas separadamente no
inventário. Não se restaura nenhuma versão antiga sobre arquivos do usuário.
HEAD e índice Git permanecem inalterados. Nenhum staging, commit, push, merge,
tag, release ou limpeza destrutiva foi executado.

**GO para validação manual. Confirmação explícita: não houve migração de schema
nem alteração persistente em membros ou suas propriedades visuais.**
