"""Track A latency pre-flight benchmark.

Sends N sequential POSTs to /describe with a JPEG payload, records end-to-end
and server-reported inference latency, and prints p50/p95/p99.

Uses a persistent HTTP/1.1 keep-alive connection so the TCP handshake is paid
once before the loop, not on every request. A single unmeasured warmup
request opens the connection.

Run with the project venv active:

    source .venv/bin/activate
    python bench_latency.py

The VS Code Remote tunnel must be forwarding localhost:8000 to the VM.
"""

import base64
import http.client
import json
import statistics
import time
from pathlib import Path
from urllib.parse import urlparse

URL = "http://localhost:8000/describe"
IMAGE_PATH = Path("test.jpg")
N = 100
SMOKE_PRINTS = 3  # print full response body for the first N requests
REQUEST_FIELD = "image_b64"  # change if your endpoint expects a different key
INFERENCE_FIELDS = ("inference_ms", "inference_latency_ms", "latency_ms")
RESULTS_PATH = Path("bench_results.json")


def percentile(values, p):
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


def extract_inference_ms(body):
    for key in INFERENCE_FIELDS:
        if key in body:
            return body[key]
    return None


def post(conn, host, port, path, payload, headers):
    """POST over the given connection. Reconnects once on a broken pipe."""
    try:
        conn.request("POST", path, body=payload, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(), conn
    except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError):
        conn.close()
        conn = http.client.HTTPConnection(host, port, timeout=60)
        conn.request("POST", path, body=payload, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(), conn


def main():
    if not IMAGE_PATH.exists():
        raise SystemExit(f"Missing {IMAGE_PATH}. Place a JPEG at this path.")

    image_bytes = IMAGE_PATH.read_bytes()
    print(f"Loaded {IMAGE_PATH} ({len(image_bytes) / 1024:.1f} KB)")

    payload = json.dumps(
        {REQUEST_FIELD: base64.b64encode(image_bytes).decode()}
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }

    parsed = urlparse(URL)
    host = parsed.hostname
    port = parsed.port or 80
    path = parsed.path or "/"

    conn = http.client.HTTPConnection(host, port, timeout=60)
    print(f"Opened persistent connection to {host}:{port}")

    print("Warmup request (not measured)...")
    status, body_bytes, conn = post(conn, host, port, path, payload, headers)
    if status != 200:
        raise SystemExit(
            f"Warmup failed: HTTP {status}: {body_bytes.decode(errors='replace')}"
        )

    results = []
    try:
        for i in range(N):
            t0 = time.perf_counter()
            status, body_bytes, conn = post(conn, host, port, path, payload, headers)
            t1 = time.perf_counter()
            e2e_ms = (t1 - t0) * 1000

            if status != 200:
                print(f"[{i+1}/{N}] HTTP {status}: {body_bytes.decode(errors='replace')}")
                raise SystemExit(1)

            body = json.loads(body_bytes)

            if i < SMOKE_PRINTS:
                print(f"\n--- request {i} response ---")
                print(json.dumps(body, indent=2)[:800])
                print("---\n")

            inference_ms = extract_inference_ms(body)
            record = {"i": i, "end_to_end_ms": e2e_ms, "response": body}
            if inference_ms is not None:
                record["inference_ms"] = inference_ms
            results.append(record)

            suffix = f"  inf={inference_ms:7.1f}ms" if inference_ms is not None else ""
            print(f"[{i+1:3d}/{N}] e2e={e2e_ms:7.1f}ms{suffix}")
    finally:
        conn.close()

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nSaved raw results to {RESULTS_PATH}")

    def col(values, label):
        print(
            f"  {label:<22s} p50={percentile(values, 50):7.0f}  "
            f"p95={percentile(values, 95):7.0f}  "
            f"p99={percentile(values, 99):7.0f}"
        )

    e2e = [r["end_to_end_ms"] for r in results]
    print("\n=== Latency breakdown (ms) ===")
    col(e2e, "end_to_end")

    def collect(key):
        return [r["response"][key] for r in results if key in r.get("response", {})]

    inf = collect("latency_ms")
    img_dec = collect("image_decode_ms")
    pre = collect("preprocess_ms")
    out_dec = collect("output_decode_ms")
    server_total = collect("server_total_ms")

    if server_total:
        col(server_total, "server_total")
    if img_dec:
        col(img_dec, "  image_decode")
    if pre:
        col(pre, "  preprocess")
    if inf:
        col(inf, "  inference (generate)")
    if out_dec:
        col(out_dec, "  output_decode")

    if server_total:
        true_net = [
            r["end_to_end_ms"] - r["response"]["server_total_ms"]
            for r in results
            if "server_total_ms" in r.get("response", {})
        ]
        print()
        col(true_net, "TRUE network (e2e-server)")

        # The old "network" estimate, for comparison with the previous run.
        legacy_net = [
            r["end_to_end_ms"] - r["response"]["latency_ms"]
            for r in results
            if "latency_ms" in r.get("response", {})
        ]
        col(legacy_net, "  (e2e - generate only)")

    res = results[0].get("response", {})
    if "image_width" in res:
        print(f"\nImage resolution as seen by server: {res['image_width']}x{res['image_height']}")

    print("\nNext: paste these numbers into latency_preflight.md and decide.")


if __name__ == "__main__":
    main()
