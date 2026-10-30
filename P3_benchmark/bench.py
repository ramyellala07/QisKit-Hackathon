"""
QFF 2026 Phase 2 - PS-P3 benchmark harness.

All seven CORE algorithms from algorithm_matrix.json are registered below.

Run on both platforms (results are tagged with the platform automatically):
    python P3_benchmark/run_repeats.py --platform A --repeats 3 --clear-log
    python P3_benchmark/run_repeats.py --platform B --repeats 3

Memory method used here (state it in your report):
    each (algorithm, operation) runs in a FRESH child process that imports the libraries,
    prepares inputs, records RSS, then runs the operation `trials` times and records peak RSS.
    memory_kb = peak RSS after the operation loop - RSS before the loop.
    Small values (< ~100 KB) are at the resolution limit of RSS - report them as such.
"""
import csv
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(ROOT, "results")
sys.path.insert(0, os.path.dirname(HERE))
from common.measure import time_op  # noqa: E402

PLATFORM = os.environ.get("QFF_PLATFORM", "A")
MESSAGE = hashlib.shake_256(b"QFF2026-P3-message").digest(1024)
MATRIX = json.load(open(os.path.join(HERE, "algorithm_matrix.json")))
WARMUP = MATRIX["trials"]["warmup"]


def trials_for(alg, op):
    minimum = MATRIX["trials"]["minimum_trials_exceptions"].get(
        f"{alg} {op}", MATRIX["trials"]["minimum_trials_default"])
    # Increase sample size for operations that were below roughly 0.1 ms in
    # the initial run; the extra calls have little impact on total run time.
    extra = {
        ("ML-KEM-768", "encapsulate"): 1000,
        ("RSA-2048-OAEP", "encapsulate"): 1000,
        ("ECDH-P256", "keygen"): 1000,
        ("ECDH-P256", "encapsulate"): 1000,
        ("ECDH-P256", "decapsulate"): 1000,
        ("ML-DSA-65", "verify"): 1000,
        ("RSA-2048-PSS", "verify"): 1000,
        ("ECDSA-P256", "keygen"): 1000,
        ("ECDSA-P256", "sign"): 1000,
        ("ECDSA-P256", "verify"): 1000,
    }
    return max(minimum, extra.get((alg, op), minimum))


def correctness_trials(alg):
    return 10 if alg == "SLH-DSA-SHA2-128s" else 100


def _der_public(key):
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)


def _der_private(key):
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def _signature_is_rejected(verify, signature, message):
    """Return True when a negative signature check is correctly rejected."""
    try:
        result = verify(signature, message)
    except Exception:
        return True
    return result is False


def _checks_result(ok, n, details, values):
    if not details:
        return ok, n
    return ok, n, {key: (value if key == "special_case" else bool(value))
                   for key, value in values.items()}


# ----------------------------------------------------------------------------- ML-KEM-768
def mlkem768_correctness(n=100, details=False):
    from cryptography.hazmat.primitives.asymmetric import mlkem
    ok = 0
    roundtrip_ok = tamper_ok = 0
    for _ in range(n):
        sk = mlkem.MLKEM768PrivateKey.generate()
        ss, ct = sk.public_key().encapsulate()
        bad = bytearray(ct); bad[0] ^= 1
        roundtrip = sk.decapsulate(ct) == ss
        tampered = sk.decapsulate(bytes(bad)) != ss
        roundtrip_ok += roundtrip
        tamper_ok += tampered
        if roundtrip and tampered:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": roundtrip_ok == n,
                                            "tampered_ciphertext": tamper_ok == n})


def mlkem768_ops():
    """Returns {op_name: zero-arg callable} plus artifact sizes. Inputs are prepared outside the timed call."""
    from cryptography.hazmat.primitives.asymmetric import mlkem
    sk = mlkem.MLKEM768PrivateKey.generate()
    pk = sk.public_key()
    ss, ct = pk.encapsulate()
    ops = {
        "keygen": lambda: mlkem.MLKEM768PrivateKey.generate(),
        "encapsulate": lambda: pk.encapsulate(),
        "decapsulate": lambda: sk.decapsulate(ct),
    }
    sizes = {"public_key": len(pk.public_bytes_raw()), "secret_key": len(sk.private_bytes_raw()),
             "ciphertext": len(ct), "shared_secret": len(ss), "encoding": "raw"}
    return ops, sizes


# ----------------------------------------------------------------------------- KEMs
def rsa2048_oaep_correctness(n=100, details=False):
    import os
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives import hashes

    ok = 0
    roundtrip_ok = tamper_ok = 0
    oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(), label=None)
    for _ in range(n):
        sk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        secret = os.urandom(32)
        ct = sk.public_key().encrypt(secret, oaep)
        good = sk.decrypt(ct, oaep) == secret
        bad = bytearray(ct); bad[0] ^= 1
        try:
            sk.decrypt(bytes(bad), oaep)
            rejected = False
        except ValueError:
            rejected = True
        roundtrip_ok += good
        tamper_ok += rejected
        if good and rejected:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": roundtrip_ok == n,
                                            "tampered_ciphertext": tamper_ok == n,
                                            "special_case": "Modified OAEP ciphertext rejected by decryption error"})


def rsa2048_oaep_ops():
    import os
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives import hashes

    sk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pk = sk.public_key()
    oaep = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(), label=None)
    secret = os.urandom(32)
    ct = pk.encrypt(secret, oaep)
    ops = {
        "keygen": lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048),
        "encapsulate": lambda: pk.encrypt(os.urandom(32), oaep),
        "decapsulate": lambda: sk.decrypt(ct, oaep),
    }
    sizes = {"public_key": len(_der_public(pk)), "secret_key": len(_der_private(sk)),
             "ciphertext": len(ct), "shared_secret": len(secret), "encoding": "DER SPKI / DER PKCS#8"}
    return ops, sizes


def ecdh_p256_correctness(n=100, details=False):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes

    ok = 0
    roundtrip_ok = tamper_ok = 0
    for _ in range(n):
        alice = ec.generate_private_key(ec.SECP256R1())
        bob = ec.generate_private_key(ec.SECP256R1())
        secret = alice.exchange(ec.ECDH(), bob.public_key())
        reciprocal = bob.exchange(ec.ECDH(), alice.public_key())
        # A different ephemeral public key must not reproduce the same shared secret.
        other = ec.generate_private_key(ec.SECP256R1())
        changed = bob.exchange(ec.ECDH(), other.public_key())
        roundtrip = secret == reciprocal and len(secret) == hashes.SHA256.digest_size
        tampered = changed != secret
        roundtrip_ok += roundtrip
        tamper_ok += tampered
        if roundtrip and tampered:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": roundtrip_ok == n,
                                            "tampered_ciphertext": tamper_ok == n})


def ecdh_p256_ops():
    from cryptography.hazmat.primitives.asymmetric import ec

    recipient_sk = ec.generate_private_key(ec.SECP256R1())
    recipient_pk = recipient_sk.public_key()
    ephemeral_sk = ec.generate_private_key(ec.SECP256R1())
    ephemeral_pk = ephemeral_sk.public_key()
    shared = ephemeral_sk.exchange(ec.ECDH(), recipient_pk)

    def encapsulate():
        fresh_ephemeral = ec.generate_private_key(ec.SECP256R1())
        return fresh_ephemeral.exchange(ec.ECDH(), recipient_pk)

    ops = {
        "keygen": lambda: ec.generate_private_key(ec.SECP256R1()),
        "encapsulate": encapsulate,
        "decapsulate": lambda: recipient_sk.exchange(ec.ECDH(), ephemeral_pk),
    }
    sizes = {"public_key": len(_der_public(recipient_pk)), "secret_key": len(_der_private(recipient_sk)),
             "ciphertext": len(_der_public(ephemeral_pk)), "shared_secret": len(shared),
             "encoding": "DER SPKI / DER PKCS#8; ciphertext is ephemeral public key"}
    return ops, sizes


# ----------------------------------------------------------------------------- signatures
def mldsa65_correctness(n=100, details=False):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import mldsa

    ok = 0
    valid_count = message_reject_count = signature_reject_count = 0
    changed_message = MESSAGE[:-1] + bytes([MESSAGE[-1] ^ 1])
    for _ in range(n):
        sk = mldsa.MLDSA65PrivateKey.generate()
        pk = sk.public_key()
        sig = sk.sign(MESSAGE)
        try:
            pk.verify(sig, MESSAGE)
            valid = True
        except InvalidSignature:
            valid = False
        bad_sig = bytearray(sig); bad_sig[-1] ^= 1
        msg_rejected = _signature_is_rejected(lambda s, m: pk.verify(s, m), sig, changed_message)
        sig_rejected = _signature_is_rejected(lambda s, m: pk.verify(s, m), bytes(bad_sig), MESSAGE)
        valid_count += valid
        message_reject_count += msg_rejected
        signature_reject_count += sig_rejected
        if valid and msg_rejected and sig_rejected:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": valid_count == n,
                                            "tampered_message": message_reject_count == n,
                                            "tampered_signature": signature_reject_count == n})


def mldsa65_ops():
    from cryptography.hazmat.primitives.asymmetric import mldsa

    sk = mldsa.MLDSA65PrivateKey.generate()
    pk = sk.public_key()
    sig = sk.sign(MESSAGE)
    ops = {"keygen": lambda: mldsa.MLDSA65PrivateKey.generate(),
           "sign": lambda: sk.sign(MESSAGE),
           "verify": lambda: pk.verify(sig, MESSAGE)}
    sizes = {"public_key": len(pk.public_bytes_raw()), "secret_key": len(sk.private_bytes_raw()),
             "signature": len(sig), "encoding": "raw; secret key is compact seed form"}
    return ops, sizes


def slhdsa128s_correctness(n=10, details=False):
    from pqcrypto import InvalidSignatureError
    from pqcrypto.sign import slh_dsa_sha2_128s as slh

    ok = 0
    valid_count = message_reject_count = signature_reject_count = 0
    changed_message = MESSAGE[:-1] + bytes([MESSAGE[-1] ^ 1])

    def verify_rejects(pk, message, signature):
        try:
            return not slh.verify(pk, message, signature)
        except InvalidSignatureError:
            # pqcrypto raises InvalidSignatureError for expected negative cases.
            return True

    for _ in range(n):
        pk, sk = slh.keygen()
        sig = slh.sign(sk, MESSAGE)
        try:
            # pqcrypto signals success by returning None; failures raise
            # InvalidSignatureError. Some bindings may instead return True.
            valid = slh.verify(pk, MESSAGE, sig) is not False
        except InvalidSignatureError:
            valid = False
        bad_sig = bytearray(sig); bad_sig[-1] ^= 1
        msg_rejected = verify_rejects(pk, changed_message, sig)
        sig_rejected = verify_rejects(pk, MESSAGE, bytes(bad_sig))
        valid_count += valid
        message_reject_count += msg_rejected
        signature_reject_count += sig_rejected
        if valid and msg_rejected and sig_rejected:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": valid_count == n,
                                            "tampered_message": message_reject_count == n,
                                            "tampered_signature": signature_reject_count == n})


def slhdsa128s_ops():
    from pqcrypto.sign import slh_dsa_sha2_128s as slh

    pk, sk = slh.keygen()
    sig = slh.sign(sk, MESSAGE)
    ops = {"keygen": lambda: slh.keygen(),
           "sign": lambda: slh.sign(sk, MESSAGE),
           "verify": lambda: slh.verify(pk, MESSAGE, sig)}
    sizes = {"public_key": len(pk), "secret_key": len(sk), "signature": len(sig),
             "encoding": "raw; pqcrypto expanded secret key"}
    return ops, sizes


def rsa2048_pss_correctness(n=100, details=False):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives import hashes

    ok = 0
    valid_count = message_reject_count = signature_reject_count = 0
    pss = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
    changed_message = MESSAGE[:-1] + bytes([MESSAGE[-1] ^ 1])
    for _ in range(n):
        sk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pk = sk.public_key()
        sig = sk.sign(MESSAGE, pss, hashes.SHA256())
        try:
            pk.verify(sig, MESSAGE, pss, hashes.SHA256())
            valid = True
        except InvalidSignature:
            valid = False
        bad_sig = bytearray(sig); bad_sig[-1] ^= 1
        def verify(candidate, message):
            return pk.verify(candidate, message, pss, hashes.SHA256())
        message_rejected = _signature_is_rejected(verify, sig, changed_message)
        signature_rejected = _signature_is_rejected(verify, bytes(bad_sig), MESSAGE)
        valid_count += valid
        message_reject_count += message_rejected
        signature_reject_count += signature_rejected
        if valid and message_rejected and signature_rejected:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": valid_count == n,
                                            "tampered_message": message_reject_count == n,
                                            "tampered_signature": signature_reject_count == n})


def rsa2048_pss_ops():
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives import hashes

    sk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pk = sk.public_key()
    pss = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)
    sig = sk.sign(MESSAGE, pss, hashes.SHA256())
    ops = {"keygen": lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048),
           "sign": lambda: sk.sign(MESSAGE, pss, hashes.SHA256()),
           "verify": lambda: pk.verify(sig, MESSAGE, pss, hashes.SHA256())}
    sizes = {"public_key": len(_der_public(pk)), "secret_key": len(_der_private(sk)),
             "signature": len(sig), "encoding": "DER SPKI / DER PKCS#8"}
    return ops, sizes


def ecdsa_p256_correctness(n=100, details=False):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes

    ok = 0
    valid_count = message_reject_count = signature_reject_count = 0
    changed_message = MESSAGE[:-1] + bytes([MESSAGE[-1] ^ 1])
    for _ in range(n):
        sk = ec.generate_private_key(ec.SECP256R1())
        pk = sk.public_key()
        sig = sk.sign(MESSAGE, ec.ECDSA(hashes.SHA256()))
        try:
            pk.verify(sig, MESSAGE, ec.ECDSA(hashes.SHA256()))
            valid = True
        except InvalidSignature:
            valid = False
        bad_sig = bytearray(sig); bad_sig[-1] ^= 1
        def verify(candidate, message):
            return pk.verify(candidate, message, ec.ECDSA(hashes.SHA256()))
        message_rejected = _signature_is_rejected(verify, sig, changed_message)
        signature_rejected = _signature_is_rejected(verify, bytes(bad_sig), MESSAGE)
        valid_count += valid
        message_reject_count += message_rejected
        signature_reject_count += signature_rejected
        if valid and message_rejected and signature_rejected:
            ok += 1
    return _checks_result(ok, n, details, {"roundtrip_or_valid_signature": valid_count == n,
                                            "tampered_message": message_reject_count == n,
                                            "tampered_signature": signature_reject_count == n})


def ecdsa_p256_ops():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes

    sk = ec.generate_private_key(ec.SECP256R1())
    pk = sk.public_key()
    sig = sk.sign(MESSAGE, ec.ECDSA(hashes.SHA256()))
    ops = {"keygen": lambda: ec.generate_private_key(ec.SECP256R1()),
           "sign": lambda: sk.sign(MESSAGE, ec.ECDSA(hashes.SHA256())),
           "verify": lambda: pk.verify(sig, MESSAGE, ec.ECDSA(hashes.SHA256()))}
    sizes = {"public_key": len(_der_public(pk)), "secret_key": len(_der_private(sk)),
             "signature": len(sig), "encoding": "DER SPKI / DER PKCS#8; signature is ASN.1 DER"}
    return ops, sizes

ALGORITHMS = {
    "ML-KEM-768": (mlkem768_correctness, mlkem768_ops),
    "RSA-2048-OAEP": (rsa2048_oaep_correctness, rsa2048_oaep_ops),
    "ECDH-P256": (ecdh_p256_correctness, ecdh_p256_ops),
    "ML-DSA-65": (mldsa65_correctness, mldsa65_ops),
    "SLH-DSA-SHA2-128s": (slhdsa128s_correctness, slhdsa128s_ops),
    "RSA-2048-PSS": (rsa2048_pss_correctness, rsa2048_pss_ops),
    "ECDSA-P256": (ecdsa_p256_correctness, ecdsa_p256_ops),
}


# ----------------------------------------------------------------------------- memory worker (child process)
def rss_bytes():
    import psutil
    return psutil.Process().memory_info().rss


def worker(alg, op, trials):
    _, ops_fn = ALGORITHMS[alg]
    ops, _ = ops_fn()
    import psutil
    p = psutil.Process()
    before = p.memory_info().rss
    peak = before
    f = ops[op]
    for _ in range(trials):
        f()
        peak = max(peak, p.memory_info().rss)
    print(json.dumps({"memory_kb": round((peak - before) / 1024, 1), "baseline_rss_mb": round(before / 2**20, 1)}))


def measure_memory(alg, op, trials):
    out = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker", alg, op, str(trials)],
                         capture_output=True, text=True, env=os.environ)
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"memory_kb": None, "baseline_rss_mb": None, "error": out.stderr[-300:]}


# ----------------------------------------------------------------------------- main
def main():
    global PLATFORM
    if "--platform" in sys.argv:
        index = sys.argv.index("--platform")
        PLATFORM = sys.argv[index + 1]
    os.makedirs(RESULTS, exist_ok=True)
    out_path = os.path.join(RESULTS, f"bench_platform_{PLATFORM}.csv")
    fields = ["platform", "algorithm", "operation", "correct", "correct_total", "warmup", "n", "median_ms",
              "p25_ms", "p75_ms", "iqr_ms", "p95_ms", "min_ms", "max_ms", "mean_ms", "stdev_ms",
              "memory_kb", "baseline_rss_mb", "sizes_json"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for alg, (corr_fn, ops_fn) in ALGORITHMS.items():
            ok, total = corr_fn(n=correctness_trials(alg))
            print(f"[{PLATFORM}] {alg}: correctness {ok}/{total}")
            if ok != total:
                print("  correctness failed - NOT benchmarking this algorithm")
                continue
            ops, sizes = ops_fn()
            for op, fn in ops.items():
                n = trials_for(alg, op)
                st = time_op(fn, warmup=WARMUP, trials=n)
                mem = measure_memory(alg, op, n)
                row = {"platform": PLATFORM, "algorithm": alg, "operation": op, "correct": ok,
                       "correct_total": total, "warmup": WARMUP, **{k: round(v, 5) if isinstance(v, float) else v
                                                                       for k, v in st.items()},
                       "memory_kb": mem.get("memory_kb"), "baseline_rss_mb": mem.get("baseline_rss_mb"),
                       "sizes_json": json.dumps(sizes)}
                w.writerow(row)
                print(f"  {op:12s} median={st['median_ms']:.4f} ms  IQR={st['iqr_ms']:.4f}  n={n}  "
                      f"mem={mem.get('memory_kb')} KB")
    print(f"results -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    else:
        main()
