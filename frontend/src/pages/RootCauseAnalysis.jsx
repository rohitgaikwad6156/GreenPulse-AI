import { ChartNoAxesCombined } from "lucide-react";
import PlaceholderPage from "../components/PlaceholderPage.jsx";

export default function RootCauseAnalysis() {
  return (
    <PlaceholderPage
      eyebrow="Model interpretation"
      title="Root Cause Analysis"
      description="Inspect how recorded features contribute to an XGBoost LST prediction. SHAP explanations describe model behavior, not causal effects."
      icon={ChartNoAxesCombined}
      emptyTitle="No model explanation available"
      emptyDescription="Feature contributions will appear after a validated LST model is trained and a grid cell is selected."
      plannedItems={["Cell-level SHAP contributions in °C", "Grouped vegetation and built-environment factors", "Model baseline and feature provenance"]}
    />
  );
}
