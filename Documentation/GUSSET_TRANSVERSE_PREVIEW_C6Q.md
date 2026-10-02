# C6-Q — prévia transversal da Gusset

Implementação local para validação visual em `develop/0.6.0`.

## Arquitetura

- `trusses/gusset_attachment.py::attachment_slot_geometry` já produz superfícies,
  materiais transversais e slots. `component_section_material` usa
  `_section_at_insertion`, `SectionGeometry2D` e `assembly_frame`, incluindo
  inserção, reflexão, rotação, translação dos componentes e contornos internos.
- `preliminary_gusset_outlines` aceita o coletor opcional `transverse_previews`.
  Ele é preenchido depois de `apply_approved_family`, usando os materiais já
  calculados, o contorno final e o `GussetAttachmentPlane` retornado por
  `resolve_gusset_attachment`. O coletor é limpo a cada chamada.
- `trusses/gusset_presentation.py` contém objetos imutáveis de apresentação e
  ajuste uniforme da escala. Não resolve posições, contato, slots ou contornos.
  A espessura ocupa exatamente `plate_low` até `plate_high`; a extensão na outra
  direção é a projeção ortogonal do contorno final no eixo transversal do banzo.
- `TrussController.preview` inclui esses dados no modelo descartável. O editor
  consome somente o nó selecionado, com os rótulos existentes de
  `_transverse_placement_regions` e `_resolved_transverse_key`.
- `interactive/gusset_section_preview.py` pinta os contornos com Qt, sem objetos
  FreeCAD, observadores de documento, timers, dependências novas ou callbacks
  externos. Os widgets pertencem à árvore Qt do diálogo.

## Interface e alcance

A área "Vista transversal" ocupa a coluna direita de "Ligação do nó". Os
controles ficam na coluna esquerda; "Região da chapa" e "Posição" ficam abaixo
da vista, próximos ao resultado que modificam. O esquema da treliça mantém a
largura inteira do editor. A legenda textual foi removida.

O perfil recebe preenchimento azul suave e contorno de alto contraste; a chapa
mantém hachura laranja. Os vazios permanecem sem preenchimento. O texto e as
cores se adaptam ao fundo claro/escuro da paleta Qt. A escala preserva
proporções, inclusive a espessura.

A seleção continua nos controles existentes. Selecionar um nó ou redimensionar
a vista não chama o resolvedor. Alterações de configuração usam o fluxo existente
de atualização do candidato; a apresentação reaproveita essa mesma passagem.

Não há regras específicas por família no desenho. Os testes cobrem U, Ue, W,
DoubleAngle, DoubleChannel com bocas para dentro e para fora, SpacedPair,
SHS e RHS, incluindo vazios, inserções, rotação e referência global inclinada.

Seções visualmente equivalentes, como as duas projeções da cumeeira validada,
aparecem numa única vista. Se houver geometrias realmente distintas, um seletor
discreto permite alternar entre elas dentro da mesma área, sem rolagem. A
comparação usa apenas os dados de apresentação, com tolerância de 0,0001 mm;
o resolvedor e seus participantes físicos continuam intactos.

## Limites deliberados

- Mostra a seção nominal física usada pelo resolvedor, antes dos recortes de
  fitting. A chapa é uma **projeção transversal**, não um corte longitudinalmente
  localizado do sólido final. O canvas não possui tooltip; os diagnósticos
  funcionais permanecem abaixo do esquema da treliça.
- Sobreposição em projeção não é um diagnóstico novo de interferência. Os
  diagnósticos existentes continuam no rodapé do nó selecionado, sem cópias na
  nova área e sem avisos de outros nós.
- Ausência de banzo, contorno inválido, plano nominal de fallback ou material
  insuficiente produzem indisponibilidade. A nova área nunca reutiliza o último
  contorno válido do esquema para inventar uma posição física atual.
- Não altera F04/F08, bandas C6-L, intents, fitting,
  StableKeys, schema, persistência ou lifecycle das chapas.

## Correção funcional após validação manual

O modo automático passa a usar `outline_band` do candidato resolvido, exatamente
como a seleção manual desse candidato. A condição antiga em `_chord_support_lines`
usava `contact_band` quando a intenção não continha uma chave explícita. Isso
alterava o contorno **físico**, inclusive fora da família W. Foi removida essa
exceção; a UI volta a identificar a região e a posição efetivamente resolvidas.
As bandas C6-L e os contornos manuais permanecem os mesmos.

A comparação antes/depois em 18 configurações preservou os 102 contornos
manuais examinados. Mudaram os automáticos de W/I a 0°/90°, U/Ue a 0° e
DoubleAngle, DoubleChannel para dentro/fora e SpacedPair a 90° (chapa de 8 mm
na matriz). Nos W/I a 90° também muda a escolha automática, pois o recesso
agora está disponível. Nos dois nós DuoPitch inclinados da regressão C6-J,
a área automática passa a 39.829,70381 e 30.413,73813 mm², respectivamente,
iguais às escolhas manuais; os limites dos membros e as margens continuam
validados. As 41 chapas das referências aprovadas mantiveram seus contornos,
incluindo F04 com truncamento condicional de 40% e F08.

O acesso ao recesso considera a direção dos participantes em relação ao banzo,
sem exigir que o vazio contenha o eixo nominal (ocupado pela alma em W/I girados).
Os slots existentes do W são reutilizados. Quando faces inclinadas não fornecem
um slot planar, o I usa a célula livre mais profunda que comporta a espessura,
derivada dos mesmos polígonos transformados, incluindo raios e inclinações.
As três posições são filtradas pela largura, acesso e contato da espessura inteira.
As janelas novas usam a fronteira real da faixa da chapa, inclusive entre estações
do contorno inclinado; não existe cálculo geométrico novo na interface.

Nos casos de teste com chapa de 8 mm, W 150 × 13,0 a 90° oferece recesso de
138,2 mm; I 3" × 8,48 a 90° usa 46,56925 mm na garganta profunda. Chapas mais
espessas no I podem usar uma célula mais próxima da abertura, limitada pelas
faces inclinadas. A 0°, as mesas bloqueiam o acesso dos participantes aos recessos
laterais; permanecem as posições existentes apoiadas na face da mesa. A presença
de um slot não elimina os diagnósticos de afastamento ou interferência dos outros
participantes: eles continuam no rodapé do nó.

O tooltip excessivo era definido por `GussetSectionCanvas.setToolTip`. A definição
foi removida, preservando os tooltips dos controles e os diagnósticos.

## Verificações executadas

```powershell
python -m unittest tests.test_gusset_w_c6q tests.test_gusset_slots_c6g tests.test_gusset_c6j tests.test_gusset_c6l tests.test_gusset_ui_c6m tests.test_gusset_c6p tests.test_gusset_families_round1 tests.test_gusset_tip_round2 tests.test_gusset_presentation_c6q tests.test_gusset_contact_c6h tests.test_gusset_attachment_c6e tests.test_gusset_c6i
```

115 testes passaram. A matriz automática/manual cobre 54 combinações de perfil,
orientação e espessura, além das famílias de ligação de referência. A comparação
física captura os vértices globais e o vetor de extrusão enviados pelo adaptador
de produção a Part; não executa OCC nem substitui a validação do sólido no FreeCAD.
Para os 13 testes Qt, foi usado o Python local que já contém
PySide6, em modo `offscreen`, sem iniciar o FreeCAD. O teste bloqueia os imports
`FreeCAD`, `FreeCADGui` e `Part`:

```powershell
$env:QT_QPA_FONTDIR = 'C:\Windows\Fonts'
& 'C:\Users\marco\Desktop\FREECAD\FreeCAD_1.1.3-Windows-x86_64-py311\bin\python.exe' -m unittest tests.test_gusset_preview_qt_c6q
```

Inclui pintura em três paletas simuladas (clara, cinza claro e escura), vazios sem preenchimento,
layout com esquema em largura inteira, seletores junto à vista, cumeeira
compacta, sinais reais dos controles, seleção sem recomputação, atualização
física, erros e destruição repetida do editor com eventos pendentes. O backend offscreen emite apenas sua
limitação de `propagateSizeHints` ao mostrar o diálogo de teste. Esses testes
não substituem a avaliação visual no FreeCAD e nos seus temas nativos.

`python scripts/check_project.py` passou. `git diff --check` terminou com código
0, sem erros de whitespace; o Git emitiu somente avisos de conversão LF/CRLF
para arquivos da árvore de trabalho já modificada.

## Roteiro manual

1. Abrir o Editor de Topologia com uma Gusset em banzo U/Ue. Selecionar o nó,
   alternar região e posição e variar a espessura. Comparar com a chapa 3D.
2. Repetir com DoubleAngle, DoubleChannel para dentro/fora e SpacedPair.
   Conferir componentes individuais, orientações e espaçamentos. Alterar a
   configuração física no painel e reabrir o editor.
3. Conferir SHS/RHS: vazio interno visível e somente as posições existentes
   nos controles. Conferir inserção e rotação do perfil.
4. Selecionar a cumeeira e nós com vários banzos. Conferir uma vista quando as
   seções forem equivalentes e o seletor compacto quando forem distintas.
   Conferir os diagnósticos do nó e alternar entre nós com e sem Gusset.
5. Introduzir uma espessura inválida, corrigir e fechar/reabrir o editor várias
   vezes. Verificar limpeza da vista e ausência de erros de widgets eliminados.
6. Repetir a inspeção em FreeCAD Classic, Dark e Light, redimensionando a janela.
   Confirmar legibilidade, controles acessíveis e esquema sem redução indevida.
7. Comparar Automática com a região/posição indicada na legenda, primeiro em W/I
   a 0°/90° e depois em U/Ue e compostos: a prévia e a chapa 3D devem coincidir.
8. Com W/I a 90° e chapa de 8 mm, alternar as três posições internas. No I,
   conferir as faces inclinadas e repetir com outra espessura. A 0°, distinguir
   apoio na mesa de acesso ao recesso lateral. Conferir também banzo superior.
9. Passar o mouse sobre o desenho: não deve surgir o tooltip grande. Os avisos
   do nó abaixo da treliça e os tooltips dos controles devem continuar presentes.

Parar para aprovação visual do usuário. Sem suíte completa, staging, commit,
push ou início da C7.
