# Auditoria técnica — Recortar / Ajustar Membro

Data: 21/10/2026. Branch `develop/0.7.0`.
HEAD inspecionado: `fd96c2fe34586d9dbc099994e2e0bd4d7e02a768`.
A referência **local** `origin/develop/0.7.0` coincide com HEAD; GitHub não
foi consultado nesta rodada. Índice vazio e nenhum rastreado modificado no
início. Auditoria de leitura, com este relatório como única alteração de fonte.
Não foram executados stage, commit, push, merge, tag ou release.

## Resultado principal

A ferramenta já oferece **limitação/prolongamento axial e corte planar real,
inclusive inclinado, em ambas as pontas, com modos fixo e associativo**.
As referências da interface são **uma Face plana ou uma Edge reta explícita**.
Uma face ou aresta de outro membro/sólido pode ser usada; selecionar seu
objeto inteiro não determina automaticamente o recorte. O sólido de referência
não é subtraído do membro.

**Meia-esquadria não está ausente da bancada:** pode ser produzida manualmente
no painel fornecendo o plano correto; o Gerador/Editor de Treliças dispõe de
resolvedores automáticos de encontros. O que falta no painel genérico é uma
operação de par que calcule o plano e ajuste os dois membros de uma vez.

**Primeira melhoria recomendada:** avaliação destacada da geometria candidata,
preview transiente e diagnóstico antes do OK, reutilizando o pipeline atual.
Isso atende os cortes já existentes e prepara seleção de membros inteiros e
meia-esquadria genérica sem duplicar o núcleo geométrico.

## Mapa de implementação

| Área | Caminho e entrada relevante |
| --- | --- |
| Comando público | `freecad/SteelStructures/commands.py:382`, `AdjustMemberCommand`; registro `SteelStructures_AdjustMember` em `:498` |
| Menu/toolbar | `freecad/SteelStructures/init_gui.py:104`: Elementos e menu Steel Structures |
| Ícone | `Resources/Icons/AdjustMember.svg`; constante em `freecad/SteelStructures/paths.py:16` |
| Interface | `interactive/member_adjustment_task_panel.py:44`, `MemberAdjustmentTaskPanel` |
| Validação/transações | `interactive/member_adjustment_controller.py:153`, `validate_proposal`; `:198`, `MemberAdjustmentController` |
| Eixo, plano, reta e gap | `member_adjustment_geometry.py:48–194` |
| LinkSub, coordenadas e ciclos | `member_adjustment_reference.py:25–170` |
| Corte planar OCC | `member_plane_cut.py:125–165`, `:270–328` |
| Propriedades/recompute/restauração | `member.py:226–412`, `:515–724`, `:793–806` |
| Avaliação destacada e filhos de treliça | `member_batch.py:44–83`, `:215–232` |
| Fitting/precedência | `fitting/freecad_adapter.py`, `fitting/precedence.py`, `trusses/fitting.py` |
| Encontros automáticos | `connections/resolver.py:142–161`, `:197–225`; `interactive/truss_topology_editor.py:755–770` |

Os caminhos abreviados acima e abaixo pertencem a `freecad/SteelStructures/`.

## Matriz das capacidades reais

**Disponível** significa existir caminho de comando/interface até a geometria;
não significa que toda combinação foi ensaiada visualmente nesta auditoria.

| Operação/capacidade | Situação real | Caminho responsável | Limitação ou semântica |
| --- | --- | --- | --- |
| Abrir sem membro selecionado | Disponível | comando + painel | Basta documento ativo; selecionar alvo depois |
| Pré-selecionar alvo | Disponível | `commands.py:413–415` | Exatamente um objeto selecionado, e ele deve ser membro estrutural; não carrega referência pré-selecionada |
| Limitar comprimento | Disponível | controller `LengthLimit`; `member.py:572–641` | Obtém estação no eixo; a extremidade resultante é perpendicular ao eixo |
| Prolongar até referência | Disponível | mesmos caminhos | Eixo/reta/plano são infinitos; estação pode ficar fora do segmento nominal, desde que reste comprimento válido |
| Recortar pelo plano perpendicular | Disponível | `PlaneCut`; `member.py:695–714` | Usa extrusão direta, sem boolean desnecessário |
| Recortar pelo plano inclinado | Disponível | `member_plane_cut.py:270–328` | Interseção OCC com sólido retentor finito; plano não pode ser paralelo ao eixo |
| Ajustar início e fim | Disponível | slots Start/End | Independentes, inclusive misturar LengthLimit e PlaneCut; painel confirma uma ponta por abertura |
| Gap positivo/negativo | Disponível | `resolve_slot`, `member.py:624` | Positivo recua, negativo prolonga; deslocamento axial, não distância normal ao plano |
| Remover ajuste | Disponível | painel `remove_adjustment`; controller `:271` | Atua em uma ponta; transação própria e fechamento do painel |
| Manter vínculo | Disponível | `AdjustmentMode=Associative` | LinkSub resolve novamente Face/Edge em recompute |
| Congelar referência | Disponível | checkbox desmarcado, `Fixed` | Guarda offset relativo à ponta nominal e normal local, sem seguir a referência externa |
| Editar gap de ajuste fixo sem referência | Disponível | `validate_existing_fixed` | Escolher Início/Fim e manter tipo; trocar tipo exige nova referência |
| Face de outro membro/sólido | Disponível | seleção explícita FaceN | Usa apenas o plano suporte; não exige que o eixo atravesse a região finita da face |
| Aresta de outro membro/sólido/Draft Line | Disponível para LengthLimit | seleção explícita EdgeN | Usa reta suporte infinita; não aceita aresta curva |
| Membro/sólido inteiro como referência | Não disponível no painel | seleção exige subelemento | Não há escolha automática de face, contato global, recorte pelo volume nem política de múltiplas interseções |
| Ponto, Vertex, coordenada ou datum abstrato | Não disponível no painel | regex LinkSub | Um Part Plane com Face plana serve por FaceN; selecionar objeto/plano abstrato sem face não serve |
| Meia-esquadria manual de uma ponta | Disponível como composição do fluxo | PlaneCut + face/plano preparado | Não existe campo de ângulo ou cálculo automático da bissetriz no painel |
| Meia-esquadria automática de par genérico | Não disponível no painel | nenhum modo de par nessa interface | Não confundir com o recurso de treliças abaixo |
| Meia-esquadria equilibrada em nó de treliça | Disponível em outra interface | `connections/resolver.py:_balanced` + editor | Duas barras terminais da alma equivalentes/coplanares; sem participante passante da alma |
| Encontro de banzos/cumeeira | Disponível em treliças | `chord_joint_plane`, `trusses/fitting.py` | Bissetor compartilhado; regras próprias para quebra e encontro terminal, não as mesmas de BalancedMiter |
| Prioridade/contato físico com outro membro | Disponível em treliças | Priority, ToChord, `trusses/fitting_geometry.py` | Resolve seção/envelope/contato de participantes conhecidos, não sólido arbitrário da seleção genérica |
| Cope, notch, saddle/ElementCut volumétrico | Não disponível neste fluxo | fora dos modos implementados | Um ou vários planos não equivalem a subtração do sólido de referência |
| Preview do ajuste neste painel | Ausente | comando declara `non-preview`; painel só valida proposta | Preview 3D da treliça existe em seu fluxo separado |
| Aplicar mantendo painel aberto | Ausente | `getStandardButtons`: OK/Cancelar | `controller.apply()` é método interno, não botão Aplicar |

## Referências e geometria: o que o resultado significa

`unpack_link_sub()` aceita exatamente um nome `FaceN` ou `EdgeN`, com índice
positivo. O alvo deve ser `Part::FeaturePython` com `StructuralMemberProxy`.
O tipo do objeto referenciado não é limitado a membros: a exigência real é
Shape/subelemento válido e superfície plana ou curva linear compatível.

- **Face em LengthLimit:** interseção do eixo nominal infinito com o plano
  suporte infinito. Mesmo uma face lateralmente afastada pode definir o limite.
  A orientação da face não se torna inclinação da extremidade nesse modo.
- **Edge em LengthLimit:** ponto do eixo de menor distância à reta suporte.
  Aceita retas reversas, sem interseção física, e estações fora da aresta finita.
  Retas paralelas/colineares são rejeitadas por não haver estação única.
- **Face em PlaneCut:** mesma estação axial, conservando a normal do plano.
  A Shape realmente recebe a extremidade inclinada. Inverter a normal da face
  não deve trocar o material retido: o lado é escolhido pelo extremo oposto.
- **Gap:** na ponta inicial soma-se ao parâmetro axial; na final subtrai-se.
  Um gap de 10 mm num corte oblíquo não promete 10 mm medidos na normal.
- **Automático:** escolhe a ponta nominal mais próxima da estação. Empate
  próximo do meio exige Início/Fim explícito. Não escolhe a face mais próxima
  de um sólido nem calcula qual membro deve ter prioridade.

O clipper extruda um precursor suficientemente longo para acomodar as alturas
do plano sobre a caixa da seção, constrói um sólido retentor finito e usa
`common()`. Dois cortes compartilham um precursor. A composição de fitting
também admite restrições adicionais da mesma ponta com estações próprias.
Seções ocas e abertas entram pelo mesmo adaptador de seção; o mecanismo não
pressupõe uma seção I nem preenche o vazio de um tubo.

## Estado paramétrico, posição, massas e persistência

Cada ponta tem seis propriedades persistentes:

| Propriedade (`Start`/`End` + sufixo) | Tipo/uso |
| --- | --- |
| `AdjustmentMode` | enum `None`, `Associative`, `Fixed` |
| `AdjustmentGeometryMode` | enum `LengthLimit`, `PlaneCut` |
| `AdjustmentReference` | `App::PropertyLinkSub`, Face/Edge explícita |
| `AdjustmentGap` | distância assinada |
| `FixedReferenceOffset` | distância assinada da referência com gap zero |
| `FixedPlaneNormal` | vetor da normal no sistema local |

Saídas somente leitura: `EffectiveStartPoint`, `EffectiveEndPoint` e
`AdjustedLength`. `StartPoint`/`EndPoint`, `Length`/`MemberLength` continuam
nominais. `AdjustedLength` é distância **axial** entre pontos efetivos, não
comprimento máximo/mínimo das bordas de uma extremidade inclinada.

A extensão da ponta ajustada deixa de determinar essa ponta; a extensão
oposta sem ajuste continua válida. Remover o ajuste reativa a extensão
correspondente, sem apagar seu valor. O ajuste não modifica seção, catálogo,
inserção ou offsets: reconstrói sua geometria física local e aplica os planos.

O Placement **não é imutável**: sua Base acompanha o início efetivo quando
esse início muda. O pipeline preserva a orientação global/rotação do usuário
e não reescreve o eixo nominal para simular o corte. Referências são obtidas
por `getSubObject()`, já em coordenadas acumuladas, evitando dupla aplicação
de Placement; normais associativas são convertidas ao sistema do membro.

Fixed não é um plano global eternamente congelado: segue o referencial do
próprio membro. Offset da ponta final é relativo ao fim nominal atual; normal
local acompanha a rotação do membro. Associative segue a referência externa.

`TotalMass` não deve ser rotulado universalmente como massa física BRep:
é massa linear de catálogo × comprimento ajustado; com corte oblíquo usa
comprimento equivalente `Shape.Volume / área geométrica da seção`, coerente
com Detailed/Simplified. Não substitui área técnica normativa pela área BRep.
A massa física por densidade pode ser obtida do volume final; a leitura de
treliças em `trusses/physical_mass.py` soma sólidos físicos. Não existe neste
painel calculador separado de densidade ou comprimento de fabricação.

O estado vive em propriedades FreeCAD, não em caches Python. `onDocumentRestored`
reestabelece propriedades/guardas/Placement; há conversão de antigas propriedades
de ajuste único para slots por ponta e normal nula legada equivale ao corte
ortogonal. Os testes simulados de restore não substituem FCStd real; scripts
nativos existentes tratam save/reopen em membros gerados e barras.

## Associatividade e encontros posteriores

O vínculo LinkSub integra o grafo de dependências FreeCAD. Em recompute,
translação/rotação e mudanças válidas da referência atualizam o limite/plano.
Não há observador próprio que decida semanticamente “esta continua sendo a
mesa externa” depois de uma alteração topológica.

Autorreferência e ciclos transitivos são rejeitados, inclusive na seleção
inicial para congelar um ajuste. Isso impede montar meia-esquadria associativa
ingênua com A referenciando a face cortada de B e B referenciando A.

**Falhas têm dois comportamentos diferentes:**

| Alvo | Referência removida/inválida ou geometria impossível |
| --- | --- |
| Membro independente | `member.py:563–570`: Shape vazia, `AdjustedLength=0`, `TotalMass=0`; eixo nominal preservado |
| Filho de treliça | `member_batch.py:215–232`: última Shape/saídas válidas preservadas e `GenerationStatus` recebe erro; a forma visível pode estar desatualizada |

No gerador, ajustes manuais válidos têm precedência sobre AutoFit por ponta.
Remoção estrutural de filho com override é protegida. Reabertura do gerador
não precisa do cache `_last_generated_result`; a validação examina estado
persistente. Dependência da própria treliça, referências pendentes de recompute
e ciclos são protegidos. Isso não transforma um corte manual em conexão
topológica automaticamente.

## Interface, confirmação e operações inválidas

1. O comando fica ativo com documento aberto. Só aproveita pré-seleção de um
   único alvo; membro + referência pré-selecionados não preenchem os dois campos.
2. Selecionar membro/referência instala observador `addSelection`; captura
   cliques do mesmo documento. Hover/preselection da vista não é mecanismo de
   captura. Não há selection gate que filtre previamente o que pode ser clicado.
3. Referência exige subelemento explícito. Clique inválido mostra mensagem;
   uma Face/Edge capturada é então validada quanto à geometria. Para trocar
   referência inválida pode ser necessário iniciar a captura novamente.
4. Há rascunhos locais por Auto/Start/End. O painel sempre inicia em Auto;
   escolher Início/Fim carrega o estado daquela ponta. **OK aplica apenas a
   ponta ativa**, não todos os rascunhos alterados ao alternar as opções.
5. Alterações dos campos revalidam matematicamente a proposta, mas não geram
   Shape candidata nem preview. A compatibilidade final das duas pontas e a
   operação OCC só são confirmadas no recompute ao aplicar.
6. OK revalida, abre uma transação, grava só o slot resolvido, recomputa,
   verifica Shape não nula, confirma e fecha. Exceção aborta a transação e
   mantém o painel com erro. Remover ajuste tem transação própria e fecha.
7. Cancelar não aplica rascunhos, remove observador e fecha. Não há preview
   ou objeto temporário de ajuste para limpar. Não restaura a seleção gráfica
   anterior, pois o painel não mantém snapshot dela.
8. Não existe botão Aplicar. Undo/Redo dependem das transações FreeCAD; os
   testes do controlador conferem abertura/commit/abort por stubs, sem provar
   toda a interação visual do painel com Undo/Redo real.

São rejeitados: alvo não estrutural, Face/Edge ausente/inválida/curva, Edge em
PlaneCut, normal nula, paralelismo, eixo nulo, referência circular e empate do
Auto. Comprimento efetivo zero/invertido ou boolean impossível falham na geração.
O painel tem gap em mm com duas casas e intervalo ±1e9; não é campo de ângulo.

## Limitações e possíveis defeitos/riscos

| Achado | Classificação/evidência | Consequência e tratamento futuro |
| --- | --- | --- |
| Confirmação de filho gerado examina apenas Shape não nula | **Risco forte por inspeção**, não reproduzido nativamente nesta rodada: controller `apply:239–269` versus `member_batch:215–232` | Falha pode preservar Shape anterior, registrar GenerationStatus de erro e ainda satisfazer o teste de sucesso do controlador. Conferir candidato/status antes de fechar/commit |
| Referências `FaceN`/`EdgeN` após alteração topológica | Limitação do contrato atual; depende também do remapeamento fornecido pelo FreeCAD/produtor da Shape | Pode invalidar ou apontar para outra entidade ainda válida; falta confirmação semântica própria |
| Sem preview nem avaliação OCC durante edição | Limitação observada na interface | OK pode estar habilitado para proposta cujo corte final falha; operações por suportes infinitos podem surpreender |
| Erros OCC convertidos em `None` | `member_plane_cut.py:257–268`, `:319–328` | Protege recompute, mas perde detalhe da causa; diagnóstico genérico de geometria vazia não explica o caso |
| Plano quase paralelo ao eixo | Risco numérico inferido, sem novo ensaio OCC | Precursor pode crescer muito antes do limiar de rejeição; exigir limites/diagnóstico e teste de condicionamento |
| Vários rascunhos, apenas slot ativo confirmado | Comportamento comprovado no painel | A alteração não ativa é descartada ao fechar; comunicar ou futuramente confirmar atomicamente ambas |
| Falha não tem política uniforme entre alvo independente e gerado | Comportamento deliberado e testado, não defeito por si | Exibir claramente Shape vazia versus última Shape preservada/obsoleta |
| Validade/volume não impõem sempre conectividade única | Inspeção do clipper e do candidato | Cortes extremos/recortes volumétricos futuros precisam de política explícita para múltiplos sólidos |

Não foi declarada uma falha OCC nova nem defeito de UI reproduzido visualmente.
As inferências acima não foram corrigidas, conforme o escopo de leitura.

## Meia-esquadria: recursos existentes e lacuna real

`BalancedMiter` no editor de ligações da treliça calcula plano comum pelas
direções incidentes, aplica PlaneCut a duas barras terminais da alma com
`geometry_key` equivalente e exige coplanaridade; casos incompatíveis são
omitidos na UI ou diagnosticados no core. Participante passante da alma impede
essa política. O gap recua cada barra no próprio eixo depois de resolver o plano.

`chord_joint_plane()` também resolve encontros de banzos. Quebra de banzo
exige seções/transformações compatíveis; encontros terminais têm regras
distintas e testes com seções diferentes. Não generalizar a restrição de
BalancedMiter a todos esses encontros, nem apresentá-los como opção deste painel.

Para tubos retangulares e perfis abertos, o clipper e o gerador de seções já
oferecem grande parte do trabalho: contorno com vazios/arcos, inserção,
orientação e corte oblíquo. Falta no fluxo genérico definir par, extremidades,
plano compartilhado, orientação das seções, assimetrias e confirmação atômica.
Um bissetor de eixos não garante acabamento desejado para perfis abertos
assimétricos, seções diferentes ou tubos girados/deslocados. Não há hoje uma
promessa de junção universal de dois membros arbitrários.

## Testes e evidências: o que de fato cobrem

Nesta auditoria foram executados somente dois grupos focados:

```powershell
python -B -m unittest tests.test_member_adjustment_geometry tests.test_member_adjustment_reference tests.test_member_plane_cut tests.test_member_adjustment_controller tests.test_member_adjustment_task_panel tests.test_member_associative_adjustment
python -B -m unittest tests.test_fitting_c5a tests.test_connections_c5b tests.test_connections_c5b_through tests.test_ridge_fitting tests.test_hollow_sections
```

**90 + 75 = 165 testes aprovados, zero skips, zero falhas.** Nenhuma suíte
completa nem novo gate GUI/OCC foi executado. `-B` evita gerar bytecode novo.

| Grupo existente | Cobertura e limite |
| --- | --- |
| `test_member_adjustment_geometry` | Planos/retas infinitos, X/Y/Z/inclinado, gap, extensões, offsets, paralelismo/tolerâncias; matemática pura |
| `test_member_adjustment_reference` | LinkSub, transformações acumuladas uma vez, normal invertida, referências inválidas e ciclos; objetos controlados |
| `test_member_plane_cut` | Clip finito, base ortonormal, bounds/margens, oblíquos, normal invertida, duas pontas/estações; FakePart, não OCC real |
| `test_member_adjustment_controller` | Seleção/validação, Auto, freeze, slot oposto preservado, transação e remoção; documento simulado |
| `test_member_adjustment_task_panel` | Labels, captura/cleanup, rascunhos, botões e ausência de mutação antes de OK; contratos de fonte/AST, não cliques Qt reais |
| `test_member_associative_adjustment` | Referência movida/rotacionada, recompute sem drift, gap, duas pontas, inválidos, massa e Detailed/Simplified; restore simulado, não arquivo FCStd |
| `test_member_placement` | Base de stubs e testes adicionais de Placement, extensões, fixed e propriedades legadas; inspecionado, não executado separadamente nesta rodada |
| Complemento de 75 testes | ToChord, BalancedMiter, passantes, encontros/cumeeira e tubos; comprova compartilhamento/limites do mecanismo, não operação genérica de par na UI |

Scripts nativos existentes, **inspecionados e não reexecutados**:

| Script | Cobertura definida |
| --- | --- |
| `tests/manual_plane_cut_diagnostic.py` | Diagnóstico FreeCAD 1.1.3 de membro selecionado; compara half-space legado e clip finito em Shapes transientes; não é gate assertivo nem modifica documento |
| `tests/manual_solid_sections_validation.py:147–180` | Controlador oficial, PlaneCut nas duas pontas, oblíquo por alteração de plano, eixo Draft, gaps, massa, LengthLimit e FCStd no restante do roteiro |
| `tests/manual_nbr16683_solid_validation.py:145–170` | Ajustes equivalentes para barras normativas; restante do roteiro salva/reabre FCStd |
| `tests/manual_freecad_connections_c5b_overrides.py` | LengthLimit/PlaneCut Fixed/Associative em filhos, Manual > AutoFit, reabertura sem cache, proteção de remoção e FCStd |
| `tests/manual_freecad_truss_associative_reopen.py` | Fixed/Associative válido/nulo/apagado, Shape preservada do filho, reabertura do gerador e FCStd |
| `tests/manual_freecad_connections_c5b.py` | Meia-esquadria/políticas em treliças, planos comuns, geometria, override, Undo/Redo e FCStd; não testa botões do painel genérico |
| `tests/manual_freecad_ridge_insertion.py`, `manual_freecad_c5b_final.py` | Encontros de banzos/cumeeira, composições, sólidos OCC e persistência |
| `tests/manual_freecad_truss_c1.py`, `manual_freecad_truss_mass.py` | Ajustes em filhos, extensões, massas físicas, mudanças nominais, persistência e Undo/Redo no fluxo de treliça |

Há artefatos locais históricos com 28 checks em
`test-results/connections-c5b-overrides/gate-result.json`, 41 em
`test-results/truss-associative-reopen/gate-result.json` e 172 em
`test-results/ridge-insertion/gate-result.json`. Eles contêm listas de checks,
mas não manifesto de fontes/versionamento nesses JSONs. Foram apenas lidos;
**não constituem uma certificação nova de execução sobre fd96c2f**.

Lacunas de cobertura: UI genérica de ponta a ponta com cliques reais,
pré-seleção/captura inválida/cancelamento, Undo/Redo de seu OK/Remover,
falha preservada em filho gerado confundida com sucesso do controlador,
troca semântica de FaceN ainda válida e planos muito próximos do paralelismo.

## Documentação: separar passado, presente e planejamento

- `README.md` e `Documentation/CHANGELOG.md` descrevem ajustes físicos e
  fitting de ligações de forma geral, não o contrato detalhado deste painel.
- `Documentation/FITTING_C5A.md` explica a separação nominal/física e a
  precedência. Sua seção “próximo escopo C5-B” é histórica: parte já foi
  implementada em C5-B e nas evoluções de encontros de banzos.
- `Documentation/CONNECTIONS_C5B.md` descreve BalancedMiter, Priority,
  composições, overrides manuais, FCStd e limitações de passantes.
- `Documentation/ROADMAP.md` ainda lista recorte/plano/meia-esquadria como
  próximos marcos, junto de recursos já presentes. Não é prova de ausência.
- ElementCut/Cope/Notch/Saddle aparecem como escopo futuro/excluído dos ajustes
  longitudinais. A busca dos modos/dispatches atuais confirma a ausência
  dessas operações neste pipeline, não apenas a menção documental.
- Preview genérico, pontos/vertices e operação de par não foram encontrados
  como caminhos implementados. São lacunas/propostas futuras; não há evidência
  suficiente para afirmar que todos foram formalmente prometidos antes.

## Prioridades propostas, sem implementação

| Prioridade | Melhoria | Reuso e dificuldade |
| --- | --- | --- |
| P0 — confiabilidade | Validar sucesso pela geometria candidata/status, especialmente no filho gerado; diagnóstico explícito de falha | Reusar `member_batch.snapshot/prepare_member`; verificar status de erro, não apenas Shape preservada. Cobertura focada e sem novo formato persistente |
| P1 — primeira melhoria de produto | **Preview fiel e transiente antes do OK**, destacando ponta/plano, resultado e erro | Mesmo snapshot + `StructuralMemberProxy.execute` + clipper. Preservar outra ponta/overrides; atualizar com debounce, sem alterar documento, transação ou propriedades até confirmar |
| P2 | Selecionar membro inteiro com política explícita de contato/plano e desambiguação | Reusar suporte físico `assemblies/attachment.py:support`, `trusses/fitting_geometry.py:member_contact_reference/chord_envelope_reference`; levar em conta inserção, offsets, rotação, vazios e componentes |
| P3 | Meia-esquadria genérica de dois membros, começando por casos coplanares definidos | Reusar bissetores e PlaneCut; validar ambos os candidatos antes de uma transação única; especificar pontas, gap, seções equivalentes/diferentes e tubos/perfis abertos |
| P4 | Associatividade semântica e diagnóstico de referência alterada | Manter LinkSub existente onde suficiente; planejar identidades/fallback explícito e associação do encontro sem links mútuos. Mudança persistente exige arquitetura e testes de restauração |
| P5 | Sólido arbitrário inteiro como ferramenta de recorte volumétrico | Novo contrato de ElementCut: cortes múltiplos, tangências, vazios, trechos desconectados, política de retenção e massa/comprimento; não disfarçar como simples LengthLimit |

A associatividade atual deve ser **preservada desde P0/P1**; P4 trata sua
ampliação topológica e encontros novos, não posterga a correção do que já existe.
Em P2, um sólido genérico pode começar pela escolha explícita de uma de suas
faces planas. Isso amplia ergonomia sem prometer boolean arbitrário. Não usar
uma face da bounding box como substituição silenciosa da geometria real.

Pontos/vertices poderiam ampliar LengthLimit por projeção axial, mas exigem
definir se é projeção, coincidência ou menor distância. Essa convenção não deve
ser inferida de um clique nem deve alterar a semântica atual das arestas.

Para meia-esquadria associativa de par, dois vínculos cruzados a faces cortadas
criam ciclos. Um encontro controlado por entradas nominais independentes ou
um controlador de conjunto é mais seguro; isso exige estudo arquitetural antes
de introduzir objetos persistentes. A infraestrutura de treliça demonstra um
modelo reutilizável, não uma dependência obrigatória para membros avulsos.

**Justificativa da primeira escolha:** o corte inclinado e sua persistência já
existem. Preview com avaliação real reduz a principal incerteza do usuário
agora, antecipa inválidos que hoje só aparecem no OK e oferece uma base única
para futuras referências e pares. É menor risco que iniciar por boolean
genérico e maior reaproveitamento que criar outro sistema de recortes.

## Preservação do workspace

Nenhum código/interface foi modificado. Nenhum documento de usuário foi aberto
ou salvo e nenhum gate que cria documentos foi executado. Os arquivos locais
de Gussets, StructuralPlate, estudos, scripts e testes experimentais foram
somente preservados. A conferência final compara hashes dos 574 arquivos
existentes inventariados no início; o único arquivo novo esperado é este
relatório. A suíte completa não foi executada.
