#!/usr/bin/env python3
"""Calibração do SDS011 face a uma estação de referência (regressão linear).

Entradas (CSV com cabeçalho; médias horárias, tempo em UTC):
  --estacao  estacao.csv     colunas: tempo_utc, pm25   (exportado da API: /api/export.csv)
  --ref      referencia.csv  colunas: tempo_utc, pm25   (estação de referência oficial)

Uso:
  python calibracao.py --estacao estacao.csv --ref referencia.csv
  python calibracao.py --demo        # dados SINTÉTICOS, só para testar o método

Saídas: coeficientes A e B (para config.h), r, R², MAE, RMSE, bias, incerteza
expandida (k = 2) e figuras em PNG.
"""
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def dados_sinteticos(semente=7, dias=25):
    """Gera séries horárias sintéticas (NÃO são medições reais)."""
    rng = np.random.default_rng(semente)
    t = pd.date_range("2026-01-01", periods=dias * 24, freq="h")
    h = np.arange(len(t))
    ref = 9 + 4 * np.sin(2 * np.pi * (h % 24 - 7) / 24) + 3 * np.sin(2 * np.pi * h / (24 * 6.5))
    ref += rng.gamma(2, 1.2, len(t)) - 2.4
    ref = np.clip(ref, 1.5, None)
    sds = 1.38 * ref + 2.1 + rng.normal(0, 2.0, len(t))           # sobrestimação típica
    sds = np.clip(sds, 0.5, None)
    return (pd.DataFrame({"tempo_utc": t, "pm25": sds}),
            pd.DataFrame({"tempo_utc": t, "pm25": ref}))


def metricas(ref, est):
    e = est - ref
    return {"MAE": np.mean(np.abs(e)), "RMSE": np.sqrt(np.mean(e**2)), "bias": np.mean(e)}


def calibrar(est, ref, fracao_treino=0.6):
    df = est.merge(ref, on="tempo_utc", suffixes=("_med", "_ref")).dropna().sort_values("tempo_utc")
    if len(df) < 48:
        raise SystemExit("Dados insuficientes: são necessárias, no mínimo, 48 horas coincidentes.")
    n = int(len(df) * fracao_treino)
    treino, valid = df.iloc[:n], df.iloc[n:]

    # Regressão: PM_ref = a * PM_med + b  (a, b aplicam-se diretamente no firmware)
    a, b = np.polyfit(treino["pm25_med"], treino["pm25_ref"], 1)
    r = np.corrcoef(treino["pm25_med"], treino["pm25_ref"])[0, 1]
    res = treino["pm25_ref"] - (a * treino["pm25_med"] + b)
    s_cal = res.std(ddof=2)                                       # desvio padrão residual

    valid = valid.assign(pm25_corr=a * valid["pm25_med"] + b)
    antes = metricas(valid["pm25_ref"], valid["pm25_med"])
    depois = metricas(valid["pm25_ref"], valid["pm25_corr"])

    # Incerteza (GUM): componentes combinadas em quadratura, k = 2
    s_rep = 0.5            # µg/m³ — substituir pelo desvio padrão de 10 leituras consecutivas
    s_ref = 1.0            # µg/m³ — incerteza da estação de referência (ver relatório da entidade)
    U = 2 * np.sqrt(s_cal**2 + s_rep**2 + s_ref**2)
    return dict(df=df, treino=treino, valid=valid, a=a, b=b, r=r, r2=r**2, s_cal=s_cal,
                antes=antes, depois=depois, U=U)


def figuras(res, prefixo="calibracao"):
    t, v = res["treino"], res["valid"]
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    ax.scatter(t["pm25_med"], t["pm25_ref"], s=8, alpha=.5, color="0.35", label="Treino")
    x = np.linspace(0, t["pm25_med"].max(), 50)
    ax.plot(x, res["a"] * x + res["b"], "k-", lw=1.4, label=f"y = {res['a']:.2f}x + {res['b']:.2f}  (r = {res['r']:.2f})")
    ax.set_xlabel("PM2.5 SDS011 (µg/m³)"); ax.set_ylabel("PM2.5 referência (µg/m³)")
    ax.legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(f"{prefixo}_dispersao.png", dpi=200)

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(v["tempo_utc"], v["pm25_ref"], "k-", lw=1.2, label="Referência")
    ax.plot(v["tempo_utc"], v["pm25_med"], color="0.65", lw=.9, label="SDS011 bruto")
    ax.plot(v["tempo_utc"], v["pm25_corr"], "k--", lw=1.0, label="SDS011 corrigido")
    ax.set_ylabel("PM2.5 (µg/m³)"); ax.legend(frameon=False, ncol=3, fontsize=8)
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(f"{prefixo}_validacao.png", dpi=200)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--estacao"); p.add_argument("--ref"); p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    if args.demo:
        est, ref = dados_sinteticos()
        print("AVISO: dados sintéticos — apenas demonstração do método.")
    else:
        est = pd.read_csv(args.estacao, parse_dates=["tempo_utc"]); ref = pd.read_csv(args.ref, parse_dates=["tempo_utc"])
        est["tempo_utc"] = est["tempo_utc"].dt.tz_localize(None) if est["tempo_utc"].dt.tz else est["tempo_utc"]
        ref["tempo_utc"] = ref["tempo_utc"].dt.tz_localize(None) if ref["tempo_utc"].dt.tz else ref["tempo_utc"]
    res = calibrar(est, ref)
    print(f"A = {res['a']:.4f}   B = {res['b']:.4f}   r = {res['r']:.3f}   R2 = {res['r2']:.3f}")
    print("Antes :", {k: round(x, 2) for k, x in res["antes"].items()})
    print("Depois:", {k: round(x, 2) for k, x in res["depois"].items()})
    print(f"Incerteza expandida U (k=2) = ±{res['U']:.2f} µg/m³")
    print(f"\nCopiar para config.h:\n#define CAL_PM25_A {res['a']:.3f}f\n#define CAL_PM25_B {res['b']:.3f}f")
    figuras(res)
