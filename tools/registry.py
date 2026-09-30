"""
tools/registry.py

Curated registry of premier open-source foundations (CNCF, Linux Foundation / LFX,
Apache, GSoC) and dynamic tier-based search strategies for IssueHawk.
"""

from typing import Dict, List, Optional

TIER_LABELS: Dict[str, List[str]] = {
    "apprentice": [
        "good first issue",
        "beginner-friendly",
        "easy",
        "starter",
        "first-timers-only"
    ],
    "contributor": [
        "help wanted",
        "bug",
        "enhancement",
        "good first issue"
    ],
    "core_contributor": [
        "help wanted",
        "enhancement",
        "feature",
        "performance",
        "refactor"
    ],
    "mentorship_ready": [
        "lfx-mentorship",
        "gsoc",
        "help wanted",
        "enhancement",
        "core",
        "RFC",
        "architecture",
        "subsystem"
    ]
}

FOUNDATION_REGISTRY: Dict[str, Dict] = {
    "cncf": {
        "name": "Cloud Native Computing Foundation (CNCF)",
        "badge": "CNCF",
        "repos": [
            "kubernetes/kubernetes",
            "prometheus/prometheus",
            "envoyproxy/envoy",
            "containerd/containerd",
            "argoproj/argo-cd",
            "etcd-io/etcd",
            "helm/helm",
            "cilium/cilium",
            "open-telemetry/opentelemetry-python",
            "open-telemetry/opentelemetry-js",
        ],
        "default_labels": ["help wanted", "good first issue", "enhancement"]
    },
    "lfx": {
        "name": "Linux Foundation Mentorship (LFX)",
        "badge": "LFX",
        "repos": [
            "hyperledger/fabric",
            "graphql/graphql-js",
            "zephyrproject-rtos/zephyr",
            "spdx/tools-python",
            "open-telemetry/opentelemetry-specification",
            "confidential-containers/cloud-api-adaptor",
        ],
        "default_labels": ["lfx-mentorship", "help wanted", "enhancement"]
    },
    "apache": {
        "name": "Apache Software Foundation",
        "badge": "Apache",
        "repos": [
            "apache/airflow",
            "apache/spark",
            "apache/arrow",
            "apache/kafka",
            "apache/superset",
            "apache/iceberg",
            "apache/arrow-datafusion"
        ],
        "default_labels": ["help wanted", "good-first-issue", "enhancement"]
    },
    "gsoc": {
        "name": "Google Summer of Code Participating Orgs",
        "badge": "GSoC",
        "repos": [
            "python/cpython",
            "django/django",
            "pallets/flask",
            "pydantic/pydantic",
            "encode/starlette",
            "fastapi/fastapi",
            "langchain-ai/langchain",
            "facebook/react",
            "vercel/next.js"
        ],
        "default_labels": ["gsoc", "help wanted", "good first issue", "enhancement"]
    }
}

def get_tier_labels(tier: str) -> List[str]:
    """Returns query labels suitable for the developer's experience tier."""
    return TIER_LABELS.get(tier.lower(), TIER_LABELS["contributor"])

def detect_foundation(repo_name: str) -> Optional[str]:
    """Detects if a repo belongs to a known prestigious foundation or program."""
    if not repo_name:
        return None
    repo_lower = repo_name.lower()
    for foundation_key, info in FOUNDATION_REGISTRY.items():
        for r in info["repos"]:
            if r.lower() == repo_lower or repo_lower.startswith(r.split("/")[0].lower() + "/"):
                return info["badge"]
    return None

def get_foundation_repos(foundation_keys: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """
    Returns a flattened list of repos across targeted foundations with their metadata.
    """
    keys = foundation_keys or list(FOUNDATION_REGISTRY.keys())
    matched_repos = []
    seen = set()

    for k in keys:
        f_info = FOUNDATION_REGISTRY.get(k.lower())
        if not f_info:
            continue
        badge = f_info["badge"]
        for repo in f_info["repos"]:
            if repo not in seen:
                seen.add(repo)
                matched_repos.append({
                    "repo": repo,
                    "foundation": badge,
                    "default_labels": f_info["default_labels"]
                })
    return matched_repos
