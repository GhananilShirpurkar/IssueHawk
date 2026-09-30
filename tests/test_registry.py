from tools.registry import (
    get_tier_labels,
    detect_foundation,
    get_foundation_repos,
    TIER_LABELS,
    FOUNDATION_REGISTRY
)

def test_get_tier_labels():
    apprentice_labels = get_tier_labels("apprentice")
    assert "good first issue" in apprentice_labels
    
    mentorship_labels = get_tier_labels("mentorship_ready")
    assert "lfx-mentorship" in mentorship_labels or "gsoc" in mentorship_labels
    assert "RFC" in mentorship_labels

def test_detect_foundation():
    assert detect_foundation("kubernetes/kubernetes") == "CNCF"
    assert detect_foundation("apache/airflow") == "Apache"
    assert detect_foundation("hyperledger/fabric") == "LFX"
    assert detect_foundation("python/cpython") == "GSoC"
    assert detect_foundation("some-random-user/repo") is None

def test_get_foundation_repos():
    repos = get_foundation_repos(["cncf", "apache"])
    repo_names = [r["repo"] for r in repos]
    assert "kubernetes/kubernetes" in repo_names
    assert "apache/airflow" in repo_names
    for item in repos:
        assert item["foundation"] in ("CNCF", "Apache")
        assert len(item["default_labels"]) > 0
