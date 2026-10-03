# Steel Structures — FreeCAD

Bancada paramétrica dedicada à modelagem de estruturas metálicas no FreeCAD.

## Versão 0.6.0

- **Gerador paramétrico de treliças**, com banzos paralelos ou duas águas, padrões de alma e editor de topologia.
- **Membros simples e compostos**, com configuração dos componentes e interconectores integrada à treliça.
- **Ajustes físicos das barras e fitting de ligações**, com controles de contato, folgas e prioridade dos participantes.
- **Chapas Gusset paramétricas**, com posições transversais compatíveis com os perfis, persistência e regeneração das ligações e prévia transversal dinâmica.
- Catálogos ampliados com **perfis tubulares Tuper** e **seções maciças conforme ABNT NBR 16683:2018**.

As chapas Gusset são preliminares: não incluem furos, soldas, parafusos ou verificação resistente. Consulte o [changelog](Documentation/CHANGELOG.md) para as novidades e os limites desta versão.

### Recursos disponíveis

- **Grid Estrutural paramétrico**, com painel visual, e comandos dedicados **Criar Membro** e **Criar Pilar** sob a identidade `SteelStructures_*`.
- **Criar Membro** reutiliza a Linha nativa do Draft para entrada por dois pontos, com snaps, restrições e modo **Continuar**; **Criar Pilar** oferece inserção interativa vertical com preview.
- **Catálogo de Perfis** nativo com busca, propriedades técnicas e preview 2D das 218 bitolas do catálogo Gerdau.
- Criação paramétrica com perfis **W**, **HP**, **I laminado**, **U laminado**, **T**, **cantoneiras de abas iguais** e **U Enrijecido (Ue) conforme ABNT NBR 6355:2012**.
- Seleção hierárquica por **Categoria do perfil → Série do perfil → Perfil**, preservando nos objetos as designações e fontes do catálogo.
- Pontos de inserção específicos por família, com mini-preview interativo da seção, orientação, rotação e referência selecionada.
- Preferências e propriedades persistentes para perfil, inserção, rotação, tipo e cor, incluindo paleta rápida de cores estruturais.
- Membros orientados entre pontos nos eixos X, Y, Z ou em direções inclinadas, com `Length`, `StartPoint`, `EndPoint` e `MemberLength` sincronizados.

## Instalação

1. Feche o FreeCAD.
2. Remova a pasta antiga `BancadaFC_Steel_v0.1.0` de `%APPDATA%\FreeCAD\Mod\`.
3. Extraia o pacote da versão 0.6.0 dentro de `%APPDATA%\FreeCAD\Mod\`, mantendo `package.xml`, `freecad` e `Resources` diretamente na pasta da bancada.
4. Reinicie o FreeCAD e selecione **Steel Structures**.

## Testes recomendados

Crie quatro elementos com ponto inicial `(0, 0, 0)`:

- X: ponto final `(3000, 0, 0)`;
- Y: ponto final `(0, 3000, 0)`;
- Z: ponto final `(0, 0, 3000)`;
- Inclinado: ponto final `(2000, 1500, 2500)`.

Em seguida, altere **Rotação da seção** para `45°` e `90°` na aba Dados.
