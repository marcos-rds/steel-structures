# U dobrado simples — Etapa B

Data: 20/10/2026. Branch `develop/0.7.0`; HEAD de referência preservado: `651c0bfd539b647839f4c5fb15e7d79dab443835`.

**GO para validação manual do usuário.** Os 125 perfis U simples estão habilitados nos consumidores compartilhados. A integração preserva o catálogo e o núcleo aprovados na Etapa A; não cria um pipeline de membros, pilares ou treliças exclusivo desta família. O fechamento técnico e qualquer publicação continuam dependentes da auditoria de fechamento e da aprovação funcional/visual do usuário.

Os relatórios de investigação e Etapa A foram lidos integralmente e confrontados com a implementação antes das alterações. As alterações locais anteriores foram complementadas, sem commit intermediário.

## Integração implementada

### Catálogo e Browser

- Série `u-simple-nbr-6355` habilitada em `SUPPORTED_CREATION_SERIES`, permitindo seleção dos 125 perfis pelo Browser, Criar Membro, Criar Pilar e perfis dos papéis de treliça.
- Identificação **U Dobrado Simples (U) — NBR 6355**, independente de U laminado e Ue. Designações brasileiras, aliases, fonte ABNT, propriedades tabeladas e rastreabilidade da A.2 preservados.
- Prévia técnica com quatro cotas/chamadas: `bw`, `bf`, `t`, `ri`. O contorno é recebido do núcleo real, não reconstruído a partir dos textos de cotas. As cotas usam as primitivas, estilos, cores e enquadramento existentes; as chamadas de espessura e raio ficam em lados verticalmente opostos da abertura, com texto além das pontas livres das mesas.
- Escala contínua existente reaproveitada para evitar o tamanho mínimo absoluto que reduziria excessivamente os perfis pequenos. Enquadramento compartilhado com Ue mantém a seção centralizada. O comportamento de Ue não foi alterado.
- Chamadas e tabela dimensional conservam `ri = 9,525 mm`; propriedades exibem `It` com três casas, incluindo `0,006 cm⁴`. Precisão de massa/área e identificação `Xg` seguem o padrão de Ue. Fonte informa Figura/Tabela A.2, edição 2012, aço sem revestimento e método linear normativo.
- Correção localizada da árvore: categorias provenientes de vários catálogos com o mesmo ID aparecem uma única vez. A biblioteca continua mantendo os registros de categoria por catálogo, enquanto a árvore apresenta um único **Aço Dobrado** com U simples e Ue. A duplicação foi identificada durante a inspeção visual e coberta por testes nos modos filtrado e consulta.

### Mini-preview e inserções

O esquema da família é próprio, com espessura uniforme e quatro curvas físicas de dobra, sem lábios. Usa o builder puro com dimensões representativas de apresentação e a conversão de segmentos já existente, evitando duplicar a construção de curvas. Essas dimensões não são dados normativos e nunca retornam ao modelo estrutural. Todas as bitolas compartilham o mesmo esquema, conforme o padrão de mini-preview por família.

Foram mapeadas as nove referências da Etapa A: `centroid`, `web_center`, `web_back`, `rear_top`, `rear_bottom`, `flange_top_tip`, `flange_bottom_tip`, `outer_top_mid`, `outer_bottom_mid`. Os labels reais são preservados. O widget existente conserva anéis azuis para pontos disponíveis e alvo vermelho para o selecionado, com hit testing e rotação já compartilhados pelas outras famílias.

O sentido do giro 2D corresponde à rotação longitudinal local aplicada pelo `Placement` do membro. O mini-preview mantém o enquadramento esquemático existente: não representa a posição global do membro. `RotationAngle` nas preferências e `Rotation` no objeto continuam usando seus contratos atuais.

### Membro, Pilar e Treliças

Nenhum código de produção dos criadores ou geradores precisou ser alterado. A liberação no catálogo fornece a definição tipada completa aos caminhos existentes de controles, eixo Draft, inserção, offsets, extrusão, orientação, propriedades e recompute.

Os perfis estão disponíveis para banzos, diagonais, montantes e fechamentos. Perfis simples, par espaçado e os dois U duplos usam as composições e transformações existentes; não há modalidade nova. As configurações de rotação, inserção e espaçamento continuam pertencendo aos mesmos contratos de papéis e componentes.

Aplicar, OK, Cancelar e Undo/Redo continuam nos controladores e sessão compartilhados do TaskPanel/Editor de Treliças. A integração não altera edição topológica, fitting ou mecanismos de cópia.

## Persistência e dados normativos

Não houve mudança de propriedades persistentes, versão de schema, serialização de membros/treliças ou migração. O núcleo e os nove IDs/labels da Etapa A permanecem intactos. Testes verificam a preservação das inserções nos controles, preferências, papéis de treliça, cópia e FCStd, sem substituição de referências válidas por Centroide.

Detailed e Simplified continuam disponíveis. A origem/referências detalhadas permanecem estáveis ao remover os raios da representação, conforme o contrato aprovado na Etapa A.

O catálogo e seu snapshot não foram modificados nesta etapa. A divergência da expressão impressa de área continua documentada na Etapa A; nenhum valor tabelado foi recalculado ou ajustado para coincidir com a BRep. Massa linear e área normativas dos membros permanecem independentes do volume e da massa física medidos na treliça.

## Arquivos da Etapa B

Modificados em produção, sob `freecad/SteelStructures/`:

| Arquivo | Alteração |
| --- | --- |
| `profile_catalog.py` | Liberação da série no catálogo compartilhado |
| `profiles/presentation.py` | Quatro dimensões, precisão de raio/It, massa/área/Xg e fonte A.2 |
| `profiles/preview_geometry.py` | Esquema próprio e nove hotspots da família |
| `interactive/profile_browser_preview.py` | Cotagem técnica, marcador e enquadramento para U simples |
| `interactive/profile_browser.py` | Um nó visual por categoria compartilhada |

Testes e documentação:

- Novo `tests/test_simple_u_stage_b.py`: nove testes focados, incluindo loops sobre todas as 125 bitolas, hit testing/rotação, preferências, serialização e composições.
- Novo `tests/manual_simple_u_stage_b_validation.py`: gate real Qt/FreeCAD de criação, interface, sessão, cópia e persistência.
- Novo `scripts/run_simple_u_stage_b_gate.py`: launcher de FreeCAD 1.1.4 com preferências isoladas por tema, manifest de hashes, capturas e logs. Não altera as preferências do usuário nem encerra instâncias preexistentes.
- `tests/test_cold_formed_simple_u.py`: substitui a fronteira temporária de bloqueio da Etapa A pela elegibilidade compartilhada, mantendo os testes normativos e geométricos.
- `tests/test_ue_stage2.py` e `tests/test_profile_catalog_v2.py`: expectativas de duas séries dobradas e 3.588 perfis elegíveis; mantém verificação explícita dos 85 Ue e contagens das famílias anteriores.
- Este relatório.

Os arquivos de núcleo, validador, catálogo, gerador e testes criados/modificados na Etapa A continuam no mesmo estado de implementação aprovado, exceto a expectativa temporária de elegibilidade no teste da nova família. Não foram alterados StructuralPlate, Gussets, Recortar/Ajustar Membro, núcleo Ue ou ferramentas de edição topológica. Arquivos experimentais, relatórios e FCStd originais foram preservados.

## Testes Python e verificadores

Execução final direcionada:

```powershell
python -m unittest tests.test_simple_u_stage_b tests.test_cold_formed_simple_u tests.test_cold_formed_ue tests.test_cold_formed_intersections tests.test_ue_stage2 tests.test_section_geometry tests.test_section_geometry_mode tests.test_section_insertion tests.test_section_orientation_preview tests.test_profile_catalog_v2 tests.test_profile_catalog_stage2b tests.test_profile_models tests.test_normative_profile_metadata tests.test_freecad_section_geometry tests.test_profile_browser tests.test_profile_search tests.test_profile_presentation tests.test_profile_options_browser_integration tests.test_creation_preferences tests.test_column_task_panel tests.test_member_creation_types tests.test_member_axis_creation tests.test_member_orientation tests.test_truss_assemblies tests.test_truss_edit_session tests.test_truss_task_panel tests.test_truss_physical_mass
```

**431 testes passaram**, sem falhas ou skips, em 14,054 s. Incluem contratos controlados/stubs; a validação nativa complementar é apresentada abaixo. Uma revisão independente também executou subconjuntos de regressão e não identificou bloqueios. A suíte completa foi reservada para a auditoria de fechamento.

Também passaram:

```powershell
python scripts/check_project.py
python scripts/generate_nbr6355_simple_u_catalog.py --check
git diff --check
```

## Validação nativa e inspeção visual

Gates executados com FreeCAD 1.1.4, Python 3.11, Qt e Part/OCC reais, em processos e perfis de preferência isolados:

```powershell
python scripts/run_simple_u_stage_b_gate.py --theme Classic
python scripts/run_simple_u_stage_b_gate.py --theme 'FreeCAD Dark'
python scripts/run_simple_u_stage_b_gate.py --theme OpenDark
```

O launcher usa as preference packs instaladas e o OpenDark local, registrando os caminhos no manifest de cada execução. As capturas foram inspecionadas para legibilidade, cotas, hotspots e Task View; automação e inspeção de capturas não substituem a aprovação manual do usuário.

Cobertura do gate:

- Quatro bitolas representativas: `U 50 × 25 × 1,20`, `U 150 × 50 × 3,00`, `U 250 × 100 × 6,35` e `U 300 × 100 × 8,00`.
- Browser em larguras 760/1.100 px, abas de dimensões/propriedades/fonte, precisão de `ri` e `It`, árvore sem duplicação. Quatro labels de cotas dentro do viewport e sem interseção entre suas caixas, usando `deviceTransform` para textos de tamanho fixo em pixels.
- Clique Qt real nos 36 hotspots (quatro bitolas × nove referências), com roll de 37°.
- Criação pelos controles e controlador genéricos em X/Y/Z/inclinado, Detailed/Simplified, nove inserções em Membro/Pilar, eixo Draft vinculado e recompute após edição da linha.
- Preview nativo Draft reativo à rotação, cancelamento sem preview/objetos órfãos; cópia Draft de membro e edição de inserção/rotação/modo com Undo/Redo.
- Treliça com papéis U simples, U duplo inward/outward, espaçamento existente, modos geométricos mistos, volume e massa física conferidos, propriedades normativas preservadas. Nove IDs de inserção atravessam o diálogo de perfil do papel sem perda.
- Task View e editor modal compartilham a mesma sessão; Aplicar, OK, Cancelar e Undo/Redo conferidos por ações reais dos widgets. Cópia da treliça tem componentes próprios, massa independente e restaura em FCStd.
- 61 membros/pilares/controles paramétricos salvos e reabertos, verificando inserção, rotação, modo, volume, massa, eixo e matriz Placement. Inclui controles W, HP, U laminado, Ue, L, SHS, RHS e CHS, além dos novos U simples. Eixo Draft restaurado continua reagindo à edição.
- Uma cópia descartável de `tests/copiatreliça.FCStd` foi aberta/recomputada; 70 membros estruturais preexistentes permaneceram válidos. O original não foi salvo nem modificado.

Resultados e diretórios finais dos três temas são registrados na tabela de evidências ao final deste relatório. As pastas `test-results/` são ignoradas pelo Git; os scripts permanentes permitem reproduzir os gates.

## Limites e roteiro manual

Há **GO para validação manual**. Não foi identificada limitação arquitetural que exija ampliar o escopo. O catálogo e os testes puros percorrem todas as 125 bitolas; os fluxos GUI reais usam quatro bitolas representativas, não todas as combinações possíveis de usuário.

O teste de FCStd preexistente cobre o arquivo citado, não todos os projetos históricos. Os controles de outras famílias foram criados e restaurados durante o gate. A suíte completa e a aprovação funcional/design do usuário continuam pendentes para o fechamento técnico. Não foi declarada aprovação manual no FreeCAD por meio dos testes automatizados.

Roteiro para o usuário:

1. Nos temas Classic, FreeCAD Dark e OpenDark, abrir o Browser e selecionar as quatro bitolas de controle; conferir identificação, fonte A.2, quatro cotas, `ri = 9,525`, `It = 0,006` e leitura em janela estreita.
2. Criar Membro e Pilar; selecionar cada uma das nove inserções no mini-preview e no menu; testar rotações 0/37/90/180/270°, eixos X/Y/Z/inclinado, offsets e extensões. Alternar Gerar raios e verificar estabilidade de posição.
3. Criar a partir de linha Draft existente, com/sem vínculo; editar a linha e as propriedades do membro; copiar, cancelar criação, desfazer/refazer; salvar, fechar e reabrir. Conferir que a inserção escolhida permanece.
4. No TaskPanel e Editor de Treliças, usar U simples em banzos/diagonais/montantes, isolados e em U duplo para dentro/fora. Conferir rotação, espaçamento e modos Detailed/Simplified; testar Aplicar, OK, Cancelar, cópia e Undo/Redo.
5. Conferir massa nominal dos membros versus massa física da treliça, salvar/reabrir a composição e abrir projetos anteriores W/HP/U/Ue do usuário. Registrar qualquer diferença de layout ou comportamento antes da auditoria de fechamento.

Não foram executados git add, commit, push, merge, tag ou release. A versão 0.7.0 não foi publicada.

## Evidências finais dos gates

Todos os gates finais retornaram sucesso no FreeCAD **1.1.4**, com 125 perfis elegíveis e 61 objetos paramétricos de controle restaurados por execução. Logs FreeCAD/stderr e callbacks Qt sem erros detectados.

| Tema | Verificações aprovadas | Diretório sob `test-results/simple_u_stage_b/` |
| --- | ---: | --- |
| Classic | 539 | `1792538598073729800_Classic_bj7i_7ts` |
| FreeCAD Dark | 539 | `1792538627089483500_FreeCAD_Dark_s36rai4n` |
| OpenDark | 540 | `1792538658008126100_OpenDark_wpjhmxkj` |

Cada diretório contém `result.json`, `checks.json`, `manifest.json`, FCStd, logs, capturas do Browser (quatro bitolas × duas larguras), mini-preview, abas Fonte/Propriedades, diálogo de perfil de treliça, Task View e editor. Os manifests registram hashes dos arquivos de produção utilizados.

As 61 instâncias salvas incluem 53 objetos U simples, contando a cópia, e oito controles de famílias existentes. A abertura da cópia do FCStd histórico verificou adicionalmente 70 membros. A treliça de controle tem 13 componentes e foi testada também em cópia e restauração.

A diferença de uma verificação no OpenDark corresponde à exportação 3D adicional. A captura da MainWindow em processo oculto pode ter viewport OpenGL branco e **não foi usada como evidência da geometria 3D**. A imagem `simple-u-truss-3d.png` no diretório OpenDark é uma exportação Coin real, inspecionada, com a composição de U simples visível.

Exemplos de evidência:

- [Browser Classic com raio 9,525](../test-results/simple_u_stage_b/1792538598073729800_Classic_bj7i_7ts/u-250x100x6.35-browser-760.png).
- [Browser FreeCAD Dark, perfil pequeno](../test-results/simple_u_stage_b/1792538627089483500_FreeCAD_Dark_s36rai4n/u-50x25x1.20-browser-760.png).
- [Mini-preview OpenDark](../test-results/simple_u_stage_b/1792538658008126100_OpenDark_wpjhmxkj/u-250x100x6.35-options.png).
- [Treliça 3D com U simples e compostos](../test-results/simple_u_stage_b/1792538658008126100_OpenDark_wpjhmxkj/simple-u-truss-3d.png).

Rodadas iniciais serviram para ajustar asserções do próprio gate à representação existente de texto, cores float32 do Qt e aspas serializadas do U laminado. Esses ajustes não modificaram as fontes normativas ou o comportamento de produção. O achado visual de categoria duplicada foi corrigido e os três gates finais foram executados com a correção.
