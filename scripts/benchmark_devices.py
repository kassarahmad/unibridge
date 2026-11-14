"""CPU vs GPU benchmark of the two models UniBridge runs locally: the embedding model and the LLM.

Parts (each can be run alone; results are merged into the same JSON file):
- embeddings  multilingual-e5-small through SentenceTransformerEmbedder (same prefixes and batch size as the
              application), on cpu and on cuda: model load time, indexing of every indexed passage of the UniBridge
              SQLite file, 200 single-query latencies. One warm-up batch before timing; torch.cuda.synchronize()
              before every clock read on cuda.
- llm         the local LLM in LM Studio, loaded with full GPU offload (`lms load --gpu max`) and on CPU only
              (`lms load --gpu off`): load time, then 20 real answer prompts (answer_prompt() with the top-6
              passages of test questions in Italian, English and Arabic), streamed, without any cache:
              time to first token, total time, output tokens per second.
- e2e         POST /v1/answer (in-process API, no response cache) on the same 20 questions, with the embedding
              model on cuda and on cpu; the LLM stays on the GPU. Measured for LLM answers and extractive answers.

No paid API is called: the only LLM endpoint is the local LM Studio server.

Usage:
    python scripts/benchmark_devices.py [--parts embeddings,llm,e2e] [--model qwen3vl-8b-instruct] [--force]
    python scripts/benchmark_devices.py --render-only
Outputs: eval/results/unibridge/benchmark_devices.json, benchmark_devices.md, docs/images/benchmark_devices.png
A part that is already in the JSON file is skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval" / "unibridge"))
os.chdir(ROOT)  # settings use paths relative to the repository root

from ub_common import RESULTS, principals, queries, unibridge_settings, write_json  # noqa: E402

from p14_search.evaluation.metrics import percentile  # noqa: E402

OUT_JSON = RESULTS / "benchmark_devices.json"
OUT_MD = RESULTS / "benchmark_devices.md"
OUT_PNG = ROOT / "docs" / "images" / "benchmark_devices.png"
BATCH = 64
N_QUERY_LATENCIES = 200
N_PROMPTS = 20
PER_LANGUAGE = {"it": 7, "en": 7, "ar": 6}
CONTEXT = 8192
LMS_TIMEOUT_S = 600


def med(xs: list[float], digits: int) -> float:
    return round(statistics.median(xs), digits)


def p95(xs: list[float], digits: int) -> float:
    return round(percentile(xs, 95), digits)


def run(cmd: list[str], timeout: int = 60) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def gpu_memory_mib() -> int | None:
    try:
        return int(run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]).strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def on_ac_power() -> bool | None:
    """True on mains power, False on battery, None when unknown. On battery a laptop throttles CPU and GPU
    (the GPU clock drops to a fraction), so the measurements would not describe the hardware."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                        ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

        status = Status()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) or status.ACLineStatus > 1:
            return None
        return status.ACLineStatus == 1
    except (AttributeError, OSError):
        return None


def system_info() -> dict:
    import torch

    cpu = platform.processor()
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        pass
    info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})", "python": platform.python_version(),
        "cpu": cpu, "logical_threads": os.cpu_count(), "torch": torch.__version__, "torch_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(), "on_ac_power": on_ac_power(),
    }
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        info.update(gpu=props.name, gpu_memory_mib=round(props.total_memory / 2**20))
        try:
            info["gpu_driver"] = run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]).strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return info


def bench_questions() -> list[dict]:
    """The same 20 in-scope test questions for the LLM prompts and the end-to-end run: 7 it, 7 en, 6 ar, by qid."""
    test = sorted((q for q in queries("test") if q["type"] != "out_of_scope"), key=lambda q: q["qid"])
    out = []
    for lang, n in PER_LANGUAGE.items():
        out += [q for q in test if q["lang"] == lang][:n]
    assert len(out) == N_PROMPTS
    return out


# --- embeddings ------------------------------------------------------------------------------------
def bench_embeddings() -> dict:
    import sqlite3

    import torch

    from p14_search.indexing.embedder import MODEL_PREFIXES, SentenceTransformerEmbedder

    settings = unibridge_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    passages = [r[0] for r in conn.execute("SELECT text FROM passages WHERE indexed = 1 ORDER BY rowid")]
    conn.close()
    texts = [q["query"] for q in queries()]
    single = [texts[i % len(texts)] for i in range(N_QUERY_LATENCIES)]  # the question file is cycled up to 200

    def sync(device: str) -> None:
        if device == "cuda":
            torch.cuda.synchronize()

    SentenceTransformerEmbedder(settings.embedding_model, "cpu")  # not timed: puts the model files in the OS file cache
    out = {"model": settings.embedding_model, "prefixes": list(MODEL_PREFIXES[settings.embedding_model]), "batch_size": BATCH,
           "n_passages": len(passages), "passage_chars": sum(len(p) for p in passages), "n_query_latencies": len(single),
           "n_distinct_queries": len(texts)}
    for device in ("cpu", "cuda"):
        start = time.perf_counter()
        embedder = SentenceTransformerEmbedder(settings.embedding_model, device, batch_size=BATCH)
        sync(device)
        load_s = time.perf_counter() - start
        embedder.embed_passages(passages[:BATCH])  # warm-up, not timed
        for q in single[:5]:
            embedder.embed_queries([q])
        sync(device)
        start = time.perf_counter()
        vectors = embedder.embed_passages(passages)
        sync(device)
        index_s = time.perf_counter() - start
        assert vectors.shape == (len(passages), embedder.dim)
        latencies = []
        for q in single:
            start = time.perf_counter()
            embedder.embed_queries([q])
            sync(device)
            latencies.append((time.perf_counter() - start) * 1000)
        out[device] = {
            "device": str(embedder.model.device), "torch_threads": torch.get_num_threads(), "load_s": round(load_s, 2),
            "index_s": round(index_s, 2), "passages_per_s": round(len(passages) / index_s, 1),
            "query_ms_median": med(latencies, 2), "query_ms_p95": p95(latencies, 2),
        }
        print("embeddings", device, out[device], flush=True)
        del embedder
        if device == "cuda":
            torch.cuda.empty_cache()
    out["speedup_cuda_vs_cpu"] = {
        "indexing": round(out["cpu"]["index_s"] / out["cuda"]["index_s"], 1),
        "query_median": round(out["cpu"]["query_ms_median"] / out["cuda"]["query_ms_median"], 1),
    }
    return out


# --- LLM -------------------------------------------------------------------------------------------
def build_prompts(questions: list[dict]) -> list[dict]:
    """answer_prompt() with the top-6 passages that the answer service retrieves (S2 hybrid, role visitor)."""
    from p14_search.answer import prompts
    from p14_search.answer.service import _Usage
    from p14_search.services import build_services

    # embedding model on the CPU: the GPU memory stays free for the LLM measurements
    settings = unibridge_settings().model_copy(update={"llm_provider": "", "embedding_device": "cpu"})
    services = build_services(settings)
    visitor = principals(settings)["visitor"]
    k = settings.answer_top_k
    out = []
    for q in questions:
        hits, _, _ = services.answer.retrieve(q["query"], q["lang"], visitor, k, False, _Usage())
        docs = services.search.hydrate(hits, visitor)
        ordered = sorted((p for d in docs for p in d.passages), key=lambda p: p.evidence.rank)[:k]
        labelled = [(f"P{i + 1}", " - ".join(x for x in (p.citation.title, p.citation.section) if x), p.text)
                    for i, p in enumerate(ordered)]
        system, user = prompts.answer_prompt(q["query"], q["lang"], labelled)
        out.append({"qid": q["qid"], "lang": q["lang"], "system": system, "user": user, "passages": len(labelled)})
    return out


def lms(*args: str) -> tuple[str, float]:
    exe = shutil.which("lms")
    if not exe:
        raise SystemExit("the LM Studio command line tool `lms` is not on PATH")
    start = time.perf_counter()
    out = run([exe, *args], timeout=LMS_TIMEOUT_S)
    return out, time.perf_counter() - start


def load_model(model: str, gpu: str) -> dict:
    """Unload everything, then load `model` with the given GPU offload ('max' or 'off'). Returns load time and memory."""
    lms("unload", "--all")
    time.sleep(2)
    before = gpu_memory_mib()
    out, seconds = lms("load", model, "--gpu", gpu, "--context-length", str(CONTEXT), "--identifier", model, "-y")
    if "loaded successfully" not in out:
        raise SystemExit(f"lms load failed: {out[-400:]}")
    after = gpu_memory_mib()
    return {"lms_gpu_option": gpu, "load_s": round(seconds, 1), "gpu_memory_before_mib": before, "gpu_memory_after_mib": after,
            "gpu_memory_delta_mib": None if before is None or after is None else after - before}


def stream_once(client, model: str, system: str, user: str, max_tokens: int) -> dict:
    start = time.perf_counter()
    first = None
    pieces, usage = [], None
    stream = client.chat.completions.create(
        model=model, temperature=0, max_tokens=max_tokens, stream=True, stream_options={"include_usage": True},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            if first is None:
                first = time.perf_counter()
            pieces.append(chunk.choices[0].delta.content)
    end = time.perf_counter()
    first = first or end
    tokens_out = usage.completion_tokens if usage else len(pieces)  # without usage: one streamed piece = one token
    generation_s = end - first
    return {"ttft_s": first - start, "total_s": end - start, "input_tokens": usage.prompt_tokens if usage else None,
            "output_tokens": tokens_out,
            # the first token arrives at `first`, so the remaining tokens are generated in `generation_s`
            "tokens_per_s": (tokens_out - 1) / generation_s if tokens_out >= 8 and generation_s > 0 else None,
            "text": "".join(pieces)}


def bench_llm(model: str, base_url: str, prompts_: list[dict], max_tokens: int) -> dict:
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key="local", timeout=1800, max_retries=0)
    out = {"server": "LM Studio (OpenAI-compatible API)", "base_url": base_url, "model": model, "context_length": CONTEXT,
           "temperature": 0, "max_output_tokens": max_tokens, "n_prompts": len(prompts_),
           "prompt_languages": {lang: sum(1 for p in prompts_ if p["lang"] == lang) for lang in PER_LANGUAGE},
           "passages_per_prompt": med([p["passages"] for p in prompts_], 0)}
    try:
        listing = json.loads(lms("ls", "--json")[0])
        entry = next(m for m in listing if m.get("modelKey") == model)
        out.update(model_name=entry.get("displayName"), parameters=entry.get("paramsString"),
                   quantization=(entry.get("quantization") or {}).get("name"), file_gb=round(entry["sizeBytes"] / 1e9, 2))
    except (ValueError, StopIteration, KeyError):
        pass
    for label, gpu in (("gpu", "max"), ("cpu", "off")):
        mode = load_model(model, gpu)
        stream_once(client, model, "Reply with one word.", "Say ok.", 5)  # warm-up, not timed
        runs = []
        for i, p in enumerate(prompts_):
            r = stream_once(client, model, p["system"], p["user"], max_tokens)
            runs.append({"qid": p["qid"], "lang": p["lang"], **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}})
            print("llm", label, i + 1, p["qid"], p["lang"], f"ttft {r['ttft_s']:.2f}s total {r['total_s']:.2f}s out {r['output_tokens']}", flush=True)
        rates = [r["tokens_per_s"] for r in runs if r["tokens_per_s"] is not None]
        mode.update(
            ttft_s_median=med([r["ttft_s"] for r in runs], 2), ttft_s_p95=p95([r["ttft_s"] for r in runs], 2),
            total_s_median=med([r["total_s"] for r in runs], 2), total_s_p95=p95([r["total_s"] for r in runs], 2),
            tokens_per_s_median=med(rates, 1), tokens_per_s_p95=p95(rates, 1), tokens_per_s_n=len(rates),
            output_tokens_median=med([r["output_tokens"] for r in runs], 0),
            citation_format_ok=sum(1 for r in runs if "[P" in r["text"] or r["text"].strip().startswith("NO_ANSWER")),
            runs=runs,
        )
        if all(r["input_tokens"] for r in runs):
            mode["input_tokens_median"] = med([r["input_tokens"] for r in runs], 0)
        out[label] = mode
        print("llm", label, {k: v for k, v in mode.items() if k != "runs"}, flush=True)
    out["speedup_gpu_vs_cpu"] = {
        "time_to_first_token": round(out["cpu"]["ttft_s_median"] / out["gpu"]["ttft_s_median"], 1),
        "total_time": round(out["cpu"]["total_s_median"] / out["gpu"]["total_s_median"], 1),
        "tokens_per_s": round(out["gpu"]["tokens_per_s_median"] / out["cpu"]["tokens_per_s_median"], 1),
    }
    load_model(model, "max")  # leave the model on the GPU for the application
    return out


# --- end to end ------------------------------------------------------------------------------------
def bench_e2e(model: str, base_url: str, questions: list[dict]) -> dict:
    import torch
    from fastapi.testclient import TestClient

    from p14_search.answer.llm import LocalProvider
    from p14_search.api.app import create_app
    from p14_search.indexing.embedder import SentenceTransformerEmbedder
    from p14_search.security.principals import PrincipalRegistry
    from p14_search.services import build_services

    settings = unibridge_settings().model_copy(update={"llm_provider": "local", "llm_model": model, "llm_base_url": base_url})
    registry = PrincipalRegistry({"bench-visitor": principals(settings)["visitor"]})
    out = {"endpoint": "POST /v1/answer (in-process API)", "n_questions": len(questions), "llm": f"{model}, full GPU offload",
           "llm_response_cache": "off"}
    for mode in ("llm_verified", "extractive"):
        out[mode] = {}
        for device in ("cuda", "cpu"):
            embedder = SentenceTransformerEmbedder(settings.embedding_model, device)
            services = build_services(settings, embedder=embedder, registry=registry,
                                      llm_provider=LocalProvider(model, base_url, settings.llm_timeout_s))
            services.llm.cache_dir = None  # every call reaches the model
            services.llm.usage_log = None
            client = TestClient(create_app(settings, services=services))

            def ask(q: dict) -> tuple[float, dict]:
                start = time.perf_counter()
                r = client.post("/v1/answer", json={"query": q["query"], "mode": mode}, headers={"X-API-Key": "bench-visitor"})
                seconds = time.perf_counter() - start
                assert r.status_code == 200, r.text
                return seconds, r.json()

            ask(questions[0])  # warm-up, not timed
            seconds, modes, calls = [], {}, []
            for q in questions:
                s, body = ask(q)
                seconds.append(s)
                modes[body["mode"]] = modes.get(body["mode"], 0) + 1
                calls.append((body.get("llm") or {}).get("calls", 0))
            out[mode][f"embeddings_{device}"] = {
                "latency_s_median": med(seconds, 3), "latency_s_p95": p95(seconds, 3), "answer_modes": modes,
                "llm_calls_per_answer": round(sum(calls) / len(calls), 2),
            }
            print("e2e", mode, device, out[mode][f"embeddings_{device}"], flush=True)
            del services, embedder, client
            torch.cuda.empty_cache()
        out[mode]["median_difference_s_cpu_minus_cuda"] = round(
            out[mode]["embeddings_cpu"]["latency_s_median"] - out[mode]["embeddings_cuda"]["latency_s_median"], 3)
    return out


# --- report ----------------------------------------------------------------------------------------
def render_markdown(data: dict) -> str:
    s, e, m, x = data["system"], data.get("embeddings"), data.get("llm"), data.get("e2e")
    lines = ["# CPU vs GPU benchmark", "",
             f"Generated by `scripts/benchmark_devices.py` on {data['generated_at'][:10]}; source: `benchmark_devices.json`.", "",
             f"Machine: {s['cpu']} ({s['logical_threads']} threads), {s.get('gpu', 'no GPU')} "
             f"({s.get('gpu_memory_mib', '-')} MiB), torch {s['torch']} (CUDA {s['torch_cuda']}), {s['os']}.", ""]
    if e:
        c, g = e["cpu"], e["cuda"]
        lines += [f"## Embeddings ({e['model']}, batch {e['batch_size']})", "",
                  "| | CPU | GPU (cuda) | GPU vs CPU |", "|---|---|---|---|",
                  f"| model load (s) | {c['load_s']} | {g['load_s']} | |",
                  f"| indexing {e['n_passages']:,} passages (s) | {c['index_s']} | {g['index_s']} | {e['speedup_cuda_vs_cpu']['indexing']}x faster |",
                  f"| indexing throughput (passages/s) | {c['passages_per_s']} | {g['passages_per_s']} | |",
                  f"| single query, median (ms) | {c['query_ms_median']} | {g['query_ms_median']} | {e['speedup_cuda_vs_cpu']['query_median']}x faster |",
                  f"| single query, p95 (ms) | {c['query_ms_p95']} | {g['query_ms_p95']} | |", ""]
    if m:
        c, g, sp = m["cpu"], m["gpu"], m["speedup_gpu_vs_cpu"]
        lines += [f"## LLM ({m.get('model_name', m['model'])} {m.get('quantization', '')}, context {m['context_length']:,}, LM Studio)", "",
                  f"{m['n_prompts']} answer prompts with {m['passages_per_prompt']:.0f} passages each "
                  f"(median {g.get('input_tokens_median', 0):.0f} input tokens), streamed, no cache.", "",
                  "| | LM Studio `--gpu off` | LM Studio `--gpu max` | Speedup with `max` |", "|---|---|---|---|",
                  f"| model load (s) | {c['load_s']} | {g['load_s']} | |",
                  f"| GPU memory increase at model load (MiB) | {c['gpu_memory_delta_mib']} | {g['gpu_memory_delta_mib']} | |",
                  f"| time to first token, median (s) | {c['ttft_s_median']} | {g['ttft_s_median']} | {sp['time_to_first_token']}x faster |",
                  f"| time to first token, p95 (s) | {c['ttft_s_p95']} | {g['ttft_s_p95']} | |",
                  f"| total time, median (s) | {c['total_s_median']} | {g['total_s_median']} | {sp['total_time']}x faster |",
                  f"| total time, p95 (s) | {c['total_s_p95']} | {g['total_s_p95']} | |",
                  f"| output tokens/s, median | {c['tokens_per_s_median']} | {g['tokens_per_s_median']} | {sp['tokens_per_s']}x faster |",
                  f"| output tokens/s, p95 | {c['tokens_per_s_p95']} | {g['tokens_per_s_p95']} | |", ""]
        lines += ["GPU memory can remain allocated with `--gpu off`. The table reports the load settings and observed allocation.", ""]
    if x:
        lines += [f"## End to end: {x['endpoint']}, {x['n_questions']} questions, LLM on the GPU", "",
                  "| | embeddings on CPU | embeddings on GPU |", "|---|---|---|"]
        for mode, label in (("llm_verified", "LLM answer + verifier"), ("extractive", "extractive answer (no LLM)")):
            c, g = x[mode]["embeddings_cpu"], x[mode]["embeddings_cuda"]
            lines += [f"| {label}, median (s) | {c['latency_s_median']} | {g['latency_s_median']} |",
                      f"| {label}, p95 (s) | {c['latency_s_p95']} | {g['latency_s_p95']} |"]
        lines.append("")
    return "\n".join(lines)


def render_chart(data: dict) -> None:
    """Small multiples, one measure per panel (each with its own scale), CPU and GPU as two bars."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    e, m, x = data["embeddings"], data["llm"], data["e2e"]
    surface, ink, muted, cpu_colour, gpu_colour = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
    panels = [
        ("Embeddings: indexing throughput", "passages / s, higher is better", e["cpu"]["passages_per_s"], e["cuda"]["passages_per_s"]),
        ("Embeddings: one query, median", "ms, lower is better", e["cpu"]["query_ms_median"], e["cuda"]["query_ms_median"]),
        ("Answer latency, embeddings on CPU or GPU", "s (median, LLM on GPU), lower is better",
         x["llm_verified"]["embeddings_cpu"]["latency_s_median"], x["llm_verified"]["embeddings_cuda"]["latency_s_median"]),
        ("LLM: time to first token, median", "s, lower is better", m["cpu"]["ttft_s_median"], m["gpu"]["ttft_s_median"]),
        ("LLM: output speed, median", "tokens / s, higher is better", m["cpu"]["tokens_per_s_median"], m["gpu"]["tokens_per_s_median"]),
        ("LLM: total time per answer prompt, median", "s, lower is better", m["cpu"]["total_s_median"], m["gpu"]["total_s_median"]),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13, 5.6), facecolor=surface)
    for index, (ax, (title, unit, cpu, gpu)) in enumerate(zip(axes.flat, panels)):
        ax.set_facecolor(surface)
        labels = ["--gpu max", "--gpu off"] if index >= 3 else ["GPU", "CPU"]
        bars = ax.barh(labels, [gpu, cpu], color=[gpu_colour, cpu_colour], height=0.5)
        top = max(cpu, gpu)
        for bar, value in zip(bars, (gpu, cpu)):
            ax.text(value + top * 0.02, bar.get_y() + bar.get_height() / 2, f"{value:g}", va="center", ha="left", color=ink, fontsize=10)
        ax.set_xlim(0, top * 1.22)
        ax.set_title(title, loc="left", fontsize=10.5, color=ink, fontweight="bold")
        ax.set_xlabel(unit, fontsize=9, color=muted)
        ax.tick_params(axis="both", colors=muted, labelsize=9, length=0)
        ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
    s = data["system"]
    fig.suptitle("UniBridge: CPU vs GPU for the embedding model and the local LLM", x=0.012, ha="left", fontsize=13, color=ink, fontweight="bold")
    fig.text(0.012, 0.012, f"{s['cpu']}, {s['logical_threads']} threads  |  {s.get('gpu', '')}  |  {e['model']}  |  "
             f"{m.get('model_name', m['model'])} {m.get('quantization', '')}, context {m['context_length']}  |  source: benchmark_devices.json",
             fontsize=8, color=muted)
    fig.tight_layout(rect=(0, 0.035, 1, 0.95), w_pad=2.5, h_pad=1.8)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=160, facecolor=surface)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="embeddings,llm,e2e")
    ap.add_argument("--model", default="qwen3vl-8b-instruct", help="LM Studio model key (see `lms ls`)")
    ap.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    ap.add_argument("--force", action="store_true", help="measure again parts that are already in the JSON file")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--allow-battery", action="store_true", help="measure even on battery power (throttled hardware)")
    args = ap.parse_args()
    if not args.render_only and on_ac_power() is False and not args.allow_battery:
        raise SystemExit("the laptop is on battery: CPU and GPU are throttled. Plug in the charger and run again.")

    data = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    if not args.render_only:
        todo = [p for p in args.parts.split(",") if p and (args.force or p not in data)]
        print("parts to run:", todo or "none (already measured; use --force)", flush=True)
        max_tokens = unibridge_settings().llm_max_output_tokens
        for part in todo:
            data["system"] = system_info()
            if part == "embeddings":
                lms("unload", "--all")  # the GPU is free for the embedding model
                data[part] = bench_embeddings()
            elif part == "llm":
                data[part] = bench_llm(args.model, args.base_url, build_prompts(bench_questions()), max_tokens)
            elif part == "e2e":
                load_model(args.model, "max")
                data[part] = bench_e2e(args.model, args.base_url, bench_questions())
            else:
                raise SystemExit(f"unknown part {part}")
            data["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            write_json(OUT_JSON, data)
    OUT_MD.write_text(render_markdown(data).rstrip() + "\n", encoding="utf-8", newline="\n")
    if all(k in data for k in ("embeddings", "llm", "e2e")):
        render_chart(data)
        print(f"written {OUT_JSON.name}, {OUT_MD.name}, {OUT_PNG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
