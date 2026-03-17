"""
zkp.py — легковесный Schnorr NIZK для P2P аутентификации нод.
Не требует внешних зависимостей и работает поверх текущего транспорта.
"""
import hashlib
import secrets
import time


class ArgosZKPEngine:
    P = int(
        "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
        "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
        "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
        "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
        "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
        "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
        "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
        "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
        "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
        "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
        "15728E5A8AACAA68FFFFFFFFFFFFFFFF",
        16,
    )
    G = 2
    Q = P - 1

    def __init__(self, node_id: str, network_secret: str, enabled: bool = False):
        self.node_id = (node_id or "").strip()
        self.enabled = bool(enabled)
        self._secret = self._derive_secret(network_secret or "")
        self._public = pow(self.G, self._secret, self.P)

    def _derive_secret(self, network_secret: str) -> int:
        raw = f"{network_secret}|{self.node_id}|argos-zkp-v1".encode("utf-8")
        val = int(hashlib.sha256(raw).hexdigest(), 16) % self.Q
        return max(2, val)

    def public_hex(self) -> str:
        return format(self._public, "x")

    def challenge(self, action: str, request_id: str = "", payload_hint: str = "") -> str:
        seed = f"{self.node_id}|{action}|{request_id}|{payload_hint}".encode("utf-8")
        return hashlib.sha256(seed).hexdigest()

    def sign(self, challenge: str) -> dict:
        nonce = secrets.randbelow(self.Q - 2) + 2
        commit = pow(self.G, nonce, self.P)
        c = self._hash_challenge(challenge, self._public, commit)
        response = (nonce + c * self._secret) % self.Q
        return {
            "node_id": self.node_id,
            "pub": self.public_hex(),
            "commit": format(commit, "x"),
            "response": format(response, "x"),
            "ts": int(time.time()),
        }

    def _hash_challenge(self, challenge: str, pub: int, commit: int) -> int:
        data = f"{challenge}|{format(pub,'x')}|{format(commit,'x')}".encode()
        return int(hashlib.sha256(data).hexdigest(), 16) % self.Q

    def verify(self, proof: dict, challenge: str,
               expected_node_id: str = None,
               expected_pub_hex: str = None,
               max_age_sec: int = 180) -> bool:
        if not isinstance(proof, dict):
            return False
        try:
            ts = int(proof.get("ts", 0))
            if abs(time.time() - ts) > max_age_sec:
                return False
            pub_hex = str(proof.get("pub", ""))
            commit_hex = str(proof.get("commit", ""))
            resp_hex = str(proof.get("response", ""))
            pub = int(pub_hex, 16)
            commit = int(commit_hex, 16)
            response = int(resp_hex, 16)
            if expected_pub_hex and pub_hex != expected_pub_hex:
                return False
            if expected_node_id and proof.get("node_id") != expected_node_id:
                return False
            c = self._hash_challenge(challenge, pub, commit)
            lhs = pow(self.G, response, self.P)
            rhs = (commit * pow(pub, c, self.P)) % self.P
            return lhs == rhs
        except Exception:
            return False

    def status(self) -> str:
        return (
            f"🔐 ZKP Engine:\n"
            f"  Enabled:  {self.enabled}\n"
            f"  Node ID:  {self.node_id[:16]}...\n"
            f"  Public:   {self.public_hex()[:24]}..."
        )
