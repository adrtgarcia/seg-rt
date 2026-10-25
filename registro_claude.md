## 1. O que é uma Rainbow Table (conceito)

Uma RT é uma técnica de **time-memory trade-off** para quebrar hashes sem guardar todo o espaço de senhas. Em vez de armazenar `hash → senha` para cada senha possível (o que gastaria muita memória), guarda-se apenas o **início** e o **fim** de "cadeias" de comprimento fixo:

```
senha₀ --hash--> h₀ --reduz--> senha₁ --hash--> h₁ --reduz--> ... --> senhaW (fim)
```

Só `(senha₀, senhaW)` fica guardado. Para quebrar um hash-alvo, reconstrói-se cadeias hipotéticas a partir dele e verifica-se se o fim bate com algum fim armazenado; se bater, a cadeia inteira é regerada a partir do início para confirmar.

- **Altura (height)**: número de cadeias armazenadas (quantas linhas a tabela tem).
- **Largura (width)**: comprimento de cada cadeia (quantos passos hash→reduz ela tem).
- **Função de redução**: o inverso "falso" do hash — pega um hash e devolve uma senha candidata (no nosso caso, uma palavra do Diceware).
- **Cores**: famílias diferentes de função de redução, cada uma gerando sua própria tabela completa. É a técnica clássica pra combater o problema de *merge* (duas cadeias diferentes colidindo e virando a mesma dali em diante), que limita muito a cobertura de uma tabela única.

## 2. Decisões de implementação

**`myHash` (dada no enunciado):** validei contra o exemplo `echo -n GBC0831234 | sha256sum` e bate exatamente (`5042f15f...609b8f`). Uma observação de análise de código: a função tem duas instruções `return` — como Python sai da função no primeiro `return` que executa, a linha `return hash_object.digest()` é **código morto** (nunca executa). Mantive o bug no arquivo (comentado) e documentei isso, já que o enunciado pediu para usar a função como está.

**Espaço de senhas "pequenas":** interpretei como **uma única palavra do Diceware** (não uma frase-senha completa), já que a wordlist tem 7776 palavras (5 dados de 6 faces = 6⁵), o que dá um espaço pequeno o suficiente para caber inteiro na memória e permitir testar a RT de ponta a ponta em segundos — exatamente o tipo de cenário didático que a disciplina pede.

**Função de redução:** `R_cor(hash, posição) = palavra[ SHA256("cor:posição:hash") mod N ]`. A posição entra na combinação porque é isso que faz R₀, R₁, ..., R_{W-1} serem funções diferentes entre si dentro da mesma cadeia (requisito clássico de RT — sem isso, duas cadeias que colidem numa posição colidem para sempre). O "cor" entra para criar famílias de redução totalmente independentes entre tabelas.

**Múltiplas cores:** implementei como múltiplas tabelas completas e independentes, cada uma com seu próprio `seed` e sua própria família de reduções. Na quebra, percorre-se todas as cores.

**Wordlist:** o código tenta, nessa ordem: (1) arquivo local, (2) baixar de `world.std.com`, (3) se nada funcionar, gera uma wordlist sintética de 7776 pseudo-palavras determinística (só para testes). **Isso é relevante**: o sandbox onde rodei os testes tem a rede bloqueada para esse host (testei com `curl`, erro de DNS), então os números abaixo usam a wordlist sintética — mas o algoritmo é indiferente ao conteúdo da lista, só ao seu tamanho (7776), então os resultados valem igualmente para a Diceware real. No seu computador, rodando `python3 rainbow_table.py`, o download real deve funcionar normalmente.

## 3. Hardware e ambiente dos testes

| Item | Valor |
|---|---|
| CPU | Intel Xeon @ 2.10GHz, **1 vCPU** |
| RAM | 3.9 GiB |
| SO | Linux x86_64 |
| Python | 3.12.3 |
| Execução | single-threaded, sem paralelismo |

Importante registrar no relatório: por ser 1 vCPU single-thread, os tempos de construção/busca são um **limite superior conservador** — em hardware real multi-core, a construção da tabela paraleliza trivialmente (cada cadeia é independente).

## 4. Testes e análises

### 4.1 Baseline — tabela direta (hash→senha completa)

Pra ter régua de comparação, construí a tabela "ingênua" com as 7776 entradas:

- Construção: 0,009 s
- Tamanho: **590.278 bytes** (~577 KB)
- Sucesso: 100%, O(1) por busca

### 4.2 Efeito da **largura** (altura=3000, 1 cor, 150 tentativas)

| Largura | Taxa de sucesso | Tempo construção | Tempo médio de busca | Pares únicos/possíveis |
|---|---|---|---|---|
| 10 | 80,7% | 0,05 s | 0,09 ms | 938 / 3000 |
| 30 | 82,7% | 0,14 s | 0,57 ms | 437 / 3000 |
| 100 | 83,3% | 0,46 s | 6,7 ms | 149 / 3000 |
| 300 | 83,3% | 1,35 s | 40,9 ms | 47 / 3000 |

**Análise:** a taxa de sucesso satura rápido (~83%) enquanto custo de construção e de busca crescem quase linear/quadraticamente com a largura. O motivo é visível na coluna "pares únicos": com largura grande, cada vez mais cadeias colidem (*merge*) e viram a mesma linha na tabela — de 3000 cadeias geradas, sobram só 47 únicas com largura 300. Ou seja, aumentar a largura sem limite é **ineficiente** quando o espaço de senhas (7776) é pequeno comparado a altura×largura.

### 4.3 Efeito da **altura** (largura=50, 1 cor, 150 tentativas)

| Altura | Taxa de sucesso | Tempo construção | Memória | Pares únicos/possíveis |
|---|---|---|---|---|
| 500 | 75,3% | 0,04 s | 3.444 B | 193 / 500 |
| 1500 | 84,0% | 0,11 s | 4.413 B | 248 / 1500 |
| 4000 | 83,3% | 0,37 s | 4.821 B | 274 / 4000 |
| 8000 | 89,3% | 0,72 s | 5.009 B | 283 / 8000 |

**Análise:** aumentar a altura ajuda mais que aumentar a largura (ganho de cobertura mais consistente), mas também satura — o número de pares *únicos* cresce muito mais devagar que a altura (de 500→8000 cadeias geradas, únicos só vão de 193→283). É o mesmo fenômeno de colisão: depois de um ponto, novas cadeias tendem a cair em caminhos já cobertos.

### 4.4 Efeito das **cores** — mesmo orçamento total de armazenamento (1000 tentativas na config final)

Fixei o "orçamento" altura×largura×cores = 500.000 e variei como ele é distribuído:

| Config | Sucesso (n=150) | Memória | Pares únicos |
|---|---|---|---|
| 1 cor (altura 5000, largura 100) | 87,3% | 2.730 B | 153 |
| 2 cores (altura 2500, largura 100) | 97,3% | 5.110 B | 286 |
| 4 cores (altura 1250, largura 100) | **100,0%** | 9.822 B | 553 |

Rodando a config de 4 cores com uma amostra maior (n=1000) pra confiança estatística: **99,8% de sucesso**, 9.841 bytes de memória, 0,98 s de construção, busca média de 7,3 ms (máxima 82 ms).

**Esta é a conclusão mais importante do trabalho**: com o *mesmo* orçamento de trabalho computacional, dividir em mais cores supera investir tudo numa cadeia mais longa ou numa tabela maior. Isso acontece porque cada cor usa uma família de redução *independente*, então os pontos "mortos" por colisão de uma cor tendem a não coincidir com os de outra — cobrindo partes diferentes do espaço de senhas.

### 4.5 RT vs. tabela direta — a economia real

Comparando a melhor config de RT com o baseline da seção 4.1:

- Tabela direta: 590.278 bytes, 100% de sucesso
- RT (4 cores, altura 1250, largura 100): **9.841 bytes**, 99,8% de sucesso

Ou seja, **~60× menos memória** por uma perda de sucesso de apenas 0,2 pontos percentuais. Esse é exatamente o ponto pedagógico da rainbow table: trocar memória por um pouco de tempo de computação (cada busca recalcula até largura hashes, em vez de 1 lookup direto).

## 5. Discussão crítica / limitações

- **O espaço escolhido é propositalmente pequeno** (7776 ≈ 2¹³). Isso é ótimo para demonstrar o algoritmo em segundos, mas também significa que, na prática, uma única palavra Diceware é **trivialmente quebrável por força bruta pura** (7776 hashes, <0,01 s, como mostrado na seção 4.1) — ninguém precisaria de uma rainbow table pra isso. O valor real de uma RT aparece em espaços muito maiores (ex.: senhas alfanuméricas de 8 caracteres, ~2×10¹⁴ possibilidades), onde a tabela direta seria inviável de armazenar mas a RT ainda cabe em disco.
- **Colisões/merges** dominam o comportamento observado: em espaços pequenos, aumentar altura×largura além de um certo ponto rende cada vez menos cobertura nova — por isso a recomendação clássica da literatura é manter altura×largura próximo do tamanho do espaço de senhas (aqui, ≈ 7776), e não muito acima disso.
- **`random` não é criptograficamente seguro**, mas isso não compromete o exercício — ele só é usado para escolher a senha inicial de cada cadeia, não para nenhuma operação de segurança real.
- A busca (`quebrar_hash`) no pior caso é O(largura² ) por tabela quando a senha não está coberta (precisa testar a hipótese de a senha estar em cada uma das `largura` posições da cadeia), o que explica o crescimento do tempo médio de busca na seção 4.2.

Se quiser, posso rodar mais variações (por exemplo, comparar o efeito de cores com largura fixa ao invés de orçamento fixo, ou testar com a wordlist Diceware real — bastando você rodar localmente onde há acesso à internet) e trazer os números pra cá.