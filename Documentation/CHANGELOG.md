# Changelog

## 0.6.0 — 2026-10-02

### Adicionado

- Gerador paramétrico de treliças com banzos paralelos ou duas águas, panelização e padrões Warren, Pratt, Warren com montantes, Howe, X, K, Fink básico, Fan, King Post e Queen Post, conforme o envelope selecionado.
- Editor de topologia para personalizar a alma, criar e remover barras e nós, mover nós internos, inverter a alma e copiar por espelhamento.
- Membros compostos integrados à treliça, com configuração dos componentes, espaçamentos e interconectores posicionados pelas superfícies físicas dos perfis.
- Ajustes paramétricos de extremidades, criação de membros a partir de eixos selecionados e fitting automático das barras e ligações, com contato direto, encontro em meia-esquadria, prioridade e folgas.
- Chapas Gusset paramétricas com espessura, margem, sobreposição e posições transversais resolvidas a partir das seções e dos participantes físicos da ligação.
- Persistência das configurações por nó e regeneração das ligações e chapas vinculadas à treliça.
- Prévia transversal dinâmica da ligação, com perfis simples ou compostos e posição projetada da chapa, integrada ao editor de topologia.
- Perfis tubulares com catálogo Tuper e seções maciças com catálogo conforme ABNT NBR 16683:2018.
- Opção de geometria simplificada das seções dos membros.

### Melhorado

- Fluxos de criação e edição de treliças, com previews, seleção de participantes e diagnósticos de ligação no nó selecionado.
- Integração física entre perfis, componentes, interconectores, fitting e chapas, respeitando inserções, rotações e espaçamentos.
- Apresentação das etiquetas e edição do Grid Estrutural.

### Corrigido

- Inconsistências de contorno, contato e posicionamento transversal das Gussets nas configurações suportadas, incluindo perfis W/I e membros compostos.
- Preservação das configurações dos nós sobreviventes durante edição e regeneração da topologia.

### Notas e limitações

- As chapas Gusset são preliminares; furos, soldas, parafusos e verificação resistente não estão incluídos. A intenção de fixação não gera esses detalhes.
- Regiões e posições transversais dependem da seção, orientação, espessura e acesso físico dos participantes. Configurações inviáveis recebem diagnóstico e podem permanecer sem chapa materializada.
- A prévia transversal usa as seções anteriores aos recortes de fitting e uma projeção da chapa; não representa um corte localizado do sólido final.
- A criação e remoção de chapas ocorre na aplicação ou regeneração explícita da treliça; o recompute ordinário atualiza os objetos existentes.

## 0.5.0 — 2026-08-25

### Adicionado

- Grid Estrutural paramétrico com painel visual, preview e propriedades persistentes.
- Ferramenta Criar Pilar com posicionamento interativo, preview do perfil e orientação no eixo global Z.
- Catálogo de Perfis nativo com busca, propriedades técnicas, fontes e preview 2D das 218 bitolas do catálogo Gerdau.
- Suporte paramétrico aos perfis W, HP, I laminado, U laminado, T, cantoneiras de abas iguais e U Enrijecido (Ue) conforme ABNT NBR 6355:2012.
- Mini-preview interativo para orientação da seção e seleção visual dos pontos de inserção.
- Pontos de inserção específicos para as novas famílias de perfis.
- Paleta rápida de cores estruturais nos fluxos de criação.

### Melhorado

- Geometria, propriedades técnicas e apresentação das famílias de perfis suportadas.
- Fluxos de Criar Membro e Criar Pilar, com preferências persistentes e integração ao Catálogo de Perfis.
- Previews técnicos com cotas, centroide, fontes dos dados e indicação da referência de inserção.
- Preservação do `Placement` e das propriedades paramétricas durante recomputes e atualizações geométricas.
- Identidade da bancada consolidada como Steel Structures em pacote, comandos e recursos.

### Corrigido

- Persistência e restauração dos pontos de inserção selecionados nas ferramentas de criação.
- Robustez das transformações e do `Placement` para membros e grids.
- Inconsistências de geometria, cotas e apresentação nas famílias de perfis suportadas.

## 0.4.0 — 31/07/2026

- Nova ferramenta `StructuralMemberDraftTool`, baseada diretamente na Linha nativa do Draft, para criação gráfica ou numérica por dois pontos.
- Entrada numérica, snaps, restrições, Relativo e Global reutilizam integralmente a infraestrutura nativa do Draft.
- Opções de nome, tipo, perfil, inserção, rotação e cor integradas ao painel nativo.
- Modo Continuar cria membros sucessivos na mesma sessão, preservando a interface, a prévia, o callback e as opções do perfil.
- Fechamento por Esc ou Close e reabertura da ferramenta estabilizados, sem referências residuais de sessão.
- Corrigido o erro `QLineEdit already deleted`, eliminando manipulação do TaskBox externo, `headerText` e travessia da árvore Qt.
- Cabeçalho externo fixo “Criar elemento estrutural”, com orientação do primeiro e do próximo ponto pela barra inferior do FreeCAD.
- Comprimento e Ângulo nativos aparecem somente depois da confirmação do primeiro ponto.
- Barra oficial Draft Snap registrada na bancada e disponível no menu de barras de ferramentas.
- Removidos o painel numérico legado, a captura Coin3D própria e os adaptadores próprios de snap e pré-visualização.
- Propriedade editável `Length`, sincronizada com `StartPoint`, `EndPoint` e `MemberLength`, preservando o ponto inicial e a direção do membro.
- O cancelamento parcial do segmento com um primeiro Esc permanece adiado; Esc conserva o encerramento nativo completo da Linha.

### Histórico dos marcos intermediários da 0.4.0

- Base do controlador de criação preparada para evolução interativa.
- Painel lateral de tarefas para criação numérica contínua de elementos.
- Preservação temporária do diálogo numérico como fallback interno.
- Correção da detecção de diálogo ativo quando a aba Tarefas está vazia.
- Correção do reinício do nome automático e do fechamento seguro do painel.
- Testes automatizados para estados, transações e ciclo de vida da sessão.
- Captura básica de dois pontos na vista 3D, com criação contínua.
- Prévia axial leve por linha Coin3D, sem objetos temporários no documento.
- Cancelamento progressivo com Esc e limpeza simétrica de callbacks e prévia.
- Entrada numérica preservada como opção para coordenadas espaciais exatas.
- Encerramento diferido da captura para evitar remoção de callbacks durante eventos Coin.
- Início automático da captura ao abrir o painel, sem botões Capturar ou Parar.
- Criação contínua, mantendo a ferramenta ativa para elementos sucessivos.
- Esc cancela o segmento após o primeiro ponto e fecha a ferramenta ao aguardar o primeiro ponto.
- Limpeza diferida contra Access violation preservada no encerramento da ferramenta.
- Captura ainda baseada em projeção da vista, sem snap geométrico.
- Snap geométrico básico em vértices e extremidades de arestas.
- Marcador Coin3D leve no ponto exato, com projeção da vista como fallback.
- Metadados de snap mantidos somente durante a sessão de criação.
- Snapper nativo do Draft passa a ser o mecanismo principal da captura.
- Modos, tolerância, marcadores e preferências de snap do Draft são respeitados.
- Barra nativa Encaixe de Draft disponibilizada sem duplicar comandos.
- Snap básico próprio permanece disponível somente como fallback.

## 0.3.0 — 30/07/2026

- Interface simplificada para um único comando de criação.
- Comando público "Criar elemento estrutural".
- Manutenção do campo Tipo do elemento.
- Designações compactas, como W150x13,0, na interface.
- Preservação da designação canônica do catálogo nos objetos.
- Testes automatizados adicionados.
- Manutenção da geometria e do comportamento paramétrico existente.

## 0.2.0 — 2026-07-30

- Renomeação visual para Metal Structure.
- Hierarquia de catálogo: categoria, série e perfil.
- Campo de nome e sequência automática com três dígitos.
- Orientação espacial controlada pelo Placement do objeto.
- Composição da rotação axial com a orientação do membro.
- Proteção contra eventos onChanged durante a criação das propriedades.
- Migração básica de objetos v0.1.0.
