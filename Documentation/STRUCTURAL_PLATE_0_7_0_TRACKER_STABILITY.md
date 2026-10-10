# StructuralPlate Rectangle — comparação isolada do tracker Draft

Registro histórico preservado, anterior à unificação. Para o resultado atual,
consulte o [fechamento técnico](STRUCTURAL_PLATE_0_7_0_TECHNICAL_CLOSURE.md).

Data: 09/10/2026. Branch `develop/0.7.0`. Baseline commitada `9ad0446`.

**Resultado: GO limitado ao protótipo que use o tracker corrigido.** Foram aprovados 800 ciclos em 40 processos, sem novo dump. A causa do crash original permanece inconclusiva; não há liberação para release nem para o caminho original com contagem 50.

Esta etapa investiga somente estabilidade. Nenhuma funcionalidade, arquitetura, propriedade persistente ou interface da StructuralPlate foi alterada. Polígono e unificação continuam fora do escopo.

## 1. Inconsistência confirmada

Nas instalações portáteis 1.1.4 e 1.1.3, o construtor `rectangleTracker` em `Mod/Draft/draftguitools/gui_trackers.py:332` faz:

```python
self.coords.point.setValues(0, 50, [[0, 0, 0],
                                  [2, 0, 0],
                                  [2, 2, 0],
                                  [0, 2, 0],
                                  [0, 0, 0]])
```

São **cinco vetores**, cada um com três componentes: 15 escalares no total. O último vetor repete o primeiro para fechar o retângulo. O `SoLineSet` imediatamente anterior também informa cinco vértices.

A [assinatura oficial Coin](https://www.coin3d.org/coin/classSoMFVec3f.html) é `setValues(start, num, xyz[][3])` ou sua sobrecarga para `SbVec3f*`. `num` é o número de vetores a copiar da fonte a partir de seu índice zero. `start` é o índice de destino. **50 não é uma reserva de capacidade nem um número de componentes escalares.** A implementação [SoMFVec3f.cpp](https://raw.githubusercontent.com/coin3d/coin/master/src/fields/SoMFVec3f.cpp) expande o destino e lê `xyz[i]` enquanto `i < numarg`. Essa fonte upstream explica o contrato, sem alegar identidade byte a byte com o binário instalado.

O wrapper Python instalado `bin/Lib/site-packages/pivy/coin.py:21999` infere `len(points)` nas sobrecargas sem contagem explícita, mas encaminha diretamente os argumentos da chamada com contagem. A inspeção anterior de um campo Coin confirmou `getNum()=50` para essa chamada e `getNum()=5` para a chamada com quantidade inferida. Não é uma chamada que apenas reserve memória no destino: ela pede a cópia de 50 vetores de uma fonte Python que fornece cinco.

Há fundamento concreto para leitura além dos elementos fornecidos. O tamanho e a alocação exata do buffer nativo gerado pelo binding não foram medidos com instrumentação de heap; a corrupção original não é considerada causalmente comprovada apenas por esse contrato inválido.

Dentro da mesma classe existe outra chamada `setValues`, em `f.coordIndex.setValues([0, 1, 2, 3])`, somente no ramo `face=True`. Ela usa quantidade inferida, trata índices de face e não tem a discrepância 50/5. Os métodos de origem/update usam `set1Value` nos índices 0–4, coerentes com cinco pontos. A análise AST delimita a classe e encontra exatamente uma chamada `self.coords.point.setValues`.

Os arquivos `gui_trackers.py` completos são idênticos nas duas instalações, SHA256 `14fb6492c27b524603d8f2e5a70dc8268f77155b2ac1e82778ee2fdc349081c9`. Há outra discrepância no `polygonTracker` regular Draft; ela foi mantida intacta neste experimento para não acrescentar variável ao comparativo. Não se trata da aquisição Polilinha prevista para o futuro Polígono Steel.

## 2. Correção experimental e isolamento

A única mudança na variante é **`50` → `5` nessa chamada do construtor Rectangle**. O runner identifica a expressão por AST e substitui somente esses bytes. O patch e os hashes estão em cada diretório de lote. Não há refatoração, mudança de métodos de preview ou ajuste de lifecycle.

Para cada lote, o runner grava uma cópia original intacta e uma corrigida em `test-results/plate_tracker_stability/<lote>/original/gui_trackers.py` e `variant/gui_trackers.py`. Os dois controles usam o mesmo mecanismo de importação `spec_from_file_location`, antes da ativação de Draft/Steel. Portanto, a ordem de importação e a instrumentação são equivalentes; o conteúdo 50/5 é a variável experimental.

O probe exige que `draftguitools.gui_trackers`, `gui_rectangles` e Steel ainda não tenham sido importados. Registra o módulo tanto em `sys.modules` quanto no atributo do pacote. Verifica em runtime:

- Caminho efetivo `__file__`, hash e `rectangleTracker.__init__.__code__.co_filename`.
- Identidade do módulo usado por `gui_rectangles.trackers` e, quando aplicável, `pilot.gui_trackers`.
- Identidade da classe realmente instanciada por `tool.rect`.
- Quantidade real de coordenadas em cada sessão: 50 nos controles e cinco nos corrigidos.

O override termina com o processo descartável. Não se modifica Draft globalmente em uma sessão do usuário. O probe desativa gravação de bytecode; as fontes instaladas `gui_trackers.py` e `pivy/coin.py`, arquivos do pacote Steel e documentos Gusset têm hashes de preservação comparados após cada processo. Não se alteram Program Files, instalações portáteis nem bibliotecas compartilhadas para aplicar a correção.

## 3. Método e cobertura

Cada processo usa perfil próprio derivado da mesma configuração inicial, diretório de módulos vazio, autoload adicional desativado e binário `bin/freecad.exe` direto. A instância pessoal do usuário permanece separada. As configurações são intercaladas A/B/C/D/E em cada rodada, em vez de executar todas as originais antes das corrigidas.

| Cenário | Ferramenta | Tracker | Plano |
| --- | --- | --- | --- |
| A | Rectangle Draft nativo | Original | WP atual |
| B | Rectangle Draft nativo | Corrigido | WP atual |
| C | StructuralPlate Rectangle | Original | WP atual |
| D | StructuralPlate Rectangle | Corrigido | WP atual |
| E | StructuralPlate Rectangle | Corrigido | Face planar inclinada / WP temporário |

Um smoke test precede as séries. A série principal usa **cinco processos por configuração e 20 ciclos por processo**, totalizando 100 ciclos/configuração. No 1.1.3, repetem-se os cenários corrigidos B/D/E, após aprovação da série 1.1.4.

Cada bloco de quatro ciclos contém:

1. Movimento real Qt → QuarterWidget → callback Coin; Esc sem P1.
2. Movimento, P1 por clique, preview no canto oposto e Esc real.
3. Movimento, P1, preview e Cancelar pelo painel real.
4. Movimento, P1, preview e P2 por clique, criando o objeto final.

Uma subclass apenas registra os tipos de eventos antes de delegar ao método original. Não injeta coordenadas por `numericInput` nem chama `action` artificialmente para simular os eventos. Cada sessão registra os marcos antes/depois da aquisição, criação e encerramento, com PID, timestamp e fsync. O processo precisa terminar por `QApplication.quit` e exit 0; o runner não trata retorno Python positivo como substituto do exit do processo.

Após cada ciclo, verifica comando ativo encerrado, TaskPanel fechado, tracker Rectangle e tracker de plano fora da cena, filas ToDo vazias, nenhum callback sobrevivendo a um movimento posterior, e exatamente um objeto válido quando houve criação. No piloto, verifica Shape/volume/ContourData, identidade de `last_created`, ausência de Draft intermediário, estado terminal, callback/observador retirados e restauração de parâmetros, `_stored` e histórico do WP. O objeto criado é removido **após** a verificação, para o próximo ciclo partir do mesmo documento limpo. Cada processo fecha seu documento e encerra completamente.

O plano temporário E passa uma referência real a uma face de caixa inclinada ao mesmo caminho `Activated(plane_face=...)`. Não avalia a interação humana de pré-seleção. Esta automação não substitui revisão visual/manual. Não cobre numérico/Enter, snaps e constraints individualmente, troca de vista/ferramenta, documentos persistidos ou todos os fluxos da futura unificação.

## 4. Interpretação e solução definitiva

Separar quatro questões:

- **Inconsistência comprovada:** quantidade 50 com fonte de cinco vetores, sem correspondência ao contrato de cópia.
- **Mecanismo provável:** leitura além dos elementos disponíveis no buffer fonte do binding; compatível com a AV em `SoMFVec3f::setValues` do dump anterior.
- **Causa da falha original:** permanece sem atribuição definitiva. O dump anterior também contém detecção de heap durante unwind/liberação em runtime/PySide; esta série não captura a operação original que corrompeu o heap.
- **Risco residual:** ausência de crashes em uma série finita não elimina intermitência, nem demonstra superioridade estatística da variante quando o controle também passa. Os ciclos dentro de um processo compartilham estado; não são 100 amostras independentes.

| Opção definitiva | Avaliação |
| --- | --- |
| Corrigir Draft na origem | Preferível: alteração mínima no componente que contém a inconsistência, beneficia todos os consumidores. Exige distribuição/validação de uma dependência corrigida; não foi enviado issue/PR nem alterada instalação nesta etapa. |
| Subclass própria apenas do tracker Rectangle | Possível mitigação local se a dependência corrigida não estiver disponível. Deve preservar os métodos nativos e substituir somente a inicialização de cinco coordenadas; chamar o `super().__init__` problemático e corrigir depois não evita a leitura original. Como o piloto instancia o tracker diretamente, exigiria um ponto de criação localizado no adaptador, a avaliar numa tarefa posterior. Há custo de acompanhar mudanças do construtor Draft. |
| Evitar todo o preview nativo | Mais arriscado e desnecessário diante de uma correção de contagem; não se recomenda um motor novo. |
| Monkeypatch global permanente | Não recomendado: afeta outras ferramentas e consumidores, pode deixar referências antigas e amplia o escopo da mitigação. O overlay completo desta investigação não deve ser distribuído como solução Steel. |

Decisão, números finais, provenance e estado Git são consolidados abaixo após as séries.

## 5. Resultados finais

**GO limitado para prosseguir com o protótipo usando o tracker corrigido em ambiente controlado.** Não é aprovação de release, nem liberação do piloto atual com o tracker original. Atribuição da causa do crash original: **INCONCLUSIVA**. Não há base para afirmar que a corrupção foi eliminada ou que o lifecycle do piloto era sua causa.

| Versão | Cenário | Processos | Ciclos verificados | Exit codes | Novos dumps |
| --- | --- | ---: | ---: | --- | ---: |
| 1.1.4 | A | 5 | 100 | 0 em todos | 0 |
| 1.1.4 | B | 5 | 100 | 0 em todos | 0 |
| 1.1.4 | C | 5 | 100 | 0 em todos | 0 |
| 1.1.4 | D | 5 | 100 | 0 em todos | 0 |
| 1.1.4 | E | 5 | 100 | 0 em todos | 0 |
| 1.1.3 | B | 5 | 100 | 0 em todos | 0 |
| 1.1.3 | D | 5 | 100 | 0 em todos | 0 |
| 1.1.3 | E | 5 | 100 | 0 em todos | 0 |

Séries principais: **800 ciclos em 40 processos**, com 200 criações, 200 Esc sem P1, 200 Esc com preview e 200 Cancelar com preview. Smoke anterior: mais 20 ciclos em cinco processos no 1.1.4, contabilizados separadamente. Não houve exclusão de execução CAD nem falha de instrumentação nas séries registradas. A primeira preparação parou numa assert AST antes de iniciar qualquer FreeCAD: a busca inicial também incluía a chamada válida de índices da face, depois delimitada ao campo de coordenadas.

Todos os 40 processos tiveram fault.log vazio, fases finais registradas e hashes de preservação válidos. A varredura dos logs não encontrou traceback, erro de criação/teardown ou access violation. Há avisos Qt de tradução `QString::arg: Argument missing` nos hints Draft; eles foram mantidos como evidência e não atribuídos ao heap. O dump antigo 7956 permanece separado; nenhum dump novo foi detectado pelo runner durante as séries.

### Processos e encerramento

| Versão | Cenário | Rodada | PID | Ciclos | Exit | Duração (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1.1.4 | A | 1 | 22096 | 20 | 0 | 10.137 |
| 1.1.4 | B | 1 | 13296 | 20 | 0 | 12.402 |
| 1.1.4 | C | 1 | 30272 | 20 | 0 | 12.472 |
| 1.1.4 | D | 1 | 23904 | 20 | 0 | 12.586 |
| 1.1.4 | E | 1 | 7860 | 20 | 0 | 14.42 |
| 1.1.4 | A | 2 | 30960 | 20 | 0 | 12.39 |
| 1.1.4 | B | 2 | 8496 | 20 | 0 | 12.53 |
| 1.1.4 | C | 2 | 9772 | 20 | 0 | 11.914 |
| 1.1.4 | D | 2 | 29808 | 20 | 0 | 10.487 |
| 1.1.4 | E | 2 | 20828 | 20 | 0 | 13.344 |
| 1.1.4 | A | 3 | 31668 | 20 | 0 | 12.208 |
| 1.1.4 | B | 3 | 9900 | 20 | 0 | 9.917 |
| 1.1.4 | C | 3 | 2644 | 20 | 0 | 11.528 |
| 1.1.4 | D | 3 | 6924 | 20 | 0 | 11.641 |
| 1.1.4 | E | 3 | 24768 | 20 | 0 | 13.67 |
| 1.1.4 | A | 4 | 18608 | 20 | 0 | 12.388 |
| 1.1.4 | B | 4 | 15264 | 20 | 0 | 12.017 |
| 1.1.4 | C | 4 | 20804 | 20 | 0 | 11.894 |
| 1.1.4 | D | 4 | 18980 | 20 | 0 | 11.887 |
| 1.1.4 | E | 4 | 29844 | 20 | 0 | 13.553 |
| 1.1.4 | A | 5 | 3996 | 20 | 0 | 12.581 |
| 1.1.4 | B | 5 | 9012 | 20 | 0 | 12.293 |
| 1.1.4 | C | 5 | 5832 | 20 | 0 | 11.91 |
| 1.1.4 | D | 5 | 16332 | 20 | 0 | 11.962 |
| 1.1.4 | E | 5 | 7860 | 20 | 0 | 14.107 |
| 1.1.3 | B | 1 | 10840 | 20 | 0 | 10.536 |
| 1.1.3 | D | 1 | 9964 | 20 | 0 | 8.067 |
| 1.1.3 | E | 1 | 20848 | 20 | 0 | 8.506 |
| 1.1.3 | B | 2 | 24420 | 20 | 0 | 9.546 |
| 1.1.3 | D | 2 | 3428 | 20 | 0 | 8.122 |
| 1.1.3 | E | 2 | 15436 | 20 | 0 | 8.533 |
| 1.1.3 | B | 3 | 30992 | 20 | 0 | 9.662 |
| 1.1.3 | D | 3 | 27260 | 20 | 0 | 8.113 |
| 1.1.3 | E | 3 | 29484 | 20 | 0 | 8.669 |
| 1.1.3 | B | 4 | 8732 | 20 | 0 | 9.63 |
| 1.1.3 | D | 4 | 31572 | 20 | 0 | 8.303 |
| 1.1.3 | E | 4 | 28992 | 20 | 0 | 12.636 |
| 1.1.3 | B | 5 | 20776 | 20 | 0 | 10.158 |
| 1.1.3 | D | 5 | 30652 | 20 | 0 | 8.171 |
| 1.1.3 | E | 5 | 19796 | 20 | 0 | 8.63 |

### Provenance dos lotes

- `C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures\test-results\plate_tracker_stability\1791586083696779200_1.1.4`; perfil inicial SHA256 `73f4433fbc8d76ccb9139e7eb1153c5c7a575950636fc9d43dbe3840ea0f2131`.
- `C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures\test-results\plate_tracker_stability\1791586619251986000_1.1.3`; perfil inicial SHA256 `73f4433fbc8d76ccb9139e7eb1153c5c7a575950636fc9d43dbe3840ea0f2131`.


Hash da variante corrigida em ambas as versões: `d37386546add4410f9c47f7768fade64ebba030389c9fc1e3ea606f17a1a8141`. Original preservado: `14fb6492c27b524603d8f2e5a70dc8268f77155b2ac1e82778ee2fdc349081c9`. Piloto preservado: `76e3fdd8fe41874490810b31634379dc528fd4ba88f24be91d0be9e98eaf5b07`.

Os resultados justificam manter a correção mínima como candidata e continuar apenas o protótipo com essa mitigação. Como A/C originais também passaram, não demonstram redução observada na taxa de falhas, nem identificam causalmente o crash anterior. Antes de futura integração em uso normal, decidir explicitamente entre dependência Draft corrigida e mitigação local restrita, testar essa implementação exata e validar manualmente. Qualquer nova falha nativa interrompe novamente o gate e exige preservação de PID/log/dump.

## 6. Reprodução, arquivos e verificações

```powershell
python scripts/diagnose_plate_tracker_stability.py --version 1.1.4 --processes 1 --cycles 4
python scripts/diagnose_plate_tracker_stability.py --version 1.1.4 --processes 5 --cycles 20
python scripts/diagnose_plate_tracker_stability.py --version 1.1.3 --scenarios BDE --processes 5 --cycles 20
```

Novos nesta etapa: `scripts/diagnose_plate_tracker_stability.py`, `tests/manual_plate_tracker_stability.py` e este relatório. Cópias de módulos, patch mínimo, manifests, resultados, logs por PID e `summary.json` ficam no diretório ignorado `test-results/plate_tracker_stability/`. Não se copia o módulo Draft para o pacote Steel distribuído. Os relatórios e probes anteriores foram preservados.

`python scripts/check_project.py`: aprovado. `git diff --check`: aprovado, com avisos de futura conversão LF/CRLF nos arquivos experimentais preexistentes. Não foi executada a suíte completa. B1, piloto, baseline funcional, fontes da instalação/Pivy e documentação Gusset foram preservados. Nenhuma migração, unificação, alteração funcional, git add, commit ou push.

### git diff --stat

O diff rastreado abaixo é preexistente; os três novos arquivos desta etapa estão não rastreados.

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
?? Documentation/STRUCTURAL_PLATE_0_7_0_TRACKER_STABILITY.md
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
?? scripts/diagnose_plate_tracker_stability.py
?? tests/manual_plate_heap_comparison.py
?? tests/manual_plate_heap_setvalues_probe.py
?? tests/manual_plate_numeric_input.py
?? tests/manual_plate_rectangle_lifecycle_gate.py
?? tests/manual_plate_rectangle_native.py
?? tests/manual_plate_tracker_stability.py
?? tests/manual_point_input_probe.py
?? tests/test_coordinate_input_widget.py
?? tests/test_draft_plate_rectangle_tool.py
?? tests/test_plate_rectangle_command.py
?? tests/test_point_input.py
```
