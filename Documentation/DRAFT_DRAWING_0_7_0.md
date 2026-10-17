# Desenho Draft na Steel Structures 0.7.0

Branch `develop/0.7.0`, base `27ca585`. Integração local, sem staging, commit ou push.

## Integração

A barra **Desenho Draft**, acrescentada após **Ferramentas Gerais** e antes de **Draft Snap**, contém nesta ordem:

| Ferramenta | ID oficial FreeCAD 1.1.4 | Recursos nativos |
|---|---|---|
| Linha | `Draft_Line` | `draftguitools.gui_lines.Line`, ícone `Draft_Line` |
| Polilinha | `Draft_Wire` | `draftguitools.gui_lines.Wire`, ícone `Draft_Wire` |
| Retângulo | `Draft_Rectangle` | `draftguitools.gui_rectangles.Rectangle`, ícone `Draft_Rectangle` |

As mesmas ações aparecem em **Steel Structures → Desenho Draft**. São as próprias QActions registradas pelo Draft, com seus ícones, textos, tooltips e shortcuts oficiais. Nenhum SVG foi copiado ou criado. Não há novo comando `SteelStructures_*`, wrapper, gerador ou formato de objeto.

`load_general_tools()` já importa `DraftTools` para Mover/Rotacionar/Clone. Esse módulo oficial também importa `DraftGui`, instala o Snapper se necessário, inicializa o Work Plane e registra as ferramentas de desenho. A ativação existente da bancada chama os serviços nativos de `Gui.draftToolBar`; Plano de Trabalho continua usando `Draft_SelectPlane`. A nova integração apenas filtra os três IDs disponíveis e os acrescenta a uma barra e submenu. Não ativa a workbench Draft.

Mudança funcional de produção: **oito linhas adicionadas em `init_gui.py`**. O diff textual não contém normalização em massa: o aviso LF/CRLF e a marcação anterior por EOL misto foram separados da mudança real. Núcleos paramétricos, StructuralPlate, Editor de Treliças, massa, aquisição Draft, Snapper, atalhos e Work Plane não foram modificados.

Objetos produzidos continuam sendo objetos Draft normais, sujeitos às preferências do próprio Draft. Linha de um segmento e Retângulo podem ser usados pelos adaptadores de referências já existentes; não se promete aceitação de uma polilinha arbitrária onde o contrato atual exige uma Linha ou um Retângulo. Não foi adicionada criação automática de referências no Gerador de Treliças.

## Arquivos desta rodada

- `freecad/SteelStructures/init_gui.py` — oito linhas de integração.
- `tests/test_general_tools.py` — duas verificações da barra/submenu, ordem, identidade dos comandos, indisponibilidade parcial e ativação repetida.
- `tests/test_draft_drawing_gate.py` — segurança do gate: erros Qt/nativos e falhas de cleanup não viram aprovação.
- `tests/manual_draft_drawing.py` — probe GUI por fases: interface, desenho e lifecycle.
- `scripts/run_draft_drawing_gate.py` — launcher FreeCAD 1.1.4 isolado, temas, comparação com baseline, hashes e logs.
- Este documento.

Estudos Gusset, relatórios antigos, experimentos e FCStd locais foram preservados. Resultados gerados ficam apenas em `test-results/draft_drawing/`.

## Validação concluída

```powershell
python -m unittest tests.test_general_tools tests.test_draft_drawing_gate tests.test_command_registration tests.test_truss_lifecycle tests.test_plate_creation_session tests.test_plate_task_panel_lifecycle
python scripts/check_project.py
git diff --check
```

**56 testes focados aprovados**; `check_project.py` e `git diff --check` aprovados. Não foi executada a suíte completa.

O gate de interface passou em **Classic, FreeCAD Dark e OpenDark**, com seis verificações por tema: entrada direta na Steel Structures, sem ativar Draft; IDs disponíveis; mesmas ações/ícones/tooltips oficiais na barra e submenu; barra visível. As capturas da barra foram inspecionadas.

```powershell
python scripts/run_draft_drawing_gate.py --phase interface --theme Classic
python scripts/run_draft_drawing_gate.py --phase interface --theme 'FreeCAD Dark'
python scripts/run_draft_drawing_gate.py --phase interface --qss 'C:/Users/marco/AppData/Roaming/FreeCAD/v26-3/Mod/OpenTheme/OpenDark/OpenDark.qss'
```

Execuções: `interface_6kfkn8jf`, `interface_p0vhb7gm` e `interface_91dl21_p`, respectivamente. Cada execução usa processo e perfil descartáveis. As preferências GUI de referência são copiadas; autoload é Part, seguido da ativação explícita da Steel Structures, sem passagem por Draft. O overlay é desativado apenas no perfil de teste, para manter os campos visíveis à entrada numérica programática. O perfil pessoal não é escrito.

## Bloqueio funcional encontrado — gate não aprovado

O gate de desenho chegou a criar **Linha e Polilinha pelos campos nativos**, conferir coordenadas da Linha e compatibilidade como eixo, entrada relativa/fechamento da Polilinha, Undo/Redo e Esc/Cancelar sem objetos adicionais. Foram registradas 23 verificações antes da falha. **Isso não aprova o gate completo.**

Ao abrir Retângulo em seguida, ocorreu a assinatura conhecida na factory nativa de campos Qt:

```text
gui_rectangles.py:66 Activated
  self.ui.pointUi(...)
DraftGui.py:907 pointUi → :756 taskUi → :353 setupToolBar
  self.xValue = self._inputfield("xValue", xl)
DraftGui.py:284 _inputfield
  inputfield.setObjectName(name)
Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.
```

Evidência integral: `test-results/draft_drawing/drawing_ty4sgadv/`, especialmente `stderr.txt`, `FreeCAD.log` e `tracebacks.txt`. O erro posterior `Rectangle.rect` ausente é secundário: a ativação falhou antes de criar o tracker.

Foi feita **uma comparação** usando `init_gui.py` extraído de `27ca585`, sem as oito linhas novas. O restante da produção é idêntico ao HEAD nesta tarefa. A sequência também falhou na mesma factory, desta vez ao abrir Polilinha:

```text
gui_lines.py:404 Wire.Activated → :80 Line.Activated
DraftGui.py:864 wireUi → :907 pointUi → :756 taskUi
→ :353 setupToolBar → :284 _inputfield
Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.
```

Evidência: `drawing_9vq8hv5v/baseline_init_gui.py`, `stderr.txt` e `tracebacks.txt`. O arquivo extraído foi conferido por hash contra `git show 27ca585:freecad/SteelStructures/init_gui.py`. A comparação mostra a ocorrência sem a nova integração; não identifica a causa interna da invalidação Qt. Timing/alocação do harness podem influenciar a reprodução. Não se atribui automaticamente o problema à StructuralPlate: ela não participou dessa sequência.

Ambos os processos terminaram com exit nativo 0, mas os gates retornaram falha. Não houve dumps novos; os arquivos monitorados da instalação Draft permaneceram idênticos. O launcher passou a verificar também assinaturas nos logs e falhas de limpeza, além do resultado do probe, e registra snapshots/hashes dos scripts e do módulo efetivamente carregado. Os primeiros manifests, anteriores a essa ampliação de metadados, são complementados pelo inventário de comparação em `baseline_comparison.json`.

As primeiras tentativas tiveram problemas de harness, separados do bloqueio acima: uma referência Qt de menu sem retenção das QActions; perfil mínimo com Task View oculta por overlay; e instrumentação lendo campos depois de seu encerramento nativo. Esses erros foram corrigidos somente no teste, com evidências preservadas. Nenhum deles motivou alteração de produção.

## Aprovação manual e limites

**O usuário concluiu e aprovou a validação manual interativa no FreeCAD 1.1.4.** Conforme confirmação do usuário, Linha, Polilinha e Retângulo funcionaram sem erros, incluindo snapping, coordenadas, Plano de Trabalho, Esc, Undo/Redo e alternância com ferramentas estruturais. Essa aprovação manual é distinta dos resultados automatizados acima; não transforma o gate de desenho em aprovado.

Após a reprodução com o baseline, não foram repetidas campanhas funcionais automatizadas. Permanecem sem conclusão pelo gate: criação final de Retângulo; snapping gráfico/restrições; Work Plane inclinado; referência posterior de Retângulo; substituições nos dois sentidos com Treliça/Membro/Pilar/Chapa; troca/fechamento de documentos durante desenho. O probe contém essas verificações, mas elas ficaram após o ponto de interrupção ou na fase lifecycle não executada. Não são resultados automatizados aprovados. A confirmação manual não especifica cobertura individual de troca/fechamento de documentos ou de cada tipo de referência.

Não há correção fundamentada nas oito linhas de integração para um wrapper inválido retornado pela factory nativa. Não foram introduzidos timers de produção, filtros globais, alterações do Draft ou contornos na StructuralPlate. A investigação/correção desse problema deve ser tratada separadamente antes de declarar estabilidade completa.

## Fechamento para commit seletivo

Avaliação técnica: **GO para commit local seletivo**, considerando a aprovação manual informada pelo usuário e a ausência de defeito comprovado nesta integração. O erro nativo `QLineEdit already deleted`, também reproduzido no baseline `27ca585`, permanece como risco conhecido. Não se declara aprovação global dos gates funcionais nem de release.

Seleção exata e mínima recomendada, incluindo o conjunto de regressão GUI e suas dependências:

```text
freecad/SteelStructures/init_gui.py
tests/test_general_tools.py
tests/test_draft_drawing_gate.py
tests/manual_draft_drawing.py
scripts/run_draft_drawing_gate.py
Documentation/DRAFT_DRAWING_0_7_0.md
```

Os dois primeiros arquivos já são versionados: o diff soma 33 inserções e nenhuma remoção (8 e 25 linhas, respectivamente). Os outros quatro são novos. O teste do gate depende do launcher e do probe; os três devem acompanhar a integração. Não há módulos funcionais ou SVGs novos necessários. Avisos LF/CRLF não correspondem a uma reescrita dos arquivos e não foram normalizados.

Todos os demais arquivos locais ficam fora da seleção, incluindo documentação antiga de Treliças/StructuralPlate, estudos Gusset, diagnósticos de chapa, FCStd, logs, dumps e resultados gerados. Nenhum deles foi removido ou reorganizado.

Mensagem sugerida: `feat: integrar comandos nativos de desenho Draft`.

## Roteiro manual — FreeCAD 1.1.4

1. Inicie diretamente na Steel Structures. Confira a barra **Desenho Draft**, depois de Ferramentas Gerais, e o submenu **Steel Structures → Desenho Draft**; compare os ícones/tooltips oficiais.
2. Crie uma Linha por pontos e outra por coordenadas. Teste snap de extremidade, restrição X/Y, Esc, Undo e Redo.
3. Crie uma Polilinha com vários segmentos e feche-a pelo controle nativo. Crie um Retângulo por dois pontos; repita em Work Plane inclinado.
4. Use a Linha e o Retângulo nos fluxos de referência atualmente suportados. Não espere que uma polilinha arbitrária seja aceita onde apenas Linha/Retângulo são suportados.
5. Abra cada ferramenta estrutural e ative os três comandos Draft. Confira encerramento da Task View e ausência de preview/captura antiga. Depois cancele o Draft e abra imediatamente Treliça, Membro, Pilar e Chapa.
6. Teste troca/fechamento de documento e os três temas. Se reaparecer `QLineEdit already deleted`, preserve a Vista de relatório e interrompa essa sequência; não classifique a ocorrência automaticamente como regressão deste incremento.

Nenhum git add, commit ou push foi realizado. Branch e HEAD continuam `develop/0.7.0` / `27ca585`.
