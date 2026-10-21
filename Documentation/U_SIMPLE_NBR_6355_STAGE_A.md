# U dobrado simples — Etapa A

Data: 20/10/2026. Branch `develop/0.7.0`; HEAD de referência preservado: `651c0bfd539b647839f4c5fb15e7d79dab443835`.

**Resultado: GO técnico para iniciar a Etapa B.** Catálogo, geometria pura, nove inserções e representação Detailed/Simplified implementados. Testes direcionados e validação nativa no FreeCAD 1.1.4 passaram. Isso não representa conclusão da integração visual nem autorização de publicação.

O relatório `U_SIMPLE_NBR_6355_IMPLEMENTATION_INVESTIGATION.md` foi lido integralmente antes das alterações e confrontado com o código. Não foram alterados Treliças, StructuralPlate, Gussets, Recortar/Ajustar Membro, comandos GUI, propriedades persistentes, versões ou changelog. Estudos e arquivos experimentais locais foram preservados. Não foram executados git add, commit, push, merge, tag ou release.

## Arquitetura implementada

- Catálogo independente `abnt-nbr-6355-2012-a2`, série `u-simple-nbr-6355`, categoria `aco-dobrado`, família normativa `U`, variante `cold_formed_channel / simple_u`.
- Snapshot de `A4:R128` preserva as strings numéricas originais do XML da planilha. O gerador determinístico valida o hash e converte números sem arredondamento para apresentação. O runtime continua consumindo JSON, sem dependência de Excel/PDF.
- `profiles/u_section.py` valida `bw`, `bf`, `t`, `ri` e constrói três retas e dois arcos de 90° na linha média. A espessura, offsets circulares, fechamento das pontas, tangência, autointerseções e centralização física reutilizam `ColdFormedPath2D` e `section_geometry_from_cold_formed()`.
- `bw` e `bf` são dimensões externas. Trechos planos: `a = bw − 2(ri+t)` e `b = bf − (ri+t)`. Raios: `rm = ri+t/2`, `re = ri+t`. Abertura canônica em +X, alma paralela a Y, seção em XY e futura extrusão em Z.
- O contorno Detailed tem 12 segmentos, quatro deles arcos: duas faces internas e duas externas de dobra. Sem enrijecedores ou furos.
- Simplified tem oito retas e conserva envelope, origem e estações da geometria Detailed. A área da sua representação CAD muda, mas não altera dados normativos nem desloca referências ao alternar modos.
- `build_section_geometry()` despacha a variante nova. `section_geometry_mode_has_effect()` reconhece seus raios. O adaptador FreeCAD/Part existente é reutilizado sem alterações.
- O validador distingue parâmetros de U simples e Ue; U simples não aceita `D`. Para o catálogo A.2 sem revestimento exige `t = tn`; a regra normativa de raio reutiliza a função existente, inclusive a fronteira 6,30/6,35 mm. O builder físico aceita raios positivos independentes de `t`, sem impor a regra de um catálogo à geometria genérica.

As funções públicas adicionadas são `simple_u_derived_dimensions`, `build_simple_u_mean_path`, `build_simple_u_section` e `build_simplified_simple_u_section`, com `SimpleUDerivedDimensions`. Não foi criado calculador de propriedades normativas a partir da expressão controversa de área.

As nove inserções são derivadas de estações geométricas nomeadas, sem índices de segmentos:

| ID | Referência |
| --- | --- |
| `centroid` | Centroide físico, origem local |
| `web_center` | Meio da espessura da alma, à meia altura |
| `web_back` | Face externa da alma, à meia altura |
| `rear_top`, `rear_bottom` | Cantos externos nominais virtuais dos planos da alma/mesas |
| `flange_top_tip`, `flange_bottom_tip` | Meio da espessura nas extremidades livres das mesas |
| `outer_top_mid`, `outer_bottom_mid` | Meio do trecho plano externo de cada mesa |

IDs e labels reutilizam o vocabulário já existente para U/Ue. Não há referências a enrijecedores. Detailed/Simplified têm as mesmas nove posições e labels.

## Fonte, rastreabilidade e cobertura

Planilha: `C:/Users/marco/Desktop/Estruturas Metálicas/NBR_6355_2012_Perfis_Formados_a_Frio_Ajustado.xlsx`, aba `U - Sem revest`, intervalo `A4:R128`.

SHA-256 da planilha: `291618ca5ad72dfb97606b4b340e72d18cfdb368b9ebaf50dc43b69c7c370155`.

Referência PDF: `C:/Users/marco/Desktop/FREECAD/MINHA BANCADA/REFERENCIAS/NBR6355-2012-Perfis-Formados-a-Frio.pdf`.

SHA-256 do PDF: `92de1de4f0547c44c1007397d87a3f80b20ae02b772fbb141220c6fda6ae4b71`.

Fingerprint das células originais no snapshot: `a0394c448abc0f1c8ecc5beddaf312816dd0562106b53627d878d675cb33883f`. A notação científica e resíduos de serialização originais foram preservados no snapshot; não houve redução para duas casas decimais.

Uma revisão independente conferiu **125 designações e 2.125 células numéricas** da planilha contra as páginas 27–31 do PDF (páginas impressas 21–25), sem divergências materiais. Também conferiu snapshot e catálogo célula por célula. `source_metadata` registra a linha da planilha, designação original, tabela, página impressa e página do PDF; propriedades e massa continuam publicadas, sem fabricante fictício.

**Diferença entre fontes:** o PDF tem 126 linhas. `U 300 × 100 × 2,65` aparece na página impressa 24/arquivo 30 com massa em branco e não consta da planilha autorizada. Esta etapa incorpora exatamente as 125 linhas autorizadas; a exclusão foi registrada em `generation_audit` e no snapshot. Não foi reconstruída massa nem inventado registro adicional.

| Base `bw × bf` (mm) | Bitolas |
| --- | ---: |
| 50 × 25 | 6 |
| 75 × 40 | 10 |
| 100 × 40 | 11 |
| 100 × 50 | 11 |
| 100 × 75 | 8 |
| 125 × 50 | 11 |
| 125 × 75 | 8 |
| 150 × 50 | 10 |
| 150 × 75 | 8 |
| 200 × 50 | 10 |
| 200 × 75 | 8 |
| 200 × 100 | 8 |
| 250 × 100 | 9 |
| 300 × 100 | 7 |
| **Total** | **125** |

Limites: `bw = 50…300 mm`, `bf = 25…100 mm`, `t = 1,20…8,00 mm`, `ri = 1,20…12,00 mm`. O perfil `U 250 × 100 × 6,35` conserva `ri = 9,525 mm` no catálogo, nas estações e nas curvas físicas. Valores pequenos como `It = 0,006 cm⁴` também permanecem íntegros.

## Área publicada e área física

A expressão impressa no item 10, página 15/arquivo 21, contém apenas uma parcela `u1`, com `u1 = 1,571 rm`. A Figura A.2 mostra duas dobras e a expressão de `It` na mesma página contém duas parcelas. A inspeção visual confirmou que não se trata apenas de erro de extração de texto.

A decomposição física independente em alma, mesas retas e dois quadrantes anulares dá `A_física = t [a + 2b + π rm]`. Essa relação descreve o contorno físico, não uma correção oficial da expressão impressa.

Para `U 50 × 25 × 1,20`:

| Origem | Área (mm²) |
| --- | ---: |
| Tabela A.2 | 115 |
| Contorno físico com duas dobras | 115,265840131754 |
| Expressão impressa com uma parcela `u1` | 111,87336 |

Nas 125 linhas, a área física difere da área tabelada por no máximo `0,004852814 cm²`, dentro de meia unidade da última casa publicada (`0,005 cm²`). A expressão com uma dobra excede esse intervalo em todas as 125 linhas. Isso sustenta o diagnóstico de aparente inconsistência na fonte; nenhuma errata oficial foi confirmada.

As áreas, massas, `xg`, inércias, módulos, raios de giração, `x0`, `It`, `Cw` e `r0` tabelados foram preservados. As propriedades seguem o método linear normativo; o contorno físico tem espessura finita e centroide próprio. Não há override para forçar coincidência, recalcular massa ou substituir a tabela pela BRep. O teste de comparação por arredondamento é um controle de diagnóstico e não muda a fonte dos dados.

## Arquivos criados e modificados

Criados:

- `freecad/SteelStructures/catalogs/abnt_nbr_6355_2012_a2.json` — catálogo das 125 bitolas.
- `freecad/SteelStructures/catalog_sources/abnt_nbr_6355_2012_a2_extracted.json` — fonte rastreável e auditoria.
- `scripts/generate_nbr6355_simple_u_catalog.py` — extração, validação, geração e comparação determinística.
- `freecad/SteelStructures/profiles/u_section.py` — dimensões derivadas e geometrias Detailed/Simplified.
- `tests/test_cold_formed_simple_u.py` — 12 testes permanentes, vários percorrendo todas as 125 bitolas.
- `tests/freecad_simple_u_geometry_validation.py` — validação nativa, executada explicitamente fora da descoberta comum.
- Este relatório.

Modificados:

- `profiles/__init__.py`, `profiles/geometry.py`, `profiles/insertion.py`, `profiles/validation.py` — integração do núcleo e inserções, sob `freecad/SteelStructures/`.
- `scripts/check_project.py` — presença dos arquivos e reprodução do catálogo A.2.
- `tests/test_profile_catalog_stage2b.py` — contagem pública tipada passou de 3.466 para 3.591, mantendo todas as contagens anteriores por catálogo.
- `tests/test_profile_browser.py` — cinco categorias vinculadas a catálogos em lugar de quatro; verifica explicitamente os dois catálogos de Aço Dobrado. Nenhuma implementação visual foi alterada.

## Testes executados

Comando final direcionado:

```powershell
python -m unittest tests.test_cold_formed_simple_u tests.test_cold_formed_ue tests.test_cold_formed_intersections tests.test_ue_stage2 tests.test_section_geometry tests.test_section_geometry_mode tests.test_section_insertion tests.test_section_orientation_preview tests.test_profile_catalog_v2 tests.test_profile_catalog_stage2b tests.test_profile_models tests.test_normative_profile_metadata tests.test_freecad_section_geometry tests.test_profile_browser tests.test_profile_search tests.test_profile_presentation tests.test_profile_options_browser_integration
```

**277 testes passaram**, sem falhas ou skips, em 12,124 s. Cobertura: integridade, unicidade, todas as células/unidades, hashes, rastreabilidade, raios 6,30/6,35/8,00 e 9,525, entradas inválidas, variantes independentes, curvas/fechamento, área e centroide por fórmula analítica independente, nove inserções, modos geométricos, rotações/reflexões, regressões de Ue/U laminado, biblioteca e contratos existentes de UI. Esses testes Python incluem módulos controlados; não equivalem a testes manuais de interface.

A primeira rodada de regressão detectou a expectativa antiga de quatro categorias. Ela foi atualizada para cinco, com as identidades de A.2/A.3 verificadas explicitamente. Não foram removidos nem enfraquecidos testes de famílias existentes.

Outros comandos:

```powershell
python scripts/generate_nbr6355_simple_u_catalog.py --xlsx 'C:/Users/marco/Desktop/Estruturas Metálicas/NBR_6355_2012_Perfis_Formados_a_Frio_Ajustado.xlsx' --check
python scripts/check_project.py
git diff --check
& 'C:/Users/marco/Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311/bin/python.exe' tests/freecad_simple_u_geometry_validation.py
```

Todos passaram. O `--check` reproduz snapshot e catálogo sem escrever. A suíte completa não foi executada nesta etapa.

Validação nativa FreeCAD **1.1.4**, Python 3.11, Part/OCC reais, sem GUI:

- 125 perfis × dois modos: **250 faces válidas e 250 sólidos válidos**, com envelope e volume conferidos.
- Raio fracionário medido na curva OCC: `9,525000000000007 mm`, diferença de ponto flutuante compatível com a tolerância do teste.
- **540 combinações** de nove inserções, direções X/Y/Z/inclinada e rotações 0/37/90/180/270°, em três perfis de controle.
- **Seis sólidos** de controle foram salvos, reabertos em FCStd e recomputados, preservando validade, volume e Placement. Isso testa persistência da Shape/Placement em `Part::Feature`, não o futuro fluxo FeaturePython de StructuralMember.
- Maior diferença área Part versus núcleo: `8,19 × 10⁻¹² mm²`; volume: `5,83 × 10⁻⁹ mm³`.

Evidências nativas: `test-results/simple_u_stage_a_native/result.json` e `simple_u_kernel.FCStd`. Revisão independente e auditoria de fontes: `test-results/u_simple_stage_a_source_review/`. Essas pastas são ignoradas pelo Git; o catálogo, snapshot, gerador, testes e este relatório são os artefatos permanentes.

## GO para Etapa B e limitações atuais

A revisão técnica independente não encontrou bloqueios no núcleo, na preservação dos dados ou na integração arquitetural. Há **GO técnico para implementar a Etapa B**, mantendo o fluxo de validação funcional e visual pelo usuário antes de publicação.

`SUPPORTED_CREATION_SERIES` não foi alterado: os 125 perfis ainda não são elegíveis para Criar Membro, Criar Pilar ou seleção de criação do Browser. A biblioteca tipada descobre o catálogo automaticamente e o Browser de consulta já pode mostrá-lo, com a apresentação genérica existente. A formatação atual dessa consulta pode apresentar `ri = 9,525` como `9,53`; o dado interno permanece 9,525. Isso precisa ser tratado na Etapa B junto às cotas e ao mini-preview.

Próximas integrações:

1. Apresentação específica: fonte Figura/Tabela A.2, quatro cotas `bw/bf/t/ri`, precisão de `ri` e `It`, marcador da inserção e enquadramento técnico.
2. Esquema normalizado curvo `simple_u` e nove hotspots no mini-preview, sem lábios nem cota `D`.
3. Liberação explícita da série, integração Membro/Pilar/Treliças e U duplo, preservando suas implementações existentes e a distinção massa nominal/física.
4. Testes de consumidores, FeaturePython, salvar/reabrir documentos paramétricos, recompute, cancelamento, Undo/Redo, previews e documentos antigos.
5. Validação manual visual no FreeCAD e aprovação do usuário sobre funcionamento e design.

Não houve teste manual de interface nesta etapa. O roteiro acima permanece obrigatório para concluir a integração visual; não há necessidade identificada de refatoração significativa do núcleo implementado.
