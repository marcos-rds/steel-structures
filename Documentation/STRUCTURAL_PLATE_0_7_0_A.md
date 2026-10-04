# Chapa Estrutural — núcleo 0.7.0-A

`StructuralPlate` armazena um contorno poligonal no plano XY local. O último
segmento liga implicitamente o último vértice ao primeiro. `Placement` define
o plano no documento e sua normal é o eixo +Z local. `Offset` posiciona a face
inferior nesse eixo; `Thickness` extruda até `Offset + Thickness`. Retângulos e
polilinhas Draft usam o mesmo contorno persistente que os polígonos interativos.

## Plano durante a entrada interativa

O modo **Plano de trabalho** fixa uma cópia do plano Draft ao iniciar o comando.
Todos os pontos devem pertencer a ele. No modo **Automático**, uma única face
plana selecionada *antes* de abrir o comando fixa explicitamente o plano;
seu contorno não é usado. Uma seleção Draft Rectangle ou Draft Wire fechada
traz seu próprio plano e dispensa a coleta de pontos.

Sem face previamente selecionada, **Automático** não consulta FaceN, hover,
arestas incidentes ou posição do cursor para escolher a orientação. P1 e P2
ficam temporariamente em coordenadas globais 3D. O primeiro ponto posterior
não colinear com a direção inicial define o plano. Pontos colineares intermediários
permanecem no polígono. Nesse instante, o controlador constrói `Placement` e
converte todos os pontos anteriores para XY local. A normal +Z vem de
`(P2-P1) × (P3-P1)`, com P3 sendo o primeiro ponto não colinear; a câmera não
inverte a orientação. Depois disso, somente o plano da chapa é usado para
validar novos pontos. Um ponto fora dele é rejeitado sem projeção silenciosa.

O snap fornece a coordenada 3D do ponto, inclusive para endpoint, midpoint,
EdgeN e VertexN. Durante a chamada síncrona ao Draft Snapper no modo
Automático, a projeção interna de snaps de objeto no Work Plane é suspensa e
imediatamente restaurada. Sem snap de objeto e sem ponto 3D obtido do modelo,
o comando pede um ponto 3D válido; uma coordenada aparente no Work Plane não
é tratada como ponto 3D real. A aquisição 3D não define a orientação do plano.

## Polígono e retângulo

O polígono aceita segmentos em quaisquer ângulos. Antes de existir plano, o
preview mostra os pontos globais já coletados e o segmento até o cursor. Só
depois de fixar o plano é possível fechar o contorno, clicando perto do primeiro
ponto ou usando **Fechar contorno**. A validação inclui o segmento final.

Com plano prévio (face selecionada ou Plano de trabalho), o retângulo continua
por dois pontos e o preview aprovado mostra seus quatro lados após P1. No
Automático sem plano prévio, o retângulo precisa de três pontos: P1 é o canto,
P2 define direção e comprimento do primeiro lado, P3 determina o plano e a
largura perpendicular a esse lado. Após P1, o preview mostra uma linha até o
cursor; após P2, mostra o retângulo provisório de quatro lados quando o cursor
define um plano válido. P3 colinear é rejeitado. O resultado é o mesmo
`ContourData` de quatro segmentos, sem definição retangular especial persistida.
O preview usa nós Coin leves; o BRep só é preparado após o contorno estar fechado.

## Contorno e origem

`ContourData` é JSON determinístico com `version`, `units`, um anel `outer`
formado por segmentos tipados e `holes`. A versão 1 aceita somente segmentos
`line` e `holes: []`. Cada objeto mantém seu último contorno válido. Em
snapshot, não há link ativo para a origem. Com `KeepSourceLink`, um link ao
objeto Draft atualiza contorno e plano em recompute; caso a origem se torne
inválida, o último sólido válido permanece e `GenerationStatus` registra o
erro. A origem permanece no documento, podendo ser ocultada após a criação.

A criação final ocorre em uma transação FreeCAD; cancelar remove preview e
callbacks da vista. Sketch e Face continuam reservados como origens de
**contorno** e não são aceitos nesta etapa.

## Limite de agrupamento

Uma chapa vinculada guarda a dependência do `App::Part` que contém a origem,
para que o movimento desse contêiner atualize a chapa. Inserir posteriormente
a própria chapa nesse mesmo `App::Part` cria um ciclo de dependências no
FreeCAD 1.1.3; esse reagrupamento não é suportado nesta etapa. Manter a chapa
fora do contêiner da origem permite mover normalmente o `App::Part` e atualizar
o `Placement` associado. A chapa independente (snapshot) não possui essa
dependência.
