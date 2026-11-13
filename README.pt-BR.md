# Gerador de Preços Simulado

[English](README.md) · [Português](README.pt-BR.md)

Script único (sem dependências) que cria **histórico de preços fictício** para o FC Trade Manager, para que os gráficos (24h / 7d / 30d) e os alertas tenham dados desde o primeiro dia. Ele lê o `cards.csv` que o backend importa e escreve um arquivo `.sql`.

> Todos os preços são fictícios e servem só para desenvolvimento e demonstração. Este projeto não tem afiliação nem endosso da EA. A base da documentação foi gerada com o Claude.

## Índice

1. [Uso rápido](#uso-rápido)
2. [O que ele gera](#o-que-ele-gera)
3. [Como o preço é calculado](#como-o-preço-é-calculado)
4. [Ajustes globais](#ajustes-globais)
5. [Ajustar uma carta específica](#ajustar-uma-carta-específica)
6. [Receitas](#receitas)
7. [Problemas comuns](#problemas-comuns)
8. [Limitações](#limitações)

## Uso rápido

Requisitos: Python 3.9 ou mais novo (testado com 3.13) e o backend já rodado ao menos uma vez, para a tabela `Cards` estar populada.

**1. Gerar o SQL**

```powershell
python seed_prices.py caminho\para\cards.csv
```

Isso cria `price_seed.sql` na pasta atual. Para escolher outro nome: `python seed_prices.py cards.csv saida.sql`.

**2. Importar no PostgreSQL (Docker)**

Descubra o nome do container com `docker ps` e rode:

```powershell
# PowerShell (o "<" não funciona nele; use pipe)
Get-Content price_seed.sql -Raw | docker exec -i <container> psql -U <usuario> -d <banco>
```

```bash
# bash / Git Bash / Linux / macOS
docker exec -i <container> psql -U <usuario> -d <banco> < price_seed.sql
```

**3. Conferir**

```sql
SELECT COUNT(*) FROM "PriceSnapshots" WHERE "Source" = 'simulated';
```

Com 156 cartas e 30 dias, o resultado é `112476` (721 pontos por carta). Depois, abra o Swagger e chame o histórico de uma carta (`24h`, `7d` e `30d`).

**Gerar de novo**: pode rodar o script e importar quantas vezes quiser. O SQL apaga antes apenas as linhas com `Source = 'simulated'` (preços manuais nunca são tocados) e insere o histórico novo, já com a janela deslocada para "agora".

## O que ele gera

| Item | Valor |
|---|---|
| Janela | últimos 30 dias (`DAYS`), terminando na hora cheia atual (UTC) |
| Frequência | um preço por hora |
| Tabela | `"PriceSnapshots"` (`Id`, `CardId`, `Price`, `Source`, `RecordedAt`) |
| `Source` | `simulated` |
| Limites | preço entre 200 e 15.000.000 (regra do backend) |
| Ids | fixos (derivados do `ExternalRef` + hora): importar o mesmo arquivo duas vezes não duplica |

**Por que o `ExternalRef` existe.** O backend cria o `Id` (GUID) de cada carta ao importar o `cards.csv`, então ele muda a cada banco. O `ExternalRef` é a chave estável que fica no CSV, e o SQL gerado usa um `JOIN` nele para achar a carta. Por isso o mesmo arquivo funciona em qualquer banco, e por isso o `ExternalRef` precisa ser **único** por carta (o script recusa um CSV com repetidos).

## Como o preço é calculado

Cada carta tem o próprio gerador aleatório (derivado de `SEED` + `ExternalRef`): a mesma semente dá o mesmo formato de curva, e incluir cartas no CSV não altera as outras. O preço é a combinação de cinco ingredientes, multiplicados entre si:

1. **Preço-base** pela fórmula `2000 × 1,4^(overall − 80) × raridade`. Cada ponto de overall multiplica o preço por 1,4. Exemplos (Gold Rare): 80 ≈ 2.000 · 85 ≈ 10.800 · 90 ≈ 57.900 · 95 ≈ 311.000 · 98 ≈ 854.000. O multiplicador de raridade é: Gold Common 0,6 · Hero 1,6 · Icon 2,2 · qualquer outra 1,0.
2. **Tendência do mês**: cada carta sobe ou cai uma porcentagem sorteada (desvio padrão de cerca de 6% em 30 dias), em linha reta.
3. **Aumento de sexta** (só cartas com overall ≥ 86): o preço sobe 8% na sexta-feira às 00:00 UTC e cai em linha reta até voltar ao normal na segunda às 00:00 UTC (72 horas depois). Sexta 00:00 UTC é quinta 21:00 em Brasília.
4. **Ruído suave**: uma oscilação que tem "memória" (cerca de 1 dia) e sempre volta ao centro, em vez de se afastar para sempre. O preço costuma ficar a uns 2,5% do centro.
5. **Arredondamento**: o preço final é limitado a 200–15.000.000 e arredondado a **3 algarismos significativos** (1.234 vira 1.230; 961.234 vira 961.000). Isso deixa as curvas suaves; o mercado real usa degraus (50, 100, 250...), mas o backend não os exige.

Como os ingredientes se multiplicam, "+8%" é de fato 8% sobre o preço, em qualquer faixa.

## Ajustes globais

No topo do `seed_prices.py`:

| Constante | O que faz | Padrão |
|---|---|---|
| `DAYS` | tamanho do histórico, em dias | `30` |
| `SEED` | muda o "sorteio" de todas as cartas | `42` |
| `BOOST_MIN_OVERALL` | overall mínimo para o aumento de sexta (use `999` para desligar para todos) | `86` |
| `BOOST_PEAK` | tamanho do aumento de sexta | `0.08` (+8%) |
| `RARITY` | multiplicador por raridade (em minúsculas); as ausentes valem 1,0 | veja o arquivo |

Dentro da função `history` há números que também são ajustáveis:

| Trecho | O que faz |
|---|---|
| `2000 * 1.4 ** (overall - 80)` | preço de um overall 80 (`2000`) e quanto cada ponto de overall encarece (`1.4`) |
| `rng.gauss(0, 0.06)` | tamanho da tendência aleatória do mês (maior = cartas mais diferentes entre si) |
| `0.97` | "memória" do ruído (mais perto de 1 = oscilações mais lentas e longas) |
| `0.006` | agitação do ruído (maior = gráfico mais nervoso) |
| `72` | duração do aumento de sexta, em horas |

Se mudar `DAYS`, `SEED` ou qualquer valor, gere e importe de novo. A mesma `SEED` mantém o formato do ruído e da tendência; só o dente de sexta muda de lugar conforme o dia em que você gera.

## Ajustar uma carta específica

Para dar a uma carta um comportamento próprio (preço, tendência, nervosismo, ou terminar num preço exato), use o dicionário `OVERRIDES`, no topo do script. A chave é o `ExternalRef` da carta.

**Passo a passo**

1. **Ache o `ExternalRef`** da carta no `cards.csv` (última coluna). No PowerShell:

   ```powershell
   Select-String -Path cards.csv -Pattern "Mbapp" -Encoding utf8
   ```

   Ou abra o CSV no VS Code ou no Excel e procure o nome.

2. **Edite o `OVERRIDES`** no topo do `seed_prices.py`:

   ```python
   OVERRIDES = {
       "cards-030": {"base": 40000, "trend": 0.25, "noise": 2, "boost": False, "end": 54000},
       "cards-001": {"trend": 0.15, "noise": 0.5},
   }
   ```

3. **Gere e importe de novo** (veja [Uso rápido](#uso-rápido)).

Só as cartas listadas mudam; todas as outras continuam exatamente como estavam.

**As opções** (todas opcionais; use só as que precisar):

| Opção | O que faz | Exemplo |
|---|---|---|
| `base` | preço aproximado **no início** da janela (30 dias atrás); substitui a fórmula por overall e raridade | `"base": 40000` |
| `trend` | variação total no período, como fração: `0.25` termina ~25% acima do início, `-0.3` termina 30% abaixo. Substitui a tendência aleatória. Deve ser maior que `-1` | `"trend": 0.25` |
| `noise` | multiplicador da agitação: `0` = linha lisa, `1` = normal, `2` ou `3` = bem nervosa | `"noise": 2` |
| `boost` | `False` desliga o aumento de sexta desta carta | `"boost": False` |
| `end` | o preço **atual**: nas últimas 48 horas a curva anda em linha reta até esse valor | `"end": 54000` |

**Sobre o `end`**: ele fixa o *último* ponto, e é o que a API devolve como preço atual e o que o serviço de alertas compara com as metas. O que vem antes só muda nas últimas 48 horas, então o histórico longo continua com a forma que a tendência e o ruído deram.

**Proteção contra erro de digitação**: um `ExternalRef` que não existe no CSV, uma opção desconhecida (por exemplo `"endd"`) ou um `trend` menor ou igual a `-1` interrompem o script com uma mensagem clara, em vez de serem ignorados em silêncio.

## Receitas

| Quero... | Use |
|---|---|
| Uma carta bem estável | `{"noise": 0.3, "trend": 0, "boost": False}` |
| Uma carta que se valoriza forte no mês | `{"trend": 0.5}` |
| Uma carta que despenca no mês | `{"trend": -0.4}` |
| Uma carta muito nervosa | `{"noise": 3}` |
| Uma linha lisa (bom para capturas de tela) | `{"noise": 0, "trend": 0, "boost": False}` |
| Uma carta cara fixa em torno de um valor | `{"base": 120000, "trend": 0, "noise": 0.5}` |
| Uma carta de 86+ **sem** o dente de sexta | `{"boost": False}` |
| Terminar num preço exato (demo de alerta) | `{"end": 54000}` |

**Demonstrar um alerta de compra ou de venda**

1. Escolha uma carta, por exemplo `cards-030`, e defina um `end` **abaixo** da meta de compra que você vai usar (ou **acima** da meta de venda): `"cards-030": {"end": 54000}`.
2. Gere e importe os preços.
3. No app, adicione a carta à watchlist com meta de compra `55000`.
4. O serviço de alertas roda a cada minuto, então o alerta deve aparecer em até cerca de um minuto, porque o último preço (54.000) já está abaixo da meta.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `INSERT 0 0` em todos os blocos | A tabela `Cards` está vazia (rode a API uma vez) ou os `ExternalRef` do CSV não são os do banco (o CSV foi alterado depois de popular o banco: recrie o banco ou reimporte as cartas) |
| `relation "PriceSnapshots" does not exist` | As migrations ainda não foram aplicadas (`dotnet ef database update`) |
| `AssertionError: OVERRIDES: ExternalRef inexistente...` | A chave do `OVERRIDES` não existe no CSV passado ao script |
| `docker exec ... the input device is not a TTY` | Não use `-t`; o comando já usa só `-i` |
| O PowerShell não aceita `<` | Use `Get-Content ... -Raw \| docker exec -i ...` |
| Os gráficos parecem os de ontem | O script usa a hora atual; gere e importe de novo para deslocar a janela |
| Uma carta ficou "reta" demais | Há `"noise": 0` (ou muito baixo) no `OVERRIDES` dela |

## Limitações

- Os preços são **inventados**: não refletem o mercado real do jogo nem usam qualquer dado da EA.
- Os valores não seguem os degraus de preço do jogo (50, 100, 250...), por escolha, para os gráficos ficarem suaves.
- O aumento de sexta é uma regra de demonstração, não uma medição do mercado.
- Os nomes de tabela e coluna (`"PriceSnapshots"`, `"Cards"`, `"Source"` em minúsculas) seguem o backend atual. Se o schema mudar, ajuste o trecho que monta o SQL no final do script.
- O arquivo gerado é SQL puro: leia antes de importar se tiver dúvida do que ele faz.
