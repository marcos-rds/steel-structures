# Aço Maciço — Etapa A

Infraestrutura nominal para três famílias, sem catálogo comercial novo e sem
atribuir dados a ABNT, Gerdau ou ArcelorMittal.

## Geometria e propriedades

Categoria `solid-steel` (Aço Maciço), tipo `solid_section`:

| Série | Variante | Parâmetros em mm | Representação nominal |
|---|---|---|---|
| `round-bar` | `circular` | `d > 0` | Círculo maciço exato |
| `square-bar` | `square` | `b > 0` | Quadrado com cantos vivos |
| `flat-bar` | `rectangular` | `b > t > 0` | Retângulo B em X, t em Y |

`profiles/solid_sections.py` produz `SectionGeometry2D` por builders puros.
Os caminhos básicos de círculo/retângulo são compartilhados com os tubulares
em `profiles/section_paths.py`. O círculo usa arcos analíticos; o adaptador
FreeCAD existente constrói a Face e o StructuralMember faz a extrusão normal.
Não há contorno interno, raio opcional, nova extrusão ou novo tipo paramétrico.
`Detailed` e `Simplified` produzem a mesma seção; `Gerar raios` fica oculto.

As propriedades técnicas são calculadas por expressões puras, sem OCC/Qt:

| Seção | A | Ix / Iy | Wx / Wy | rx / ry |
|---|---|---|---|---|
| Redonda | πD²/4 | πD⁴/64, iguais | πD³/32, iguais | D/4, iguais |
| Quadrada | B² | B⁴/12, iguais | B³/6, iguais | B/√12, iguais |
| Chata | Bt | Bt³/12 / tB³/12 | Bt²/6 / tB²/6 | t/√12 / B/√12 |

X-X é horizontal; Y-Y é vertical. Na chata, Iy/Ix = (B/t)². Dimensões não
são trocadas nem normalizadas como H×B. A rotação da seção não altera essas
propriedades locais. `CatalogArea` recebe a área técnica nominal, convertida
pela facade existente de mm² para cm²; a área da Face é um contrato separado.

## Fixtures e origem da massa

`catalogs/dev/solid_sections_validation.json` contém somente Ø20, Ø50,
20×20, 50×50, 50×6,35 e 100×10. IDs são independentes de locale.
O loader descobre os JSON de `catalogs/dev` após os catálogos da raiz;
reabrir o Browser não depende de registro em runtime.

O Browser identifica a origem já no subtítulo:
**Steel Structures — fixture de desenvolvimento**. A aba Fonte identifica
massa sintética e densidade de referência. Não há fabricante ou norma declarados.

Contrato de massa, sem mudar o schema persistente dos membros:

- `catalog.source.source_type = development_fixture` identifica o catálogo dev.
- `source_metadata.mass_type = calculated_fixture`, com
  `density_kg_m3 = 7850`, permite calcular exclusivamente a massa das fixtures
  maciças: `mass_per_length_kg_m = area_mm2 * density_kg_m3 * 1e-6`.
- Massa física pode faltar no JSON dev; é resolvida antes de chegar à facade.
  Massa fornecida junto ao cálculo deve coincidir; conflitos são rejeitados.
- Massa publicada em kg/m pode usar `source_mass_per_length_kg_m` e
  `mass_type = published`, sem exigir peso por 6 m. A resolução ocorre antes
  do cálculo de qualquer família, inclusive tubulares. Valores publicados
  não são substituídos por densidade teórica.
- O formato Tuper legado mantém `source_weight_p_kg_per_6m`,
  `source_weight_basis_mm = 6000` e massa física igual a p/6. Quando presentes,
  peso e base devem vir juntos. Nenhum arquivo Tuper foi alterado.
- Página e designação de origem são opcionais; valores presentes são validados.

## Browser, inserção e modelo

Cotas: `Ø valor` na redonda; `(b) valor` na quadrada; `(b)` horizontal e `(t)`
vertical na chata. Anotações permanecem em espaço de tela; auto-fit e contorno
cosmético preservam a proporção geométrica, inclusive no caso de teste 100×3.

Redondas oferecem centroide e quatro faces (cinco pontos). Quadradas/chatas
oferecem também os quatro cantos (nove pontos). IDs existentes `top_left` etc.
são preservados; aliases `outer_top_left`, `outer_top_right`,
`outer_bottom_left`, `outer_bottom_right` resolvem nos mesmos cantos, sem
duplicar hotspots. A mini-preview usa o estilo e o marcador existentes.

Rotation continua disponível nas três famílias, incluindo a redonda com
inserção excêntrica. A propriedade persistente existente chama-se `Rotation`.
Chata a 90° fica em cutelo. O pipeline de Member/Pilar e AxisSource permanece
inalterado: eixo nominal, extensões e ajustes físicos continuam independentes.

## Verificação e reprodução

Testes puros: `tests/test_solid_sections.py` e `tests/test_solid_sections_ui.py`.
Cobrem dimensões obrigatórias, fórmulas, simetria, eixos, modos, validação de
origem/massa, reload, inserções e renderer. A revisão detectou alias numérico
preexistente no integrador genérico de semicírculos: a correção mínima semeia
intervalos angulares antes do Simpson adaptativo; regressões cobrem círculo
maciço e anel CHS. As propriedades técnicas novas continuam usando fórmulas.

`tests/manual_solid_sections_validation.py` deve ser executado no Python do
FreeCAD com a raiz do repositório no `sys.path`. Use `runpy.run_path(caminho,
run_name="__main__")` para evitar conflitos com pacotes `tests` de outras
workbenches. O roteiro cria um documento e FCStd temporários, não edita documentos
existentes e deixa o documento reaberto disponível para inspeção.

O roteiro passou em 128 verificações no FreeCAD 1.1.3 via MCP: seis sólidos,
volume positivo/Shape válida, massa, modos, extensões, X/Y/Z/inclinado, inserção
excêntrica, rotação 0/90, três Draft Lines vinculadas, alterações de endpoints,
preview SourceAxis e sinais do painel nativo, cor, cancelamento, LengthLimit,
PlaneCut ortogonal/oblíquo em duas extremidades com Gaps, Placement acumulado,
Browser reaberto, raios ocultos, chatas finas e persistência dos dez membros.
As cotas e proporções foram também inspecionadas em capturas do Qt real.

## Limites e próxima etapa

- Fixtures são dados de desenvolvimento; sua retirada/substituição futura deve
  tratar referências de documentos existentes. Não remover os IDs silenciosamente.
- Separar futuramente **canonical section versus commercial offers**. Esta etapa
  não altera identidade de perfis, resolução de designações duplicadas ou ofertas.
- Catálogos comerciais, tolerâncias, materiais e outras famílias continuam fora
  do escopo. Não inferir raio de canto nem geometria a partir da massa publicada.
- Validação visual/funcional do usuário é necessária antes de qualquer commit.
