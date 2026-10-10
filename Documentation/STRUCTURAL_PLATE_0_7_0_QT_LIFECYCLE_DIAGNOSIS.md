# Diagnóstico Qt — Criar Chapa Estrutural 0.7.0

10/10/2026. Branch `develop/0.7.0`, HEAD
`9ad0446f9cb896a8f9255a3ea698156adc063834`. Continuação do
[fechamento técnico](STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md).

**NO-GO para repetir o gate final neste estado.** O mesmo erro de wrapper Qt
destruído foi reproduzido com Draft Line puro, sem importar Steel Structures.
Uma variante do controle também registrou Access Violation capturado pelo
FreeCAD. A campanha GUI foi interrompida ao identificar essa evidência.
Nenhuma correção de produção foi aplicada: não foi demonstrada causa corrigível
na bancada. Commit e release continuam sem aprovação.

## Reconstrução do fechamento

Run `test-results/plate_unified_gate/1791666148716274100_1.1.3_integrated/1/`,
PID 6692, 42 verificações e 62 ativações. O harness abriu Polígono Automático
sem confirmar pontos, ainda sem plano, e executou `Gui.runCommand("Draft_Line")`
diretamente, sem Esc prévio. A nova Line começou sua construção após o
encerramento da sessão anterior. O log registra:

```text
Running the Python command 'Draft_Line' failed:
gui_lines.py:86 Activated → self.ui.lineUi(...)
DraftGui.py:849 lineUi → pointUi(...)
DraftGui.py:907 pointUi → taskUi(...)
DraftGui.py:756 taskUi → setupToolBar(task=True)
DraftGui.py:357 setupToolBar → self.yValue = self._inputfield("yValue", yl)
DraftGui.py:284 _inputfield → inputfield.setObjectName(name)
Internal C++ object (PySide6.QtWidgets.QLineEdit) already deleted.
```

`Gui::InputField` aparece em Python como `PySide6.QtWidgets.QLineEdit`.
`replacement_debug` registrou `old_state=FINISHED`, `session_closed=true`,
`has_panel=false`, `attached=false`, `old_active=false`, `new_command=Line`.
A assertion de diálogo da nova Line falhou depois. O registro não contém uma
fotografia completa dos timers/closures pendentes naquele instante; não é
possível reconstruí-los retroativamente nem afirmar que todos estavam vazios.
O callback Coin da nova Line ainda não fora instalado no ponto da exceção.

A ocorrência anterior em 1.1.4, PID 3396,
`1791662756163138800_1.1.4_integrated/1/FreeCAD.log:384–403`, já falhava na mesma
factory antes de abrir Automático. Logo, Automático não é condição necessária.

## Probe e resultados desta investigação

`scripts/diagnose_plate_qt_lifecycle.py` executa processos GUI reais independentes,
com perfil isolado e logs de stdout/stderr/FreeCAD, resultado, estado Draft,
validade Shiboken, hashes e detecção de novos dumps. Não modifica instalações.
`tests/manual_plate_qt_lifecycle.py` contém A–G. A instrumentação opcional delega
à factory original; a closure de `destroyed` guarda somente números, não widgets.
O campo `valid` no evento `inputfield_destroyed` é o snapshot da criação;
somente as consultas posteriores `qt_state` medem a validade atual.

Foram usados inicialmente poucos processos, nunca campanhas de centenas de ciclos:

| Cenário | FreeCAD 1.1.3 nesta rodada | FreeCAD 1.1.4 nesta rodada |
|---|---|---|
| A: Line → Esc → Line | Reproduziu o erro; variante queued registrou Access Violation | Não executado após interrupção |
| B: Polígono Draft → Esc → Line | 2 processos aprovados, sem erros Python/nativos nos logs | Não executado |
| C: Automático vazio → Esc → Line | 1 falha do harness antes de abrir Line; 2º processo interrompido | Não executado |
| D: Automático P1 → Esc → Line | Não executado | Não executado |
| E: Automático P1/P2/P3 → Esc → Line | Não executado | Não executado |
| F: Automático criar → Line | Não executado | Não executado |
| G: Automático → Line diretamente | Não executado isoladamente; falhou no fechamento anterior | Não executado |

Comandos executados, na ordem (não representam autorização para nova campanha):

```text
python scripts/diagnose_plate_qt_lifecycle.py --version 1.1.3 --scenarios ABCDEFG --repetitions 2
python scripts/diagnose_plate_qt_lifecycle.py --version 1.1.3 --scenarios A --repetitions 2 --trace
python scripts/diagnose_plate_qt_lifecycle.py --version 1.1.3 --scenarios ABCDEFG --repetitions 2 --dispatch queued --continue-python-errors
```

Os dois primeiros comandos usaram o dispatch `nested` então padrão: ambos
pararam em A1, na segunda abertura, sem evidência nativa nos logs. Artefatos:
`1791674286835968900_1.1.3` e `1791674316837753700_1.1.3`.
O código posterior do probe passou a oferecer etapas por generator; os manifests
preservam o hash do harness efetivamente executado, não o da revisão atual.

No terceiro batch, `1791674436450325900_1.1.3`, as etapas retornaram ao event loop
entre ações, usando singleShot de 50 ms, sem loop manual de `processEvents`.
A1/PID 8588 mostrou campos válidos imediatamente após a segunda abertura e
inválidos na etapa seguinte; `DraftBaseWidget.eventFilter:81` e
`ToDo.doTasks:141 → DraftToolBar.setFocus:803` acessaram campos destruídos.
O controle A2 falhou ao verificar o diálogo da primeira Line: falha diferente,
não classificada como reprodução de InputField. C1 falhou ao verificar sessão
encerrada após Esc, antes da transição para Line. Foco/timing do harness nesses
dois casos permanece hipótese; não há prova de defeito da chapa nesses resultados.

**Interrupção nativa:** A1 contém dez mensagens `The error message is: Access
violation` em stderr, também presentes no FreeCAD.log, emitidas por
`GUIApplication::notify`. São as mesmas ocorrências duplicadas nos dois arquivos,
não vinte falhas independentes. No stderr surgem depois da assertion do probe,
no período de limpeza/encerramento; não há stack nativa que localize o acesso
causador. O processo terminou com zero e sem novo dump.
O runner inicial detectava falhas Python, saída e dumps, mas não essa mensagem
nativa capturada: continuou até C2 enquanto os logs eram examinados. Ao identificar
o Access Violation, a campanha foi interrompida e o processo C2 encerrado; sua
ausência foi conferida. D–G não foram iniciados. O classificador foi corrigido
para interromper também por assinatura nativa no log, mesmo com exit zero e
`--continue-python-errors`. Essa correção do harness foi testada offline;
nenhuma campanha GUI foi retomada depois da interrupção.

## Mecanismo observado e hipóteses

O controle A não importa Steel Structures. No trace A1:

- após Esc, comando/sourceCmd nulos, diálogo fechado e filas ToDo vazias;
- os campos antigos existem como wrappers Python, mas `isValid=false`;
- a segunda factory devolve o mesmo objeto Python do antigo `zValue`, ID
  `1788829471488`, já inválido, agora na construção de `xValue`;
- não há evento de GC entre entrada e retorno dessa factory;
- ao iniciar Line, o Draft enfileira seu próprio `closeDialog`. Isso não é
  callback da chapa. A influência dessa ordem ainda não foi isolada.

Portanto, está comprovado o retorno de um wrapper inválido pela factory em
Draft puro, dentro do harness. A falha não depende de um callback Steel ativo.
Isso não prova reprodução por interação humana, nem exclui influência do harness
ou timing na infraestrutura Draft/Qt.

O código do [FreeCAD no commit 145529fe](https://raw.githubusercontent.com/FreeCAD/FreeCAD/145529fe741292ff0b3977a01195bf0247425794/src/Gui/PythonWrapper.cpp)
tem a conversão `fromQWidget` por `Shiboken::Object::newObject` (817–832) e
invalidação por WrapperManager (395–432). Esta marca o wrapper inválido, sem
remoção explícita do registro BindingManager nesse trecho. Em
[Shiboken 6.8.3, basewrapper.cpp](https://raw.githubusercontent.com/pyside/pyside-setup/v6.8.3/sources/shiboken6/libshiboken/basewrapper.cpp)
(1466–1495), a conversão consulta um wrapper já registrado e pode retorná-lo sem
teste de validade. A consulta é por endereço no
[bindingmanager.cpp](https://raw.githubusercontent.com/pyside/pyside-setup/v6.8.3/sources/shiboken6/libshiboken/bindingmanager.cpp)
(290–296). O helper QObject de
[PySide 6.8.3](https://raw.githubusercontent.com/pyside/pyside-setup/v6.8.3/sources/pyside6/libpyside/pyside.cpp)
(671–684, 740–764) inclui outro contrato de remoção do registro.

**Inferência, não causa concluída:** registro antigo associado a endereço C++
reutilizado. O novo endereço não foi medido quando o wrapper veio inválido;
também não foi instrumentada a propriedade de invalidação do QObject. Não se
pode afirmar alias de memória, nem relacionar conclusivamente essa hipótese ao
Access Violation ou ao histórico `0xc0000374`. A instalação 1.1.3 informa commit
FreeCAD 145529fe e PySide/Shiboken 6.8.3; não houve depuração nativa do binário.

## Auditoria da bancada e decisão de correção

Revisados `PlateCreationSession.finish/_legacy_closed/_defer_advanced_cancel`,
`PlateTaskPanel._finish/_disconnect_widgets`, `PlateController.cancel/stop_capture`
e `StructuralMemberDraftTool._terminate_native_session`:

- o painel desliga timers próprios, sinais, atalhos e referências de atualização;
- o controller remove callbacks Coin e preview; a troca para outra ferramenta
  protege o Snapper que já pertence ao novo comando;
- Automático não chama o teardown Creator nativo sobre a nova Line nem muda
  `DraftToolBar.sourceCmd` nesse caminho;
- Membro encerra Creator sincronamente e invalida atualizações por geração;
- `singleShot(0, self.finish)` da sessão captura `self`. Duplicação/reentrância
  desse caminho merece isolamento futuro, mas não foi demonstrada como causa
  deste erro; não foi alterada por hipótese.

Não foi identificado callback da Steel acessando o InputField da nova Line.
O probe isolado não equivale a provar ausência universal de callbacks tardios.
Não foram adicionados try/except, retries, limpeza global Draft, checagens de
validade em produção ou alteração de ownership. O tracker local de cinco vetores
e todos os sistemas de aquisição aprovados permanecem intactos.

## Verificações e integridade

Executado somente o conjunto Python focado:

```text
python -m unittest tests.test_plate_qt_lifecycle_probe tests.test_plate_creation_session tests.test_plate_task_panel_lifecycle tests.test_plate_interactive tests.test_draft_plate_polygon_tool tests.test_draft_plate_rectangle_tool tests.test_plate_panel_shortcuts tests.test_draft_native_member_tool tests.test_plate_command tests.test_point_input tests.test_plate_rectangle_tracker
```

**200 aprovados, zero falhas/erros/skips.** Inclui quatro testes offline da
classificação e interrupção do probe. Esses testes não substituem GUI real.
A suíte completa não foi repetida. Comparação 1.1.4, D–G, criação seguida de
Line, Membro/Rectangle, troca de vista/documento e callbacks pendentes ficaram
sem nova validação GUI por causa da interrupção nativa; resultados anteriores
do fechamento não são apresentados como novas aprovações.

`python scripts/check_project.py`: aprovado (XML, versões, catálogos, sintaxe e
arquivos essenciais). `git diff --check`: aprovado; somente avisos preexistentes
de conversão LF/CRLF. Os cinco arquivos desta rodada também foram conferidos
quanto a whitespace. Evidências locais ignoradas em
`test-results/plate_qt_lifecycle/`: manifests, logs, eventos, resultados parciais,
`evidence_audit.json` e `diagnosis_delta.json`. A auditoria posterior dos logs
preserva os results originais, que antecedem a detecção de assinaturas nativas.
Hashes dos cinco arquivos instalados monitorados permanecem iguais.

Arquivos criados nesta rodada:

- `scripts/diagnose_plate_qt_lifecycle.py`;
- `tests/manual_plate_qt_lifecycle.py`;
- `tests/test_plate_qt_lifecycle_probe.py`;
- `Documentation/STRUCTURAL_PLATE_0_7_0_QT_LIFECYCLE_DIAGNOSIS.md`.

Acrescentada nota em `Documentation/STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md`,
que já era untracked. Nenhum arquivo Python preexistente foi alterado,
inclusive produção. Os 95 arquivos Gusset protegidos têm hashes inalterados.
Branch/HEAD preservados, index vazio; alterações acumuladas anteriores continuam
locais. Nenhum add/commit/push/tag/release. `git diff --stat` continua descrevendo
somente o incremento tracked anterior: 13 arquivos, 1.171 inserções e 159 exclusões
(não inclui os untracked). Status completo preservado em
`test-results/plate_qt_lifecycle/final_git_status.txt`. Logs, perfis isolados,
snapshots, dumps e os estudos Gusset ficam fora de qualquer proposta de staging.

## Próximo gate

**NO-GO.** Não há correção fundamentada eliminando a reprodução. Antes de repetir
o gate final, é necessário esclarecer o contrato da factory/invalidação e a
ocorrência nativa em um ambiente de diagnóstico seguro. Comparar 1.1.4 e completar
D–G permanece pendente. Uma aprovação futura do gate não autoriza commit ou release
automaticamente. Não se recomenda novo roteiro manual enquanto persistir essa
ocorrência nativa; a sequência mínima documentada é A: Line → Esc → Line.
