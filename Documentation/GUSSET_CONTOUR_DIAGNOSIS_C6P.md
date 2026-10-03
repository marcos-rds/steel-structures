# Diagnóstico de contornos após C6-P — propostas para aprovação

> **Registro histórico anterior às famílias geométricas finais.** Este documento
> registra o diagnóstico que levou à arquitetura final; alguns contornos e
> decisões foram posteriormente substituídos. O contrato técnico atual está em
> [GUSSET_PLATES.md](GUSSET_PLATES.md).

Referência lida: `../testeC6.FCStd`, sem alterações. Inspeção do `Document.xml`,
`AppliedState` e `SourceSignature` das chapas; reconstrução pelo pipeline Python
local. Não foi feita validação visual no FreeCAD nem inspeção do BRep com Part.
Os pontos persistidos e os recomputados estão separados abaixo: o documento
contém geometria anterior a algumas correções locais. Coordenadas em mm, no plano
local da chapa, relativas ao nó. Nenhuma geometria foi modificada nesta tarefa.

## Conclusão arquitetural

O pipeline conhece envelopes físicos e restrições locais, mas não contém um
contrato completo de **forma convencional por configuração do encontro**.
Assim, uma chapa pode satisfazer os limites implementados e ainda ter proporções,
quinas e transições pouco adequadas à forma desejada pelo usuário.

1. `trusses/gussets.py::_corridors` projeta seções, inserções, rotações e componentes.
   Esses corredores são dados de cobertura necessários. O uso simultâneo de suas
   direções e normais como orientações do contorno cria facetas sem função explícita
   de fabricação; um banzo passante também fornece corredores em dois sentidos.
2. `connections/gusset.py::_regularized_envelope` constrói um polígono convexo por
   interseção de limites nessas direções (k-DOP), com margem. Isso não escolhe uma
   família de chapa: o número e a orientação das faces emergem dos participantes.
3. `_chord_support_lines` impõe o contato físico no banzo, considerando a posição
   transversal e a faixa de material. A extensão externa explicitamente selecionada
   usa `outline_band`, preservando a C6-L. Esse contrato deve continuar prioritário.
4. `_web_end_lines` cria `WEB_END_CAP` perpendicular a cada barra, inicialmente em
   sobreposição + margem, podendo afastá-lo por causa de outro participante.
   Com exatamente duas barras, pode omitir o cap se a extensão exceder o limite
   local. São restrições globais de meio-plano para requisitos que têm origem local;
   suas interseções podem alongar faces ou gerar bicos.
5. `_web_sector_bridge_lines` só trata dois terminais, sem barra passante da alma.
   Compara ponte paralela ao banzo e conexão direta por comprimento; a cumeeira
   tem regra pela bissetriz. A C6-P dispensa a ponte para diagonal + montante.
   Não existe escolha uniforme da sequência de faces para todos os encontros.
6. `_regularize_web_cap_chains` e `semantic_outline_regularization` tentam corrigir
   facetas depois da construção. Protegem suportes semânticos, contêm o polígono
   anterior e usam limites locais (uma faceta adjacente; proporção 0,18).
   Uma borda indesejada pode estar protegida como semântica e não ser removível.

**Área mínima:** não há minimização global de área no pipeline inspecionado.
`polygon_area > TOLERANCE` verifica não degeneração. A ponte prefere menor vão,
e os envelopes tendem à compacidade; isso não equivale a uma função de fabricação.
Minimizar área, comprimento ou número de vértices isoladamente não resolve o problema.

## Caso 1 — encontro inferior comum, diagonal + montante

- Objeto: `StructuralTruss002`, Parallel / Pratt.
- NodeKey: `B_S_MAIN_1_6`; chapa `StructuralGussetPlate014`.
- Banzo inferior passante, diagonal terminando, montante iniciando.
- Persistido e recomputado coincidem: pentágono
  `(-37,854;-11,59), (36,5;-11,59), (36,5;175),
  (-63,359;175), (-140,072;111,072)`.
- Faces: contato no banzo, lateral livre, cap horizontal do montante,
  cap inclinado da diagonal, lateral livre. Não há `WEB_SECTOR_BRIDGE`.

O encontro entre caps dá uma quina determinada pelas duas barras, e não por uma
escolha explícita de forma de chapa. O ponto lateral `(-140,072;111,072)` e a
extensão horizontal do cap são consequências da interseção dos suportes. Não há
evidência de erro numérico nesses pontos; a inadequação é de forma pretendida.
O nó superior `T_S_MAIN_1_3` da mesma treliça apresenta o mesmo mecanismo.

**Proposta:** família pentagonal de encontro simples, definida de antemão por
contato no banzo, duas laterais e fechamento em dois segmentos ligados diretamente.
Usar os corredores para dimensionar a cobertura dessa família, classificando quais
caps precisam ser bordas finais e quais são apenas requisitos de cobertura. Se o
usuário preferir uma única borda livre, avaliar um trapézio envolvente como variante
explícita, admitindo maior área. Não selecionar automaticamente a menor chapa.

**Aceitação proposta:** preservação da margem configurada nos terminais livres e
da sobreposição; contato no banzo inalterado; polígono simples; ausência de faceta
intermediária entre os dois caps na variante pentagonal; estabilidade da sequência
de faces sob pequenas variações de altura, rotação e perfil. A forma final depende
da aprovação visual, sem impor comprimentos mínimos de fabricação inventados.

## Caso 2 — nó intermediário DuoPitch

- Objeto: `StructuralTruss005`, DuoPitch / Warren.
- NodeKey: `T_S_LEFT_1_3`; chapa `StructuralGussetPlate024`.
- Banzo superior passante inclinado, diagonal + montante.
- Persistido: hexágono com transição
  `(16,315;-175) → (137,941;-126,349)` entre os caps.
- Recomputado na C6-P: pentágono
  `(118,481;-175), (182,353;-15,320), (56,423;35,052),
  (-53,5;-8,917), (-53,5;-175)`.

A ponte persistida gerava um chanfro adicional. A C6-P já a suprime neste encontro,
mas os caps agora se prolongam até uma interseção remota, em `(118,481;-175)`.
Eliminar a ponte não define, por si só, a proporção convencional desejada. A base
inclina com o banzo enquanto o cap do montante permanece horizontal; essa combinação
explica a assimetria, sem provar que todo pentágono assimétrico seja inadequado.

**Proposta:** aplicar a mesma família explícita do encontro simples num referencial
orientado pelo banzo, mantendo a direção física dos requisitos das barras. Avaliar
como alternativas aprováveis o fechamento pelos dois caps ou uma borda livre única
envolvente. A escolha deve preceder o cálculo dos vértices e não surgir de um corte
posterior por menor área ou menor ponte.

**Aceitação proposta:** contato paralelo ao banzo real; cobertura e margem dos dois
terminais; ausência do chanfro intermediário persistido quando aprovada a variante
de caps diretos; sequência de faces estável quando a inclinação varia; comportamento
espelhado em caso geometricamente simétrico. Não exigir simetria se perfis e inserções
forem assimétricos.

## Caso 3 — cumeeira com duas diagonais

- Objeto: `StructuralTruss005`, DuoPitch / Warren.
- NodeKey: `T_S_APEX`; chapa `StructuralGussetPlate023`.
- Dois banzos em `ChordBreak`, duas diagonais, sem montante central.
- Persistido: seis vértices, ponta inferior em `(0;-227,799)`.
- Recomputado: sete vértices; a ponta é substituída por uma borda horizontal
  entre `(-96,244;-147,595)` e `(96,244;-147,595)`.
  Permanecem caps até `(±153,132;-100,189)`, laterais até
  `(±88,859;-23,061)` e os dois contatos de banzo até `(0;12,483)`.

A ponta persistida resulta do encontro de dois caps sem fechamento convencional
do setor inferior. A C6-P já acrescenta uma ponte pela bissetriz. Ainda assim, seus
sete lados são resultado de suportes acumulados; não existe uma definição de quais
faces são obrigatórias e quais podem ser substituídas por laterais mais simples.

**Proposta:** família de cumeeira com dois contatos superiores obrigatórios,
fechamento inferior único e pares de laterais definidos pela cobertura das diagonais.
Comparar uma variante com caps explícitos (sete lados) e outra envolvente com menos
faces, somente se preservar a cobertura e os contatos. Simetria deve decorrer da
simetria dos dados. O caso com montante central é outro contrato e fica preservado.

**Aceitação proposta:** ausência de ponta inferior sem função de cobertura;
borda inferior única; preservação das duas linhas físicas dos banzos, sobreposição
e margem; simetria para dados simétricos; continuidade sob pequenas mudanças de
inclinação; nenhuma alteração na cumeeira aprovada de duas diagonais + montante.

## Limites e aprovação necessária

Os casos usam valores já persistidos: espessura 10 mm, margem 25 mm e sobreposição
150 mm. São dados da referência, não dimensionamento recomendado. Não foram
definidos parafusos, soldas ou dimensões mínimas de fabricação.

As assinaturas de ligação também registram afastamentos transversais; um contorno
2D mais convencional não resolve esses contatos. A prévia transversal e C7 não
fazem parte desta tarefa.

Preservar integralmente a forma aprovada de duas diagonais + montante, incluindo
`StructuralTruss001/B_S_MAIN_1_3` e `T_S_MAIN_1_2`, e a extensão externa da C6-L.
Nenhuma proposta acima autoriza alterar esses contratos.

O FCStd mostra o resultado atual, mas não a forma desejada. Para definir as variantes,
solicitar apenas três imagens ou croquis com o contorno desejado sobre os nós:
`StructuralTruss002/B_S_MAIN_1_6`, `StructuralTruss005/T_S_LEFT_1_3` e
`StructuralTruss005/T_S_APEX`. Não implementar a geometria antes dessa aprovação.

Inspeção reproduzível, sem gravar no documento:

```powershell
python scripts/inspect_gusset_reference.py '..\testeC6.FCStd'
```
