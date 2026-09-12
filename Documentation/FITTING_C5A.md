# Physical Fitting C5-A

C5-A introduz um núcleo genérico e puro para transformar relações topológicas declaradas em ajustes físicos de extremidade. O pipeline é `Topology / PhysicalRuns → PhysicalFitResolver → PhysicalFitPlan → ajustes do StructuralMember → Shape`.

## Contrato

`PhysicalFitPlan` é imutável, versionado e usa somente IDs estáveis. Cada plano identifica o membro físico e o `PhysicalRun` lógico e pode conter uma ação independente para `Start` e `End`. Uma ação registra modo (`LengthLimit` ou `PlaneCut`), referência estável, gap, fonte e, quando necessário, origem e normal de um plano geométrico puro. O resolver não importa FreeCAD, Part, Qt ou Coin e não cria nem altera objetos de documento.

Os modos conceituais são `None`, `ToChord`, `GussetAware` e `Custom`. C5-A implementa `None` e `ToChord`. Os dois últimos já são reconhecidos pelo schema, porém retornam diagnóstico de modo ainda não implementado. Reservas futuras de gusset (`normal_clearance`, `plate_thickness` e `side_clearance`) são grandezas distintas do gap axial.

## Eixo nominal e forma física

`StartPoint` e `EndPoint` continuam representando sempre o eixo nominal lógico entre nós. O fitting alimenta a infraestrutura existente de ajustes por ponta. Seus resultados permanecem em `EffectiveStartPoint`, `EffectiveEndPoint`, `AdjustedLength` e `Shape`. Mover ou recortar a forma física nunca reescreve os pontos nominais.

## ToChord

Somente incidências explícitas em `TopologyNode` criam candidatos. A ponta é escolhida por `start_node_key` ou `end_node_key`, nunca pela ordem das coordenadas. Cruzamentos geométricos sem nó continuam desconectados. Em um nó com várias webs, cada diagonal, montante ou fechamento recebe um plano independente.

Top e bottom chords são referências. Um `PhysicalRun` contínuo pode atravessar vários nós interiores e não é segmentado nem cortado por causa deles. Chords já segmentados por política explícita preservam essa cardinalidade; C5-A não inventa cortes adicionais.

O adapter da treliça cruza o eixo da web com o contorno físico da seção do banzo, incluindo inserção e transformações da seção. O plano de encontro passa por essa face física e contém a direção do banzo. Sua normal fica no plano da treliça, perpendicular ao banzo e é orientada deterministicamente. Assim, `gap = 0` chega à face resolvida mesmo em perfis abertos, e o cálculo continua válido quando o plano da treliça está inclinado, sem depender de câmera ou eixos globais.

`LengthLimit` é usado quando a face final é transversal ao eixo da web ou como fallback axial estável. `PlaneCut` é usado quando a obliquidade muda visivelmente a face final. Referências degeneradas ou ambiguidades produzem diagnóstico e não introduzem uma ação inválida.

## Gap e prioridade

`Gap` é sempre axial ao `StructuralMember`: um valor positivo recua `Start` no sentido do eixo e recua `End` no sentido oposto. Ele não representa afastamento normal à face do banzo, espessura de gusset ou folga de solda.

O adapter persiste o plano automático e um snapshot canônico dos campos que ele controlou. Um campo divergente desse snapshot é tratado como ajuste manual e tem prioridade (`Manual > AutoFit`). O autofit não o sobrescreve silenciosamente e registra diagnóstico humano. Planos e referências usam IDs estáveis, nunca `Label`, para reprodução após save/reopen e atualização sem recriar objetos quando a cardinalidade não muda.

## Assemblies, preview e limites

O target pertence ao `PhysicalRun` lógico, mas o plano é materializado para cada componente primário A/B usando seu próprio eixo físico. Interconnectors de C4 são excluídos explicitamente do fitting de nós e continuam sob controle da camada de assembly. Depois do fitting dos componentes A/B, sua distribuição é regenerada sobre o envelope físico útil do hospedeiro e respeita o envelope completo do banzo; isso evita presilhas em regiões removidas por um corte oblíquo ou dentro de uma aba de perfil aberto. O preview 3D da Treliça chama o mesmo `prepare_batch` e os mesmos `PhysicalFitPlan` usados pelo documento, sem criar FeaturePython temporário.

O editor de role expõe apenas `Nenhum`, `Ajustar ao banzo` e `Gap axial` para diagonais, montantes e fechamentos. Não há editor completo de conexões nesta etapa.

Novas treliças iniciam diagonais, montantes e fechamentos esquerdo/direito em `ToChord`, com gap axial igual a zero. Banzos iniciam em `None`. Essa escolha pertence somente ao factory de uma nova treliça: documentos e payloads antigos sem campos de fitting continuam interpretados como `None` e não são migrados silenciosamente.

Ao reabrir o Gerador depois de Undo/Redo, o controller reconstrói o snapshot aceito somente para membros cujas propriedades controladas ainda correspondem exatamente ao `AppliedState` restaurado. Uma propriedade realmente alterada fora do fluxo continua divergente e mantém o diagnóstico de edição manual.

## Próximo escopo C5-B

- conexão direta entre webs;
- miter/meia-esquadria equilibrada em nó;
- prioridade entre membros no encontro;
- evolução do modo `GussetAware`.

Essas operações continuarão preservando os eixos nominais e os `TopologyNode`. C5-A não resolve fitting web-web.

Ficam fora de C5-A: gusset físico, parafusos, furos, soldas, ConnectionIntent completo, cope, notch, ElementCut, saddle cut, recortes flange-specific e verificações normativas. Operações futuras de `ElementCut`/`Cope`/`Notch` deverão formar uma etapa geométrica posterior; elas não serão adicionadas como variantes de ajuste longitudinal de extremidade.
