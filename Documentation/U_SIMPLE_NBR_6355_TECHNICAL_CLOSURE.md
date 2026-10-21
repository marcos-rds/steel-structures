# Fechamento técnico — U Dobrado Simples — ABNT NBR 6355:2012

Data: 21/10/2026. Steel Structures 0.7.0, branch `develop/0.7.0`.
Base de todo o incremento: `651c0bfd539b647839f4c5fb15e7d79dab443835`.

**Resultado: GO técnico para commit local seletivo.** O usuário declarou
aprovação manual integral da implementação e dos refinamentos finais. A
auditoria abrange a diferença acumulada desde a base, incluindo catálogo,
geometria, integração e polimento. Não foi implementada funcionalidade nova.

No início da auditoria, HEAD e a referência local `origin/develop/0.7.0`
apontavam para a base acima e o índice estava vazio. Não houve atualização
remota, push, tag, release, incremento de versão ou alteração de changelog.
Após concluir a auditoria e revisar o conjunto de 34 arquivos, o usuário
autorizou explicitamente o stage seletivo e a criação do commit local,
sem push. Este relatório integra esse conjunto aprovado.

## Escopo e contratos conferidos

- 125 bitolas A.2, em 14 pares `bw × bf`, catálogo independente
  `abnt-nbr-6355-2012-a2`, série `u-simple-nbr-6355`, variante
  `cold_formed_channel / simple_u`. As identidades anteriores permanecem.
- Snapshot preserva as 2.125 células numéricas autorizadas, metadados,
  fingerprints e unidades. O registro incompleto `U300x100x2,65` existente
  somente no PDF não foi inventado nem incorporado.
- Builder próprio: três retas e duas dobras na linha média; Detailed com
  quatro arcos físicos e 12 segmentos; Simplified com oito retas, preservando
  origem, envelope e referências. `ri` é parâmetro independente de `t`;
  `rm=ri+t/2`, `re=ri+t`. Catálogo conserva a regra normativa e `ri=9,525 mm`.
- Nove inserções compartilhadas. Pontas superior/inferior nas extremidades
  externas das mesas, não no meio da espessura. Centro da alma à meia altura
  e meia espessura, sem deslocamento visual artificial ou guia.
- Browser com quatro cotas, precisão de raio e `It`, seta técnica aguda,
  fechada e preenchida, chamada a 45° e `(ri) R valor`. Mini-preview deriva
  da definição compartilhada, com hotspots selecionáveis após rotação.
- Membro/Pilar e papéis da treliça conservam controles existentes; botões
  ±90° compartilhados. Catálogo aberto pelos painéis permanece neutro sem
  herdar a inserção, preservando seleção, filtros, confirmação/cancelamento.
- U simples e U duplo inward/outward usam os consumidores existentes.
  Edição, cópia, sessões, Apply/OK/Cancel, Undo/Redo, eixos Draft vinculados,
  recompute e restauração FCStd conferidos nos gates nativos.
- Barra redonda/chata, incluindo tamanhos mínimos, máximos e chata esbelta:
  centro em pixels e eixos/letras legíveis. Ue, U laminado, W/HP/L e tubos
  mantidos como controles de regressão. Não houve mudança de schema.

## Propriedades normativas, geometria e massa

Área, massa linear, `xg`, inércias, módulos, raios de giração, `x0`, `It`,
`Cw` e `r0` continuam tabelados, com origem normativa, sem override pela BRep.
O centroide físico usado no CAD não substitui o centroide tabelado.

A divergência documentada da expressão impressa de área permanece explícita:
na primeira bitola são **115 mm² tabelados**, **115,265840131754 mm² físicos**
com duas dobras e **111,87336 mm²** pela expressão impressa com uma parcela
`u1`. Há evidência de aparente inconsistência na fonte, sem confirmação de
errata oficial. Nenhum valor normativo foi ajustado para coincidir com a forma.

`TotalMass` dos membros conserva o contrato nominal: massa linear publicada
vezes comprimento, ou comprimento equivalente quando há cortes. A massa
física é derivada do volume atual e da densidade. Treliças somam seus sólidos
e componentes reais, inclusive U duplo, sem contar previews ou duplicar o
membro lógico. Detailed/Simplified podem ter volumes/massas físicas diferentes.

## Compatibilidade da alteração das pontas

A base publicada `651c0bf` ainda não continha `simple_u`. O risco específico
é para documentos **locais da implementação prévia** que já usavam essas
pontas. IDs, labels, serialização, eixo e Placement não são migrados.

Ao recomputar com a definição final, o contorno local muda de posição:

| Inserção antiga | Variação da posição da seção no plano local |
| --- | --- |
| Ponta superior da mesa | `ΔY = −t/2` |
| Ponta inferior da mesa | `ΔY = +t/2` |

A variação vai de **0,6 a 4 mm** nas bitolas disponíveis. A orientação do
membro e transformações de componentes transportam essa variação para o
espaço global. As outras sete referências e as famílias anteriores não mudam.

Foi criado um FCStd sintético descartável com a antiga semântica das pontas:
54 FeaturePython, três bitolas, nove referências, dois modos, eixo inclinado e
roll 37°. Após reabrir com a semântica atual e forçar recompute, **12 objetos
nas pontas deslocaram exatamente o esperado e 42 permaneceram imóveis**;
matrizes Placement, volumes, massa nominal, labels e validade foram preservados.
Evidência: `test-results/simple_u_closure/old-tip-compatibility.json`.

O deslocamento pode produzir consequências em cortes inclinados e contatos,
ou em vínculos/referências a faces/arestas. Por isso não se declara neutralidade
geométrica universal para documentos locais antigos que usavam essas pontas.
O probe não cobre todas as combinações de cortes e vínculos. **Nenhuma
migração automática ou alteração em documentos particulares foi realizada.**

## Suítes Python completas e comparação com a base

Python do sistema, executado em processos separados e diretórios próprios:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Na base e na candidata foi acrescentado `-v` para identificar os skips.

| Árvore | Executados | Aprovados | Skips | Falhas/erros |
| --- | ---: | ---: | ---: | ---: |
| Base exata `651c0bf` | 1.901 | 1.752 | 149 | 0 |
| Candidata seletiva | 1.923 | 1.774 | 149 | 0 |
| Workspace completo | 1.927 | 1.778 | 149 | 0 |

O incremento acrescenta 22 testes descobertos em relação à base. Os quatro
testes extras do workspace pertencem ao diagnóstico local de ciclo Qt de
chapas (`test_plate_qt_lifecycle_probe.py`) e ficaram fora da candidata.
Não houve falha introduzida nem falha histórica nesta execução.

Os mesmos 149 skips de base/candidata são restrições do Python do sistema:
30 exigem loop FreeCAD GUI/Qt; 26 PySide6 indisponível; 15 Python nativo
FreeCAD/Draft; 47 FreeCAD GUI/Qt; 8 FreeCAD Units/PySide6; 15 units/PySide6;
8 PySide6. São skips, não aprovações. Os gates reais abaixo complementam
os cenários do incremento, sem alegar executar cada teste omitido da suíte.

Logs e resumo: `test-results/simple_u_closure/{workspace,candidate,base}-unittest.log`
e `suite-summary.json`. A revisão independente executou adicionalmente 44
testes de U simples, composições e massa física, todos aprovados.

## Gates nativos finais — FreeCAD 1.1.4

```powershell
python scripts/run_simple_u_stage_b_gate.py --theme Classic
python scripts/run_simple_u_stage_b_gate.py --theme "FreeCAD Dark"
python scripts/run_simple_u_stage_b_gate.py --theme OpenDark
python scripts/run_simple_u_stage_b_gate.py --refinement --theme Classic
python scripts/run_simple_u_stage_b_gate.py --refinement --theme "FreeCAD Dark"
python scripts/run_simple_u_stage_b_gate.py --refinement --theme OpenDark
```

| Árvore/tema | Gate integração | Gate refinamentos |
| --- | ---: | ---: |
| Workspace / Classic | 540 | 524 |
| Workspace / FreeCAD Dark | 540 | 524 |
| Workspace / OpenDark | 540 | 524 |
| Candidata / Classic | 469 | — |
| Candidata / OpenDark | — | 524 |

Todos passaram. Cada gate de integração criou/restaurou 61 objetos de controle,
incluindo oito controles de famílias anteriores, e verificou treliças e cópias.
O workspace abriu adicionalmente uma cópia descartável do FCStd particular
`tests/copiatreliça.FCStd`: 70 membros anteriores válidos. O original não foi
salvo. Esse arquivo não rastreado **não integra a candidata nem o commit**;
as 71 verificações correspondentes estão indisponíveis na candidata, explicando
540 versus 469. As restaurações autocontidas geradas pelo gate permanecem.

Núcleo Part/OCC, executado também explicitamente:

```powershell
& '<FreeCAD-1.1.4>/bin/python.exe' tests/freecad_simple_u_geometry_validation.py --output test-results/simple_u_closure/kernel
```

**250 faces e 250 sólidos válidos**, 540 placements e seis Shapes FCStd
restauradas; raio OCC medido `9,525000000000007 mm`. Erros máximos:
área `8,19e−12 mm²`, volume `5,83e−9 mm³`.

Os manifests dos oito gates gráficos correspondem aos fontes de cada árvore;
os fontes da candidata e workspace são equivalentes, desconsiderando somente
LF/CRLF em arquivos anteriores. Logs stderr/FreeCAD foram varridos pelo filtro
dos runners e por filtro adicional de Traceback, C++/Qt deletado, Access
violation, Fatal Python, Unhandled Base::Exception, `0xC0000005`, `0xC0000374`,
heap corruption, segmentation fault, ASSERT failure e destruição de QThread
em execução. **Nenhuma ocorrência**. `native-summary.json` lista diretórios,
quantidades, capturas e filtro. As notas fixas de “human approval pending” dos
gates são textos genéricos anteriores; a aprovação manual foi declarada pelo
usuário nesta etapa e está registrada no início deste relatório.

## Candidata isolada e reprodução

`test-results/simple_u_closure/candidate/` foi extraída de `git archive 651c0bf`
e recebeu somente a allowlist do incremento. A base separada está em `base/`.
Nenhum arquivo experimental foi copiado para satisfazer os testes. A suíte,
o verificador de projeto, a reprodução e dois gates gráficos passaram nessa
árvore sem o restante dos não rastreados do workspace.

```powershell
python scripts/check_project.py
python scripts/generate_nbr6355_simple_u_catalog.py --check
git diff --check
```

Verificador e reprodução passaram tanto no workspace como na candidata.
`git diff --check` passou. O snapshot incluído contém todos os dados para
regenerar o catálogo sem XLSX/PDF ou caminhos pessoais. `--xlsx` é opcional
e exige a fonte original com hash registrado. Instalação FreeCAD/OpenDark
usadas pelos gates podem ser indicadas com `--install` e `--opendark`.

Única correção adicional de fechamento: duas regras `text eol=lf` em
`.gitattributes` para catálogo e snapshot A.2. Com `core.autocrlf=true`, os
filtros reais do Git converteram os arquivos para CRLF sem essas regras,
quebrando a reprodução byte a byte; com elas, ambos são idênticos ao gerador.
Não mudou nenhum dado. Prova em `checkout-proof.json`, sem stage no repositório
principal e sem adição de testes experimentais à suíte permanente.

## Conjunto seletivo para commit

**34 arquivos: 19 modificados e 15 adicionados.**

Modificados:

```text
.gitattributes
freecad/SteelStructures/interactive/profile_browser.py
freecad/SteelStructures/interactive/profile_browser_preview.py
freecad/SteelStructures/interactive/profile_options_widget.py
freecad/SteelStructures/interactive/truss_task_panel.py
freecad/SteelStructures/profile_catalog.py
freecad/SteelStructures/profiles/__init__.py
freecad/SteelStructures/profiles/geometry.py
freecad/SteelStructures/profiles/insertion.py
freecad/SteelStructures/profiles/presentation.py
freecad/SteelStructures/profiles/preview_geometry.py
freecad/SteelStructures/profiles/validation.py
scripts/check_project.py
tests/test_profile_browser.py
tests/test_profile_catalog_stage2b.py
tests/test_profile_catalog_v2.py
tests/test_profile_options_browser_integration.py
tests/test_solid_sections_ui.py
tests/test_ue_stage2.py
```

Adicionados:

```text
Documentation/U_SIMPLE_NBR_6355_IMPLEMENTATION_INVESTIGATION.md
Documentation/U_SIMPLE_NBR_6355_STAGE_A.md
Documentation/U_SIMPLE_NBR_6355_STAGE_B.md
Documentation/U_SIMPLE_NBR_6355_PREVIEW_REFINEMENT.md
Documentation/U_SIMPLE_NBR_6355_TECHNICAL_CLOSURE.md
freecad/SteelStructures/catalog_sources/abnt_nbr_6355_2012_a2_extracted.json
freecad/SteelStructures/catalogs/abnt_nbr_6355_2012_a2.json
freecad/SteelStructures/profiles/u_section.py
scripts/generate_nbr6355_simple_u_catalog.py
scripts/run_simple_u_stage_b_gate.py
tests/freecad_simple_u_geometry_validation.py
tests/manual_simple_u_stage_b_validation.py
tests/manual_profile_preview_refinement.py
tests/test_cold_formed_simple_u.py
tests/test_simple_u_stage_b.py
```

O arquivo `interactive/section_orientation_preview.py` terminou igual à base
depois da retirada da guia e não precisa integrar o commit. Os relatórios
anteriores são históricos; descrições intermediárias de elegibilidade, pontas,
seta ou aprovação pendente são superadas por este fechamento.

Ficam fora: demais relatórios de chapas/treliças, estudos de gussets,
diagnósticos e probes locais, FCStd particulares, ambientes, logs, capturas,
arquivos temporários e árvores sob `test-results/`. Versão/metadados de release
e CHANGELOG não são parte deste commit.

Manifest com SHA-256 e exclusões: `test-results/simple_u_closure/candidate-manifest.json`.
Mensagem proposta: `feat(profiles): integrate NBR 6355 simple U sections`.
