# U dobrado simples — investigação para implementação

Data: 20/10/2026. Base local: `develop/0.7.0`, HEAD `651c0bfd539b647839f4c5fb15e7d79dab443835`.

Escopo desta rodada: leitura da arquitetura e das fontes, diagnóstico e proposta. Nenhum código de produção, catálogo, versão ou changelog foi alterado. O estado inicial já continha arquivos não rastreados de outros trabalhos; eles foram preservados. A publicação remota informada pelo usuário não foi verificada novamente.

## Decisão recomendada

Incorporar a Tabela A.2 como catálogo JSON schema v2 independente e criar um gerador puro específico para U simples. Reutilizar `ColdFormedPath2D`, `SectionGeometry2D`, o adaptador Part, a extrusão de membros e os widgets existentes. A linha média precisa de apenas três retas e dois arcos de 90°. Não usar o U laminado nem tentar obter U simples passando `D = 0` ao Ue: além de ser outra topologia, o validador de Ue exige `D > 0`.

É uma extensão localizada da infraestrutura de perfis, com testes de integração em vários consumidores. Não há necessidade identificada de novo subsistema, dependência de execução, comando público, propriedade persistente ou migração de schema. Para esta investigação curta foi suficiente uma análise individual; uma revisão independente de geometria e regressões será útil na implementação.

## Fontes encontradas e conferência da planilha

- Planilha: `C:/Users/marco/Desktop/Estruturas Metálicas/NBR_6355_2012_Perfis_Formados_a_Frio_Ajustado.xlsx`.
- SHA-256: `291618ca5ad72dfb97606b4b340e72d18cfdb368b9ebaf50dc43b69c7c370155`.
- Aba: `U - Sem revest`; cabeçalho `A3:R3`; dados `A4:R128`.
- PDF local: `C:/Users/marco/Desktop/FREECAD/MINHA BANCADA/REFERENCIAS/NBR6355-2012-Perfis-Formados-a-Frio.pdf`.
- No PDF, Anexo A nas páginas impressas 11–12, Figura A.2 na 12, item 10 na 15 e Tabela A.2 nas 21–25. Correspondem às páginas 17–18, 18, 21 e 27–31 do arquivo, contando a partir de 1.

A leitura direta do XLSX confirmou 125 designações e 125 combinações dimensionais distintas, 14 pares `bw × bf`, sem células vazias em `A4:R128` e sem fórmulas na aba. Todos os valores numéricos dessas linhas são positivos e finitos. Todos os raios conferem com a regra do Anexo A e todas as dimensões acomodam trechos retos positivos. A planilha está disponível; não é necessário solicitá-la novamente.

| Colunas | Conteúdo | Destino proposto no catálogo |
| --- | --- | --- |
| A | Designação original | `designation`, alias e `source_metadata.source_designation` |
| B–C | Massa kg/m; área cm² | `physical_properties.mass_per_length`, `physical_properties.area` |
| D–G | `bw`, `bf`, `t = tn`, `ri`, em mm | `geometry.bw/bf/t/tn/ri` |
| H–J | `Ix`, `Wx`, `rx` | `section_properties.ix/wx/rx` |
| K | `xg`, em cm | `centroid.x` |
| L | `x0`, em cm | `section_properties.x0` |
| M–R | `Iy`, `Wy`, `ry`, `It`, `Cw`, `r0` | `section_properties.iy/wy/ry/it/cw/r0` |

Limites observados: `bw = 50…300 mm`, `bf = 25…100 mm`, `t = 1,20…8,00 mm`, `ri = 1,20…12,00 mm`. Há espessuras 6,30 e 6,35 mm: a fronteira da regra de raio precisa de teste explícito. A linha 120 contém `U250x100x6,35`, com `ri = 9,525 mm`.

Essa conferência de integridade não equivale a uma auditoria de cada propriedade das 125 linhas contra o PDF. Antes de liberar o catálogo, conferir a transcrição integral e registrar divergências, sem preencher valores ausentes por aproximação.

## Convenção dimensional e geometria física

A Figura A.2 representa uma alma com duas mesas paralelas, abertura para a direita e extremidades livres sem enrijecedores. `bw` e `bf` são dimensões nominais externas, incluindo as regiões de dobra; não são comprimentos dos trechos planos. Para o aço sem revestimento da Tabela A.2, `t = tn`.

As relações dimensionais lidas no Anexo A são:

- `ri = tn` para `tn ≤ 6,3 mm`; `ri = 1,5 tn` acima desse limite.
- `rm = ri + t/2`; para o contorno externo, `re = ri + t`.
- Trecho plano da alma: `a = bw − 2 re`; trecho plano de cada mesa: `b = bf − re`.
- Dimensões entre interseções das linhas médias: `am = bw − t`, `bm = bf − t/2`.

Assim, a mesa do U simples tem uma única dobra. A relação de Ue `b = bf − 2 re` não se aplica.

Proposta de construção, ainda não implementada: datum nominal com face externa da alma em `x = 0`, altura `y = 0…bw` e abertura em `+X`. A linha média percorre os pontos abaixo, nesta ordem:

1. Ponta superior `(bf, bw − t/2)` até `(re, bw − t/2)`.
2. Arco de raio `rm`, centro `(re, bw − re)`, até `(t/2, bw − re)`.
3. Alma até `(t/2, re)`.
4. Arco de raio `rm`, centro `(re, re)`, até `(re, t/2)`.
5. Mesa inferior até `(bf, t/2)`.

`ColdFormedPath2D.physical_contour()` já faz offsets de `±t/2`, conserva os arcos circulares, fecha as duas extremidades com segmentos retos e verifica tangência e autointerseção. O resultado esperado tem 12 segmentos, dos quais quatro são arcos físicos: dois internos e dois externos. Não há furos internos nem lábios.

`section_geometry_from_cold_formed()` calcula o centroide físico por integração numérica de alta precisão e translada o contorno para essa origem. A área de caminhos com arcos também dispõe de integração analítica em `SectionPath2D.signed_area`. O envelope esperado continua tendo largura `bf` e altura `bw`. O novo gerador deve fornecer `dimension_stations` nomeadas para faces, tangências, pontas, espessura e raio; evitar inferir essas referências por índices de segmentos.

## Área, propriedades tabeladas, massa e precisão

Preservar três contratos já separados na bancada:

| Informação | Origem e uso |
| --- | --- |
| Dimensões nominais | Definem o contorno e as cotas; `geometry` em mm |
| Propriedades da Tabela A.2 | Área, massa, inércias, módulos, raios, `xg`, `x0`, `It`, `Cw`; permanecem publicadas, sem substituição pela BRep |
| Geometria e quantitativos físicos | Contorno com espessura e curvas; área física, volume após cortes e massa física conforme o contrato existente |

O Anexo A usa seção bruta e método linear, concentrando o material na linha média; para `Cw` e centro de torção adota cantos retos. Portanto, inércias e centroide tabelados não devem ser forçados a coincidir com as integrações do contorno espesso. O `xg` publicado fica como dado técnico; a origem CAD segue o centroide físico, como no Ue aprovado. Eixos locais: X paralelo às mesas, Y paralelo à alma e Z longitudinal.

**Divergência na fonte que merece registro:** a expressão de área impressa no item 10, página 15, contém apenas uma contribuição `u1`. A figura tem duas dobras, a expressão de `It` nessa mesma página inclui duas contribuições, e a primeira linha da tabela é compatível com duas. Para `U 50 × 25 × 1,20`, a área publicada é `1,15 cm²`; o contorno de duas dobras fornece aproximadamente `115,265840 mm²`, enquanto a expressão impressa com uma contribuição fornece `111,873360 mm²`. Isso é evidência de aparente inconsistência, não confirmação de errata oficial. Usar a tabela como fonte de propriedades e a topologia física como fonte da geometria; não criar nesta etapa um calculador normativo que reproduza ou corrija silenciosamente a expressão.

`member.py` já conserva `MassPerMeter` e `CatalogArea` e calcula `TotalMass` pela massa linear publicada e comprimento; com cortes usa comprimento equivalente por volume/área de seção. `trusses/physical_mass.py` mede separadamente os sólidos atuais e aplica a densidade configurada. A massa física pode diferir da nominal e pode variar entre representações Detailed/Simplified; não mudar esse contrato nesta evolução. Somar todos os componentes em compostos, sem duplicar o membro lógico ou incluir previews.

Importar os valores numéricos das células, nunca os textos formatados para tela. O XML contém resíduos binários como `9.5250000000000004`; normalização de serialização não autoriza reduzir `9,525` a `9,53`. Manter a precisão interna disponível, converter unidades apenas na fronteira do catálogo e arredondar só na apresentação. Unidades canônicas atuais: mm, mm², mm³, mm⁴ e mm⁶; fatores de cm para mm conforme a potência.

Há dois cuidados de apresentação: `format_number()` limita por padrão a duas casas, o que ocultaria a precisão de `ri = 9,525`; `It` tem valores como `0,006 cm⁴`, que também exigem apresentação apropriada. Ajustar a apresentação da nova família de modo localizado, sem alterar indiscriminadamente outras famílias. O maior desvio observado entre massa tabelada e `0,785 × área tabelada em cm²` é `0,008 kg/m`; não copiar automaticamente a tolerância `0,007` do teste de Ue nem recalcular a massa para fazê-la passar.

## Identidade e incorporação econômica dos 125 perfis

Proposta de identidade nova, preservando todas as identidades existentes:

- Arquivo `catalogs/abnt_nbr_6355_2012_a2.json`; catálogo `abnt-nbr-6355-2012-a2`.
- Categoria existente `aco-dobrado` / **Aço Dobrado**.
- Série nova `u-simple-nbr-6355` / **U Dobrado Simples (U) — NBR 6355**.
- Família normativa `U`; par geométrico novo `cold_formed_channel / simple_u`. O U laminado atual usa `channel_section / tapered_flange`, série `u`, família `u`; Ue usa `cold_formed_channel / stiffened_u`, família `Ue`. A distinção deve depender de categoria, série, ProfileRef e par geométrico, sem depender apenas de maiúsculas/minúsculas.
- Exemplo de ID estável `u-50x25x1.20`; designação brasileira `U 50 × 25 × 1,20`; alias original `U50x25x1,20` e alias ASCII com ponto decimal.
- Fonte ABNT, edição 2012, Anexo A informativo, Figura A.2, Tabela A.2, aço sem revestimento; sem fabricante fictício.

Um importador executado no desenvolvimento deve ler a aba, validar as 125 linhas e gerar o JSON determinístico ordenado numericamente por `bw, bf, tn`. O runtime continua lendo apenas JSON, sem dependência de Excel. Registrar arquivo/aba e hash da fonte no processo de geração; usar os campos existentes de `source_metadata` para designação, tabela, linha da planilha e páginas conferidas, distinguindo página impressa e página do PDF. Não reutilizar o catálogo A.3 nem modificar seus 85 registros.

## Mapa mínimo de integração

Os caminhos abaixo são relativos a `freecad/SteelStructures/`, salvo indicação.

| Área | Implementação atual e intervenção futura |
| --- | --- |
| Catálogo tipado | `profiles/catalog.py` descobre JSONs automaticamente; `models.py` já comporta geometria e propriedades necessárias. Novo catálogo dispensa mudança de schema |
| Validação | `profiles/validation.py:367` aceita apenas `stiffened_u` e exige `D`. Separar parâmetros e validação por variante; conferir `t = tn` no novo catálogo sem revestimento. Reutilizar a regra de raio já disponível sem alterar a validação de Ue |
| Geometria | Novo `profiles/u_section.py`; registrar o builder em `profiles/geometry.py:689` e, conforme o padrão público atual, exports em `profiles/__init__.py`. Reusar integralmente o núcleo de offsets/interseções |
| Modo geométrico | Registrar `simple_u` em `section_geometry_mode_has_effect`; oferecer Detailed com raios e Simplified com cantos retos, mantendo datum do centroide detalhado, referências e dados técnicos |
| Elegibilidade | Adicionar a série a `profile_catalog.py:20` (`SUPPORTED_CREATION_SERIES`). A fachada preserva `definition`; não preencher artificialmente `d/tw/tf` para fingir seção laminada |
| Browser | `interactive/profile_browser_model.py` já filtra e seleciona por ProfileRef. `profiles/presentation.py` precisa das quatro dimensões, precisão adequada e fonte A.2; a apresentação de Ue contém referências A.3 explícitas |
| Prévia técnica | `interactive/profile_browser_preview.py` tem dispatch, enquadramento e marcador explícitos para Ue. Acrescentar `simple_u`, reaproveitar primitivas de cotagem e evitar chamadas da cota `D` ou de índices do contorno de Ue |
| Inserção e mini-preview | Novo ramo em `profiles/insertion.py`; novo esquema curvo em `profiles/preview_geometry.py`. `interactive/section_orientation_preview.py` pode consumir o esquema sem novo widget |
| Criar Membro / Pilar | `member.py:109/648` já usa geometria tipada, face local e extrusão Z. `ProfileOptionsWidget` é compartilhado pelo pilar. Integração prevista por catálogo/dispatch, sem reescrever controladores |
| Treliças / compostos | `trusses/realization.py` usa ProfileRef; `trusses/assemblies.py:39` já permite `cold_formed_channel` nos dois U duplos. `assemblies/presets.py` assume abertura +X, compatível com a proposta; transformações já tratam arcos e reflexões |
| Quantitativos | Preservar `member.py:499/648` e `trusses/physical_mass.py`. Verificar volumes, cortes, componentes e exclusão de temporários com a nova família |

Adicionar apenas JSON não basta: o validador rejeitaria a variante, os comandos não liberariam a série e o mini-preview não teria esquema. A extensão econômica cobre esses pontos explícitos e deixa os fluxos genéricos existentes em uso.

## Proposta de prévia técnica e inserção

Usar o mesmo canvas técnico do Ue, contorno real cinza, traços e cotas consistentes com a bancada e abertura para `+X` na orientação canônica. Dispor `bw` à esquerda, entre os planos externos superior e inferior; `bf` acima, da face externa da alma até a extremidade livre da mesa; chamada `t` para uma parte plana; chamada `ri` para o arco interno, sem ampliar artificialmente a geometria. Remover a cota e qualquer referência a `D`. Mostrar o ponto de inserção selecionado pelo marcador existente. Na visualização de propriedades, manter os eixos locais e separar o significado técnico de `xg` da origem física CAD.

Proposta inicial de nove referências, todas derivadas das mesmas estações geométricas:

- `centroid`: Centroide físico.
- `web_center`: Centro da alma, no meio da espessura e da altura.
- `web_back`: Face externa da alma, no meio da altura.
- `rear_top`, `rear_bottom`: interseções nominais dos planos externos traseiro/superior e traseiro/inferior. São cantos virtuais por causa das dobras, como no Ue.
- `flange_top_tip`, `flange_bottom_tip`: meio da espessura nas extremidades livres das mesas.
- `outer_top_mid`, `outer_bottom_mid`: meio do trecho plano da face externa de cada mesa.

Nenhuma referência a enrijecedor deve aparecer. Os nomes/labels precisam ser estáveis antes da liberação porque a inserção participa da persistência. O mini-preview será um esquema normalizado próprio de U simples, com curvas e espessura uniforme, compartilhando rotação, cores e seleção de hotspots existentes. Não reutilizar o desenho de U laminado, que representa mesas de espessura variável.

## Persistência e limites de risco

Manter a seção local em XY, extrusão em Z, translação de inserção/offsets no plano local e orientação/rotação longitudinal pelo `Placement`, como em `member.py`. O modo Simplified deve conservar a origem física da representação Detailed, impedindo saltos de posição ao alternar raios. Preservar as propriedades atuais `ProfileCategory`, `ProfileSeries`, `Profile`, `Insertion`, `Rotation` e `SectionGeometryMode`; treliças e compostos já serializam ProfileRef e transformações de componentes.

Não foi identificada necessidade de nova propriedade persistente ou `SchemaVersion`. Isso é uma conclusão de arquitetura, ainda sujeita a testes de salvar, reabrir e recompute da implementação. Conferir também troca U/Ue/U laminado e restauração de inserção inválida pelo fallback existente, sem resetar arbitrariamente o Placement de documentos antigos.

## Verificações desta rodada e roteiro da implementação

Auditoria reproduzível: `python test-results/u_simple_investigation/inspect_sources.py` — passou as verificações de quantidade, unicidade, completude, valores finitos, raios e acomodação dimensional. Script, resumo JSON e imagens de consulta do PDF estão em `test-results/u_simple_investigation/`, ignorado pelo Git. Não foi criado protótipo de seção, UI ou catálogo de produção.

Testes direcionados executados:

```powershell
python -m unittest tests.test_cold_formed_ue tests.test_cold_formed_intersections tests.test_ue_stage2 tests.test_section_geometry_mode tests.test_section_insertion tests.test_section_orientation_preview tests.test_profile_browser tests.test_freecad_section_geometry
```

Resultado: 125 testes passaram. Eles verificam a infraestrutura existente, incluindo adaptadores controlados, e não demonstram que U simples já está implementado.

`python scripts/check_project.py` — passou.

`python -m unittest discover -s tests -p 'test_*.py'` — 1.905 testes em 59,472 s, sem falhas, com 149 ignorados (`OK (skipped=149)`). Os testes ignorados não foram validados por essa execução. A suíte contém módulos controlados/stubs e não substitui testes no FreeCAD.

Na implementação, acrescentar testes para os 125 registros, unidades e procedência; espessuras 6,30/6,35/8,00; raio 9,525; espessura constante; dois arcos na linha média; quatro no contorno; tangência e ausência de autointerseção; área física independente e centroide; paridade entre modos e inserções; Browser e mini-preview; criação por todos os consumidores; U duplo para dentro/fora e quantitativos. Ajustar expectativas exatas de catálogo que atualmente pressupõem somente Ue em Aço Dobrado, sem enfraquecer testes existentes de Ue.

Roteiro manual futuro no FreeCAD 1.1.3:

1. Conferir Browser, fonte A.2, cotas e precisão com U pequeno, U grande e `U 250 × 100 × 6,35`.
2. Criar membros em X, Y, Z e inclinados; testar nove inserções, rotação 0/90/180/270° e arbitrária, offsets e extensões. Alternar raios sem deslocamento de referências.
3. Criar pilar; cancelar e repetir criação; conferir preview, transações e Undo/Redo.
4. Criar/editar treliça com U simples em diferentes papéis; testar membro simples, par espaçado e U duplo com bocas para dentro/fora, rotação e cortes existentes.
5. Conferir massa nominal, massa física e quantidade de sólidos/componentes; salvar/reabrir/recomputar; abrir documentos antigos com Ue e U laminado.

Nenhum teste manual no FreeCAD foi realizado nesta investigação. Implementação e validação funcional/design pelo usuário permanecem etapas futuras; nenhum commit ou push foi realizado.
