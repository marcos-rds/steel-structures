# Refinamento visual — Eixos nominais e extremidades

Data: 24/10/2026. Branch: `develop/0.7.0`. HEAD: `f303f81`.

**GO para validação manual do refinamento visual.** A implementação e os gates
descritos abaixo estão concluídos; a aprovação estética em modelos reais permanece
com o usuário. Não há autorização de publicação implícita neste relatório.

## Escopo e referência

Esta etapa parte do MVP local funcional, documentado em
[STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md](STRUCTURAL_REFERENCE_VISUALIZATION_MVP.md),
e mantém os contratos da
[auditoria arquitetural](STRUCTURAL_REFERENCE_ARCHITECTURE_STUDY.md).
Altera somente a apresentação transitória dos eixos nominais e suas extremidades.
Os parâmetros visuais deste relatório substituem os valores iniciais do MVP;
os relatórios anteriores ficam preservados como histórico.

Não houve alteração da resolução geométrica, engine de membros, fontes de eixos,
elegibilidade das categorias, cortes, treliças, schema, propriedades persistentes,
transações, catálogo ou referências paramétricas. Não foram acrescentados snaps,
conectividade, divisão de eixos, Raio X ou inferência de nós estruturais.

## Decisões visuais

| Elemento | MVP anterior | Refinamento |
| --- | --- | --- |
| Linha principal | Ciano, largura 1,5 | Dourado `RGB (1,0; 0,78; 0,10)`, largura 3 |
| Contraste da linha | Passagem escura, largura 3,5 | Passagem escura, largura 5 |
| Padrão | `0xE4E4`, traço/ponto denso | `0x00FF`, tracejado uniforme, fator 2 |
| Extremidades | Início circular/fim quadrado, preenchimento azul 5 e exterior escuro 9 | Ambos circulares, preenchimento laranja 9, contorno branco 13 e proteção externa escura 15 |
| Escala de apresentação | Tamanhos iniciais fixos | Espessuras e diâmetros acompanham o DPR Qt |

Larguras e diâmetros são valores de tela, sem unidade do modelo. O padrão usa
oito bits ligados/oito desligados e fator 2: aproximadamente 16 pixels de traço
e 16 de intervalo em DPR 1. O contorno escuro acompanha o mesmo padrão, reforçando
a linha também sobre fundos claros. A cor dourada e o laranja não dependem da
cor dos perfis ou da paleta do painel. Não foi criado diálogo de preferências.

Em DPR 1,5, as larguras principal/externa são 4,5/7,5; os marcadores usam diâmetros
ímpares 23/21/15 para exterior/contorno/preenchimento. O fator do tracejado passa
a 3. O ajuste é de apresentação: não muda coordenadas, cache de eixos ou sólidos.
A reconciliação leve de vistas já existente detecta mudança de DPR; com escala
inalterada, `refresh_style()` retorna sem atualizar os campos Coin.

Os dois extremos recebem o mesmo círculo forte. Isso elimina a aparência de
quadrado fraco e atende à preferência visual desta etapa. Start/End continuam
distintos nos dados nominais; o símbolo não afirma ligação ou conectividade.

### Marcadores circulares e robustez

São três passagens de `SoMarkerSet` sobre as mesmas coordenadas: proteção escura,
disco branco e disco laranja. Os pequenos mapas circulares são registrados pela
API pública e compartilhados por diâmetro. Os registros não são removidos ao
desligar uma camada, pois outra vista pode utilizá-los; repetir liga/desliga não
acrescenta registros para diâmetros já disponíveis. O gate verifica 20 ciclos.

A implementação usa a sobrecarga Pivy de `addMarker`, que recebe mapa ASCII
largura × altura, com espaço para pixel apagado. O binding empacota esse mapa;
não se deve fornecer diretamente bytes já empacotados da API C++.
Referências primárias: [SoMarkerSet](https://www.coin3d.org/coin/classSoMarkerSet.html),
[binding Pivy](https://github.com/coin3d/pivy/blob/master/Inventor/nodes/SoMarkerSet.i)
e [SoDrawStyle](https://www.coin3d.org/coin/classSoDrawStyle.html).

Um protótipo intermediário com bytes empacotados passou pelas asserções funcionais,
mas produziu símbolos incorretos nas capturas. Foi descartado após inspeção visual.
Os quatro gates finais usam o mapa ASCII corrigido, e seus renders foram
inspecionados. Os diretórios intermediários permanecem como evidência diagnóstica,
sem integrar a certificação final abaixo.

### Contratos mantidos

- `SoPickStyle.UNPICKABLE`, teste de profundidade normal `LEQUAL` e ausência de
  escrita no depth buffer da camada permanecem ativos.
- Nenhuma transparência, cor ou propriedade visual dos membros é modificada.
- Mostrar/Ocultar Eixos e Mostrar/Ocultar Extremidades continuam independentes,
  sem transação e com os mesmos IDs, ícones, estados e integração de bancada.
- Somente o tooltip de extremidades foi atualizado para descrever os círculos;
  continua informando que são extremidades nominais e podem ficar ocultas.
- A camada conserva um lote por vista. A terceira passagem dos marcadores leva
  o total de 21 a 24 nós Coin por vista, constante para 100 ou 1.000 membros.
- Remoção de cenas, observers, timers e flags por documento segue o serviço
  existente. Os mapas de marcador são pequenos recursos compartilhados do processo.

## Inventário fechado desta etapa

A comparação é contra o snapshot do MVP local no início desta rodada, não contra
o HEAD publicado, que ainda não contém o MVP.

| Arquivo | Alteração nesta rodada |
| --- | --- |
| `freecad/SteelStructures/interactive/structural_reference_view.py` | Estilo, mapas circulares compartilhados e atualização de DPI |
| `freecad/SteelStructures/interactive/structural_reference_commands.py` | Texto do tooltip de extremidades |
| `tests/test_structural_reference_view.py` | Contratos do renderer, mapa circular, escala e reuso |
| `tests/manual_structural_reference_visualization.py` | Asserções nativas de estilo/reuso e galeria W/U/treliça |
| `Documentation/STRUCTURAL_REFERENCE_VISUAL_REFINEMENT.md` | Este relatório novo |

O runner `scripts/run_structural_reference_visualization_gate.py`, o resolver
`structural_reference.py`, a integração `init_gui.py` e todos os módulos físicos
permanecem iguais ao início desta etapa. Arquivos já locais do MVP ou de estudos
externos não devem ser confundidos com modificações deste refinamento.

## Validação automatizada

### Python direcionado

**354 testes aprovados, sem failures, errors ou skips** (2,276 s). O módulo de
apresentação contém 14 testes, incluindo dois novos casos. Cobrem formato e
simetria do mapa ASCII, cores, espessuras, tracejado, três passagens, DPR 1/1,5,
reuso de registros e ausência de atualização geométrica ao mudar somente o DPI.
O caso de lote vazio/reduzido verifica `numPoints`, preservando picking e depth.
Permanecem as regressões de documentos, vistas, cache, replay, limpeza e comandos.

Comando da campanha, com os 20 módulos relevantes:

```powershell
python -B -m unittest -v tests.test_structural_reference tests.test_structural_reference_view tests.test_general_tools tests.test_grid_command tests.test_member_axis_source tests.test_member_axis_creation tests.test_member_placement tests.test_member_orientation tests.test_column_command tests.test_draft_native_member_tool tests.test_grid_object tests.test_grid_view tests.test_truss_copy tests.test_truss_lifecycle tests.test_truss_apply_session tests.test_member_adjustment_controller tests.test_member_adjustment_preview tests.test_member_miter_controller tests.test_member_miter_preview tests.test_member_plane_cut
```

### Gates FreeCAD 1.1.4 / Windows

| Execução final | DPR observado | Verificações | Resultado |
| --- | --- | --- | --- |
| Classic — `1792864557821849800_Classic_kyimhddo` | 1,0 | 162 | PASS |
| FreeCAD Dark — `1792864581400458200_FreeCAD_Dark_9vypdw8q` | 1,0 | 162 | PASS |
| OpenDark — `1792864713028523100_OpenDark_p0qvdxb0` | 1,0 | 162 | PASS |
| OpenDark 150% — `1792864471581359300_OpenDark_4a7zfn9g` | 1,5 | 162 | PASS |

**648 verificações**, quatro processos com saída 0, sem timeout, erros Python/Qt
de callbacks ou erros capturados nos logs nativos. Os quatro manifestos registram
os mesmos 156 hashes de fontes, correspondentes aos arquivos atuais.

Os gates exercitam os comandos reais, toggles independentes, 20 ciclos de
ativação, registro de marcadores sem crescimento por toggle, atualização e redução
do lote, membros inclinados/hierárquicos, filhos físicos elegíveis de treliças,
cortes, Undo/Redo sem recompute manual para replay conhecido, documentos/vistas
múltiplos, fechamento, desativação, FCStd e preservação de parâmetros, sólidos,
estado visual e histórico. Os critérios de elegibilidade anteriores não mudaram.

Foram acrescentados renders frontais de pórticos W e U, eixo excêntrico exposto e
treliça, com sólidos opacos e com transparência manual de 70% aplicada somente
às fixtures de teste, depois restaurada. A câmera da galeria tem animação
desabilitada para capturas estáveis; a navegação da produção não mudou.
Renders `saveImage` foram inspecionados nos três temas e em OpenDark 150%.
Grabs da janela continuam sujeitos ao artefato OpenGL de captura do ambiente;
a avaliação da geometria usa os renders da vista.

Comandos executados:

```powershell
python scripts/run_structural_reference_visualization_gate.py --theme Classic --output-root test-results/structural-reference-visual-refinement/native
python scripts/run_structural_reference_visualization_gate.py --theme "FreeCAD Dark" --output-root test-results/structural-reference-visual-refinement/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --output-root test-results/structural-reference-visual-refinement/native
python scripts/run_structural_reference_visualization_gate.py --theme OpenDark --scale-factor 1.5 --output-root test-results/structural-reference-visual-refinement/native
python scripts/check_project.py
git diff --check
```

`check_project.py` e `git diff --check` aprovados. Também foi verificada a
integridade UTF-8 e ausência de whitespace inválido nos cinco arquivos da etapa,
inclusive os ainda não rastreados pelo Git, com comparação `--no-index --check`.
A suíte Python completa não foi executada nesta rodada de polimento; fica
reservada para o fechamento após aprovação manual.

### Desempenho e preservação

As quatro execuções mantiveram 24 nós Coin tanto em 100 como em 1.000 membros.
A treliça de 103 filhos físicos utilizou uma leitura compartilhada do owner por
lote. São verificações de sanidade no ambiente local, não benchmark universal.
A mudança de estilo não solicita recompute de sólidos nem cria callbacks de mouse.

O snapshot inicial inclui 611 arquivos. Somente os quatro arquivos existentes do
inventário acima mudaram; **607 arquivos fora desta etapa permaneceram idênticos**.
Este relatório é a única adição fora dos artefatos ignorados de evidência.
HEAD e índice Git permanecem inalterados. StructuralPlate, Gusset, treliças,
FCStd, backups e documentação anterior estão preservados. Não houve staging,
commit, push, merge, tag, release ou limpeza destrutiva.

Evidências locais: `test-results/structural-reference-visual-refinement/`, com
logs Python, manifestos, resultados nativos, imagens e conferência de hashes.

## Alternativas descartadas

- Manter traço/ponto denso: continuava fraco em fundo escuro; adotado tracejado limpo.
- Apenas ampliar o marcador embutido: tamanhos disponíveis eram insuficientes
  para preenchimento e contorno legíveis; adotada a API pública de mapa circular.
- Esferas em unidades do modelo: tamanho variaria inadequadamente com zoom.
- Desligar profundidade, usar `SoAnnotation` para atravessar sólidos ou aplicar
  transparência automática: introduziria uma forma de Raio X fora do escopo.
- Shaders, billboards próprios, hooks OpenGL e dependências nativas adicionais:
  complexidade desnecessária para esta apresentação.

## Limitações remanescentes

1. **Sólidos opacos continuam ocultando eixos internos.** Um eixo centrado pode
   desaparecer integralmente; círculos podem aparecer parcialmente nas faces.
   O refinamento melhora os trechos expostos, sem prometer visão através do aço.
2. As dimensões são de tela: zoom muito distante pode juntar extremidades próximas.
   Círculos rasterizados podem revelar discretização em ampliação de captura.
3. Largura de linha e antialiasing dependem do driver OpenGL. A certificação desta
   rodada é FreeCAD 1.1.4 no Windows disponível, não todos os drivers/plataformas.
4. OpenDark com `QT_SCALE_FACTOR=1.5` foi exercitado nativamente. A transição física
   entre monitores com DPI diferentes foi coberta por teste de estilo, sem prova
   manual de movimentação de janela entre telas.
5. Início e fim compartilham o símbolo circular. Não há rótulos, indicação de
   conectividade nem deduplicação de extremidades coincidentes nesta etapa.
6. Aprovação visual em estruturas reais e interação manual completa com previews
   de outras ferramentas continuam no roteiro do usuário; gates não substituem
   essa aprovação.

## Roteiro curto de validação manual

1. Reiniciar/recarregar a bancada e abrir um modelo W e U. Ligar eixos e
   extremidades separadamente e juntos. Conferir dourado tracejado e círculos
   laranja/branco, sem alteração da aparência ao desligar.
2. Observar pórticos e treliças em vista frontal e perspectiva, com zoom próximo
   e distante. Conferir se as extremidades chamam atenção sem encobrir o modelo.
3. Comparar sólidos opacos e transparência aplicada manualmente pelo usuário.
   Em sólidos opacos, avaliar os trechos realmente expostos; não esperar Raio X.
4. Conferir membro com inserção/offset excêntrico e membro cortado: referências
   continuam nominais e não precisam coincidir com as faces físicas finais.
5. Repetir em Classic, FreeCAD Dark e OpenDark, incluindo OpenDark a 150%.
   Avaliar contraste, espessura e espaçamento do tracejado na tela de trabalho.
6. Mover/rotacionar e usar Undo/Redo; repetir liga/desliga, alternar documento,
   fechar vista e trocar de bancada. Não devem restar símbolos órfãos.
7. Com a camada ligada, selecionar membros e abrir/cancelar uma ferramenta
   existente; os símbolos não devem capturar seleção ou modificar gestos.

**Decisão: GO para validação manual visual.** Persistem as limitações de
profundidade explicitadas acima; nenhum novo modo de visualização foi introduzido.
