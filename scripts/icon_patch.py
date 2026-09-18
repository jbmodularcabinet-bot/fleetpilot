from pathlib import Path

p = Path(r"C:\Users\User\Documents\ChatGPT\FleetPilot\apps\web\src\components\navigation.tsx")
s = p.read_text(encoding="utf-8")
repls = {
    "  BarChart3,": "  ChartSpline,",
    "  CreditCard,": "  WalletCards,",
    "  House,": "  Gauge,",
    "  Sparkles,": "  BrainCircuit,",
    "  Users,": "  Building2,",
    "  Workflow,": "  Route,",
    '[Workflow, "Operations"],': '[Route, "Operations"],',
    '[CreditCard, "Money"],': '[WalletCards, "Money"],',
    '[Users, "Customers"],': '[Building2, "Customers"],',
    '[Sparkles, "Intelligence"],': '[BrainCircuit, "Intelligence"],',
    '[BarChart3, "Reports"],': '[ChartSpline, "Reports"],',
    '<House size={19} />': '<Gauge size={19} />',
}
for old, new in repls.items():
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("patched navigation icons")
