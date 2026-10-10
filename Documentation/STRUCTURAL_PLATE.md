# Criar Chapa Estrutural — guia do incremento 0.7.0

Este documento descreve o comando unificado validado no desenvolvimento local
de `develop/0.7.0`. Não representa uma publicação da versão. O comando público
é `SteelStructures_CreatePlate`, **Criar Chapa Estrutural**, disponível no menu
e na barra de elementos da Steel Structures.

## Formas e planos

- **Polígono**: vértices ordenados e fechamento explícito do contorno.
- **Retângulo**: dois cantos opostos, com aquisição nativa Draft.
- **Retângulo orientado 3P**: opção avançada; primeiro ponto, direção e largura.

O seletor **Plano de criação** oferece **Plano de trabalho** como padrão,
**Face do modelo** e, para Polígono, **Automático — pelos pontos 3D**.
Uma face planar explicitamente pré-selecionada ativa Face do modelo ao abrir.
Sem referência capturada, escolher essa opção solicita uma face. A identificação
`Objeto — FaceN` confirma a captura; **Alterar face** permite substituí-la.
Esc durante a escolha retorna ao estado anterior. A face orienta o plano,
sem criar vínculo associativo ou `SourceObject`.

Com pontos confirmados, a mudança de forma/plano exige descarte explícito.
**Limpar pontos** remove todos os pontos e permite recomeçar na mesma ferramenta;
não mantém o último vértice como a operação Wipe original do Draft. No Retângulo
2P, a ação aparece quando há primeiro canto confirmado. Não há comando público
separado nem botão permanente redundante de reinício.

## Entrada de pontos

Polígono e Retângulo comuns preservam os campos, snaps e restrições Draft-native.
Em Face do modelo, o Working Plane temporário acompanha o frame capturado.
O Working Plane anterior é restaurado ao trocar de aquisição ou encerrar.

No Automático, P1 é um ponto 3D real; P2 define a primeira direção. Pontos
colineares adicionais não definem plano. O primeiro ponto não colinear determina
o frame; os pontos seguintes precisam ser coplanares. O plano nasce exclusivamente
dos pontos confirmados, sem inferência por câmera, hover ou Working Plane.

Antes do plano, snaps e geometria identificável fornecem candidatos XYZ reais.
No espaço vazio falta profundidade: os campos aguardam referência 3D ou XYZ
digitado. Depois do plano, o raio da vista pode intersectá-lo no espaço vazio.
Raios paralelos/interseções inválidas não produzem candidatos. Snaps fora do plano
são rejeitados, sem projeção silenciosa. O preview não altera geometria permanente.

**Relativo** controla a origem: usa o último ponto confirmado, quando existe.
**Global** controla os eixos; permanece ativo e bloqueado antes de definir o plano.
Depois, desmarcá-lo utiliza o frame local. Os rótulos mostram X/Y/Z, Global ΔX/ΔY/ΔZ,
Local X/Y/Z ou Local ΔX/ΔY/ΔZ. Local Z é informativo, sem deslocamento normal ao
plano. As conversões preservam a coordenada mundial do candidato.

O Automático usa campos Qt próprios com unidades/precisão de apresentação do
FreeCAD e métricas dos campos nativos. Não reutiliza o TaskPanel nem o motor do
Draft. A apresentação não arredonda o candidato interno e não substitui texto
durante edição. É possível digitar negativos e unidades; texto incompleto impede
confirmação. Enter confirma o ponto válido, Esc cancela. Ao sair da edição, o
mouse volta a apresentar candidatos.

As ações do Polígono ocupam a mesma grade nos dois mecanismos:

| | |
|---|---|
| Adicionar ponto | Desfazer ponto |
| Fechar contorno | Limpar pontos |

Desfazer remove o último confirmado. Fechar valida o contorno. Os estados dos
botões acompanham a disponibilidade real. A orientação curta no rodapé indica
primeiro ponto, direção, definição do plano, seleção de face ou fechamento.
As propriedades ficam em uma seção recolhível do mesmo painel.

## Atalhos e restrições

Os atalhos acompanham as preferências Draft. No perfil validado nas versões
1.1.4/1.1.3: **V** adicionar ponto, **/** desfazer, **O** fechar, **W** limpar,
**R** relativo, **G** global e **N** continuar criando, quando disponível.
Adicionar escolhe P ou V livres nas preferências; a indicação só aparece quando
há tecla disponível. N e as ações de polígono não são oferecidos em mecanismos
que não os implementam.

Os atalhos pertencem à sessão e são removidos no encerramento. Durante edição
explícita, o teclado pertence ao campo. O foco programático que o Draft dá aos
campos durante o movimento não equivale a edição manual. Não há filtro global.
Restrições nativas X/Y/Z permanecem nos modos Draft que as suportam. O Automático
não oferece um solver de restrições Draft antes de existir um plano; permite XYZ
numérico e, depois, entrada local no plano. Não exibe atalhos fictícios de eixo.

## Propriedades e origem

`Thickness` é sempre positiva. `Offset` é a posição assinada da face de referência
em Z local. Normal: intervalo `[Offset, Offset + Thickness]`; com
`ReverseExtrusion`: `[Offset - Thickness, Offset]`. Não se invertem vértices,
espessura ou eixos do Placement. A propriedade pode ser alterada pela Vista de
propriedades; arquivos anteriores recebem False sem migração destrutiva.

O contorno local permanece em `ContourData`, orientado por `Placement`.
`GrossArea` mede a área bruta; `EnvelopeVolume` é área × espessura. A inversão
não altera essas medidas. `GenerationStatus` informa o resultado da regeneração.

Um Draft Rectangle ou Wire fechado planar pré-selecionado pode fornecer o
contorno. **Manter vínculo com origem** atualiza a chapa com a fonte e seus
contêineres. Desativado, a chapa guarda um snapshot independente e não mantém
`SourceObject`. Pontos interativos também produzem contornos independentes.
Fonte associativa inválida mantém o último sólido válido e informa erro.

Não há Sketch/Face como contorno, furos, material, dimensionamento resistente,
ligações ou Gussets nesta ferramenta. Uma face selecionada define apenas o plano.

## Estabilidade e verificação

O Retângulo usa um tracker local com cinco vetores; o Draft instalado não é
modificado. A investigação histórica de `0xc0000374` e o episódio Qt de campo
destruído permanecem riscos residuais sem causa completa demonstrada.
Consulte o [fechamento técnico](STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md),
o [diagnóstico de heap](STRUCTURAL_PLATE_0_7_0_HEAP_DIAGNOSTIC.md) e a
[verificação do tracker](STRUCTURAL_PLATE_0_7_0_TRACKER_STABILITY.md).

Roteiro curto: criar Polígono e Retângulo no WP; selecionar/alterar face; criar
Automático inclinado com snap e XYZ; alternar R/G após P3; desfazer/limpar/fechar;
inverter extrusão e variar Offset; salvar/reabrir; cancelar e abrir outra
ferramenta. Conferir restauração do WP e ausência de preview residual.
