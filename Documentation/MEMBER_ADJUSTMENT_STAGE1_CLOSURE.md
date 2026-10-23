# Etapa 1 — fechamento técnico de Recortar / Ajustar Membro

**Atualização de 23/10/2026: GO técnico para commit local**, após reprodução
causal e correção mínima do detector de mudanças. Ver o
[complemento técnico](#complemento-técnico--resolução-do-no-go-em-23102026)
ao final. O NO-GO de 22/10 abaixo é histórico e foi superado; nenhuma ação de
staging/publicação foi executada. Release continua fora da certificação desta etapa.

Data: 22/10/2026. Branch `develop/0.7.0`.
Base: `fd96c2fe34586d9dbc099994e2e0bd4d7e02a768` (`fd96c2f`), informada
pelo usuário como HEAD publicado. A comparação desta rodada usa esse objeto
Git local; não houve consulta ao remoto.

**Decisão histórica em 22/10: NO-GO técnico para commit local**, até esclarecer
uma falha intermitente de atualização automática do preview no gate OpenDark.
O inventário e a árvore seletiva estão preparados, mas não devem ser tratados
como uma certificação sem pendências. **Release: NO-GO**, separadamente.
Nenhum `git add`, commit, push, merge, tag ou release foi executado.

## Aprovação manual e escopo

O usuário informou ter concluído e aprovado a validação manual de geometria
candidata, corte convencional/inclinado, diagnóstico e bloqueio de inválidos,
cancelamento, Undo/Redo, restauração do eixo nominal, membros de treliças e
apresentação visual. Essa aprovação foi registrada como evidência do usuário;
não é uma nova sessão manual executada pelo auditor.

Foram lidos integralmente [a auditoria da base](MEMBER_ADJUSTMENT_TECHNICAL_AUDIT.md)
e [o relatório da implementação](MEMBER_ADJUSTMENT_STAGE1.md). Ambos permanecem
inalterados e devem ser lidos em ordem histórica: a auditoria descreve a base
sem preview; o relatório da etapa descreve a implementação e seus testes
anteriores; este documento registra o fechamento e a pendência encontrada agora.

Nesta rodada não houve alteração de código de produção, testes do incremento,
semântica, catálogos, propriedades persistentes, schema, versão ou changelog.
A única adição fora de `test-results/` é este relatório. Uma revisão técnica
independente, somente leitura, não encontrou bloqueador estático nos caminhos
de confirmação e limpeza; a falha dinâmica descrita abaixo permanece aberta.

## Limitar comprimento e Recortar pelo plano

A observação manual em membros inclinados corresponde ao contrato existente.
Em `member_adjustment_controller.py:_reference_geometry()` e
`member.py:resolve_slot()`, **Limitar comprimento (`LengthLimit`)** obtém uma
estação sobre o eixo nominal infinito: interseção com o plano suporte da Face,
ou ponto de menor distância à reta suporte da Edge. A normal da Face não é
conservada como plano de corte. O sólido termina perpendicular ao eixo local,
por extrusão da seção até a estação axial.

Portanto, quando o plano de referência é oblíquo ao eixo, pontos da seção podem
ultrapassá-lo, mesmo com a estação axial correta. Inclinar o membro, por si só,
não causa ultrapassagem: a diferença depende da orientação relativa do plano,
do eixo e da extensão transversal da seção. Esse modo não promete conter todo
o volume em um semiespaço do plano de referência.

**Recortar pelo plano (`PlaneCut`)** usa a estação e conserva a normal,
convertida ao referencial local. `member.py` e `member_plane_cut.py` geram o
corte planar real, inclusive oblíquo; o caso perpendicular usa extrusão direta.
Com gap zero, a extremidade segue o plano. Nos dois modos, gap positivo recua
a ponta e negativo prolonga, medidos **ao longo do eixo**, não pela distância
normal ao plano. `AdjustedLength` também é axial. Nenhuma dessas convenções
foi alterada neste fechamento.

## Auditoria da confirmação e do ciclo de vida

O snapshot de `member_batch.prepare_member()` não copia a Shape anterior.
A avaliação candidata executa o pipeline real do membro e exige nova Shape
não nula, válida, com volume positivo e finito. O controlador reavalia a
referência e a candidata no OK, antes de abrir a transação. Após gravar e
recomputar, rejeita estado `Invalid`, Shape inválida, status de geração do
filho diferente de `Valid` e divergências de comprimento ajustado, massa,
volume ou Placement. Exceções abortam a transação.

Isso impede interpretar a proteção legítima da última Shape do filho como
sucesso de uma operação inválida atual nos caminhos auditados. A comparação
de produção usa saídas/volume/Placement; equivalência BRep por diferenças
booleanas nos dois sentidos é uma verificação adicional do gate nativo.
Não se afirma uma prova exaustiva para todas as entradas OCC possíveis.

Na reprodução da base, **4/8 operações inválidas foram aceitas**, todas em
filhos de treliças, nas combinações LengthLimit/PlaneCut e Fixed/Associative.
A Shape anterior permaneceu, mas propriedades inválidas foram gravadas e
restauradas do FCStd. Na candidata, os oito casos foram recusados em cada
execução completa, preservando propriedades, saídas, Shape, Undo e restauração
FCStd. Os testes também cobrem Shape anterior com `Invalid`/erro de geração,
falha OCC, volume não finito, candidato que se torna inválido após preview
válido e rollback de falha injetada depois do recompute.

O preview usa branch Coin temporário, sem objeto auxiliar de documento nem
transação de preview. A máscara do original não escreve Visibility persistente.
A finalização idempotente remove o branch, restaura apresentação, remove o
observer de seleção e para/desconecta o QTimer; a referência do filtro de
eventos ao painel é limpa. O timer/filtro pertence ao formulário. Não foi
introduzido observer de documento nem callback de viewport.

Os gates completos verificaram ausência dos resíduos monitorados após OK,
Cancelar, Esc em controle filho, fechamento do formulário, fechamento nativo
da tarefa e comando público; também cobriram troca/exclusão de alvo/referência,
mudança de vista e fechamento de documento. Não houve objeto temporário,
branch, observer de seleção ou timer ativo residual nos caminhos aprovados,
nem erro capturado de callback Qt/Python. Isso não equivale a um detector geral
de vazamento de memória do processo.

## Árvore candidata e reprodução

Evidências locais: [`test-results/member_adjustment_closure/`](../test-results/member_adjustment_closure/).
`baseline/` foi extraída por `git archive` do SHA completo acima; `candidate/`
recebeu exclusivamente os 14 arquivos da seleção abaixo. Não é worktree e
não tem índice Git próprio. Nenhuma branch ou índice do usuário foi alterado.

`base.zip`, `selection.json`, `tracked-stage1.patch`, `candidate-manifest.json`
e `staging-list.txt` registram origem, seleção e hashes. Diretórios internos
`test-results/` contêm apenas evidências de execução e ficam fora do incremento.
O relatório foi copiado à candidata depois da execução da suíte; nenhum arquivo
Python ou recurso executável mudou desde essa execução.

Os helpers de fechamento ficam apenas em evidências e não integram a seleção:

```powershell
python test-results/member_adjustment_closure/closure_harness.py setup
python test-results/member_adjustment_closure/closure_harness.py suite workspace
python test-results/member_adjustment_closure/closure_harness.py suite baseline
python test-results/member_adjustment_closure/closure_harness.py suite candidate
```

Cada execução de suíte usa, na respectiva raiz:

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
```

Python externo: **3.11.9**. Resultados completos em `*-unittest.log`,
`*-unittest-result.json` e `suite-comparison.json`.

| Árvore | Descobertos | Aprovados | Skips | Falhas/erros | Resultado |
| --- | ---: | ---: | ---: | ---: | --- |
| Base fd96c2f | 1.923 | 1.774 | 149 | 0 | OK |
| Candidata seletiva | 1.945 | 1.796 | 149 | 0 | OK |
| Workspace com experimentos locais | 1.949 | 1.800 | 149 | 0 | OK |

Há **22 testes novos**, nenhum removido e nenhuma alteração de resultado nos
testes comuns entre base e candidata. Os quatro extras do workspace pertencem
a `tests/test_plate_qt_lifecycle_probe.py`, dependente de experimento local;
passaram, mas não pertencem ao incremento e não entram na árvore candidata.
Os estudos Gusset já rastreados na base continuam presentes nas duas árvores.

Os mesmos 149 testes são ignorados nas três árvores por requisitos ambientais:
30 exigem GUI/event loop FreeCAD; 26 PySide6 indisponível neste Python;
15 Python nativo FreeCAD/Draft; 47 GUI FreeCAD e Qt; 23 Units FreeCAD e
PySide6 (mensagens em duas capitalizações); 8 PySide6. Não são regressões nem
passes nativos implícitos. Os gates seguintes complementam apenas os fluxos
que efetivamente executam, sem substituir todos esses 149 testes.

Revisão independente executou também:
`python -m unittest tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_placement`:
**56 testes, OK**, sem skips.

## Gates FreeCAD 1.1.4

Os processos usaram FreeCAD **1.1.4**, Python 3.11/Qt6, preferências e documentos
isolados. Nenhum processo/documento já aberto do usuário foi controlado.
Na raiz candidata foram executados:

```powershell
python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme Classic
python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme "FreeCAD Dark"
python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme OpenDark
```

Pastas abaixo são relativas a `candidate/test-results/member_adjustment_stage1/`:

| Tema / tentativa | Resultado | Pasta |
| --- | --- | --- |
| Classic | 288 checks, OK, 0/8 inválidos aceitos | `1792716989415211800_stage1_Classic_6esdsgyf` |
| FreeCAD Dark | 288 checks, OK, 0/8 inválidos aceitos | `1792717030323626000_stage1_FreeCAD_Dark_v_kwvn9e` |
| OpenDark, primeira | **Falhou**, 178 checks anteriores à falha | `1792717108477759200_stage1_OpenDark_ejaca7kj` |
| OpenDark, repetição sem alteração | 288 checks, OK, 0/8 inválidos aceitos | `1792717171703812800_stage1_OpenDark_kixa7bti` |

Os três passes completos somam 864 verificações, não testes independentes.
Verificam W em X/Y, RHS em Z, U simples inclinado, diagonal de treliça,
Detailed/Simplified, offsets/extensões, orientação manual, Face/Edge,
Fixed/Associative, gaps, ambas as pontas, remoção preservando a outra ponta,
geometria por volume/centro/bounds/diferença booleana, massa física de treliça,
recompute, restauração FCStd, transações e Undo/Redo sem deriva do eixo nominal.
Os filtros de logs nativos ficaram vazios nessas execuções, assim como a
captura de erros de callbacks. Foram produzidas capturas, mas não se declara
nova inspeção visual humana delas nesta rodada; a aprovação visual é a do usuário.

A base foi ensaiada com os mesmos runner/probe como instrumentação externa,
sem modificar suas fontes de produção, em `baseline-native/`:

```powershell
python test-results/member_adjustment_closure/native_supplement.py reproduction
```

Internamente: `python scripts/run_member_adjustment_stage1_gate.py --phase reproduction --theme Classic`.
Resultado: 21 checks, reprodução esperada aprovada, **4/8 inválidos aceitos**.
Evidência: `baseline-native/test-results/member_adjustment_stage1/1792717085904348100_reproduction_Classic_f6vkx3z_/`.
Um gate de reprodução aprovado confirma o defeito da base, não sua segurança.

### Pendência de atualização automática — bloqueador deste fechamento

No primeiro OpenDark falhou `external reference updates preview 5`, ao mover
a referência do ajuste inicial associativo de uma diagonal com a outra ponta
já ajustada. O volume continuou `390917.63051817386 mm³`, sem mensagem de erro;
no retry mudou corretamente para `384837.63051817415 mm³`. Oito rejeições de
risco já haviam passado antes desse ponto. O processo saiu com código zero,
mas o runner retornou falha por `result.ok=false`: não foi contabilizado como OK.

Cinco repetições adicionais instrumentadas em `diagnostic/`, com produção
idêntica à candidata e somente o probe de evidência ampliado, passaram
(288 checks cada). Registraram mudança de hash/assinatura da Face e volume
candidato direto igual ao preview atualizado, timer ativo, sem erro. Elas
**não reproduziram nem explicaram a tentativa falha**. Comando:
`python test-results/member_adjustment_closure/diagnose_preview.py`.
Artefatos: `diagnostic/test-results/member_adjustment_stage1/*/diagnostic-reference-5.json`.

Não há evidência suficiente para atribuir a falha ao tema, timing, ambiente
ou colisão/insuficiência de `hashCode()`. A assinatura do painel monitora hash
do subelemento; timer e detecção de mudança permanecem hipóteses. A tentativa
falha não registrou o hash anterior nem os ticks, impedindo concluir a causa.
Não foi classificada como skip ambiental, nem apagada por retries aprovados.

Não foi observada aceitação inválida associada a esse sintoma: o OK reavalia
independentemente a candidata. A pendência é a confiabilidade da atualização
automática do preview, requisito da própria etapa. Para liberar o commit,
é necessário esclarecer a causa com evidência de assinatura/ticks/candidata
direta durante uma falha, ou validar uma correção focada em tarefa posterior.
Não foi aplicada correção nesta auditoria, conforme o escopo solicitado.

### Gates complementares e comparação com a base

Executados, em processos separados por roteiro e árvore:

```powershell
python test-results/member_adjustment_closure/native_supplement.py candidate
python test-results/member_adjustment_closure/native_supplement.py baseline
python test-results/member_adjustment_closure/native_supplement.py candidate draft
python test-results/member_adjustment_closure/native_supplement.py baseline draft
```

O lançador direciona apenas caminhos históricos de saída para a árvore isolada,
configura namespace/imports e mantém as assertivas originais. Manifesta fontes
de produção e hashes original/adaptado do roteiro. Resultados válidos estão
em `supplement-v2/{candidate,baseline}/` e `supplement-draft/{candidate,baseline}/`.

| Roteiro em `tests/` | Candidata | Base | Classificação |
| --- | --- | --- | --- |
| `manual_grid_placement_persistence.py` | OK | OK | Placement z=3000 preservado em FCStd; executado por afetar Placement |
| `manual_freecad_connections_c5b_overrides.py` | 28 checks OK | 28 checks OK | Ferramenta oficial, Manual > AutoFit, reabertura e FCStd |
| `manual_freecad_truss_associative_reopen.py` | 41 checks OK | 41 checks OK | Referências válidas/nulas/apagadas, Shape protegida e reabertura |
| `manual_freecad_connections_c5b.py` | Falha na linha 94 | Mesma falha | `balanced two physical members`; falha preexistente, não gate aprovado |
| `manual_solid_sections_validation.py` | KeyError na linha 57 | Mesmo KeyError | Fixture antiga `round-bar-20` ausente da seleção atual; roteiro incompatível com a base atual |
| `manual_nbr16683_solid_validation.py`, sem Draft ativo | AttributeError | Mesmo AttributeError | Pré-condição ambiental ausente: `App.activeDraftCommand` |
| Mesmo roteiro, Draft inicializado | **75 checks OK** | **75 checks OK** | Cortes, geometria, massa, eixo vinculado, cancelamento e FCStd |

A primeira versão do lançador (`supplement/`) teve falhas de importação
`freecad.SteelStructures`; o namespace foi corrigido somente no helper externo.
Essas tentativas são inválidas como medição do incremento e permanecem salvas.
As falhas de C5-B/fixtures são de roteiros já rastreados, não os quatro testes
experimentais StructuralPlate externos. Não foram alteradas nem ocultadas.
Outros roteiros nativos históricos não listados aqui não foram reexecutados.

## Inventário e seleção preparada

**14 caminhos: 7 modificados e 7 novos em relação a fd96c2f.** A tabela é a
lista fechada para eventual staging seletivo futuro; não é autorização para
executá-lo. Os arquivos já modificados antes desta auditoria foram preservados.

| Estado | Caminho | Papel |
| --- | --- | --- |
| M | `freecad/SteelStructures/commands.py` | Fechamento nativo sem reentrada |
| M | `freecad/SteelStructures/interactive/member_adjustment_controller.py` | Avaliação candidata e confirmação segura |
| M | `freecad/SteelStructures/interactive/member_adjustment_task_panel.py` | Preview, diagnóstico, bloqueio e limpeza |
| M | `freecad/SteelStructures/member.py` | Proteção do eixo nominal durante replay/rollback |
| M | `freecad/SteelStructures/member_batch.py` | Avaliação destacada, Placement e volume finito |
| M | `tests/test_member_adjustment_controller.py` | Regressões de confirmação/candidata |
| M | `tests/test_member_placement.py` | Regressões de replay |
| Novo | `freecad/SteelStructures/interactive/member_adjustment_preview.py` | Preview Coin transiente |
| Novo | `tests/test_member_adjustment_preview.py` | Ownership e limpeza |
| Novo | `tests/manual_member_adjustment_stage1.py` | Gate Qt/Coin/OCC nativo |
| Novo | `scripts/run_member_adjustment_stage1_gate.py` | Runner isolado e manifestos |
| Novo | `Documentation/MEMBER_ADJUSTMENT_TECHNICAL_AUDIT.md` | Histórico da auditoria da base |
| Novo | `Documentation/MEMBER_ADJUSTMENT_STAGE1.md` | Implementação e validações anteriores |
| Novo | `Documentation/MEMBER_ADJUSTMENT_STAGE1_CLOSURE.md` | Este fechamento |

Não usar seleção por diretório, `git add .` ou `git add -A`. Excluir todos os
134 caminhos locais listados no apêndice, além de qualquer artefato ignorado
de `test-results/`, FCStd/backup local, caches e configurações locais. O conjunto
exato também está em `excluded-paths.json`; a seleção, em `staging-list.txt`.

## Integridade e preservação

`python scripts/check_project.py`: aprovado no workspace, base e candidata
(também executado com `-B`). `git diff --check`: aprovado no workspace.
A checagem equivalente dos 14 caminhos candidatos inclui arquivos novos via
`git diff --no-index --check`; não apontou erro de whitespace. Nesse modo,
o código 1 indica as diferenças esperadas entre base e candidata; houve
somente avisos de futura normalização LF/CRLF em arquivos novos, sem alteração
dos arquivos. Saídas e códigos brutos ficam em `integrity-results.json`.

O manifesto inicial contém **583 arquivos** fora de `.git`, `test-results`,
caches/ambientes e estado local do agente. A comparação final confirmou zero
modificações/remoções desses arquivos e somente este relatório novo.
Ela inclui os estudos Gusset, experimentos StructuralPlate, documentação de
outras etapas e os dois FCStd locais. Fontes candidatas são iguais às do
workspace; o delta sobre o arquivo Git da base contém exatamente os 14
caminhos selecionados, sem exclusões ou diferenças adicionais. Ver
`preservation-final.json`, `candidate-base-comparison.json` e `candidate-manifest.json`.
HEAD e referência local `origin/develop/0.7.0` continuam em `fd96c2f`, com
índice vazio.
Evidências históricas em `test-results/` não foram reescritas: esta rodada
usa uma pasta de fechamento nova.

## Avaliação final e mensagem sugerida

| Decisão | Avaliação | Motivo |
| --- | --- | --- |
| Segurança de confirmação nos cenários auditados | GO | Candidata nova, reavaliação no OK, status/saídas e rollback verificados |
| Preparação seletiva | Concluída | Base isolada, inventário fechado, suíte completa e comparações disponíveis |
| Commit local agora | **NO-GO técnico** | Falha intermitente de atualização automática ainda sem causa comprovada |
| Release | **NO-GO** | Pendência acima; esta auditoria não certifica release nem altera versão/metadados |

A aprovação manual do usuário permanece registrada. Não se pede repetir toda
a validação já aprovada. A verificação manual complementar, se necessário ao
diagnóstico, é mover a referência do início associativo de uma diagonal com
fim já ajustado, em OpenDark, e comparar imediatamente preview/diagnóstico com
nova avaliação, registrando se o timer e a assinatura detectaram o movimento.

Mensagem sugerida **para depois da resolução da pendência e autorização**:

```text
Torna seguro o ajuste de membros e adiciona preview da geometria candidata

Reavalia a candidata antes do OK e recusa falhas mesmo com Shape anterior
preservada em filhos de treliças. Adiciona preview Coin transiente e limpeza
da tarefa, preservando o eixo nominal durante Undo/Redo e rollback.

Documenta o contrato axial de Limitar comprimento e os gates da Etapa 1.
```

Não estão no incremento: meia-esquadria automática genérica, recorte por
sólido completo, botão Aplicar, novas modalidades de referência ou mudanças
no fitting automático de treliças.

## Apêndice — exclusões locais explícitas

Os caminhos abaixo são relativos à raiz e permanecem fora da seleção:

```text
Documentation/STRUCTURAL_PLATE_0_7_0_AUTO_PLANE_REFINEMENT.md
Documentation/STRUCTURAL_PLATE_0_7_0_B1.md
Documentation/STRUCTURAL_PLATE_0_7_0_B_RECTANGLE_PILOT.md
Documentation/STRUCTURAL_PLATE_0_7_0_FINAL_UI_REFINEMENT.md
Documentation/STRUCTURAL_PLATE_0_7_0_INPUT_CONSISTENCY.md
Documentation/STRUCTURAL_PLATE_0_7_0_UI_POLISH.md
Documentation/STRUCTURAL_PLATE_0_7_0_UNIFICATION_GATE.md
Documentation/STRUCTURAL_PLATE_0_7_0_UNIFIED_PROTOTYPE.md
Documentation/STRUCTURAL_PLATE_0_7_0_USABILITY_EXTRUSION.md
Documentation/STRUCTURAL_PLATE_QLINEEDIT_BASELINE_DIAGNOSIS.md
Documentation/TRUSS_0_7_0_COMPACT_TASK_PANEL.md
Documentation/TRUSS_0_7_0_DIRECT_DRAFT_REFERENCE.md
Documentation/TRUSS_0_7_0_EDITOR_ACTIONS.md
Documentation/TRUSS_0_7_0_INTERACTIVE_REFERENCE_SELECTION.md
Documentation/TRUSS_0_7_0_REFERENCE_LAYOUT_FIX.md
Documentation/TRUSS_0_7_0_STAGE1_EDIT_SESSION.md
Documentation/TRUSS_0_7_0_STAGE2_LIFECYCLE_UNDO.md
Documentation/TRUSS_0_7_0_STAGE2_REPEAT_APPLY.md
Documentation/TRUSS_0_7_0_STAGE3A_EXPANDED_EDITOR.md
Documentation/TRUSS_0_7_0_STAGE3B1_FUNCTIONAL_TABS.md
Documentation/TRUSS_0_7_0_STAGE3B2_FIVE_TABS.md
Documentation/TRUSS_0_7_0_STAGE3B2_THEME_COMPATIBILITY.md
Documentation/TRUSS_0_7_0_STAGE3B2_TOOLBAR_VISUAL_POLISH.md
Documentation/TRUSS_0_7_0_STAGE3B2_UI_REFINEMENT.md
Documentation/TRUSS_0_7_0_TASK_PANEL_INPUT_REFINEMENT.md
Documentation/TRUSS_0_7_0_UX_UI_RESUME_VALIDATION.md
Documentation/TRUSS_0_7_0_VISUAL_POLISH.md
Documentation/gusset_family_review/CONFIGURACOES.md
Documentation/gusset_family_review/ESTRATEGIA.md
Documentation/gusset_family_review/F01_01.svg
Documentation/gusset_family_review/F01_02.svg
Documentation/gusset_family_review/F02_01.svg
Documentation/gusset_family_review/F02_02.svg
Documentation/gusset_family_review/F02_03.svg
Documentation/gusset_family_review/F02_04.svg
Documentation/gusset_family_review/F02_05.svg
Documentation/gusset_family_review/F02_06.svg
Documentation/gusset_family_review/F02_07.svg
Documentation/gusset_family_review/F02_08.svg
Documentation/gusset_family_review/F02_09.svg
Documentation/gusset_family_review/F02_10.svg
Documentation/gusset_family_review/F03_01.svg
Documentation/gusset_family_review/F03_02.svg
Documentation/gusset_family_review/F03_03.svg
Documentation/gusset_family_review/F03_04.svg
Documentation/gusset_family_review/F04_01.svg
Documentation/gusset_family_review/F04_02.svg
Documentation/gusset_family_review/F04_03.svg
Documentation/gusset_family_review/F04_04.svg
Documentation/gusset_family_review/F04_05.svg
Documentation/gusset_family_review/F05_01.svg
Documentation/gusset_family_review/F06_01.svg
Documentation/gusset_family_review/F07_01.svg
Documentation/gusset_family_review/F07_02.svg
Documentation/gusset_family_review/F07_03.svg
Documentation/gusset_family_review/F07_04.svg
Documentation/gusset_family_review/F07_05.svg
Documentation/gusset_family_review/F08_01.svg
Documentation/gusset_family_review/F09_01.svg
Documentation/gusset_family_review/MATRIZ.md
Documentation/gusset_family_review/index.html
Documentation/gusset_phase1/A_propostas.svg
Documentation/gusset_phase1/B_propostas.svg
Documentation/gusset_phase1/C_propostas.svg
Documentation/gusset_phase1/PROPOSTAS.md
Documentation/gusset_phase1/coordenadas.json
Documentation/gusset_phase1/coordenadas.md
Documentation/gusset_round1/F01_01.svg
Documentation/gusset_round1/F01_02.svg
Documentation/gusset_round1/F02_01.svg
Documentation/gusset_round1/F02_02.svg
Documentation/gusset_round1/F02_03.svg
Documentation/gusset_round1/F02_04.svg
Documentation/gusset_round1/F02_05.svg
Documentation/gusset_round1/F02_06.svg
Documentation/gusset_round1/F02_07.svg
Documentation/gusset_round1/F02_08.svg
Documentation/gusset_round1/F02_09.svg
Documentation/gusset_round1/F02_10.svg
Documentation/gusset_round1/F03_01.svg
Documentation/gusset_round1/F03_02.svg
Documentation/gusset_round1/F03_03.svg
Documentation/gusset_round1/F03_04.svg
Documentation/gusset_round1/F04_01.svg
Documentation/gusset_round1/F04_02.svg
Documentation/gusset_round1/F04_03.svg
Documentation/gusset_round1/F04_04.svg
Documentation/gusset_round1/F04_05.svg
Documentation/gusset_round1/F05_01.svg
Documentation/gusset_round1/F06_01.svg
Documentation/gusset_round1/F07_01.svg
Documentation/gusset_round1/F07_02.svg
Documentation/gusset_round1/F07_03.svg
Documentation/gusset_round1/F07_04.svg
Documentation/gusset_round1/F07_05.svg
Documentation/gusset_round1/F08_01.svg
Documentation/gusset_round1/F09_01.svg
Documentation/gusset_round1/RELATORIO.md
Documentation/gusset_round1/estudos/F04_03.json
Documentation/gusset_round1/estudos/F04_03.svg
Documentation/gusset_round1/estudos/F04_04.json
Documentation/gusset_round1/estudos/F04_04.svg
Documentation/gusset_round1/estudos/F08_01.json
Documentation/gusset_round1/estudos/F08_01.svg
Documentation/gusset_round1/estudos/index.html
Documentation/gusset_round1/index.html
Documentation/gusset_round1/resultados.json
Documentation/gusset_tip_depth/CRITERIO.md
Documentation/gusset_tip_depth/F04_03.svg
Documentation/gusset_tip_depth/F04_04.svg
Documentation/gusset_tip_depth/HP_limite.svg
Documentation/gusset_tip_depth/coordenadas.json
Documentation/gusset_tip_depth/index.html
Documentation/gusset_tip_round2/CRITERIO.md
Documentation/gusset_tip_round2/F04_01.svg
Documentation/gusset_tip_round2/F04_02.svg
Documentation/gusset_tip_round2/F04_03.svg
Documentation/gusset_tip_round2/F04_04.svg
Documentation/gusset_tip_round2/F04_05.svg
Documentation/gusset_tip_round2/coordenadas.json
Documentation/gusset_tip_round2/index.html
scripts/diagnose_plate_heap.py
scripts/diagnose_plate_qt_lifecycle.py
scripts/diagnose_plate_tracker_stability.py
tests/copiatreliça.FCStd
tests/copiatreliça2.FCStd
tests/manual_plate_heap_comparison.py
tests/manual_plate_heap_setvalues_probe.py
tests/manual_plate_numeric_input.py
tests/manual_plate_qt_lifecycle.py
tests/manual_plate_rectangle_lifecycle_gate.py
tests/manual_plate_tracker_stability.py
tests/manual_point_input_probe.py
tests/test_plate_qt_lifecycle_probe.py
```

## Complemento técnico — resolução do NO-GO em 23/10/2026

**Resultado atual: GO técnico para commit local da Etapa 1.** O detector
anterior foi reproduzido falhando naturalmente e por um controle determinístico;
a correção elimina essa falha sem mudar operações geométricas ou lifecycle.
Nenhum staging, commit, push, merge, tag ou release foi executado.

### Recuperação da ocorrência original

A execução original e seus arquivos foram preservados byte a byte em
`test-results/member_adjustment_closure/candidate/test-results/member_adjustment_stage1/1792717108477759200_stage1_OpenDark_ejaca7kj/`.
Foram recuperados `result.json`, `checks.json`, `reference-update-5.json`,
manifesto de fontes, stdout/stderr e log nativo. Os hashes desses arquivos
estão em `test-results/member_adjustment_preview_sync/original-failure-manifest.json`.

Comando original, na candidata anterior: `python scripts/run_member_adjustment_stage1_gate.py --phase stage1 --theme OpenDark`.
O runner executava `bin/freecad.exe --write-log --log-file <pasta>/FreeCAD.log <raiz>/tests/manual_member_adjustment_stage1.py`,
com SS_ADJUST_ROOT/OUT/PHASE/THEME e perfil isolado definidos pelo runner.
O processo FreeCAD saiu com código zero; o runner corretamente recusou
`result.ok=false`. Havia 178 checks anteriores à falha.

O roteiro tinha acabado de aplicar o fim fixo oblíquo de uma diagonal.
Na abertura seguinte propunha `LengthLimit`, início associativo, gap de 15 mm.
Mover a Face 20 mm ao longo do eixo deveria mudar a estação de
438,634243989 para 458,634243989 mm e reduzir o volume de
390917,63051817386 para 384837,63051817415 mm³. O gate observou candidata
ainda válida, porém com o volume anterior, sem diagnóstico de erro.
O registro original não incluía hash anterior, ticks ou captura do sexto
preview; sozinho, ele não demonstrava a causa nem distinguia Coin e candidata.

### Causa demonstrada e classificação

A mesma divergência foi reproduzida com produção anterior intacta em
**FreeCAD Dark**, sem depender de OpenDark:

`test-results/member_adjustment_preview_sync/instrumented/test-results/member_adjustment_stage1/1792791907231488600_stage1_FreeCAD_Dark_8yicszds/trace-5.json`.

| Camada | Evidência nessa reprodução |
| --- | --- |
| Antes do movimento | Seq. 99–105 publicam candidata correta para a entrada anterior; seq. 106 captura a baseline |
| Referência | Seq. 107 atribui Placement; seq. 108 conclui recompute; plano global/estação direta mudaram |
| Eventos Qt | Seq. 109–138: **dez polls reais**, timer ativo; nenhuma chamada de refresh depois do movimento |
| Assinatura | Hash **−2034574800** antes e depois; assinatura observada igual a `_watch_state` em todos os polls |
| Cálculo direto | Estação 458,634243989 mm e volume 384837,63051817415 mm³ corretos |
| Estado do painel | Candidata conservada em estação 438,634243989 mm e volume 390917,63051817386 mm³ |
| Coin | Shape exportada e bounds do branch ainda correspondiam ao estado anterior |

**Defeito de produção confirmado:** `_reference_signature()` usava apenas
nome/subelemento/hash para reconhecer mudanças da referência. A igualdade do
hash nativo, apesar de mudança do suporte geométrico global, impedia o refresh.
Não se usa hash como identidade geométrica única após a correção.

Não foi observação prematura do gate: dez polls já haviam concluído sem
atualização. O cálculo compartilhado estava correto; a falha ocorreu antes
da substituição da candidata/branch. Não era somente repaint atrasado do
viewport. Não houve sobreposição de refreshes na transição falha nem evidência
de timer parado/desconectado. A captura original não permite recuperar seu
hash anterior, mas a reprodução com a mesma produção demonstrou o mesmo
sintoma, volumes e transição, e isolou o mecanismo causal.

Três controles nativos adicionais substituíram **somente o campo hash** da
assinatura por uma constante, mantendo geometria, objetos FreeCAD, timer e
pipeline reais. Com o detector anterior, **3/3 falharam**, uma vez em cada
tema, na primeira comparação de candidata após movimento. Com a correção,
o mesmo controle passa. Não se depende de encontrar outra colisão natural.

Não há evidência de relação com o problema histórico Qt/Draft do FreeCAD
1.1.4: o caminho falho não ativou ferramenta Draft, os polls continuaram e
os logs não mostraram destruição indevida de objeto Qt nessa ocorrência.
O tema não participa da assinatura ou da resolução do suporte; os controles
nos três temas confirmaram o defeito comum.

### Correção e contrato de sincronização

A única alteração funcional adicional em produção está em
`MemberAdjustmentTaskPanel._reference_signature()`: conservar o hash e
acrescentar `plane_reference_from_link(link)` para Face ou
`linear_reference_from_link(link)` para Edge. São os mesmos helpers usados
pelo controlador, com descritores imutáveis de ponto/normal ou ponto/direção
**globais**. Não foi duplicado algoritmo geométrico nem acrescentado observer.
Isso também reconhece mudança de suporte/transformação acumulada com Placement
local constante e transições válido/inválido. Sem entradas novas, schema,
transação ou alteração persistente do membro durante preview.

O gate foi fortalecido: `wait_preview_poll()` entra no ciclo de eventos e
aguarda um sinal real do timer, concluindo por conexão enfileirada depois dos
slots síncronos. Não chama `_poll_reference()` manualmente, não aumenta prazos
para obter passe e não repete uma tentativa falha. Destruição do timer libera
o ciclo para as assertivas de fechamento. O watchdog externo de processo
continua sendo apenas um limite de falha em caso de travamento.

O critério é o estado correto após esse dispatch, comparado com uma candidata
nova avaliada independentemente do detector: volume, diferença BRep bidirecional
da Shape global exportada, branch Coin anexado e bounds contra exportação
nova. Capturas via `saveImage()` verificam pixels idênticos ao render de uma
candidata nova no mesmo viewport. A rodada visual adicional exige também
pixels diferentes quando o branch é retirado: duas capturas vazias não aprovam.
O render é solicitado explicitamente; não se usa sleep ou janela temporal
arbitrária como critério de correção.

O gate inclui Face e Edge sucessivas, deslocamentos positivos/negativos,
mudança da normal, gap, LengthLimit/PlaneCut, membro independente e filho com
fim fixo já ajustado. Repete sessões após Cancelar/Esc, com hash natural e
constante. Temas são aplicados antes de cada processo isolado. Não foi preciso
alterar ou testar troca de tema no meio da sessão para explicar esta causa,
pois o detector falhava independentemente do tema; não se declara esse teste.

O runner ganhou `--phase preview-sync`, `--output-root` e criação explícita da
pasta temporária do perfil. A saída curta evita interferência da gravação de
evidências em diretórios diagnósticos profundamente aninhados. Isso afeta
somente infraestrutura de teste, não o ambiente normal do usuário.

### Execuções exatas desta investigação

Evidências e comandos completos em `test-results/member_adjustment_preview_sync/`;
resultados nativos com caminhos curtos em `test-results/msyncruns/`.

| Grupo | Execuções | Sucessos completos | Falhas | Observação |
| --- | ---: | ---: | ---: | --- |
| Diagnóstico inicial instrumentado | 12 | 0 | 12 | 1 reprodução causal; 5 falhas do logger ao ler controle destruído; 6 OSError de gravação de evidência |
| Controle anterior com hash constante | 3 | 0 | 3 esperadas | Detector antigo recusa o requisito nos três temas |
| Corrigido, focado inicial | 6 | 6 | 0 | 2/tema, 137 checks por execução |
| Corrigido, completo | 6 | 6 | 0 | 2/tema, 524 checks por execução |
| Corrigido, visual reforçado + Face/Edge | 3 | 3 | 0 | 1/tema, 241 checks por execução |

**30 processos nativos nesta rodada:** 12 diagnósticos, 3 controles negativos
e **15/15 execuções de validação corrigida aprovadas**. São 5 passes corrigidos
por tema. Os passes corrigidos somam 4689 checks, não testes independentes.
Nenhuma falha foi apagada ou convertida em skip. As repetições da auditoria
de 22/10 não entram nesses totais.

As falhas do logger eram instrumentação lendo `gap.value()` depois de fechar
o formulário; o logger passou a consultar validade Qt. São distintas da
ocorrência original, que ocorreu com formulário vivo e timer ativo. As seis
interrupções de gravação ocorreram depois das transições de preview em pastas
diagnósticas profundas. Elas não constituem gates completos aprovados nem
explicam a falha de observação. Os logs antigos também continham avisos de
criação de diretórios temporários, inclusive nos passes; não se atribuiu
causalidade geométrica a esses avisos. A rodada final com saída curta não
apresentou esses avisos. Resultados iniciais permanecem em
`investigation-results.json`; versões e manifestos distinguem instrumentação
e produção.

Comandos de orquestração executados:

```powershell
python test-results/member_adjustment_preview_sync/investigate.py 4
python test-results/member_adjustment_preview_sync/validate.py before
python test-results/member_adjustment_preview_sync/validate.py focused
python test-results/member_adjustment_preview_sync/validate.py final
python test-results/member_adjustment_preview_sync/validate.py visual
```

O runner oficial foi chamado nas raízes isoladas com `--phase preview-sync`
ou `--phase stage1`, `--theme` para cada um dos três temas e
`--output-root <raiz>/test-results/msyncruns`. `before-results.json`,
`focused-results.json`, `final-results.json` e `visual-results.json` contêm
argv, cwd, pasta de evidência, resultado e erro de **cada** execução.
Manifestos de fontes por processo comprovam a versão executada.

Os seis gates completos preservaram as oito rejeições inválidas por processo
(**0/48 aceitações inválidas**), as verificações de transações, rollback,
Undo/Redo, eixo nominal, membros avulsos/filhos, Fixed/Associative, massa,
FCStd e fechamento da tarefa. Nenhum resíduo monitorado de branch, observer,
timer ativo ou objeto de preview. Os quinze passes corrigidos tiveram filtros
nativos vazios e zero erros de callbacks capturados.

### Testes Python, integridade e seleção

Cinco regressões em `tests/test_member_adjustment_preview.py` executam os
métodos reais de assinatura/polling com suportes globais e hash constante:
Face transladada, Face rotacionada/movimentos sucessivos, Edge, referência
associativa da ponta oposta e validade. **Antes: 5 falhas; depois: 5 passes.**
O suporte global muda enquanto o Placement local do double permanece constante,
evitando uma correção limitada à matriz local do objeto.

```powershell
python -B -m unittest tests.test_member_adjustment_preview tests.test_member_adjustment_task_panel tests.test_member_adjustment_controller tests.test_member_adjustment_reference tests.test_member_associative_adjustment
python -B -m unittest discover -s tests -p "test_*.py" -v
python scripts/check_project.py
git diff --check
```

Direcionados: **87 testes OK**, sem skips. Revisão independente: os
**17 testes de preview OK**, sem bloqueador identificado na correção ou no gate.
Como produção mudou, a suíte completa foi **reexecutada**, não reutilizada:

| Árvore | Descobertos | Aprovados | Skips | Falhas/erros |
| --- | ---: | ---: | ---: | ---: |
| Candidata corrigida isolada | 1950 | **1801** | 149 | 0 |
| Workspace, incluindo experimentos | 1954 | **1805** | 149 | 0 |

Os cinco testes adicionados explicam todo o aumento sobre a candidata anterior;
nenhum teste foi removido e nenhum teste comum mudou de resultado. Os mesmos
149 skips ambientais e os quatro testes externos StructuralPlate continuam
separados. Base publicada reutilizada apenas como comparação de resultados
da auditoria anterior. `summary.json` e logs registram os detalhes.
A ampliação final do gate manual (Face/Edge e imagem sem branch) não altera
produção nem testes descobertos pela suíte Python; foi validada pelas rodadas
nativas e por `check_project.py`, sem repetir desnecessariamente a suíte.

`check_project.py` e `git diff --check` aprovados. Nesta rodada foram alterados
somente **cinco arquivos já pertencentes aos 14 selecionados**: painel,
`tests/test_member_adjustment_preview.py`, gate manual, runner e este relatório.
Nenhum caminho novo de produção ou de staging. A candidata corrigida em
`test-results/member_adjustment_preview_sync/candidate/` mantém exclusivamente
o mesmo incremento sobre `fd96c2f`; `staging-list.txt`, `candidate-manifest.json`,
`candidate-increment.zip` e `preservation-final.json` substituem a preparação
anterior para revisão. Artefatos históricos não foram sobrescritos.

Os **134 excluídos** e todos os demais estudos/experimentos locais permanecem
preservados. A conferência compara hashes dos 584 arquivos inventariados nesta
rodada, permite somente os cinco caminhos acima e confirma que as fontes do
workspace coincidem com a candidata. O manifesto da falha original permanece
igual. Índice vazio e HEAD ainda `fd96c2f`.

### Decisão atual e limites

**GO técnico para commit local:** há causa reproduzida, correção mínima,
regressão determinística negativa/positiva, prova de atualização Coin/render,
suíte completa da candidata e gates nativos aprovados. A aprovação manual já
informada pelo usuário continua registrada. O commit não foi executado.

Não há causa indeterminada remanescente para o mecanismo reproduzido. Não se
afirma que isso prove ausência de qualquer outro defeito Qt/OCC. Permanecem
os limites paramétricos/topológicos e de desempenho documentados na Etapa 1.
Não foi feita nova sessão manual pelo auditor; os testes nativos foram
instrumentados. FreeCAD 1.1.3 não foi reexecutado nesta correção solicitada
para 1.1.4. **Release continua sem GO nesta etapa**: o GO local não certifica
matriz de release nem autoriza publicação.

Mensagem sugerida permanece a da Etapa 1, acrescentando, se desejado:
`Detecta mudanças dos suportes globais mesmo quando o hash da referência permanece igual.`
Não houve meia-esquadria automática, recorte por sólido completo, botão
Aplicar, nova referência ou alteração semântica de LengthLimit/PlaneCut.
