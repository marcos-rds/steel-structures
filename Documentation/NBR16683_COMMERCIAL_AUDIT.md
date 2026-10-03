# NBR 16683 — auditoria comercial separada

Consulta em 05/09/2026. O catálogo-base contém exclusivamente as 164 linhas das
Tabelas A.1, A.2 e A.3 da ABNT NBR 16683:2018, Versão Corrigida:2020. Esta auditoria
não acrescenta produtos, corrige valores normativos ou atribui fabricante ao
catálogo-base. Sua finalidade é registrar cobertura e divergências das fontes.

## Fontes congeladas para a comparação

| Fonte | Documento e páginas conferidas | SHA-256 do PDF baixado |
|---|---|---|
| ABNT | Exemplar primário fornecido pelo usuário; edição 29/11/2018, correção 23/04/2020; A.1 pp. 6–9, A.2 pp. 10–11, A.3 p. 12 | `dfda6bd8d496dfaf435503d0145fa0ac6d5bb47515c06975bba4bb54fbccddbd` |
| Gerdau | [Barras e Perfis — Tabela de bolso](https://gsn.gerdau.com/sites/gsn_gerdau/files/downloadable_files/Barras-e-Perfis-Tabela-de-bolso.pdf), 14 páginas; redondas p. 8, chatas p. 9, quadradas p. 10; marca editorial `03/19` conferida na p. 14 | `b4bb07ff74652fdc5989665447f57766d0179b91faa6bf971e2d6f1683662501` |
| ArcelorMittal | [Guia do Aço](https://conexao.arcelormittal.com.br/catalogos/barra-chata_1?location=%2Fprodutos%2F), 92 páginas, Fevereiro 2026 impresso na p. 92; listas comerciais pp. 5 e 7; massas genéricas pp. 90–91 | `7a1bed2dd320344ee57089d20b6ba0228b96e3b7f425e7c8f1cf727dde48cb42` |

Os PDFs comerciais foram baixados somente em `test-results/nbr16683-audit/`,
pasta ignorada. O PDF ABNT foi lido no caminho fornecido, sem cópia para o
repositório. Não se presume que uma tabela comercial publicada garanta estoque,
classe de aço ou conformidade de qualquer lote. A vigência atual da publicação
ABNT não foi confirmada no catálogo online; edição e correção foram conferidas
no exemplar primário.

A comparação comercial foi feita com os intermediários locais
`test-results/nbr16683-audit/compare_commercial.py` e
`test-results/nbr16683-audit/commercial-comparison.json`. Na sessão de auditoria,
`python -X utf8 test-results/nbr16683-audit/compare_commercial.py` relê o snapshot
ABNT e os PDFs `gerdau-barras-perfis.pdf` e `arcelor-guia-aco.pdf` dessa pasta,
usando PyMuPDF. Esses arquivos são ignorados, não são distribuídos no pacote
nem estarão disponíveis em um checkout novo. O relatório registra método,
URLs, hashes e resultados, mas não promete reprodução automática da auditoria
comercial após um checkout. O extrator normativo distribuído em `scripts/`
tem finalidade separada e continua exigindo o exemplar primário fornecido.

## Método e cobertura

As dimensões foram comparadas numericamente, com decimais exatos: `25,4` e
`25,40` são iguais; `26,98` e `26,99` são diferentes. Não se aplicou tolerância
geométrica, conversão de polegadas, substituição por massa semelhante ou
arredondamento para aumentar a cobertura. Para chatas, largura e espessura são
uma chave ordenada. Designações equivalentes diferem somente na escrita de
frações mistas, aspas e símbolo de multiplicação.

| Fonte comercial | Família | Entradas na fonte | Coincidência exata em mm | Mesma designação, mm diferentes | Só designação, mm não publicados | Linhas normativas não localizadas |
|---|---|---:|---:|---:|---:|---:|
| Gerdau PDF | Redonda | 48 | 38/53 | 9 | 0 | 6 |
| Gerdau PDF | Quadrada | 13 | 13/19 | 0 | 0 | 6 |
| Gerdau PDF | Chata | 83 células preenchidas | 70/92 | 0 | 0 | 22 |
| ArcelorMittal comercial | Redonda | 56 | 38/53 | 7 | 0 | 8 |
| ArcelorMittal comercial | Quadrada | Sem lista comercial localizada | 0/19 | 0 | 0 | 19 |
| ArcelorMittal comercial | Chata | 107 | 4/92 | 0 | 67 | 21 |

Estas contagens resultam da extração das tabelas completas indicadas e da
comparação com todas as 53/19/92 linhas normativas. As páginas foram renderizadas
e inspecionadas, incluindo cabeçalhos e células. Na extração da matriz Gerdau,
o texto `152,40` atravessou uma fronteira de célula: os dois últimos cabeçalhos
foram alinhados com a imagem, `120,65` e `152,40`. Isso corrige a extração, sem
alterar o conteúdo da fonte.

O balanço abaixo lê a comparação na direção inversa, da fonte comercial para
as tabelas normativas. `D` permanece separado: diferença nos mm de uma
designação existente não é contada como uma nova bitola normativa. `P` também
permanece separado porque a fonte não informa os mm.

| Fonte | Família | Fora das dimensões exatas ABNT, com mm explícitos | Dessas, correspondências D | Adicionais com mm explícitos, sem correspondência de designação | Adicionais só em polegadas, sem correspondência de designação |
|---|---|---:|---:|---:|---:|
| Gerdau PDF | Redonda | 10 | 9 | 1 | 0 |
| Gerdau PDF | Quadrada | 0 | 0 | 0 | 0 |
| Gerdau PDF | Chata | 13 | 0 | 13 | 0 |
| ArcelorMittal comercial | Redonda | 18 | 7 | 11 | 0 |
| ArcelorMittal comercial | Quadrada | Não há lista | — | — | — |
| ArcelorMittal comercial | Chata | 23 | 0 | 23 | 13 |

Assim, os adicionais comerciais além de E/D/P são 1/0/13 na Gerdau e
11/sem lista/36 na ArcelorMittal, respectivamente redonda/quadrada/chata.
As 36 chatas adicionais da ArcelorMittal se dividem em 23 entradas métricas
e 13 designações sem mm. As 67 entradas P que já correspondem a designações
normativas não entram nesses 36 adicionais. Nenhum desses conjuntos é
importado no catálogo-base.

A tabela ArcelorMittal de chatas p. 7 publica `-` na coluna mm para as entradas
em polegadas. Por isso 67 coincidências de designação não são contadas como
coincidências dimensionais verificadas. As quatro coincidências métricas são
130 × 11, 130 × 12, 130 × 16 e 130 × 19 mm. A lista de redondas p. 5 é acompanhada
na p. 6 por requisitos de aplicações mecânicas da NBR 11294:2025; a seção de
chatas p. 8 cita a NBR 16683:2018. Uma correspondência comercial de dimensão
não transforma a primeira em certificação estrutural pela segunda.

## Comprimentos e referências de aço da Gerdau

As páginas 8–10 da Tabela de bolso identificam dimensões e massa linear, mas
não fixam comprimentos comerciais para essas três famílias nem citam uma
norma dimensional específica. O aviso de tolerância de comprimento de
0/+10 cm aparece nas páginas 3–6, junto aos perfis; não foi estendido
automaticamente às barras das páginas 8–10. A página atual de redondas
menciona comprimentos diferentes sem discriminar valores. Portanto, esta
fonte auditada não comprova um comprimento único de 6 m ou 12 m para cada
bitola Gerdau. Os comprimentos de 6 m e 12 m da seção 4.4 da NBR 16683 são
informação normativa separada, não confirmação de oferta comercial.

O [Catálogo Barras e Perfis Gerdau](https://gsn.gerdau.com/sites/gsn_gerdau/files/downloadable_files/catalogo-barras-e-perfis.pdf),
com marca editorial `02/14`, distingue na p. 6 a linha estrutural ASTM/NBR
7007 da linha SAE. Cita A36/MR250 para redondas, quadradas e chatas;
A572/AR350 ou AR415 inclui chatas; A588/AR350 COR inclui redondas e chatas,
sob consulta. SAE 1020 inclui redondas e quadradas; SAE 1045 inclui redondas
e chatas. Essas referências de material e aplicação são históricas e não
comprovam que todas as bitolas das tabelas existam em todas as qualidades.
O catálogo antecede a NBR 16683:2018 e não foi usado para atestar conformidade
dimensional com ela.

Não se transferiram comprimentos de produtos diferentes. Por exemplo, a
[redonda trefilada Gerdau](https://mais.gerdau.com.br/produtos/barra-redonda-trefilada)
informa 5–7 m, e o [catálogo de barras trefiladas](https://gsn.gerdau.com/sites/gsn_gerdau/files/downloadable_files/catalogo-barras-trefiladas.pdf)
cita NBR 8580. Essas informações pertencem a barras trefiladas, fora do
conjunto laminado comparado neste relatório.

## Diferenças dimensionais e de massa

As diferenças de conversão/publicação de diâmetros estão registradas em tabela
própria abaixo. Não foram classificadas automaticamente como erros do fabricante
ou erratas da norma. Em particular, os valores Gerdau 46,40 e 95,35 mm foram
conferidos visualmente no PDF e não são erros introduzidos pela extração.

Para massa, somente pares com dimensões nominais exatamente iguais entram na
comparação Gerdau. O PDF publica duas casas decimais e a norma publica três.
O diagnóstico de compatibilidade de precisão usa diferença absoluta até
0,0055 kg/m, correspondente à soma das meias unidades das últimas casas
publicadas. Isso não prova qual arredondamento foi usado, nem constitui
tolerância de fornecimento. Diferenças maiores permanecem diferenças entre
fontes, sem substituição da massa normativa.

| Família | Pares exatos em mm | Massas numericamente iguais | Demais pares compatíveis com a precisão declarada | Diferença acima de 0,0055 kg/m |
|---|---:|---:|---:|---:|
| Redonda | 38 | 5 | 24 | 9 |
| Quadrada | 13 | 10 | 2 | 1 |
| Chata | 70 | 7 | 61 | 2 |

Exemplos que não se resumem a arredondamento: quadrada 44,45 mm, norma
15,510 kg/m e Gerdau 15,19 kg/m; chatas 88,90 × 15,88 e 88,90 × 19,05 mm,
respectivamente 10,847/11,08 e 13,047/13,29 kg/m. As massas orientativas da
norma permanecem intactas. A matriz Gerdau também publica 15,19 kg/m para
76,20 × 38,10 mm; a massa parecida de uma linha normativa com espessura
diferente não autoriza tratar as duas geometrias como iguais.

As tabelas ArcelorMittal pp. 90–91 são de consulta genérica de massas, incluindo
formas sem lista comercial nesse guia. Foram conferidas separadamente: há
30 diâmetros redondos e 15 lados quadrados exatamente iguais aos da norma;
outros 16/4 pares correspondem apenas à designação com mm diferentes. Não
há tabela de chatas nessa seção. Por exemplo, quadrada 38,10 mm aparece com
11,38 kg/m, enquanto A.3 publica 11,150 kg/m. Esses valores não alimentam o
catálogo ABNT e não demonstram disponibilidade comercial de quadradas.

## Divergências entre canais oficiais

A página atual [Barra Redonda Gerdau](https://mais.gerdau.com.br/produtos/barra-redonda)
tem 48 linhas, mas difere do PDF: 15/16 aparece como 23,80 mm, contra 23,81 mm;
2 polegadas tem 15,90, contra 15,91 kg/m; 2.1/16 tem 116,92, contra 16,92 kg/m.
Assim, a cobertura exata dessa página é 37/53, com dez correspondências de
designação e mm diferentes, mantendo seis linhas não localizadas. Não se
escolheu silenciosamente um valor para substituir o outro.

A página [Barra Quadrada Gerdau](https://mais.gerdau.com.br/produtos/barra-quadrada)
tem 14 linhas e inclui 11/16, 17,46 mm, 2,39 kg/m, ausente no PDF. Sua cobertura
exata é 14/19. O relatório conserva o resultado de cada publicação separadamente.

No guia ArcelorMittal, o resumo p. 5 indica espessura mínima de chata 3,75 mm,
enquanto a lista p. 7 inclui 2,50 mm. As listas explícitas foram auditadas sem
usar intervalos gerais para fabricar combinações. Uma URL antiga do guia não
foi usada como identificador da edição: a revisão corresponde ao PDF baixado,
ao hash registrado e à data efetivamente impressa.

## Resultado para a Etapa B

Nenhuma diferença comercial elimina uma das 164 entradas normativas ou
autoriza trocar seus valores. Produtos adicionais das fontes comerciais não
são acrescentados ao catálogo-base. Nenhuma tolerância comercial é usada
para deformar a geometria nominal, e nenhuma massa é recalculada para apagar
uma divergência. Eventuais catálogos comerciais futuros precisam identificar
publicação, edição, fabricante e diferenças conhecidas de maneira própria.

## Matriz completa de conferência

Cada linha abaixo é uma entrada do snapshot ABNT. `E` = dimensões exatamente
iguais; `D` = mesma designação com mm diferentes; `P` = só designação publicada,
sem mm verificáveis; `—` = não localizada na lista comercial auditada.
O identificador de origem contém tabela, página impressa e linha naquela página.
As colunas comerciais referem-se aos PDFs identificados por hash acima.

### Barra Redonda

| Origem ABNT | Dimensões nominais (mm) | Gerdau | ArcelorMittal |
|---|---|:---:|:---:|
| A.2 p.10 l.1 | 6,35 | E | E |
| A.2 p.10 l.2 | 7,94 | E | E |
| A.2 p.10 l.3 | 9,53 | E | E |
| A.2 p.10 l.4 | 11,11 | — | E |
| A.2 p.10 l.5 | 11,50 | — | — |
| A.2 p.10 l.6 | 12,00 | — | E |
| A.2 p.10 l.7 | 12,70 | E | E |
| A.2 p.10 l.8 | 14,29 | E | E |
| A.2 p.10 l.9 | 15,88 | E | E |
| A.2 p.10 l.10 | 17,46 | E | — |
| A.2 p.10 l.11 | 19,05 | E | E |
| A.2 p.10 l.12 | 20,64 | E | — |
| A.2 p.10 l.13 | 22,23 | E | D |
| A.2 p.10 l.14 | 23,81 | E | — |
| A.2 p.10 l.15 | 25,40 | E | E |
| A.2 p.10 l.16 | 26,98 | D | D |
| A.2 p.10 l.17 | 28,58 | E | E |
| A.2 p.10 l.18 | 30,16 | E | E |
| A.2 p.10 l.19 | 31,75 | E | E |
| A.2 p.10 l.20 | 34,93 | E | E |
| A.2 p.10 l.21 | 36,51 | E | E |
| A.2 p.10 l.22 | 38,10 | E | E |
| A.2 p.10 l.23 | 39,68 | D | D |
| A.2 p.10 l.24 | 41,28 | E | E |
| A.2 p.10 l.25 | 42,86 | E | E |
| A.2 p.11 l.1 | 44,45 | E | E |
| A.2 p.11 l.2 | 46,04 | D | — |
| A.2 p.11 l.3 | 47,62 | D | D |
| A.2 p.11 l.4 | 50,80 | E | E |
| A.2 p.11 l.5 | 52,38 | D | D |
| A.2 p.11 l.6 | 53,98 | E | E |
| A.2 p.11 l.7 | 57,15 | E | E |
| A.2 p.11 l.8 | 58,73 | D | D |
| A.2 p.11 l.9 | 60,33 | E | E |
| A.2 p.11 l.10 | 61,91 | E | E |
| A.2 p.11 l.11 | 63,50 | E | E |
| A.2 p.11 l.12 | 65,09 | D | E |
| A.2 p.11 l.13 | 66,68 | E | E |
| A.2 p.11 l.14 | 68,26 | — | E |
| A.2 p.11 l.15 | 69,85 | E | E |
| A.2 p.11 l.16 | 71,43 | D | — |
| A.2 p.11 l.17 | 73,03 | E | E |
| A.2 p.11 l.18 | 76,20 | E | E |
| A.2 p.11 l.19 | 77,79 | E | E |
| A.2 p.11 l.20 | 79,38 | E | E |
| A.2 p.11 l.21 | 82,55 | E | E |
| A.2 p.11 l.22 | 87,31 | E | E |
| A.2 p.11 l.23 | 88,90 | E | E |
| A.2 p.11 l.24 | 95,25 | D | E |
| A.2 p.11 l.25 | 96,84 | — | — |
| A.2 p.11 l.26 | 98,42 | — | D |
| A.2 p.11 l.27 | 101,60 | E | E |
| A.2 p.11 l.28 | 103,19 | E | — |

### Barra Quadrada

| Origem ABNT | Dimensões nominais (mm) | Gerdau | ArcelorMittal |
|---|---|:---:|:---:|
| A.3 p.12 l.1 | 6,35 | E | — |
| A.3 p.12 l.2 | 7,94 | E | — |
| A.3 p.12 l.3 | 9,53 | E | — |
| A.3 p.12 l.4 | 12,70 | E | — |
| A.3 p.12 l.5 | 15,88 | E | — |
| A.3 p.12 l.6 | 17,46 | — | — |
| A.3 p.12 l.7 | 19,05 | E | — |
| A.3 p.12 l.8 | 20,64 | — | — |
| A.3 p.12 l.9 | 22,23 | E | — |
| A.3 p.12 l.10 | 25,40 | E | — |
| A.3 p.12 l.11 | 28,58 | E | — |
| A.3 p.12 l.12 | 31,75 | E | — |
| A.3 p.12 l.13 | 33,34 | — | — |
| A.3 p.12 l.14 | 38,10 | E | — |
| A.3 p.12 l.15 | 39,69 | — | — |
| A.3 p.12 l.16 | 44,45 | E | — |
| A.3 p.12 l.17 | 46,04 | — | — |
| A.3 p.12 l.18 | 50,80 | E | — |
| A.3 p.12 l.19 | 52,39 | — | — |

### Barra Chata

| Origem ABNT | Dimensões nominais (mm) | Gerdau | ArcelorMittal |
|---|---|:---:|:---:|
| A.1 p.6 l.1 | 9,53 × 3,18 | E | P |
| A.1 p.6 l.2 | 12,70 × 3,18 | E | P |
| A.1 p.6 l.3 | 12,70 × 4,76 | E | P |
| A.1 p.6 l.4 | 12,70 × 6,35 | E | P |
| A.1 p.6 l.5 | 15,88 × 3,18 | E | P |
| A.1 p.6 l.6 | 15,88 × 4,76 | E | P |
| A.1 p.6 l.7 | 15,88 × 6,35 | E | P |
| A.1 p.6 l.8 | 19,05 × 3,18 | E | P |
| A.1 p.6 l.9 | 19,05 × 4,76 | E | P |
| A.1 p.6 l.10 | 19,05 × 6,35 | E | P |
| A.1 p.6 l.11 | 22,23 × 3,18 | E | P |
| A.1 p.6 l.12 | 22,23 × 4,76 | E | P |
| A.1 p.6 l.13 | 22,23 × 6,35 | E | P |
| A.1 p.6 l.14 | 22,23 × 7,94 | — | — |
| A.1 p.7 l.1 | 22,23 × 12,70 | E | — |
| A.1 p.7 l.2 | 25,40 × 3,18 | E | P |
| A.1 p.7 l.3 | 25,40 × 4,76 | E | P |
| A.1 p.7 l.4 | 25,40 × 6,35 | E | P |
| A.1 p.7 l.5 | 25,40 × 7,94 | E | — |
| A.1 p.7 l.6 | 25,40 × 9,53 | E | — |
| A.1 p.7 l.7 | 31,75 × 3,18 | E | P |
| A.1 p.7 l.8 | 31,75 × 4,76 | E | P |
| A.1 p.7 l.9 | 31,75 × 6,35 | E | P |
| A.1 p.7 l.10 | 31,75 × 7,94 | E | P |
| A.1 p.7 l.11 | 31,75 × 9,53 | E | P |
| A.1 p.7 l.12 | 31,75 × 12,70 | E | P |
| A.1 p.7 l.13 | 38,10 × 3,18 | E | P |
| A.1 p.7 l.14 | 38,10 × 4,76 | E | P |
| A.1 p.7 l.15 | 38,10 × 6,35 | E | P |
| A.1 p.7 l.16 | 38,10 × 7,94 | E | P |
| A.1 p.7 l.17 | 38,10 × 9,53 | E | P |
| A.1 p.7 l.18 | 38,10 × 12,70 | E | P |
| A.1 p.7 l.19 | 38,10 × 15,88 | E | P |
| A.1 p.7 l.20 | 44,45 × 12,70 | — | — |
| A.1 p.7 l.21 | 44,45 × 6,35 | — | P |
| A.1 p.7 l.22 | 50,80 × 3,18 | E | P |
| A.1 p.7 l.23 | 50,80 × 4,76 | E | P |
| A.1 p.7 l.24 | 50,80 × 6,35 | E | P |
| A.1 p.7 l.25 | 50,80 × 7,94 | E | P |
| A.1 p.7 l.26 | 50,80 × 9,53 | E | P |
| A.1 p.7 l.27 | 50,80 × 12,70 | E | P |
| A.1 p.7 l.28 | 50,80 × 15,88 | E | P |
| A.1 p.7 l.29 | 50,80 × 19,05 | E | P |
| A.1 p.8 l.1 | 50,80 × 25,40 | E | — |
| A.1 p.8 l.2 | 63,50 × 4,76 | — | — |
| A.1 p.8 l.3 | 63,50 × 6,35 | E | P |
| A.1 p.8 l.4 | 63,50 × 7,94 | E | P |
| A.1 p.8 l.5 | 63,50 × 9,53 | E | P |
| A.1 p.8 l.6 | 63,50 × 12,70 | E | P |
| A.1 p.8 l.7 | 63,50 × 15,88 | E | P |
| A.1 p.8 l.8 | 63,50 × 19,05 | E | P |
| A.1 p.8 l.9 | 69,85 × 12,70 | — | — |
| A.1 p.8 l.10 | 76,20 × 6,35 | E | P |
| A.1 p.8 l.11 | 76,20 × 7,94 | E | P |
| A.1 p.8 l.12 | 76,20 × 9,53 | E | P |
| A.1 p.8 l.13 | 76,20 × 12,70 | E | P |
| A.1 p.8 l.14 | 76,20 × 15,88 | E | P |
| A.1 p.8 l.15 | 76,20 × 19,05 | E | P |
| A.1 p.8 l.16 | 76,20 × 25,40 | — | P |
| A.1 p.8 l.17 | 76,20 × 28,57 | — | — |
| A.1 p.8 l.18 | 76,20 × 31,75 | — | — |
| A.1 p.8 l.19 | 76,20 × 50,80 | E | — |
| A.1 p.8 l.20 | 88,90 × 6,35 | — | — |
| A.1 p.8 l.21 | 88,90 × 9,52 | — | — |
| A.1 p.8 l.22 | 88,90 × 12,70 | — | P |
| A.1 p.8 l.23 | 88,90 × 15,88 | E | P |
| A.1 p.8 l.24 | 88,90 × 19,05 | E | — |
| A.1 p.8 l.25 | 101,60 × 6,35 | E | P |
| A.1 p.8 l.26 | 101,60 × 7,94 | E | P |
| A.1 p.8 l.27 | 101,60 × 9,53 | E | P |
| A.1 p.8 l.28 | 101,60 × 12,70 | E | P |
| A.1 p.8 l.29 | 101,60 × 15,88 | E | P |
| A.1 p.9 l.1 | 101,60 × 19,05 | E | P |
| A.1 p.9 l.2 | 101,60 × 25,40 | E | P |
| A.1 p.9 l.3 | 152,40 × 6,35 | E | P |
| A.1 p.9 l.4 | 152,40 × 7,94 | E | P |
| A.1 p.9 l.5 | 152,40 × 9,53 | E | P |
| A.1 p.9 l.6 | 152,40 × 12,70 | E | P |
| A.1 p.9 l.7 | 152,40 × 15,88 | E | P |
| A.1 p.9 l.8 | 152,40 × 19,05 | E | P |
| A.1 p.9 l.9 | 152,40 × 25,40 | E | P |
| A.1 p.9 l.10 | 130,00 × 10,00 | — | — |
| A.1 p.9 l.11 | 130,00 × 11,00 | — | E |
| A.1 p.9 l.12 | 130,00 × 12,00 | — | E |
| A.1 p.9 l.13 | 130,00 × 13,00 | — | — |
| A.1 p.9 l.14 | 130,00 × 14,00 | — | — |
| A.1 p.9 l.15 | 130,00 × 15,00 | — | — |
| A.1 p.9 l.16 | 130,00 × 16,00 | — | E |
| A.1 p.9 l.17 | 130,00 × 18,00 | — | — |
| A.1 p.9 l.18 | 130,00 × 19,00 | — | E |
| A.1 p.9 l.19 | 130,00 × 21,00 | — | — |
| A.1 p.9 l.20 | 130,00 × 22,00 | — | — |

## Correspondências de designação com mm diferentes

A coluna ABNT conserva exatamente as dimensões publicadas. As duas fontes comerciais
são independentes; a ausência de uma delas em uma linha não significa ausência
na outra. Esta tabela não altera a matriz de coincidências exatas.

| Família | Designação (pol) | ABNT (mm) | Fonte comercial | Publicado (mm) |
|---|---|---|---|---|
| Barra Redonda | 1.1/16 | 26,98 | Gerdau PDF p.8 | 26,99 |
| Barra Redonda | 1.9/16 | 39,68 | Gerdau PDF p.8 | 39,69 |
| Barra Redonda | 1.13/16 | 46,04 | Gerdau PDF p.8 | 46,40 |
| Barra Redonda | 1.7/8 | 47,62 | Gerdau PDF p.8 | 47,63 |
| Barra Redonda | 2.1/16 | 52,38 | Gerdau PDF p.8 | 52,39 |
| Barra Redonda | 2.5/16 | 58,73 | Gerdau PDF p.8 | 58,74 |
| Barra Redonda | 2.9/16 | 65,09 | Gerdau PDF p.8 | 65,08 |
| Barra Redonda | 2.13/16 | 71,43 | Gerdau PDF p.8 | 71,44 |
| Barra Redonda | 3.3/4 | 95,25 | Gerdau PDF p.8 | 95,35 |
| Barra Redonda | 7/8 | 22,23 | ArcelorMittal p.5 | 22,22 |
| Barra Redonda | 1.1/16 | 26,98 | ArcelorMittal p.5 | 26,99 |
| Barra Redonda | 1.9/16 | 39,68 | ArcelorMittal p.5 | 39,69 |
| Barra Redonda | 1.7/8 | 47,62 | ArcelorMittal p.5 | 47,60 |
| Barra Redonda | 2.1/16 | 52,38 | ArcelorMittal p.5 | 52,39 |
| Barra Redonda | 2.5/16 | 58,73 | ArcelorMittal p.5 | 58,74 |
| Barra Redonda | 3.7/8 | 98,42 | ArcelorMittal p.5 | 98,43 |
