# Refinamento dos previews e da orientação de perfis

## Polimento complementar — estado atual

Após a validação da rodada anterior, foram feitos somente três ajustes:

- A seta aberta da cota de raio foi substituída por um triângulo agudo,
  fechado e preenchido, em pixels. Chamada a 45° e `(ri) R valor` preservados
  no renderizador técnico compartilhado.
- `flange_top_tip` e `flange_bottom_tip` agora usam respectivamente
  `(nominal_flange_tip_x, nominal_top_y)` e
  `(nominal_flange_tip_x, nominal_bottom_y)`. A mudança é funcional na definição
  compartilhada, inclusive para membro, pilar, treliça e mini-preview.
  Cada ponto se deslocou por `t/2` para a face externa correspondente.
- Centro da alma voltou à meia altura da alma no esquema. Removidos o
  deslocamento vertical artificial e a guia tracejada, preservando as curvas
  e os demais hotspots já aprovados.

IDs, textos, catálogo, contorno da seção, propriedades tabeladas e formatos
persistidos permanecem iguais. Objetos que usam essas duas pontas passam a
usar a referência externa quando recomputados; isso é o efeito funcional
solicitado, sem migração de schema ou modificação do gerador geométrico.
Botões ±90°, catálogo neutro e adornos das barras foram preservados.

Arquivos editados neste complemento:

- `freecad/SteelStructures/interactive/profile_browser_preview.py`
- `freecad/SteelStructures/interactive/section_orientation_preview.py`
- `freecad/SteelStructures/profiles/insertion.py`
- `freecad/SteelStructures/profiles/preview_geometry.py`
- `tests/test_profile_browser.py`
- `tests/test_simple_u_stage_b.py`
- `tests/test_cold_formed_simple_u.py`
- `tests/manual_profile_preview_refinement.py`
- Este relatório.

Validações deste complemento:

```powershell
python -m unittest tests.test_simple_u_stage_b tests.test_cold_formed_simple_u tests.test_profile_browser tests.test_section_orientation_preview tests.test_profile_options_browser_integration tests.test_column_task_panel tests.test_truss_task_panel
python scripts/run_simple_u_stage_b_gate.py --refinement --theme Classic
python scripts/run_simple_u_stage_b_gate.py --refinement --theme "FreeCAD Dark"
python scripts/run_simple_u_stage_b_gate.py --refinement --theme OpenDark
python scripts/check_project.py
git diff --check
```

138 testes Python passaram. FreeCAD 1.1.4: 524 verificações por tema passaram,
com logs nativos limpos. Conferidos seta fechada/preenchida, mini-preview,
hit-test dos nove pontos, membro/pilar pequeno e grande nas representações
Detailed/Simplified e treliça real com ambas as pontas distribuídas nos papéis.
Na Shape local criada, `XMax=0` e `YMax=0` (ponta superior) ou `YMin=0`
(ponta inferior), confirmando a extremidade externa sobre o eixo de inserção.
O gate também conserva as regressões de rotação ±90° e catálogo neutro U/Ue.

Uma comparação das referências antes/depois, em 3.588 perfis com geometria
suportada, encontrou somente as 250 mudanças esperadas nas 125 bitolas U
simples; todas as outras referências permaneceram iguais.

Evidências atuais:

- [Classic](../test-results/profile_preview_refinement/1792623293030222100_Classic_mjd3ixsw/result.json)
- [FreeCAD Dark](../test-results/profile_preview_refinement/1792623326797475000_FreeCAD_Dark_mqfe0jmm/result.json)
- [OpenDark](../test-results/profile_preview_refinement/1792623336980871100_OpenDark_4h2jkt2a/result.json)

Pronto para validação manual do usuário: conferir a seta no Browser, selecionar
as pontas externas e Centro da alma, e criar membro/pilar/treliça. As verificações
nativas são automatizadas com revisão de capturas; não representam aprovação
manual do usuário. Sem suíte completa, stage, commit ou push.

## Registro histórico da rodada anterior

Rodada de 21/10/2026. Pronta para validação manual do usuário; sem stage,
commit ou push. O working tree já continha a integração aprovada do U simples
e outros trabalhos. A lista abaixo identifica somente os arquivos editados
nesta rodada.

## Ajustes

- Browser U simples: raio interno com seta aberta, trecho radial a 45°,
  patamar horizontal e texto `(ri) R valor`. Valores e demais cotas preservados.
- Barras maciças: centro com diâmetro de 6 pixels; letras X/Y ancoradas às
  extremidades dos eixos com deslocamentos em pixels. Envelope de enquadramento
  proporcional também em Propriedades, evitando que os adornos comprimam os
  perfis pequenos. A solução atende redonda, chata e quadrada.
- Mini-preview U simples: representante esquemático com curvas menores e
  espessura legível. Pontas das mesas mantidas no meio da espessura; centros
  externos e cantos alinhados aos planos nominais. Hotspot Centro da alma
  separado verticalmente, com uma guia curta, fraca e tracejada até sua estação
  real no esquema. IDs e coordenadas físicas de inserção não mudaram.
- Membro e pilar: botões de rotação ±90° junto ao campo existente. Reuso dos
  ícones e da normalização já usados na treliça; o editor da treliça passa a
  compartilhar os controles para evitar duplicação.
- Catálogo aberto pelos painéis: deixa de receber a inserção do chamador.
  Seleção inicial, filtros, confirmação e cancelamento preservados. A API
  explícita de inserção do Browser permanece disponível para contextos próprios.

Nenhum catálogo, propriedade normativa, núcleo geométrico, gerador 3D,
persistência, schema ou metadado de release foi editado nesta rodada.

## Arquivos editados nesta rodada

| Arquivo | Responsabilidade |
| --- | --- |
| `freecad/SteelStructures/interactive/profile_browser_preview.py` | Cota radial e adornos das barras |
| `freecad/SteelStructures/interactive/profile_options_widget.py` | Rotação compartilhada e catálogo neutro |
| `freecad/SteelStructures/interactive/section_orientation_preview.py` | Desenho da guia discreta |
| `freecad/SteelStructures/interactive/truss_task_panel.py` | Reuso dos botões compartilhados |
| `freecad/SteelStructures/profiles/preview_geometry.py` | Esquema e hotspot do U simples |
| `tests/test_simple_u_stage_b.py` | Regressões da seta/45°/R, alinhamentos e hotspots |
| `tests/test_solid_sections_ui.py` | Centro e letras invariantes em pixels para escalas extremas |
| `tests/test_profile_options_browser_integration.py` | Neutralidade do catálogo e retenção de perfil/filtro |
| `tests/manual_profile_preview_refinement.py` | Gate automatizado nativo Qt/FreeCAD com capturas |
| `scripts/run_simple_u_stage_b_gate.py` | Opção `--refinement`, mantendo o gate anterior como padrão |
| `Documentation/U_SIMPLE_NBR_6355_PREVIEW_REFINEMENT.md` | Registro desta rodada |

## Validação executada

```powershell
python -m unittest tests.test_simple_u_stage_b tests.test_solid_sections_ui tests.test_profile_browser tests.test_section_orientation_preview tests.test_profile_options_browser_integration tests.test_column_task_panel tests.test_truss_task_panel
```

139 testes passaram.

```powershell
python -m unittest tests.test_cold_formed_simple_u tests.test_ue_stage2 tests.test_freecad_section_geometry tests.test_member_creation_types tests.test_member_axis_creation tests.test_creation_preferences tests.test_truss_assemblies
```

99 testes passaram. Os testes com stubs não substituem o gate nativo.

```powershell
python scripts/run_simple_u_stage_b_gate.py --refinement --theme Classic
python scripts/run_simple_u_stage_b_gate.py --refinement --theme "FreeCAD Dark"
python scripts/run_simple_u_stage_b_gate.py --refinement --theme OpenDark
python scripts/check_project.py
git diff --check
```

Todos passaram. FreeCAD 1.1.4 real: 424 verificações por tema, sem erros nos
logs nativos. Preferências isoladas, documentos descartáveis. Cobertura:
U simples pequeno/grande e raio atípico 9,525; barras redondas/chatas mínimas,
máximas e chata mais esbelta do catálogo em Dimensões/Propriedades;
larguras de Browser 760/1100; painéis em 340/620; nove hotspots em cinco
rotações; botões e atualização do mini-preview; criação de membro e pilar;
catálogo modal dos dois painéis com U/Ue, Cancelar/Selecionar; reuso da
treliça; preview nativo Draft e limpeza ao cancelar.

A primeira tentativa Classic identificou uma espera ausente no roteiro:
Draft remove seu preview no próximo ciclo de eventos. O roteiro passou a
processar esse ciclo antes de conferir a limpeza e fechar o documento.
A repetição passou com logs limpos; não foi necessária mudança na ferramenta.

Evidências finais (resultados, checks, manifestos de fontes, logs e 54 PNGs por tema):

- [Classic](../test-results/profile_preview_refinement/1792622061151083800_Classic_dnz29rgt/result.json)
- [FreeCAD Dark](../test-results/profile_preview_refinement/1792622089208109800_FreeCAD_Dark_gy63kzze/result.json)
- [OpenDark](../test-results/profile_preview_refinement/1792622099392887000_OpenDark_ui3fbp25/result.json)

Capturas representativas foram inspecionadas nos três temas: raio,
mini-preview, painéis estreitos, barras e catálogo Ue. Revisão técnica
independente sem bloqueios. A suíte completa e o gate amplo de persistência
da etapa anterior não foram repetidos, conforme o escopo focado desta rodada.

## Validação manual pendente

1. Nos três temas, conferir a chamada `(ri) R` no Browser do U simples e os
   eixos/centro de redondas e chatas pequenas, grandes e esbeltas.
2. Em Criar Membro e Criar Pilar, selecionar os nove pontos do mini-preview U,
   conferir a guia de Centro da alma, editar o ângulo e usar os dois botões.
3. Com inserção externa selecionada, abrir o catálogo para U e Ue: deve ficar
   neutro. Cancelar e confirmar a seleção, conferindo o painel ao retornar.
4. Criar e cancelar membros/pilares e conferir a ergonomia no tamanho habitual
   do painel de tarefas. Aprovação de funcionamento e design permanece com o usuário.
