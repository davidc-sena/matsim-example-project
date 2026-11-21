# IDEF-SIM Studio

Programa desktop para **criar, documentar, validar e simular** modelos conceituais
na técnica **IDEF-SIM** (Leal, Almeida & Montevechi, 2008), usada na
simulação a eventos discretos.

![Janela principal](docs/screenshot.png)

## Funcionalidades

| Área | O que faz |
|---|---|
| **Editor gráfico** | Paleta com todos os símbolos IDEF-SIM. Pode arrastar, encaixar na grade, dar zoom (Ctrl+roda), duplicar (Ctrl+D), excluir, desfazer e refazer. |
| **Propriedades** | Nome, descrição e parâmetros de cada elemento: chegadas, tempos, capacidades e probabilidades. |
| **Validação** (F7) | Erros e avisos em tempo real: elementos sem fluxo, distribuições inválidas, conectores sem par, probabilidades, elementos inalcançáveis… Clique em uma mensagem para ir ao elemento. |
| **Simulação** (F5) | Motor de eventos discretos (SimPy) que executa o próprio diagrama, com replicações, aquecimento, média, desvio padrão e IC 95%. Os resultados exportam para CSV. |
| **Gestão de modelos** | Arquivos `.idefsim` (JSON legível e versionável), metadados (autor, versão e descrição), arquivos recentes e modelos de exemplo. |
| **Documentação** | Exportação do diagrama em PNG ou SVG e do dicionário do modelo conceitual em HTML (com o diagrama embutido). |

## Instalação e execução

```bash
cd idefsim-studio
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py                       # ou: python main.py examples/usinagem_inspecao.idefsim
```

### Executáveis prontos (Windows, macOS, Linux)

O workflow `.github/workflows/idefsim-studio.yml` compila automaticamente os executáveis
em máquinas Windows, macOS e Linux do GitHub Actions:

* **A cada push** que altere `idefsim-studio/`, os pacotes ficam em *Actions* → execução → *Artifacts*.
* **Ao publicar um Release** no GitHub, os pacotes são anexados ao Release.
* Também é possível rodar manualmente em *Actions* → *IDEF-SIM Studio - executáveis* → *Run workflow*.

| Sistema | Arquivo | Como instalar |
|---|---|---|
| Windows 10/11 (64 bits) | `IDEF-SIM-Studio-windows-x64.zip` | Extraia a pasta e execute `IDEF-SIM Studio.exe`. |
| macOS Apple Silicon (M1–M4) | `IDEF-SIM-Studio-macos-arm64.dmg` | Abra o `.dmg` e arraste o app para *Aplicativos*. |
| macOS Intel | `IDEF-SIM-Studio-macos-x64.dmg` | Igual ao anterior. |
| Linux 64 bits (Ubuntu 22.04+ e similares) | `IDEF-SIM-Studio-linux-x64.tar.gz` | `tar -xzf IDEF-SIM-Studio-linux-x64.tar.gz` e execute `IDEF-SIM Studio/IDEF-SIM Studio`. |

> **Aviso de segurança na primeira execução.** Os executáveis não têm assinatura digital
> paga, por isso o sistema pode exibir um alerta:
> * **Windows** (SmartScreen): clique em *Mais informações* → *Executar assim mesmo*.
> * **macOS** (Gatekeeper): clique com o botão direito no app → *Abrir* → *Abrir*. Se não
>   funcionar, rode `xattr -dr com.apple.quarantine "/Applications/IDEF-SIM Studio.app"`.

### Gerar o executável localmente

O PyInstaller gera o executável **do sistema em que é executado** (é preciso um Windows
para gerar o `.exe` e um Mac para o `.app`):

```bash
pip install -r requirements.txt pyinstaller pillow
pyinstaller --noconfirm packaging/idefsim_studio.spec
# resultado em dist/
```

O ícone (`idefsim/resources/icon.png`) é gerado por `python packaging/make_icon.py`.

### Testes

```bash
pip install pytest
python -m pytest
```

## Como modelar

1. Escolha um símbolo na paleta (ou use o atalho) e clique no diagrama. **Shift** mantém a ferramenta ativa; **Esc** ou o botão direito volta a *Selecionar*.
2. Para conectar dois elementos, escolha a ligação (*Fluxo*, *Fluxo de entrada*, *Recurso*, *Controle* ou *Nota*), clique na origem e depois no destino.
3. Edite os parâmetros no painel **Propriedades**. Sem nada selecionado, o painel mostra as propriedades do modelo (duração, aquecimento, replicações, unidade de tempo).
4. **F7** valida o modelo e **F5** executa a simulação.

### Símbolos e semântica de simulação

| Símbolo | Atalho | Interpretação na simulação |
|---|---|---|
| Entidade (círculo) | E | Sem fluxo de entrada é uma **fonte de chegadas** (intervalo, primeira chegada, lote, máximo). Com fluxo de entrada é uma **transformação**: a entidade passa a ser deste tipo. |
| Fluxo de entrada no sistema (seta com dois traços) | Shift+E | Entrada de entidades externas no sistema modelado: liga a Entidade de chegada ao primeiro elemento. Na simulação comporta-se como um fluxo comum. |
| Função (retângulo) | F | Captura 1 unidade de cada recurso ligado, processa durante o tempo definido e libera os recursos. Sem recurso, capacidade infinita. |
| Recurso | R | Capacidade (n.º de unidades). Fica **abaixo** da função; a *Ligação de recurso* sobe e entra pela base da função. |
| Controle | C | Documental. Fica **acima** da função; a *Ligação de controle* entra pelo topo da função. |
| Movimentação (seta larga) | M | Como a função, mas representa um transporte. |
| Regra E (&) | 1 | Várias entradas: espera uma entidade de cada ramo (junção ou montagem). Várias saídas: segue por todos os ramos (paralelo). |
| Regra OU (X) | 2 | Segue **uma** saída, escolhida pelas probabilidades. |
| Regra E/OU (O) | 3 | Cada saída é seguida de forma independente com sua probabilidade (pelo menos uma). |
| Ponto final | X | A entidade sai do sistema (contabiliza o tempo no sistema). |
| Conexão | K | Conectores com o **mesmo nome** estão ligados (útil para diagramas grandes). |
| Informação explicativa | N | Nota de texto, sem efeito na simulação. |

**Distribuições** (notação semelhante à do Arena): `5`, `CONST(5)`, `EXPO(média)`,
`NORM(média, desvio)`, `TRIA(mín, moda, máx)`, `UNIF(mín, máx)`, `LOGN(média, desvio)`,
`ERLA(média, k)`, `WEIB(escala, forma)`. Para vírgula decimal, separe os argumentos
com `;`, por exemplo `NORM(5,5; 0,8)`.

### Indicadores calculados

* **Sistema:** saídas, throughput, WIP médio e final, tempo médio no sistema.
* **Entidade:** criadas, saídas, tempo médio e máximo no sistema.
* **Função/Movimentação:** atendimentos, tempo médio de processamento, tempo médio em fila, fila média e máxima.
* **Recurso:** utilização (%) e ocupação média.
* **Ponto final:** entidades por saída.

Todos os indicadores têm média, desvio padrão, IC 95% (t de Student) e mínimo–máximo entre replicações.
Durante o aquecimento as estatísticas não são recolhidas.

## Estrutura do código

```
idefsim/
  model.py          modelo de dados e regras de ligação (sem dependência de Qt)
  distributions.py  leitura e amostragem de distribuições
  validation.py     verificação de consistência
  simulation.py     motor SimPy e estatísticas
  report.py         documentação HTML
  storage.py        leitura e gravação de .idefsim
  examples.py       modelos de exemplo
  gui/              interface PySide6 (janela, cena, itens, propriedades, diálogos)
tests/              testes automáticos (núcleo + interface)
examples/           arquivos .idefsim de exemplo
```

O núcleo (`model`, `simulation`, …) não depende da interface, por isso pode ser usado
em scripts ou notebooks para experimentar cenários:

```python
from idefsim.storage import load_model
from idefsim.simulation import run_simulation

m = load_model("examples/usinagem_inspecao.idefsim")
inspetor = next(e for e in m.elements.values() if e.name == "Inspetor")
inspetor.params["capacity"] = 2          # cenário: 2 inspetores
print(run_simulation(m).to_csv())
```

## Próximos passos sugeridos

* Exportar o modelo para Arena, FlexSim ou outro software comercial.
* Atributos de entidade e regras de decisão por condição (não só por probabilidade).
* Turnos e indisponibilidade de recursos (paragens e manutenção).
* Gestor de cenários (comparar várias configurações lado a lado).
* Animação do fluxo de entidades sobre o diagrama.
