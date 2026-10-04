"""Reject explicitly non-production artifacts before model use."""


def reject_demo_metadata(metadata: dict) -> None:
    """Legacy metadata can be unlabeled; explicit demo/synthetic labels cannot pass.

    Real source verification is enforced by the pipeline manifest, including hashes.
    This additional guard stops existing labeled demo artifacts in production paths.
    """
    for key in ("source", "data_type", "data_classification"):
        label = str(metadata.get(key, "")).lower()
        if "demo" in label or "synthetic" in label:
            raise ValueError("Demo/synthetic artifacts cannot supply real LST predictions; run the real heat-map pipeline")
