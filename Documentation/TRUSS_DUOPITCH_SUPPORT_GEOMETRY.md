# Duas Águas — alturas de extremidade e referência superior

Implementação local em `develop/0.7.0`, sobre HEAD `14449d2`. Pronta para
validação manual do usuário; sem staging, commit, push ou alteração de versão.

## Propriedades e interface

| Propriedade | Significado / padrão compatível |
| --- | --- |
| `LeftEndHeight` | Altura nominal esquerda, perpendicular ao banzo inferior; 0 mm. |
| `RightEndHeight` | Altura nominal direita; 0 mm. |
| `LinkEndHeights` | Vincula as alturas; esquerda controla direita; inicialmente `True`. |
| `ReferenceAlignment` | `BottomChord` (padrão) ou `TopChordSupports`. |
| `NominalSpan` | Vão nominal calculado do banzo inferior; somente leitura. |

`Height` mantém o significado: altura da cumeeira sobre o eixo nominal inferior.
`ApexPosition` mantém a fração do vão nominal. Alturas são medidas no referencial
nominal da treliça, inclusive quando a linha fornecida é inclinada.

`Span` continua registrando o comprimento da linha fornecida. No alinhamento
inferior ele é também o vão nominal. No superior, por decisão explícita do
usuário nesta tarefa, o vão nominal pode ser menor. O painel mostra
“Distância entre apoios” nesse modo e o resultado calculado na seção Referência.
Os controles adicionais aparecem somente em Duas Águas. A prévia esquemática
mostra as duas alturas e a linha física superior calculada, ou o banzo inferior.

## Definição geométrica

Sejam `D = |P1-P0|`, `S` o vão nominal, `H` a altura na cumeeira,
`a` sua posição proporcional e `hL`, `hR` as alturas das extremidades.

O banzo inferior é `B(x) = (x,0,0)`. O superior é linear por ramo:

```text
T(x) = (x, hL + (H-hL)x/(aS), 0)                 para 0 <= x <= aS
T(x) = (x, hR + (H-hR)(S-x)/((1-a)S), 0)         para aS <= x <= S

mL = (H-hL)/(aS)
mR = (hR-H)/((1-a)S)
```

Exige-se `D,H > 0`, `0 < a < 1`, `0 <= hL,hR < H`, com valores finitos.
Assim os dois ramos sobem até a cumeeira; inclinação nula ou invertida é rejeitada.
Comprimentos menores que a tolerância geométrica do grafo continuam inválidos.

O alinhamento **Banzo inferior** usa exatamente `S=D` e o referencial anterior.

No modo **Topo do banzo superior nos apoios**, `c` é o extremo superior da seção
física na normal ascendente do banzo, relativo ao seu eixo nominal de inserção.
Ele é calculado pelo máximo entre componentes, considerando:

- contornos de segmentos e arcos com extremos analíticos;
- perfil e modo Detailed/Simplified;
- ponto de inserção, rotação da seção, reflexões e transformações;
- translação dos componentes no frame rotacionado da composição.

Interconectores não definem o topo do próprio banzo. O deslocamento `c` não usa
dimensões nominais aproximadas nem uma bounding box rotacionada.

A superfície tangente superior extrudada encontra os planos de estação `x=0`
e `x=S` nas cotas:

```text
qL = hL + c sqrt(1+mL²)
qR = hR + c sqrt(1+mR²)
QL = (0,qL,0)
QR = (S,qR,0)

S² + (qR-qL)² = D²
phi = -atan2(qR-qL,S)
```

O resolvedor escolhe a maior raiz positiva admissível, ou informa ausência de
solução. O fator `sqrt(1+m²)` decorre da interseção da face com o plano de apoio;
usar apenas a projeção vertical `c/sqrt(1+m²)` seria incorreto.

Se `(O,X,Y,Z)` é o referencial bruto da linha:

```text
X' = cos(phi) X + sin(phi) Y
Y' = -sin(phi) X + cos(phi) Y
O' = P0 - qL Y'
p_global = O' + x X' + y Y' + z Z
```

Essa transformação rígida leva `QL` a `P0` e `QR` a `P1`, sem shear. Mantém
alturas, posição proporcional da cumeeira e critérios de distribuição. Listas
de espaçamentos fornecidas na linha são escaladas proporcionalmente para `S`;
o driver por espaçamento/ângulo continua resolvendo o envelope nominal efetivo.
O `Placement` do owner continua no referencial **bruto**. Membros, Gussets e
planos de fitting usam o referencial físico separado, aplicado uma única vez.

Antes de aplicar um lote, o OCC secciona os sólidos candidatos finais nos dois
planos de apoio e verifica a cota superior real. Um corte que retire essa
superfície, ou um perfil que não alcance a estação dentro do ramo disponível,
impede a aplicação com diagnóstico; o último estado aplicado é preservado.

## Topologias e compatibilidade

Altura zero conserva o nó compartilhado e as identidades antigas. Com altura
positiva, o nó inferior mantém `N_S_START` / `N_S_END`, surge um nó superior
separado e um fechamento `END_POST`. Warren, Warren com montantes, Pratt, Howe
e X incluem suas diagonais nos painéis de extremidade que passam a ter altura.
Fink, Fan, King Post, Queen Post e Custom mantêm os padrões existentes, com
fechamentos nos apoios. K continua disponível somente em Paralela.

Em Custom, a migração retargeta apenas os banzos superiores; conserva os nós
inferiores, a alma e as configurações materializadas. O retorno a zero reúne
os nós e remove somente fechamentos de apoio colapsados. Não há novo schema
de topologia nem aumento de `SchemaVersion`.

Inicialização e restauração adicionam propriedades ausentes com alturas zero,
vínculo ativo e referência inferior. Não materializam geometria adicional em
documentos antigos. `AppliedState`, registries e grupos seguem seus contratos.
Alterações pela Property View regeneram também as transições zero/positivo,
sem recompute recursivo nem transação aninhada. A aplicação automática prepara
todo o lote, conserva os objetos antigos até a validação e restaura propriedades,
grupos, Shapes e caches se uma aplicação falhar antes da remoção final.

Intenções de ligação existentes não são descartadas silenciosamente na
separação dos apoios. Uma ligação criada exclusivamente no nó superior impede
reuni-lo ao inferior se isso eliminaria seu nó; deve ser reassociada no editor.
Overrides manuais continuam sujeitos às proteções existentes.

A implementação aprovada de cópia via Draft Move não foi alterada. A mudança
usa suas mesmas identidades e registries. StructuralPlate, estudos Gusset e
experimentos anteriores permanecem fora do escopo.

## Limitações verificadas

O alinhamento superior é o **envelope físico superior em projeção longitudinal**
através da largura do perfil/conjunto. A linha define a altura do plano tangente
superior; não define a largura nem a área de contato de um pilar. Em composições
espaçadas, ou seções assimétricas rotacionadas, pode haver vazio exatamente no
eixo transversal central. Não se anuncia contato material pontual nesse eixo.
O máximo físico sobre os componentes é verificado, inclusive em DoubleAngle,
DoubleChannelOutward e SpacedPair.

Também foram comprovadas configurações inviáveis: linha curta demais para as
alturas/seção; seção grande demais para alcançar o plano do apoio antes da
cumeeira; topo abaixo da inserção; cortes que removam o topo previsto. Esses
casos são rejeitados somente na configuração afetada.

Limitação **preexistente**, reproduzida com o builder de `14449d2`: Duas Águas
com DoubleChannelOutward, espaçamento 160 mm, rotação de role -90° e Battens
pode falhar na cumeeira com “Comprimentos dos componentes devem corresponder
ao comprimento nominal”. O fitting produz comprimentos efetivos distintos.
Não foi corrigida nesta rodada. Interconectores com rotação 0° passaram nos
gates com Gusset, alinhamento e persistência. Diagnóstico preservado em
`test-results/truss-duopitch/check_connector_baseline.py`.

## Validação automatizada

Comandos executados na raiz, sem descoberta da suíte completa:

```powershell
python -m unittest tests.test_truss_support_alignment tests.test_truss_duopitch_heights tests.test_truss_duopitch_custom tests.test_truss_duopitch_ui tests.test_truss_regeneration_rollback tests.test_truss_core tests.test_truss_qa tests.test_truss_c2 tests.test_truss_c2_editor tests.test_truss_c2_custom_review tests.test_truss_c2_refinements tests.test_truss_c2_references tests.test_truss_assemblies tests.test_truss_interconnectors tests.test_truss_manual_fixes tests.test_truss_copy tests.test_truss_task_panel tests.test_gusset_c6f tests.test_gusset_c6k tests.test_gusset_c6p tests.test_gusset_attachment_c6e tests.test_gusset_plate_document_c6b tests.test_gusset_contact_c6h
python scripts/run_truss_duopitch_gate.py
python scripts/check_project.py
git diff --check
```

Resultado Python: 276 testes focados aprovados. `check_project.py` e
`git diff --check` aprovados; o Git emite apenas o aviso preexistente de
normalização LF/CRLF em `init_gui.py`.

O gate usa FreeCAD **1.1.4** em processo oculto com perfil isolado. Valida sólidos
e seções OCC, todos os 10 padrões de Duas Águas, alturas zero/iguais/diferentes,
edição pela Property View, Custom, falha injetada com rollback, Undo/Redo,
famílias de seção e inserções, linha horizontal/inclinada, Gussets, perfis
compostos e interconectores compatíveis, snapshot/associativo com alteração da
fonte, cópia independente e salvar/reabrir. Verifica ainda o painel Qt real e
produz `panel.png` e `schematic.png`. Os diretórios por execução contêm
manifest com hashes das fontes, logs, `checks.json`, `result.json` e FCStd.

Tentativas iniciais identificaram diferença irrelevante nos últimos bits de
volume após salvar/reabrir (comparador corrigido com tolerância) e a limitação
preexistente dos interconectores descrita acima. Não se atribuem esses casos
a avisos nativos do Draft. A execução final é registrada no resultado do gate.
Execução final: `test-results/truss-duopitch/1791715210826605900/`, **123
verificações aprovadas**, exit code 0, sem erros/avisos de recompute no log final
e stderr vazio. Captura do painel e prévia inspecionadas visualmente; cotas sem
recorte nas bordas. `duopitch.fcstd` fica disponível para revisão manual.
Avisos nativos conhecidos de recompute do Draft não foram reinvestigados.
Esta validação automatizada no runtime real não é teste manual do usuário.

## Roteiro manual — FreeCAD 1.1.4

1. Abrir um documento anterior: conferir alturas zero, alinhamento inferior e
   geometria anterior. Criar Duas Águas e repetir com Warren, Pratt, Howe e Fink.
2. Definir alturas 180/300 mm, desligar o vínculo e conferir fechamentos e
   cumeeira. Ligar o vínculo; conferir direita igual à esquerda e desabilitada.
3. Alternar alinhamentos em uma linha horizontal e outra inclinada. Comparar
   a linha com o envelope superior físico, `Span` e `NominalSpan`; variar perfil,
   rotação e inserção e conferir a prévia e os sólidos.
4. Alterar alturas pela Property View, inclusive zero/positivo/zero. Repetir
   em Custom e com Gusset interior; confirmar que ligações não desaparecem.
5. Alterar uma linha associativa; conferir que a snapshot não muda. Fazer
   Undo/Redo, salvar/reabrir e copiar via Draft Move; editar só a cópia.
6. Conferir visualmente grupos, Gussets e interconectores compatíveis, e testar
   rejeição de altura maior/igual à cumeeira, linha curta ou corte sem apoio.

## Arquivos desta rodada

- `freecad/SteelStructures/truss.py`: propriedades/migração, entrada bruta,
  atualização paramétrica e rollback automático.
- `freecad/SteelStructures/trusses/{models,envelope,drivers,patterns,editing,realization}.py`:
  envelope, topologias e integração do referencial físico.
- Novos `trusses/support_alignment.py` e `support_alignment_freecad.py`:
  equações analíticas e verificação OCC.
- `interactive/{truss_controller,truss_task_panel,truss_preview}.py`:
  controles e prévia incremental.
- Novos testes `test_truss_{duopitch_heights,duopitch_custom,duopitch_ui,support_alignment,regeneration_rollback}.py`;
  adaptação de fixture em `test_truss_manual_fixes.py`.
- Novo `tests/manual_freecad_truss_duopitch.py` e
  `scripts/run_truss_duopitch_gate.py`.
- Este relatório; evidências isoladas em `test-results/truss-duopitch/`.

`init_gui.py`, parte do diff de `truss.py`/`test_truss_manual_fixes.py` e vários
documentos/scripts/fixtures não rastreados já estavam modificados antes desta
rodada. Foram preservados, incluindo a correção Draft Move aprovada e todos os
estudos Gusset. HEAD continua `14449d2`; nada foi adicionado ao index.
