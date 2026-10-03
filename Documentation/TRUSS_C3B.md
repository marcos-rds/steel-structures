# Treliça C3-B — integração e editor de composição

Implementação local para validação manual; sem staging, commit ou push.
O núcleo C3-A permanece inalterado. Não há elementos C4, corte automático,
seção equivalente ou cálculo de folga livre.

## Fluxo e persistência

`RoleSpec → PhysicalRun nominal → MemberAssemblySpec C3-A → componentes →
StructuralMember`. O novo módulo puro `trusses/assemblies.py` faz a ponte;
não contém geração de contorno nem extrusão por família. Perfil, modo
geométrico, inserção e cor do role são autoritativos e sincronizados no spec.
As transformações relativas e o espaçamento ficam no MemberAssemblySpec.

O campo existente `assembly` seleciona o modo; `assembly_spec` contém o JSON
versionado da C3-A. Ausência de `assembly` equivale a `Single`; ausência de
`assembly_spec` é normal em Single. Definição dupla residual em Single é
rejeitada. `configure_assembly()` produz os campos coerentes para UI/scripts.

Documentos C1/C2 (schemas 1/2) continuam legíveis, sem conversão destrutiva.
Estado sem composições continua sendo escrito como schema 2. Configurações
com composições usam schema 3, inclusive quando o role composto está ausente
na topologia atual. Recompute de um C2 inalterado não grava migração nem exige
NeedsRegeneration. A versão de release do projeto não foi alterada.

## Identidade, aplicação e árvore

A identidade conceitual é `(run_key, "ASSEMBLY", component_key)`. Os filhos
possuem RunKey, AssemblyKey e ComponentKey somente leitura. Para preservar
bindings C1/C2 e reutilizar o mesmo objeto Single→Double, o GenerationKey de A
mantém o alias legado `run_key`. B usa JSON inequívoco da identidade completa.
Índice, Label, posição e ordem da Shape não são usados como identidade.

Os grupos de roles existentes permanecem; componentes duplos recebem labels
como `Diagonal 03 / A` e `Diagonal 03 / B`, sem nível adicional de árvore.
O owner continua StructuralTruss, com registro hidden e link dos filhos para
o owner, preservando o DAG aprovado.

RegenerationPlan inclui cardinalidade/identidades na assinatura estrutural.
Spacing, orientação, cor, perfil compatível e mudança inward/outward com as
mesmas chaves atualizam os mesmos membros. Single↔Double é estrutural; A é
preservado sempre que os conflitos permitem. Double→Single limpa a
AssemblySectionTransform anterior de A. Extensões/ajustes preservados não são
apagados. O lote completo é preparado antes da transação; falhas abortam a
aplicação e invalidam os caches Python afetados.

O editor trabalha em cópia do role. Cancelar descarta a edição. O Gerador
mantém seu candidate; a cardinalidade só chega ao documento pelo OK explícito.
Alterações estruturais externas continuam pendentes em recompute, conforme
C1/C2. Inserção e propriedades controladas dos filhos continuam bloqueadas.

## Coordenadas e orientação

O frame base mantém X=u=-normal da treliça, Y=v=w×u e Z=w. A rotação do role
gira **o conjunto inteiro**, incluindo os eixos físicos. Dentro desse frame,
SectionTransform atua no contorno e na referência de inserção do componente:

```text
p_global = eixo_nominal + frame_base · R_role · (d + T_componente(p - q))
```

`d` é a translação entre eixos e `q` a inserção canônica do perfil. Para duplos,
R_role já está no frame passado ao resolver C3-A; não é repetida em Rotation.
Para Single, o caminho histórico de Rotation/Placement permanece idêntico.
Assim, girar o conjunto 90° também gira a direção do espaçamento. O editor
mostra isso imediatamente. Ao escolher uma composição dupla partindo de
Single, inicia explicitamente o conjunto em 0° e informa essa escolha no editor.

ComponentSpacing significa **distância entre eixos de inserção**, exibida
como “Distância entre eixos”, em mm, com tooltip. Não se aplica em OffsetX/Y.
O editor C3-B trata pares A/B em ±spacing/2 no u do conjunto. Outras translações
2D continuam suportadas pelo núcleo C3-A, mas são rejeitadas neste editor
restrito para não serem silenciosamente achatadas ao reabrir.

Centro e Par simétrico estão expostos; duplos iniciam como Par simétrico.
Ambos usam a origem nominal e eixos opostos nesta UI. Não há Near/Far.

## Editor e previews

Cada linha em Perfis mantém o botão compacto do role, com indicação da
composição e miniatura. O modal reutiliza o seletor de perfil, inserção, cor,
rotação e atalhos de 90° já existentes. Os modos em PT-BR são:

- Simples: qualquer perfil suportado.
- Dupla cantoneira: requer L; abas para fora por padrão, com opção para dentro.
- U duplo — bocas para dentro: requer U compatível.
- U duplo — bocas para fora: requer U compatível.
- Par espaçado: qualquer perfil suportado, mesma orientação por padrão;
  disposições individuais A/B permitem giro e inversão lateral explícitos.

Categoria, série e perfil são filtrados pela mesma regra de compatibilidade,
inclusive no navegador de catálogo. Trocar a composição preserva o perfil
compatível; caso contrário recupera a última escolha compatível desse modo
ou o primeiro perfil na ordem normal do catálogo. A validação interna permanece.
O modo U e seus transforms devem concordar, inclusive na carga de JSON.

**Convenção dos U:** preservada a C3-A aprovada. Na vista transversal canônica,
o U original abre para +X; bocas para dentro são `[]`, e para fora são `][`.
Os rótulos se baseiam nas bocas físicas. Os desenhos invertidos da solicitação
C3-B não foram usados para inverter o comportamento aprovado da C3-A.

O preview transversal usa SectionGeometry2D, referências canônicas e
transform_section da C3-A; arcos são amostrados apenas para desenho. Mostra
contornos/furos, cor, A/B, eixos de inserção, origem nominal e distância.
O fundo segue QPalette; contornos usam halo sobre fundo escuro, e os textos
escolhem contraste claro/escuro. Single mantém o preview de inserção existente.

O preview 3D existente recebe agora os componentes expandidos através do mesmo
prepare_batch da geração. Mostra sólidos A/B deslocados, orientados e com os
ajustes existentes. Continua uma branch Coin descartável e não selecionável,
sem FeaturePython temporário, transações ou objetos de documento.

## Validação desta etapa

Comando focado:

```powershell
python -m unittest tests.test_truss_assemblies tests.test_truss_core tests.test_truss_c2 tests.test_assemblies tests.test_truss_task_panel tests.test_member_orientation tests.test_section_geometry_mode
```

O gate inicial usou somente os testes focados abaixo; o fechamento está registrado ao final.

Resultado: 115 testes focados aprovados. `python scripts/check_project.py`
executado uma vez e aprovado; `git diff --check` aprovado. Arquivos novos
também verificados quanto a whitespace, sem staging.

`tests/manual_freecad_truss_c3b.py` contém dez etapas cirúrgicas. Executadas no
FreeCAD 1.1.3 em instância isolada: fixture C2 sem assembly; U simples; U duplo
para dentro/fora com ocupação física do sólido; caso A misto; caso B espaçado;
plano inclinado; spacing preservando objetos/extensão; Single↔Double com
Undo/Redo; preview sem mutação; save/reopen/recompute. Todas aprovadas.
Comparação de volume após serialização usa tolerância de 1e-5 mm³/1e-12 relativa;
pontos e quaternion usam 1e-8. Nenhum ciclo foi encontrado.

O MCP abriu e capturou o editor no FreeCAD da sessão; chamadas posteriores
esgotaram o tempo de despacho GUI. O gate geométrico/persistência foi concluído
pela mesma fixture em instância isolada autorizada, com configurações próprias.
Não se alega que as dez etapas tenham sido executadas pelo transporte MCP.

`run_editor(document, output_directory)` também passou com Qt real: mudança
de composição/distância, bloqueio por família incompatível, inversão explícita
de B, Cancelar sem mutação e renderização das linhas compactas de Perfis.
Capturas Classic e de preview com paleta escura foram inspecionadas. A captura
inicial via MCP usou o tema da sessão; a verificação final de Dark/OpenDark na
instalação habitual permanece no roteiro manual abaixo.

Artefatos locais (fora do Git): `test-results/truss-c3b/TrussC3B.FCStd`,
`legacy-single.FCStd`, `report.json`, `truss-isometric.png` e capturas do editor.

## Roteiro de validação do usuário

1. Abrir o FCStd e dar duplo clique na Treliça. Expandir Perfis e abrir um role.
2. Comparar U para dentro/fora e dupla cantoneira; testar Par espaçado com mesma
   disposição A/B e depois inverter explicitamente um componente.
3. Alterar distância e rotação do conjunto: conferir preview transversal/3D,
   especialmente no plano inclinado. Cancelar deve conservar o documento.
4. Confirmar uma mudança de spacing, depois Single↔Double. Conferir árvore,
   Undo/Redo e reabertura. Voltar a Simples deve remover o sufixo `/ A`.
   Trocar a composição deve filtrar categoria, série e perfil, preservando
   a escolha compatível e atualizando o preview imediatamente.
5. Conferir legibilidade do editor em Classic/Dark/OpenDark na instalação usual.

Validação manual no FreeCAD 1.1.3 e aprovação funcional/design confirmadas pelo
usuário no fechamento da C3-B.
Folga livre entre faces, disposições fora do editor restrito e recursos C4
continuam fora do escopo.

## Gate final de fechamento

Revisão curta sem blocker evidente e sem nova auditoria MCP. Suíte completa
executada uma única vez com `python -m unittest discover -s tests -p "test_*.py"`:
1.021 testes em 16,917 s, com um erro de fixture em `test_profile_browser`.
O stub `SimpleNamespace` não definia `_profile_filter`, inicializado pelo
construtor real. A fixture recebeu o filtro padrão permissivo; nenhuma
asserção foi removida e nenhuma alteração de produção foi necessária.

Após a correção, `python -m unittest tests.test_profile_browser
tests.test_assembly_refinements tests.test_profile_options_browser_integration`
aprovou 65 testes. A suíte completa não foi repetida.
`python scripts/check_project.py` aprovado. Commit autorizado pelo usuário;
push e C4 não fazem parte deste fechamento.
