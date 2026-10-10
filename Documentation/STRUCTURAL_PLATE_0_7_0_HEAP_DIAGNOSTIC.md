# StructuralPlate 0.7.0 — diagnóstico nativo de heap

Registro histórico preservado. As recomendações abaixo referem-se à investigação
naquela etapa; consulte o [fechamento técnico atual](STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md)
e a [verificação posterior do tracker local](STRUCTURAL_PLATE_0_7_0_TRACKER_STABILITY.md).

Data: 09/10/2026. Branch `develop/0.7.0`, baseline `9ad0446`.

**Conclusão C: falha não reproduzida; dump parcialmente esclarecedor, sem causa completa demonstrada. Recomendação: NO-GO para ampliar a integração Draft-native por enquanto.**

Há evidência concreta de uma access violation anterior dentro de Coin e uma inconsistência de contagem no tracker Draft compartilhado pelo Rectangle nativo e pelo piloto. Não há evidência suficiente para atribuir a corrupção ao lifecycle da StructuralPlate, declarar double-free/use-after-free ou afirmar que a instabilidade foi eliminada. Nenhuma correção funcional foi aplicada nesta investigação.

## 1. Dump, ferramenta e limitações

Arquivo: `C:/Users/marco/AppData/Local/CrashDumps/freecad.exe.7956.dmp`, 18.539.859 bytes, gravado às 19:14:32. O evento Application 1000 ocorreu às 19:14:27.919. PID 7956 (`0x1f14`), FreeCAD 1.1.4.0, `ntdll.dll` 10.0.26100.9444, offset `0x117eb5`. Report ID `0f9c2e7c-2ac7-497c-986d-5eb265aad98d`.

Não foram encontrados WinDbg, CDB, KD, dumpchk ou LLDB nas instalações/caminhos examinados. A análise usou **DbgEng já disponível no Windows**, via adaptador Python/ctypes e interfaces COM. Não houve instalação de ferramentas, attach ao processo do usuário nem download de símbolos. Foi baixado apenas o [header oficial DbgEng.h da Microsoft](https://raw.githubusercontent.com/microsoft/win32metadata/main/generation/WinSDK/RecompiledIdlHeaders/um/DbgEng.h) para obter interfaces e posições dos métodos.

Comandos efetivamente usados: `.lastevent`, `.dumpdebug`, `.ecxr`, `r`, `kv 80`, `.exr`, `.cxr`, `kv 40`, `kn 40`, disassembly, `~`, `~* kv 15`, `lm` e consultas de tipos Python. `!analyze -v` e `!heap -s` foram tentados, mas as extensões responderam **“No export analyze found”** e **“No export heap found”**. O HRESULT zero do comando não significa que essas extensões funcionaram.

O minidump contém 48 threads e 275 módulos; flags `0x200121`, sem heap completo. Foi possível carregar o PDB Python 3.11 fornecido com esta instalação. Para Coin, Qt, PySide, FreeCAD e ntdll, há principalmente exports: nomes de exports distantes não identificam necessariamente a função interna em execução.

### Exceção final

Thread principal TID 27404 (`0x6b0c`), exceção `0xc0000374`, RIP `0x7ffd97d37eb5`. A stack contém:

```text
ntdll — detecção da corrupção
ntdll!RtlFreeHeap+0x6da
ucrtbase!free_base+0x1b
pyside6_cp311_win_amd64 + offset sem símbolo privado confiável
runtime VC / unwind de exceção C++
FreeCADApp / FreeCADGui
KiUserExceptionDispatcher
contexto anterior em Coin4!SoMFVec3f::setValues
```

Isso localiza a detecção em uma liberação durante tratamento/unwind de exceção. Não identifica a operação que originalmente corrompeu o heap, nem comprova que o objeto liberado pertencia ao piloto.

### Exceção anterior recuperada

O registro em `0x479f2fa130` e o contexto em `0x479f2f9c40` mostram:

```text
ExceptionCode:    0xc0000005 — leitura inválida
ExceptionAddress: 0x7ffcc9c95310 — Coin4!SoMFVec3f::setValues+0xe0
Read address:     0x1e9b9ee3000
Instruction:      movss xmm0,dword ptr [r9+0Ch]
R9:               0x1e9b9ee2ff4
R8 / RBP:         0x32 (50)
```

Trecho da stack anterior, no sentido da falha para o chamador:

```text
Coin4!SoMFVec3f::setValues+0xe0
_coin.pyd — dois frames sem símbolos privados
python311!cfunction_call
python311!_PyObject_Call / do_call_core / _PyEval_EvalFrameDefault
python311!_PyObject_Call_Prepend
python311!slot_tp_init / type_call
python311!_PyObject_MakeTpCall / PyObject_Vectorcall
python311!_PyEval_EvalFrameDefault
PySide::SignalManager::callPythonMetaMethod
Qt6Core!QTimer::timerEvent
Qt / FreeCAD — event loop
```

É compatível com construção de objeto Python chamada por timer Qt. Não aparece uma entrega ativa de SoEvent neste trecho. A classe Python, arquivo e linha não puderam ser recuperados: a memória da cadeia de frames Python não está capturada (`0x1e9c0fb02d8`). `R15=5` também existe no contexto, mas isoladamente não prova o tamanho da lista fonte.

As demais stacks foram extraídas; predominam esperas, workers, Qt/threadpool e threads gráficas. Não foi identificado um segundo contexto de exceção que esclarecesse a origem. A lista completa de DLLs está no comando `lm`: inclui Coin4, _coin, python311, PySide6/QtCore/QtGui/QtWidgets/QtTest, FreeCADApp/Gui, Part, runtimes VC/UCRT e drivers gráficos. A simples presença de uma DLL não estabelece causalidade.

## 2. Correlação com a execução original

O processo começou aproximadamente às 19:14:13.586; o evento de falha veio cerca de 14,33 s depois. O launcher retornou zero, mas seu filho `bin/freecad.exe` falhou: o retorno do launcher não valida o filho.

Os nomes de JSON/log eram reutilizados entre execuções. Seus timestamps de criação antecedem a falha, enquanto o conteúdo atual foi sobrescrito pelo probe posterior. Além disso, o script importava WorkingPlane, Qt e QtTest antes de seu primeiro registro. **Não é possível recuperar um último evento de fase confiável, associado ao PID 7956, desses arquivos.** A observação antiga de ausência do JSON não demonstra que Steel Structures ou o piloto ainda não tinham sido carregados.

| Marco original | Evidência disponível |
| --- | --- |
| FreeCAD iniciou | Confirmado por WER e stack do event loop |
| Qt/Python/Coin/Part carregados | Confirmado por módulos e stack |
| Steel Structures ativada | Não confirmado diretamente pelo dump/log por PID |
| Módulo do piloto importado | Não confirmado diretamente; módulos Python não recuperados |
| Documento criado | Não confirmado diretamente |
| Ferramenta aberta / tracker construído | Construção Python em `setValues` é provável; identidade exata desconhecida |
| Callback Coin registrado | Não confirmado para a tentativa que falhou |
| Teste começou/terminou | Fase exata não recuperável; sucesso posterior pertence a outro processo |

No piloto inspecionado, `rectangleTracker()` é construído antes de `addEventCallback`. **Se** esse construtor corresponde à stack original, a falha ocorreu antes do registro daquele callback. Trata-se de inferência condicional, não de identificação comprovada da fase.

## 3. Comparação controlada A–F

Mesma instalação portable FreeCAD 1.1.4 (`4fd3bf320`), binário direto, perfis separados derivados da mesma configuração, autoload adicional desativado, diretórios de módulos vazios e um processo por tentativa. SHA256 inicial de `user.cfg` comum às 12 execuções válidas: `73f4433fbc8d76ccb9139e7eb1153c5c7a575950636fc9d43dbe3840ea0f2131`.

A bancada inicial efetivamente observada foi PartDesign, apesar da preferência de startup Start. A mesma condição foi mantida para todos. A/B verificam ausência do módulo do piloto; A verifica ausência de módulos Steel. A instância pessoal já aberta não foi utilizada nem encerrada.

| Cenário | Processos válidos / resultado | PIDs | Cobertura |
| --- | --- | --- | --- |
| A — sem ativar Steel | 2/2, exit 0 | 3560, 14476 | Startup e event loop, sem módulos Steel |
| B — Steel carregada, sem Criar Chapa | 2/2, exit 0 | 12896, 28752 | Registro e ativação da bancada, sem importar piloto |
| C — Criar Chapa baseline 0.7.0-A | 2/2, exit 0 | 27828, 29200 | Comando real, painel, três callbacks, P1/preview programáticos, Cancelar |
| D — Rectangle nativo Draft | 2/2, exit 0 | 20748, 27796 | Um ciclo por processo, P1/preview/Esc por Qt → callback Coin real |
| E — piloto, WP atual | 2/2, exit 0 | 31276, 13104 | Três ciclos por processo, P1/preview/Esc reais, reabertura |
| F — piloto, WP temporário | 2/2, exit 0 | 29424, 2936 | Três ciclos por processo, face planar inclinada, cancelamento e restauração |

C usa `git archive 9ad0446` extraído em diretório ignorado, sem reset/checkout do working tree. Os caminhos dos módulos importados foram verificados contra esse diretório; B1 e piloto não foram importados. O archive converteu finais de linha para CRLF: os três arquivos centrais comparados são iguais aos blobs de `9ad0446` após normalização LF, registrada em `diagnostic_summary.json`.

Em D/E/F, após Esc, verificaram-se ferramenta ativa encerrada, painel fechado, tracker fora da cena e ausência de objeto criado. E/F verificaram também estado terminal do piloto e restauração dos parâmetros, `_stored` e histórico do WP. F passa uma referência de face ao mesmo caminho `Activated(plane_face=...)`; não testa a interação humana de pré-seleção.

Oito tentativas iniciais B/C/E/F foram inválidas por `ModuleNotFoundError` na instrumentação: o namespace `freecad` já inicializado pelo aplicativo exigia adicionar explicitamente o caminho do pacote isolado. Foram preservadas e excluídas do resultado. Não foram falhas nativas do produto. Os probes foram corrigidos, sem modificar os módulos funcionais.

Os novos logs são append-only, com PID, fsync antes/depois dos marcos, provenance de módulos, resultado Python e exit code do binário monitorado. Esses testes são automação nativa dentro do FreeCAD, não avaliação visual humana. Não cobrem criação final, numérico/Enter, troca de vistas/ferramentas ou todos os fluxos CAD.

## 4. Evidência comum em Draft/Pivy

Nas instalações **1.1.4 e 1.1.3**, `Mod/Draft/draftguitools/gui_trackers.py:332` contém:

```python
self.coords.point.setValues(0, 50, [[0, 0, 0],
                                  [2, 0, 0],
                                  [2, 2, 0],
                                  [0, 2, 0],
                                  [0, 0, 0]])
```

O SHA256 desse arquivo é igual nas duas instalações: `14fb6492c27b524603d8f2e5a70dc8268f77155b2ac1e82778ee2fdc349081c9`. O Rectangle nativo e o piloto instanciam esse mesmo tracker. A documentação de [Coin SoMFVec3f::setValues](https://www.coin3d.org/coin/classSoMFVec3f.html) define `num` como a quantidade de elementos a copiar da fonte.

O wrapper instalado `bin/Lib/site-packages/pivy/coin.py`, em `SoMFVec3f.setValues`, infere a quantidade para as sobrecargas sem `num`, mas encaminha diretamente a sobrecarga com contagem explícita. Em todos os ciclos D/E/F o tracker reportou **50 elementos**, apesar dos cinco pontos fornecidos.

Foram feitos somente dois probes adicionais, independentes, sem Steel, documento, tracker, WP ou callback:

| Chamada | PID | Resultado |
| --- | --- | --- |
| `field.setValues(points)` com cinco pontos | 26340 | getNum=5, primeiros cinco corretos, destruição/exit 0 |
| `field.setValues(0, 50, points)` com cinco pontos | 27896 | getNum=50, primeiros cinco corretos, destruição/exit 0 |

Isso confirma a discrepância e a ausência de rejeição dessa contagem pelo wrapper. Não reproduziu a corrupção e não demonstra a origem dos 45 elementos adicionais. Uma leitura além do buffer fonte é hipótese forte e compatível com a AV registrada em Coin, mas o dump não preserva o buffer e seu tamanho para comprová-la completamente.

Há discrepância semelhante no `polygonTracker` Draft (50 versus quatro pontos). Esse tracker é do polígono regular Draft; não é a Polilinha `Line(mode="wire")` prevista na migração. Não foi integrado nem exercitado nesta etapa.

## 5. Responsabilidade, hipóteses e decisão

- **Não classificar A:** nenhum crash novo aponta especificamente à inicialização/aquisição/teardown do piloto. A stack anterior favorece construção de objeto, sem comprovar a classe Python. Os cancelamentos reais E/F passaram.
- **Não classificar B:** nenhuma falha nativa foi reproduzida sem o piloto. O defeito de contagem é compartilhado, mas isso não equivale a reproduzir `0xc0000374` no Draft puro.
- **Classificar C:** 12 processos válidos passaram; o dump esclarece a AV anterior, mas a origem completa da corrupção e a fase original permanecem abertas.

Hipóteses abertas: leitura indevida pela contagem 50; problema secundário de tradução/unwind da AV entre Coin, FreeCAD e PySide; corrupção anterior independente, detectada na liberação; diferenças do perfil/launcher/ambiente original não reproduzidas pelos perfis isolados. Não há fundamento atual para reescrever callbacks, trocar coordenadores ou remover proteções de teardown.

**NO-GO para continuar a unificação agora.** O volume pequeno de execuções é apropriado para investigação, mas não resolve o risco identificado. A correção mínima candidata é usar `setValues(points)` ou quantidade igual a `len(points)` no construtor Draft afetado. Ela atua sobre um erro concreto, fora da arquitetura Steel; não é uma prova de correção integral do heap. Não foi aplicada à instalação, ao piloto nem por monkeypatch global nesta tarefa.

Gate proposto para uma próxima etapa delimitada: corrigir a contagem numa cópia isolada/revisável da instalação; repetir D/E/F em dois processos independentes por cenário, em **1.1.4 e 1.1.3**, com três ciclos de P1/preview/Esc/reabertura por processo, cancelamento também sem P1, WP atual e temporário. Exigir exit 0, fases por PID, nenhum novo dump, nenhum painel/tracker/objeto residual e restauração do WP. Qualquer nova falha interrompe o gate. Aprovação desse gate permitiria retomar a integração com risco residual documentado, sem afirmar eliminação absoluta.

## 6. Arquivos, preservação e verificações

Novos desta investigação:

- `scripts/diagnose_plate_heap.py`: execução limitada e perfis isolados.
- `tests/manual_plate_heap_comparison.py`: cenários A–F e logs por processo.
- `tests/manual_plate_heap_setvalues_probe.py`: comparação mínima das sobrecargas Pivy.
- Este relatório.

O relatório anterior `STRUCTURAL_PLATE_0_7_0_UNIFICATION_GATE.md` recebeu apenas uma ressalva factual sobre a inferência do primeiro JSON e referência a este diagnóstico. B1, piloto, baseline funcional, documentos Gusset e alterações locais foram preservados. SHA256 do piloto continua `76e3fdd8fe41874490810b31634379dc528fd4ba88f24be91d0be9e98eaf5b07`.

Evidências completas, ignoradas pelo Git, em `test-results/plate_heap_diagnostic/`: dump analisado em `dbgeng_dump7956.txt`, comandos em `dbgeng_commands.json`, limitação Python em `python_frames7956.json`, resultados `comparison_*.json` e diretórios individuais com `launch.json`, `events.jsonl`, `result.json`, FreeCAD.log/stdout/stderr. `diagnostic_summary.json` agrega os resultados e provenance. O dump original e evidências anteriores foram mantidos.

Comparação A–F e dois probes Pivy executados no **1.1.4**. Não foi repetida a comparação no 1.1.3 nesta investigação; apenas seu arquivo Draft foi inspecionado. Os 20 ciclos aprovados por versão do gate anterior são evidência histórica separada, não resultado desta comparação.

Verificações finais e snapshots Git constam abaixo. Não houve suíte completa, migração do Polígono, unificação, alteração de schema, git add, commit ou push. O diff rastreado corresponde às alterações experimentais preexistentes; os novos diagnósticos não entram no `git diff --stat` por estarem não rastreados.

## 7. Verificações finais e estado Git

`python scripts/check_project.py`: aprovado (exit 0). `git diff --check`: aprovado (exit 0), apenas avisos LF/CRLF nos arquivos experimentais preexistentes. Os hashes dos módulos Steel carregados nos probes E/F continuam iguais aos observados durante os testes. Não foi executada a suíte completa.

### git diff --stat

```text
 freecad/SteelStructures/commands.py                |  58 +++++++-
 freecad/SteelStructures/init_gui.py                |   2 +-
 .../interactive/plate_controller.py                |  70 ++++++++--
 .../interactive/plate_task_panel.py                |  47 +++++++
 tests/test_plate_interactive.py                    | 150 +++++++++++++++++++++
 tests/test_plate_task_panel_lifecycle.py           |   1 +
 6 files changed, 314 insertions(+), 14 deletions(-)
```

### git status --short

```text
 M freecad/SteelStructures/commands.py
 M freecad/SteelStructures/init_gui.py
 M freecad/SteelStructures/interactive/plate_controller.py
 M freecad/SteelStructures/interactive/plate_task_panel.py
 M tests/test_plate_interactive.py
 M tests/test_plate_task_panel_lifecycle.py
?? Documentation/STRUCTURAL_PLATE_0_7_0_B1.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_B_RECTANGLE_PILOT.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_HEAP_DIAGNOSTIC.md
?? Documentation/STRUCTURAL_PLATE_0_7_0_UNIFICATION_GATE.md
?? Documentation/gusset_family_review/CONFIGURACOES.md
?? Documentation/gusset_family_review/ESTRATEGIA.md
?? Documentation/gusset_family_review/F01_01.svg
?? Documentation/gusset_family_review/F01_02.svg
?? Documentation/gusset_family_review/F02_01.svg
?? Documentation/gusset_family_review/F02_02.svg
?? Documentation/gusset_family_review/F02_03.svg
?? Documentation/gusset_family_review/F02_04.svg
?? Documentation/gusset_family_review/F02_05.svg
?? Documentation/gusset_family_review/F02_06.svg
?? Documentation/gusset_family_review/F02_07.svg
?? Documentation/gusset_family_review/F02_08.svg
?? Documentation/gusset_family_review/F02_09.svg
?? Documentation/gusset_family_review/F02_10.svg
?? Documentation/gusset_family_review/F03_01.svg
?? Documentation/gusset_family_review/F03_02.svg
?? Documentation/gusset_family_review/F03_03.svg
?? Documentation/gusset_family_review/F03_04.svg
?? Documentation/gusset_family_review/F04_01.svg
?? Documentation/gusset_family_review/F04_02.svg
?? Documentation/gusset_family_review/F04_03.svg
?? Documentation/gusset_family_review/F04_04.svg
?? Documentation/gusset_family_review/F04_05.svg
?? Documentation/gusset_family_review/F05_01.svg
?? Documentation/gusset_family_review/F06_01.svg
?? Documentation/gusset_family_review/F07_01.svg
?? Documentation/gusset_family_review/F07_02.svg
?? Documentation/gusset_family_review/F07_03.svg
?? Documentation/gusset_family_review/F07_04.svg
?? Documentation/gusset_family_review/F07_05.svg
?? Documentation/gusset_family_review/F08_01.svg
?? Documentation/gusset_family_review/F09_01.svg
?? Documentation/gusset_family_review/MATRIZ.md
?? Documentation/gusset_family_review/index.html
?? Documentation/gusset_phase1/
?? Documentation/gusset_round1/
?? Documentation/gusset_tip_depth/
?? Documentation/gusset_tip_round2/
?? freecad/SteelStructures/interactive/coordinate_input_widget.py
?? freecad/SteelStructures/interactive/draft_plate_rectangle_tool.py
?? freecad/SteelStructures/interactive/point_input.py
?? scripts/diagnose_plate_heap.py
?? tests/manual_plate_heap_comparison.py
?? tests/manual_plate_heap_setvalues_probe.py
?? tests/manual_plate_numeric_input.py
?? tests/manual_plate_rectangle_lifecycle_gate.py
?? tests/manual_plate_rectangle_native.py
?? tests/manual_point_input_probe.py
?? tests/test_coordinate_input_widget.py
?? tests/test_draft_plate_rectangle_tool.py
?? tests/test_plate_rectangle_command.py
?? tests/test_point_input.py
```
