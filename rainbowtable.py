"""
rainbow_table.py
=================
Implementacao de uma Rainbow Table (RT) para quebra de senhas "pequenas"
baseadas na wordlist Diceware.

Uso tipico:
    python3 rainbow_table.py --wordlist diceware.wordlist.asc \
        --colors 4 --height 20000 --width 400 --trials 500

Se nenhuma wordlist for encontrada em disco e o download falhar (ex.: rede
bloqueada), o script cai para uma wordlist sintetica reprodutivel, apenas
para fins de teste do algoritmo (ver gerar_wordlist_sintetica()).
"""

import argparse
import hashlib
import json
import os
import pickle
import random
import sys
import time
import urllib.request

DICEWARE_URL = "http://world.std.com/~reinhold/diceware.wordlist.asc"
CACHE_PATH = "diceware.wordlist.asc"


# ---------------------------------------------------------------------------
# 1. Funcao de hash (fornecida pelo enunciado)
# ---------------------------------------------------------------------------
def myHash(s: str) -> str:
    hash_object = hashlib.sha256()
    hash_object.update(b"GBC083")
    hash_object.update(s.encode('utf-8'))
    return hash_object.hexdigest()
    # NOTA: a linha abaixo, presente no enunciado original, e codigo morto
    # (unreachable): uma funcao Python retorna no primeiro `return` que
    # executa, entao `hash_object.digest()` jamais e alcancado. Isso e
    # discutido no relatorio.
    # return hash_object.digest()


# ---------------------------------------------------------------------------
# 2. Carregamento da wordlist Diceware
# ---------------------------------------------------------------------------
def carregar_diceware(caminho_local: str = CACHE_PATH, url: str = DICEWARE_URL):
    """Carrega a wordlist diceware (formato 'NNNNN\\tpalavra' por linha).

    Ordem de tentativas:
      1) arquivo local (cache ja baixado)
      2) download da URL oficial
      3) wordlist sintetica reprodutivel (apenas para teste do algoritmo
         quando a rede do ambiente de execucao bloqueia o host oficial)
    """
    if os.path.exists(caminho_local):
        return _parse_diceware(open(caminho_local, encoding="latin-1").read())

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            texto = resp.read().decode("latin-1")
        with open(caminho_local, "w", encoding="latin-1") as f:
            f.write(texto)
        return _parse_diceware(texto)
    except Exception as e:
        print(f"[aviso] nao foi possivel baixar a wordlist oficial ({e}); "
              f"usando wordlist sintetica para teste.", file=sys.stderr)
        return gerar_wordlist_sintetica()


def _parse_diceware(texto: str):
    palavras = []
    for linha in texto.splitlines():
        partes = linha.strip().split()
        if len(partes) == 2 and partes[0].isdigit() and len(partes[0]) == 5:
            palavras.append(partes[1])
    if not palavras:
        raise ValueError("wordlist diceware vazia ou em formato inesperado")
    return palavras


def gerar_wordlist_sintetica(n: int = 7776, seed: int = 83):
    """Gera uma lista de 7776 pseudo-palavras (mesmo tamanho da diceware
    real) de forma determinista, para permitir testar o algoritmo em
    ambientes sem acesso ao host world.std.com."""
    rng = random.Random(seed)
    silabas = ["ba", "ca", "da", "fe", "go", "hi", "ju", "ka", "lo", "mu",
               "ne", "pi", "ra", "se", "ta", "vu", "wi", "xo", "ya", "zu"]
    vistas = set()
    palavras = []
    while len(palavras) < n:
        w = "".join(rng.choice(silabas) for _ in range(rng.randint(2, 3)))
        if w not in vistas:
            vistas.add(w)
            palavras.append(w)
    return palavras


# ---------------------------------------------------------------------------
# 3. Funcoes de reducao (uma familia por "cor")
# ---------------------------------------------------------------------------
def fabrica_reducao(wordlist, cor: int):
    """Cria uma funcao de reducao R_i(hash) -> palavra_diceware.

    Cada "cor" usa um sal diferente, e cada posicao i da cadeia tambem
    entra na combinacao -- isso e o que a literatura chama de familia de
    funcoes de reducao R_0 .. R_{w-1}: evita que duas cadeias que colidem
    numa posicao i continuem identicas dali em diante (reduz fusao/merge).
    """
    n = len(wordlist)

    def reducao(hash_hex: str, posicao: int) -> str:
        combinado = f"{cor}:{posicao}:{hash_hex}".encode("utf-8")
        digest = hashlib.sha256(combinado).hexdigest()
        idx = int(digest, 16) % n
        return wordlist[idx]

    return reducao


# ---------------------------------------------------------------------------
# 4. Geracao de cadeias e construcao da tabela
# ---------------------------------------------------------------------------
def gerar_cadeia(senha_inicial: str, largura: int, reducao):
    atual = senha_inicial
    for i in range(largura):
        h = myHash(atual)
        atual = reducao(h, i)
    return atual  # senha final da cadeia


def construir_tabela(wordlist, altura: int, largura: int, reducao, rng=None):
    """Constroi uma Rainbow Table (uma unica "cor").

    altura = numero de cadeias (linhas)
    largura = numero de reducoes por cadeia (comprimento da cadeia)

    Retorna um dict {senha_final: senha_inicial} -- so os extremos sao
    armazenados, como em uma RT real.
    """
    rng = rng or random.Random()
    tabela = {}
    colisoes_na_construcao = 0
    for _ in range(altura):
        inicio = rng.choice(wordlist)
        fim = gerar_cadeia(inicio, largura, reducao)
        if fim in tabela:
            colisoes_na_construcao += 1
        tabela[fim] = inicio  # ultima cadeia com esse fim "vence"
    return tabela, colisoes_na_construcao


def construir_multitabela(wordlist, altura: int, largura: int, n_cores: int,
                           seed: int = 0):
    """Constroi n_cores tabelas independentes (cada uma com sua propria
    familia de funcoes de reducao). Retorna lista de (tabela, reducao)."""
    resultado = []
    stats = []
    for cor in range(n_cores):
        rng = random.Random(seed * 1000 + cor)
        reducao = fabrica_reducao(wordlist, cor)
        tabela, colisoes = construir_tabela(wordlist, altura, largura, reducao, rng)
        resultado.append((tabela, reducao))
        stats.append({
            "cor": cor,
            "cadeias_geradas": altura,
            "finais_unicos": len(tabela),
            "colisoes_na_construcao": colisoes,
            "taxa_cobertura_bruta": len(tabela) / altura,
        })
    return resultado, stats


# ---------------------------------------------------------------------------
# 5. Fase online: quebra de uma senha a partir do hash alvo
# ---------------------------------------------------------------------------
def quebrar_hash(hash_alvo: str, tabelas, largura: int, max_tentativas_merge=1):
    """Tenta recuperar a senha original a partir de hash_alvo, percorrendo
    todas as (tabela, reducao) fornecidas (uma por cor).

    Retorna (senha, cor, posicao_estimada) ou (None, None, None).
    """
    for cor, (tabela, reducao) in enumerate(tabelas):
        for i in range(largura - 1, -1, -1):
            # Reconstroi a cadeia assumindo que hash_alvo apareceu na
            # posicao i, avancando ate o fim da cadeia (posicao largura-1).
            atual = reducao(hash_alvo, i)
            for j in range(i + 1, largura):
                h = myHash(atual)
                atual = reducao(h, j)
            fim_candidato = atual

            if fim_candidato in tabela:
                inicio = tabela[fim_candidato]
                senha = inicio
                for j in range(largura):
                    h = myHash(senha)
                    if h == hash_alvo:
                        return senha, cor, j
                    senha = reducao(h, j)
                # "falso positivo" de fusao: o final bate mas a senha nao
                # estava nessa cadeia -> segue tentando outras posicoes/tabelas
    return None, None, None


# ---------------------------------------------------------------------------
# 6. Harness de testes / metricas
# ---------------------------------------------------------------------------
def rodar_experimento(wordlist, altura, largura, n_cores, n_trials, seed=0,
                       amostrar_fora_da_tabela=True):
    rng = random.Random(seed)

    t0 = time.perf_counter()
    tabelas, stats_construcao = construir_multitabela(
        wordlist, altura, largura, n_cores, seed=seed)
    t_construcao = time.perf_counter() - t0

    tam_memoria = sum(
        sys_getsize_dict(tabela) for tabela, _ in tabelas
    )

    senhas_alvo = [rng.choice(wordlist) for _ in range(n_trials)]

    acertos = 0
    tempos_busca = []
    for senha in senhas_alvo:
        h = myHash(senha)
        t1 = time.perf_counter()
        recuperada, cor, pos = quebrar_hash(h, tabelas, largura)
        tempos_busca.append(time.perf_counter() - t1)
        if recuperada == senha:
            acertos += 1

    cobertura_teorica = 1 - sum(
        (1 - len(tabela) / len(wordlist)) for tabela, _ in tabelas
    ) / n_cores  # aproximacao media por cor, ver relatorio

    return {
        "parametros": {
            "altura": altura, "largura": largura, "cores": n_cores,
            "tamanho_espaco_senhas": len(wordlist), "n_trials": n_trials,
        },
        "construcao": {
            "tempo_s": t_construcao,
            "memoria_bytes_aprox": tam_memoria,
            "pares_unicos_total": sum(len(t) for t, _ in tabelas),
            "pares_possiveis_total": altura * n_cores,
            "stats_por_cor": stats_construcao,
        },
        "crack": {
            "taxa_sucesso": acertos / n_trials,
            "acertos": acertos,
            "tentativas": n_trials,
            "tempo_medio_busca_s": sum(tempos_busca) / len(tempos_busca),
            "tempo_max_busca_s": max(tempos_busca),
        },
    }


def sys_getsize_dict(d: dict) -> int:
    # aproximacao: soma do pickle (reflete melhor o custo real de
    # armazenamento em disco do que sys.getsizeof, que so mede o objeto
    # dict em si e nao as strings referenciadas em CPython >=3.6 de forma
    # confiavel entre versoes).
    return len(pickle.dumps(d, protocol=pickle.HIGHEST_PROTOCOL))


def salvar_tabela(tabelas, caminho="rainbow_table.pkl"):
    with open(caminho, "wb") as f:
        pickle.dump(tabelas, f, protocol=pickle.HIGHEST_PROTOCOL)


def carregar_tabela(caminho="rainbow_table.pkl"):
    with open(caminho, "rb") as f:
        return pickle.load(f)


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wordlist", default=CACHE_PATH,
                     help="caminho do arquivo diceware.wordlist.asc")
    ap.add_argument("--altura", type=int, default=20000,
                     help="numero de cadeias por tabela (altura)")
    ap.add_argument("--largura", type=int, default=400,
                     help="comprimento de cada cadeia (largura)")
    ap.add_argument("--cores", type=int, default=4,
                     help="numero de tabelas/funcoes de reducao distintas")
    ap.add_argument("--trials", type=int, default=300,
                     help="numero de senhas aleatorias testadas na quebra")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--salvar", default=None,
                     help="se definido, salva a(s) tabela(s) nesse caminho (pickle)")
    args = ap.parse_args()

    wordlist = carregar_diceware(args.wordlist)
    print(f"Wordlist carregada: {len(wordlist)} palavras.")

    resultado = rodar_experimento(
        wordlist, args.altura, args.largura, args.cores, args.trials,
        seed=args.seed)

    print(json.dumps(resultado, indent=2, ensure_ascii=False))

    if args.salvar:
        tabelas, _ = construir_multitabela(
            wordlist, args.altura, args.largura, args.cores, seed=args.seed)
        salvar_tabela(tabelas, args.salvar)
        print(f"Tabela salva em {args.salvar}")


if __name__ == "__main__":
    main()