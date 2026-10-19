# Pré-seleção de aresta no Gerador de Treliças

Correção local sobre `develop/0.7.0`, HEAD publicado `29439b8`, preservando
a implementação local de Snapshot e os estudos existentes. Sem staging,
commit, push, alteração de versão ou changelog de release.

## Causa verificada

`open_truss_panel()` obtinha `Gui.Selection.getSelectionEx()` e chamava
`selected_reference()`, cujo adaptador `truss_reference.selection_reference()`
reconhece somente Linha e Retângulo Draft. A seleção explícita de `EdgeN`
de um sólido chegava a esse filtro e era recusada com a mensagem antiga.

O botão **Selecionar existente**, na categoria **Linha ou aresta**, já usava
`getSelectionEx("", 0)` e `selected_linear_reference()`. Esse caminho conserva
objeto raiz e caminho hierárquico, valida por `selected_path()`, captura por
`capture_edge()` e projeta o resultado por `_adopt_selected_reference()`.

## Correção

A abertura coleta SelectionEx com `resolve=0`. Depois de construir o painel
e vincular a sessão, encaminha a seleção completa ao mesmo resolvedor linear
e ao mesmo método de adoção utilizados pela captura interativa.

Uma opção restrita à abertura preserva o reconhecimento do Retângulo Draft
inteiro como envelope. A distinção usa a fonte resolvida e o índice do
subelemento, inclusive em caminhos de objeto inteiro terminados em ponto.
Retângulos não quadrados conservam a base inicial legada; quadrados continuam
aguardando escolha explícita. Uma aresta explícita de Retângulo é segmento
Snapshot, sem importar sua altura ou envelope.

Linha Draft continua no adaptador existente, com vínculo opcional. Arestas
genéricas conservam `TwoPoints` na configuração e **Linha ou aresta** na UI;
P0/P1 globais, vão, normal e prévia são atualizados pelo método existente.
O rótulo informa Snapshot e a opção de vínculo fica desmarcada/desabilitada.
Não há objeto auxiliar ou aplicação automática. Seleções inválidas/múltiplas
produzem aviso do resolvedor atual e preservam a configuração inicial.

Não foram modificados geometria de captura, persistência, esquema,
associatividade Draft, layout, Editor, topologias, perfis, Gussets, massa,
StructuralPlate ou comandos globais Draft.

## Arquivos desta correção

- `freecad/SteelStructures/interactive/truss_controller.py`: encaminhamento
  da abertura e exceção compatível para Retângulo inteiro.
- `tests/test_truss_preselection.py`: sete contratos Python de encaminhamento,
  seleção bruta, rejeição, abertura sem seleção e despacho compartilhado.
- `tests/test_truss_edge_snapshot_gui.py`: cinco regressões nativas adicionais,
  preservando os testes Snapshot locais anteriores.
- Este documento.

## Validação automatizada

```powershell
python -m unittest tests.test_truss_preselection tests.test_truss_edge_snapshot tests.test_truss_reference_selection tests.test_truss_reference_controls tests.test_truss_edit_session tests.test_truss_task_panel
python scripts/run_truss_duopitch_gate.py --probe edge_snapshot --editor-theme Classic
python scripts/run_truss_duopitch_gate.py --probe edge_snapshot --editor-theme "FreeCAD Dark"
python scripts/run_truss_duopitch_gate.py --probe edge_snapshot --editor-qss "C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss"
python scripts/check_project.py
git diff --check
```

Python: **73 aprovados**, sem executar a suíte completa. Verificações do
projeto e diff: aprovadas. Resultados nativos FreeCAD 1.1.4 são registrados
nos diretórios `test-results/truss-duopitch/`, com JSON, logs e capturas.

| Tema | Resultado final | Diretório do gate |
| --- | --- | --- |
| Classic | 31/31 aprovados | `1792367967606795400_4v6zd_lo` |
| FreeCAD Dark | 31/31 aprovados | `1792367860877873400_tjrvmqyg` |
| OpenDark | 31/31 aprovados | `1792367913109479000_7jsnpkl5` |

Todos encerraram com código zero, sem erros Qt ou ocorrências nos filtros de
erros nativos dos logs. As capturas da abertura estão em
`opening_edge_snapshot.png` em cada diretório. Houve também revisão técnica
independente, sem bloqueios identificados.

As regressões A/B comparam a configuração inteira e a origem informativa
exatamente, para Part Box, perfil estrutural, aresta de Retângulo e caminhos
hierárquicos transformados. Verificam modo visual, campos, candidato e
prévia 3D, ausência de objetos novos e vínculo indevido. Os demais casos
cobrem Linha Draft associativa, Retângulo inteiro em App::Part, faces,
vértices, objeto genérico inteiro, curva, Shape nula, seleção múltipla,
Esc, Cancelar, Aplicar, OK e Undo/Redo. Os testes Snapshot anteriores
continuam cobrindo demais geometrias inválidas e ciclos.

No primeiro Classic, uma comparação após persistência/Undo/Redo detectou
somente resíduo de rotação Placement de `2,2e-13`. Essa comparação usa agora
tolerância geométrica de `1e-7`; a comparação direta A/B permanece exata.

## Roteiro manual no FreeCAD 1.1.4

1. Em Classic, FreeCAD Dark e OpenDark, selecionar uma única aresta reta de
   Box/perfil antes de **Criar Treliça**. Confirmar **Linha ou aresta**, rótulo
   Snapshot, vínculo desabilitado, extremos globais, vão e prévia corretos,
   sem mensagem antiga e sem criar objetos.
2. Cancelar; abrir sem seleção, escolher **Linha ou aresta → Selecionar
   existente** e capturar a mesma aresta. Comparar coordenadas e prévia.
   Repetir após mover/rotacionar fontes e containers aninhados.
3. Pré-selecionar uma aresta de Retângulo: confirmar segmento Snapshot.
   Pré-selecionar o Retângulo inteiro: confirmar envelope/base legados;
   em quadrado, escolher a base. Pré-selecionar Linha Draft e testar vínculo.
4. Tentar objeto genérico inteiro, face, vértice, curva e seleção múltipla:
   conferir aviso coerente e ausência de escolha arbitrária/objetos novos.
5. Testar Esc, Cancelar, Aplicar, OK e Undo/Redo. Após aplicar Snapshot,
   mover/remover a fonte e confirmar independência e ausência de Linha Draft
   auxiliar.

Os gates são automação nativa FreeCAD/Qt, não validação manual do usuário.
Funcionamento e design desta correção ficam disponíveis para validação na
instalação habitual; não há autorização implícita para publicação.
