# Aço Maciço — Etapa B: catálogo brasileiro NBR 16683

Implementação para Steel Structures 0.6.0, sobre o commit
`1782911ddbee5c96e07de9feb9ff5c0ef58b6f12`. Validada visual e funcionalmente
pelo usuário no FreeCAD 1.1.3, com fechamento em commit autorizado.

## Fonte primária e limites da verificação

Foi utilizado o PDF integral fornecido pelo usuário, com 25 páginas: seis
preliminares e 19 numeradas. O título é **Barras laminadas de aço, chatas,
redondas, quadradas e sextavadas, para uso estrutural — Dimensões e tolerâncias**.
A capa informa ABNT NBR 16683:2018, primeira edição de 29/11/2018 e versão
corrigida de 23/04/2020. O prefácio confirma a incorporação da Errata 1 de
23/04/2020 e a substituição da NBR 5907:1982.

SHA-256 do exemplar primário:
`dfda6bd8d496dfaf435503d0145fa0ac6d5bb47515c06975bba4bb54fbccddbd`.

O status de vigência em setembro de 2026 e a existência de correções posteriores
não foram confirmados no catálogo online da ABNT. O dataset identifica a edição
efetivamente conferida, sem afirmar que ela é a edição vigente. O PDF completo
não é distribuído no repositório. Nenhuma fonte comercial substituiu suas células.

O escopo da publicação é de barras laminadas a quente para uso estrutural/geral,
com exclusões para outros produtos/processos. Esta implementação contempla
somente as três famílias aprovadas; não incorpora sextavadas, barras nervuradas,
produtos cortados de chapa/bobina ou produtos para uso mecânico.

## Conteúdo e transformação

| Série | Tabela | Páginas impressas | Entradas |
|---|---|---|---:|
| Barra Redonda | A.2 | 10–11 | 53 |
| Barra Quadrada | A.3 | 12 | 19 |
| Barra Chata | A.1 | 6–9 | 92 |
| Total | | | 164 |

As 92 chatas são combinações explícitas de 17 larguras. Não foi construído um
produto cartesiano. As dimensões nominais das colunas próprias prevalecem sobre
conversões de polegadas e sobre bitolas comerciais parecidas. Por exemplo,
88,90 × 9,52 permanece diferente de 88,90 × 9,53; redonda 52,38 permanece distinta
da quadrada de lado 52,39.

Os números originais ficam no snapshot como strings decimais com vírgula:
duas casas para dimensões e três para massa. A normalização remove somente zeros
finais na apresentação, usa números em mm/kg/m no catálogo e IDs ASCII estáveis.
Exemplos: `round-bar-20-64`, `square-bar-20-64`, `flat-bar-50-8x6-35`.
O `ProfileRef` inclui o catálogo `abnt-nbr-16683-2018-solid`.

### Massas e notas

A seção 4.3.3, página 2, informa densidade de 7,85 g/cm³ (7850 kg/m³) e caráter
orientativo das massas; elas não são critério de rejeição. Todas as 164 linhas
possuem massa publicada, preservada numericamente com a precisão original no
snapshot. `mass_type=published` e `mass_basis=normative_table` distinguem essa
origem de uma massa calculada. Não se recalcula massa para coincidir com a Shape.

`CatalogArea`, A, Ix/Iy, Wx/Wy, rx/ry e centroide continuam calculados pela
Steel Structures para a seção nominal ideal. A massa não determina a área.
O cálculo de massa do membro continua usando a massa linear publicada e o
comprimento físico equivalente da geometria, incluindo ajustes existentes.

A seção 4.4 trata de comprimentos usuais de 6 m e 12 m e tolerância de corte de
até +100 mm, com outros comprimentos por acordo. Isso fica documentado como
informação da fonte; não limita o comprimento criado no CAD. Dimensões por acordo
previstas em 4.3.4 não são convertidas em linhas adicionais do catálogo.

O Anexo B trata das tolerâncias. Limites de canto não definem um raio nominal
único: permanecem os cantos vivos aprovados para quadradas e chatas. As tolerâncias
não alteram nominalmente a seção, não habilitam raios e não criam modo Detailed
distinto. A aplicação não implementa verificação de conformidade de fornecimento.

### Divergências preservadas da publicação

- A.1, p. 8, linha 19: referência textual `76,20 × 49,80`, mas colunas nominais
  explícitas 76,20 × 50,80 e massa 30,390 kg/m. O catálogo usa essas colunas
  nominais; mantém a referência divergente e uma nota por perfil.
- A nota de massa das tabelas remete a 4.1.3, enquanto a regra aplicável aparece
  em 4.3.3. A observação fica registrada, sem alegar errata oficial adicional.
- A marca `b` identifica denominações métricas comerciais em 13 linhas. Não gera
  aliases em polegadas. O sinal `’` de `13/16’` na quadrada é preservado na origem
  e removido somente na formação do alias de pesquisa.
- Nenhuma célula foi corrigida: `source_corrections_applied=[]`. As observações
  não são classificadas como erratas oficiais.

Há 12 massas com diferença absoluta relativa de pelo menos 0,5% em relação à
seção ideal vezes 7850 kg/m³. Esse limiar serve somente para auditoria; não é
tolerância normativa. Todas foram reconferidas no PDF e preservadas.

| Seção nominal (mm) | Publicada (kg/m) | Ideal (kg/m, arredondada aqui) |
|---|---:|---:|
| Quadrada 6,35 | 0,310 | 0,316532 |
| Quadrada 38,10 | 11,150 | 11,395139 |
| Chata 44,45 × 6,35 | 1,966 | 2,215721 |
| Chata 44,45 × 12,70 | 4,181 | 4,431443 |
| Chata 63,50 × 4,76 | 2,335 | 2,372741 |
| Chata 69,85 × 12,70 | 6,714 | 6,963696 |
| Chata 88,90 × 6,35 | 4,307 | 4,431443 |
| Chata 88,90 × 9,52 | 6,490 | 6,643675 |
| Chata 88,90 × 12,70 | 8,590 | 8,862885 |
| Chata 88,90 × 15,88 | 10,847 | 11,082096 |
| Chata 88,90 × 19,05 | 13,047 | 13,294328 |
| Chata 130 × 13 | 13,130 | 13,266500 |

O catálogo contém a comparação completa das 164 linhas em `generation_audit`.
A massa publicada de quadrada 44,45, 15,510 kg/m, por exemplo, coincide com o
cálculo ideal à precisão publicada; uma diferença comercial para essa linha
não deve ser confundida com a auditoria geométrica acima.

## Processo reproduzível

1. `scripts/extract_nbr16683_solid_snapshot.py` lê o exemplar fornecido, verifica
   o hash e extrai as tabelas em desenvolvimento usando PyMuPDF. Não instala uma
   dependência na workbench. Recebe o caminho `pdf` e a opção `--output`; consulte
   `--help`.
2. `catalog_sources/abnt_nbr_16683_2018_solid_extracted.json` preserva células,
   família, tabela, página impressa, página PDF, linha, notas e metadados comuns.
3. `scripts/generate_nbr16683_solid_catalog.py` valida identidade, hash dos
   registros, contagens, posições, dimensões, massas e duplicatas. Ordena
   numericamente por D, B ou B/t e gera o JSON estático.
4. O carregador normal lê `catalogs/abnt_nbr_16683_2018_solid.json`; não abre PDF
   nem executa extração em runtime.

```powershell
python scripts/generate_nbr16683_solid_catalog.py
python scripts/generate_nbr16683_solid_catalog.py --check
```

SHA-256 dos registros originais, com serialização definida pelo snapshot:
`0a6b9823c9983f844212a5b180a7e186a88dd74292eb462d84279765567d4b35`.

Duas execuções independentes do gerador produziram bytes idênticos. O teste
automatizado também compara o arquivo instalado com a saída do gerador.
As fórmulas geométricas não são duplicadas no gerador: a comparação de massa usa
`solid_section_properties`, existente desde a Etapa A.

## Schema, proveniência e packs futuros

Metadados comuns do catálogo:

```text
region = BR
country = Brazil
catalog_pack = brazil
issuer.id = abnt
source.source_type = normative
standard_references = ABNT NBR 16683:2018, versão corrigida 23.04.2020
```

Cada perfil alcança esses metadados pelo catálogo e acrescenta tabela, página,
linha, referência original, dimensões e massa publicada. `availability_status`
é `normative_table`: informa dimensão tabelada, sem prometer oferta comercial.

Os campos regionais são opcionais para catálogos existentes. `region` aceita
dois caracteres ASCII maiúsculos, `country` é texto e `catalog_pack` usa ID
estável. O esquema permite packs como Brasil/ABNT, Europa/EN e Internacional/ISO;
região supranacional não deve ser interpretada como um país obrigatório. Identidade
de perfil permanece em `ProfileRef`, sem renomear IDs ao adicionar filtros.

A densidade comum da fonte é informativa. Continua distinta da densidade por
perfil que autoriza o cálculo de uma fixture. A massa normativa em kg/m não
depende de `source_weight_p` ou base de 6 m. O contrato Tuper de kg/6 m permanece
compatível e validado; também permanece possível massa comercial publicada em kg/m.

Pendências futuras, sem implementação nesta etapa:

- Packs e filtros de região/norma na UI.
- ISO 1035 como candidata a pack internacional; EN 10058 para chatas, EN 10059
  para quadradas e EN 10060 para redondas. Edição, escopo e licenciamento dessas
  fontes deverão ser auditados antes de qualquer integração.
- Separação entre seção canônica e ofertas comerciais, sem obrigar fabricante
  no nome público. Nenhum catálogo completo Gerdau/ArcelorMittal foi incorporado.

## UI, membros e compatibilidade

A árvore mantém Aço Maciço com Barra Redonda, Barra Quadrada e Barra Chata.
O subtítulo e a aba Fonte identificam ABNT NBR 16683; dimensões, cotas e previews
mantêm a linguagem da Etapa A: Ø, (b) e (b)/(t). Proporções, pontos de inserção,
rotação e mini-preview continuam no mesmo pipeline `solid_section`.

Nenhum builder, adaptador de Face ou algoritmo de AxisSource/ajuste foi alterado.
O único ajuste em `member.py` passa a seleção atual ao preenchimento do enum de
perfil para preservar uma fixture já utilizada em documento antigo.

O carregamento público deixa de incluir `catalogs/dev/`. As seis fixtures
permanecem nesse diretório para testes explícitos e resolução histórica pela
fachada. O enum de um objeto antigo conserva somente sua fixture atual, junto
das opções normativas públicas. Não há fixtures no Browser ou nas listas de nova
criação. Sua remoção física futura requer rever esse mecanismo de compatibilidade.

Não existem linhas normativas exatas de Ø20, Ø50, quadrada 20/50, chata 50×6,35
ou 100×10 nas tabelas utilizadas. Portanto:

- `Barra Redonda 20`, `Ø20` e `20` podem encontrar resultados por substring,
  incluindo Ø20,64; não geram Ø20.
- `Barra Quadrada 20x20` e `20x20` não retornam um perfil normativo exato.
- `Barra Chata 50x6,35`, `50x6.35` e `50x6,35` não inventam a dimensão ausente.
  A dimensão presente `50,8x6,35` é pesquisável com ponto ou vírgula.
- Aliases de polegadas existem somente quando a coluna original oferece base.

## Auditoria e validação

O QA independente reconstruiu e comparou 164/164 registros por extração espacial
do PDF, sem depender do extrator que gerou o snapshot. Conferiu também as sete
páginas de tabelas renderizadas, amostras pequenas/médias/grandes, notas e massas
divergentes. O relatório de cobertura, diferenças e publicações comerciais está
em [NBR16683_COMMERCIAL_AUDIT.md](NBR16683_COMMERCIAL_AUDIT.md).

Revisão final independente aprovada, sem bloqueios. O QA identificou e a
implementação corrigiu a apresentação de metadados opcionais ausentes; há um
teste de regressão específico. Resultado automatizado final:

| Verificação | Resultado |
|---|---|
| Foco independente de QA | 212 testes — OK |
| Módulo normativo após correção de apresentação | 20 testes — OK |
| `python -m unittest discover -s tests -p "test_*.py"` | 842 testes — OK; baseline 808 |
| `python scripts/check_project.py` | OK |
| `git diff --check` | OK |
| Whitespace/EOF dos nove arquivos novos | OK |

As contagens focadas se sobrepõem à suíte completa, não são testes adicionais.

O roteiro `tests/manual_nbr16683_solid_validation.py` foi executado via MCP no
FreeCAD 1.1.3 real: **86 verificações aprovadas**. Criou 12 membros temporários
(Membro/Pilar, Independent/Linked, uma entrada de cada família), conferiu Shape
válida e Volume > 0, massa publicada, eixo, inserção, rotação, extensões, PlaneCut
ortogonal/oblíquo com dois extremos e Gap, LengthLimit, sinais reais do preview
SourceAxis, cancelamento, Browser e persistência. Reabriu cópia de um documento
Etapa A: seus dez membros de fixtures recompuseram com geometria e massa válidas.

Capturas reais das três séries foram inspecionadas para cotas e proporções.
O documento do usuário já aberto não foi editado. FCStd, imagens e relatório
numérico de validação ficam somente no diretório ignorado
`test-results/nbr16683-source/freecad/`.

Para validação do usuário: reiniciar a workbench, abrir o Browser, conferir uma
entrada de cada série e a aba Fonte; criar Membro/Pilar, testar uma linha
vinculada e salvar/reabrir. Revisar especialmente a apresentação das massas
normativas orientativas e a ausência das antigas bitolas de fixture nas listas.

Nenhuma alteração foi feita em versão, changelog de release ou catálogos
comerciais existentes. Os testes finais passaram e o usuário aprovou o
funcionamento e a apresentação no FreeCAD 1.1.3. O commit de fechamento foi
autorizado; push permanece sem autorização.
